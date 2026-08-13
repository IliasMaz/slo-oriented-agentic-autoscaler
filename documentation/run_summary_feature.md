# Run Summary Feature

This feature adds a compact, readable summary for every workload run so that each execution is easier to interpret, compare, and present.

## What it captures

For each run, the generator records:

- final action distribution (`scale_up`, `scale_down`, `hold`)
- average RPS, latency, error rate, and in-progress requests
- vetoes triggered by safety rules
- distribution of agent recommendations
- the main decisions that shaped the run

This is the operational counterpart to the explainability timeline and the policy benchmark scorecard.

## Why it matters

A run without summary is hard to read. A run with summary becomes:

- easier to compare across traffic shapes
- easier to explain in demos
- easier to review for SLO or safety issues
- easier to archive as research evidence

## Generated output

The summary is produced from a JSONL payload export and emitted as markdown.

The output includes sections like:

- Run Summary
- Final action distribution
- Snapshot averages
- Safety veto summary
- Agent activity

## Implementation

The feature is implemented in:

- `analysis/run_summary.py`

The core functions are:

- `summarize_run(events)`
- `build_run_summary_markdown(summary)`

## Example usage

```bash
python analysis/run_summary.py \
  --jsonl storage/json/your_run.jsonl \
  --output documentation/run_summary_example.md
```

This produces a short run report that can be committed alongside the workload artifacts and benchmark outputs.
