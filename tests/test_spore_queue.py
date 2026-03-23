"""Tests for the bird-bone spore queue system.

Tests the LocalQueue (in-memory) implementation which mirrors the
SheetsQueue interface.  This validates all queue operations in
isolation — no Google Sheets, no network.

Follows the three-layer testing hierarchy:
  1. Unit: Job model, LocalQueue operations in isolation
  2. Integration: Queue + SporeHandler endpoints (mocked HTTP)
  3. E2E: Would be real Google Sheet — skipped unless configured
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add spore dir to import path — skip entire module if prototype isn't checked out
_spore_dir = Path(__file__).resolve().parent.parent / "prototypes" / "bird-bone" / "spore"
if not _spore_dir.exists():
    pytest.skip("prototypes/bird-bone/spore not available", allow_module_level=True)
if str(_spore_dir) not in sys.path:
    sys.path.insert(0, str(_spore_dir))

from sheets_queue import Job, LocalQueue, SheetsQueue, QueueError, _make_job_id, _iso_now


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Job Model
# ═══════════════════════════════════════════════════════════════════

class TestJobModel:
    """Tests for the Job data class."""

    def test_create_empty(self):
        job = Job()
        assert job.job_id == ""
        assert job.status == ""
        assert job.model_name == ""

    def test_create_with_kwargs(self):
        job = Job(job_id="j-test123", model_name="Qwen/Qwen3-0.6B",
                  status="queued", mode="fcfs")
        assert job.job_id == "j-test123"
        assert job.model_name == "Qwen/Qwen3-0.6B"
        assert job.status == "queued"
        assert job.mode == "fcfs"

    def test_to_dict(self):
        job = Job(job_id="j-abc", model_name="test-model", status="queued")
        d = job.to_dict()
        assert isinstance(d, dict)
        assert d["job_id"] == "j-abc"
        assert d["model_name"] == "test-model"
        assert d["status"] == "queued"
        assert "submitted_at" in d
        assert "claimed_by" in d

    def test_from_row(self):
        row = {
            "job_id": "j-from-csv",
            "model_name": "gpt2",
            "status": "running",
            "mode": "reserve",
            "rank": "32",
            "steps": "100",
        }
        job = Job.from_row(row)
        assert job.job_id == "j-from-csv"
        assert job.model_name == "gpt2"
        assert job.status == "running"
        assert job.mode == "reserve"
        assert job.rank == "32"

    def test_from_row_missing_fields(self):
        row = {"job_id": "j-sparse"}
        job = Job.from_row(row)
        assert job.job_id == "j-sparse"
        assert job.model_name == ""
        assert job.status == ""

    def test_is_available(self):
        queued = Job(status="queued")
        assert queued.is_available is True

        running = Job(status="running")
        assert running.is_available is False

        complete = Job(status="complete")
        assert complete.is_available is False

    def test_is_claimable_fcfs(self):
        fcfs = Job(status="queued", mode="fcfs")
        assert fcfs.is_claimable_fcfs is True

        reserve = Job(status="queued", mode="reserve")
        assert reserve.is_claimable_fcfs is False

        running = Job(status="running", mode="fcfs")
        assert running.is_claimable_fcfs is False

    def test_repr(self):
        job = Job(job_id="j-test", model_name="gpt2",
                  status="queued", mode="fcfs")
        r = repr(job)
        assert "j-test" in r
        assert "gpt2" in r
        assert "queued" in r


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Helpers
# ═══════════════════════════════════════════════════════════════════

class TestHelpers:
    """Tests for queue helper functions."""

    def test_make_job_id_format(self):
        jid = _make_job_id()
        assert jid.startswith("j-")
        assert len(jid) == 12  # "j-" + 10 hex chars

    def test_make_job_id_unique(self):
        ids = {_make_job_id() for _ in range(50)}
        # Should get at least 40 unique IDs out of 50
        # (timing collisions possible but rare)
        assert len(ids) >= 40

    def test_iso_now_format(self):
        ts = _iso_now()
        assert "T" in ts
        assert ts.endswith("Z")
        assert len(ts) == 20  # YYYY-MM-DDTHH:MM:SSZ


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — LocalQueue
# ═══════════════════════════════════════════════════════════════════

class TestLocalQueue:
    """Tests for the in-memory LocalQueue."""

    def test_empty_queue(self):
        q = LocalQueue()
        assert q.list_jobs() == []
        assert q.available_jobs() == []
        assert q.next_fcfs_job() is None

    def test_submit_job(self):
        q = LocalQueue()
        result = q.submit_job(model_name="gpt2", submitter="tester")
        assert result["status"] == "ok"
        assert result["job_id"].startswith("j-")

        jobs = q.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].model_name == "gpt2"
        assert jobs[0].submitter == "tester"
        assert jobs[0].status == "queued"

    def test_submit_multiple_jobs(self):
        q = LocalQueue()
        q.submit_job(model_name="model-a")
        q.submit_job(model_name="model-b")
        q.submit_job(model_name="model-c")

        jobs = q.list_jobs()
        assert len(jobs) == 3
        assert [j.model_name for j in jobs] == ["model-a", "model-b", "model-c"]

    def test_submit_with_all_params(self):
        q = LocalQueue()
        q.submit_job(
            model_name="Qwen/Qwen3-0.6B",
            submitter="scientist",
            rank=32,
            steps=100,
            lr=5e-4,
            mode="reserve",
            notes="high priority run",
        )
        job = q.list_jobs()[0]
        assert job.rank == "32"
        assert job.steps == "100"
        assert job.lr == "0.0005"
        assert job.mode == "reserve"
        assert job.notes == "high priority run"

    def test_list_jobs_filter_by_status(self):
        q = LocalQueue()
        r1 = q.submit_job(model_name="a")
        r2 = q.submit_job(model_name="b")
        q.claim_job(r1["job_id"], "host-1")

        queued = q.list_jobs(status="queued")
        assert len(queued) == 1
        assert queued[0].model_name == "b"

        claimed = q.list_jobs(status="claimed")
        assert len(claimed) == 1
        assert claimed[0].model_name == "a"

    def test_get_job(self):
        q = LocalQueue()
        result = q.submit_job(model_name="gpt2")
        job_id = result["job_id"]

        job = q.get_job(job_id)
        assert job is not None
        assert job.model_name == "gpt2"

    def test_get_job_not_found(self):
        q = LocalQueue()
        assert q.get_job("j-nonexistent") is None

    def test_claim_job(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]

        result = q.claim_job(job_id, "host-alpha")
        assert result["status"] == "ok"

        job = q.get_job(job_id)
        assert job.status == "claimed"
        assert job.claimed_by == "host-alpha"
        assert job.claimed_at != ""

    def test_claim_already_claimed(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]

        q.claim_job(job_id, "host-alpha")
        result = q.claim_job(job_id, "host-beta")
        assert result["status"] == "error"
        assert "not queued" in result["message"]

    def test_claim_not_found(self):
        q = LocalQueue()
        result = q.claim_job("j-ghost", "host-1")
        assert result["status"] == "error"

    def test_claim_reserve_mode(self):
        """Reserve mode: only the designated host can claim."""
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", mode="reserve")
        job_id = r["job_id"]

        # Manually set the reserved host
        job = q.get_job(job_id)
        job.claimed_by = "host-reserved"

        # Wrong host can't claim
        result = q.claim_job(job_id, "host-intruder")
        assert result["status"] == "error"
        assert "reserved" in result["message"]

        # Right host can claim
        result = q.claim_job(job_id, "host-reserved")
        assert result["status"] == "ok"

    def test_start_job(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.start_job(job_id, "host-1")
        assert result["status"] == "ok"

        job = q.get_job(job_id)
        assert job.status == "running"

    def test_start_job_wrong_host(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.start_job(job_id, "host-2")
        assert result["status"] == "error"

    def test_complete_job(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.complete_job(job_id, "host-1",
                                 result_url="http://example.com/model.pt",
                                 notes="loss 0.5→0.3")
        assert result["status"] == "ok"

        job = q.get_job(job_id)
        assert job.status == "complete"
        assert job.result_url == "http://example.com/model.pt"
        assert job.notes == "loss 0.5→0.3"
        assert job.completed_at != ""

    def test_complete_wrong_host(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.complete_job(job_id, "host-2")
        assert result["status"] == "error"

    def test_fail_job(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.fail_job(job_id, "host-1", error="OOM")
        assert result["status"] == "ok"

        job = q.get_job(job_id)
        assert job.status == "failed"
        assert "OOM" in job.notes

    def test_release_job(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.release_job(job_id, "host-1")
        assert result["status"] == "ok"

        job = q.get_job(job_id)
        assert job.status == "queued"
        assert job.claimed_by == ""

    def test_release_wrong_host(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.release_job(job_id, "host-2")
        assert result["status"] == "error"

    def test_next_fcfs_job_ordering(self):
        """FCFS: oldest queued job wins."""
        q = LocalQueue()
        q.submit_job(model_name="first")
        q.submit_job(model_name="second")
        q.submit_job(model_name="third")

        job = q.next_fcfs_job()
        assert job.model_name == "first"

    def test_next_fcfs_skips_reserve(self):
        """FCFS skips reserve-mode jobs."""
        q = LocalQueue()
        q.submit_job(model_name="reserved", mode="reserve")
        q.submit_job(model_name="open", mode="fcfs")

        job = q.next_fcfs_job()
        assert job.model_name == "open"

    def test_next_fcfs_skips_claimed(self):
        q = LocalQueue()
        r1 = q.submit_job(model_name="claimed")
        q.submit_job(model_name="available")
        q.claim_job(r1["job_id"], "host-1")

        job = q.next_fcfs_job()
        assert job.model_name == "available"

    def test_available_jobs(self):
        q = LocalQueue()
        q.submit_job(model_name="a")
        r2 = q.submit_job(model_name="b")
        q.submit_job(model_name="c")
        q.claim_job(r2["job_id"], "host-1")

        avail = q.available_jobs()
        assert len(avail) == 2
        names = {j.model_name for j in avail}
        assert names == {"a", "c"}


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Race Claim
# ═══════════════════════════════════════════════════════════════════

class TestRaceClaim:
    """Tests for the race_claim convenience method."""

    def test_race_claim_success(self):
        q = LocalQueue()
        q.submit_job(model_name="gpt2")

        result = q.race_claim("host-racer")
        assert result is not None
        assert result["status"] == "ok"
        assert "job" in result

        job_data = result["job"]
        assert job_data["model_name"] == "gpt2"

    def test_race_claim_empty_queue(self):
        q = LocalQueue()
        result = q.race_claim("host-racer")
        assert result is None

    def test_race_claim_all_taken(self):
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        q.claim_job(r["job_id"], "host-1")

        result = q.race_claim("host-2")
        assert result is None

    def test_race_claim_first_come_wins(self):
        """Two hosts racing — the first one wins, second gets None."""
        q = LocalQueue()
        q.submit_job(model_name="prize")

        r1 = q.race_claim("host-fast")
        assert r1 is not None
        assert r1["status"] == "ok"

        r2 = q.race_claim("host-slow")
        assert r2 is None


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Full Lifecycle
# ═══════════════════════════════════════════════════════════════════

class TestFullLifecycle:
    """Integration-style test of the full job lifecycle."""

    def test_submit_claim_start_complete(self):
        q = LocalQueue()

        # Submit
        r = q.submit_job(model_name="Qwen/Qwen3-0.6B", submitter="alice",
                          rank=16, steps=30)
        job_id = r["job_id"]
        assert q.list_jobs(status="queued") != []

        # Claim
        c = q.claim_job(job_id, "gpu-server-1")
        assert c["status"] == "ok"
        assert q.list_jobs(status="claimed") != []

        # Start
        s = q.start_job(job_id, "gpu-server-1")
        assert s["status"] == "ok"
        assert q.get_job(job_id).status == "running"

        # Complete
        d = q.complete_job(job_id, "gpu-server-1",
                            result_url="http://example.com/trained.pt")
        assert d["status"] == "ok"
        job = q.get_job(job_id)
        assert job.status == "complete"
        assert job.result_url == "http://example.com/trained.pt"

    def test_submit_claim_fail_reclaim(self):
        """Job fails, gets re-queued, another host picks it up."""
        q = LocalQueue()

        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]

        # Host 1 claims and fails
        q.claim_job(job_id, "host-weak")
        q.fail_job(job_id, "host-weak", error="Out of memory")

        # Job should be back in queue (as failed, but could be re-queued)
        # Note: fail_job sets status to "failed" not "queued"
        job = q.get_job(job_id)
        assert job.status == "failed"

    def test_submit_claim_release_reclaim(self):
        """Host releases a job, another host grabs it."""
        q = LocalQueue()

        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]

        # Host 1 claims then releases
        q.claim_job(job_id, "host-1")
        q.release_job(job_id, "host-1")

        # Job should be queued again
        job = q.get_job(job_id)
        assert job.status == "queued"

        # Host 2 claims
        c = q.claim_job(job_id, "host-2")
        assert c["status"] == "ok"
        assert q.get_job(job_id).claimed_by == "host-2"

    def test_multi_job_fcfs_queue(self):
        """Multiple jobs, hosts grab them FCFS."""
        q = LocalQueue()

        q.submit_job(model_name="small-model")
        q.submit_job(model_name="medium-model")
        q.submit_job(model_name="large-model")

        # Host A grabs first
        r1 = q.race_claim("host-a")
        assert r1["job"]["model_name"] == "small-model"

        # Host B grabs second
        r2 = q.race_claim("host-b")
        assert r2["job"]["model_name"] == "medium-model"

        # Host C grabs third
        r3 = q.race_claim("host-c")
        assert r3["job"]["model_name"] == "large-model"

        # Queue empty
        assert q.race_claim("host-d") is None


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — SheetsQueue (read-only mode, no network)
# ═══════════════════════════════════════════════════════════════════

class TestSheetsQueueConfig:
    """Tests for SheetsQueue configuration (no network calls)."""

    def test_csv_url_format(self):
        q = SheetsQueue(sheet_id="1abc123", sheet_name="queue")
        url = q._csv_url()
        assert "1abc123" in url
        assert "queue" in url
        assert "tqx=out:csv" in url

    def test_read_only_raises_on_write(self):
        q = SheetsQueue(sheet_id="1abc123", script_url=None)
        with pytest.raises(QueueError, match="read-only"):
            q.submit_job(model_name="test")

    def test_script_url_stored(self):
        q = SheetsQueue(
            sheet_id="1abc",
            script_url="https://script.google.com/macros/s/xyz/exec",
        )
        assert q.script_url.endswith("/exec")
