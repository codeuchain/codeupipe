"""Tests for the bird-bone spore identity & signing system.

Tests the Identity class, HMAC signing/verification, key derivation,
and ownership enforcement.  All in isolation — no Google API calls.

Follows the three-layer testing hierarchy:
  1. Unit: Identity creation, signing, verification, canonicalization
  2. Integration: Identity + LocalQueue ownership enforcement
  3. E2E: Would be real Google OAuth — skipped unless configured
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add spore dir to import path
_spore_dir = Path(__file__).resolve().parent.parent / "prototypes" / "bird-bone" / "spore"
if str(_spore_dir) not in sys.path:
    sys.path.insert(0, str(_spore_dir))

from identity import (
    Identity,
    AuthError,
    verify_google_id_token,
    verify_identity_offline,
    server_verify_signature,
    server_derive_secret,
    _derive_signing_secret,
    _derive_public_id,
    _canonicalize,
    _hmac_sign,
    _hmac_verify,
)


# ═══════════════════════════════════════════════════════════════════
# Test Constants
# ═══════════════════════════════════════════════════════════════════

SALT = "test-server-salt-keep-secret"
GOOGLE_ID = "118234567890123456789"
EMAIL = "alice@example.com"
NAME = "Alice Builder"
PICTURE = "https://lh3.googleusercontent.com/photo.jpg"
CLIENT_ID = "123456789-app.apps.googleusercontent.com"

CLAIMS = {
    "sub": GOOGLE_ID,
    "email": EMAIL,
    "email_verified": "true",
    "name": NAME,
    "picture": PICTURE,
    "aud": CLIENT_ID,
    "exp": "9999999999",  # Far future
}


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Crypto Primitives
# ═══════════════════════════════════════════════════════════════════

class TestCryptoPrimitives:
    """Tests for the low-level HMAC and derivation functions."""

    def test_canonicalize_sorted_keys(self):
        """Keys are sorted alphabetically regardless of insertion order."""
        fields = {"model_name": "gpt2", "rank": "16", "steps": "30"}
        canonical = _canonicalize(fields)
        assert canonical == b"model_name=gpt2&rank=16&steps=30"

    def test_canonicalize_reverse_order(self):
        """Same output regardless of dict ordering."""
        a = _canonicalize({"z": "1", "a": "2", "m": "3"})
        b = _canonicalize({"a": "2", "m": "3", "z": "1"})
        assert a == b

    def test_canonicalize_empty(self):
        assert _canonicalize({}) == b""

    def test_canonicalize_single(self):
        assert _canonicalize({"key": "val"}) == b"key=val"

    def test_hmac_sign_returns_hex(self):
        sig = _hmac_sign(b"test data", "test-secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in sig)

    def test_hmac_sign_deterministic(self):
        """Same input always produces the same signature."""
        sig1 = _hmac_sign(b"hello", "secret")
        sig2 = _hmac_sign(b"hello", "secret")
        assert sig1 == sig2

    def test_hmac_sign_different_data(self):
        """Different data produces different signatures."""
        sig1 = _hmac_sign(b"hello", "secret")
        sig2 = _hmac_sign(b"world", "secret")
        assert sig1 != sig2

    def test_hmac_sign_different_secrets(self):
        """Different secrets produce different signatures."""
        sig1 = _hmac_sign(b"hello", "secret-a")
        sig2 = _hmac_sign(b"hello", "secret-b")
        assert sig1 != sig2

    def test_hmac_verify_correct(self):
        sig = _hmac_sign(b"test data", "my-secret")
        assert _hmac_verify(b"test data", "my-secret", sig) is True

    def test_hmac_verify_wrong_data(self):
        sig = _hmac_sign(b"test data", "my-secret")
        assert _hmac_verify(b"wrong data", "my-secret", sig) is False

    def test_hmac_verify_wrong_secret(self):
        sig = _hmac_sign(b"test data", "my-secret")
        assert _hmac_verify(b"test data", "wrong-secret", sig) is False

    def test_hmac_verify_wrong_sig(self):
        assert _hmac_verify(b"data", "secret", "deadbeef" * 8) is False

    def test_derive_signing_secret_deterministic(self):
        """Same Google ID + salt always gives the same secret."""
        s1 = _derive_signing_secret(GOOGLE_ID, SALT)
        s2 = _derive_signing_secret(GOOGLE_ID, SALT)
        assert s1 == s2

    def test_derive_signing_secret_format(self):
        secret = _derive_signing_secret(GOOGLE_ID, SALT)
        assert isinstance(secret, str)
        assert len(secret) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in secret)

    def test_derive_signing_secret_different_ids(self):
        """Different Google IDs produce different secrets."""
        s1 = _derive_signing_secret("user-1", SALT)
        s2 = _derive_signing_secret("user-2", SALT)
        assert s1 != s2

    def test_derive_signing_secret_different_salts(self):
        """Different salts produce different secrets."""
        s1 = _derive_signing_secret(GOOGLE_ID, "salt-a")
        s2 = _derive_signing_secret(GOOGLE_ID, "salt-b")
        assert s1 != s2

    def test_derive_public_id_format(self):
        pid = _derive_public_id(GOOGLE_ID)
        assert pid.startswith("u-")
        assert len(pid) == 14  # "u-" + 12 hex chars
        assert all(c in "0123456789abcdef-u" for c in pid)

    def test_derive_public_id_deterministic(self):
        p1 = _derive_public_id(GOOGLE_ID)
        p2 = _derive_public_id(GOOGLE_ID)
        assert p1 == p2

    def test_derive_public_id_different_ids(self):
        p1 = _derive_public_id("user-a")
        p2 = _derive_public_id("user-b")
        assert p1 != p2


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Identity Class
# ═══════════════════════════════════════════════════════════════════

class TestIdentity:
    """Tests for the Identity data class and methods."""

    def test_create_basic(self):
        identity = Identity(
            google_id=GOOGLE_ID,
            email=EMAIL,
            name=NAME,
        )
        assert identity.google_id == GOOGLE_ID
        assert identity.email == EMAIL
        assert identity.name == NAME
        assert identity.public_id.startswith("u-")

    def test_public_id_derived(self):
        """Public ID is derived from Google ID, not stored separately."""
        identity = Identity(google_id=GOOGLE_ID, email=EMAIL)
        expected_pid = _derive_public_id(GOOGLE_ID)
        assert identity.public_id == expected_pid

    def test_from_google_claims(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        assert identity.google_id == GOOGLE_ID
        assert identity.email == EMAIL
        assert identity.name == NAME
        assert identity.picture == PICTURE
        assert identity.signing_secret != ""
        assert len(identity.signing_secret) == 64

    def test_from_google_claims_missing_sub(self):
        bad_claims = {"email": "test@example.com"}
        with pytest.raises(AuthError, match="sub"):
            Identity.from_google_claims(bad_claims, SALT)

    def test_from_google_claims_empty_sub(self):
        bad_claims = {"sub": "", "email": "test@example.com"}
        with pytest.raises(AuthError, match="sub"):
            Identity.from_google_claims(bad_claims, SALT)

    def test_from_signing_secret(self):
        """Reconstruct identity from a saved signing secret."""
        # First, create normally
        original = Identity.from_google_claims(CLAIMS, SALT)
        secret = original.signing_secret
        pid = original.public_id

        # Reconstruct from saved secret
        restored = Identity.from_signing_secret(
            signing_secret=secret,
            public_id=pid,
            email=EMAIL,
        )
        assert restored.signing_secret == secret
        assert restored.public_id == pid
        assert restored.email == EMAIL

    def test_signing_secret_deterministic(self):
        """Same claims + salt always produce the same secret."""
        id1 = Identity.from_google_claims(CLAIMS, SALT)
        id2 = Identity.from_google_claims(CLAIMS, SALT)
        assert id1.signing_secret == id2.signing_secret

    def test_to_public_dict(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        public = identity.to_public_dict()
        assert "public_id" in public
        assert "email" in public
        assert "name" in public
        assert "signing_secret" not in public  # No secrets in public dict
        assert "google_id" not in public

    def test_to_dict_includes_secret(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        full = identity.to_dict()
        assert "signing_secret" in full
        assert len(full["signing_secret"]) == 64

    def test_repr(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        r = repr(identity)
        assert "Identity" in r
        assert EMAIL in r


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Job Signing & Verification
# ═══════════════════════════════════════════════════════════════════

class TestJobSigning:
    """Tests for signing and verifying job operations."""

    def test_sign_job_returns_hex(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        sig = identity.sign_job({"model_name": "gpt2", "rank": "16"})
        assert isinstance(sig, str)
        assert len(sig) == 64

    def test_sign_job_deterministic(self):
        """Same job fields always produce the same signature."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2", "rank": "16", "steps": "30"}
        sig1 = identity.sign_job(fields)
        sig2 = identity.sign_job(fields)
        assert sig1 == sig2

    def test_sign_job_order_independent(self):
        """Dict ordering doesn't affect signature."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        sig1 = identity.sign_job({"a": "1", "b": "2", "c": "3"})
        sig2 = identity.sign_job({"c": "3", "a": "1", "b": "2"})
        assert sig1 == sig2

    def test_verify_job_correct(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2", "rank": "16"}
        sig = identity.sign_job(fields)
        assert identity.verify_job(fields, sig) is True

    def test_verify_job_wrong_fields(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        sig = identity.sign_job({"model_name": "gpt2"})
        assert identity.verify_job({"model_name": "gpt3"}, sig) is False

    def test_verify_job_extra_field(self):
        """Adding a field invalidates the signature."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2"}
        sig = identity.sign_job(fields)
        assert identity.verify_job({"model_name": "gpt2", "extra": "x"}, sig) is False

    def test_verify_job_wrong_sig(self):
        identity = Identity.from_google_claims(CLAIMS, SALT)
        assert identity.verify_job({"a": "1"}, "dead" * 16) is False

    def test_different_users_different_sigs(self):
        """Two users signing the same job get different signatures."""
        claims_a = {**CLAIMS, "sub": "user-a"}
        claims_b = {**CLAIMS, "sub": "user-b"}
        id_a = Identity.from_google_claims(claims_a, SALT)
        id_b = Identity.from_google_claims(claims_b, SALT)

        fields = {"model_name": "gpt2", "rank": "16"}
        sig_a = id_a.sign_job(fields)
        sig_b = id_b.sign_job(fields)
        assert sig_a != sig_b

    def test_sign_without_secret_raises(self):
        identity = Identity(google_id=GOOGLE_ID, email=EMAIL)
        with pytest.raises(AuthError, match="signing secret"):
            identity.sign_job({"a": "1"})

    def test_verify_without_secret_returns_false(self):
        identity = Identity(google_id=GOOGLE_ID, email=EMAIL)
        assert identity.verify_job({"a": "1"}, "deadbeef" * 8) is False


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Server-Side Verification
# ═══════════════════════════════════════════════════════════════════

class TestServerVerification:
    """Tests for server-side signature verification."""

    def test_server_verify_correct(self):
        """Server can verify a signature using google_id + salt."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2", "rank": "16"}
        sig = identity.sign_job(fields)

        # Server re-derives the secret from google_id + salt
        assert server_verify_signature(GOOGLE_ID, SALT, fields, sig) is True

    def test_server_verify_wrong_google_id(self):
        """Wrong Google ID fails verification."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2"}
        sig = identity.sign_job(fields)

        assert server_verify_signature("wrong-id", SALT, fields, sig) is False

    def test_server_verify_wrong_salt(self):
        """Wrong salt fails verification."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2"}
        sig = identity.sign_job(fields)

        assert server_verify_signature(GOOGLE_ID, "wrong-salt", fields, sig) is False

    def test_server_verify_tampered_fields(self):
        """Tampered fields fail verification."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        sig = identity.sign_job({"model_name": "gpt2"})

        assert server_verify_signature(
            GOOGLE_ID, SALT, {"model_name": "evil-model"}, sig
        ) is False

    def test_server_derive_secret_matches_client(self):
        """Server derives the same secret as the client."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        server_secret = server_derive_secret(GOOGLE_ID, SALT)
        assert server_secret == identity.signing_secret


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Google ID Token Verification
# ═══════════════════════════════════════════════════════════════════

class TestGoogleTokenVerification:
    """Tests for Google ID token verification (mocked network)."""

    def _mock_tokeninfo(self, claims):
        """Helper: mock urlopen to return token claims."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(claims).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("identity.urlopen")
    def test_verify_valid_token(self, mock_urlopen):
        import time as _time
        valid_claims = {
            "sub": GOOGLE_ID,
            "email": EMAIL,
            "email_verified": "true",
            "name": NAME,
            "picture": PICTURE,
            "aud": CLIENT_ID,
            "exp": str(int(_time.time()) + 3600),
        }
        mock_urlopen.return_value = self._mock_tokeninfo(valid_claims)

        identity = verify_google_id_token("fake-token", CLIENT_ID, SALT)
        assert identity.google_id == GOOGLE_ID
        assert identity.email == EMAIL
        assert identity.signing_secret != ""

    @patch("identity.urlopen")
    def test_verify_wrong_audience(self, mock_urlopen):
        bad_claims = {**CLAIMS, "aud": "wrong-client-id"}
        mock_urlopen.return_value = self._mock_tokeninfo(bad_claims)

        with pytest.raises(AuthError, match="audience"):
            verify_google_id_token("fake-token", CLIENT_ID, SALT)

    @patch("identity.urlopen")
    def test_verify_expired_token(self, mock_urlopen):
        expired_claims = {**CLAIMS, "exp": "1000000000"}  # 2001, long expired
        mock_urlopen.return_value = self._mock_tokeninfo(expired_claims)

        with pytest.raises(AuthError, match="expired"):
            verify_google_id_token("fake-token", CLIENT_ID, SALT)

    @patch("identity.urlopen")
    def test_verify_unverified_email(self, mock_urlopen):
        unverified = {**CLAIMS, "email_verified": "false"}
        mock_urlopen.return_value = self._mock_tokeninfo(unverified)

        with pytest.raises(AuthError, match="not verified"):
            verify_google_id_token("fake-token", CLIENT_ID, SALT)

    @patch("identity.urlopen")
    def test_verify_network_error(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        with pytest.raises(AuthError, match="verification failed"):
            verify_google_id_token("fake-token", CLIENT_ID, SALT)


# ═══════════════════════════════════════════════════════════════════
# Unit Tests — Offline Verification
# ═══════════════════════════════════════════════════════════════════

class TestOfflineVerification:
    """Tests for lightweight offline identity verification."""

    def test_valid_format(self):
        secret = _derive_signing_secret(GOOGLE_ID, SALT)
        pid = _derive_public_id(GOOGLE_ID)
        assert verify_identity_offline(secret, pid, SALT) is True

    def test_bad_secret_length(self):
        assert verify_identity_offline("short", "u-abc123def456", SALT) is False

    def test_bad_secret_chars(self):
        bad = "g" * 64  # 'g' is not hex
        assert verify_identity_offline(bad, "u-abc123def456", SALT) is False

    def test_bad_public_id(self):
        secret = "a" * 64
        assert verify_identity_offline(secret, "", SALT) is False


# ═══════════════════════════════════════════════════════════════════
# Integration Tests — Cross-User Isolation
# ═══════════════════════════════════════════════════════════════════

class TestCrossUserIsolation:
    """Verify that one user can't forge signatures for another."""

    def test_alice_cannot_forge_bob(self):
        """Alice's secret cannot produce valid sigs for Bob's jobs."""
        alice = Identity.from_google_claims(
            {**CLAIMS, "sub": "alice-id", "email": "alice@example.com"},
            SALT,
        )
        bob = Identity.from_google_claims(
            {**CLAIMS, "sub": "bob-id", "email": "bob@example.com"},
            SALT,
        )

        fields = {"model_name": "shared-model", "rank": "16"}

        # Alice signs
        alice_sig = alice.sign_job(fields)

        # Bob verifies — should fail (different secret)
        assert bob.verify_job(fields, alice_sig) is False

        # Server verifies for Bob — should fail
        assert server_verify_signature("bob-id", SALT, fields, alice_sig) is False

        # Server verifies for Alice — should succeed
        assert server_verify_signature("alice-id", SALT, fields, alice_sig) is True

    def test_salt_compromise_isolation(self):
        """If an attacker knows the salt but not a user's Google ID,
        they can't derive the signing secret."""
        # Attacker knows the salt and tries random IDs
        real_identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "target-model"}
        real_sig = real_identity.sign_job(fields)

        # Attacker guesses wrong Google ID
        attacker_secret = _derive_signing_secret("wrong-guess-123", SALT)
        attacker = Identity.from_signing_secret(attacker_secret)
        assert attacker.verify_job(fields, real_sig) is False

    def test_re_authentication_gives_same_secret(self):
        """User can re-derive their secret by re-authenticating."""
        # First auth
        id1 = Identity.from_google_claims(CLAIMS, SALT)
        secret1 = id1.signing_secret

        # Second auth (same Google account)
        id2 = Identity.from_google_claims(CLAIMS, SALT)
        secret2 = id2.signing_secret

        assert secret1 == secret2

        # Signature from first session verifiable with second
        fields = {"model_name": "gpt2"}
        sig = id1.sign_job(fields)
        assert id2.verify_job(fields, sig) is True


# ═══════════════════════════════════════════════════════════════════
# Integration Tests — Identity + Job Fields
# ═══════════════════════════════════════════════════════════════════

class TestIdentityJobIntegration:
    """Tests for signing realistic job submissions."""

    def test_sign_full_job_fields(self):
        """Sign all the fields that would be in a real job submission."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {
            "model_name": "Qwen/Qwen3-0.6B",
            "rank": "16",
            "steps": "30",
            "lr": "0.001",
            "mode": "fcfs",
            "notes": "test run",
            "submitter": identity.public_id,
        }
        sig = identity.sign_job(fields)
        assert identity.verify_job(fields, sig) is True

        # Server can verify too
        assert server_verify_signature(GOOGLE_ID, SALT, fields, sig) is True

    def test_sign_empty_fields(self):
        """Signing empty fields works (edge case)."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        sig = identity.sign_job({})
        assert identity.verify_job({}, sig) is True

    def test_partial_field_tampering(self):
        """Changing even one field invalidates the signature."""
        identity = Identity.from_google_claims(CLAIMS, SALT)
        fields = {"model_name": "gpt2", "rank": "16", "steps": "30"}
        sig = identity.sign_job(fields)

        # Tamper with rank
        tampered = {**fields, "rank": "32"}
        assert identity.verify_job(tampered, sig) is False

        # Tamper with model
        tampered2 = {**fields, "model_name": "gpt3"}
        assert identity.verify_job(tampered2, sig) is False

    def test_saved_secret_roundtrip(self):
        """User saves secret to file, loads it later, can still sign."""
        # Create identity (first login)
        original = Identity.from_google_claims(CLAIMS, SALT)
        saved_data = original.to_dict()

        # Simulate saving to file and loading later
        loaded_secret = saved_data["signing_secret"]
        loaded_pid = saved_data["public_id"]
        loaded_email = saved_data["email"]

        # Reconstruct identity from saved data
        restored = Identity.from_signing_secret(
            signing_secret=loaded_secret,
            public_id=loaded_pid,
            email=loaded_email,
        )

        # Sign with restored identity
        fields = {"model_name": "gpt2", "rank": "16"}
        sig = restored.sign_job(fields)

        # Verify with server (which has google_id + salt)
        assert server_verify_signature(GOOGLE_ID, SALT, fields, sig) is True
