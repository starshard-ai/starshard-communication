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
  [SPEC-0003](docs/SPEC-0003-agent-identity-authentication-and-secure-messaging.md)
  spells out exactly which established standards, at which maturity level, and how
  they compose — it composes, it does not invent.
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

## For Agent / LLM Consumers

If you are an agent or automated system looking to parse and integrate with this
protocol, start here instead of the prose below:

- **[INTEGRATION.md](INTEGRATION.md)** — structured integration guide (object
  model table, enum reference, example flows as JSON, CLI reference).
- **[schemas/spec0001.schema.json](schemas/spec0001.schema.json)** — formal JSON
  Schema for all SPEC-0001 and SPEC-0002 objects (`$defs` keyed by object name).

## Agent-to-Agent Identity and Secure Messaging (SPEC-0003)

SPEC-0001 and SPEC-0002 cover messages arriving at *a human's* agent.
**[SPEC-0003](docs/SPEC-0003-agent-identity-authentication-and-secure-messaging.md)**
covers the other direction, and is the longest document here:

> **How do two agents, belonging to two different people, on two different machines,
> with no shared platform and no common identity provider, authenticate each other,
> verify what each is allowed to do on its human's behalf, and exchange messages that
> survive being offline, duplicated, replayed, or observed?**

It covers: agent identity as a keypair (`did:key` vs `did:web` vs X.509/SPIFFE, with
a correction — `did:key` and `did:web` are **W3C Community Group drafts, not
Recommendations**); the principal / agent / host identity triple; key rotation, device
loss, and why revocation fundamentally fights offline verifiability; **the agent-fork
problem**, which we consider unsolved by anyone; mutual authentication with Noise `XX`
and `IK`; preventing an agent from impersonating its own principal; a
**machine-readable, offline-verifiable authority envelope** with attenuation-only
delegation and a structurally-enforced non-delegable set; why Signal, email, and
platform DMs each cannot be the whole answer; store-and-forward commit sequencing,
idempotency, and replay protection; **two-phase receipts** (intent before, execution
after, hash-linked) and why one is not enough; a correction to our own shipped
work-claim design, which is **not sound across a trust boundary** because leases
without fencing tokens do not stop a stale holder; and a ten-item list of what we have
**not** solved.

Every claim carries a confidence badge: ✅ RUNNING / 🔵 DESIGNED / 🟡 CONJECTURE /
📚 CITED / ⚠️ OPEN. Every external standard is cited with its verified maturity level,
because several of the most-cited "standards" in agent identity are not standards.

中文：**没有中心化平台时,两个 agent 如何互相认证、如何用机器可读的方式表达"我被授权做什么"、
如何安全异步传递消息。** 不发明新密码学,只组合已有标准,并诚实标注哪些已实现、哪些只是设计、
哪些没解决。

## Start Here

- [SPEC-0001 — Inbox, Addressing, and Receipts](docs/SPEC-0001-inbox-addressing-receipts.md)
- [SPEC-0002 — False-Negative Monitoring](docs/SPEC-0002-false-negative-monitoring.md)
- [**SPEC-0003 — Agent Identity, Authentication, and Secure Agent-to-Agent Messaging**](docs/SPEC-0003-agent-identity-authentication-and-secure-messaging.md)
- [Message envelope example](examples/message-envelope.json)
- [Receipt example](examples/receipt.json)
- [Authority envelope example (SPEC-0003)](examples/authority-envelope.json)
- [Two-phase receipt pair example (SPEC-0003)](examples/receipt-pair.json)
- [Reference implementation — basic router](reference-impl/router.py)
- [Reference implementation — monitoring router](reference-impl/monitor.py)
- [False-negative monitoring demo](examples/fn-monitoring-scenario/)

## Run The Demos

Basic router (SPEC-0001):

```bash
python3 reference-impl/router.py \
  --message examples/message-envelope.json \
  --out /tmp/starshard-communication-demo
```

False-negative monitoring (SPEC-0002):

```bash
bash examples/fn-monitoring-scenario/run-demo.sh
```

The monitoring demo routes 4 messages, generates a filtered-message digest,
and scans for false-negative signals. Expected: one uncertainty escalation
(low-confidence AI score) and one false-negative alert (sender resend detected).

## Roadmap

See **[ROADMAP.md](ROADMAP.md)** for the full displacement strategy, per-stage
risk analysis, falsifiers, and open questions.

Summary:

- **Stage 0 (now)** — protocol draft (SPEC-0001 + SPEC-0002), reference router,
  public build log.
- **Stage 1** — first real adapter end-to-end (email or webhook → identity →
  policy → receipt → audit).
- **Stage 2** — second adapter; demonstrate transport-neutrality.
- **Stage 3** — selective attention + digest surface.
- **Stage 4** — agent does the work (MCP/webhook task execution from messages).
- **Stage 5** — work-comms migration (small self-selecting teams).
- **Stage 6** — super-app dependence decline (uncertain; project designed so
  Stages 0-5 stand alone without this).

Each stage is independently valuable. Later stages are not assumed.

## Progress Log

Public, append-only build log. Newest first. Each entry: date, what shipped, a
verifiable artifact (commit / file / demo output).

| Date | Shipped | Artifact |
|------|---------|----------|
| 2026-08-22 | SPEC-0003: Agent identity, authentication, and secure agent-to-agent messaging — identity triple, offline-verifiable authority envelope with attenuation-only delegation, two-phase receipts, a correction to our own work-claim design across trust boundaries, and 10 open problems. Standards cited with verified maturity levels. | [`docs/SPEC-0003-…`](docs/SPEC-0003-agent-identity-authentication-and-secure-messaging.md) + [`examples/authority-envelope.json`](examples/authority-envelope.json) + [`examples/receipt-pair.json`](examples/receipt-pair.json) |
| 2026-06-11 | SPEC-0002: False-negative monitoring — decision trace, shadow mode, filtered digest, uncertainty escalation, FN alert detection. Reference impl + runnable demo scenario. | branch `fn-monitoring-v0` |
| 2026-06-11 | Repo published: README (whitepaper-in-one-page) + SPEC-0001 + reference router + envelope/receipt examples + Apache-2.0 | first public commit (`2fa9962`) |

> Build-in-public convention: every substantive change appends one row here with
> a link to the commit or artifact, so the protocol's evolution is itself
> auditable — the same receipt-loop principle the spec describes.

## License

Apache-2.0. See [LICENSE](LICENSE).
