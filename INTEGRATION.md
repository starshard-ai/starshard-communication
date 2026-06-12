# Integration Guide (Agent-Optimized)

> Target audience: LLM agents and automated integrators.
> For human-readable overview, see [README.md](README.md).

## What This Repo Provides

- A **personal-agent communication substrate** protocol (not a hosted service).
- Core loop: `message -> identity -> trust tier -> policy -> receipt -> audit`.
- Two specs: SPEC-0001 (inbox/addressing/receipts), SPEC-0002 (false-negative monitoring).
- JSON Schema for all objects: [`schemas/spec0001.schema.json`](schemas/spec0001.schema.json).
- Reference implementations in Python (zero dependencies beyond stdlib).

## Object Model

| Object | Spec | Schema `$ref` path | Purpose |
|---|---|---|---|
| `EndpointAddress` | 0001 | `#/$defs/EndpointAddress` | Channel-qualified address (scheme + address) |
| `ContactIdentity` | 0001 | `#/$defs/ContactIdentity` | Known contact with endpoints and trust tier |
| `TrustTier` | 0001 | `#/$defs/TrustTier` | Enum: `direct`, `priority`, `standard`, `public`, `blocked` |
| `MessageEnvelope` | 0001 | `#/$defs/MessageEnvelope` | Inbound message wrapper (transport-neutral) |
| `AgentPolicy` | 0001 | `#/$defs/AgentPolicy` | Per-user routing rules mapping tiers to actions |
| `Receipt` | 0001 | `#/$defs/Receipt` | Lifecycle state of a routed message |
| `AuditEvent` | 0001 | `#/$defs/AuditEvent` | Auditable record of every routing decision |
| `DecisionTrace` | 0002 | `#/$defs/DecisionTrace` | Per-message routing decision with AI scores and flags |
| `FilteredDigest` | 0002 | `#/$defs/FilteredDigest` | Periodic summary of suppressed messages |
| `MonitoringConfig` | 0002 | `#/$defs/MonitoringConfig` | Shadow mode, uncertainty threshold, FN detection config |

## Key Enums

| Enum | Values |
|---|---|
| `TrustTier` | `direct`, `priority`, `standard`, `public`, `blocked` |
| `ReceiptState` | `received`, `routed`, `surfaced`, `digested`, `task_created`, `replied`, `delegated`, `blocked`, `handled`, `failed` |
| `DeclaredUrgency` | `low`, `normal`, `high`, `critical` |
| `AuditEventType` | `message_routed`, `receipt_written`, `false_negative_suspected`, `uncertainty_escalated`, `shadow_mode_comparison`, `filtered_digest_generated` |
| `TierSource` | `policy_lookup`, `ai_classification`, `uncertainty_escalation`, `manual_override` |
| `TierAction` | `deliver_now`, `classify`, `surface_soon`, `digest`, `route_public_agent`, `write_receipt`, `audit_only` |
| `FN Trigger` | `resend_detected`, `escalation_path_used`, `multi_channel_detected`, `third_party_relay` |
| `HumanVerdict` | `correct`, `should_have_surfaced`, `should_have_blocked`, `null` |

## How to Integrate

### 1. Produce a MessageEnvelope

Build a transport adapter (email, webhook, Matrix, etc.) that converts inbound messages to `MessageEnvelope` JSON conforming to `#/$defs/MessageEnvelope`.

Required fields: `message_id`, `created_at`, `from`, `to`, `channel`, `body`.

### 2. Define an AgentPolicy

Create a policy JSON conforming to `#/$defs/AgentPolicy`. Map known contacts to trust tiers. Define per-tier action lists. Optionally add `monitoring` config (SPEC-0002).

### 3. Route and Produce Receipts

Pass the envelope through your router. Output:
- One `Receipt` per message (lifecycle state).
- One `AuditEvent` per routing decision.
- One `DecisionTrace` per routing decision (if SPEC-0002 monitoring enabled).

### 4. Consume Receipts

Receipts are append-only JSONL. Query by `message_id`, `state`, or `metadata.trust_tier`.

### 5. Run False-Negative Monitoring (Optional, SPEC-0002)

- Generate `FilteredDigest` on schedule (default: 12h).
- Scan for FN signals: resend detection, escalation path, multi-channel, third-party relay.
- Flag `false_negative_suspect` on original `DecisionTrace`.

## Example Flows

### Flow 1: Basic Route (SPEC-0001)

**Input** (MessageEnvelope):
```json
{
  "message_id": "msg_20260513_0001",
  "created_at": "2026-05-13T00:00:00Z",
  "from": {"scheme": "email", "address": "person@example.com"},
  "to": {"scheme": "agent-endpoint", "address": "owner@example.net"},
  "channel": "email",
  "subject": "hello",
  "body": "Can you take a look at this?",
  "attachments": [],
  "declared_urgency": "normal",
  "metadata": {}
}
```

**Output** (Receipt):
```json
{
  "receipt_id": "rcpt_msg_20260513_0001",
  "message_id": "msg_20260513_0001",
  "created_at": "2026-05-13T00:00:05Z",
  "state": "surfaced",
  "state_detail": "priority_contact_surfaced_soon",
  "actor": "recipient_agent",
  "next_expected_event": null,
  "metadata": {"trust_tier": "priority"}
}
```

### Flow 2: Uncertainty Escalation (SPEC-0002)

**Input** (MessageEnvelope with low AI confidence):
```json
{
  "message_id": "msg_20260611_0002",
  "created_at": "2026-06-11T10:05:00Z",
  "from": {"scheme": "email", "address": "unknown@example.com"},
  "to": {"scheme": "agent-endpoint", "address": "owner@example.net"},
  "channel": "email",
  "subject": "meeting tomorrow",
  "body": "Are we still on for tomorrow?",
  "metadata": {"ai_score": 0.35, "ai_confidence": 0.4}
}
```

**Output** (DecisionTrace -- note escalation from `standard` to `priority`):
```json
{
  "trace_id": "dtrace_msg_20260611_0002",
  "message_id": "msg_20260611_0002",
  "created_at": "2026-06-11T10:05:01Z",
  "sender": "unknown@example.com",
  "subject": "meeting tomorrow",
  "ai_score": 0.35,
  "ai_confidence": 0.4,
  "tier_assigned": "priority",
  "tier_source": "uncertainty_escalation",
  "routing_outcome": "surfaced",
  "receipt_id": "rcpt_msg_20260611_0002",
  "shadow_mode": false,
  "shadow_outcome": null,
  "flags": ["uncertainty_escalated"]
}
```

### Flow 3: False-Negative Alert (SPEC-0002)

**Trigger**: Sender re-sends a similar message after original was digested.

**Output** (AuditEvent):
```json
{
  "audit_id": "audit_fn_msg_20260611_0003",
  "created_at": "2026-06-11T14:30:00Z",
  "event_type": "false_negative_suspected",
  "message_id": "msg_20260611_0003",
  "trigger": "resend_detected",
  "trigger_message_id": "msg_20260611_0009",
  "original_trace_id": "dtrace_msg_20260611_0003",
  "actor": "monitoring_system",
  "summary": "Sender colleague@example.com re-sent a similar message 4h after original was digested. Possible false negative."
}
```

## Reference Implementation CLI

```bash
# SPEC-0001: route a message
python3 reference-impl/router.py --message MSG.json --out /tmp/output

# SPEC-0002: route with decision trace
python3 reference-impl/monitor.py route --message MSG.json --out /tmp/output

# SPEC-0002: generate filtered digest
python3 reference-impl/monitor.py digest --out /tmp/output --period-start T0 --period-end T1

# SPEC-0002: scan for false negatives
python3 reference-impl/monitor.py scan-fn --out /tmp/output --messages /path/to/msgs/
```

## File Index

| Path | Contents |
|---|---|
| `schemas/spec0001.schema.json` | JSON Schema for all SPEC-0001 and SPEC-0002 objects |
| `docs/SPEC-0001-inbox-addressing-receipts.md` | Full SPEC-0001 text |
| `docs/SPEC-0002-false-negative-monitoring.md` | Full SPEC-0002 text |
| `reference-impl/router.py` | SPEC-0001 reference router (Python, no deps) |
| `reference-impl/monitor.py` | SPEC-0002 monitoring router (Python, no deps) |
| `examples/message-envelope.json` | Example MessageEnvelope |
| `examples/receipt.json` | Example Receipt |
| `examples/fn-monitoring-scenario/` | Runnable SPEC-0002 demo |

## Schema Validation

To validate an object against the schema:

```python
import json, jsonschema
schema = json.load(open("schemas/spec0001.schema.json"))
envelope = json.load(open("examples/message-envelope.json"))
jsonschema.validate(envelope, schema["$defs"]["MessageEnvelope"])
```

## Versioning

- SPEC-0001: draft (2026-05-13)
- SPEC-0002: draft (2026-06-11), depends on SPEC-0001
- Schema tracks both specs in a single file. `$defs` names are stable identifiers.
