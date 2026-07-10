"""Safety checks placeholder."""


import math
import time

from .config import (
    ERROR_RATE_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    SCALE_DOWN_COOLDOWN_SECONDS,
    SCALE_DOWN_STEP,
    SCALE_UP_COOLDOWN_SECONDS,
    SCALE_UP_STEP,
)
from .models import (
    AggregatedDecision,
    FinalDecision,
    MetricsSnapshot,
    VetoRuleResult,
)
from .veto_policy import VetoPolicy

class SafetyGate:
    def __init__(self):
        self.last_scale_up_at = 0.0
        self.last_scale_down_at = 0.0
        self.policy = VetoPolicy(
            latency_p95_threshold=LATENCY_P95_THRESHOLD,
            error_rate_threshold=ERROR_RATE_THRESHOLD,
            max_scale_up_step=SCALE_UP_STEP,
            max_scale_down_step=SCALE_DOWN_STEP,
            scale_up_cooldown_seconds=SCALE_UP_COOLDOWN_SECONDS,
            scale_down_cooldown_seconds=SCALE_DOWN_COOLDOWN_SECONDS,
            stale_metrics_after_seconds=60,
        )

    def _invalid_metrics(self,metrics: MetricsSnapshot) -> VetoPolicy:
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
            vetoed=invalid,
            reason="Metrics snapshot contains invalid values." if invalid else "Metrics snapshot is valid.",
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

    def _rule_excessive_scale_up_step(self, decision: AggregatedDecision) -> VetoRuleResult:
        """Check if scale up step exceeds maximum allowed."""
        triggered = False
        delta = decision.desired_replicas - decision.current_replicas

        if decision.action == "scale_up" and delta > self.policy.max_scale_up_step:
            triggered = True

        if decision.action == "scale_down" and abs(delta) > self.policy.max_scale_down_step:
            triggered = True

        return VetoRuleResult(
            rule_name="excessive_scale_up_step",
            triggered=triggered,
            severity="medium",
            reason=(
                f"Scale up step {decision.desired_replicas - decision.current_replicas} exceeds "
                f"maximum allowed {self.policy.max_scale_up_step}"
                if triggered
                else "Scale up step is within allowed limits"
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
            self._rule_excessive_scale_up_step(decision),
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
        elif decision.action == "scale_down":
            self.last_scale_down_at = now

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