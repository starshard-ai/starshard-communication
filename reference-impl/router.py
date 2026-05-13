#!/usr/bin/env python3
"""Tiny inbox/addressing/receipt reference implementation.

This demo intentionally has no model dependency and no private system
dependency. It receives one MessageEnvelope JSON file, applies a static local
policy, and writes receipt/audit JSONL files.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_POLICY = {
    "default_tier": "standard",
    "known_contacts": {
        "person@example.com": "priority",
    },
    "tier_states": {
        "direct": ("surfaced", "direct_contact_surfaced_now"),
        "priority": ("surfaced", "priority_contact_surfaced_soon"),
        "standard": ("digested", "standard_contact_added_to_digest"),
        "public": ("routed", "public_contact_routed_to_public_agent"),
        "blocked": ("blocked", "blocked_contact_audit_only"),
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def route(message: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sender = message.get("from", {}).get("address", "")
    tier = policy["known_contacts"].get(sender, policy["default_tier"])
    state, state_detail = policy["tier_states"].get(tier, policy["tier_states"]["standard"])
    now = utc_now()
    message_id = message["message_id"]
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
            "trust_tier": tier,
        },
    }
    audit = {
        "audit_id": f"audit_{message_id}",
        "created_at": now,
        "event_type": "message_routed",
        "message_id": message_id,
        "receipt_id": receipt_id,
        "actor": "recipient_agent",
        "summary": f"Message from {sender or 'unknown sender'} routed as {tier}.",
    }
    return receipt, audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()

    message = load_json(args.message)
    policy = load_json(args.policy) if args.policy else DEFAULT_POLICY
    receipt, audit = route(message, policy)

    append_jsonl(args.out / "receipts.jsonl", receipt)
    append_jsonl(args.out / "audit-events.jsonl", audit)

    print(json.dumps({"receipt": receipt, "audit": audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
