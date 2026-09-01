#!/usr/bin/env bash

set -uo pipefail

AGGREGATE_LOG_FILE=""
APP_PORT_FORWARD_PID=""

capture_replica_samples() {
  local output_path="$1"
  while true; do
    local snapshot
    snapshot="$(kubectl get deployment demo-app -n thesis-autoscaling \
      -o jsonpath='{.spec.replicas},{.status.readyReplicas}' 2>/dev/null || true)"
    if [ -n "$snapshot" ]; then
      local desired current
      desired="${snapshot%,*}"
      current="${snapshot#*,}"
      printf '{"timestamp_epoch":%s,"desired_replicas":%s,"current_replicas":%s}\n' \
        "$(date +%s)" "${desired:-0}" "${current:-0}" >> "$output_path"
    fi
    sleep 5
  done
}

cleanup_app_port_forward() {
  if [ -n "$APP_PORT_FORWARD_PID" ]; then
    kill "$APP_PORT_FORWARD_PID" 2>/dev/null || true
  fi
}
trap cleanup_app_port_forward EXIT INT TERM

ensure_app_reachable() {
  if curl -fsS --max-time 2 http://localhost:8000/health >/dev/null 2>&1; then
    return 0
  fi

  kubectl port-forward svc/demo-app 8000:8000 -n thesis-autoscaling \
    > "${TMPDIR:-/tmp}/demo-app-port-forward.log" 2>&1 &
  APP_PORT_FORWARD_PID=$!

  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 http://localhost:8000/health >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$APP_PORT_FORWARD_PID" 2>/dev/null; then
      echo "ERROR: demo app port-forward failed; see ${TMPDIR:-/tmp}/demo-app-port-forward.log" >&2
      return 1
    fi
    sleep 1
  done

  echo "ERROR: demo app is not reachable at http://localhost:8000" >&2
  return 1
}

stage_log() {
  local stage="$1"
  shift
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[load-runner] ts=${ts} stage=${stage} $*"
}

append_profile_jsonl() {
  local jsonl_path="$1"
  local event="$2"
  local profile="$3"
  local dry_run_value="$4"
  local exit_code_value="$5"
  local summary_path_value="$6"
  local log_path_value="$7"
  local start_replicas_value="$8"
  local timeline_log_path_value="$9"
  local ts

  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [ -n "$summary_path_value" ]; then
    printf '{"ts":"%s","event":"%s","profile":"%s","dry_run":%s,"exit_code":%s,"summary_path":"%s","log_path":"%s","start_replicas":"%s","autoscaler_timeline_log":"%s"}\n' \
      "$ts" "$event" "$profile" "$dry_run_value" "$exit_code_value" "$summary_path_value" "$log_path_value" "$start_replicas_value" "$timeline_log_path_value" >> "$jsonl_path"
  else
    printf '{"ts":"%s","event":"%s","profile":"%s","dry_run":%s,"exit_code":%s,"summary_path":null,"log_path":"%s","start_replicas":"%s","autoscaler_timeline_log":"%s"}\n' \
      "$ts" "$event" "$profile" "$dry_run_value" "$exit_code_value" "$log_path_value" "$start_replicas_value" "$timeline_log_path_value" >> "$jsonl_path"
  fi
}

print_usage() {
  cat <<'EOF'
Usage:
  ./scripts/run-loads.sh [options] [profile1 profile2 ...]

Options:
  --interactive     Pick load profiles from a terminal menu.
  --parallel        Run selected profiles in parallel.
  --all             Run all profiles from load/*.js (default if no profiles provided).
  --out-dir DIR     Base output directory (default: storage/runs).
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
output_base="storage/runs"

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

detect_start_replicas() {
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  kubectl get deployment demo-app \
    -n thesis-autoscaling \
    -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "unknown"
}

append_autoscaler_diagnostics() {
  local log_path="$1"

  if ! command -v kubectl >/dev/null 2>&1; then
    {
      echo
      echo "[autoscaler-check] kubectl unavailable, skipped diagnostics"
    } >> "$log_path"
    return 0
  fi

  local recent_errors
  recent_errors="$(kubectl logs deployment/agent-autoscaler -n thesis-autoscaling -c agent-autoscaler --since=5m 2>/dev/null | grep -E 'cycle_error|exception:control_loop|Cycle failed|Traceback' | tail -n 30 || true)"

  {
    echo
    echo "[autoscaler-check] recent control-loop diagnostics"
    if [ -n "$recent_errors" ]; then
      echo "[autoscaler-check] WARNING: recent autoscaler errors detected"
      echo "$recent_errors"
    else
      echo "[autoscaler-check] OK: no recent control-loop errors in last 5m"
    fi
  } >> "$log_path"
}

append_system_health_status() {
  local output_log="$1"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if ! command -v kubectl >/dev/null 2>&1; then
    {
      echo "[system] ts=${ts} status=SYSTEM_ERROR reason=kubectl_unavailable"
    } >> "$output_log"
    return 0
  fi

  local app_ready
  local app_spec
  local auto_ready
  local auto_spec
  local status="SYSTEM_OK"
  local reason="all_checks_passed"

  app_ready="$(kubectl get deploy demo-app -n thesis-autoscaling -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "")"
  app_spec="$(kubectl get deploy demo-app -n thesis-autoscaling -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "")"
  auto_ready="$(kubectl get deploy agent-autoscaler -n thesis-autoscaling -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "")"
  auto_spec="$(kubectl get deploy agent-autoscaler -n thesis-autoscaling -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "")"

  if [ -z "$app_spec" ] || [ -z "$auto_spec" ]; then
    status="SYSTEM_ERROR"
    reason="deployment_query_failed"
  elif [ "${app_ready:-0}" -lt "${app_spec:-0}" ] || [ "${auto_ready:-0}" -lt "${auto_spec:-0}" ]; then
    status="SYSTEM_ERROR"
    reason="deployment_not_ready"
  fi

  local recent_errors
  recent_errors="$(kubectl logs deployment/agent-autoscaler -n thesis-autoscaling -c agent-autoscaler --since=5m 2>/dev/null | grep -E 'cycle_error|exception:control_loop|Cycle failed|Traceback' | tail -n 20 || true)"
  if [ -n "$recent_errors" ]; then
    status="SYSTEM_ERROR"
    reason="autoscaler_runtime_errors"
  fi

  {
    echo "[system] ts=${ts} status=${status} reason=${reason} app_ready=${app_ready:-0}/${app_spec:-0} autoscaler_ready=${auto_ready:-0}/${auto_spec:-0}"
    if [ -n "$recent_errors" ]; then
      echo "[system] recent_autoscaler_errors_start"
      echo "$recent_errors"
      echo "[system] recent_autoscaler_errors_end"
    fi
  } >> "$output_log"
}

get_autoscaler_pod() {
  if ! command -v kubectl >/dev/null 2>&1; then
    echo ""
    return 0
  fi
  kubectl get pod -n thesis-autoscaling -l app=agent-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo ""
}

get_control_log_offset() {
  local pod
  pod="$(get_autoscaler_pod)"
  if [ -z "$pod" ]; then
    echo ""
    return 0
  fi

  kubectl exec -n thesis-autoscaling "$pod" -c agent-autoscaler -- sh -c 'wc -c < /service/storage/logs/autoscaler/control.log' 2>/dev/null | tr -d '[:space:]'
}

capture_control_log_window() {
  local start_offset="$1"
  local output_file="$2"
  local pod
  local end_offset

  pod="$(get_autoscaler_pod)"
  if [ -z "$pod" ]; then
    echo "[aggregate] autoscaler pod not found" >> "$output_file"
    return 0
  fi

  end_offset="$(kubectl exec -n thesis-autoscaling "$pod" -c agent-autoscaler -- sh -c 'wc -c < /service/storage/logs/autoscaler/control.log' 2>/dev/null | tr -d '[:space:]')"

  if [ -z "$start_offset" ] || [ -z "$end_offset" ]; then
    echo "[aggregate] control.log offsets unavailable" >> "$output_file"
    return 0
  fi

  if [ "$end_offset" -le "$start_offset" ]; then
    echo "[aggregate] no new autoscaler control.log content during profile window" >> "$output_file"
    return 0
  fi

  kubectl exec -n thesis-autoscaling "$pod" -c agent-autoscaler -- sh -c "tail -c +$((start_offset + 1)) /service/storage/logs/autoscaler/control.log" 2>/dev/null >> "$output_file" || {
    echo "[aggregate] failed to read control.log window" >> "$output_file"
    return 0
  }
}

append_story_from_window() {
  local profile="$1"
  local window_file="$2"
  local output_file="$3"
  local dry_run_value="$4"
  local start_offset="$5"
  local timeline_events
  local control_events

  {
    echo "[story] chapter_start profile=${profile}"
    echo "[story] context dry_run=${dry_run_value} control_log_start_offset=${start_offset:-unknown}"
  } >> "$output_file"

  timeline_events="$(grep 'autoscaler\.timeline' "$window_file" || true)"

  if [ -n "$timeline_events" ]; then
    {
      echo "[story] source=timeline"
      echo "$timeline_events" | \
        sed -E 's/^([0-9-]+ [0-9:,]+) INFO autoscaler\.timeline \[([^]]+)\] cycle=([^ ]+) (.*)$/[story] ts=\1 cycle=\3 stage=\2 message=\4/'
    } >> "$output_file"
  else
    control_events="$(grep -E 'lifecycle:cycle_start|metrics:snapshot|agents:aggregate_votes|aggregation:final|safety:|replicas:|lifecycle:cycle_end|errors:cycle:|exception:control_loop' "$window_file" || true)"
    {
      if [ -n "$control_events" ]; then
        echo "[story] source=control_events"
        echo "$control_events" | \
          sed -E 's/^([0-9-]+ [0-9:,]+) INFO autoscaler\.[^.]+ \[(.*)\] (.*)$/[story] ts=\1 event=\2 details=\3/'
      else
        echo "[story] source=none"
        echo "[story] no_events_observed reason=no_autoscaler_control_log_delta"
      fi
    } >> "$output_file"
  fi

  {
    echo "[story] chapter_end profile=${profile}"
  } >> "$output_file"
}

append_aggregate_autoscaler_window() {
  local profile="$1"
  local start_offset="$2"
  local profile_log="$3"
  local ts
  local window_file
  local key_summary

  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  window_file="$(mktemp "${TMPDIR:-/tmp}/autoscaler-window.XXXXXX")"

  capture_control_log_window "$start_offset" "$window_file"
  grep 'autoscaler\.timeline' "$window_file" >> "$RUN_TIMELINE_LOG" || true

  {
    echo
    echo "================================================================================"
    echo "[aggregate] PROFILE REPORT BEGIN profile=${profile} ts=${ts}"
    echo "[aggregate] ts=${ts} profile=${profile}"
    if grep -Eq 'errors:cycle:|exception:control_loop|\\[error\\] cycle=|Traceback' "$window_file"; then
      echo "[aggregate] status=SYSTEM_ERROR reason=autoscaler_runtime_failure"
      echo "[aggregate] error_context_start"
      cat "$window_file"
      echo "[aggregate] error_context_end"
    else
      echo "[aggregate] status=SYSTEM_OK reason=no_runtime_failure"
      key_summary="$(python3 analysis/aggregate_decision_log.py "$window_file" 2>/dev/null || true)"
      if [ -n "$key_summary" ]; then
        echo "[aggregate] decision_summary_start"
        echo "$key_summary"
        echo "[aggregate] decision_summary_end"
      else
        echo "[aggregate] decision_summary_empty"
      fi
    fi
  } >> "$AGGREGATE_LOG_FILE"

  append_story_from_window "$profile" "$window_file" "$profile_log" "$dry_run" "$start_offset"

  {
    echo "[aggregate] PROFILE REPORT END profile=${profile}"
    echo "================================================================================"
    echo
    echo "[run] aggregate_log=${AGGREGATE_LOG_FILE}"
    tail -n 120 "$AGGREGATE_LOG_FILE"
  } >> "$profile_log"

  rm -f "$window_file"
}

get_audit_event_count() {
  local pod
  pod="$(get_autoscaler_pod)"
  if [ -z "$pod" ]; then
    echo "0"
    return 0
  fi

  kubectl exec -n thesis-autoscaling "$pod" -c audit-db -- \
    psql -U autoscaler -d autoscaler -At -c 'select count(*) from audit_events' 2>/dev/null \
    | tr -d '[:space:]' || echo "0"
}

capture_audit_payloads() {
  local start_count="$1"
  local output_file="$2"
  local pod
  local captured

  pod="$(get_autoscaler_pod)"
  if [ -z "$pod" ]; then
    : > "$output_file"
    return 0
  fi

  captured="$(kubectl exec -n thesis-autoscaling "$pod" -c audit-db -- \
    psql -U autoscaler -d autoscaler -At \
    -c "select payload_json::text from audit_events order by id asc offset ${start_count}" 2>/dev/null || true)"

  printf '%s\n' "$captured" | while IFS= read -r line; do
    case "$line" in
      \{*\}) printf '%s\n' "$line" ;;
    esac
  done > "$output_file"
}

run_post_run_insights() {
  local audit_payloads_path="$1"
  local insights_dir="$2"
  local report_status

  mkdir -p "$insights_dir"
  if [ ! -s "$audit_payloads_path" ]; then
    {
      echo "[analysis] status=NO_AUDIT_EVENTS"
      echo "[analysis] audit_payloads=${audit_payloads_path}"
    } >> "$AGGREGATE_LOG_FILE"
    return 0
  fi

  if python3 analysis/run_insights.py \
    --jsonl "$audit_payloads_path" \
    --output-dir "$insights_dir" \
    > "${insights_dir}/analysis.log" 2>&1; then
    report_status="OK"
  else
    report_status="ERROR"
  fi

  {
    echo "[analysis] status=${report_status}"
    echo "[analysis] audit_payloads=${audit_payloads_path}"
    echo "[analysis] metrics_json=${insights_dir}/metrics.json"
    echo "[analysis] report_markdown=${insights_dir}/report.md"
    echo "[analysis] control_response=${insights_dir}/control_response.png"
    echo "[analysis] analysis_log=${insights_dir}/analysis.log"
  } >> "$AGGREGATE_LOG_FILE"
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
profile_slug="$(IFS=_; echo "${requested_profiles[*]}")"
run_dir="${output_base}/run_${profile_slug}_${timestamp}"
json_dir="${run_dir}"
log_dir="${run_dir}"
autoscaler_timeline_log="storage/logs/autoscaler/timeline.log"
mkdir -p "$json_dir" "$log_dir"
AGGREGATE_LOG_FILE="${run_dir}/aggregate.log"
RUN_TIMELINE_LOG="${run_dir}/timeline.log"

{
  echo "[aggregate] started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_dir=${run_dir}"
  echo "[aggregate] profiles=${requested_profiles[*]} dry_run=${dry_run} parallel=${parallel_mode}"
} > "$AGGREGATE_LOG_FILE"

status_file="${run_dir}/status.txt"

{
  printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'parallel=%s\n' "$parallel_mode"
  printf 'dry_run=%s\n' "$dry_run"
  printf 'profiles=%s\n' "${requested_profiles[*]}"
} > "$status_file"

echo "Run directory: $run_dir"
stage_log "initialized" "run_dir=${run_dir} parallel=${parallel_mode} dry_run=${dry_run} profiles=${requested_profiles[*]}"
append_system_health_status "$AGGREGATE_LOG_FILE"
if [ "$dry_run" -eq 0 ]; then
  ensure_app_reachable
fi
audit_start_count="$(get_audit_event_count)"
echo "[aggregate] audit_start_count=${audit_start_count}" >> "$AGGREGATE_LOG_FILE"

run_one() {
  local profile="$1"
  local summary_path="${json_dir}/${profile}_summary.json"
  local log_path="${log_dir}/${profile}.log"
  local jsonl_path="${log_dir}/${profile}.jsonl"
  local start_replicas
  local started_at_utc
  local control_log_start_offset
  local replica_sampler_pid=""
  local replica_samples_path="${run_dir}/${profile}_replica_samples.jsonl"

  start_replicas="$(detect_start_replicas)"
  started_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  control_log_start_offset="$(get_control_log_offset)"

  stage_log "profile_start" "profile=${profile} dry_run=${dry_run} start_replicas=${start_replicas}"
  {
    echo "[run] profile=${profile} started_at=${started_at_utc} start_replicas=${start_replicas}"
    echo "[run] autoscaler_timeline_log=${autoscaler_timeline_log}"
    echo "[run] aggregate_log=${AGGREGATE_LOG_FILE}"
    echo "[run] control_log_start_offset=${control_log_start_offset:-unknown}"
    echo
  } > "$log_path"
  append_system_health_status "$AGGREGATE_LOG_FILE"
  append_profile_jsonl "$jsonl_path" "profile_start" "$profile" "$dry_run" "-1" "" "$log_path" "$start_replicas" "$autoscaler_timeline_log"

  if [ "$dry_run" -eq 0 ]; then
    capture_replica_samples "$replica_samples_path" &
    replica_sampler_pid=$!
  fi

  if [ "$dry_run" -eq 1 ]; then
    {
      echo "[dry-run] Inspecting load/${profile}.js"
      k6 inspect "load/${profile}.js"
    } >> "$log_path" 2>&1
    local exit_code=$?
    append_autoscaler_diagnostics "$log_path"
    append_aggregate_autoscaler_window "$profile" "$control_log_start_offset" "$log_path"
    printf '%s exit_code=%s\n' "$profile" "$exit_code" >> "$status_file"
    stage_log "profile_end" "profile=${profile} exit_code=${exit_code} log=${log_path}"
    append_profile_jsonl "$jsonl_path" "profile_end" "$profile" "$dry_run" "$exit_code" "" "$log_path" "$start_replicas" "$autoscaler_timeline_log"
    return "$exit_code"
  fi

  k6 run "load/${profile}.js" --summary-export "$summary_path" >> "$log_path" 2>&1
  local exit_code=$?
  if [ -n "$replica_sampler_pid" ]; then
    kill "$replica_sampler_pid" 2>/dev/null || true
    wait "$replica_sampler_pid" 2>/dev/null || true
  fi
  append_autoscaler_diagnostics "$log_path"
  append_aggregate_autoscaler_window "$profile" "$control_log_start_offset" "$log_path"
  printf '%s exit_code=%s\n' "$profile" "$exit_code" >> "$status_file"
  stage_log "profile_end" "profile=${profile} exit_code=${exit_code} summary=${summary_path} log=${log_path}"
  append_profile_jsonl "$jsonl_path" "profile_end" "$profile" "$dry_run" "$exit_code" "$summary_path" "$log_path" "$start_replicas" "$autoscaler_timeline_log"
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

audit_payloads_path="${json_dir}/audit_payloads.jsonl"
insights_dir="${run_dir}/insights"
capture_audit_payloads "${audit_start_count:-0}" "$audit_payloads_path"
run_post_run_insights "$audit_payloads_path" "$insights_dir"

{
  printf 'finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'overall_exit=%s\n' "$overall_exit"
} >> "$status_file"

if [ "$overall_exit" -eq 0 ]; then
  echo "All requested loads completed successfully."
else
  echo "One or more load profiles failed."
fi

stage_log "completed" "overall_exit=${overall_exit} status=${status_file} run_dir=${run_dir}"

echo "Storage:"
echo "- Status: ${status_file}"
echo "- All run artifacts: ${run_dir}"
echo "- Autoscaler decision flow: ${autoscaler_timeline_log}"
echo "- Autoscaler aggregate log: ${AGGREGATE_LOG_FILE}"

exit "$overall_exit"
