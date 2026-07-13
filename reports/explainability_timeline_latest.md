# Explainability Timeline

Generated from autoscaler audit events.

Regenerate with:

```bash
python3 analysis/explainability_timeline.py \
	--jsonl /tmp/audit_payloads.jsonl \
	--limit 50 \
	--output reports/explainability_timeline_latest.md
```

## Event Timeline

### Event #1 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #2 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.9`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: Traffic is zero and all metrics are below thresholds; already at minimum replicas, so maintain 1 replica.

### Event #3 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are well below thresholds; service is already at minimum replicas, so remain at 1.

### Event #4 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.97`
- Top veto trigger: `none`
- Best arbitration score: `0.052150537634408606`
- OpenAI reason: All metrics are well below thresholds and service is already at minimum replicas; no additional capacity needed.

### Event #5 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: All metrics are well below thresholds and service is already at the minimum replica count, so remain at 1 replica.

### Event #6 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #7 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #8 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #9 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #10 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #11 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so maintain current size.

### Event #12 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.95`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: All metrics are at or below thresholds and service is already at minimum replicas; no scale down possible.

### Event #13 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #14 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #15 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #16 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #17 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.95`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: Traffic is zero and all metrics are well below thresholds; already at minimum replicas, so maintain 1 replica.

### Event #18 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #19 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; minimum replica count is 1 so remain at floor.

### Event #20 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #21 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.051752021563342326`
- OpenAI reason: No traffic and all metrics are well below thresholds; minimum replica count is 1 so remain at floor.

### Event #22 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.97`
- Top veto trigger: `none`
- Best arbitration score: `0.052150537634408606`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #23 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #24 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so maintain current capacity.

### Event #25 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #26 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #27 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: All metrics are far below thresholds and service is already at minimum replicas; remain at 1 to avoid unnecessary resource use.

### Event #28 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #29 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #30 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #31 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: All metrics are well below thresholds and service is already at minimum replicas; effectively maintain at 1.

### Event #32 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.051752021563342326`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #33 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #34 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: All metrics are below thresholds and service is already at minimum replicas; no additional capacity needed.

### Event #35 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so remain at 1.

### Event #36 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #37 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: Idle service with all metrics below thresholds; already at minimum replicas, so remain at 1.

### Event #38 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #39 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas so remain at 1.

### Event #40 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so effectively maintain at 1.

### Event #41 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.99`
- Top veto trigger: `none`
- Best arbitration score: `0.05294117647058824`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #42 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.49091801669121266`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.97`
- Top veto trigger: `none`
- Best arbitration score: `0.0049091801669121264`
- OpenAI reason: All metrics are well below thresholds and service is already at min replicas; scaling down is not possible.

### Event #43 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.8546386878568571`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.97`
- Top veto trigger: `none`
- Best arbitration score: `0.008546386878568572`
- OpenAI reason: All observed metrics are well below thresholds and service is already at minimum replicas, so keep current capacity.

### Event #44 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`1.236341157433501`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.01236341157433501`
- OpenAI reason: All observed metrics are well below thresholds and service is already at minimum replicas, so maintain current capacity.

### Event #45 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`1.1818396698121785`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.06436531358820222`
- OpenAI reason: All metrics are well below thresholds and service is already at minimum replicas; cannot reduce further.

### Event #46 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.6727639689437606`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.97`
- Top veto trigger: `none`
- Best arbitration score: `0.006727639689437606`
- OpenAI reason: All observed metrics are far below thresholds and service is already at min_replicas; scaling down is not possible and scaling up is unnecessary.

### Event #47 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.96`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so maintain current capacity.

### Event #48 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: No traffic and all metrics are well below thresholds; already at minimum replicas, so remain at 1.

### Event #49 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`hold`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.0`
- OpenAI reason: No traffic and all metrics are below thresholds; already at minimum replicas, so keep current state.

### Event #50 - n/a

- Final action: `hold`
- Desired replicas: `1`
- Scaled: `false`
- Snapshot: rps=`0.0`, p95=`0.0`, error_rate=`0.0`, inprogress=`0`, current_replicas=`1`
- OpenAI recommendation: action=`scale_down`, confidence=`0.98`
- Top veto trigger: `none`
- Best arbitration score: `0.05254691689008043`
- OpenAI reason: All metrics are well below thresholds and service is already at minimum replicas; no additional capacity needed.
