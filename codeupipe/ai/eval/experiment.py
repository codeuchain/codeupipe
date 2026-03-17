"""Experiment — Run multiple configs × multiple scenarios.

An experiment is a structured comparison: take N configurations,
run each against M scenarios, collect all the data, and compare.

The experiment runner is config-agnostic: it takes a callable
``run_fn`` that executes a single run with a given config and
prompt.  This keeps the eval framework decoupled from the
codeupipe.ai internals — you provide the execution function.

Usage:
    store = EvalStore("eval.db")

    # Define how to run the agent
    async def run_agent(config: RunConfig, prompt: str) -> RunRecord:
        agent = Agent(AgentConfig(model=config.model))
        collector = EvalCollector(store)
        collector.begin_run(config=config)
        async for event in agent.run(prompt):
            collector.record_agent_event(event)
        return collector.end_run(RunOutcome.SUCCESS)

    # Run experiment
    result = await run_experiment(
        store=store,
        name="model-comparison",
        configs=[
            RunConfig(model="gpt-4.1"),
            RunConfig(model="claude-sonnet-4"),
        ],
        scenario_ids=["sc_abc", "sc_def"],
        run_fn=run_agent,
        repeats=5,
    )
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Awaitable

from codeupipe.ai.eval.baseline import compare_to_baseline, establish_baseline
from codeupipe.ai.eval.scorer import ScoreResult, score_deterministic
from codeupipe.ai.eval.stats import ComparisonResult, describe
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Experiment,
    ExperimentStatus,
    Metric,
    RunConfig,
    RunRecord,
    _new_id,
    _utcnow,
)

logger = logging.getLogger("codeupipe.ai.eval.experiment")


# ── Type alias for run function ───────────────────────────────────────

RunFn = Callable[[RunConfig, str], Awaitable[RunRecord]]


# ── Experiment result ─────────────────────────────────────────────────

class ExperimentResult:
    """Complete results of an experiment.

    Groups runs by config for easy comparison.
    """

    def __init__(
        self,
        experiment: Experiment,
        runs_by_config: dict[str, list[RunRecord]],
        comparisons: list[ComparisonResult] | None = None,
        scores: list[ScoreResult] | None = None,
    ) -> None:
        self.experiment = experiment
        self.runs_by_config = runs_by_config
        self.comparisons = comparisons or []
        self.scores = scores or []

    @property
    def total_runs(self) -> int:
        return sum(len(runs) for runs in self.runs_by_config.values())

    def config_labels(self) -> list[str]:
        return list(self.runs_by_config.keys())

    def metric_summary(self, metric_name: str) -> dict[str, dict]:
        """Get descriptive stats for a metric across all configs."""
        summary: dict[str, dict] = {}
        for label, runs in self.runs_by_config.items():
            values = []
            for run in runs:
                for m in run.metrics:
                    if m.name == metric_name:
                        values.append(m.value)
            summary[label] = describe(values).to_dict()
        return summary

    def all_runs(self) -> list[RunRecord]:
        """Return all runs across all configs in a flat list."""
        result: list[RunRecord] = []
        for runs in self.runs_by_config.values():
            result.extend(runs)
        return result

    def success_rate(self, config_label: str | None = None) -> float:
        """Success rate — overall or per-config.

        Returns percentage (0-100).
        """
        if config_label:
            runs = self.runs_by_config.get(config_label, [])
        else:
            runs = self.all_runs()
        if not runs:
            return 0.0
        successes = sum(1 for r in runs if str(r.outcome) == "success")
        return successes / len(runs) * 100.0

    def outcome_distribution(
        self, config_label: str | None = None,
    ) -> dict[str, int]:
        """Count of runs by outcome — overall or per-config."""
        if config_label:
            runs = self.runs_by_config.get(config_label, [])
        else:
            runs = self.all_runs()
        dist: dict[str, int] = {}
        for r in runs:
            key = str(r.outcome)
            dist[key] = dist.get(key, 0) + 1
        return dist

    def best_config(self, metric_name: str, *, higher_is_better: bool = True) -> str:
        """Return the config label with the best mean for a metric.

        Args:
            metric_name: Which metric to compare.
            higher_is_better: Direction of "best". Set False for cost-like metrics.

        Returns:
            Config label string. Empty string if no data.
        """
        best_label = ""
        best_mean: float | None = None
        summary = self.metric_summary(metric_name)
        for label in self.config_labels():
            stats = summary.get(label, {})
            # Skip configs with no observations for this metric
            if stats.get("count", 0) == 0:
                continue
            mean_val = stats.get("mean")
            if mean_val is None:
                continue
            if best_mean is None:
                best_label = label
                best_mean = mean_val
            elif higher_is_better and mean_val > best_mean:
                best_label = label
                best_mean = mean_val
            elif not higher_is_better and mean_val < best_mean:
                best_label = label
                best_mean = mean_val
        return best_label

    def to_dict(self) -> dict:
        return {
            "experiment": self.experiment.to_dict(),
            "total_runs": self.total_runs,
            "config_labels": self.config_labels(),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "scores": [s.to_dict() for s in self.scores],
        }


# ── Run experiment ────────────────────────────────────────────────────

async def run_experiment(
    store: EvalStore,
    name: str,
    configs: list[RunConfig],
    scenario_ids: list[str],
    run_fn: RunFn,
    *,
    repeats: int = 1,
    baseline_config_index: int = 0,
    description: str = "",
) -> ExperimentResult:
    """Execute a full experiment — all configs × all scenarios × repeats.

    Args:
        store: Persistence layer.
        name: Human-readable experiment name.
        configs: List of configurations to compare.
        scenario_ids: Scenario IDs to run each config against.
        run_fn: Async function that executes one run.
        repeats: How many times to run each config×scenario pair.
        baseline_config_index: Which config to use as the control (default: first).
        description: Optional description.

    Returns:
        ExperimentResult with all runs, comparisons, and scores.
    """
    experiment_id = _new_id()

    # Create experiment record
    experiment = Experiment(
        experiment_id=experiment_id,
        name=name,
        description=description or name,
        created_at=_utcnow(),
        configs=tuple(configs),
        scenario_ids=tuple(scenario_ids),
        status=ExperimentStatus.RUNNING,
    )
    store.save_experiment(experiment)

    # Load scenarios
    scenarios = {}
    for sid in scenario_ids:
        s = store.get_scenario(sid)
        if s:
            scenarios[sid] = s
        else:
            logger.warning("Scenario %s not found — skipping", sid)

    # Run all configs × scenarios × repeats
    all_runs: list[RunRecord] = []
    runs_by_config: dict[str, list[RunRecord]] = defaultdict(list)

    for config_idx, config in enumerate(configs):
        config_label = f"config_{config_idx}_{config.model}"
        logger.info("Running config %d/%d: %s", config_idx + 1, len(configs), config_label)

        for scenario_id, scenario in scenarios.items():
            for repeat in range(repeats):
                logger.debug(
                    "  Scenario %s, repeat %d/%d",
                    scenario.name, repeat + 1, repeats,
                )
                try:
                    run = await run_fn(config, scenario.input_prompt)

                    # Tag the run with experiment and scenario
                    run = RunRecord(
                        run_id=run.run_id,
                        session_id=run.session_id,
                        scenario_id=scenario_id,
                        experiment_id=experiment_id,
                        config=config,
                        started_at=run.started_at,
                        ended_at=run.ended_at,
                        outcome=run.outcome,
                        turns=run.turns,
                        tool_calls=run.tool_calls,
                        metrics=run.metrics,
                        audit_events=run.audit_events,
                        raw_data=run.raw_data,
                    )

                    all_runs.append(run)
                    runs_by_config[config_label].append(run)

                except Exception as exc:
                    logger.error(
                        "Run failed for config %s, scenario %s: %s",
                        config_label, scenario.name, exc,
                    )

    # Score runs
    scores: list[ScoreResult] = []
    for run in all_runs:
        scenario = scenarios.get(run.scenario_id or "")
        if scenario:
            score = score_deterministic(run, scenario)
            scores.append(score)

    # Compare against baseline config
    comparisons: list[ComparisonResult] = []
    if len(configs) > 1:
        baseline_label = f"config_{baseline_config_index}_{configs[baseline_config_index].model}"
        baseline_runs = runs_by_config.get(baseline_label, [])

        if baseline_runs:
            # Establish baseline
            baseline = establish_baseline(
                store,
                name=f"{name}_baseline",
                runs=baseline_runs,
            )

            # Compare each non-baseline config
            for label, runs in runs_by_config.items():
                if label == baseline_label:
                    continue
                config_comparisons = compare_to_baseline(
                    store, baseline, runs,
                )
                comparisons.extend(config_comparisons)

    # Update experiment status
    run_ids = tuple(r.run_id for r in all_runs)
    experiment = Experiment(
        experiment_id=experiment.experiment_id,
        name=experiment.name,
        description=experiment.description,
        created_at=experiment.created_at,
        configs=experiment.configs,
        scenario_ids=experiment.scenario_ids,
        status=ExperimentStatus.COMPLETED,
        run_ids=run_ids,
        metadata={"total_runs": len(all_runs)},
    )
    store.save_experiment(experiment)

    logger.info(
        "Experiment '%s' completed: %d runs across %d configs",
        name, len(all_runs), len(configs),
    )

    return ExperimentResult(
        experiment=experiment,
        runs_by_config=dict(runs_by_config),
        comparisons=comparisons,
        scores=scores,
    )


# ── Quick comparison utility ──────────────────────────────────────────

def compare_runs(
    runs_a: list[RunRecord],
    runs_b: list[RunRecord],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> dict[str, ComparisonResult]:
    """Quick head-to-head comparison of two sets of runs.

    Returns a dict mapping metric_name → ComparisonResult.
    """
    from codeupipe.ai.eval.baseline import LOWER_IS_BETTER

    # Collect metric values
    values_a: dict[str, list[float]] = defaultdict(list)
    values_b: dict[str, list[float]] = defaultdict(list)

    for run in runs_a:
        for m in run.metrics:
            values_a[m.name].append(m.value)
    for run in runs_b:
        for m in run.metrics:
            values_b[m.name].append(m.value)

    # Compare all shared metrics
    shared = sorted(set(values_a.keys()) & set(values_b.keys()))
    results: dict[str, ComparisonResult] = {}

    from codeupipe.ai.eval.stats import compare as stats_compare

    for name in shared:
        higher = name not in LOWER_IS_BETTER
        results[name] = stats_compare(
            name, values_a[name], values_b[name],
            higher_is_better=higher,
        )

    return results
