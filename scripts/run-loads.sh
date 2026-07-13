#!/usr/bin/env bash

set -uo pipefail

print_usage() {
  cat <<'EOF'
Usage:
  ./scripts/run-loads.sh [options] [profile1 profile2 ...]

Options:
  --interactive     Pick load profiles from a terminal menu.
  --parallel        Run selected profiles in parallel.
  --all             Run all profiles from load/*.js (default if no profiles provided).
  --out-dir DIR     Base output directory (default: results).
  --dry-run         Validate/inspect scripts and create run folder without executing k6 load.
  -h, --help        Show this help message.

Examples:
  ./scripts/run-loads.sh --interactive
  ./scripts/run-loads.sh steady
  ./scripts/run-loads.sh spike sawtooth
  ./scripts/run-loads.sh --parallel spike sawtooth
  ./scripts/run-loads.sh --all
EOF
}

if ! command -v k6 >/dev/null 2>&1; then
  echo "ERROR: k6 is not installed or not in PATH"
  exit 1
fi

parallel_mode=0
run_all=0
dry_run=0
interactive_mode=0
output_base="results"

declare -a requested_profiles=()
declare -a available_profiles=()

auto_profiles() {
  local f
  for f in load/*.js; do
    [ -f "$f" ] || continue
    basename "$f" .js
  done
}

load_available_profiles() {
  available_profiles=()
  while IFS= read -r p; do
    [ -n "$p" ] && available_profiles+=("$p")
  done < <(auto_profiles)
}

add_unique_profile() {
  local target="$1"
  local existing
  if [ "${#requested_profiles[@]}" -gt 0 ]; then
    for existing in "${requested_profiles[@]}"; do
      [ "$existing" = "$target" ] && return 0
    done
  fi
  requested_profiles+=("$target")
}

interactive_pick_profiles() {
  local idx mode choice token profile

  load_available_profiles
  if [ "${#available_profiles[@]}" -eq 0 ]; then
    echo "ERROR: no load profiles found under load/*.js"
    exit 1
  fi

  echo "Available load profiles:"
  for idx in "${!available_profiles[@]}"; do
    printf '  %d) %s\n' "$((idx + 1))" "${available_profiles[$idx]}"
  done

  echo
  echo "Execution mode:"
  echo "  1) single profile"
  echo "  2) multiple profiles (sequential)"
  echo "  3) multiple profiles (parallel)"
  echo "  4) all profiles"
  echo "  5) cancel"
  read -r -p "Choose mode [1-5]: " mode

  case "$mode" in
    1)
      read -r -p "Choose profile number: " choice
      case "$choice" in
        ''|*[!0-9]*)
          echo "ERROR: expected a numeric choice"
          exit 1
          ;;
      esac
      if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#available_profiles[@]}" ]; then
        echo "ERROR: choice out of range"
        exit 1
      fi
      add_unique_profile "${available_profiles[$((choice - 1))]}"
      ;;
    2|3)
      [ "$mode" = "3" ] && parallel_mode=1
      echo "Enter profile numbers separated by spaces (or type 'all')."
      read -r -p "Selection: " choice
      if [ "$choice" = "all" ]; then
        run_all=1
      else
        for token in $choice; do
          case "$token" in
            ''|*[!0-9]*)
              echo "ERROR: '$token' is not a valid number"
              exit 1
              ;;
          esac
          if [ "$token" -lt 1 ] || [ "$token" -gt "${#available_profiles[@]}" ]; then
            echo "ERROR: selection out of range: $token"
            exit 1
          fi
          profile="${available_profiles[$((token - 1))]}"
          add_unique_profile "$profile"
        done
      fi
      ;;
    4)
      run_all=1
      ;;
    5)
      echo "Cancelled"
      exit 0
      ;;
    *)
      echo "ERROR: invalid mode"
      exit 1
      ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --interactive)
      interactive_mode=1
      shift
      ;;
    --parallel)
      parallel_mode=1
      shift
      ;;
    --all)
      run_all=1
      shift
      ;;
    --out-dir)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --out-dir requires a value"
        exit 1
      fi
      output_base="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      requested_profiles+=("$1")
      shift
      ;;
  esac
done

if [ "$interactive_mode" -eq 1 ]; then
  interactive_pick_profiles
fi

if [ "$run_all" -eq 1 ] || [ "${#requested_profiles[@]}" -eq 0 ]; then
  load_available_profiles
  requested_profiles=("${available_profiles[@]}")
fi

if [ "${#requested_profiles[@]}" -eq 0 ]; then
  echo "ERROR: no load profiles found under load/*.js"
  exit 1
fi

for p in "${requested_profiles[@]}"; do
  p="${p%.js}"
  if [ ! -f "load/${p}.js" ]; then
    echo "ERROR: load profile not found: load/${p}.js"
    exit 1
  fi
done

timestamp="$(date +%Y%m%d_%H%M%S)"
run_dir="${output_base}/load_runs_${timestamp}"
json_dir="${run_dir}/json"
log_dir="${run_dir}/logs"
mkdir -p "$json_dir" "$log_dir"

status_file="${run_dir}/status.txt"

{
  printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'parallel=%s\n' "$parallel_mode"
  printf 'dry_run=%s\n' "$dry_run"
  printf 'profiles=%s\n' "${requested_profiles[*]}"
} > "$status_file"

echo "Run directory: $run_dir"

run_one() {
  local profile="$1"
  local summary_path="${json_dir}/${profile}_summary.json"
  local log_path="${log_dir}/${profile}.log"

  if [ "$dry_run" -eq 1 ]; then
    {
      echo "[dry-run] Inspecting load/${profile}.js"
      k6 inspect "load/${profile}.js"
    } > "$log_path" 2>&1
    local exit_code=$?
    printf '%s exit_code=%s\n' "$profile" "$exit_code" >> "$status_file"
    return "$exit_code"
  fi

  k6 run "load/${profile}.js" --summary-export "$summary_path" > "$log_path" 2>&1
  local exit_code=$?
  printf '%s exit_code=%s\n' "$profile" "$exit_code" >> "$status_file"
  return "$exit_code"
}

overall_exit=0

if [ "$parallel_mode" -eq 1 ] && [ "${#requested_profiles[@]}" -gt 1 ]; then
  declare -a pids=()
  declare -a pid_profiles=()

  for profile in "${requested_profiles[@]}"; do
    run_one "$profile" &
    pid=$!
    pids+=("$pid")
    pid_profiles+=("$profile")
  done

  for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    profile="${pid_profiles[$i]}"
    if ! wait "$pid"; then
      overall_exit=1
      echo "Profile failed: $profile"
    fi
  done
else
  for profile in "${requested_profiles[@]}"; do
    if ! run_one "$profile"; then
      overall_exit=1
      echo "Profile failed: $profile"
    fi
  done
fi

{
  printf 'finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'overall_exit=%s\n' "$overall_exit"
} >> "$status_file"

if [ "$overall_exit" -eq 0 ]; then
  echo "All requested loads completed successfully."
else
  echo "One or more load profiles failed."
fi

echo "Artifacts:"
echo "- Status: ${status_file}"
echo "- JSON summaries: ${json_dir}"
echo "- Logs: ${log_dir}"

exit "$overall_exit"
