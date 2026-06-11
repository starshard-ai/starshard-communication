# SPEC-0002: False-Negative Monitoring

Status: draft
Date: 2026-06-11
Depends-on: SPEC-0001

This spec adds the "learn from failures" pillar to the communication substrate.
When an AI agent filters or deprioritizes messages on behalf of a user, some of
those decisions will be wrong. This spec defines structured mechanisms to detect,
surface, and learn from those mistakes.

## Motivation

A selective-attention router that filters messages has an asymmetric failure
mode: false negatives (important messages filtered out) are invisible by default.
The sender gets silence; the recipient never sees what was suppressed. Unlike
spam filters where false positives (good mail in spam) are at least discoverable
in a spam folder, a trust-tier router that quietly digests or drops a message
leaves no natural feedback loop.

This spec defines five mechanisms to close that gap:

1. **Decision Trace** — structured per-message routing record.
2. **Shadow Mode** — log-only mode for comparing AI judgment to human ground truth.
3. **Filtered-Message Digest** — periodic human-readable summary of suppressed messages.
4. **Uncertainty Escalation** — default-to-pass when AI confidence is low.
5. **False-Negative Alert** — detect and flag likely filtering mistakes.

## 1. DecisionTrace

Every routing decision produces a `DecisionTrace` record alongside (not
replacing) the existing `Receipt` and `AuditEvent`.

```json
{
  "trace_id": "dtrace_msg_20260611_0001",
  "message_id": "msg_20260611_0001",
  "created_at": "2026-06-11T10:00:00Z",
  "sender": "person@example.com",
  "subject": "Can we talk?",
  "ai_score": null,
  "ai_confidence": null,
  "threshold_applied": null,
  "tier_assigned": "standard",
  "tier_source": "policy_lookup",
  "routing_outcome": "digested",
  "receipt_id": "rcpt_msg_20260611_0001",
  "shadow_mode": false,
  "shadow_outcome": null,
  "flags": []
}
```

### Field semantics

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | string | `dtrace_` + message_id |
| `message_id` | string | From `MessageEnvelope` |
| `created_at` | ISO-8601 | When decision was made |
| `sender` | string | Sender address |
| `subject` | string | For human review in digests |
| `ai_score` | float or null | AI-assigned importance score [0.0, 1.0], null if no AI scoring |
| `ai_confidence` | float or null | AI self-reported confidence [0.0, 1.0], null if no AI scoring |
| `threshold_applied` | float or null | The cutoff used for this tier boundary |
| `tier_assigned` | string | One of TrustTier values from SPEC-0001 |
| `tier_source` | string | How tier was determined: `policy_lookup`, `ai_classification`, `uncertainty_escalation`, `manual_override` |
| `routing_outcome` | string | Receipt state from SPEC-0001: `surfaced`, `digested`, `blocked`, etc. |
| `receipt_id` | string | Link to the Receipt produced |
| `shadow_mode` | bool | If true, actual delivery used a safer fallback; this trace records what the AI *would* have done |
| `shadow_outcome` | string or null | What would have happened if AI decision was applied (only set when shadow_mode=true) |
| `flags` | list[string] | Machine-set flags: `uncertainty_escalated`, `false_negative_suspect`, `resend_detected`, `escalation_path_used` |

### Queryability requirement

Decision traces MUST be queryable by `sender`, `tier_assigned`,
`routing_outcome`, and `flags` within the retention window. The reference
implementation uses JSONL; production systems may use any store that supports
these queries.

### Retention

Decision traces SHOULD be retained for at least 90 days. Traces flagged
`false_negative_suspect` SHOULD be retained for at least 1 year.

## 2. Shadow Mode

Shadow mode lets operators evaluate AI routing judgment without risk.

### Behavior

When `shadow_mode` is enabled (globally or per-tier):

1. The router computes the AI-recommended tier and outcome as usual.
2. Instead of applying the AI decision, it applies a **safe fallback** (one tier
   more permissive than the AI recommendation — e.g., if AI says `standard`, use
   `priority`).
3. Both the AI recommendation and the actual outcome are recorded in the
   `DecisionTrace`.

### Shadow fallback map

```text
AI says blocked   → actual: standard (+ digest)
AI says standard  → actual: priority (+ surface soon)
AI says priority  → actual: direct   (+ surface now)
AI says direct    → actual: direct   (no change)
AI says public    → actual: public   (no change)
```

### Shadow evaluation

Over time, the owner reviews messages that arrived via the safe fallback and
marks them as correctly or incorrectly routed. This produces ground-truth labels
for measuring AI accuracy.

The `FilteredDigest` (section 3) is the primary vehicle for this review.

## 3. FilteredDigest

A periodic digest of messages the router suppressed (routed to `standard`,
`blocked`, or lower than the sender's historical tier).

```json
{
  "digest_id": "fdigest_20260611_1200",
  "created_at": "2026-06-11T12:00:00Z",
  "period_start": "2026-06-11T00:00:00Z",
  "period_end": "2026-06-11T12:00:00Z",
  "items": [
    {
      "message_id": "msg_20260611_0003",
      "sender": "colleague@example.com",
      "subject": "Quick question about tomorrow",
      "tier_assigned": "standard",
      "ai_score": 0.35,
      "ai_confidence": 0.72,
      "flags": [],
      "human_verdict": null
    }
  ],
  "stats": {
    "total_filtered": 5,
    "total_passed": 12,
    "uncertainty_escalations": 1,
    "false_negative_suspects": 0
  }
}
```

### Digest generation rules

- Generated on a configurable schedule (default: every 12 hours).
- Includes all messages with `routing_outcome` in {`digested`, `blocked`} from
  the period.
- Each item shows sender, subject, assigned tier, AI score/confidence, and flags.
- The `human_verdict` field is initially null. The owner sets it to `correct`,
  `should_have_surfaced`, or `should_have_blocked` during review.
- Verdicts feed back into accuracy tracking (section 5).

### Delivery

The digest is delivered through whichever channel the owner designates for
meta-notifications (email summary, dashboard, etc.). It MUST NOT be subject to
the same filtering it reports on.

## 4. Uncertainty Escalation

When the AI is uncertain, it should pass the message through rather than filter
it.

### Rule

```text
IF ai_confidence < uncertainty_threshold (default: 0.6)
THEN escalate one tier toward direct
AND set flag "uncertainty_escalated"
AND record both original and escalated tier in DecisionTrace
```

### Rationale

False negatives are more costly than false positives in a personal communication
system. A message incorrectly surfaced wastes a moment of attention. A message
incorrectly filtered can damage a relationship. The asymmetry justifies
defaulting to escalation under uncertainty.

### Configuration

```json
{
  "uncertainty_threshold": 0.6,
  "escalation_map": {
    "blocked": "standard",
    "standard": "priority",
    "priority": "direct"
  }
}
```

The threshold is tunable. Operators with high message volume may lower it;
operators who are more risk-averse about missed messages may raise it.

## 5. False-Negative Alert

Detect probable false negatives by observing sender behavior after filtering.

### Trigger signals

A `false_negative_suspect` flag is set on a `DecisionTrace` when **any** of
these occur within a configurable lookback window (default: 48 hours) after the
original message was filtered:

1. **Resend**: Same sender sends a substantially similar message (subject or body
   overlap > 0.7 by normalized edit distance or embedding similarity).
2. **Escalation path**: Same sender contacts via a higher-trust channel (e.g.,
   first sent email which was digested, then sent via direct/priority channel).
3. **Multi-channel**: Same sender contacts via a different channel within the
   lookback window, suggesting the first message didn't get through.
4. **Third-party relay**: A `direct`-tier contact forwards or mentions the
   filtered sender's message.

### Alert behavior

When a `false_negative_suspect` flag is set:

1. The original `DecisionTrace` is updated with the flag.
2. An `AuditEvent` with `event_type: "false_negative_suspected"` is written.
3. The message is retroactively surfaced to the owner (if not already seen via
   digest).
4. The alert appears in the next `FilteredDigest` with the flag highlighted.

### Alert schema

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

## Integration with SPEC-0001

This spec extends SPEC-0001 without modifying it:

- `DecisionTrace` references but does not replace `Receipt` or `AuditEvent`.
- New `AuditEvent` types: `false_negative_suspected`, `uncertainty_escalated`,
  `shadow_mode_comparison`, `filtered_digest_generated`.
- New `Receipt` metadata field: `decision_trace_id` (optional backlink).
- `AgentPolicy` gains optional fields: `shadow_mode`, `uncertainty_threshold`,
  `digest_interval_hours`, `fn_lookback_hours`.

## Extended AgentPolicy

```json
{
  "policy_id": "policy_default_v1",
  "recipient_user_id": "user_local",
  "default_tier": "standard",
  "tier_actions": {
    "direct": ["deliver_now", "write_receipt"],
    "priority": ["classify", "surface_soon", "write_receipt"],
    "standard": ["classify", "digest", "write_receipt"],
    "public": ["route_public_agent", "write_receipt"],
    "blocked": ["audit_only"]
  },
  "monitoring": {
    "shadow_mode": false,
    "uncertainty_threshold": 0.6,
    "digest_interval_hours": 12,
    "fn_lookback_hours": 48,
    "fn_similarity_threshold": 0.7
  }
}
```

## Success Criterion

A reference implementation should demonstrate:

1. Every routing decision produces a queryable `DecisionTrace`.
2. Shadow mode logs what-if outcomes alongside actual routing.
3. A `FilteredDigest` is generated for a time period.
4. Messages with low AI confidence are escalated one tier.
5. A resend by the same sender triggers a `false_negative_suspect` flag on the
   original trace.

## Non-Goals (same spirit as SPEC-0001)

- No automatic tier adjustment from false-negative signals (that is a future
  adaptive-policy extension).
- No sender reputation system.
- No cross-user signal sharing.
- No dependency on a specific AI model or embedding provider.
