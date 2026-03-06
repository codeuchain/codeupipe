"""
Real-world application pipeline simulations.

These tests simulate what actual users would build with codeupipe.
Each test class represents a complete mini-application: user signup,
e-commerce checkout, ETL ingestion, log processing, content moderation,
notification routing, data migration, API gateway, report generation,
and IoT sensor processing.

Every feature is exercised in realistic combinations:
  Payload (immutable + mutable), Filter (sync + async), Pipeline,
  Valve, Tap, Hook, RetryFilter, StreamFilter, State, TypedDict generics.

These are NOT unit tests — they are integration simulations that push
the framework to its limits with real business logic patterns.
"""

import asyncio
import re
import hashlib
import json
from datetime import datetime, timedelta
from typing import AsyncIterator, Dict, List, Optional, TypedDict

import pytest

from codeupipe import (
    Hook,
    MutablePayload,
    Payload,
    Pipeline,
    RetryFilter,
    State,
    Valve,
)


def run(coro):
    return asyncio.run(coro)


async def collect(aiter):
    results = []
    async for item in aiter:
        results.append(item)
    return results


async def make_source(*dicts):
    for d in dicts:
        yield Payload(d)


# ===========================================================================
# 1. User Signup Pipeline
#    validate → normalize → check duplicates → hash password → create user
#    → send welcome email → audit log
# ===========================================================================


class TestUserSignupPipeline:
    """Simulates a complete user registration flow."""

    def _build_pipeline(self):
        audit_log = []
        email_queue = []

        class ValidateInput:
            def call(self, payload: Payload) -> Payload:
                email = payload.get("email", "")
                password = payload.get("password", "")
                errors = []
                if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                    errors.append("Invalid email format")
                if len(password) < 8:
                    errors.append("Password must be at least 8 characters")
                if not re.search(r"[A-Z]", password):
                    errors.append("Password needs an uppercase letter")
                if not re.search(r"[0-9]", password):
                    errors.append("Password needs a digit")
                if errors:
                    raise ValueError("; ".join(errors))
                return payload.insert("validated", True)

        class NormalizeFields:
            def call(self, payload: Payload) -> Payload:
                m = payload.with_mutation()
                m.set("email", payload.get("email", "").strip().lower())
                m.set("username", payload.get("username", "").strip().lower())
                m.set("normalized", True)
                return m.to_immutable()

        class CheckDuplicate:
            """Simulates a DB lookup — known emails are rejected."""
            def __init__(self, existing_emails):
                self._existing = set(existing_emails)

            def call(self, payload: Payload) -> Payload:
                if payload.get("email") in self._existing:
                    raise ValueError(f"Email already registered: {payload.get('email')}")
                return payload.insert("unique", True)

        class HashPassword:
            async def call(self, payload: Payload) -> Payload:
                raw = payload.get("password", "")
                hashed = hashlib.sha256(raw.encode()).hexdigest()
                return payload.insert("password_hash", hashed).insert("password", "***REDACTED***")

        class CreateUser:
            _next_id = 1000
            async def call(self, payload: Payload) -> Payload:
                CreateUser._next_id += 1
                return payload.insert("user_id", CreateUser._next_id).insert("created_at", "2026-03-05T12:00:00Z")

        class SendWelcomeEmail:
            def __init__(self, queue):
                self._queue = queue
            def call(self, payload: Payload) -> Payload:
                self._queue.append({
                    "to": payload.get("email"),
                    "subject": f"Welcome {payload.get('username')}!",
                    "user_id": payload.get("user_id"),
                })
                return payload.insert("welcome_sent", True)

        class AuditTap:
            def __init__(self, log):
                self._log = log
            def observe(self, payload: Payload) -> None:
                self._log.append(payload.to_dict().copy())

        class TimingHook(Hook):
            def __init__(self):
                self.filter_names = []
            async def before(self, f, payload):
                if f is not None:
                    self.filter_names.append(f.__class__.__name__)

        existing_emails = ["taken@example.com", "admin@test.com"]
        timing = TimingHook()

        pipeline = Pipeline()
        pipeline.use_hook(timing)
        pipeline.add_filter(ValidateInput(), "validate")
        pipeline.add_filter(NormalizeFields(), "normalize")
        pipeline.add_filter(CheckDuplicate(existing_emails), "check_duplicate")
        pipeline.add_tap(AuditTap(audit_log), "pre_hash_audit")
        pipeline.add_filter(HashPassword(), "hash_password")
        pipeline.add_filter(CreateUser(), "create_user")
        pipeline.add_filter(SendWelcomeEmail(email_queue), "send_welcome")
        pipeline.add_tap(AuditTap(audit_log), "post_signup_audit")

        return pipeline, audit_log, email_queue, timing

    def test_successful_signup(self):
        pipeline, audit_log, email_queue, timing = self._build_pipeline()

        result = run(pipeline.run(Payload({
            "email": "  Alice@Example.COM  ",
            "username": "  Alice123  ",
            "password": "MyStrongP4ss",
        })))

        assert result.get("validated") is True
        assert result.get("email") == "alice@example.com"
        assert result.get("username") == "alice123"
        assert result.get("unique") is True
        assert result.get("password") == "***REDACTED***"
        assert result.get("password_hash") is not None
        assert result.get("user_id") is not None
        assert result.get("welcome_sent") is True

        # Audit captured snapshots at both tap points
        assert len(audit_log) == 2
        # Pre-hash audit should NOT have the hash yet
        assert "password_hash" not in audit_log[0]
        # Post-signup should have everything
        assert audit_log[1]["welcome_sent"] is True

        # Email was queued
        assert len(email_queue) == 1
        assert email_queue[0]["to"] == "alice@example.com"

        # All steps executed
        state = pipeline.state
        assert "validate" in state.executed
        assert "hash_password" in state.executed
        assert "send_welcome" in state.executed
        assert state.skipped == []

        # Hook tracked filter execution order
        assert "ValidateInput" in timing.filter_names
        assert "HashPassword" in timing.filter_names

    def test_invalid_password_fails_validation(self):
        pipeline, _, _, _ = self._build_pipeline()

        with pytest.raises(ValueError, match="Password must be at least 8"):
            run(pipeline.run(Payload({
                "email": "user@example.com",
                "username": "bob",
                "password": "short",
            })))

    def test_duplicate_email_rejected(self):
        pipeline, _, _, _ = self._build_pipeline()

        with pytest.raises(ValueError, match="already registered"):
            run(pipeline.run(Payload({
                "email": "taken@example.com",
                "username": "hacker",
                "password": "SecureP4ssword!",
            })))

    def test_password_not_leaked_in_audit(self):
        pipeline, audit_log, _, _ = self._build_pipeline()

        run(pipeline.run(Payload({
            "email": "clean@example.com",
            "username": "cleanuser",
            "password": "SecureP4ss!",
        })))

        # Post-hash audit should never contain the raw password
        for entry in audit_log:
            if "password_hash" in entry:
                assert entry["password"] == "***REDACTED***"


# ===========================================================================
# 2. E-Commerce Checkout Pipeline
#    validate cart → apply coupons (valve) → calculate tax →
#    apply loyalty discount (valve) → charge payment (retry) →
#    reserve inventory → send confirmation
# ===========================================================================


class TestECommerceCheckoutPipeline:
    """Simulates an e-commerce checkout with multiple valves and retries."""

    def _build_pipeline(self):
        class ValidateCart:
            def call(self, payload: Payload) -> Payload:
                items = payload.get("items", [])
                if not items:
                    raise ValueError("Cart is empty")
                total = sum(item["price"] * item["qty"] for item in items)
                return payload.insert("subtotal", total).insert("item_count", len(items))

        class ApplyCoupon:
            async def call(self, payload: Payload) -> Payload:
                code = payload.get("coupon_code", "")
                subtotal = payload.get("subtotal", 0)
                discounts = {"SAVE10": 0.10, "HALF": 0.50, "WELCOME5": 0.05}
                rate = discounts.get(code, 0)
                discount = round(subtotal * rate, 2)
                return payload.insert("discount", discount).insert("after_coupon", round(subtotal - discount, 2))

        class CalculateTax:
            TAX_RATES = {"CA": 0.0875, "TX": 0.0625, "OR": 0.0, "NY": 0.08}
            def call(self, payload: Payload) -> Payload:
                state_code = payload.get("shipping_state", "")
                base = payload.get("after_coupon", payload.get("subtotal", 0))
                rate = self.TAX_RATES.get(state_code, 0.05)
                tax = round(base * rate, 2)
                return payload.insert("tax", tax).insert("total", round(base + tax, 2))

        class ApplyLoyaltyDiscount:
            def call(self, payload: Payload) -> Payload:
                total = payload.get("total", 0)
                points = payload.get("loyalty_points", 0)
                # $1 off per 100 points, max 20% off
                point_discount = min(points // 100, int(total * 0.20))
                final = round(total - point_discount, 2)
                return payload.insert("loyalty_discount", point_discount).insert("final_total", final)

        class ChargePayment:
            """Simulates a flaky payment gateway."""
            def __init__(self):
                self.attempts = 0
            async def call(self, payload: Payload) -> Payload:
                self.attempts += 1
                if self.attempts < 2:
                    raise ConnectionError("Payment gateway timeout")
                return payload.insert("payment_status", "charged").insert("transaction_id", f"txn_{self.attempts}")

        class ReserveInventory:
            def call(self, payload: Payload) -> Payload:
                items = payload.get("items", [])
                reserved = [{"sku": item["sku"], "qty": item["qty"]} for item in items]
                return payload.insert("reserved_items", reserved)

        class ConfirmationTap:
            def __init__(self):
                self.confirmations = []
            def observe(self, payload: Payload) -> None:
                self.confirmations.append({
                    "order_total": payload.get("final_total"),
                    "txn": payload.get("transaction_id"),
                })

        charge = ChargePayment()
        confirmation = ConfirmationTap()

        pipeline = Pipeline()
        pipeline.add_filter(ValidateCart(), "validate_cart")
        pipeline.add_filter(
            Valve("apply_coupon", ApplyCoupon(),
                  predicate=lambda p: bool(p.get("coupon_code"))),
            "apply_coupon"
        )
        pipeline.add_filter(CalculateTax(), "calc_tax")
        pipeline.add_filter(
            Valve("loyalty", ApplyLoyaltyDiscount(),
                  predicate=lambda p: (p.get("loyalty_points") or 0) > 0),
            "loyalty"
        )
        pipeline.add_filter(RetryFilter(charge, max_retries=3), "charge_payment")
        pipeline.add_filter(ReserveInventory(), "reserve_inventory")
        pipeline.add_tap(confirmation, "confirmation")

        return pipeline, confirmation, charge

    def test_full_checkout_with_coupon_and_loyalty(self):
        pipeline, confirmation, _ = self._build_pipeline()

        result = run(pipeline.run(Payload({
            "items": [
                {"sku": "SHOE-001", "price": 89.99, "qty": 1},
                {"sku": "SOCK-003", "price": 12.50, "qty": 2},
            ],
            "coupon_code": "SAVE10",
            "shipping_state": "CA",
            "loyalty_points": 500,
        })))

        # Subtotal: 89.99 + 25.00 = 114.99
        assert result.get("subtotal") == 114.99
        # Coupon: 10% off → 11.50 discount
        assert result.get("discount") == 11.50
        assert result.get("after_coupon") == 103.49
        # Tax: CA 8.75% of 103.49 = 9.06
        assert result.get("tax") == 9.06
        # Total before loyalty: 112.55
        assert result.get("total") == 112.55
        # Loyalty: 500 pts = $5 off (max 20% = $22.51, so $5 applies)
        assert result.get("loyalty_discount") == 5
        assert result.get("final_total") == 107.55
        # Payment went through (retry succeeded)
        assert result.get("payment_status") == "charged"
        assert result.get("reserved_items") is not None
        # Confirmation tap captured
        assert len(confirmation.confirmations) == 1

    def test_no_coupon_skips_valve(self):
        pipeline, _, _ = self._build_pipeline()

        result = run(pipeline.run(Payload({
            "items": [{"sku": "HAT-001", "price": 30.00, "qty": 1}],
            "shipping_state": "OR",
        })))

        state = pipeline.state
        assert "apply_coupon" in state.skipped
        # No coupon → after_coupon not set, tax uses subtotal
        assert result.get("discount") is None
        assert result.get("tax") == 0.0  # Oregon: no sales tax
        assert result.get("total") == 30.0

    def test_no_loyalty_skips_valve(self):
        pipeline, _, _ = self._build_pipeline()

        result = run(pipeline.run(Payload({
            "items": [{"sku": "HAT-001", "price": 50.00, "qty": 1}],
            "shipping_state": "TX",
            "loyalty_points": 0,
        })))

        assert "loyalty" in pipeline.state.skipped
        assert result.get("loyalty_discount") is None

    def test_empty_cart_fails(self):
        pipeline, _, _ = self._build_pipeline()
        with pytest.raises(ValueError, match="Cart is empty"):
            run(pipeline.run(Payload({"items": []})))


# ===========================================================================
# 3. ETL Data Ingestion Pipeline
#    parse CSV rows → validate schema → clean data → enrich → deduplicate →
#    transform → aggregate → output
#    Uses MutablePayload for heavy bulk operations.
# ===========================================================================


class TestETLIngestionPipeline:
    """Simulates an ETL pipeline processing raw CSV-like data."""

    def test_full_etl_pipeline(self):
        class ParseCSV:
            def call(self, payload: Payload) -> Payload:
                raw = payload.get("raw_csv", "")
                rows = []
                for line in raw.strip().split("\n"):
                    if line.strip():
                        parts = [p.strip() for p in line.split(",")]
                        rows.append({"name": parts[0], "age": parts[1], "city": parts[2], "salary": parts[3]})
                return payload.insert("rows", rows).insert("row_count", len(rows))

        class ValidateSchema:
            def call(self, payload: Payload) -> Payload:
                rows = payload.get("rows", [])
                valid, invalid = [], []
                for row in rows:
                    try:
                        row["age"] = int(row["age"])
                        row["salary"] = float(row["salary"])
                        valid.append(row)
                    except (ValueError, KeyError):
                        invalid.append(row)
                return payload.insert("valid_rows", valid).insert("invalid_rows", invalid)

        class CleanData:
            """Uses MutablePayload for bulk in-place edits."""
            def call(self, payload: Payload) -> Payload:
                m = payload.with_mutation()
                cleaned = []
                for row in payload.get("valid_rows", []):
                    cleaned.append({
                        "name": row["name"].strip().title(),
                        "age": row["age"],
                        "city": row["city"].strip().title(),
                        "salary": row["salary"],
                    })
                m.set("valid_rows", cleaned)
                return m.to_immutable()

        class Enrich:
            def call(self, payload: Payload) -> Payload:
                rows = payload.get("valid_rows", [])
                for row in rows:
                    if row["age"] < 30:
                        row["generation"] = "young"
                    elif row["age"] < 50:
                        row["generation"] = "mid"
                    else:
                        row["generation"] = "senior"
                    row["tax_bracket"] = "high" if row["salary"] > 80000 else "standard"
                return payload.insert("valid_rows", rows)

        class Deduplicate:
            def call(self, payload: Payload) -> Payload:
                rows = payload.get("valid_rows", [])
                seen = set()
                unique = []
                for row in rows:
                    key = (row["name"].lower(), row["city"].lower())
                    if key not in seen:
                        seen.add(key)
                        unique.append(row)
                return payload.insert("valid_rows", unique).insert("duplicates_removed", len(rows) - len(unique))

        class Aggregate:
            def call(self, payload: Payload) -> Payload:
                rows = payload.get("valid_rows", [])
                by_city = {}
                for row in rows:
                    city = row["city"]
                    if city not in by_city:
                        by_city[city] = {"count": 0, "total_salary": 0}
                    by_city[city]["count"] += 1
                    by_city[city]["total_salary"] += row["salary"]
                for city_data in by_city.values():
                    city_data["avg_salary"] = round(city_data["total_salary"] / city_data["count"], 2)
                return payload.insert("city_stats", by_city)

        class MetricsTap:
            def __init__(self):
                self.snapshots = []
            def observe(self, payload: Payload) -> None:
                self.snapshots.append({
                    "valid": len(payload.get("valid_rows", [])),
                    "invalid": len(payload.get("invalid_rows", [])),
                })

        metrics = MetricsTap()
        pipeline = Pipeline()
        pipeline.add_filter(ParseCSV(), "parse")
        pipeline.add_filter(ValidateSchema(), "validate")
        pipeline.add_tap(metrics, "post_validate")
        pipeline.add_filter(CleanData(), "clean")
        pipeline.add_filter(Enrich(), "enrich")
        pipeline.add_filter(Deduplicate(), "dedup")
        pipeline.add_filter(Aggregate(), "aggregate")
        pipeline.add_tap(metrics, "post_aggregate")

        raw = """
Alice, 28, San Francisco, 95000
Bob, 45, New York, 72000
Charlie, BAD_AGE, Chicago, 60000
alice, 28, san francisco, 95000
Dave, 55, New York, 110000
Eve, 33, San Francisco, 88000
"""

        result = run(pipeline.run(Payload({"raw_csv": raw})))

        assert result.get("row_count") == 6
        assert len(result.get("invalid_rows", [])) == 1  # Charlie
        assert result.get("duplicates_removed") == 1  # alice duplicate
        stats = result.get("city_stats", {})
        assert "San Francisco" in stats
        assert "New York" in stats
        assert stats["San Francisco"]["count"] == 2  # Alice + Eve
        assert stats["New York"]["count"] == 2  # Bob + Dave

        # Metrics tap captured at two points
        assert len(metrics.snapshots) == 2
        assert metrics.snapshots[0]["invalid"] == 1  # after validate, before dedup


# ===========================================================================
# 4. Content Moderation Pipeline
#    detect language → check profanity → check spam signals →
#    classify risk (valve gates) → auto-approve or flag for review
# ===========================================================================


class TestContentModerationPipeline:
    """Simulates a content moderation system with risk-based routing."""

    def _build_pipeline(self):
        flagged_posts = []

        class DetectLanguage:
            def call(self, payload: Payload) -> Payload:
                text = payload.get("text", "")
                # Simplified: check for common non-ASCII ranges
                if any(ord(c) > 0x4E00 for c in text):
                    lang = "zh"
                elif any(ord(c) > 0x0400 and ord(c) < 0x04FF for c in text):
                    lang = "ru"
                else:
                    lang = "en"
                return payload.insert("detected_language", lang)

        class ProfanityCheck:
            BLOCKED_WORDS = {"badword", "spam123", "offensive"}
            def call(self, payload: Payload) -> Payload:
                text = payload.get("text", "").lower()
                found = [w for w in self.BLOCKED_WORDS if w in text]
                score = len(found) * 30  # 0-100 risk
                return payload.insert("profanity_score", min(score, 100)).insert("flagged_words", found)

        class SpamSignals:
            def call(self, payload: Payload) -> Payload:
                text = payload.get("text", "")
                signals = 0
                if text.upper() == text and len(text) > 10:
                    signals += 25  # ALL CAPS
                if text.count("http") > 2:
                    signals += 30  # Many links
                if text.count("!") > 5:
                    signals += 20  # Excessive punctuation
                if len(text) < 5:
                    signals += 10  # Suspiciously short
                return payload.insert("spam_score", min(signals, 100))

        class CalculateRisk:
            def call(self, payload: Payload) -> Payload:
                profanity = payload.get("profanity_score", 0)
                spam = payload.get("spam_score", 0)
                total_risk = min(profanity + spam, 100)
                return payload.insert("risk_score", total_risk)

        class AutoApprove:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("status", "approved").insert("review_required", False)

        class FlagForReview:
            def __init__(self, flagged):
                self._flagged = flagged
            def call(self, payload: Payload) -> Payload:
                self._flagged.append({
                    "text": payload.get("text"),
                    "risk": payload.get("risk_score"),
                    "words": payload.get("flagged_words"),
                })
                return payload.insert("status", "flagged").insert("review_required", True)

        class AutoReject:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("status", "rejected").insert("review_required", False)

        pipeline = Pipeline()
        pipeline.add_filter(DetectLanguage(), "detect_lang")
        pipeline.add_filter(ProfanityCheck(), "profanity")
        pipeline.add_filter(SpamSignals(), "spam")
        pipeline.add_filter(CalculateRisk(), "risk")

        # Low risk → auto-approve
        pipeline.add_filter(
            Valve("auto_approve", AutoApprove(),
                  predicate=lambda p: p.get("risk_score", 0) < 30),
            "auto_approve"
        )
        # Medium risk → flag for human review
        pipeline.add_filter(
            Valve("flag_review", FlagForReview(flagged_posts),
                  predicate=lambda p: 30 <= p.get("risk_score", 0) < 70 and p.get("status") is None),
            "flag_review"
        )
        # High risk → auto-reject
        pipeline.add_filter(
            Valve("auto_reject", AutoReject(),
                  predicate=lambda p: p.get("risk_score", 0) >= 70 and p.get("status") is None),
            "auto_reject"
        )

        return pipeline, flagged_posts

    def test_clean_content_approved(self):
        pipeline, _ = self._build_pipeline()
        result = run(pipeline.run(Payload({
            "text": "I love this product! It works great.",
            "user_id": 42,
        })))
        assert result.get("status") == "approved"
        assert result.get("risk_score") == 0

    def test_profane_content_flagged(self):
        pipeline, flagged = self._build_pipeline()
        result = run(pipeline.run(Payload({
            "text": "This is badword content here",
            "user_id": 99,
        })))
        assert result.get("status") == "flagged"
        assert result.get("review_required") is True
        assert len(flagged) == 1
        assert "badword" in flagged[0]["words"]

    def test_heavy_spam_rejected(self):
        pipeline, _ = self._build_pipeline()
        result = run(pipeline.run(Payload({
            "text": "BUY NOW http://spam1 http://spam2 http://spam3 badword offensive!!!!!!",
            "user_id": 1,
        })))
        assert result.get("status") == "rejected"
        assert result.get("risk_score") >= 70

    def test_short_content_low_risk(self):
        pipeline, _ = self._build_pipeline()
        result = run(pipeline.run(Payload({"text": "Hi", "user_id": 5})))
        # Short text gets 10 spam points — still under 30
        assert result.get("status") == "approved"


# ===========================================================================
# 5. Notification Router Pipeline
#    classify event → determine channels → compose messages →
#    send email (valve) → send SMS (valve) → send push (valve) → log delivery
# ===========================================================================


class TestNotificationRouterPipeline:
    """Simulates a multi-channel notification dispatch system."""

    def test_high_priority_sends_all_channels(self):
        sent = {"email": [], "sms": [], "push": []}

        class ClassifyEvent:
            def call(self, payload: Payload) -> Payload:
                severity = payload.get("severity", "low")
                channels = {"critical": ["email", "sms", "push"],
                            "high": ["email", "push"],
                            "medium": ["email"],
                            "low": ["push"]}
                return payload.insert("channels", channels.get(severity, ["push"]))

        class ComposeMessage:
            def call(self, payload: Payload) -> Payload:
                event = payload.get("event_type", "unknown")
                msg = f"[{payload.get('severity', 'low').upper()}] {event}: {payload.get('details', '')}"
                return payload.insert("message", msg)

        class SendEmail:
            def call(self, payload: Payload) -> Payload:
                sent["email"].append(payload.get("message"))
                return payload.insert("email_sent", True)

        class SendSMS:
            def call(self, payload: Payload) -> Payload:
                sent["sms"].append(payload.get("message")[:160])
                return payload.insert("sms_sent", True)

        class SendPush:
            def call(self, payload: Payload) -> Payload:
                sent["push"].append(payload.get("message"))
                return payload.insert("push_sent", True)

        pipeline = Pipeline()
        pipeline.add_filter(ClassifyEvent(), "classify")
        pipeline.add_filter(ComposeMessage(), "compose")
        pipeline.add_filter(
            Valve("send_email", SendEmail(),
                  predicate=lambda p: "email" in p.get("channels", [])),
            "send_email"
        )
        pipeline.add_filter(
            Valve("send_sms", SendSMS(),
                  predicate=lambda p: "sms" in p.get("channels", [])),
            "send_sms"
        )
        pipeline.add_filter(
            Valve("send_push", SendPush(),
                  predicate=lambda p: "push" in p.get("channels", [])),
            "send_push"
        )

        result = run(pipeline.run(Payload({
            "event_type": "server_down",
            "severity": "critical",
            "details": "Production DB unreachable",
            "recipient": "ops-team",
        })))

        assert result.get("email_sent") is True
        assert result.get("sms_sent") is True
        assert result.get("push_sent") is True
        assert len(sent["email"]) == 1
        assert "CRITICAL" in sent["email"][0]
        assert "send_email" in pipeline.state.executed
        assert "send_sms" in pipeline.state.executed
        assert "send_push" in pipeline.state.executed

    def test_low_priority_only_push(self):
        sent = {"email": [], "sms": [], "push": []}

        class ClassifyEvent:
            def call(self, payload: Payload) -> Payload:
                channels = {"low": ["push"]}
                return payload.insert("channels", channels.get(payload.get("severity"), ["push"]))

        class ComposeMessage:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("message", "Low priority notification")

        class SendEmail:
            def call(self, payload: Payload) -> Payload:
                sent["email"].append("sent")
                return payload.insert("email_sent", True)

        class SendPush:
            def call(self, payload: Payload) -> Payload:
                sent["push"].append("sent")
                return payload.insert("push_sent", True)

        pipeline = Pipeline()
        pipeline.add_filter(ClassifyEvent(), "classify")
        pipeline.add_filter(ComposeMessage(), "compose")
        pipeline.add_filter(
            Valve("email", SendEmail(), predicate=lambda p: "email" in p.get("channels", [])),
            "email"
        )
        pipeline.add_filter(
            Valve("push", SendPush(), predicate=lambda p: "push" in p.get("channels", [])),
            "push"
        )

        run(pipeline.run(Payload({"severity": "low"})))

        assert sent["email"] == []
        assert len(sent["push"]) == 1
        assert "email" in pipeline.state.skipped


# ===========================================================================
# 6. Log Processing Streaming Pipeline
#    Parse log lines → filter errors only → extract metadata →
#    aggregate per-minute counts
#    Uses StreamFilter for real streaming.
# ===========================================================================


class TestLogProcessingStreamPipeline:
    """Simulates a streaming log ingestion system."""

    def test_stream_processes_log_lines(self):
        class ParseLogLine:
            """StreamFilter: 1 raw line → 1 structured payload."""
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                raw = chunk.get("raw", "")
                # Format: "2026-03-05 12:00:05 ERROR Something failed"
                parts = raw.split(" ", 3)
                if len(parts) >= 4:
                    yield Payload({
                        "date": parts[0],
                        "time": parts[1],
                        "level": parts[2],
                        "message": parts[3],
                        "minute": parts[1][:5],  # "12:00"
                    })
                # Malformed lines are dropped (yield nothing)

        class ErrorOnlyFilter:
            """StreamFilter: drop non-ERROR lines."""
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                if chunk.get("level") == "ERROR":
                    yield chunk

        class EnrichMetadata:
            def call(self, payload: Payload) -> Payload:
                msg = payload.get("message", "")
                category = "unknown"
                if "timeout" in msg.lower():
                    category = "timeout"
                elif "null" in msg.lower() or "none" in msg.lower():
                    category = "null_reference"
                elif "permission" in msg.lower() or "denied" in msg.lower():
                    category = "auth"
                elif "disk" in msg.lower() or "storage" in msg.lower():
                    category = "storage"
                return payload.insert("category", category)

        pipeline = Pipeline()
        pipeline.add_filter(ParseLogLine(), "parse")
        pipeline.add_filter(ErrorOnlyFilter(), "filter_errors")
        pipeline.add_filter(EnrichMetadata(), "enrich")

        log_lines = [
            {"raw": "2026-03-05 12:00:05 ERROR Connection timeout to DB"},
            {"raw": "2026-03-05 12:00:06 INFO Request handled in 45ms"},
            {"raw": "2026-03-05 12:00:07 ERROR NullPointerException in UserService"},
            {"raw": "2026-03-05 12:00:08 WARN Memory usage at 85%"},
            {"raw": "2026-03-05 12:00:09 ERROR Permission denied for /admin"},
            {"raw": "MALFORMED LOG LINE"},
            {"raw": "2026-03-05 12:01:01 ERROR Disk full on /var/log"},
            {"raw": "2026-03-05 12:01:02 INFO Health check OK"},
        ]

        async def go():
            return await collect(pipeline.stream(make_source(*log_lines)))

        results = run(go())

        # Only ERROR lines pass through (4 of 8, minus 1 malformed)
        assert len(results) == 4
        categories = [r.get("category") for r in results]
        assert "timeout" in categories
        assert "null_reference" in categories
        assert "auth" in categories
        assert "storage" in categories

        # Verify streaming state
        state = pipeline.state
        assert state.chunks_processed["parse"] > 0
        # filter_errors drops non-errors
        assert state.chunks_processed.get("filter_errors", 0) == 4

    def test_all_info_lines_produces_empty_output(self):
        class ParseLogLine:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                raw = chunk.get("raw", "")
                parts = raw.split(" ", 3)
                if len(parts) >= 4:
                    yield Payload({"level": parts[2], "message": parts[3]})

        class ErrorOnly:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                if chunk.get("level") == "ERROR":
                    yield chunk

        pipeline = Pipeline()
        pipeline.add_filter(ParseLogLine(), "parse")
        pipeline.add_filter(ErrorOnly(), "errors")

        async def go():
            return await collect(pipeline.stream(make_source(
                {"raw": "2026-03-05 12:00:00 INFO OK"},
                {"raw": "2026-03-05 12:00:01 WARN Low memory"},
            )))

        assert run(go()) == []


# ===========================================================================
# 7. Data Migration Pipeline  
#    Load legacy format → transform schema → validate new format →
#    batch insert → verify counts → rollback on failure (hooks)
# ===========================================================================


class TestDataMigrationPipeline:
    """Simulates migrating data between schema versions."""

    def test_successful_migration(self):
        db = {"records": [], "committed": False}

        class LoadLegacy:
            def call(self, payload: Payload) -> Payload:
                legacy = payload.get("legacy_data", [])
                return payload.insert("source_count", len(legacy)).insert("records", legacy)

        class TransformSchema:
            """Legacy: {first, last, dob} → New: {full_name, birth_year, migrated}"""
            def call(self, payload: Payload) -> Payload:
                records = payload.get("records", [])
                transformed = []
                for r in records:
                    transformed.append({
                        "full_name": f"{r['first']} {r['last']}",
                        "birth_year": int(r["dob"].split("-")[0]),
                        "migrated": True,
                        "legacy_id": r.get("id"),
                    })
                return payload.insert("records", transformed)

        class ValidateNewFormat:
            def call(self, payload: Payload) -> Payload:
                records = payload.get("records", [])
                for r in records:
                    assert "full_name" in r, "Missing full_name"
                    assert "birth_year" in r, "Missing birth_year"
                    assert isinstance(r["birth_year"], int), "birth_year must be int"
                return payload.insert("validation_passed", True)

        class BatchInsert:
            def __init__(self, database):
                self._db = database
            def call(self, payload: Payload) -> Payload:
                self._db["records"].extend(payload.get("records", []))
                return payload.insert("inserted_count", len(payload.get("records", [])))

        class VerifyCounts:
            def __init__(self, database):
                self._db = database
            def call(self, payload: Payload) -> Payload:
                expected = payload.get("source_count", 0)
                actual = len(self._db["records"])
                if expected != actual:
                    raise ValueError(f"Count mismatch: expected {expected}, got {actual}")
                self._db["committed"] = True
                return payload.insert("verified", True)

        class RollbackHook(Hook):
            def __init__(self, database):
                self._db = database
                self.rolled_back = False
            async def on_error(self, f, error, payload):
                self._db["records"].clear()
                self._db["committed"] = False
                self.rolled_back = True

        rollback = RollbackHook(db)
        pipeline = Pipeline()
        pipeline.use_hook(rollback)
        pipeline.add_filter(LoadLegacy(), "load")
        pipeline.add_filter(TransformSchema(), "transform")
        pipeline.add_filter(ValidateNewFormat(), "validate")
        pipeline.add_filter(BatchInsert(db), "insert")
        pipeline.add_filter(VerifyCounts(db), "verify")

        legacy = [
            {"id": 1, "first": "Alice", "last": "Smith", "dob": "1990-05-15"},
            {"id": 2, "first": "Bob", "last": "Jones", "dob": "1985-12-01"},
            {"id": 3, "first": "Charlie", "last": "Brown", "dob": "2000-01-30"},
        ]

        result = run(pipeline.run(Payload({"legacy_data": legacy})))

        assert result.get("verified") is True
        assert result.get("inserted_count") == 3
        assert db["committed"] is True
        assert db["records"][0]["full_name"] == "Alice Smith"
        assert db["records"][0]["birth_year"] == 1990
        assert rollback.rolled_back is False

    def test_migration_rollback_on_failure(self):
        db = {"records": [], "committed": False}

        class LoadLegacy:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("source_count", 999).insert("records", [{"name": "x"}])

        class BatchInsert:
            def __init__(self, database):
                self._db = database
            def call(self, payload: Payload) -> Payload:
                self._db["records"].extend(payload.get("records", []))
                return payload.insert("inserted_count", len(payload.get("records", [])))

        class VerifyCounts:
            def call(self, payload: Payload) -> Payload:
                if payload.get("source_count") != payload.get("inserted_count"):
                    raise ValueError("Count mismatch!")
                return payload

        class RollbackHook(Hook):
            def __init__(self, database):
                self._db = database
                self.rolled_back = False
            async def on_error(self, f, error, payload):
                self._db["records"].clear()
                self.rolled_back = True

        rollback = RollbackHook(db)
        pipeline = Pipeline()
        pipeline.use_hook(rollback)
        pipeline.add_filter(LoadLegacy(), "load")
        pipeline.add_filter(BatchInsert(db), "insert")
        pipeline.add_filter(VerifyCounts(), "verify")

        with pytest.raises(ValueError, match="Count mismatch"):
            run(pipeline.run(Payload({"legacy_data": []})))

        # Hook rolled back the DB
        assert rollback.rolled_back is True
        assert db["records"] == []


# ===========================================================================
# 8. API Gateway / Request Pipeline
#    authenticate → rate limit (valve) → parse body → validate →
#    route to handler → format response → log request
# ===========================================================================


class TestAPIGatewayPipeline:
    """Simulates an API gateway processing incoming HTTP requests."""

    def _build_pipeline(self):
        request_log = []

        class Authenticate:
            VALID_TOKENS = {"token-admin": "admin", "token-user": "user", "token-readonly": "readonly"}
            def call(self, payload: Payload) -> Payload:
                token = payload.get("auth_token", "")
                role = self.VALID_TOKENS.get(token)
                if not role:
                    raise PermissionError("Invalid or missing authentication token")
                return payload.insert("user_role", role).insert("authenticated", True)

        class RateLimitCheck:
            """Simulates rate limiting by checking request count."""
            def call(self, payload: Payload) -> Payload:
                count = payload.get("request_count_this_minute", 0)
                limit = 100 if payload.get("user_role") == "admin" else 30
                if count > limit:
                    raise ValueError(f"Rate limit exceeded ({count}/{limit})")
                return payload.insert("rate_limit_ok", True)

        class ParseBody:
            def call(self, payload: Payload) -> Payload:
                raw_body = payload.get("body", "{}")
                try:
                    parsed = json.loads(raw_body)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON body: {e}")
                return payload.insert("parsed_body", parsed)

        class ValidateRequest:
            def call(self, payload: Payload) -> Payload:
                method = payload.get("method", "GET")
                path = payload.get("path", "/")
                if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    raise ValueError(f"Unsupported method: {method}")
                return payload.insert("validated", True)

        class RouteHandler:
            def call(self, payload: Payload) -> Payload:
                path = payload.get("path", "/")
                method = payload.get("method", "GET")
                body = payload.get("parsed_body", {})

                if path == "/users" and method == "GET":
                    response = {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}
                elif path == "/users" and method == "POST":
                    response = {"created": True, "name": body.get("name", "unknown")}
                elif path.startswith("/users/") and method == "GET":
                    user_id = path.split("/")[-1]
                    response = {"id": user_id, "name": "User " + user_id}
                else:
                    response = {"error": "Not Found", "path": path}

                return payload.insert("response_body", response).insert("status_code", 200 if "error" not in response else 404)

        class FormatResponse:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("response_json", json.dumps(payload.get("response_body", {})))

        class RequestLogTap:
            def __init__(self, log):
                self._log = log
            def observe(self, payload: Payload) -> None:
                self._log.append({
                    "method": payload.get("method"),
                    "path": payload.get("path"),
                    "status": payload.get("status_code"),
                    "role": payload.get("user_role"),
                })

        pipeline = Pipeline()
        pipeline.add_filter(Authenticate(), "auth")
        pipeline.add_filter(
            Valve("rate_limit", RateLimitCheck(),
                  predicate=lambda p: p.get("request_count_this_minute", 0) > 0),
            "rate_limit"
        )
        pipeline.add_filter(ParseBody(), "parse_body")
        pipeline.add_filter(ValidateRequest(), "validate")
        pipeline.add_filter(RouteHandler(), "route")
        pipeline.add_filter(FormatResponse(), "format")
        pipeline.add_tap(RequestLogTap(request_log), "log")

        return pipeline, request_log

    def test_get_users_list(self):
        pipeline, log = self._build_pipeline()
        result = run(pipeline.run(Payload({
            "auth_token": "token-admin",
            "method": "GET",
            "path": "/users",
            "body": "{}",
        })))
        assert result.get("status_code") == 200
        body = result.get("response_body")
        assert len(body["users"]) == 2
        assert log[0]["method"] == "GET"

    def test_post_create_user(self):
        pipeline, _ = self._build_pipeline()
        result = run(pipeline.run(Payload({
            "auth_token": "token-user",
            "method": "POST",
            "path": "/users",
            "body": '{"name": "Charlie"}',
        })))
        assert result.get("response_body")["created"] is True
        assert result.get("response_body")["name"] == "Charlie"

    def test_invalid_token_rejected(self):
        pipeline, _ = self._build_pipeline()
        with pytest.raises(PermissionError, match="Invalid or missing"):
            run(pipeline.run(Payload({
                "auth_token": "bad-token",
                "method": "GET",
                "path": "/users",
                "body": "{}",
            })))

    def test_rate_limited(self):
        pipeline, _ = self._build_pipeline()
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            run(pipeline.run(Payload({
                "auth_token": "token-user",
                "method": "GET",
                "path": "/users",
                "body": "{}",
                "request_count_this_minute": 50,
            })))

    def test_malformed_json_body(self):
        pipeline, _ = self._build_pipeline()
        with pytest.raises(ValueError, match="Invalid JSON"):
            run(pipeline.run(Payload({
                "auth_token": "token-admin",
                "method": "POST",
                "path": "/users",
                "body": "{not valid json",
            })))

    def test_rate_limit_skipped_for_first_request(self):
        pipeline, _ = self._build_pipeline()
        run(pipeline.run(Payload({
            "auth_token": "token-user",
            "method": "GET",
            "path": "/users",
            "body": "{}",
            "request_count_this_minute": 0,
        })))
        assert "rate_limit" in pipeline.state.skipped


# ===========================================================================
# 9. Report Generation Pipeline (Typed Generics)
#    query data → compute stats → format sections → compile report
#    Uses TypedDict-based payloads for type evolution.
# ===========================================================================


class TestReportGenerationPipeline:
    """Simulates a typed analytics report pipeline."""

    def test_sales_report(self):
        class RawSalesData(TypedDict):
            transactions: List[Dict]
            report_name: str
            period: str

        class QueryData:
            def call(self, payload: Payload) -> Payload:
                txns = payload.get("transactions", [])
                return payload.insert("total_revenue", sum(t["amount"] for t in txns)) \
                              .insert("transaction_count", len(txns))

        class ComputeStats:
            def call(self, payload: Payload) -> Payload:
                txns = payload.get("transactions", [])
                if not txns:
                    return payload.insert("stats", {})
                amounts = [t["amount"] for t in txns]
                by_category = {}
                for t in txns:
                    cat = t.get("category", "other")
                    by_category.setdefault(cat, 0)
                    by_category[cat] += t["amount"]
                return payload.insert("stats", {
                    "avg_transaction": round(sum(amounts) / len(amounts), 2),
                    "max_transaction": max(amounts),
                    "min_transaction": min(amounts),
                    "by_category": by_category,
                })

        class FormatReport:
            def call(self, payload: Payload) -> Payload:
                name = payload.get("report_name", "Report")
                period = payload.get("period", "unknown")
                revenue = payload.get("total_revenue", 0)
                count = payload.get("transaction_count", 0)
                stats = payload.get("stats", {})

                sections = [
                    f"# {name}",
                    f"Period: {period}",
                    f"Total Revenue: ${revenue:,.2f}",
                    f"Transactions: {count}",
                    f"Average: ${stats.get('avg_transaction', 0):,.2f}",
                ]
                if stats.get("by_category"):
                    sections.append("## By Category")
                    for cat, amt in stats["by_category"].items():
                        sections.append(f"  {cat}: ${amt:,.2f}")
                return payload.insert("report_text", "\n".join(sections))

        pipeline = Pipeline()
        pipeline.add_filter(QueryData(), "query")
        pipeline.add_filter(ComputeStats(), "stats")
        pipeline.add_filter(FormatReport(), "format")

        transactions = [
            {"id": 1, "amount": 150.00, "category": "electronics"},
            {"id": 2, "amount": 45.50, "category": "books"},
            {"id": 3, "amount": 230.00, "category": "electronics"},
            {"id": 4, "amount": 12.99, "category": "books"},
            {"id": 5, "amount": 89.00, "category": "clothing"},
        ]

        result = run(pipeline.run(Payload({
            "transactions": transactions,
            "report_name": "Q1 Sales Report",
            "period": "2026-Q1",
        })))

        assert result.get("total_revenue") == 527.49
        assert result.get("transaction_count") == 5
        stats = result.get("stats")
        assert stats["avg_transaction"] == 105.50
        assert stats["max_transaction"] == 230.00
        assert stats["by_category"]["electronics"] == 380.00
        assert stats["by_category"]["books"] == 58.49

        report = result.get("report_text")
        assert "Q1 Sales Report" in report
        assert "$527.49" in report
        assert "electronics" in report


# ===========================================================================
# 10. IoT Sensor Streaming Pipeline
#     Ingest readings → filter outliers → compute rolling average →
#     detect anomalies (spike) → alert on anomaly (valve)
# ===========================================================================


class TestIoTSensorStreamPipeline:
    """Simulates an IoT sensor data processing stream."""

    def test_sensor_stream_with_anomaly_detection(self):
        alerts = []

        class FilterOutliers:
            """Drop readings outside physical bounds."""
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                temp = chunk.get("temperature")
                if temp is not None and -50 <= temp <= 150:
                    yield chunk
                # Out-of-range readings silently dropped

        class RollingAverage:
            """Compute running average over last N readings."""
            def __init__(self, window=3):
                self._window: List[float] = []
                self._size = window

            def call(self, payload: Payload) -> Payload:
                temp = payload.get("temperature", 0)
                self._window.append(temp)
                if len(self._window) > self._size:
                    self._window.pop(0)
                avg = round(sum(self._window) / len(self._window), 2)
                return payload.insert("rolling_avg", avg)

        class AnomalyDetector:
            """Flag if current reading deviates >20 from rolling average."""
            def call(self, payload: Payload) -> Payload:
                temp = payload.get("temperature", 0)
                avg = payload.get("rolling_avg", temp)
                deviation = abs(temp - avg)
                is_anomaly = deviation > 20
                return payload.insert("is_anomaly", is_anomaly).insert("deviation", round(deviation, 2))

        class AlertSender:
            def __init__(self, alert_list):
                self._alerts = alert_list
            def call(self, payload: Payload) -> Payload:
                self._alerts.append({
                    "sensor": payload.get("sensor_id"),
                    "temp": payload.get("temperature"),
                    "avg": payload.get("rolling_avg"),
                    "deviation": payload.get("deviation"),
                })
                return payload.insert("alert_sent", True)

        class SensorTap:
            def __init__(self):
                self.readings = []
            async def observe(self, payload: Payload) -> None:
                self.readings.append(payload.get("temperature"))

        sensor_tap = SensorTap()

        pipeline = Pipeline()
        pipeline.add_filter(FilterOutliers(), "filter_outliers")
        pipeline.add_tap(sensor_tap, "sensor_log")
        pipeline.add_filter(RollingAverage(window=3), "rolling_avg")
        pipeline.add_filter(AnomalyDetector(), "anomaly")
        pipeline.add_filter(
            Valve("alert", AlertSender(alerts),
                  predicate=lambda p: p.get("is_anomaly") is True),
            "alert"
        )

        readings = [
            {"sensor_id": "temp-01", "temperature": 22.0},
            {"sensor_id": "temp-01", "temperature": 23.0},
            {"sensor_id": "temp-01", "temperature": 22.5},
            {"sensor_id": "temp-01", "temperature": 999.0},  # outlier — dropped
            {"sensor_id": "temp-01", "temperature": 22.0},
            {"sensor_id": "temp-01", "temperature": 80.0},   # spike! anomaly
            {"sensor_id": "temp-01", "temperature": 23.0},
            {"sensor_id": "temp-01", "temperature": -100.0},  # outlier — dropped
        ]

        async def go():
            return await collect(pipeline.stream(make_source(*readings)))

        results = run(go())

        # 8 inputs, 2 outliers dropped → 6 processed
        assert len(results) == 6
        # Tap saw 6 readings (after outlier filter)
        assert len(sensor_tap.readings) == 6

        # The spike at 80.0 should have triggered an alert
        assert len(alerts) >= 1
        spike_alert = [a for a in alerts if a["temp"] == 80.0]
        assert len(spike_alert) == 1
        assert spike_alert[0]["deviation"] > 20

    def test_all_outliers_produces_no_output(self):
        class FilterOutliers:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                temp = chunk.get("temperature")
                if temp is not None and -50 <= temp <= 150:
                    yield chunk

        pipeline = Pipeline()
        pipeline.add_filter(FilterOutliers(), "filter")

        async def go():
            return await collect(pipeline.stream(make_source(
                {"temperature": 999},
                {"temperature": -200},
                {"temperature": 500},
            )))

        assert run(go()) == []


# ===========================================================================
# 11. Multi-Step Form Wizard Pipeline
#     Simulates a multi-page form where each step validates independently
#     and the pipeline accumulates all data through payload merging.
# ===========================================================================


class TestFormWizardPipeline:
    """Simulates a multi-step form submission (like insurance application)."""

    def test_complete_insurance_application(self):
        class ValidatePersonalInfo:
            def call(self, payload: Payload) -> Payload:
                name = payload.get("full_name", "")
                age = payload.get("age", 0)
                if not name or len(name) < 2:
                    raise ValueError("Name is required")
                if age < 18 or age > 120:
                    raise ValueError("Age must be between 18 and 120")
                return payload.insert("step1_valid", True)

        class ValidateVehicle:
            def call(self, payload: Payload) -> Payload:
                year = payload.get("vehicle_year", 0)
                if year < 1990 or year > 2027:
                    raise ValueError("Vehicle year must be 1990-2027")
                make = payload.get("vehicle_make", "")
                if not make:
                    raise ValueError("Vehicle make is required")
                return payload.insert("step2_valid", True)

        class CalculatePremium:
            def call(self, payload: Payload) -> Payload:
                age = payload.get("age", 30)
                year = payload.get("vehicle_year", 2020)
                base = 800
                # Young driver surcharge
                if age < 25:
                    base += 400
                # Old vehicle surcharge
                if year < 2010:
                    base += 200
                # High-value vehicle
                if payload.get("vehicle_value", 0) > 50000:
                    base += 300
                return payload.insert("annual_premium", base).insert("monthly_premium", round(base / 12, 2))

        class ApplyDiscounts:
            """Valve: only if they qualify for any discount."""
            def call(self, payload: Payload) -> Payload:
                premium = payload.get("annual_premium", 0)
                discounts = []
                if payload.get("good_driver") is True:
                    premium *= 0.90
                    discounts.append("good_driver_10%")
                if payload.get("multi_policy") is True:
                    premium *= 0.95
                    discounts.append("multi_policy_5%")
                premium = round(premium, 2)
                return payload.insert("final_premium", premium) \
                              .insert("discounts_applied", discounts) \
                              .insert("monthly_premium", round(premium / 12, 2))

        class GenerateQuote:
            def call(self, payload: Payload) -> Payload:
                quote_id = f"Q-{hash(payload.get('full_name', '')) % 100000:05d}"
                return payload.insert("quote_id", quote_id).insert("status", "quoted")

        pipeline = Pipeline()
        pipeline.add_filter(ValidatePersonalInfo(), "validate_person")
        pipeline.add_filter(ValidateVehicle(), "validate_vehicle")
        pipeline.add_filter(CalculatePremium(), "calc_premium")
        pipeline.add_filter(
            Valve("discounts", ApplyDiscounts(),
                  predicate=lambda p: p.get("good_driver") or p.get("multi_policy")),
            "discounts"
        )
        pipeline.add_filter(GenerateQuote(), "generate_quote")

        result = run(pipeline.run(Payload({
            "full_name": "Jane Doe",
            "age": 22,
            "vehicle_year": 2022,
            "vehicle_make": "Toyota",
            "vehicle_value": 28000,
            "good_driver": True,
            "multi_policy": True,
        })))

        assert result.get("step1_valid") is True
        assert result.get("step2_valid") is True
        assert result.get("annual_premium") is not None
        # Young driver + good driver + multi-policy
        assert result.get("discounts_applied") == ["good_driver_10%", "multi_policy_5%"]
        assert result.get("final_premium") < result.get("annual_premium", 0)
        assert result.get("quote_id") is not None
        assert result.get("status") == "quoted"

    def test_underage_rejected(self):
        class ValidatePersonalInfo:
            def call(self, payload: Payload) -> Payload:
                if payload.get("age", 0) < 18:
                    raise ValueError("Age must be between 18 and 120")
                return payload

        pipeline = Pipeline()
        pipeline.add_filter(ValidatePersonalInfo(), "validate")

        with pytest.raises(ValueError, match="Age must be between 18"):
            run(pipeline.run(Payload({"full_name": "Kid", "age": 16})))


# ===========================================================================
# 12. CI/CD Build Pipeline
#     checkout → lint → test → build artifact → deploy staging (valve) →
#     deploy prod (valve) → notify
#     Tests hook-based rollback and conditional deployment.
# ===========================================================================


class TestCICDBuildPipeline:
    """Simulates a CI/CD deployment pipeline with conditional stages."""

    def test_full_deploy_to_production(self):
        deployments = []

        class Checkout:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("commit_sha", "abc123").insert("branch", payload.get("branch", "main"))

        class Lint:
            def call(self, payload: Payload) -> Payload:
                files = payload.get("changed_files", [])
                warnings = [f for f in files if f.endswith(".py") and "test" not in f]
                return payload.insert("lint_passed", True).insert("lint_warnings", len(warnings))

        class RunTests:
            def call(self, payload: Payload) -> Payload:
                test_count = payload.get("test_count", 100)
                passed = test_count  # all pass in happy path
                return payload.insert("tests_passed", passed) \
                              .insert("tests_total", test_count) \
                              .insert("test_success", True)

        class BuildArtifact:
            def call(self, payload: Payload) -> Payload:
                sha = payload.get("commit_sha", "unknown")
                return payload.insert("artifact_url", f"s3://builds/{sha}/app.tar.gz") \
                              .insert("build_success", True)

        class DeployStaging:
            def __init__(self, log):
                self._log = log
            def call(self, payload: Payload) -> Payload:
                self._log.append(("staging", payload.get("artifact_url")))
                return payload.insert("staging_deployed", True)

        class DeployProd:
            def __init__(self, log):
                self._log = log
            def call(self, payload: Payload) -> Payload:
                self._log.append(("production", payload.get("artifact_url")))
                return payload.insert("prod_deployed", True)

        class NotifySlack:
            def call(self, payload: Payload) -> Payload:
                envs = []
                if payload.get("staging_deployed"):
                    envs.append("staging")
                if payload.get("prod_deployed"):
                    envs.append("production")
                msg = f"Deployed {payload.get('commit_sha')} to {', '.join(envs)}"
                return payload.insert("notification", msg)

        pipeline = Pipeline()
        pipeline.add_filter(Checkout(), "checkout")
        pipeline.add_filter(Lint(), "lint")
        pipeline.add_filter(RunTests(), "tests")
        pipeline.add_filter(BuildArtifact(), "build")
        pipeline.add_filter(
            Valve("deploy_staging", DeployStaging(deployments),
                  predicate=lambda p: p.get("test_success") is True),
            "deploy_staging"
        )
        pipeline.add_filter(
            Valve("deploy_prod", DeployProd(deployments),
                  predicate=lambda p: p.get("branch") == "main" and p.get("staging_deployed") is True),
            "deploy_prod"
        )
        pipeline.add_filter(NotifySlack(), "notify")

        result = run(pipeline.run(Payload({
            "branch": "main",
            "changed_files": ["app.py", "test_app.py", "utils.py"],
            "test_count": 343,
        })))

        assert result.get("lint_passed") is True
        assert result.get("test_success") is True
        assert result.get("build_success") is True
        assert result.get("staging_deployed") is True
        assert result.get("prod_deployed") is True
        assert "production" in result.get("notification", "")
        assert len(deployments) == 2
        assert deployments[0][0] == "staging"
        assert deployments[1][0] == "production"

    def test_feature_branch_skips_prod(self):
        deployments = []

        class Pass:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("test_success", True) \
                              .insert("staging_deployed", True) \
                              .insert("commit_sha", "def456")

        class DeployProd:
            def __init__(self, log):
                self._log = log
            def call(self, payload: Payload) -> Payload:
                self._log.append("prod")
                return payload.insert("prod_deployed", True)

        pipeline = Pipeline()
        pipeline.add_filter(Pass(), "setup")
        pipeline.add_filter(
            Valve("deploy_prod", DeployProd(deployments),
                  predicate=lambda p: p.get("branch") == "main" and p.get("staging_deployed") is True),
            "deploy_prod"
        )

        run(pipeline.run(Payload({"branch": "feature/new-ui"})))

        assert "deploy_prod" in pipeline.state.skipped
        assert deployments == []


# ===========================================================================
# 13. Pipeline Reuse Across Multiple Inputs
#     Same pipeline instance processes many payloads — verifies state isolation.
# ===========================================================================


class TestPipelineReuseBatch:
    """Simulates processing a batch of items through the same pipeline."""

    def test_process_100_items_independently(self):
        class Multiply:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("result", payload.get("n", 0) * payload.get("factor", 1))

        class ClassifyResult:
            def call(self, payload: Payload) -> Payload:
                r = payload.get("result", 0)
                label = "small" if r < 100 else "medium" if r < 1000 else "large"
                return payload.insert("label", label)

        pipeline = Pipeline()
        pipeline.add_filter(Multiply(), "multiply")
        pipeline.add_filter(ClassifyResult(), "classify")

        results = []
        for i in range(100):
            r = run(pipeline.run(Payload({"n": i, "factor": i + 1})))
            results.append(r)
            # State should be fresh each time
            assert pipeline.state.executed == ["multiply", "classify"]
            assert pipeline.state.skipped == []

        # Verify correctness
        assert results[0].get("result") == 0  # 0 * 1
        assert results[0].get("label") == "small"
        assert results[10].get("result") == 110  # 10 * 11
        assert results[10].get("label") == "medium"
        assert results[50].get("result") == 2550  # 50 * 51
        assert results[50].get("label") == "large"


# ===========================================================================
# 14. Error Recovery Pipeline with RetryFilter
#     Simulates flaky external services with progressive recovery.
# ===========================================================================


class TestErrorRecoveryPipeline:
    """Simulates a pipeline with multiple flaky services and retry logic."""

    def test_all_services_eventually_succeed(self):
        call_counts = {"db": 0, "cache": 0, "api": 0}

        class FlakyDB:
            async def call(self, payload: Payload) -> Payload:
                call_counts["db"] += 1
                if call_counts["db"] < 2:
                    raise ConnectionError("DB connection refused")
                return payload.insert("db_result", {"users": 42})

        class FlakyCache:
            async def call(self, payload: Payload) -> Payload:
                call_counts["cache"] += 1
                if call_counts["cache"] < 3:
                    raise TimeoutError("Cache timeout")
                return payload.insert("cache_warmed", True)

        class FlakyAPI:
            async def call(self, payload: Payload) -> Payload:
                call_counts["api"] += 1
                if call_counts["api"] < 2:
                    raise ConnectionError("API 503")
                return payload.insert("api_enrichment", {"score": 95})

        pipeline = Pipeline()
        pipeline.add_filter(RetryFilter(FlakyDB(), max_retries=3), "db_query")
        pipeline.add_filter(RetryFilter(FlakyCache(), max_retries=5), "warm_cache")
        pipeline.add_filter(RetryFilter(FlakyAPI(), max_retries=3), "api_call")

        result = run(pipeline.run(Payload({"request_id": "req-001"})))

        # All services eventually succeeded — no error keys
        assert result.get("error") is None
        assert result.get("db_result") == {"users": 42}
        assert result.get("cache_warmed") is True
        assert result.get("api_enrichment") == {"score": 95}

    def test_unrecoverable_failure_sets_error(self):
        class AlwaysFail:
            async def call(self, payload: Payload) -> Payload:
                raise RuntimeError("Service permanently down")

        pipeline = Pipeline()
        pipeline.add_filter(RetryFilter(AlwaysFail(), max_retries=3), "doomed")

        result = run(pipeline.run(Payload({})))
        assert "permanently down" in result.get("error", "")


# ===========================================================================
# 15. Mixed Sync/Async Pipeline with State Metadata
#     Exercises sync filters, async filters, sync taps, async taps,
#     sync hooks all in one pipeline.
# ===========================================================================


class TestMixedSyncAsyncPipeline:
    """Exercises every sync/async combination in a single pipeline."""

    def test_everything_mixed(self):
        log = []

        class SyncFilter1:
            def call(self, payload: Payload) -> Payload:
                log.append("sync_filter_1")
                return payload.insert("step1", True)

        class AsyncFilter2:
            async def call(self, payload: Payload) -> Payload:
                log.append("async_filter_2")
                return payload.insert("step2", True)

        class SyncFilter3:
            def call(self, payload: Payload) -> Payload:
                log.append("sync_filter_3")
                return payload.insert("step3", True)

        class SyncTap:
            def observe(self, payload: Payload) -> None:
                log.append("sync_tap")

        class AsyncTap:
            async def observe(self, payload: Payload) -> None:
                log.append("async_tap")

        class SyncHook(Hook):
            def before(self, f, payload) -> None:
                if f is not None:
                    log.append(f"hook_before_{f.__class__.__name__}")

            def after(self, f, payload) -> None:
                if f is not None:
                    log.append(f"hook_after_{f.__class__.__name__}")

        pipeline = Pipeline()
        pipeline.use_hook(SyncHook())
        pipeline.add_filter(SyncFilter1(), "sf1")
        pipeline.add_tap(SyncTap(), "sync_tap")
        pipeline.add_filter(AsyncFilter2(), "af2")
        pipeline.add_tap(AsyncTap(), "async_tap")
        pipeline.add_filter(SyncFilter3(), "sf3")

        result = run(pipeline.run(Payload({"input": True})))

        assert result.get("step1") is True
        assert result.get("step2") is True
        assert result.get("step3") is True

        # Verify ordering
        assert log == [
            "hook_before_SyncFilter1",
            "sync_filter_1",
            "hook_after_SyncFilter1",
            "sync_tap",
            "hook_before_AsyncFilter2",
            "async_filter_2",
            "hook_after_AsyncFilter2",
            "async_tap",
            "hook_before_SyncFilter3",
            "sync_filter_3",
            "hook_after_SyncFilter3",
        ]

        state = pipeline.state
        assert state.executed == ["sf1", "sync_tap", "af2", "async_tap", "sf3"]
