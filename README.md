# Starshard Communication

> v0 — experimental. An open communication substrate for personal-agent users.
> Whitepaper + reference implementation + public build log.

## The Core Claim

The AI-agent-era replacement for closed super-app chat is probably **not another
chat app**. It is a **user-owned layer** for inboxes, addresses, trust policies,
receipts, and channel adapters — a thin protocol that sits *above* existing
transports rather than replacing them.

The thinnest useful loop:

```text
message -> local identity -> local policy -> receipt -> audit
```

Memory systems, task ledgers, public/friends/private agents, and richer agent
workflows are all extensions. The first protocol should work without any of them.

## What This Is

- A small protocol draft for **inbox, addressing, trust tiers, policy, and receipts**.
- Reference JSON shapes for `MessageEnvelope`, `AgentPolicy`, and `Receipt`.
- A tiny local reference implementation that routes one inbound message and
  writes auditable receipts.

## What This Is Not

- Not a hosted service.
- Not a new cryptographic protocol — transport security reuses established
  protocols and libraries (Matrix/MLS, Signal Protocol, TLS, mail/webhook patterns).
- Not a chat-app clone.
- Not a platform scraper.
- Not a claim that every private message should be read by an AI.

Existing channels — email, webhooks, Matrix, SimpleX, ActivityPub, MCP
endpoints, or local inboxes — can each become an **adapter** into this substrate.

## The Whitepaper, In One Page

**Problem.** As personal AI agents become the primary interface, the bottleneck
moves from "how do I send a message" to "how does *my agent* receive, classify,
route, acknowledge, and audit the communication coming at me — on terms I own."
Closed super-apps don't expose that layer; they own it.

**Thesis.** Communication for the agent era should decompose into a small,
inspectable substrate:

1. **ContactIdentity / EndpointAddress** — who, and through which channel.
2. **TrustTier** — `direct` / `priority` / `standard` / `public` / `blocked`,
   *local to the recipient* (no claim of global truth about a relationship).
3. **AgentPolicy** — per-tier actions (deliver now, classify, digest, route to a
   public agent, audit-only).
4. **Receipt** — not just "delivered," but a **lifecycle state**:
   `received → routed → surfaced/digested/delegated/blocked → handled`.
5. **AuditEvent** — every routing decision is locally auditable.

**Why it matters.** This makes the recipient's *policy* — not the platform — the
thing that decides what reaches them. It is portable across transports, provider-
neutral, and degrades gracefully: the thin layer still works if no memory hub,
task ledger, or fancy agent exists.

**Six-month success metric.** Not stars or agreement. A real win: a user can move
their active communication graph onto non-super-app paths with a working receipt
loop end to end.

See [SPEC-0001](docs/SPEC-0001-inbox-addressing-receipts.md) for the full
object model and the first protocol spike.

## Start Here

- [SPEC-0001 — Inbox, Addressing, and Receipts](docs/SPEC-0001-inbox-addressing-receipts.md)
- [Message envelope example](examples/message-envelope.json)
- [Receipt example](examples/receipt.json)
- [Reference implementation](reference-impl/router.py)

## Run The Demo

```bash
python3 reference-impl/router.py \
  --message examples/message-envelope.json \
  --out /tmp/starshard-communication-demo
```

The demo writes `receipts.jsonl` and `audit-events.jsonl`.

## Roadmap

- **v0 (now)** — protocol draft (SPEC-0001), envelope/receipt shapes, single
  reference router, public build log.
- **v0.1** — one real adapter end-to-end (email or webhook → identity → policy →
  receipt → audit).
- **v0.2** — second adapter; demonstrate transport-neutrality across two channels.
- **v0.3** — trust-tier policy examples + digest surface.
- **later** — optional extension points: memory persistence, task ledger,
  public/friends agents, contact-graph sync, cross-device notification surfaces.
  Each is strictly additive; the thin layer never depends on them.

## Progress Log

Public, append-only build log. Newest first. Each entry: date, what shipped, a
verifiable artifact (commit / file / demo output).

| Date | Shipped | Artifact |
|------|---------|----------|
| 2026-06-xx | Repo bootstrapped: README + SPEC-0001 + reference router + examples | this commit |

> Build-in-public convention: every substantive change appends one row here with
> a link to the commit or artifact, so the protocol's evolution is itself
> auditable — the same receipt-loop principle the spec describes.

## License

Apache-2.0. See [LICENSE](LICENSE).
