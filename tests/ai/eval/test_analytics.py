"""Unit tests for codeupipe.ai.eval.analytics — audit-powered analytics."""

import pytest

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


# ── Fixtures ──────────────────────────────────────────────────────────


def _audit_event(
    link_name: str = "TestLink",
    duration_ms: float = 100.0,
    session_id: str = "s1",
    loop_iteration: int = 1,
    error: str | None = None,
    input_keys: list[str] | None = None,
    output_keys: list[str] | None = None,
) -> dict:
    return {
        "link_name": link_name,
        "duration_ms": duration_ms,
        "session_id": session_id,
        "loop_iteration": loop_iteration,
        "error": error,
        "input_keys": input_keys or ["prompt"],
        "output_keys": output_keys or ["prompt", "response"],
    }


# ── Link Profiling ───────────────────────────────────────────────────


@pytest.mark.unit
class TestProfileLinks:
    def test_basic(self):
        events = [
            _audit_event("LinkA", 100),
            _audit_event("LinkA", 200),
            _audit_event("LinkB", 50),
        ]
        profiles = profile_links(events)
        assert len(profiles) == 2
        # Sorted by total time descending
        assert profiles[0].link_name == "LinkA"
        assert profiles[0].invocation_count == 2
        assert profiles[0].total_time_ms == 300.0

    def test_error_rate(self):
        events = [
            _audit_event("LinkA", 100),
            _audit_event("LinkA", 100, error="boom"),
            _audit_event("LinkA", 100, error="fail"),
        ]
        profiles = profile_links(events)
        assert profiles[0].error_count == 2
        assert profiles[0].error_rate == pytest.approx(66.67, rel=0.01)

    def test_empty(self):
        assert profile_links([]) == []

    def test_no_link_name(self):
        """Events without link_name are skipped."""
        events = [{"duration_ms": 100}]
        assert profile_links(events) == []

    def test_percent_of_total(self):
        events = [
            _audit_event("LinkA", 100),
            _audit_event("LinkB", 100),
        ]
        profiles = profile_links(events)
        total_pct = sum(p.percent_of_total for p in profiles)
        assert total_pct == pytest.approx(100.0)

    def test_to_dict(self):
        events = [_audit_event("LinkA", 50)]
        profiles = profile_links(events)
        d = profiles[0].to_dict()
        assert d["link_name"] == "LinkA"
        assert "timing" in d


# ── Session Analytics ─────────────────────────────────────────────────


@pytest.mark.unit
class TestAnalyzeSession:
    def test_basic_session(self):
        events = [
            _audit_event("LinkA", 100, session_id="s1", loop_iteration=1),
            _audit_event("LinkB", 200, session_id="s1", loop_iteration=1),
            _audit_event("LinkA", 150, session_id="s1", loop_iteration=2),
        ]
        summary = analyze_session(events, session_id="s1")
        assert isinstance(summary, SessionSummary)
        assert summary.session_id == "s1"
        assert summary.total_events == 3
        assert summary.total_iterations == 2
        assert summary.total_duration_ms == 450.0
        assert summary.unique_links == 2

    def test_error_tracking(self):
        events = [
            _audit_event(error="kaboom"),
            _audit_event(),
        ]
        summary = analyze_session(events, session_id="s1")
        assert summary.total_errors == 1
        assert summary.error_rate == pytest.approx(50.0)

    def test_bottleneck(self):
        events = [
            _audit_event("Fast", 10),
            _audit_event("Slow", 1000),
        ]
        summary = analyze_session(events, session_id="s1")
        assert summary.bottleneck_link == "Slow"
        assert summary.bottleneck_pct > 90.0

    def test_empty(self):
        summary = analyze_session([], session_id="empty")
        assert summary.session_id == "empty"
        assert summary.total_events == 0

    def test_to_dict(self):
        events = [_audit_event()]
        d = analyze_session(events, session_id="s1").to_dict()
        assert d["session_id"] == "s1"


@pytest.mark.unit
class TestAnalyzeSessions:
    def test_groups_by_session(self):
        events = [
            _audit_event(session_id="s1"),
            _audit_event(session_id="s2"),
            _audit_event(session_id="s1"),
        ]
        summaries = analyze_sessions(events)
        assert len(summaries) == 2
        ids = {s.session_id for s in summaries}
        assert ids == {"s1", "s2"}

    def test_empty(self):
        assert analyze_sessions([]) == []


# ── Data Flow Analysis ────────────────────────────────────────────────


@pytest.mark.unit
class TestAnalyzeDataFlow:
    def test_basic(self):
        events = [
            _audit_event("LinkA",
                         input_keys=["prompt"],
                         output_keys=["prompt", "response"]),
        ]
        flow = analyze_data_flow(events)
        assert len(flow) == 1
        assert flow[0].link_name == "LinkA"
        assert "response" in flow[0].added_keys
        assert len(flow[0].removed_keys) == 0

    def test_removed_keys(self):
        events = [
            _audit_event("LinkA",
                         input_keys=["a", "b"],
                         output_keys=["a"]),
        ]
        flow = analyze_data_flow(events)
        assert "b" in flow[0].removed_keys

    def test_empty(self):
        assert analyze_data_flow([]) == []

    def test_most_common_keys(self):
        """Uses the most common key set when multiple invocations."""
        events = [
            _audit_event("LinkA",
                         input_keys=["x"],
                         output_keys=["x", "y"]),
            _audit_event("LinkA",
                         input_keys=["x"],
                         output_keys=["x", "y"]),
            _audit_event("LinkA",
                         input_keys=["x"],
                         output_keys=["x", "z"]),
        ]
        flow = analyze_data_flow(events)
        assert flow[0].added_keys == ("y",)  # most common

    def test_to_dict(self):
        events = [_audit_event(input_keys=["a"], output_keys=["a", "b"])]
        d = analyze_data_flow(events)[0].to_dict()
        assert "added_keys" in d


# ── Timing Anomaly Detection ─────────────────────────────────────────


@pytest.mark.unit
class TestDetectTimingAnomalies:
    def test_no_anomalies(self):
        events = [
            _audit_event("Link", 100),
            _audit_event("Link", 105),
            _audit_event("Link", 95),
            _audit_event("Link", 100),
        ]
        anomalies = detect_timing_anomalies(events)
        assert anomalies == []

    def test_with_anomaly(self):
        # Need enough data points so outlier doesn't distort mean/stddev
        events = [
            _audit_event("Link", 100),
            _audit_event("Link", 105),
            _audit_event("Link", 95),
            _audit_event("Link", 100),
            _audit_event("Link", 98),
            _audit_event("Link", 102),
            _audit_event("Link", 97),
            _audit_event("Link", 103),
            _audit_event("Link", 99),
            _audit_event("Link", 101),
            _audit_event("Link", 10000),  # way out there
        ]
        anomalies = detect_timing_anomalies(events)
        assert len(anomalies) >= 1
        assert anomalies[0].duration_ms == 10000.0

    def test_sorted_by_zscore(self):
        events = [
            _audit_event("Link", 100),
            _audit_event("Link", 100),
            _audit_event("Link", 100),
            _audit_event("Link", 500),
            _audit_event("Link", 10000),
        ]
        anomalies = detect_timing_anomalies(events, threshold=1.5)
        if len(anomalies) >= 2:
            assert abs(anomalies[0].z_score) >= abs(anomalies[1].z_score)

    def test_to_dict(self):
        anomaly = TimingAnomaly(
            link_name="Link", duration_ms=999, z_score=3.5,
        )
        d = anomaly.to_dict()
        assert d["link_name"] == "Link"


# ── Turn Type Distribution ───────────────────────────────────────────


@pytest.mark.unit
class TestTurnTypeDistribution:
    def test_basic(self):
        turns = [
            {"turn_type": "user_prompt"},
            {"turn_type": "user_prompt"},
            {"turn_type": "follow_up"},
        ]
        dist = turn_type_distribution(turns)
        assert dist["user_prompt"] == 2
        assert dist["follow_up"] == 1

    def test_empty(self):
        assert turn_type_distribution([]) == {}

    def test_missing_type(self):
        turns = [{}]
        dist = turn_type_distribution(turns)
        assert dist.get("unknown", 0) == 1


# ── Tool Usage Analysis ──────────────────────────────────────────────


@pytest.mark.unit
class TestProfileTools:
    def test_basic(self):
        tool_calls = [
            {"tool_name": "file_read", "success": True, "duration_ms": 50},
            {"tool_name": "file_read", "success": True, "duration_ms": 60},
            {"tool_name": "file_write", "success": False, "duration_ms": 100},
        ]
        profiles = profile_tools(tool_calls)
        assert len(profiles) == 2
        # Sorted by count descending
        assert profiles[0].tool_name == "file_read"
        assert profiles[0].call_count == 2
        assert profiles[0].success_rate == pytest.approx(100.0)

    def test_failure_rate(self):
        tool_calls = [
            {"tool_name": "flaky", "success": True},
            {"tool_name": "flaky", "success": False},
        ]
        profiles = profile_tools(tool_calls)
        assert profiles[0].success_rate == pytest.approx(50.0)
        assert profiles[0].failure_count == 1

    def test_servers_tracked(self):
        tool_calls = [
            {"tool_name": "t", "server_name": "srv1"},
            {"tool_name": "t", "server_name": "srv2"},
            {"tool_name": "t", "server_name": "srv1"},
        ]
        profiles = profile_tools(tool_calls)
        assert set(profiles[0].servers) == {"srv1", "srv2"}

    def test_empty(self):
        assert profile_tools([]) == []

    def test_to_dict(self):
        tool_calls = [{"tool_name": "t", "success": True, "duration_ms": 10}]
        d = profile_tools(tool_calls)[0].to_dict()
        assert d["tool_name"] == "t"
        assert "timing" in d


# ── Health Dashboard ──────────────────────────────────────────────────


@pytest.mark.unit
class TestBuildHealthDashboard:
    def test_basic(self):
        events = [
            _audit_event("LinkA", 100, session_id="s1"),
            _audit_event("LinkB", 200, session_id="s1"),
        ]
        tool_calls = [
            {"tool_name": "file_read", "success": True, "duration_ms": 50},
        ]
        turns = [
            {"turn_type": "user_prompt"},
        ]
        dashboard = build_health_dashboard(
            events, tool_calls=tool_calls, turns=turns, total_runs=5,
        )
        assert isinstance(dashboard, HealthDashboard)
        assert len(dashboard.link_profiles) == 2
        assert len(dashboard.tool_profiles) == 1
        assert dashboard.turn_distribution["user_prompt"] == 1
        assert dashboard.total_runs == 5

    def test_to_dict(self):
        dashboard = build_health_dashboard([])
        d = dashboard.to_dict()
        assert "link_profiles" in d
        assert "overall_error_rate" in d
