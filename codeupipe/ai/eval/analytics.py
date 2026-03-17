"""Audit-powered analytics — Extract insights from raw event data.

Route 4 from EVAL_ROUTES.md: zero-cost insights from data we
already capture.  The audit pipeline records everything; this
module turns that firehose into structured analysis.

Three analysis levels:
  1. Link Profiling — Which links are slow, failing, or bottlenecking?
  2. Session Analytics — Per-session health metrics from audit data.
  3. Data Flow Analysis — What keys appear/disappear across links?

All functions operate on dicts (parsed audit events) so they work
with both live events and stored raw_events from EvalStore.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from codeupipe.ai.eval.stats import (
    DescriptiveStats,
    describe,
    detect_outliers_zscore,
    mean,
    percentile,
)

logger = logging.getLogger("codeupipe.ai.eval.analytics")


# ── Link Profile ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class LinkProfile:
    """Performance profile for a single link in the turn chain."""

    link_name: str = ""
    invocation_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    timing: DescriptiveStats = field(default_factory=DescriptiveStats)
    slowest_invocation_ms: float = 0.0
    fastest_invocation_ms: float = 0.0
    total_time_ms: float = 0.0
    percent_of_total: float = 0.0

    def to_dict(self) -> dict:
        return {
            "link_name": self.link_name,
            "invocation_count": self.invocation_count,
            "error_count": self.error_count,
            "error_rate": self.error_rate,
            "timing": self.timing.to_dict(),
            "slowest_invocation_ms": self.slowest_invocation_ms,
            "fastest_invocation_ms": self.fastest_invocation_ms,
            "total_time_ms": self.total_time_ms,
            "percent_of_total": self.percent_of_total,
        }


def profile_links(audit_events: list[dict]) -> list[LinkProfile]:
    """Profile all links from a collection of audit events.

    Groups events by ``link_name``, computes timing stats, error
    rates, and relative time contribution.

    Args:
        audit_events: List of AuditEvent dicts (from to_dict()
            or stored raw_events with event_type="audit").

    Returns:
        List of LinkProfile, sorted by total time descending
        (heaviest links first).
    """
    # Group durations and errors by link name
    durations: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)

    for event in audit_events:
        link_name = event.get("link_name", "")
        if not link_name:
            continue
        duration = event.get("duration_ms", 0.0)
        durations[link_name].append(duration)
        if event.get("error"):
            errors[link_name] += 1

    # Compute total time across all links
    grand_total = sum(
        sum(times) for times in durations.values()
    )

    profiles: list[LinkProfile] = []
    for name, times in durations.items():
        total = sum(times)
        count = len(times)
        err = errors.get(name, 0)

        profiles.append(LinkProfile(
            link_name=name,
            invocation_count=count,
            error_count=err,
            error_rate=(err / count * 100.0) if count > 0 else 0.0,
            timing=describe(times),
            slowest_invocation_ms=max(times) if times else 0.0,
            fastest_invocation_ms=min(times) if times else 0.0,
            total_time_ms=total,
            percent_of_total=(total / grand_total * 100.0)
            if grand_total > 0 else 0.0,
        ))

    profiles.sort(key=lambda p: p.total_time_ms, reverse=True)
    return profiles


# ── Session Analytics ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionSummary:
    """Operational health summary for a single session."""

    session_id: str = ""
    total_events: int = 0
    total_iterations: int = 0
    total_duration_ms: float = 0.0
    total_errors: int = 0
    error_rate: float = 0.0
    unique_links: int = 0
    link_invocations: dict = field(default_factory=dict)
    avg_iteration_ms: float = 0.0
    bottleneck_link: str = ""
    bottleneck_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "total_events": self.total_events,
            "total_iterations": self.total_iterations,
            "total_duration_ms": self.total_duration_ms,
            "total_errors": self.total_errors,
            "error_rate": self.error_rate,
            "unique_links": self.unique_links,
            "link_invocations": self.link_invocations,
            "avg_iteration_ms": self.avg_iteration_ms,
            "bottleneck_link": self.bottleneck_link,
            "bottleneck_pct": self.bottleneck_pct,
        }


def analyze_session(
    audit_events: list[dict],
    session_id: str = "",
) -> SessionSummary:
    """Analyze a single session's audit events.

    Computes operational health metrics: total time, error rate,
    iteration count, bottleneck identification.

    Args:
        audit_events: Audit event dicts for one session.
        session_id: Override session ID (if not in events).
    """
    if not audit_events:
        return SessionSummary(session_id=session_id)

    # Determine session_id from events if not provided
    if not session_id:
        session_id = audit_events[0].get("session_id", "")

    # Filter to this session
    events = [
        e for e in audit_events
        if e.get("session_id", "") == session_id or not session_id
    ]

    total_duration = sum(e.get("duration_ms", 0.0) for e in events)
    total_errors = sum(1 for e in events if e.get("error"))
    iterations = set()
    link_counts: Counter[str] = Counter()
    link_times: dict[str, float] = defaultdict(float)

    for event in events:
        it = event.get("loop_iteration", 0)
        if it > 0:
            iterations.add(it)
        link = event.get("link_name", "")
        if link:
            link_counts[link] += 1
            link_times[link] += event.get("duration_ms", 0.0)

    n_iters = len(iterations) if iterations else 1
    avg_iter = total_duration / n_iters if n_iters > 0 else 0.0

    # Bottleneck: link with most total time
    bottleneck = ""
    bottleneck_pct = 0.0
    if link_times and total_duration > 0:
        bottleneck = max(link_times, key=link_times.get)  # type: ignore[arg-type]
        bottleneck_pct = link_times[bottleneck] / total_duration * 100.0

    return SessionSummary(
        session_id=session_id,
        total_events=len(events),
        total_iterations=len(iterations),
        total_duration_ms=total_duration,
        total_errors=total_errors,
        error_rate=(total_errors / len(events) * 100.0)
        if events else 0.0,
        unique_links=len(link_counts),
        link_invocations=dict(link_counts),
        avg_iteration_ms=avg_iter,
        bottleneck_link=bottleneck,
        bottleneck_pct=bottleneck_pct,
    )


def analyze_sessions(
    audit_events: list[dict],
) -> list[SessionSummary]:
    """Analyze multiple sessions from a mixed bag of audit events.

    Groups events by session_id and returns a summary per session,
    sorted by total duration descending.
    """
    by_session: dict[str, list[dict]] = defaultdict(list)
    for event in audit_events:
        sid = event.get("session_id", "unknown")
        by_session[sid].append(event)

    summaries = [
        analyze_session(events, session_id=sid)
        for sid, events in by_session.items()
    ]
    summaries.sort(key=lambda s: s.total_duration_ms, reverse=True)
    return summaries


# ── Data Flow Analysis ────────────────────────────────────────────────


@dataclass(frozen=True)
class DataFlowEntry:
    """Data flow for a single link — what keys go in and come out."""

    link_name: str = ""
    input_keys: tuple[str, ...] = ()
    output_keys: tuple[str, ...] = ()
    added_keys: tuple[str, ...] = ()
    removed_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "link_name": self.link_name,
            "input_keys": list(self.input_keys),
            "output_keys": list(self.output_keys),
            "added_keys": list(self.added_keys),
            "removed_keys": list(self.removed_keys),
        }


def analyze_data_flow(audit_events: list[dict]) -> list[DataFlowEntry]:
    """Analyze data flow through the link chain.

    For each link, determines which context keys it adds, removes,
    or passes through.  Uses the most common key set per link when
    multiple invocations exist.

    Useful for understanding data dependencies between links.
    """
    # Collect all key sets per link
    link_input_keys: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    link_output_keys: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    for event in audit_events:
        link = event.get("link_name", "")
        if not link:
            continue
        in_keys = tuple(sorted(event.get("input_keys", [])))
        out_keys = tuple(sorted(event.get("output_keys", [])))
        link_input_keys[link].append(in_keys)
        link_output_keys[link].append(out_keys)

    entries: list[DataFlowEntry] = []
    for link in sorted(link_input_keys.keys()):
        # Use the most common key set (mode)
        in_counter: Counter[tuple[str, ...]] = Counter(link_input_keys[link])
        out_counter: Counter[tuple[str, ...]] = Counter(link_output_keys[link])

        common_in = in_counter.most_common(1)[0][0] if in_counter else ()
        common_out = out_counter.most_common(1)[0][0] if out_counter else ()

        in_set = set(common_in)
        out_set = set(common_out)

        entries.append(DataFlowEntry(
            link_name=link,
            input_keys=common_in,
            output_keys=common_out,
            added_keys=tuple(sorted(out_set - in_set)),
            removed_keys=tuple(sorted(in_set - out_set)),
        ))

    return entries


# ── Timing Anomaly Detection ─────────────────────────────────────────


@dataclass(frozen=True)
class TimingAnomaly:
    """A link invocation with anomalous timing."""

    link_name: str = ""
    duration_ms: float = 0.0
    z_score: float = 0.0
    iteration: int = 0
    session_id: str = ""

    def to_dict(self) -> dict:
        return {
            "link_name": self.link_name,
            "duration_ms": self.duration_ms,
            "z_score": self.z_score,
            "iteration": self.iteration,
            "session_id": self.session_id,
        }


def detect_timing_anomalies(
    audit_events: list[dict],
    *,
    threshold: float = 2.5,
) -> list[TimingAnomaly]:
    """Detect link invocations with anomalous timing.

    Groups durations by link, then flags any invocation whose
    duration is more than ``threshold`` standard deviations from
    the link's mean.
    """
    # Group events by link
    by_link: dict[str, list[dict]] = defaultdict(list)
    for event in audit_events:
        link = event.get("link_name", "")
        if link:
            by_link[link].append(event)

    anomalies: list[TimingAnomaly] = []
    for link, events in by_link.items():
        durations = [e.get("duration_ms", 0.0) for e in events]
        if len(durations) < 3:
            continue

        outlier_indices = detect_outliers_zscore(durations, threshold=threshold)
        m = mean(durations)
        from codeupipe.ai.eval.stats import stddev as _stddev
        s = _stddev(durations)

        for idx in outlier_indices:
            event = events[idx]
            z = (durations[idx] - m) / s if s > 0 else 0.0
            anomalies.append(TimingAnomaly(
                link_name=link,
                duration_ms=durations[idx],
                z_score=z,
                iteration=event.get("loop_iteration", 0),
                session_id=event.get("session_id", ""),
            ))

    anomalies.sort(key=lambda a: abs(a.z_score), reverse=True)
    return anomalies


# ── Turn Type Distribution ───────────────────────────────────────────


def turn_type_distribution(
    turns: list[dict],
) -> dict[str, int]:
    """Count turn types from turn snapshot dicts.

    Args:
        turns: List of TurnSnapshot.to_dict() or stored turn records.

    Returns:
        Dict mapping turn_type → count, sorted by count descending.
    """
    counts: Counter[str] = Counter()
    for turn in turns:
        tt = turn.get("turn_type", "unknown")
        counts[tt] += 1
    return dict(counts.most_common())


# ── Tool Usage Analysis ──────────────────────────────────────────────


@dataclass(frozen=True)
class ToolUsageProfile:
    """Aggregated usage stats for a single tool."""

    tool_name: str = ""
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    timing: DescriptiveStats = field(default_factory=DescriptiveStats)
    servers: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "timing": self.timing.to_dict(),
            "servers": list(self.servers),
        }


def profile_tools(tool_calls: list[dict]) -> list[ToolUsageProfile]:
    """Profile tool usage from tool call records.

    Args:
        tool_calls: List of ToolCallRecord.to_dict() or stored dicts.

    Returns:
        List of ToolUsageProfile sorted by call count descending.
    """
    # Group by tool name
    by_tool: dict[str, list[dict]] = defaultdict(list)
    for tc in tool_calls:
        name = tc.get("tool_name", "unknown")
        by_tool[name].append(tc)

    profiles: list[ToolUsageProfile] = []
    for name, calls in by_tool.items():
        successes = sum(1 for c in calls if c.get("success", True))
        failures = len(calls) - successes
        durations = [c.get("duration_ms", 0.0) for c in calls]
        servers = tuple(sorted({
            c.get("server_name", "") for c in calls
            if c.get("server_name")
        }))

        profiles.append(ToolUsageProfile(
            tool_name=name,
            call_count=len(calls),
            success_count=successes,
            failure_count=failures,
            success_rate=(successes / len(calls) * 100.0) if calls else 0.0,
            timing=describe(durations),
            servers=servers,
        ))

    profiles.sort(key=lambda p: p.call_count, reverse=True)
    return profiles


# ── Health Dashboard Data ─────────────────────────────────────────────


@dataclass
class HealthDashboard:
    """Aggregated health data suitable for a dashboard view.

    Combines link profiles, session summaries, tool profiles,
    and anomalies into a single struct.
    """

    link_profiles: list[LinkProfile] = field(default_factory=list)
    session_summaries: list[SessionSummary] = field(default_factory=list)
    tool_profiles: list[ToolUsageProfile] = field(default_factory=list)
    timing_anomalies: list[TimingAnomaly] = field(default_factory=list)
    turn_distribution: dict[str, int] = field(default_factory=dict)
    total_runs: int = 0
    total_errors: int = 0
    overall_error_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "link_profiles": [p.to_dict() for p in self.link_profiles],
            "session_summaries": [s.to_dict() for s in self.session_summaries],
            "tool_profiles": [t.to_dict() for t in self.tool_profiles],
            "timing_anomalies": [a.to_dict() for a in self.timing_anomalies],
            "turn_distribution": self.turn_distribution,
            "total_runs": self.total_runs,
            "total_errors": self.total_errors,
            "overall_error_rate": self.overall_error_rate,
        }


def build_health_dashboard(
    audit_events: list[dict],
    tool_calls: list[dict] | None = None,
    turns: list[dict] | None = None,
    total_runs: int = 0,
) -> HealthDashboard:
    """Build a complete health dashboard from raw data.

    Convenience function that runs all analytics and combines
    results into a single HealthDashboard struct.
    """
    links = profile_links(audit_events)
    sessions = analyze_sessions(audit_events)
    anomalies = detect_timing_anomalies(audit_events)
    tools = profile_tools(tool_calls or [])
    turn_dist = turn_type_distribution(turns or [])

    total_errors = sum(s.total_errors for s in sessions)
    total_events = sum(s.total_events for s in sessions)

    return HealthDashboard(
        link_profiles=links,
        session_summaries=sessions,
        tool_profiles=tools,
        timing_anomalies=anomalies,
        turn_distribution=turn_dist,
        total_runs=total_runs,
        total_errors=total_errors,
        overall_error_rate=(total_errors / total_events * 100.0)
        if total_events > 0 else 0.0,
    )
