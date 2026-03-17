"""Query — Fluent query builder for EvalStore.

Replaces the one-method-per-question pattern with composable,
chainable query objects.  No new SQL — delegates to EvalStore
methods, but provides a declarative API for slicing data.

Usage:
    from codeupipe.ai.eval.query import RunQuery

    # Find all successful runs for a scenario in the last week
    runs = (RunQuery(store)
        .scenario("sc_auth_test")
        .outcome(RunOutcome.SUCCESS)
        .after(datetime.now() - timedelta(days=7))
        .limit(50)
        .execute())

    # Get metric values from those runs
    values = RunQuery(store).tag("env", "prod").metric_values("turns_total")

    # Count runs matching filters
    count = RunQuery(store).model("gpt-4.1").count()
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Sequence

from codeupipe.ai.eval.stats import DescriptiveStats, describe
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import RunOutcome, RunRecord

logger = logging.getLogger("codeupipe.ai.eval.query")


class RunQuery:
    """Fluent query builder for RunRecords in EvalStore.

    Filters are additive (AND logic).  Call ``execute()`` to fetch
    matching runs, or use convenience methods like ``count()``,
    ``metric_values()``, ``stats()``.
    """

    def __init__(self, store: EvalStore) -> None:
        self._store = store
        self._scenario_id: str | None = None
        self._experiment_id: str | None = None
        self._outcome: RunOutcome | None = None
        self._model_name: str | None = None
        self._after: datetime | None = None
        self._before: datetime | None = None
        self._tag_key: str | None = None
        self._tag_value: str | None = None
        self._limit: int | None = None
        self._run_ids: list[str] | None = None

    # ── Filter methods (chainable) ────────────────────────────────

    def scenario(self, scenario_id: str) -> RunQuery:
        """Filter by scenario ID."""
        self._scenario_id = scenario_id
        return self

    def experiment(self, experiment_id: str) -> RunQuery:
        """Filter by experiment ID."""
        self._experiment_id = experiment_id
        return self

    def outcome(self, outcome: RunOutcome) -> RunQuery:
        """Filter by run outcome."""
        self._outcome = outcome
        return self

    def model(self, model_name: str) -> RunQuery:
        """Filter by model name."""
        self._model_name = model_name
        return self

    def after(self, dt: datetime) -> RunQuery:
        """Filter to runs started after this datetime."""
        self._after = dt
        return self

    def before(self, dt: datetime) -> RunQuery:
        """Filter to runs started before this datetime."""
        self._before = dt
        return self

    def tag(self, key: str, value: str | None = None) -> RunQuery:
        """Filter by tag key (and optionally value)."""
        self._tag_key = key
        self._tag_value = value
        return self

    def limit(self, n: int) -> RunQuery:
        """Limit the number of results."""
        self._limit = n
        return self

    def run_ids(self, ids: Sequence[str]) -> RunQuery:
        """Filter to specific run IDs."""
        self._run_ids = list(ids)
        return self

    # ── Execution methods ─────────────────────────────────────────

    def execute(self) -> list[RunRecord]:
        """Execute the query and return matching RunRecords."""
        # Start with the broadest applicable method
        if self._tag_key is not None:
            runs = self._store.list_runs_by_tag(
                self._tag_key, self._tag_value,
            )
        elif self._after is not None or self._before is not None:
            runs = self._store.list_runs_by_time(
                after=self._after,
                before=self._before,
                outcome=self._outcome,
            )
            # outcome already applied in list_runs_by_time
            return self._apply_filters(runs, skip_outcome=True)
        else:
            runs = self._store.list_runs(
                scenario_id=self._scenario_id,
                outcome=self._outcome,
            )
            # scenario_id and outcome already applied
            return self._apply_filters(runs, skip_scenario=True, skip_outcome=True)

        return self._apply_filters(runs)

    def _apply_filters(
        self,
        runs: list[RunRecord],
        *,
        skip_scenario: bool = False,
        skip_outcome: bool = False,
    ) -> list[RunRecord]:
        """Apply remaining filters in Python."""
        result = runs

        if not skip_scenario and self._scenario_id is not None:
            result = [r for r in result if r.scenario_id == self._scenario_id]

        if not skip_outcome and self._outcome is not None:
            result = [
                r for r in result
                if str(r.outcome) == str(self._outcome)
            ]

        if self._experiment_id is not None:
            result = [
                r for r in result
                if r.experiment_id == self._experiment_id
            ]

        if self._model_name is not None:
            result = [
                r for r in result
                if r.config.model == self._model_name
            ]

        if self._run_ids is not None:
            id_set = set(self._run_ids)
            result = [r for r in result if r.run_id in id_set]

        if self._after is not None:
            result = [
                r for r in result
                if r.started_at and r.started_at >= self._after
            ]

        if self._before is not None:
            result = [
                r for r in result
                if r.started_at and r.started_at <= self._before
            ]

        if self._limit is not None:
            result = result[: self._limit]

        return result

    def count(self) -> int:
        """Count matching runs without loading full records."""
        # If we can use store.count_runs() for simple filters, do so
        if (
            self._tag_key is None
            and self._model_name is None
            and self._experiment_id is None
            and self._run_ids is None
            and self._after is None
            and self._before is None
        ):
            return self._store.count_runs(
                scenario_id=self._scenario_id,
                outcome=self._outcome,
            )
        # Otherwise, full execution and count
        return len(self.execute())

    def first(self) -> RunRecord | None:
        """Return the first matching run, or None."""
        results = self.limit(1).execute()
        return results[0] if results else None

    def metric_values(self, metric_name: str) -> list[float]:
        """Extract values of a named metric from all matching runs."""
        runs = self.execute()
        values: list[float] = []
        for run in runs:
            for m in run.metrics:
                if m.name == metric_name:
                    values.append(m.value)
        return values

    def stats(self, metric_name: str) -> DescriptiveStats:
        """Compute descriptive stats for a metric across matching runs."""
        return describe(self.metric_values(metric_name))

    def group_by_model(self) -> dict[str, list[RunRecord]]:
        """Execute and group results by model name."""
        runs = self.execute()
        groups: dict[str, list[RunRecord]] = defaultdict(list)
        for r in runs:
            groups[r.config.model].append(r)
        return dict(groups)

    def group_by_scenario(self) -> dict[str, list[RunRecord]]:
        """Execute and group results by scenario ID."""
        runs = self.execute()
        groups: dict[str, list[RunRecord]] = defaultdict(list)
        for r in runs:
            groups[r.scenario_id or "untagged"].append(r)
        return dict(groups)

    def group_by_outcome(self) -> dict[str, list[RunRecord]]:
        """Execute and group results by outcome."""
        runs = self.execute()
        groups: dict[str, list[RunRecord]] = defaultdict(list)
        for r in runs:
            groups[str(r.outcome)].append(r)
        return dict(groups)
