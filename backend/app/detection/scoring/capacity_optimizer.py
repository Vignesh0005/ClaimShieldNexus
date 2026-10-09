from dataclasses import dataclass, field


@dataclass
class QueueCase:
    case_id: str
    provider_id: str | None
    risk_score: float
    expected_recovery: float
    member_harm_score: float
    estimated_hours: float
    evidence_strength: float

    @property
    def value(self) -> float:
        return self.expected_recovery * (0.5 + 0.5 * self.member_harm_score)


@dataclass
class OptimizationResult:
    selected_cases: list[QueueCase] = field(default_factory=list)
    total_hours: float = 0.0
    capacity: float = 0.0
    total_expected_recovery: float = 0.0
    total_harm_reduction: float = 0.0
    skipped_low_evidence: int = 0
    optimization_method: str = "integer_linear_programming"


class CapacityOptimizer:
    """Chooses the set of cases that maximises expected recovery weighted by member harm, within
    the review hours available. Selection only orders the work; it decides nothing about a case."""

    def optimize(
        self,
        cases: list[QueueCase],
        num_investigators: int,
        hours_per_investigator: float,
        min_evidence: float = 0.5,
        max_cases: int | None = None,
    ) -> OptimizationResult:
        capacity = num_investigators * hours_per_investigator
        eligible = [c for c in cases if c.evidence_strength >= min_evidence and c.estimated_hours > 0]
        selected, method = self._solve_ilp(eligible, capacity, max_cases)
        if selected is None:
            selected, method = self._solve_greedy(eligible, capacity, max_cases), "greedy_value_per_hour"
        selected.sort(key=lambda c: c.risk_score, reverse=True)
        all_harm = sum(c.member_harm_score for c in cases)
        return OptimizationResult(
            selected_cases=selected,
            total_hours=round(sum(c.estimated_hours for c in selected), 2),
            capacity=capacity,
            total_expected_recovery=round(sum(c.expected_recovery for c in selected), 2),
            # Share of the queue's member-harm exposure covered by the selected cases.
            total_harm_reduction=round(sum(c.member_harm_score for c in selected) / all_harm, 2) if all_harm else 0.0,
            skipped_low_evidence=len(cases) - len(eligible),
            optimization_method=method,
        )

    @staticmethod
    def _solve_ilp(eligible: list[QueueCase], capacity: float, max_cases: int | None):
        if not eligible:
            return [], "integer_linear_programming"
        try:
            import pulp

            prob = pulp.LpProblem("SIU_Selection", pulp.LpMaximize)
            x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(eligible))]
            prob += pulp.lpSum(x[i] * c.value for i, c in enumerate(eligible))
            prob += pulp.lpSum(x[i] * c.estimated_hours for i, c in enumerate(eligible)) <= capacity
            if max_cases:
                prob += pulp.lpSum(x) <= max_cases
            prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=10))
            if pulp.LpStatus[prob.status] != "Optimal":
                return None, ""
            return [c for i, c in enumerate(eligible) if (x[i].value() or 0) > 0.5], "integer_linear_programming"
        except Exception:  # noqa: BLE001  (solver missing or failed: fall back to greedy)
            return None, ""

    @staticmethod
    def _solve_greedy(eligible: list[QueueCase], capacity: float, max_cases: int | None) -> list[QueueCase]:
        chosen, used = [], 0.0
        for c in sorted(eligible, key=lambda c: c.value / c.estimated_hours, reverse=True):
            if max_cases and len(chosen) >= max_cases:
                break
            if used + c.estimated_hours <= capacity:
                chosen.append(c)
                used += c.estimated_hours
        return chosen
