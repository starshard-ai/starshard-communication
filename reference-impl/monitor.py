#!/usr/bin/env python3
"""False-negative monitoring reference implementation (SPEC-0002).

Implements all five pillars:
1. DecisionTrace logging
2. Shadow mode framework
3. FilteredDigest generation
4. Uncertainty escalation
5. False-negative alert detection

No model dependency. AI scores are passed in via message metadata or
set to null (pure policy-lookup mode). Similarity detection uses
basic string overlap — production systems should use embeddings.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Tier ordering (lower index = higher priority)
# ---------------------------------------------------------------------------

TIER_ORDER = ["direct", "priority", "standard", "public", "blocked"]


def tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return len(TIER_ORDER)


def escalate_one(tier: str) -> str:
    """Move one tier toward direct (more permissive)."""
    rank = tier_rank(tier)
    if rank <= 0:
        return tier
    return TIER_ORDER[rank - 1]


# ---------------------------------------------------------------------------
# Default policy with SPEC-0002 monitoring fields
# ---------------------------------------------------------------------------

DEFAULT_POLICY: dict[str, Any] = {
    "default_tier": "standard",
    "known_contacts": {
        "person@example.com": "priority",
    },
    "tier_states": {
        "direct":   ("surfaced", "direct_contact_surfaced_now"),
        "priority": ("surfaced", "priority_contact_surfaced_soon"),
        "standard": ("digested", "standard_contact_added_to_digest"),
        "public":   ("routed",   "public_contact_routed_to_public_agent"),
        "blocked":  ("blocked",  "blocked_contact_audit_only"),
    },
    "monitoring": {
        "shadow_mode": False,
        "uncertainty_threshold": 0.6,
        "digest_interval_hours": 12,
        "fn_lookback_hours": 48,
        "fn_similarity_threshold": 0.7,
    },
}

# Shadow fallback: when shadow_mode is on, use one tier more permissive
SHADOW_FALLBACK = {
    "blocked":  "standard",
    "standard": "priority",
    "priority": "direct",
    "direct":   "direct",
    "public":   "public",
}


# ---------------------------------------------------------------------------
# 1. Route with DecisionTrace
# ---------------------------------------------------------------------------

def route_with_trace(
    message: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Route a message and produce Receipt + AuditEvent + DecisionTrace.

    Returns (receipt, audit_event, decision_trace).
    """
    sender = message.get("from", {}).get("address", "")
    subject = message.get("subject", "")
    message_id = message["message_id"]
    message_created_at = message.get("created_at", utc_now())
    now = utc_now()

    monitoring = policy.get("monitoring", DEFAULT_POLICY["monitoring"])
    shadow_mode = monitoring.get("shadow_mode", False)
    uncertainty_threshold = monitoring.get("uncertainty_threshold", 0.6)

    # --- Determine tier ---
    ai_score = message.get("metadata", {}).get("ai_score")
    ai_confidence = message.get("metadata", {}).get("ai_confidence")
    threshold_applied = message.get("metadata", {}).get("threshold_applied")

    # Start with policy lookup
    tier = policy.get("known_contacts", {}).get(sender, policy["default_tier"])
    tier_source = "policy_lookup"
    flags: list[str] = []

    # If AI classification is present, use it (AI overrides policy for unknown contacts)
    if ai_score is not None and sender not in policy.get("known_contacts", {}):
        # Simple threshold-based tier assignment from AI score
        if ai_score >= 0.8:
            tier = "direct"
        elif ai_score >= 0.5:
            tier = "priority"
        elif ai_score >= 0.2:
            tier = "standard"
        else:
            tier = "blocked"
        tier_source = "ai_classification"

    # --- 4. Uncertainty escalation ---
    original_tier = tier
    if (
        ai_confidence is not None
        and ai_confidence < uncertainty_threshold
        and tier_source == "ai_classification"
    ):
        tier = escalate_one(tier)
        tier_source = "uncertainty_escalation"
        flags.append("uncertainty_escalated")

    # --- Determine outcome ---
    tier_states = policy.get("tier_states", DEFAULT_POLICY["tier_states"])
    state, state_detail = tier_states.get(tier, tier_states["standard"])

    # --- 2. Shadow mode ---
    shadow_outcome = None
    actual_tier = tier
    if shadow_mode and tier_source in ("ai_classification", "uncertainty_escalation"):
        # Record what AI wanted, but deliver via safe fallback
        shadow_outcome = state  # what AI would have done
        actual_tier = SHADOW_FALLBACK.get(tier, tier)
        state, state_detail = tier_states.get(actual_tier, tier_states["standard"])

    # --- Build receipt ---
    receipt_id = f"rcpt_{message_id}"
    receipt = {
        "receipt_id": receipt_id,
        "message_id": message_id,
        "created_at": now,
        "state": state,
        "state_detail": state_detail,
        "actor": "recipient_agent",
        "next_expected_event": None,
        "metadata": {
            "trust_tier": actual_tier if shadow_mode else tier,
            "decision_trace_id": f"dtrace_{message_id}",
        },
    }

    # --- Build audit event ---
    audit = {
        "audit_id": f"audit_{message_id}",
        "created_at": now,
        "event_type": "message_routed",
        "message_id": message_id,
        "receipt_id": receipt_id,
        "actor": "recipient_agent",
        "summary": f"Message from {sender or 'unknown'} routed as {actual_tier if shadow_mode else tier}.",
    }

    # --- 1. Build decision trace ---
    trace = {
        "trace_id": f"dtrace_{message_id}",
        "message_id": message_id,
        "created_at": now,
        "message_created_at": message_created_at,
        "sender": sender,
        "subject": subject,
        "ai_score": ai_score,
        "ai_confidence": ai_confidence,
        "threshold_applied": threshold_applied,
        "tier_assigned": tier,
        "tier_source": tier_source,
        "routing_outcome": state,
        "receipt_id": receipt_id,
        "shadow_mode": shadow_mode,
        "shadow_outcome": shadow_outcome,
        "flags": flags,
    }

    return receipt, audit, trace


# ---------------------------------------------------------------------------
# 3. FilteredDigest generation
# ---------------------------------------------------------------------------

def generate_filtered_digest(
    traces: list[dict[str, Any]],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    """Build a FilteredDigest from decision traces in a time window."""
    start_dt = parse_iso(period_start)
    end_dt = parse_iso(period_end)

    filtered_items = []
    total_passed = 0
    total_filtered = 0
    uncertainty_escalations = 0
    fn_suspects = 0

    for t in traces:
        t_dt = parse_iso(t["created_at"])
        if t_dt < start_dt or t_dt >= end_dt:
            continue

        outcome = t.get("routing_outcome", "")
        is_filtered = outcome in ("digested", "blocked")

        if is_filtered:
            total_filtered += 1
            filtered_items.append({
                "message_id": t["message_id"],
                "sender": t["sender"],
                "subject": t["subject"],
                "tier_assigned": t["tier_assigned"],
                "ai_score": t.get("ai_score"),
                "ai_confidence": t.get("ai_confidence"),
                "flags": t.get("flags", []),
                "human_verdict": None,
            })
        else:
            total_passed += 1

        if "uncertainty_escalated" in t.get("flags", []):
            uncertainty_escalations += 1
        if "false_negative_suspect" in t.get("flags", []):
            fn_suspects += 1

    digest_id = f"fdigest_{period_start.replace(':', '').replace('-', '').replace('T', '_')[:13]}"
    return {
        "digest_id": digest_id,
        "created_at": utc_now(),
        "period_start": period_start,
        "period_end": period_end,
        "items": filtered_items,
        "stats": {
            "total_filtered": total_filtered,
            "total_passed": total_passed,
            "uncertainty_escalations": uncertainty_escalations,
            "false_negative_suspects": fn_suspects,
        },
    }


# ---------------------------------------------------------------------------
# 5. False-negative detection
# ---------------------------------------------------------------------------

def text_similarity(a: str, b: str) -> float:
    """Normalized string similarity (SequenceMatcher). Production should use embeddings."""
    if not a or not b:
        return 0.0
    a_clean = re.sub(r"\s+", " ", a.lower().strip())
    b_clean = re.sub(r"\s+", " ", b.lower().strip())
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def detect_false_negatives(
    traces: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scan traces for false-negative signals. Returns new AuditEvents to write.

    Checks:
    - Resend: same sender, similar subject/body within lookback window.
    - Escalation path: same sender contacts via higher-trust channel.
    - Multi-channel: same sender uses different channel within lookback.
    - Third-party relay: direct-tier contact mentions filtered sender.

    Args:
        traces: all decision traces (will be mutated to add flags).
        messages: all message envelopes (for body/channel comparison).
        policy: agent policy (for lookback window, similarity threshold).
    """
    monitoring = policy.get("monitoring", DEFAULT_POLICY["monitoring"])
    lookback_hours = monitoring.get("fn_lookback_hours", 48)
    similarity_threshold = monitoring.get("fn_similarity_threshold", 0.7)

    # Index messages by id
    msg_by_id: dict[str, dict[str, Any]] = {m["message_id"]: m for m in messages}

    # Index traces by sender
    traces_by_sender: dict[str, list[dict[str, Any]]] = {}
    for t in traces:
        traces_by_sender.setdefault(t["sender"], []).append(t)

    # Find filtered traces
    filtered_traces = [
        t for t in traces
        if t.get("routing_outcome") in ("digested", "blocked")
        and "false_negative_suspect" not in t.get("flags", [])
    ]

    new_alerts: list[dict[str, Any]] = []

    for ft in filtered_traces:
        # Use message_created_at for temporal ordering (when msg was sent),
        # falling back to trace created_at (when routing happened)
        ft_dt = parse_iso(ft.get("message_created_at", ft["created_at"]))
        ft_msg = msg_by_id.get(ft["message_id"], {})
        ft_sender = ft["sender"]
        ft_subject = ft.get("subject", "")
        ft_body = ft_msg.get("body", "")
        ft_channel = ft_msg.get("channel", "")
        lookback_end = ft_dt + timedelta(hours=lookback_hours)

        # Check later messages from same sender
        for later_t in traces_by_sender.get(ft_sender, []):
            if later_t["message_id"] == ft["message_id"]:
                continue
            later_dt = parse_iso(later_t.get("message_created_at", later_t["created_at"]))
            if later_dt <= ft_dt or later_dt > lookback_end:
                continue

            later_msg = msg_by_id.get(later_t["message_id"], {})
            trigger = None

            # Check 1: Resend (similar subject or body)
            later_subject = later_t.get("subject", "")
            later_body = later_msg.get("body", "")
            subj_sim = text_similarity(ft_subject, later_subject)
            body_sim = text_similarity(ft_body, later_body)
            if subj_sim >= similarity_threshold or body_sim >= similarity_threshold:
                trigger = "resend_detected"

            # Check 2: Escalation path (later message got higher tier)
            if trigger is None:
                if tier_rank(later_t.get("tier_assigned", "standard")) < tier_rank(ft.get("tier_assigned", "standard")):
                    trigger = "escalation_path_used"

            # Check 3: Multi-channel
            if trigger is None:
                later_channel = later_msg.get("channel", "")
                if later_channel and ft_channel and later_channel != ft_channel:
                    trigger = "multi_channel_detected"

            if trigger:
                ft.setdefault("flags", []).append("false_negative_suspect")
                ft["flags"].append(trigger)
                alert = {
                    "audit_id": f"audit_fn_{ft['message_id']}",
                    "created_at": utc_now(),
                    "event_type": "false_negative_suspected",
                    "message_id": ft["message_id"],
                    "trigger": trigger,
                    "trigger_message_id": later_t["message_id"],
                    "original_trace_id": ft["trace_id"],
                    "actor": "monitoring_system",
                    "summary": (
                        f"Sender {ft_sender} triggered {trigger} "
                        f"{(later_dt - ft_dt).total_seconds() / 3600:.1f}h after "
                        f"original was {ft.get('routing_outcome', 'filtered')}. "
                        f"Possible false negative."
                    ),
                }
                new_alerts.append(alert)
                break  # one alert per filtered trace

        # Check 4: Third-party relay (direct-tier contact mentions filtered sender)
        if "false_negative_suspect" not in ft.get("flags", []):
            known_contacts = policy.get("known_contacts", {})
            direct_contacts = {addr for addr, tier in known_contacts.items() if tier == "direct"}
            for other_t in traces:
                if other_t["message_id"] == ft["message_id"]:
                    continue
                other_dt = parse_iso(other_t.get("message_created_at", other_t["created_at"]))
                if other_dt <= ft_dt or other_dt > lookback_end:
                    continue
                if other_t["sender"] not in direct_contacts:
                    continue
                other_msg = msg_by_id.get(other_t["message_id"], {})
                other_body = other_msg.get("body", "")
                # Check if the direct contact's message mentions the filtered sender
                if ft_sender and ft_sender.lower() in other_body.lower():
                    ft.setdefault("flags", []).append("false_negative_suspect")
                    ft["flags"].append("third_party_relay")
                    alert = {
                        "audit_id": f"audit_fn_{ft['message_id']}",
                        "created_at": utc_now(),
                        "event_type": "false_negative_suspected",
                        "message_id": ft["message_id"],
                        "trigger": "third_party_relay",
                        "trigger_message_id": other_t["message_id"],
                        "original_trace_id": ft["trace_id"],
                        "actor": "monitoring_system",
                        "summary": (
                            f"Direct contact {other_t['sender']} mentioned "
                            f"filtered sender {ft_sender}. Possible false negative."
                        ),
                    }
                    new_alerts.append(alert)
                    break

    return new_alerts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_route(args: argparse.Namespace) -> int:
    """Route a message with full decision trace."""
    message = load_json(args.message)
    policy = load_json(args.policy) if args.policy else DEFAULT_POLICY
    receipt, audit, trace = route_with_trace(message, policy)

    out = Path(args.out)
    append_jsonl(out / "receipts.jsonl", receipt)
    append_jsonl(out / "audit-events.jsonl", audit)
    append_jsonl(out / "decision-traces.jsonl", trace)

    print(json.dumps({"receipt": receipt, "audit": audit, "trace": trace}, ensure_ascii=False, indent=2))
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    """Generate a filtered-message digest for a time period."""
    out = Path(args.out)
    traces = load_jsonl(out / "decision-traces.jsonl")

    if args.period_start and args.period_end:
        period_start = args.period_start
        period_end = args.period_end
    else:
        # Default: last 12 hours
        now = datetime.now(timezone.utc).replace(microsecond=0)
        period_end = now.isoformat().replace("+00:00", "Z")
        period_start = (now - timedelta(hours=12)).isoformat().replace("+00:00", "Z")

    digest = generate_filtered_digest(traces, period_start, period_end)
    digest_path = out / "filtered-digests.jsonl"
    append_jsonl(digest_path, digest)
    print(json.dumps(digest, ensure_ascii=False, indent=2))
    return 0


def cmd_scan_fn(args: argparse.Namespace) -> int:
    """Scan for false-negative signals."""
    out = Path(args.out)
    policy = load_json(args.policy) if args.policy else DEFAULT_POLICY
    traces = load_jsonl(out / "decision-traces.jsonl")

    # Load all messages from a directory or messages.jsonl
    messages: list[dict[str, Any]] = []
    msg_dir = Path(args.messages) if args.messages else None
    if msg_dir and msg_dir.is_dir():
        for p in sorted(msg_dir.glob("*.json")):
            messages.append(load_json(p))
    elif msg_dir and msg_dir.exists():
        messages = load_jsonl(msg_dir)
    else:
        # Try to reconstruct minimal messages from traces
        for t in traces:
            messages.append({
                "message_id": t["message_id"],
                "created_at": t.get("message_created_at", t["created_at"]),
                "from": {"scheme": "email", "address": t["sender"]},
                "subject": t.get("subject", ""),
                "body": "",
                "channel": "email",
            })

    alerts = detect_false_negatives(traces, messages, policy)

    if alerts:
        for alert in alerts:
            append_jsonl(out / "audit-events.jsonl", alert)
        # Rewrite traces with updated flags
        trace_path = out / "decision-traces.jsonl"
        trace_path.unlink(missing_ok=True)
        for t in traces:
            append_jsonl(trace_path, t)

    print(json.dumps({"alerts": alerts, "count": len(alerts)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SPEC-0002 false-negative monitoring reference implementation."
    )
    sub = parser.add_subparsers(dest="command")

    # route
    p_route = sub.add_parser("route", help="Route a message with decision trace")
    p_route.add_argument("--message", required=True, type=Path)
    p_route.add_argument("--out", required=True, type=Path)
    p_route.add_argument("--policy", type=Path)

    # digest
    p_digest = sub.add_parser("digest", help="Generate filtered-message digest")
    p_digest.add_argument("--out", required=True, type=Path)
    p_digest.add_argument("--period-start", type=str)
    p_digest.add_argument("--period-end", type=str)

    # scan-fn
    p_fn = sub.add_parser("scan-fn", help="Scan for false-negative signals")
    p_fn.add_argument("--out", required=True, type=Path)
    p_fn.add_argument("--policy", type=Path)
    p_fn.add_argument("--messages", type=str, help="Directory of message JSONs or a messages.jsonl")

    args = parser.parse_args()

    if args.command == "route":
        return cmd_route(args)
    elif args.command == "digest":
        return cmd_digest(args)
    elif args.command == "scan-fn":
        return cmd_scan_fn(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
