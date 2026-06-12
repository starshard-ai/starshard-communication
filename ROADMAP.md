# Roadmap: From Protocol to Platform Displacement

> Status: living document. Updated 2026-06-12.
> This is a public, append-only record of where this project is going, what risks
> exist at each stage, and what must be true for each stage to succeed.

## Strategic Thesis

Closed super-app messaging (WeChat, LINE, KakaoTalk, etc.) is structurally
hostile to the agent era:

- **Every message is a hard notification.** No user-owned policy layer exists.
  The platform decides what reaches you, optimized for engagement, not for your
  attention budget.
- **No agent access.** Third-party automation is actively suppressed. Bots get
  banned. APIs get revoked. Protocol reverse-engineering is an arms race.
- **No portability.** Your social graph, message history, and identity are
  platform-locked. Switching cost is artificially maximized.
- **No receipts.** You cannot audit what was filtered, delayed, or lost. The
  platform's routing is a black box.

The replacement is **not another chat app.** It is a user-owned communication
substrate — thin enough to sit above existing transports, open enough for agents
to operate as first-class participants, and portable enough that no single
platform owns your communication graph.

## The Wedge: Start From Work, Not Social

Displacing a super-app's social graph head-on is a network-effects problem with
no clean solution. But there is a beachhead that does not require network effects
to deliver Day-1 value:

**The individual knowledge worker drowning in notifications.**

- DingTalk / WeCom / Feishu / Slack all share the same failure: every message is
  equally loud. The user's attention is the unprotected resource.
- An agent-owned inbox layer *in front of* the existing firehose — where the user
  sets their own tiers, and the agent folds non-urgent traffic into digests with
  receipts — is a **single-player painkiller**. It works for one person, today,
  without asking anyone else to switch.
- The agent doesn't just filter — it **does routine work** via adapters
  (email, webhook, MCP endpoints). The communication tool becomes the execution
  tool. That is the lock-in.

### Why Work Before Social

| Factor | Work comms | Social comms |
|--------|-----------|--------------|
| Network effects needed for Day-1 value | No (single-player) | Yes (need friends) |
| Buyer = sufferer = chooser | Yes (individual) | Partially (group dynamics) |
| Willingness to try new tools | High (productivity gain) | Low (inertia) |
| Agent value proposition | Obvious (do my work) | Unclear (chat with friends?) |
| Incumbent vulnerability | High (notification overload is universal pain) | Low (good enough + locked in) |

## Displacement Stages

Each stage is independently valuable. Later stages are NOT assumed — if the
wedge thesis is wrong, the protocol and tooling still work as infrastructure.

### Stage 0: Protocol + Reference Implementation (NOW)

**What exists:**
- SPEC-0001: Inbox, addressing, trust tiers, policy, receipts.
- SPEC-0002: False-negative monitoring (shadow mode, uncertainty escalation,
  filtered digests).
- Reference router + monitoring implementation (Python, zero deps).
- JSON Schema for all objects.

**Key risk:** Protocol is an intellectual toy that nobody runs real communication
through.

**Falsifier:** If nobody routes real daily messages through the reference
implementation within 60 days of v0.1 shipping, the protocol is too abstract.

### Stage 1: First Real Adapter (v0.1)

**Goal:** One real transport adapter end-to-end. Likely: email or webhook →
identity → policy → receipt → audit.

**What must be true:**
- A real user can receive a real email, have it classified by their agent,
  routed according to their policy, and produce an auditable receipt — all
  locally, no hosted service required.

**Key risk:** The adapter is fragile, requires too much setup, or the policy
language is too complex for non-developers.

**Falsifier:** Setup takes > 30 minutes for a developer, or > 2 hours for a
non-developer with agent assistance.

### Stage 2: Transport Neutrality (v0.2)

**Goal:** Second adapter. Demonstrate that the same identity + policy + receipt
loop works across two different transports (e.g., email + Matrix, or email +
webhook).

**What must be true:**
- A user's trust tiers and policies are transport-neutral. Moving a contact from
  one channel to another does not require reconfiguring policy.
- Receipts are unified across transports.

**Key risk:** Transport-specific semantics leak into the protocol (e.g., email
threading vs. Matrix rooms vs. webhook payloads create irreconcilable models).

### Stage 3: Selective Attention + Digest Surface (v0.3)

**Goal:** Trust-tier policy examples + a real digest surface. The user gets a
daily/periodic summary of everything their agent filtered, with one-tap
escalation for false negatives.

**What must be true:**
- The digest is useful enough that the user checks it instead of checking the
  raw firehose.
- False-negative rate is low enough that the user trusts the agent's filtering.

**Key risk:** False negatives erode trust faster than correct filtering builds
it. One missed urgent message = user abandons the layer and goes back to
checking everything manually.

**Falsifier:** If a test user reverts to manual checking within 2 weeks, the
false-negative monitoring (SPEC-0002) is insufficient.

### Stage 4: Agent Does The Work (v0.4+)

**Goal:** The agent doesn't just filter — it handles routine communication tasks
via MCP / webhook adapters. Reply drafting, meeting scheduling, information
forwarding, task creation from messages.

**What must be true:**
- The communication layer and the task execution layer share identity and
  receipts. A message that becomes a task produces a receipt chain that traces
  from inbound message → task created → task completed → reply sent.

**Key risk:** Scope creep. This is where "communication substrate" can silently
become "build an entire agent OS." The discipline is: the communication layer
provides hooks, not implementations. Execution is the agent's job.

### Stage 5: Work-Comms Migration (later)

**Goal:** Small self-selecting teams (2-5 people) route their work communication
through the substrate instead of through DingTalk/WeCom/Feishu, because the
agent layer is genuinely better for their workflow.

**What must be true:**
- Multi-party receipts work (A sends to B and C; B's agent handles it; C's agent
  digests it; A gets differentiated receipts from both).
- No employer permission is required — this is a personal layer *in front of*
  the mandated app, not a replacement that requires IT department buy-in.

**Key risk:** China's work-comms is employer-chosen, not user-chosen. If the
personal layer conflicts with employer-mandated tools (e.g., compliance logging
requirements), adoption stalls.

**Hardest problem:** The employer can mandate DingTalk. They cannot mandate that
you read every message in DingTalk with equal attention. The personal layer
exploits this gap.

### Stage 6: Super-App Dependence Decline (uncertain)

**Goal:** Users who have migrated their work-comms begin migrating social comms.
The super-app is downgraded from "home" to "bridge" — a transport adapter, not
the primary interface.

**What must be true:**
- Social graph portability exists (contacts can be addressed across transports).
- The substrate supports casual/social communication patterns, not just
  work-oriented structured messaging.

**Key risk:** This may never happen, or may take a decade. Social communication
has stronger network effects than work communication. The project should be
designed so that Stages 0-5 are independently valuable even if Stage 6 never
arrives.

**Anti-signal:** If the project's success metrics depend on Stage 6, the
strategy is wrong. Each stage must stand alone.

## Anti-Signals (Things That Mean We Are Failing)

- Readers mainly ask "how do I scrape WeChat?" → the framing failed; we are
  attracting bridge-builders, not substrate-builders.
- Nobody runs real daily communication through it → intellectual toy.
- The protocol requires a hosted service to work → we recreated a platform.
- Important contacts can only reach the user through platform DMs → the
  substrate is not a real communication path.
- The project spends more energy on platform-evasion than on building owned
  capability → we are still in the parasite mindset.
- Public artifacts exist only as platform posts (WeChat articles, Xiaohongshu
  notes) → we have not left the old body.

## Open Questions

- **Mobile form factor:** Is the end-user surface a standalone app, a PWA, a CLI
  tool, or something else? Deferred until real usage data from early adopters
  arrives.
- **Encryption:** Transport security reuses established protocols (TLS,
  Signal Protocol, MLS). Whether the substrate needs its own E2E layer or can
  delegate to transport adapters is an open design question.
- **Existing community leverage:** Projects like Wechaty have built substantial
  developer communities (200+ contributors) around WeChat automation. These
  developers understand the pain of closed-platform restrictions intimately.
  The substrate should be useful to them — not as a better scraping tool, but
  as the thing they graduate *to* when they are ready to stop fighting the
  platform's anti-bot measures.
- **Memory-addressed communication:** Should the protocol support addressing by
  *topic* or *memory reference* rather than by contact identity? (e.g., "send
  this to whoever is handling the hotel booking" rather than "send this to
  person X"). Design exploration pending.
- **Regulatory surface:** In jurisdictions with messaging compliance requirements
  (China's cybersecurity law, EU's Digital Services Act), the substrate must be
  designed so that compliance is achievable without centralizing control. This
  is a hard design constraint, not an afterthought.

## How to Contribute

This is an open project. If you are building agent-mediated communication tools,
fighting closed-platform restrictions, or thinking about what comes after the
super-app era, you are the target audience.

- Read SPEC-0001 and SPEC-0002.
- Build an adapter for a transport you care about.
- Run the reference implementation against your real message flow.
- File issues for protocol gaps you hit.
- Share what breaks.

The protocol evolves from real usage, not from committee.

## Build Log

See the [Progress Log in README.md](README.md#progress-log) for shipped
artifacts and their dates.
