"""EvalStore — SQLite persistence for all evaluation data.

Capture-everything philosophy: every table has a ``raw_json``
column for data we haven't formally typed yet.  The schema is
deliberately wide — we store everything and filter later.

Tables:
  - runs          Master record per agent execution
  - turns         Per-turn snapshots within a run
  - tool_calls    Individual tool invocations
  - metrics       Named measurements attached to runs
  - raw_events    The everything-table: any event, any shape
  - scenarios     Evaluation scenario definitions
  - baselines     Saved control-group aggregations
  - experiments   A/B experiment definitions
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from codeupipe.ai.eval.types import (
    Baseline,
    Experiment,
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

logger = logging.getLogger("codeupipe.ai.eval.storage")

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL DEFAULT '',
    scenario_id   TEXT,
    experiment_id TEXT,
    config_json   TEXT NOT NULL DEFAULT '{}',
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    outcome       TEXT NOT NULL DEFAULT 'unknown',
    raw_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT NOT NULL,
    iteration         INTEGER NOT NULL,
    turn_type         TEXT NOT NULL DEFAULT '',
    input_prompt      TEXT NOT NULL DEFAULT '',
    response_content  TEXT,
    tool_calls_count  INTEGER NOT NULL DEFAULT 0,
    tokens_estimated  INTEGER NOT NULL DEFAULT 0,
    duration_ms       REAL NOT NULL DEFAULT 0.0,
    model_used        TEXT NOT NULL DEFAULT '',
    timestamp         TEXT NOT NULL,
    raw_json          TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    call_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    iteration      INTEGER NOT NULL,
    tool_name      TEXT NOT NULL,
    server_name    TEXT NOT NULL DEFAULT '',
    arguments_json TEXT NOT NULL DEFAULT '{}',
    result_summary TEXT NOT NULL DEFAULT '',
    duration_ms    REAL NOT NULL DEFAULT 0.0,
    success        INTEGER NOT NULL DEFAULT 1,
    timestamp      TEXT NOT NULL,
    raw_json       TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS metrics (
    metric_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    name       TEXT NOT NULL,
    value      REAL NOT NULL,
    unit       TEXT NOT NULL DEFAULT '',
    tags_json  TEXT NOT NULL DEFAULT '[]',
    timestamp  TEXT NOT NULL,
    raw_json   TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS raw_events (
    event_id   TEXT PRIMARY KEY,
    run_id     TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL DEFAULT '',
    timestamp  TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id       TEXT PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT '',
    description       TEXT NOT NULL DEFAULT '',
    input_prompt      TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT 'standard',
    expectations_json TEXT NOT NULL DEFAULT '{}',
    tags_json         TEXT NOT NULL DEFAULT '[]',
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS baselines (
    baseline_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    config_json   TEXT NOT NULL DEFAULT '{}',
    metrics_json  TEXT NOT NULL DEFAULT '{}',
    run_count     INTEGER NOT NULL DEFAULT 0,
    run_ids_json  TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id  TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    configs_json   TEXT NOT NULL DEFAULT '[]',
    scenario_ids   TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL DEFAULT 'pending',
    baseline_id    TEXT,
    run_ids_json   TEXT NOT NULL DEFAULT '[]',
    metadata_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tags (
    tag_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS annotations (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    author        TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_runs_outcome ON runs(outcome);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_turns_run ON turns(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_run ON metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
CREATE INDEX IF NOT EXISTS idx_raw_events_run ON raw_events(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_type ON raw_events(event_type);
CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp ON raw_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_tags_run ON tags(run_id);
CREATE INDEX IF NOT EXISTS idx_tags_key ON tags(key);
CREATE INDEX IF NOT EXISTS idx_tags_key_value ON tags(key, value);
CREATE INDEX IF NOT EXISTS idx_annotations_run ON annotations(run_id);
"""


class EvalStore:
    """SQLite store for evaluation data.  Keeps everything."""

    def __init__(self, path: str | Path = "eval.db") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        # Track schema version
        self._conn.execute(
            "INSERT OR REPLACE INTO eval_meta (key, value) VALUES (?, ?)",
            ("schema_version", str(_SCHEMA_VERSION)),
        )
        self._conn.commit()
        logger.debug("EvalStore initialized at %s (v%d)", self._path, _SCHEMA_VERSION)

    def close(self) -> None:
        self._conn.close()

    # ── Runs ──────────────────────────────────────────────────────────

    def save_run(self, run: RunRecord) -> None:
        """Persist a complete RunRecord and all its child data."""
        self._conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, session_id, scenario_id, experiment_id,
                config_json, started_at, ended_at, outcome, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.session_id,
                run.scenario_id,
                run.experiment_id,
                json.dumps(run.config.to_dict()),
                run.started_at.isoformat(),
                run.ended_at.isoformat() if run.ended_at else None,
                str(run.outcome),
                json.dumps(run.raw_data),
            ),
        )

        # Turns
        for turn in run.turns:
            self._save_turn(run.run_id, turn)

        # Tool calls
        for tc in run.tool_calls:
            self._save_tool_call(run.run_id, tc)

        # Metrics
        for m in run.metrics:
            self._save_metric(run.run_id, m)

        # Audit events as raw events
        for ae in run.audit_events:
            self.save_raw_event(RawEvent(
                run_id=run.run_id,
                event_type="audit",
                payload=ae,
            ))

        self._conn.commit()
        logger.debug("Saved run %s (%d turns, %d metrics)",
                      run.run_id, len(run.turns), len(run.metrics))

    def _save_turn(self, run_id: str, turn: TurnSnapshot) -> None:
        self._conn.execute(
            """INSERT INTO turns
               (run_id, iteration, turn_type, input_prompt,
                response_content, tool_calls_count, tokens_estimated,
                duration_ms, model_used, timestamp, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                turn.iteration,
                turn.turn_type,
                turn.input_prompt,
                turn.response_content,
                turn.tool_calls_count,
                turn.tokens_estimated,
                turn.duration_ms,
                turn.model_used,
                turn.timestamp.isoformat(),
                json.dumps(turn.raw_data),
            ),
        )

    def _save_tool_call(self, run_id: str, tc: ToolCallRecord) -> None:
        self._conn.execute(
            """INSERT INTO tool_calls
               (run_id, iteration, tool_name, server_name,
                arguments_json, result_summary, duration_ms,
                success, timestamp, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                tc.iteration,
                tc.tool_name,
                tc.server_name,
                json.dumps(tc.arguments),
                tc.result_summary,
                tc.duration_ms,
                int(tc.success),
                tc.timestamp.isoformat(),
                json.dumps(tc.raw_data),
            ),
        )

    def _save_metric(self, run_id: str, m: Metric) -> None:
        self._conn.execute(
            """INSERT INTO metrics
               (run_id, name, value, unit, tags_json, timestamp, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                m.name,
                m.value,
                m.unit,
                json.dumps(list(m.tags)),
                m.timestamp.isoformat(),
                json.dumps(m.raw_data),
            ),
        )

    def get_run(self, run_id: str) -> RunRecord | None:
        """Load a RunRecord by ID, including all child data."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    def list_runs(
        self,
        *,
        scenario_id: str | None = None,
        experiment_id: str | None = None,
        outcome: RunOutcome | None = None,
        limit: int = 100,
    ) -> list[RunRecord]:
        """List runs matching optional filters."""
        query = "SELECT * FROM runs WHERE 1=1"
        params: list = []
        if scenario_id:
            query += " AND scenario_id = ?"
            params.append(scenario_id)
        if experiment_id:
            query += " AND experiment_id = ?"
            params.append(experiment_id)
        if outcome:
            query += " AND outcome = ?"
            params.append(str(outcome))
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_run(r) for r in rows]

    def _row_to_run(self, row: sqlite3.Row) -> RunRecord:
        config_data = json.loads(row["config_json"])
        turns = self._get_turns(row["run_id"])
        tool_calls = self._get_tool_calls(row["run_id"])
        metrics = self._get_metrics(row["run_id"])
        audit_events = self._get_raw_events_payload(row["run_id"], "audit")

        return RunRecord(
            run_id=row["run_id"],
            session_id=row["session_id"],
            scenario_id=row["scenario_id"],
            experiment_id=row["experiment_id"],
            config=RunConfig(
                model=config_data.get("model", "gpt-4.1"),
                max_iterations=config_data.get("max_iterations", 10),
                context_budget=config_data.get("context_budget", 128_000),
                directives=tuple(config_data.get("directives", [])),
                extra=config_data.get("extra", {}),
            ),
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            outcome=RunOutcome(row["outcome"]),
            turns=tuple(turns),
            tool_calls=tuple(tool_calls),
            metrics=tuple(metrics),
            audit_events=tuple(audit_events),
            raw_data=json.loads(row["raw_json"]),
        )

    def _get_turns(self, run_id: str) -> list[TurnSnapshot]:
        rows = self._conn.execute(
            "SELECT * FROM turns WHERE run_id = ? ORDER BY iteration", (run_id,)
        ).fetchall()
        return [
            TurnSnapshot(
                iteration=r["iteration"],
                turn_type=r["turn_type"],
                input_prompt=r["input_prompt"],
                response_content=r["response_content"],
                tool_calls_count=r["tool_calls_count"],
                tokens_estimated=r["tokens_estimated"],
                duration_ms=r["duration_ms"],
                model_used=r["model_used"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                raw_data=json.loads(r["raw_json"]),
            )
            for r in rows
        ]

    def _get_tool_calls(self, run_id: str) -> list[ToolCallRecord]:
        rows = self._conn.execute(
            "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY iteration", (run_id,)
        ).fetchall()
        return [
            ToolCallRecord(
                iteration=r["iteration"],
                tool_name=r["tool_name"],
                server_name=r["server_name"],
                arguments=json.loads(r["arguments_json"]),
                result_summary=r["result_summary"],
                duration_ms=r["duration_ms"],
                success=bool(r["success"]),
                timestamp=datetime.fromisoformat(r["timestamp"]),
                raw_data=json.loads(r["raw_json"]),
            )
            for r in rows
        ]

    def _get_metrics(self, run_id: str) -> list[Metric]:
        rows = self._conn.execute(
            "SELECT * FROM metrics WHERE run_id = ? ORDER BY name", (run_id,)
        ).fetchall()
        return [
            Metric(
                name=r["name"],
                value=r["value"],
                unit=r["unit"],
                tags=tuple(json.loads(r["tags_json"])),
                timestamp=datetime.fromisoformat(r["timestamp"]),
                raw_data=json.loads(r["raw_json"]),
            )
            for r in rows
        ]

    def _get_raw_events_payload(self, run_id: str, event_type: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT payload FROM raw_events WHERE run_id = ? AND event_type = ?",
            (run_id, event_type),
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ── Raw Events (the everything-table) ─────────────────────────────

    def save_raw_event(self, event: RawEvent) -> None:
        """Store any event with minimal structure."""
        self._conn.execute(
            """INSERT OR REPLACE INTO raw_events
               (event_id, run_id, event_type, timestamp, payload)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.run_id,
                event.event_type,
                event.timestamp.isoformat(),
                json.dumps(event.payload, default=str),
            ),
        )

    def count_raw_events(self, *, run_id: str = "", event_type: str = "") -> int:
        """Count raw events matching optional filters."""
        query = "SELECT COUNT(*) FROM raw_events WHERE 1=1"
        params: list = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        return self._conn.execute(query, params).fetchone()[0]

    def get_raw_events(
        self,
        *,
        run_id: str = "",
        event_type: str = "",
        limit: int = 1000,
    ) -> list[RawEvent]:
        """Retrieve raw events matching optional filters."""
        query = "SELECT * FROM raw_events WHERE 1=1"
        params: list = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            RawEvent(
                event_id=r["event_id"],
                run_id=r["run_id"],
                event_type=r["event_type"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                payload=json.loads(r["payload"]),
            )
            for r in rows
        ]

    # ── Metrics (cross-run queries) ───────────────────────────────────

    def get_metric_values(
        self,
        metric_name: str,
        *,
        scenario_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[float]:
        """Get all values for a metric across runs, with optional filters."""
        query = """
            SELECT m.value FROM metrics m
            JOIN runs r ON m.run_id = r.run_id
            WHERE m.name = ?
        """
        params: list = [metric_name]
        if scenario_id:
            query += " AND r.scenario_id = ?"
            params.append(scenario_id)
        if experiment_id:
            query += " AND r.experiment_id = ?"
            params.append(experiment_id)

        rows = self._conn.execute(query, params).fetchall()
        return [r[0] for r in rows]

    # ── Scenarios ─────────────────────────────────────────────────────

    def save_scenario(self, scenario: Scenario) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO scenarios
               (scenario_id, name, description, input_prompt,
                category, expectations_json, tags_json, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scenario.scenario_id,
                scenario.name,
                scenario.description,
                scenario.input_prompt,
                str(scenario.category),
                json.dumps(scenario.expectations.to_dict()),
                json.dumps(list(scenario.tags)),
                json.dumps(scenario.metadata),
            ),
        )
        self._conn.commit()

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        row = self._conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
        ).fetchone()
        if not row:
            return None
        expectations_data = json.loads(row["expectations_json"])
        return Scenario(
            scenario_id=row["scenario_id"],
            name=row["name"],
            description=row["description"],
            input_prompt=row["input_prompt"],
            category=ScenarioCategory(row["category"]),
            expectations=ScenarioExpectations(
                max_turns=expectations_data.get("max_turns"),
                max_cost=expectations_data.get("max_cost"),
                required_tool_calls=tuple(
                    expectations_data.get("required_tool_calls", [])
                ),
                forbidden_tool_calls=tuple(
                    expectations_data.get("forbidden_tool_calls", [])
                ),
                output_contains=tuple(
                    expectations_data.get("output_contains", [])
                ),
                output_not_contains=tuple(
                    expectations_data.get("output_not_contains", [])
                ),
                must_complete=expectations_data.get("must_complete", True),
                custom=expectations_data.get("custom", {}),
            ),
            tags=tuple(json.loads(row["tags_json"])),
            metadata=json.loads(row["metadata_json"]),
        )

    def list_scenarios(self, category: str | None = None) -> list[Scenario]:
        query = "SELECT scenario_id FROM scenarios"
        params: list = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        rows = self._conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            s = self.get_scenario(r["scenario_id"])
            if s:
                results.append(s)
        return results

    # ── Baselines ─────────────────────────────────────────────────────

    def save_baseline(self, baseline: Baseline) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO baselines
               (baseline_id, name, created_at, config_json,
                metrics_json, run_count, run_ids_json, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                baseline.baseline_id,
                baseline.name,
                baseline.created_at.isoformat(),
                json.dumps(baseline.config.to_dict()),
                json.dumps(baseline.metrics),
                baseline.run_count,
                json.dumps(list(baseline.run_ids)),
                json.dumps(baseline.metadata),
            ),
        )
        self._conn.commit()

    def get_baseline(self, baseline_id: str) -> Baseline | None:
        row = self._conn.execute(
            "SELECT * FROM baselines WHERE baseline_id = ?", (baseline_id,)
        ).fetchone()
        if not row:
            return None
        config_data = json.loads(row["config_json"])
        return Baseline(
            baseline_id=row["baseline_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            config=RunConfig(
                model=config_data.get("model", "gpt-4.1"),
                max_iterations=config_data.get("max_iterations", 10),
                context_budget=config_data.get("context_budget", 128_000),
                directives=tuple(config_data.get("directives", [])),
                extra=config_data.get("extra", {}),
            ),
            metrics=json.loads(row["metrics_json"]),
            run_count=row["run_count"],
            run_ids=tuple(json.loads(row["run_ids_json"])),
            metadata=json.loads(row["metadata_json"]),
        )

    def get_latest_baseline(self, name: str = "") -> Baseline | None:
        """Get the most recent baseline, optionally filtered by name."""
        query = "SELECT baseline_id FROM baselines"
        params: list = []
        if name:
            query += " WHERE name = ?"
            params.append(name)
        query += " ORDER BY created_at DESC LIMIT 1"
        row = self._conn.execute(query, params).fetchone()
        if not row:
            return None
        return self.get_baseline(row["baseline_id"])

    # ── Experiments ───────────────────────────────────────────────────

    def save_experiment(self, experiment: Experiment) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO experiments
               (experiment_id, name, description, created_at,
                configs_json, scenario_ids, status, baseline_id,
                run_ids_json, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                experiment.experiment_id,
                experiment.name,
                experiment.description,
                experiment.created_at.isoformat(),
                json.dumps([c.to_dict() for c in experiment.configs]),
                json.dumps(list(experiment.scenario_ids)),
                str(experiment.status),
                experiment.baseline_id,
                json.dumps(list(experiment.run_ids)),
                json.dumps(experiment.metadata),
            ),
        )
        self._conn.commit()

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if not row:
            return None
        configs_data = json.loads(row["configs_json"])
        return Experiment(
            experiment_id=row["experiment_id"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            configs=tuple(
                RunConfig(
                    model=c.get("model", "gpt-4.1"),
                    max_iterations=c.get("max_iterations", 10),
                    context_budget=c.get("context_budget", 128_000),
                    directives=tuple(c.get("directives", [])),
                    extra=c.get("extra", {}),
                )
                for c in configs_data
            ),
            scenario_ids=tuple(json.loads(row["scenario_ids"])),
            status=row["status"],
            baseline_id=row["baseline_id"],
            run_ids=tuple(json.loads(row["run_ids_json"])),
            metadata=json.loads(row["metadata_json"]),
        )

    # ── Temporal queries ──────────────────────────────────────────────

    def list_runs_by_time(
        self,
        *,
        after: datetime | None = None,
        before: datetime | None = None,
        outcome: RunOutcome | None = None,
        limit: int = 100,
    ) -> list[RunRecord]:
        """List runs within a time range."""
        query = "SELECT * FROM runs WHERE 1=1"
        params: list = []
        if after:
            query += " AND started_at >= ?"
            params.append(after.isoformat())
        if before:
            query += " AND started_at <= ?"
            params.append(before.isoformat())
        if outcome:
            query += " AND outcome = ?"
            params.append(str(outcome))
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_run(r) for r in rows]

    def count_runs(
        self,
        *,
        after: datetime | None = None,
        before: datetime | None = None,
        outcome: RunOutcome | None = None,
        scenario_id: str | None = None,
    ) -> int:
        """Count runs matching filters (without loading full records)."""
        query = "SELECT COUNT(*) FROM runs WHERE 1=1"
        params: list = []
        if after:
            query += " AND started_at >= ?"
            params.append(after.isoformat())
        if before:
            query += " AND started_at <= ?"
            params.append(before.isoformat())
        if outcome:
            query += " AND outcome = ?"
            params.append(str(outcome))
        if scenario_id:
            query += " AND scenario_id = ?"
            params.append(scenario_id)
        return self._conn.execute(query, params).fetchone()[0]

    # ── Metric aggregation (SQL-level) ────────────────────────────────

    def aggregate_metric(
        self,
        metric_name: str,
        *,
        scenario_id: str | None = None,
        experiment_id: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> dict:
        """Aggregate a metric across runs using SQL.

        Returns dict with count, sum, avg, min, max — computed
        in SQLite, not in Python.  Much faster for large datasets.
        """
        query = """
            SELECT
                COUNT(m.value) as cnt,
                COALESCE(SUM(m.value), 0) as total,
                COALESCE(AVG(m.value), 0) as avg,
                COALESCE(MIN(m.value), 0) as min_val,
                COALESCE(MAX(m.value), 0) as max_val
            FROM metrics m
            JOIN runs r ON m.run_id = r.run_id
            WHERE m.name = ?
        """
        params: list = [metric_name]
        if scenario_id:
            query += " AND r.scenario_id = ?"
            params.append(scenario_id)
        if experiment_id:
            query += " AND r.experiment_id = ?"
            params.append(experiment_id)
        if after:
            query += " AND r.started_at >= ?"
            params.append(after.isoformat())
        if before:
            query += " AND r.started_at <= ?"
            params.append(before.isoformat())

        row = self._conn.execute(query, params).fetchone()
        return {
            "metric_name": metric_name,
            "count": row["cnt"],
            "sum": row["total"],
            "avg": row["avg"],
            "min": row["min_val"],
            "max": row["max_val"],
        }

    def metric_time_series(
        self,
        metric_name: str,
        *,
        scenario_id: str | None = None,
        limit: int = 1000,
    ) -> list[tuple[str, float]]:
        """Get a time-ordered series of (timestamp, value) for a metric.

        Returns values ordered by run start time — suitable for
        trend analysis.
        """
        query = """
            SELECT r.started_at, m.value
            FROM metrics m
            JOIN runs r ON m.run_id = r.run_id
            WHERE m.name = ?
        """
        params: list = [metric_name]
        if scenario_id:
            query += " AND r.scenario_id = ?"
            params.append(scenario_id)
        query += " ORDER BY r.started_at ASC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [(r[0], r[1]) for r in rows]

    def list_metric_names(self) -> list[str]:
        """Return all distinct metric names in the database."""
        rows = self._conn.execute(
            "SELECT DISTINCT name FROM metrics ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    # ── Tags ──────────────────────────────────────────────────────────

    def add_tag(self, run_id: str, key: str, value: str = "") -> None:
        """Add a tag to a run.  Tags are key-value pairs.

        Use for version labels, git SHAs, environment flags,
        feature flags, or experiment annotations.

        Examples:
            store.add_tag(run_id, "version", "v2.1.0")
            store.add_tag(run_id, "git_sha", "abc123f")
            store.add_tag(run_id, "env", "staging")
        """
        self._conn.execute(
            """INSERT INTO tags (run_id, key, value, created_at)
               VALUES (?, ?, ?, ?)""",
            (run_id, key, value, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_tags(self, run_id: str) -> dict[str, str]:
        """Get all tags for a run as a dict.

        If a key appears multiple times, the latest value wins.
        """
        rows = self._conn.execute(
            "SELECT key, value FROM tags WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def list_runs_by_tag(
        self,
        key: str,
        value: str | None = None,
        *,
        limit: int = 100,
    ) -> list[RunRecord]:
        """List runs that have a specific tag.

        If ``value`` is provided, matches exactly.
        If ``value`` is None, returns all runs with that key.
        """
        if value is not None:
            query = """
                SELECT DISTINCT r.* FROM runs r
                JOIN tags t ON r.run_id = t.run_id
                WHERE t.key = ? AND t.value = ?
                ORDER BY r.started_at DESC LIMIT ?
            """
            params: list = [key, value, limit]
        else:
            query = """
                SELECT DISTINCT r.* FROM runs r
                JOIN tags t ON r.run_id = t.run_id
                WHERE t.key = ?
                ORDER BY r.started_at DESC LIMIT ?
            """
            params = [key, limit]

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_run(r) for r in rows]

    def remove_tag(self, run_id: str, key: str) -> None:
        """Remove all tags with the given key from a run."""
        self._conn.execute(
            "DELETE FROM tags WHERE run_id = ? AND key = ?",
            (run_id, key),
        )
        self._conn.commit()

    # ── Annotations ───────────────────────────────────────────────────

    def add_annotation(
        self,
        run_id: str,
        content: str,
        *,
        author: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Add a human annotation to a run.

        Use for observations, bug IDs, notes, or quality feedback.
        Unlike tags, annotations are append-only and timestamped.
        """
        self._conn.execute(
            """INSERT INTO annotations
               (run_id, author, content, created_at, metadata_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                run_id,
                author,
                content,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(metadata or {}),
            ),
        )
        self._conn.commit()

    def get_annotations(self, run_id: str) -> list[dict]:
        """Get all annotations for a run, ordered by creation time."""
        rows = self._conn.execute(
            """SELECT author, content, created_at, metadata_json
               FROM annotations WHERE run_id = ?
               ORDER BY created_at""",
            (run_id,),
        ).fetchall()
        return [
            {
                "author": r["author"],
                "content": r["content"],
                "created_at": r["created_at"],
                "metadata": json.loads(r["metadata_json"]),
            }
            for r in rows
        ]

    # ── Search ────────────────────────────────────────────────────────

    def search_raw_events(
        self,
        *,
        run_id: str = "",
        event_type: str = "",
        payload_contains: str = "",
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[RawEvent]:
        """Search raw events with rich filters.

        ``payload_contains`` does a SQLite LIKE search on the
        JSON payload — useful for finding events mentioning a
        specific tool, error message, or keyword.
        """
        query = "SELECT * FROM raw_events WHERE 1=1"
        params: list = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if payload_contains:
            query += " AND payload LIKE ?"
            params.append(f"%{payload_contains}%")
        if after:
            query += " AND timestamp >= ?"
            params.append(after.isoformat())
        if before:
            query += " AND timestamp <= ?"
            params.append(before.isoformat())
        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            RawEvent(
                event_id=r["event_id"],
                run_id=r["run_id"],
                event_type=r["event_type"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                payload=json.loads(r["payload"]),
            )
            for r in rows
        ]

    def event_type_counts(
        self,
        *,
        run_id: str = "",
    ) -> dict[str, int]:
        """Count raw events by event_type.

        Returns a dict of event_type → count.
        """
        query = "SELECT event_type, COUNT(*) as cnt FROM raw_events"
        params: list = []
        if run_id:
            query += " WHERE run_id = ?"
            params.append(run_id)
        query += " GROUP BY event_type ORDER BY cnt DESC"

        rows = self._conn.execute(query, params).fetchall()
        return {r["event_type"]: r["cnt"] for r in rows}

    # ── Lifecycle management ──────────────────────────────────────────

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and all associated data.

        Removes turns, tool_calls, metrics, raw_events, tags,
        and annotations for the given run.  Returns True if the
        run existed (and was deleted).
        """
        existing = self._conn.execute(
            "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not existing:
            return False

        # FK cascades don't auto-delete in SQLite unless we
        # define ON DELETE CASCADE — do it explicitly.
        for table in (
            "turns", "tool_calls", "metrics",
            "raw_events", "tags", "annotations",
        ):
            self._conn.execute(
                f"DELETE FROM {table} WHERE run_id = ?", (run_id,)
            )
        self._conn.execute(
            "DELETE FROM runs WHERE run_id = ?", (run_id,)
        )
        self._conn.commit()
        logger.debug("Deleted run %s", run_id)
        return True

    def purge_before(self, cutoff: datetime) -> int:
        """Delete all runs started before the cutoff datetime.

        Returns the number of runs deleted.  Use for data retention
        policies — keep the last N days of data.
        """
        rows = self._conn.execute(
            "SELECT run_id FROM runs WHERE started_at < ?",
            (cutoff.isoformat(),),
        ).fetchall()

        count = 0
        for row in rows:
            if self.delete_run(row["run_id"]):
                count += 1

        logger.info("Purged %d runs before %s", count, cutoff.isoformat())
        return count

    def list_experiments(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Experiment]:
        """List all experiments, optionally filtered by status."""
        query = "SELECT experiment_id FROM experiments"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            exp = self.get_experiment(r["experiment_id"])
            if exp:
                results.append(exp)
        return results

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment record (does not delete associated runs).

        Returns True if the experiment existed.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if not existing:
            return False

        self._conn.execute(
            "DELETE FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        )
        self._conn.commit()
        logger.debug("Deleted experiment %s", experiment_id)
        return True

    def delete_baseline(self, baseline_id: str) -> bool:
        """Delete a baseline record (does not delete associated runs).

        Returns True if the baseline existed.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM baselines WHERE baseline_id = ?",
            (baseline_id,),
        ).fetchone()
        if not existing:
            return False

        self._conn.execute(
            "DELETE FROM baselines WHERE baseline_id = ?",
            (baseline_id,),
        )
        self._conn.commit()
        logger.debug("Deleted baseline %s", baseline_id)
        return True

    def database_stats(self) -> dict[str, int]:
        """Return row counts for every table.

        Useful for monitoring database growth and diagnosing
        storage issues.
        """
        tables = [
            "runs", "turns", "tool_calls", "metrics",
            "raw_events", "scenarios", "baselines",
            "experiments", "tags", "annotations",
        ]
        stats: dict[str, int] = {}
        for table in tables:
            row = self._conn.execute(
                f"SELECT COUNT(*) as cnt FROM {table}"
            ).fetchone()
            stats[table] = row["cnt"]
        return stats

    def vacuum(self) -> None:
        """Reclaim disk space after deleting data.

        SQLite doesn't automatically shrink the database file
        after deletes.  Call this periodically after purges.
        """
        self._conn.execute("VACUUM")
        logger.debug("Database vacuumed")
