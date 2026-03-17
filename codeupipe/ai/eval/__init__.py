"""Copilot Agent Eval — Evaluation framework for the codeupipe AI suite.

Capture everything.  Filter later.  Every component is a variable.

Public API — see ``__all__`` for the full export list.
"""

# Core types
from codeupipe.ai.eval.types import (
    Baseline,
    Experiment,
    ExperimentStatus,
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    Scenario,
    ScenarioCategory,
    ScenarioExpectations,
    ToolCallRecord,
    TurnSnapshot,
)

# Data collection
from codeupipe.ai.eval.collector import EvalCollector

# Persistence
from codeupipe.ai.eval.storage import EvalStore

# Metrics — core
from codeupipe.ai.eval.metrics import compute_all, register_metric

# Metrics — derived framework
from codeupipe.ai.eval.metrics import (
    composite_metric,
    difference_metric,
    product_metric,
    ratio_metric,
    register_derived_metrics,
    threshold_metric,
)

# Scenarios
from codeupipe.ai.eval.scenario import (
    build_scenario,
    check_expectations,
    load_scenarios_from_json,
    save_scenarios_to_json,
    ScenarioVerdict,
)

# Scoring
from codeupipe.ai.eval.scorer import (
    DEFAULT_DIMENSIONS,
    ScoreDimension,
    ScoreResult,
    build_judge_prompt,
    score_deterministic,
    score_with_judge_response,
)

# Baselines
from codeupipe.ai.eval.baseline import (
    check_regression,
    compare_to_baseline,
    establish_baseline,
)

# Experiments
from codeupipe.ai.eval.experiment import (
    ExperimentResult,
    compare_runs,
    run_experiment,
)

# Statistics — core
from codeupipe.ai.eval.stats import (
    ComparisonResult,
    DescriptiveStats,
    compare,
    describe,
)

# Statistics — correlation
from codeupipe.ai.eval.stats import (
    CorrelationResult,
    correlate,
    correlation_label,
    correlation_matrix,
    pearson_r,
    spearman_rho,
)

# Statistics — hypothesis testing
from codeupipe.ai.eval.stats import (
    HypothesisResult,
    bootstrap_ci,
    mann_whitney_u,
    welch_t_test,
)

# Statistics — anomaly detection
from codeupipe.ai.eval.stats import (
    AnomalyResult,
    detect_anomaly,
    detect_outliers_iqr,
    detect_outliers_zscore,
    z_score,
)

# Statistics — trend analysis
from codeupipe.ai.eval.stats import (
    TrendResult,
    analyze_trend,
    linear_regression,
    moving_average,
    r_squared,
    rate_of_change,
)

# Analytics — audit-powered insights
from codeupipe.ai.eval.analytics import (
    DataFlowEntry,
    HealthDashboard,
    LinkProfile,
    SessionSummary,
    TimingAnomaly,
    ToolUsageProfile,
    analyze_data_flow,
    analyze_session,
    analyze_sessions,
    build_health_dashboard,
    detect_timing_anomalies,
    profile_links,
    profile_tools,
    turn_type_distribution,
)

# Export
from codeupipe.ai.eval.export import (
    metrics_to_csv,
    raw_events_to_jsonl,
    run_to_summary,
    runs_to_csv,
    runs_to_jsonl,
    runs_to_summary_dicts,
    save_csv,
    save_jsonl,
)

# Reports
from codeupipe.ai.eval.report import (
    aggregate_report_md,
    baseline_report_md,
    comparison_report_md,
    dashboard_report_md,
    experiment_report_md,
    regression_report_md,
    run_report_md,
    save_report,
    trend_report_md,
)

# Comparator — structured comparison engine
from codeupipe.ai.eval.comparator import (
    ConfigRanking,
    MetricDelta,
    OutcomeSummary,
    RegressionAlert,
    RunSetComparison,
    compare_run_sets,
    rank_configs,
    regression_alert,
)

# Query — fluent query builder
from codeupipe.ai.eval.query import RunQuery

# Validation — data integrity checks
from codeupipe.ai.eval.validation import (
    ValidationError,
    is_valid_run,
    is_valid_scenario,
    validate_metric,
    validate_run,
    validate_scenario,
)

__all__ = [
    # Types
    "Baseline",
    "Experiment",
    "ExperimentStatus",
    "Metric",
    "RawEvent",
    "RunConfig",
    "RunOutcome",
    "RunRecord",
    "Scenario",
    "ScenarioCategory",
    "ScenarioExpectations",
    "ToolCallRecord",
    "TurnSnapshot",
    # Collection
    "EvalCollector",
    # Persistence
    "EvalStore",
    # Metrics — core
    "compute_all",
    "register_metric",
    # Metrics — derived framework
    "composite_metric",
    "difference_metric",
    "product_metric",
    "ratio_metric",
    "register_derived_metrics",
    "threshold_metric",
    # Scenarios
    "build_scenario",
    "check_expectations",
    "load_scenarios_from_json",
    "save_scenarios_to_json",
    "ScenarioVerdict",
    # Scoring
    "DEFAULT_DIMENSIONS",
    "ScoreDimension",
    "ScoreResult",
    "build_judge_prompt",
    "score_deterministic",
    "score_with_judge_response",
    # Baselines
    "check_regression",
    "compare_to_baseline",
    "establish_baseline",
    # Experiments
    "ExperimentResult",
    "compare_runs",
    "run_experiment",
    # Stats — core
    "ComparisonResult",
    "DescriptiveStats",
    "compare",
    "describe",
    # Stats — correlation
    "CorrelationResult",
    "correlate",
    "correlation_label",
    "correlation_matrix",
    "pearson_r",
    "spearman_rho",
    # Stats — hypothesis testing
    "HypothesisResult",
    "bootstrap_ci",
    "mann_whitney_u",
    "welch_t_test",
    # Stats — anomaly detection
    "AnomalyResult",
    "detect_anomaly",
    "detect_outliers_iqr",
    "detect_outliers_zscore",
    "z_score",
    # Stats — trend analysis
    "TrendResult",
    "analyze_trend",
    "linear_regression",
    "moving_average",
    "r_squared",
    "rate_of_change",
    # Analytics
    "DataFlowEntry",
    "HealthDashboard",
    "LinkProfile",
    "SessionSummary",
    "TimingAnomaly",
    "ToolUsageProfile",
    "analyze_data_flow",
    "analyze_session",
    "analyze_sessions",
    "build_health_dashboard",
    "detect_timing_anomalies",
    "profile_links",
    "profile_tools",
    "turn_type_distribution",
    # Export
    "metrics_to_csv",
    "raw_events_to_jsonl",
    "run_to_summary",
    "runs_to_csv",
    "runs_to_jsonl",
    "runs_to_summary_dicts",
    "save_csv",
    "save_jsonl",
    # Reports
    "aggregate_report_md",
    "baseline_report_md",
    "comparison_report_md",
    "dashboard_report_md",
    "experiment_report_md",
    "regression_report_md",
    "run_report_md",
    "save_report",
    "trend_report_md",
    # Comparator
    "ConfigRanking",
    "MetricDelta",
    "OutcomeSummary",
    "RegressionAlert",
    "RunSetComparison",
    "compare_run_sets",
    "rank_configs",
    "regression_alert",
    # Query
    "RunQuery",
    # Validation
    "ValidationError",
    "is_valid_run",
    "is_valid_scenario",
    "validate_metric",
    "validate_run",
    "validate_scenario",
]
