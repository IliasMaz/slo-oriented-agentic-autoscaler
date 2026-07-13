"""Layer: safety-policy.
Applies veto and anti-thrashing checks
before scale actuation.
"""


import time

from config import (
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    MIN_SCALE_ACTION_INTERVAL_SECONDS,
    PER_REPLICA_RPS_THRESHOLD,
    SCALE_DOWN_COOLDOWN_SECONDS,
    SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS,
    SCALE_DOWN_RELEASE_MARGIN,
    SCALE_DOWN_STEP,
    SCALE_UP_COOLDOWN_SECONDS,
    SCALE_UP_STEP,
)
from models import (
    AggregatedDecision,
    FinalDecision,
    MetricsSnapshot,
    VetoRuleResult,
)
from veto_policy import VetoPolicy

class SafetyGate:
    def __init__(self):
        self.last_scale_up_at = 0.0
        self.last_scale_down_at = 0.0
        self.last_scale_action_at = 0.0
        self.last_scale_action = "hold"
        self.policy = VetoPolicy(
            latency_p95_threshold=LATENCY_P95_THRESHOLD,
            error_rate_threshold=ERROR_RATE_THRESHOLD,
            inprogress_threshold=INPROGRESS_THRESHOLD,
            per_replica_rps_threshold=PER_REPLICA_RPS_THRESHOLD,
            max_scale_up_step=SCALE_UP_STEP,
            max_scale_down_step=SCALE_DOWN_STEP,
            scale_up_cooldown_seconds=SCALE_UP_COOLDOWN_SECONDS,
            scale_down_cooldown_seconds=SCALE_DOWN_COOLDOWN_SECONDS,
            min_scale_action_interval_seconds=MIN_SCALE_ACTION_INTERVAL_SECONDS,
            scale_direction_change_cooldown_seconds=SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS,
            scale_down_release_margin=SCALE_DOWN_RELEASE_MARGIN,
            stale_metrics_after_seconds=60,
        )

    @staticmethod
    def _is_scale_action(action: str) -> bool:
        return action in {"scale_up", "scale_down"}

    def _invalid_metrics(self, metrics: MetricsSnapshot) -> VetoRuleResult:
        """Check if the metrics snapshot is invalid."""
        invalid = any(
            [
                metrics.rps < 0,
                metrics.error_rate < 0,
                metrics.p95_latency < 0,
                metrics.inprogress < 0,
                metrics.current_replicas < 0,
                metrics.current_replicas > MAX_REPLICAS,
                metrics.current_replicas < MIN_REPLICAS,
            ]
        )

        return VetoRuleResult(
            rule_name="invalid_metrics",
            triggered=invalid,
            severity="high",
            reason=(
                "metrics snapshot contains invalid values"
                if invalid
                else "metrics snapshot is valid"
            ),
        )

    def _rule_high_latency_blocks_scale_down(self, metrics: MetricsSnapshot, decision: AggregatedDecision) -> VetoRuleResult:
        """Check if high latency should block scale down."""
        triggered = (
            decision.action == "scale_down"
            and metrics.p95_latency > self.policy.latency_p95_threshold
        )

        return VetoRuleResult(
            rule_name="high_latency_blocks_scale_down",
            triggered=triggered,
            severity="high",
            reason=(
                f"p95 latency {metrics.p95_latency:.3f}s exceeds threshold "
                f"{self.policy.latency_p95_threshold:.3f}s during scale_down"
                if triggered
                else "latency does not block scale_down"
            ),
        )

    def _rule_high_error_rate_blocks_scale_down(self, metrics: MetricsSnapshot, decision: AggregatedDecision) -> VetoRuleResult:
        """Check if high error rate should block scale down."""
        triggered = (
            decision.action == "scale_down"
            and metrics.error_rate > self.policy.error_rate_threshold
        )

        return VetoRuleResult(
            rule_name="high_error_rate_blocks_scale_down",
            triggered=triggered,
            severity="high",
            reason=(
                f"error rate {metrics.error_rate:.3f} exceeds threshold "
                f"{self.policy.error_rate_threshold:.3f} during scale_down"
                if triggered
                else "error rate does not block scale_down"
            ),
        )

    def _rule_scale_up_cooldown(self, decision: AggregatedDecision) -> VetoRuleResult:
        """Check if scale up is within cooldown period."""
        triggered = (
            decision.action == "scale_up"
            and (time.time() - self.last_scale_up_at) < self.policy.scale_up_cooldown_seconds
        )

        return VetoRuleResult(
            rule_name="scale_up_cooldown",
            triggered=triggered,
            severity="medium",
            reason=(
                f"Scale up action is within cooldown period of "
                f"{self.policy.scale_up_cooldown_seconds}s"
                if triggered
                else "Scale up action is outside cooldown period"
            ),
        )

    def _rule_scale_down_cooldown(self, decision: AggregatedDecision) -> VetoRuleResult:
        """Check if scale down is within cooldown period."""
        triggered = (
            decision.action == "scale_down"
            and (time.time() - self.last_scale_down_at) < self.policy.scale_down_cooldown_seconds
        )

        return VetoRuleResult(
            rule_name="scale_down_cooldown",
            triggered=triggered,
            severity="medium",
            reason=(
                f"Scale down action is within cooldown period of "
                f"{self.policy.scale_down_cooldown_seconds}s"
                if triggered
                else "Scale down action is outside cooldown period"
            ),
        )

    def _rule_min_scale_action_interval(self, decision: AggregatedDecision) -> VetoRuleResult:
        triggered = (
            self._is_scale_action(decision.action)
            and (time.time() - self.last_scale_action_at) < self.policy.min_scale_action_interval_seconds
        )

        return VetoRuleResult(
            rule_name="min_scale_action_interval",
            triggered=triggered,
            severity="medium",
            reason=(
                f"scale action is within min interval of {self.policy.min_scale_action_interval_seconds}s"
                if triggered
                else "scale action interval is satisfied"
            ),
        )

    def _rule_scale_direction_change_cooldown(self, decision: AggregatedDecision) -> VetoRuleResult:
        opposite_direction = (
            self._is_scale_action(decision.action)
            and self._is_scale_action(self.last_scale_action)
            and decision.action != self.last_scale_action
        )
        triggered = (
            opposite_direction
            and (time.time() - self.last_scale_action_at) < self.policy.scale_direction_change_cooldown_seconds
        )

        return VetoRuleResult(
            rule_name="scale_direction_change_cooldown",
            triggered=triggered,
            severity="medium",
            reason=(
                f"opposite scale direction is blocked for {self.policy.scale_direction_change_cooldown_seconds}s"
                if triggered
                else "scale direction change is allowed"
            ),
        )

    def _rule_scale_down_hysteresis(self, metrics: MetricsSnapshot, decision: AggregatedDecision) -> VetoRuleResult:
        per_replica_rps = metrics.rps / max(metrics.current_replicas, 1)
        release = self.policy.scale_down_release_margin
        safe_to_scale_down = (
            metrics.p95_latency <= self.policy.latency_p95_threshold * release
            and metrics.error_rate <= self.policy.error_rate_threshold * release
            and metrics.inprogress <= int(self.policy.inprogress_threshold * release)
            and per_replica_rps <= self.policy.per_replica_rps_threshold * release
        )
        triggered = decision.action == "scale_down" and not safe_to_scale_down

        return VetoRuleResult(
            rule_name="scale_down_hysteresis",
            triggered=triggered,
            severity="medium",
            reason=(
                f"scale_down blocked until metrics are below {release:.2f} release margin"
                if triggered
                else "scale_down release margin is satisfied"
            ),
        )

    def _rule_excessive_scale_up_step(
        self,
        metrics: MetricsSnapshot,
        decision: AggregatedDecision,
    ) -> VetoRuleResult:
        """Check if scale up step exceeds maximum allowed."""
        triggered = False
        delta = decision.desired_replicas - metrics.current_replicas

        if decision.action == "scale_up" and delta > self.policy.max_scale_up_step:
            triggered = True

        if decision.action == "scale_down" and abs(delta) > self.policy.max_scale_down_step:
            triggered = True

        return VetoRuleResult(
            rule_name="excessive_scale_up_step",
            triggered=triggered,
            severity="medium",
            reason=(
                f"scale step {delta} exceeds allowed policy limits"
                if triggered
                else "scale step is within allowed limits"
            ),
        )

    def evaluate(self,decision: AggregatedDecision, metrics: MetricsSnapshot) -> list[VetoRuleResult]:
        """Evaluate all safety rules and return a list of veto results."""
        results = [
            self._invalid_metrics(metrics),
            self._rule_high_latency_blocks_scale_down(metrics, decision),
            self._rule_high_error_rate_blocks_scale_down(metrics, decision),
            self._rule_scale_up_cooldown(decision),
            self._rule_scale_down_cooldown(decision),
            self._rule_min_scale_action_interval(decision),
            self._rule_scale_direction_change_cooldown(decision),
            self._rule_scale_down_hysteresis(metrics, decision),
            self._rule_excessive_scale_up_step(metrics, decision),
        ]

        return results

    def apply(
        self,
        decision: AggregatedDecision,
        metrics: MetricsSnapshot,
    ) -> tuple[FinalDecision, list[VetoRuleResult]]:
        results = self.evaluate(decision, metrics)
        triggered_rules = [rule for rule in results if rule.triggered]

        if triggered_rules:
            first_rule = triggered_rules[0]
            return (
                FinalDecision(
                    action="hold",
                    desired_replicas=metrics.current_replicas,
                    veto_applied=True,
                    veto_rule=first_rule.rule_name,
                    reason=first_rule.reason,
                ),
                results,
            )

        now = time.time()
        if decision.action == "scale_up":
            self.last_scale_up_at = now
            self.last_scale_action_at = now
            self.last_scale_action = "scale_up"
        elif decision.action == "scale_down":
            self.last_scale_down_at = now
            self.last_scale_action_at = now
            self.last_scale_action = "scale_down"

        return (
            FinalDecision(
                action=decision.action,
                desired_replicas=decision.desired_replicas,
                veto_applied=False,
                veto_rule=None,
                reason="decision accepted by safety gate",
            ),
            results,
        )