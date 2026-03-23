"""Tests for queue ownership enforcement with identity signing.

Integration tests: Identity + LocalQueue — verifies that job
submit/cancel operations properly enforce ownership via HMAC signatures.

Follows TDD: RED → GREEN for ownership enforcement.
"""

import sys
from pathlib import Path

import pytest

# Add spore dir to import path — skip entire module if prototype isn't checked out
_spore_dir = Path(__file__).resolve().parent.parent / "prototypes" / "bird-bone" / "spore"
if not _spore_dir.exists():
    pytest.skip("prototypes/bird-bone/spore not available", allow_module_level=True)
if str(_spore_dir) not in sys.path:
    sys.path.insert(0, str(_spore_dir))

from identity import Identity, AuthError, server_verify_signature, _canonicalize, _hmac_sign
from sheets_queue import Job, LocalQueue, QueueError


# ═══════════════════════════════════════════════════════════════════
# Test Constants
# ═══════════════════════════════════════════════════════════════════

SALT = "test-server-salt"

ALICE_CLAIMS = {
    "sub": "alice-google-id-123",
    "email": "alice@example.com",
    "name": "Alice",
}

BOB_CLAIMS = {
    "sub": "bob-google-id-456",
    "email": "bob@example.com",
    "name": "Bob",
}


def _make_alice():
    return Identity.from_google_claims(ALICE_CLAIMS, SALT)


def _make_bob():
    return Identity.from_google_claims(BOB_CLAIMS, SALT)


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Job Model Owner Fields
# ═══════════════════════════════════════════════════════════════════

class TestJobOwnerFields:
    """Tests for owner_id and signature fields on Job."""

    def test_job_has_owner_slots(self):
        assert "owner_id" in Job.__slots__
        assert "signature" in Job.__slots__

    def test_job_owner_default_empty(self):
        job = Job()
        assert job.owner_id == ""
        assert job.signature == ""

    def test_job_with_owner(self):
        job = Job(
            job_id="j-test",
            owner_id="u-abc123def456",
            signature="deadbeef" * 8,
        )
        assert job.owner_id == "u-abc123def456"
        assert job.signature == "deadbeef" * 8

    def test_job_to_dict_includes_owner(self):
        job = Job(owner_id="u-xyz", signature="sig123")
        d = job.to_dict()
        assert d["owner_id"] == "u-xyz"
        assert d["signature"] == "sig123"

    def test_job_from_row_with_owner(self):
        row = {
            "job_id": "j-owned",
            "owner_id": "u-abc123def456",
            "signature": "a" * 64,
            "model_name": "gpt2",
            "status": "queued",
        }
        job = Job.from_row(row)
        assert job.owner_id == "u-abc123def456"
        assert job.signature == "a" * 64


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Signed Job Submission
# ═══════════════════════════════════════════════════════════════════

class TestSignedSubmission:
    """Tests for submitting jobs with ownership signatures."""

    def test_submit_with_owner(self):
        """Submit a job with owner_id and signature."""
        alice = _make_alice()
        q = LocalQueue()

        fields = {"model_name": "gpt2", "rank": "16", "steps": "30",
                  "lr": "0.001", "mode": "fcfs"}
        sig = alice.sign_job(fields)

        result = q.submit_job(
            model_name="gpt2",
            submitter=alice.email,
            rank=16,
            steps=30,
            lr=1e-3,
            mode="fcfs",
            owner_id=alice.public_id,
            signature=sig,
        )
        assert result["status"] == "ok"

        job = q.list_jobs()[0]
        assert job.owner_id == alice.public_id
        assert job.signature == sig

    def test_submit_anonymous_no_owner(self):
        """Anonymous submissions have empty owner fields."""
        q = LocalQueue()
        q.submit_job(model_name="gpt2")

        job = q.list_jobs()[0]
        assert job.owner_id == ""
        assert job.signature == ""

    def test_submit_preserves_backward_compat(self):
        """Existing submit calls without owner args still work."""
        q = LocalQueue()
        result = q.submit_job(
            model_name="gpt2",
            submitter="tester",
            rank=16,
            steps=30,
        )
        assert result["status"] == "ok"
        job = q.list_jobs()[0]
        assert job.model_name == "gpt2"
        assert job.owner_id == ""


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Cancel Job with Ownership
# ═══════════════════════════════════════════════════════════════════

class TestCancelJobOwnership:
    """Tests for cancel_job ownership enforcement."""

    def test_owner_can_cancel_own_job(self):
        """Alice can cancel her own job."""
        alice = _make_alice()
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", owner_id=alice.public_id)
        job_id = r["job_id"]

        result = q.cancel_job(job_id, alice.public_id)
        assert result["status"] == "ok"
        assert q.get_job(job_id) is None

    def test_stranger_cannot_cancel_owned_job(self):
        """Bob cannot cancel Alice's job."""
        alice = _make_alice()
        bob = _make_bob()
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", owner_id=alice.public_id)
        job_id = r["job_id"]

        result = q.cancel_job(job_id, bob.public_id)
        assert result["status"] == "error"
        assert "owned by" in result["message"]

        # Job still exists
        assert q.get_job(job_id) is not None

    def test_anyone_can_cancel_anonymous_job(self):
        """Anonymous jobs (no owner_id) can be cancelled by anyone."""
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2")
        job_id = r["job_id"]

        result = q.cancel_job(job_id, "random-user")
        assert result["status"] == "ok"
        assert q.get_job(job_id) is None

    def test_cannot_cancel_running_job(self):
        """Cannot cancel a job that is already running."""
        alice = _make_alice()
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", owner_id=alice.public_id)
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")
        q.start_job(job_id, "host-1")

        result = q.cancel_job(job_id, alice.public_id)
        assert result["status"] == "error"
        assert "cannot cancel" in result["message"]

    def test_cannot_cancel_complete_job(self):
        """Cannot cancel a job that is complete."""
        alice = _make_alice()
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", owner_id=alice.public_id)
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")
        q.complete_job(job_id, "host-1")

        result = q.cancel_job(job_id, alice.public_id)
        assert result["status"] == "error"
        assert "cannot cancel" in result["message"]

    def test_owner_can_cancel_claimed_job(self):
        """Owner can cancel a job that's been claimed but not started."""
        alice = _make_alice()
        q = LocalQueue()
        r = q.submit_job(model_name="gpt2", owner_id=alice.public_id)
        job_id = r["job_id"]
        q.claim_job(job_id, "host-1")

        result = q.cancel_job(job_id, alice.public_id)
        assert result["status"] == "ok"
        assert q.get_job(job_id) is None

    def test_cancel_not_found(self):
        """Cancel a non-existent job."""
        q = LocalQueue()
        result = q.cancel_job("j-ghost", "some-user")
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ═══════════════════════════════════════════════════════════════════
# Integration Tests — Full Signed Lifecycle
# ═══════════════════════════════════════════════════════════════════

class TestSignedLifecycle:
    """Full lifecycle: signed submit → claim → complete → verify ownership."""

    def test_alice_submits_bob_cannot_cancel(self):
        """Complete flow: Alice submits, Bob tries to cancel, fails."""
        alice = _make_alice()
        bob = _make_bob()
        q = LocalQueue()

        # Alice submits with signature
        fields = {"model_name": "Qwen/Qwen3-0.6B", "rank": "16",
                  "steps": "30", "lr": "0.001", "mode": "fcfs"}
        sig = alice.sign_job(fields)

        r = q.submit_job(
            model_name="Qwen/Qwen3-0.6B",
            submitter=alice.email,
            rank=16, steps=30,
            owner_id=alice.public_id,
            signature=sig,
        )
        job_id = r["job_id"]

        # Server can verify Alice's signature
        assert server_verify_signature(
            "alice-google-id-123", SALT, fields, sig
        ) is True

        # Bob tries to cancel — denied
        result = q.cancel_job(job_id, bob.public_id)
        assert result["status"] == "error"

        # Alice cancels — allowed
        result = q.cancel_job(job_id, alice.public_id)
        assert result["status"] == "ok"

    def test_mixed_owned_and_anonymous_queue(self):
        """Queue with a mix of owned and anonymous jobs."""
        alice = _make_alice()
        bob = _make_bob()
        q = LocalQueue()

        # Alice submits an owned job
        r1 = q.submit_job(model_name="alice-model", owner_id=alice.public_id)
        # Bob submits an owned job
        r2 = q.submit_job(model_name="bob-model", owner_id=bob.public_id)
        # Anonymous job
        r3 = q.submit_job(model_name="open-model")

        assert len(q.list_jobs()) == 3

        # Alice can't cancel Bob's job
        assert q.cancel_job(r2["job_id"], alice.public_id)["status"] == "error"

        # Bob can't cancel Alice's job
        assert q.cancel_job(r1["job_id"], bob.public_id)["status"] == "error"

        # Anyone can cancel the anonymous job
        assert q.cancel_job(r3["job_id"], "random")["status"] == "ok"

        # Each owner can cancel their own
        assert q.cancel_job(r1["job_id"], alice.public_id)["status"] == "ok"
        assert q.cancel_job(r2["job_id"], bob.public_id)["status"] == "ok"

        assert len(q.list_jobs()) == 0

    def test_signature_verifiable_on_stored_job(self):
        """After submission, the stored signature can be verified server-side."""
        alice = _make_alice()
        q = LocalQueue()

        fields = {"model_name": "gpt2", "rank": "32", "steps": "50",
                  "lr": "0.0005", "mode": "fcfs"}
        sig = alice.sign_job(fields)

        q.submit_job(
            model_name="gpt2", rank=32, steps=50, lr=5e-4,
            owner_id=alice.public_id, signature=sig,
        )

        # Retrieve the job and verify its signature
        job = q.list_jobs()[0]
        assert job.owner_id == alice.public_id
        assert job.signature == sig

        # Server verifies the stored signature
        assert server_verify_signature(
            "alice-google-id-123", SALT, fields, job.signature
        ) is True

    def test_ownership_survives_claim_and_complete(self):
        """Owner fields persist through the full lifecycle."""
        alice = _make_alice()
        q = LocalQueue()

        r = q.submit_job(
            model_name="gpt2", owner_id=alice.public_id,
            signature="test-sig",
        )
        job_id = r["job_id"]

        # Claim
        q.claim_job(job_id, "host-1")
        job = q.get_job(job_id)
        assert job.owner_id == alice.public_id
        assert job.signature == "test-sig"

        # Start
        q.start_job(job_id, "host-1")
        job = q.get_job(job_id)
        assert job.owner_id == alice.public_id

        # Complete
        q.complete_job(job_id, "host-1", result_url="http://example.com")
        job = q.get_job(job_id)
        assert job.owner_id == alice.public_id
        assert job.signature == "test-sig"
