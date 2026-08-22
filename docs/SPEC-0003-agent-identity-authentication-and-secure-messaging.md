# SPEC-0003: Agent Identity, Authentication, and Secure Agent-to-Agent Messaging

> **Status:** draft (v0) · **Date:** 2026-08-22 · **Layer:** identity & transport security
> **Relationship to the rest of this repo:** [SPEC-0001](SPEC-0001-inbox-addressing-receipts.md)
> defines the inbox/policy/receipt loop for messages arriving at *a human's* agent and
> explicitly lists "no custom encryption protocol" and "no identity system" as non-goals.
> [ROADMAP.md](../ROADMAP.md) lists encryption under Open Questions. The
> [Fleet Coordination Protocol](https://github.com/starshard-ai/fleet-coordination-protocol)
> §1 states plainly that its `source` field is *"an opaque label, not an authenticated
> identity in v0."*
>
> **This document is that gap.** It is about the other direction: how two agents belonging
> to two different people, on two different machines, with no shared platform and no common
> identity provider, come to believe each other's identity, verify what each is allowed to
> do on its human's behalf, and exchange messages that survive being offline, duplicated,
> replayed, or observed.
>
> 中文摘要：本文讨论 **没有中心化平台时,两个 agent 如何互相认证、如何表达"我被授权做什么"、
> 如何安全异步传递消息**。它不发明新密码学,而是把已有标准(DID / VC / UCAN / Noise / MLS /
> WebAuthn / SPIFFE)组合成一个可实现的最小层,并诚实标注哪些已实现、哪些只是设计、哪些是推测。

---

## 0. How to read this document

Every substantive claim carries a confidence badge. This is the same discipline as the
[Claim-Receipt format](https://github.com/MachengShen/system-evolution-public/blob/main/CLAIM-RECEIPT.md),
mapped to this document's subject matter:

| Badge | Meaning | Claim-Receipt equivalent |
|---|---|---|
| ✅ **RUNNING** | There is code we run daily that does this. Named, and the failure it prevents is a real logged incident. | `survived-stress-test` |
| 🔵 **DESIGNED** | Specified here in enough detail to implement. Not implemented. May be wrong in ways only implementation will reveal. | `speculative`, high confidence in the *shape* |
| 🟡 **CONJECTURE** | We believe it and can argue for it. No implementation, no proof, possibly no consensus. | `speculative` |
| 📚 **CITED** | A factual statement about an external standard, verified against the primary source on 2026-08-22. | `raw` (intake, verified) |
| ⚠️ **OPEN** | We do not know how to do this. Stated because omitting it would make the document dishonest. | — |

A document about security that does not separate "we run this" from "we think this" is
marketing. §9 is the list of things we cannot do; if you read only one section, read that one.

**Standards accuracy note.** Every external standard referenced here was checked against its
primary source (IETF Datatracker, W3C `/TR/`, or the spec's own repository) on 2026-08-22, and
the *maturity level* is stated, not assumed. Several widely-cited "standards" in this space are
not standards — see §10.

---

## 1. The problem: what disappears when there is no platform

When you message someone on a closed platform, the platform silently provides seven things:

1. **Namespace** — a globally unique handle for each party.
2. **Identity binding** — proof that the handle belongs to who you think.
3. **Key distribution** — you never exchange keys; the platform does it.
4. **Revocation** — a lost phone is handled by the platform's account recovery.
5. **Liveness** — the platform knows if the recipient is reachable.
6. **Ordering and deduplication** — you do not get the same message twice.
7. **Arbitration** — when two clients conflict, the server decides.

All seven are provided in exchange for the platform being the trust root, the routing
authority, and the observer of everything. The agent era makes this trade worse, not better:
an agent acting on your behalf needs a *machine-readable, verifiable statement of what it may
do*, and no platform offers one, because within a platform the answer is always "whatever the
platform permits."

Remove the platform and each of the seven becomes an explicit protocol problem. This document
takes them in order: namespace and binding (§3), key distribution and revocation (§3.3),
authorization (§5), liveness and ordering (§6), arbitration (§6.5), and auditability (§7).

### 1.1 What specifically breaks — the concrete failure classes

These are failure classes we have hit in a running multi-agent, multi-machine, multi-person
setup. They are why this document exists rather than "we should probably use TLS."

| # | Failure | Why the platform normally hides it |
|---|---|---|
| F1 | **A channel dies and nobody notices.** An agent-to-agent path stopped working; both sides kept operating on the assumption it worked, for days. | Platforms surface delivery failure synchronously. |
| F2 | **Notification mistaken for delivery.** A file-sync/webhook/push event fired, and the sender recorded "delivered." The receiver never durably held it. | Platform ACKs come from the store, not the notifier. |
| F3 | **Duplicate irreversible action.** Three concurrent sessions independently formed the same intent and each performed it once — three identical external sends. | Platforms deduplicate server-side by message id. |
| F4 | **Unauthenticated `source` label.** Coordination records were tagged with a plain string naming the writing agent. Anything could write anything. | Inside a platform, the server authenticates the writer. |
| F5 | **Authority is prose, not data.** "This agent may do X on my behalf" existed only as English in a config file. The receiving side had nothing to verify. | Platforms have no concept of delegated authority at all — which is the deeper problem. |
| F6 | **Receipts written after the fact.** A log entry saying "I did X" cannot prove X was authorized *before* it happened. | Platforms don't try. |

✅ **RUNNING** — F1–F4 and F6 are logged incidents in our own system, not hypotheticals. The
mitigations described in §6 and §7 exist as code. F5 is mitigated only *within* our fleet, by a
schema that never crosses a trust boundary (§5.2).

---

## 2. Threat model

A protocol without a threat model is a wish. Here is what we assume, and what we are trying
to stop.

### 2.1 Adversaries

| Adversary | Capability assumed | In scope? |
|---|---|---|
| **A1 Network attacker** | Reads, drops, reorders, replays, and injects anything on the wire. Cannot break modern AEAD or forge Ed25519 signatures. | Yes |
| **A2 Malicious peer agent** | A legitimately-identified agent that lies about what it is authorized to do, or asks for more than it should. | Yes |
| **A3 Curious relay** | The store-and-forward host (mail server, object store, shared folder, hub) reads everything it carries and logs metadata. | Yes for content; **partially** for metadata (§9.2) |
| **A4 Compromised agent host** | Full control of one endpoint, including any key material on its disk. | Detection only, not prevention (§3.4) |
| **A5 Forked/cloned agent** | An exact copy of an agent, including its private key and state, run elsewhere. | Detection only, and imperfectly (§3.5) — this is the hardest one |
| **A6 Over-reaching own agent** | *Your own* agent exceeding the authority its principal granted, whether by bug, prompt injection, or drift. | Yes — this is the one platforms ignore entirely |
| **A7 Coerced principal** | The human is compelled to authorize. | **No.** Out of scope. |

A6 deserves emphasis. Most identity work in this space asks "is this agent who it says it is?"
The more common and more damaging failure is an agent that *is* who it says it is and does
something its human never sanctioned. Identity without a machine-checkable authority bound to
it solves the easy half of the problem.

### 2.2 Explicit non-goals

- **No new cryptographic primitives.** Everything here composes published, reviewed
  constructions. If this document appears to invent a cipher, mode, or handshake, that is a bug
  in the document.
- **No global consensus, ledger, or chain.** Nothing here requires third parties to agree.
  Two agents must be able to derive full value with `n = 2`.
- **No mandatory hosted service.** A hosted relay may exist for reachability; it must never be
  the trust root.
- **No metadata-hiding guarantee.** We do not claim to be Tor or a mixnet. See §9.2.
- **No protection against a coerced or careless human.**
- **Not a replacement for Signal, MLS, or email.** §6.1 explains what each is good at and where
  each is load-bearing here.

### 2.3 Security goals, stated so they could fail

1. **G1 Mutual authentication with no IdP.** Each side ends a handshake knowing the other's
   long-term public key, with no third party consulted at handshake time.
2. **G2 Offline verifiability.** A receiver can validate an inbound message's identity *and*
   authority using only the message, the principal's public key, and its local clock. No
   callback to an issuer, no introspection endpoint.
3. **G3 Attenuation-only delegation.** No delegation chain can produce more authority than its
   root. Structurally enforced, not policy-enforced.
4. **G4 Non-delegable core.** Certain actions can never appear in any valid delegation,
   regardless of who signed it.
5. **G5 Exactly-once external effect.** Under retry, duplication, and partition, an irreversible
   action happens at most once, and the fact of it is auditable by the counterparty.
6. **G6 No unauditable action.** Every irreversible action has a pre-action record the
   counterparty could have read *before* it happened, and a post-action record.

Falsifiers for each are in §11.

---

## 3. Identity

### 3.1 What an agent's identity actually is

An agent's identity is **an asymmetric key pair whose public half is the identifier**, plus a
signed statement from a human principal about what it may do. Everything else — a DID, an
X.509 certificate, a SPIFFE ID, a username — is an *encoding* or a *discovery mechanism* laid
over that.

🔵 **DESIGNED** — We take a position: **the key is the identity; names are conveniences.** The
practical consequence is that the protocol must work when the only thing you have is a 32-byte
public key, and must degrade gracefully when nicer naming is available.

The three candidate encodings, honestly compared:

| | `did:key` | `did:web` | X.509 / SPIFFE |
|---|---|---|---|
| **What it is** | The public key, multibase-encoded, *is* the identifier | An HTTPS URL that resolves to a DID document | A certificate signed by a CA / a `spiffe://` URI in a cert SAN |
| **Resolution needs** | Nothing. Offline. | DNS + TLS + the domain being up | A trusted CA / a trust-domain root |
| **Rotation** | ⛔ Impossible — rotating the key changes the identifier | ✅ Update the document | ✅ Reissue |
| **Revocation** | ⛔ None | ✅ Remove from document | ✅ CRL/OCSP, or SPIRE's short TTLs |
| **Trust root** | None needed | The domain owner + web PKI | The CA / SPIRE server |
| **Fails when** | You need to rotate | The domain lapses or is seized | The CA is unreachable or compromised |
| **Maturity** | 📚 W3C **Credentials Community Group draft, v0.9 — *not* a W3C Recommendation** | 📚 W3C CG spec, self-labelled `"unofficial"` | 📚 RFC 5280 (Standards Track, 2008); SPIFFE = CNCF-graduated spec set, not IETF/W3C |

📚 **CITED** — A correction worth making loudly, because it is miscited constantly:
[DIDs v1.0](https://www.w3.org/TR/did/) is a genuine **W3C Recommendation (19 July 2022)**, and
DIDs v1.1 is a **Candidate Recommendation Snapshot (5 March 2026)**. But **`did:key` and
`did:web` are neither.** Both are W3C Credentials Community Group products —
[`did:key` v0.9](https://w3c-ccg.github.io/did-key-spec/) and
[`did:web`](https://w3c-ccg.github.io/did-method-web/), the latter carrying
`"specStatus": "unofficial"` in its own source. Writing "the W3C did:key standard" in a design
doc is a signal the author did not check. DID *methods* live outside the Rec track.

**Our choice:** 🔵 **DESIGNED** — `did:key` as the *wire identifier*, with rotation handled by a
signed rotation credential (§3.3) rather than by making the identifier mutable. This keeps G2
(offline verifiability) intact, which `did:web` cannot: a `did:web` receiver that is offline, or
whose peer's domain has lapsed, cannot verify anything. We pay for that with rotation complexity
instead of borrowing the web PKI's availability assumptions.

### 3.2 The identity triple — principal, agent, host

The single most common modelling error we have seen is collapsing three distinct identities
into one.

```text
   ┌──────────────┐      delegates to      ┌──────────────┐   runs on   ┌──────────────┐
   │  PRINCIPAL   │ ─────────────────────▶ │    AGENT     │ ──────────▶ │     HOST     │
   │   (human)    │  signed, attenuated,   │  (instance)  │  attested   │  (device)    │
   │              │  expiring capability   │              │             │              │
   │ root key,    │                        │ own keypair, │             │ own keypair, │
   │ never on an  │                        │ never speaks │             │ says nothing │
   │ agent host   │                        │ AS principal │             │ about intent │
   └──────────────┘                        └──────────────┘             └──────────────┘
```

- **Principal** — the human. Holds a root key that **never resides on a machine an agent
  controls**. Ideally in a hardware authenticator. 📚 **CITED** —
  [W3C Web Authentication Level 2](https://www.w3.org/TR/webauthn-2/) is a full W3C
  Recommendation and is the realistic vehicle here;
  [Level 3](https://www.w3.org/TR/webauthn-3/) is a **Candidate Recommendation Snapshot
  (26 May 2026)** — advancement to Recommendation was proposed in mid-2026 but the TR page still
  reads CR, so cite Level 2 for anything load-bearing. WebAuthn is the browser API; the
  authenticator side is FIDO CTAP2, a FIDO Alliance spec (verify the current CTAP version at
  <https://fidoalliance.org/specifications/> before citing a number — published version strings
  disagree across secondary sources).
- **Agent** — one running instance. Own key pair, generated locally, never leaving its host.
  An agent's messages are signed with the *agent* key and carry a proof of delegation from the
  principal. **The agent never possesses the principal's key**, which is what makes
  impersonation structurally impossible rather than merely forbidden (§4.3).
- **Host** — the device. Its key attests to *where* an agent runs, not to what the agent
  intends. 📚 **CITED** — this layer is exactly what
  [SPIFFE](https://spiffe.io/) formalizes for workloads (SPIFFE ID + X509-SVID/JWT-SVID, CNCF
  graduated since Sept 2022). SPIFFE solves host/workload identity well and deliberately says
  nothing about a human principal's delegated authority — which is why it is a component here,
  not the answer.

🟡 **CONJECTURE** — We think the industry will converge on this triple, and that the current
crop of vendor "agent identity" products are under-modelled because they collapse
principal↔agent (treating the agent as the user, via a borrowed OAuth token) or agent↔host
(treating the agent as a workload, via SPIFFE alone). Confidence ~0.7. Falsifier: a widely
adopted design that handles delegation revocation and agent forking correctly with only two
levels.

### 3.3 Key rotation, device loss, revocation

Revocation is the hardest requirement to reconcile with G2 (offline verifiability), because
revocation is inherently *news* and offline verifiers get no news. Anyone claiming to have
solved both at once has quietly dropped one.

Our position — 🔵 **DESIGNED**:

1. **Short-lived agent credentials, long-lived principal key.** An agent's delegation carries
   an `exp` measured in hours or days. Revocation is then mostly *expiry*: to de-authorize an
   agent, stop renewing it. This is the same trade SPIFFE/SPIRE makes with short-TTL SVIDs, and
   it is the only revocation mechanism that works offline, because the verifier needs no news
   to reject an expired credential — only a clock.
2. **Rotation as a signed statement, not a new identity.** A `KeyRotation` credential signed by
   the *outgoing* agent key and countersigned by the principal binds old → new:
   ```json
   {
     "type": "KeyRotation",
     "prev": "did:key:z6Mk...OLD",
     "next": "did:key:z6Mk...NEW",
     "principal": "did:key:z6Mk...PRINCIPAL",
     "not_before": "2026-08-22T10:00:00Z",
     "reason": "scheduled",
     "sig_prev": "...",
     "sig_principal": "..."
   }
   ```
   A peer holding only the old key can follow the chain forward offline. **The principal
   countersignature is required** — otherwise anyone who steals the old key can rotate to a key
   they control and inherit the relationship. This is the failure mode of naive
   self-signed rotation.
3. **Device loss = principal-signed revocation + no renewal.** The principal publishes a
   `Revocation` for the lost agent key and stops renewing. Peers who are online learn
   immediately; peers who are offline learn at the credential's `exp`. **This window is real and
   we do not close it.** Setting `exp` short shrinks it and raises renewal cost — a dial, not a
   solution.
4. **Principal root key loss.** ⚠️ **OPEN.** Social recovery, an M-of-N guardian set, or a
   pre-signed offline successor credential are the candidates. We have implemented none. A
   design that requires the human to never lose a hardware key is not deployable, and we do not
   currently have a better answer than "keep a second authenticator."

📚 **CITED** — For the "learn revocation when online" half, the mature pattern is a
transparency log. [Certificate Transparency](https://www.rfc-editor.org/info/rfc6962/) (RFC 6962)
and [CT v2.0](https://www.rfc-editor.org/info/rfc9162/) (RFC 9162) are the canonical designs —
noting that both are IETF **Experimental**, not Standards Track, despite CT being effectively
mandatory in web PKI through browser policy rather than IETF status. That gap between "formal
status" and "actually required" is itself instructive for this space.

### 3.4 Compromised host

⚠️ **OPEN, with a partial answer.** If A4 holds the host, it holds the agent key. Nothing in a
software-only design prevents this. Partial mitigations, in decreasing order of how much we
believe in them:

- **Hardware-bound keys.** Keep the agent key in a Secure Enclave / TPM so it can sign but not be
  exfiltrated. Effective, and it breaks agent migration — an agent that cannot be moved between
  machines loses a property we actually want.
- **Short expiry.** Bounds the damage window (§3.3).
- **Behavioural detection.** Out of scope here, and we are sceptical of it as a security control.

We flag this rather than paper over it: **an agent's key is only as safe as the least-defended
machine it runs on**, and personal-agent fleets run on laptops.

### 3.5 The fork problem — the genuinely unsolved one

⚠️ **OPEN.** This is the question classical PKI never had to ask, and we consider it the most
interesting open problem in agent identity.

Copy an agent's state directory and you have copied its identity. Not impersonated it — *copied*
it. Both instances are, cryptographically, the same agent. They will both hold valid
delegations. They will both pass every check in this document. And agent state is *designed* to
be copyable: that is what snapshots, migrations, backups, and handoffs are.

The candidate answers and why each is unsatisfying:

| Approach | Mechanism | Why it falls short |
|---|---|---|
| **Hardware binding** | Key in a TPM/Enclave; cannot be copied | Kills migration, backup, and multi-device — the things agents need most |
| **Monotonic counter** | Each message carries a strictly increasing counter; verifier rejects regressions | Detects a fork only *after* both copies have talked to the same verifier; two forks talking to disjoint peers are invisible |
| **Key transparency** | Publish agent-key→principal bindings to an append-only log; forks show as anomalies | Same as above but with a shared observer; requires the log to exist and be watched, which reintroduces a third party |
| **Epoch re-attestation** | Identity = `(key, lineage_id, epoch)`; each epoch requires a fresh principal countersignature, which the principal grants to exactly one instance | Requires the principal to be reachable at every epoch boundary; a fork that grabs the epoch first wins, and the honest instance is the one that looks wrong |

🟡 **CONJECTURE**, confidence ~0.65 — **the honest answer is detection, not prevention**, and the
right primitive is a monotonic counter plus an append-only log of agent-key events, exactly
parallel to how the web gave up on preventing mis-issuance and settled for making it *visible*
(CT). We suspect the eventual formulation is that an agent's identity is not the key but the
key *plus an unforgeable position in a history*, and that a fork is defined as two claims to the
same position — the same structure as a double-spend, without needing a chain to detect it
pairwise.

We have not implemented this. Anyone who tells you agent forking is a solved problem should be
asked what happens to the honest copy.

---

## 4. Authentication

### 4.1 Mutual authentication with no identity provider

📚 **CITED** — The mature building block is the
[Noise Protocol Framework](https://noiseprotocol.org/noise.html), **revision 34 (11 July 2018)**,
authored and maintained by Trevor Perrin as an **independent specification — it is not an RFC
and sits on no standards track**, which has not stopped it from underpinning WireGuard,
WhatsApp, the Lightning Network, and libp2p. Longevity without a standards body is worth noting:
the spec has been stable since 2018.

The two handshake patterns that matter here:

- **`XX`** — a three-message mutual handshake in which neither side knows the other's static
  public key beforehand; both statics are transmitted **encrypted**, not in the clear. Use for
  **first contact**: you learn the peer's key as an *outcome* of the handshake, then pin it
  (trust-on-first-use, or confirm the fingerprint out of band).
- **`IK`** — the initiator already knows the responder's static key, so the handshake completes
  in one round trip. The initiator's static key travels in the first message, encrypted to the
  responder's known static. Use for **every subsequent session**, since after `XX` you have the
  key.

The honest characterization of the trade: `IK` is not "less secure" than `XX` overall — it
buys 1-RTT at the cost of *some* initiator identity-hiding strength, because an attacker who
already knows or guesses the responder's static key has a probe against message 1. If
initiator anonymity against an adversary who knows your peer matters more than latency, stay
on `XX`.

🔵 **DESIGNED** — `XX` for introduction, pin the resulting key, `IK` thereafter. Out-of-band
confirmation of the pinned key (a fingerprint compared over any existing channel) upgrades TOFU
to real authentication and is a one-time cost per relationship. This is deliberately the same
shape as SSH host keys and Signal safety numbers, because that shape has survived contact with
real users.

**Where a certificate approach is better:** if both agents live inside one administrative trust
domain — a company, a homelab, a fleet — a CA is simpler and gives you revocation. SPIFFE/SPIRE
is the well-trodden version. The pairwise, pinned-key design here is for the case a CA cannot
cover: two people who do not share an employer, a platform, or a root of trust.

### 4.2 Offline-verifiable credentials

For claims that outlive a session — "this agent may act for this principal until Friday" — a
handshake is the wrong tool; you want a signed, self-contained, offline-checkable credential.

📚 **CITED**, with maturity levels that differ more than most people realize:

- **[Verifiable Credentials Data Model v2.0](https://www.w3.org/TR/vc-data-model-2.0/)** — a
  **W3C Recommendation since 15 May 2025**, shipped with a family of companion Recommendations
  (Data Integrity 1.0, EdDSA/ECDSA cryptosuites, VC-JOSE-COSE, Controlled Identifiers v1.0,
  Bitstring Status List v1.0). [v1.1](https://www.w3.org/TR/vc-data-model-1.1/) remains a valid
  Recommendation (3 March 2022) for existing deployments. Worth knowing: v2.0 explicitly does
  *not* require DIDs — VCs and DIDs are separable, and conflating them is a common error.
- **SD-JWT** — "Selective Disclosure for JSON Web Tokens" is **RFC 9901**, IETF Standards Track,
  published **November 2025**. Real, finished, citable.
- **SD-JWT VC** — the credential *format* layered on it is still
  [`draft-ietf-oauth-sd-jwt-vc`](https://datatracker.ietf.org/doc/draft-ietf-oauth-sd-jwt-vc/)
  (`-18` as of August 2026), **an Internet-Draft, not an RFC.** These two get cited
  interchangeably; they are at different maturity levels and should not be.
- Signature layer: **[RFC 8032](https://www.rfc-editor.org/info/rfc8032/)** EdDSA/Ed25519 —
  IRTF CFRG, **Informational**, January 2017, and a de facto standard despite that status.
  Serialization: JOSE (**RFC 7515** JWS, **RFC 7519** JWT) or COSE (**RFC 9052**, Standards Track
  / STD 96, plus **RFC 9053** Informational for algorithms) where CBOR is preferable.

🔵 **DESIGNED** — Our credential is a VC-shaped object signed with Ed25519, serialized as a JWS,
with the delegation semantics of §5. Selective disclosure (SD-JWT) matters for a specific case:
proving *one* capability to a counterparty without revealing the full scope of what your
principal authorized — which is a real privacy leak in naive capability tokens, since handing
over the token hands over the whole list.

### 4.3 Preventing an agent from impersonating its principal

This is where most designs quietly fail, and it is A6 from the threat model.

If an agent holds its principal's key, then "the agent acting as the human" and "the human"
are cryptographically identical, and no receiving party can tell them apart. Every "let the
agent use the user's OAuth token" integration has this property. It is not a policy weakness;
it is an absence of the information needed to have a policy.

🔵 **DESIGNED** — three rules, all structural:

1. **The principal's key never touches an agent host.** Not encrypted-at-rest, not in an agent's
   keychain. If it is there, rule 2 is unenforceable.
2. **Every agent message is signed by the agent key and carries `on_behalf_of`.** The principal's
   identifier appears as *data inside a statement signed by someone else*. A verifier can always
   distinguish "signed by the principal" (`iss == principal`) from "signed by an agent claiming
   to act for the principal" (`iss == agent`, `on_behalf_of == principal`), because the outer
   signature says so.
3. **Receivers must render the distinction.** 🔵 **DESIGNED** — A conforming implementation MUST
   NOT display an agent-signed message as though it came from the principal. This is a UI
   requirement derived from a cryptographic fact, and it is the point where the whole scheme is
   most likely to be defeated in practice: a beautiful delegation chain is worthless if the
   receiving app renders it as a message from Alice.

A test any design in this space should pass: **can the receiver produce different behaviour for
"Alice said this" versus "Alice's agent said this"?** If not, the delegation model is decorative.

---

## 5. Authorization — making "what I may do" machine-readable

Authentication tells you *who* is talking. It says nothing about whether they may ask for what
they are asking for. For agents this is the load-bearing half, and it is the half no current
messaging system has at all.

### 5.1 Why capabilities, not access-control lists

An ACL lives with the resource and answers "who may touch me?" That requires the resource owner
to enumerate every principal in advance — impossible when the requester is an agent belonging to
someone you met yesterday, and worse when that agent spawns a sub-agent.

A **capability** travels with the request and answers "here is my authority, verify it yourself."
It composes, it delegates, it attenuates, and — critically for G2 — **it can be checked offline**,
because the proof is in the token, not in a database the verifier must query.

📚 **CITED** — the design space, with maturity stated honestly, because this field is full of
things described as standards that are not:

| Design | What it is | Maturity — verified 2026-08-22 |
|---|---|---|
| **Macaroons** | Bearer token; authority narrowed by appending HMAC-chained *caveats* that cannot be removed without invalidating the signature; supports third-party caveats | Google Research paper, **NDSS 2014** (Birgisson, Politz, Erlingsson, Taly, Vrable, Lentczner). An academic paper plus implementations — **never a standard** |
| **Biscuit** | Ordered signed blocks; an authority block grants, later appended blocks add Datalog checks that can only *restrict*. Attenuation needs no access to the original secret key | Eclipse Biscuit (formerly biscuit-auth); spec in-project, implementations at v3.x. **Not a standards-body spec** |
| **UCAN** | DID-addressed delegation chains: each delegation names an issuer and audience, and a chain is valid when each link's audience is the next link's issuer | Community-maintained by the UCAN Working Group — **not IETF, not W3C**. The core/delegation/invocation specs are on the **v1.0 line**; secondary sources still circulate `1.0.0-rc.1`, so check <https://github.com/ucan-wg/spec> for the exact patch level before pinning |
| **ZCAP-LD** | Linked-Data authorization capabilities, invocation + delegation proofs | **W3C Credentials Community Group draft, v0.4.0-draft.** A CG report carries no W3C standards status — "the W3C ZCAP standard" does not exist |
| **OAuth family** | `RFC 8693` Token Exchange (Standards Track, Jan 2020); `RFC 9068` JWT access tokens (Oct 2021); `RFC 8705` mTLS-bound tokens (Feb 2020); `RFC 9449` DPoP (Sept 2023) | All four are genuine IETF Standards Track RFCs. Built for client-server, not peer-to-peer delegation |
| **GNAP** | `RFC 9635` Grant Negotiation and Authorization Protocol, Standards Track, **October 2024**; companion `RFC 9767` (April 2025). A clean-sheet rethink of OAuth with richer, negotiated grants | A real, finished RFC. Its working group has since closed |

A note on UCAN's field names, because pre-1.0 tutorials are still the top search results and
they are wrong for current versions: the v1.0 line uses `iss` / `aud` / `sub` / `cmd` (a
path-like command such as `/crud/read`) / `pol` (constraints on invocation arguments) / `prf`
(proof chain, carried in the *invocation*, tagged `ucan/inv@1.0.0`, while a delegation is tagged
`ucan/dlg@1.0.0`). The `att` "attenuations" array that most blog posts show was the pre-1.0
JWT-era model and no longer exists. If a design document cites `att`, it was written against
v0.10 or copied from something that was.

🔵 **DESIGNED** — Our position: **UCAN-shaped delegation chains, VC-shaped credential
serialization.** UCAN because the chain-of-delegation model is exactly the principal→agent→
sub-agent structure of §3.2; VC/JOSE for serialization because that side actually is a W3C
Recommendation with interoperable tooling. We are not proposing a new token format, and we would
rather adopt UCAN v1.0 wholesale than fork it — the section below is our *semantics* layered on
that shape, not a competing envelope.

### 5.2 The authority envelope

Inside our own fleet we already run a machine-checkable permission gate. ✅ **RUNNING** — a JSON
Schema (`permission-gate/v0`) that every gated action must validate against, with these fields:

- `enforcement_mode`: `advisory` | `cooperative` | `mandatory`
- `requested_action`: a closed enum, from `local_file_read` up through `external_send`,
  `spend_money`, `credential_or_identity_change`, `dns_or_billing_change`, `public_release`
- `capability`: `{ namespace, verb, resource }`, where `namespace` ∈ `local`, `internal`,
  `audit`, `communication`, `finance`, `identity`, `infrastructure`, `data`, `publication`
- `risk_class`: `routine` | `user_visible` | `owner_private_read` | `persistent_service` |
  `identity_reputation` | `security_or_billing_root`
- `decision`: `allowed` | `owner_gate_required` | `blocked`
- `authority`: `{ source, valid, receipt_ref, expires_at }`
- `receipt_required`, `evidence_refs`

The honest limitation, stated because it is exactly F5 from §1.1: **this schema has never
crossed a trust boundary.** It is unsigned. It works because every participant is our own
process on our own machines. A peer's copy of it means nothing to us, and ours means nothing to
them. What follows is the signed, cross-boundary version — 🔵 **DESIGNED**, not running.

```json
{
  "typ": "authority-envelope/v0",
  "iss": "did:key:z6MkPrincipalAlice",
  "aud": "did:key:z6MkAgentAlice1",
  "sub": "did:key:z6MkPrincipalAlice",
  "nbf": "2026-08-22T00:00:00Z",
  "exp": "2026-08-23T00:00:00Z",
  "nonce": "b8f1c2...",
  "cmd": "/communication/send",
  "pol": [
    ["==", "$.namespace", "communication"],
    ["<=", "$.risk_class_rank", 2],
    ["in", "$.peer", ["did:key:z6MkAgentBob1"]],
    ["<=", "$.count_per_day", 20]
  ],
  "non_delegable": [
    "/identity/**",
    "/finance/**",
    "/infrastructure/dns/**",
    "/infrastructure/billing/**",
    "/publication/first_public_identity"
  ],
  "prf": []
}
```

Verification, as an ordered algorithm a receiver runs offline — 🔵 **DESIGNED**:

1. **Parse and schema-check.** Reject unknown `typ`. Ignore unknown *fields* (forward
   compatibility), reject unknown *semantics*.
2. **Walk the chain.** For each link in `prf`, check `link[n].aud == link[n+1].iss`. A break is
   fatal. The root's `iss` must be a principal key you have a reason to trust.
3. **Verify every signature** in the chain against the `iss` of that link.
4. **Check the time window** of *every* link against your own clock, not just the leaf. A chain
   is valid only over the intersection of its links' windows.
5. **Check attenuation monotonicity (G3).** For each link, the child's `cmd` must be a
   descendant of the parent's `cmd` in the path hierarchy, and the child's `pol` must be a
   superset of constraints — never a relaxation. **Any link that widens authority invalidates
   the whole chain**, not just that link.
6. **Check the non-delegable set (G4).** If any link's `cmd` matches any ancestor's
   `non_delegable` patterns, the chain is invalid *regardless of signatures*. `non_delegable` is
   union-inherited down the chain and can only grow.
7. **Check the request against the leaf.** The actual requested operation must satisfy `cmd`
   and every predicate in `pol`.
8. **Check replay.** `nonce` not seen before within the `exp` window (§6.4).

Step 5 and step 6 are what make G3 and G4 *structural* rather than *policy*. A verifier that
implements them correctly cannot be talked into over-granting, because there is no code path
where a signature check succeeds and an authority widening is accepted.

### 5.3 The non-delegable set — encoding a bright line

🔵 **DESIGNED** — Some things a human must do personally. In our own operating rules this is a
short, explicit list: changing identity or account roots, moving money, altering DNS or billing,
signing keys, recovery paths, and irreversible first-time public commitments. The engineering
question is how to make a *counterparty* able to check that, not just our own process.

The answer is that `non_delegable` is (a) present in the root credential, (b) union-inherited so
a child can add but never remove, and (c) checked *before* signatures are trusted to imply
authority. The practical effect: even a fully compromised agent with a perfectly valid
delegation chain cannot produce a chain that authorizes `/finance/**`, because the widening
would be caught at step 6 by a verifier that has never met it.

🟡 **CONJECTURE**, confidence ~0.6 — we think the non-delegable set is the single highest-value
field in the whole envelope, and that it will be undervalued because it does nothing in the
happy path. Its entire purpose is to fail closed in a scenario that, if the rest of the system
works, never occurs. Falsifier: an incident where a compromised delegation chain does damage in
a namespace that a static non-delegable list would not have covered — which would mean the
static-list approach is too coarse and the real answer is dynamic.

---

## 6. Messaging

### 6.1 Why not just use Signal, or email, or platform DMs

This question deserves a real answer rather than a dismissal, because each of these is better
than what most people would build.

| Transport | Genuinely good at | Why it cannot be the whole answer |
|---|---|---|
| **Signal** | Best-in-class E2E cryptography. 📚 X3DH, Double Ratchet, PQXDH and Sesame are **Signal-published specifications, not RFCs** — PQXDH keeps X3DH's four X25519 operations and adds an **ML-KEM-1024** encapsulation combined via HKDF, so an attacker must break both; and as of the 2025 **SPQR / "Triple Ratchet"** work, post-quantum protection extends across the conversation lifetime rather than only the handshake | Identity is bound to a phone number and a device — exactly the platform-shaped trust root we are removing. No machine-readable authority. No idempotency key. No third-party programmatic access. **And liveness is not part of the protocol**, which is failure F1: a dead channel looks identical to a quiet one |
| **Email / SMTP** | Federated, store-and-forward, offline-tolerant, nobody owns the namespace. The strongest existing *transport* candidate | Confidentiality is opportunistic hop-by-hop TLS, not end-to-end. Sender authentication is domain-level (SPF/DKIM/DMARC), not principal-level. No idempotency, trivial replay, no receipts beyond an MDN nobody honours |
| **Platform DMs** | Reachability. The people you want to talk to are already there | The platform is the IdP, the router, and the observer. This is precisely the dependency being removed |
| **Matrix + MLS** | Closest architectural fit. 📚 **MLS is `RFC 9420`, IETF Standards Track, July 2023**, with the architecture document at **`RFC 9750`, Informational, 2025**. Real group E2EE with efficient membership changes | Identity is still typically homeserver-bound. 📚 The cross-provider interoperability work, **IETF MIMI**, is active but **entirely at Internet-Draft stage — `draft-ietf-mimi-arch`, `-protocol`, `-content`, `-room-policy`; no RFCs yet** |

🔵 **DESIGNED** — the resolution is that **none of these is a competitor; the layer described
here rides on any of them.** Identity and authority are ours; confidentiality and transport are
borrowed. Concretely: MLS for group sessions, a Noise `XX`/`IK` session for direct pairwise
links, and email or an object store as the store-and-forward plane when the peer is offline.
Reinventing any of that would be the mistake SPEC-0001's non-goals already warned against.

### 6.2 The store-and-forward envelope and its commit sequence

Agents are offline more than online — asleep, rate-limited, mid-restart, on a laptop that shut.
Asynchrony is the normal case, not the degraded one.

✅ **RUNNING** — We operate a store-and-forward packet protocol over a shared durable folder. The
commit sequence is the part that matters, and it is ordered the way it is because of failure F2:

1. Write **artifacts** first, under immutable unique names.
2. Compute and record each artifact's **SHA-256**.
3. Write the **envelope** as `<message_id>.json`.
4. Write **`<message_id>.ready`** last. Only now is the packet eligible for processing.
5. Receiver validates schema + every hash, and **persists to its own durable queue** before
   writing an `accepted` receipt.
6. Receiver later writes **exactly one** terminal receipt.

The `.ready` marker exists because a shared folder has no atomic multi-file write. Without it a
receiver can observe an envelope referencing an artifact that is still uploading. This is the
generic "commit record written last" pattern, and it is the difference between a protocol and a
directory.

**The invariant that is easy to state and constantly violated** — ✅ **RUNNING**, learned from
failure F2: *a storage notification, a sync event, a webhook, or a file appearing is **not**
proof of delivery. It is only permission to go and look.* Delivery is proved by the receiver
reconciling against its own durable state and emitting a receipt. Any protocol whose "delivered"
status is derived from the transport's own signal has an unfalsifiable delivery claim, which is
to say no delivery claim at all.

Sender writes only into its own outbox; receiver writes only receipts and results; envelopes and
artifacts are append-only and never edited or moved. Invalid, oversized, or hash-mismatched
packets go to a dead-letter path **with a repair receipt** — they are never silently dropped and
never executed.

🔵 **DESIGNED** — the cross-trust-boundary version adds three things to the envelope above:
a `sig` over the canonicalized envelope by the sending agent's key, the §5.2 `authority` envelope,
and `enc` metadata when the body and artifacts are sealed to the recipient rather than merely
placed in a shared location. The relay is assumed hostile (A3): it sees sizes, timings, and
recipients, and must see nothing else.

### 6.3 Idempotency and replay protection

✅ **RUNNING** for dedupe; 🔵 **DESIGNED** for the signed anti-replay layer.

- **Idempotency by `message_id`.** Every write in the pipeline is idempotent by `message_id`;
  processing the same envelope twice converges to one terminal receipt. 📚 The HTTP analogue
  is being standardized as
  [`draft-ietf-httpapi-idempotency-key-header`](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
  — at `-07` and **still an Internet-Draft, not an RFC**; useful as prior art, not yet citable
  as a standard.
- **Replay window.** `nonce` + `created_at`, with receivers rejecting anything outside a bounded
  clock skew and remembering seen nonces for at least that window. Bounded memory, because the
  window is bounded.
- **Reconciliation, not event-trust.** On restart, reconnect, cursor loss, or watcher error, the
  receiver **replays from its last durable cursor and additionally scans for envelopes lacking a
  terminal receipt.** Watcher events only *trigger* a reconciliation scan; they are never the
  source of truth. This is F1 and F2's shared fix: the system's picture of what was delivered is
  reconstructible from durable state alone.

### 6.4 Encryption choices

🔵 **DESIGNED** — three options, and the choice is genuinely situational:

| Option | When it fits | Cost |
|---|---|---|
| **Sealed per-message (HPKE)** | Fire-and-forget store-and-forward to a recipient who may be offline for days. No session state. | No forward secrecy across messages unless you rotate recipient keys |
| **Pairwise ratchet (Double Ratchet)** | Long-lived two-party links with strong forward secrecy and post-compromise security | Session state both sides must persist and resynchronize |
| **Group (MLS)** | Three or more agents, changing membership | Real complexity; needs a delivery service for ordering |

📚 **CITED**, and this is the single most mis-cited fact in the set:
[HPKE is **`RFC 9180`, Informational**](https://www.rfc-editor.org/info/rfc9180/), a product of
the IRTF's Crypto Forum Research Group (February 2022) — **not IETF Standards Track**, despite
being load-bearing under TLS Encrypted Client Hello, MLS, and Oblivious HTTP. "Informational"
here reflects the stream it came from, not its quality; but a design document that calls it "an
IETF standard" is wrong on a checkable fact.

On post-quantum: 📚 NIST finalized **FIPS 203 (ML-KEM)**, **FIPS 204 (ML-DSA)** and **FIPS 205
(SLH-DSA)** on **13 August 2024**, effective the following day. Hybrid classical+PQ key exchange
is on by default in the major browsers and CDNs. 🔵 **DESIGNED** — our position is hybrid
X25519 + ML-KEM for key establishment, and Ed25519 signatures for now, because signature
harvest-now-decrypt-later is not a threat the way key-exchange harvesting is: a signature that
becomes forgeable in 2040 does not retroactively expose a 2026 conversation, whereas a recorded
key exchange does. We deliberately cite no specific RFC number for the TLS hybrid groups; the
number we could find was not independently confirmable, and a wrong RFC number is worse than
none.

### 6.5 Coordination across a trust boundary — the part we got wrong

This is the most useful thing in this document, because it is a correction to our own shipped
design rather than a proposal.

✅ **RUNNING** — We operate a leaderless work-claim primitive to stop failure F3 (duplicate
irreversible actions). A `work_key` is a normalized intent string — `send-email:<recipient>:<topic>`,
`git-push:<repo>:<branch>`, `deploy:<service>`, `spend:<vendor>`. Two sessions forming the same
intent normalize to the same key and therefore collide on the same record. Acquisition is
compare-and-set: write the claim, immediately re-read all live claims for that key, and if
another live holder exists, the **lowest session id wins that key only** and the loser releases
and yields. Leases carry a **600-second TTL** so a crashed holder cannot wedge a key, plus
`heartbeat_at` for renewal. The gate **fails closed** when the registry is unreachable, and
**fails open** — never gating — for anything reversible or internal, because a bug in a safety
gate must not brick the system it protects. A privacy refinement learned the hard way: the
cleartext `work_key` embeds recipients and identifiers, so **only a salted SHA-256 prefix is
written to the shared registry**; collision semantics are unchanged because equal keys hash
equal.

**And that design is not sound across a trust boundary.** Stating this plainly:

1. **"Lowest session id wins" is trivially gameable.** Inside a fleet of cooperating processes
   it is a fine tiebreak. Between mutually distrusting agents it is an invitation: name yourself
   `0000` and win every contested key forever. Any tiebreak an adversary can choose their own
   input to is not a tiebreak.
2. **Unsigned claims mean anyone can claim anything.** This is F4 at the coordination layer.
   Cross-boundary claims must be signed by the claiming agent and carry an authority envelope
   showing the claimant may perform the underlying action at all.
3. **TTL expiry needs a shared clock nobody controls.** Within a fleet, clock skew is a nuisance.
   Across a boundary it is an attack surface: an adversary who convinces you their lease expired
   gets you to act while they still hold it.
4. **A lease alone does not prevent a stale holder from acting.** 📚 The canonical treatment is
   Martin Kleppmann's
   ["How to do distributed locking"](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)
   (8 February 2016) — a blog post, not a paper, and the origin of "fencing token" as it is
   commonly used. The mechanism: each lease grant carries a monotonically increasing token, and
   **the protected resource rejects any operation carrying a token lower than the highest it has
   already seen.** The crucial and widely-missed condition is the second half: *the resource
   itself must check.* A fencing token that only the clients validate provides nothing, because
   the whole scenario it addresses is a client that was paused past its lease and does not know
   it. Our current implementation has leases and heartbeats and **no fencing token**, which
   means a holder that stalls past TTL and wakes up can still act. Inside a cooperating fleet
   that is a tolerable risk; across a trust boundary it is not.

🟡 **CONJECTURE**, confidence ~0.75 — **cross-boundary mutual exclusion over an irreversible
external action cannot be solved by the two agents alone.** Either (a) the resource being acted
upon is itself the arbiter and enforces a fencing token — the only construction we believe is
actually sound — or (b) both parties agree on a sequencer, which is a third party and therefore
a partial return of the thing we removed, or (c) you give up on mutual exclusion and make the
effect idempotent at the resource, which is often the right engineering answer and is not
mutual exclusion at all.

Note what (a) and (c) have in common: **the guarantee lives at the resource, not in the
protocol between the agents.** We currently believe this is a genuine impossibility rather than
a gap in our design, and would like to be shown wrong. Falsifier: a construction giving
cross-boundary exactly-once external effect with no trusted third party and no cooperation from
the resource.

---

## 7. Receipts — why one is not enough

### 7.1 The two-phase argument

A single receipt cannot do the job, in either direction:

- **Post-action only** ("I sent the email at 10:04") proves an action occurred. It cannot prove
  authorization existed *beforehand*, because it was written afterwards by the same party, and
  nothing distinguishes a legitimate action from one back-justified after the fact.
- **Pre-action only** ("I am about to send this email, under this authority") proves
  authorization was claimed. It cannot prove what actually happened — whether it succeeded,
  what the far side returned, or whether the action matched the declaration.

You need both, hash-linked. 🔵 **DESIGNED**:

```json
{
  "typ": "intent-receipt/v0",
  "receipt_id": "irc_01J...",
  "created_at": "2026-08-22T10:03:58Z",
  "actor": "did:key:z6MkAgentAlice1",
  "on_behalf_of": "did:key:z6MkPrincipalAlice",
  "action": "communication/send",
  "target": "did:key:z6MkAgentBob1",
  "artifact_hash": "sha256:9f2b...",
  "authority_ref": "sha256:1c77...",
  "self_check": {
    "private_identifiers": false,
    "financial_values": false,
    "new_public_identity": false,
    "target_in_cleared_set": true,
    "reversible_within_1h": true
  },
  "work_claim": "sha256:44ab...",
  "sig": "..."
}
```

```json
{
  "typ": "execution-receipt/v0",
  "receipt_id": "erc_01J...",
  "intent_ref": "irc_01J...",
  "created_at": "2026-08-22T10:04:07Z",
  "actor": "did:key:z6MkAgentAlice1",
  "status": "succeeded",
  "observed": {
    "transport": "smtp",
    "remote_status": "250 2.0.0 Ok",
    "artifact_hash": "sha256:9f2b..."
  },
  "prediction_error": {
    "expected": ["accepted-immediately"],
    "observed": ["accepted-immediately"],
    "surprise": "none"
  },
  "sig": "..."
}
```

Two details carry most of the weight:

- **`artifact_hash` appears in both and must match.** This is what makes the pair checkable
  rather than merely present: the thing declared is provably the thing shipped.
- ⚠️ **The intent receipt must be durably readable by the counterparty *before* the action.**
  A locally-written intent receipt is worth nothing — the actor can write it at any time and
  claim any timestamp. Publishing it to the shared plane before acting is the entire mechanism.
  This is the honest weak point of every "receipts" story, ours included: **without a
  third-party timestamp, an intent receipt's ordering rests on the counterparty having actually
  read it.** A transparency log or an RFC 3161-style timestamp would close this; we have not
  built either.

✅ **RUNNING** — We write pre-action receipts carrying `artifact_hash` + target surface + a
mechanical content self-check before every irreversible publish, and post-action kernel receipts
with a `status` from `succeeded` / `blocked` / `failed` / `owner_gate_required` / `superseded` /
`audit_only`, plus a `prediction_error` block recording expected vs. observed and the lesson.
🔵 **DESIGNED** — the signed, counterparty-readable, hash-linked pair above; today the two
halves exist but are not cryptographically linked into a verifiable pair.

The `prediction_error` field is not security machinery and is there deliberately: an execution
receipt that records only success teaches nothing. Recording what was expected next to what
occurred makes the receipt log a learning surface as well as an audit surface.

### 7.2 Terminal states

✅ **RUNNING** — Every inbound packet converges to **exactly one** terminal state:
`handled`, `delegated`, `escalated`, `owner_gate_required`, or `blocked_with_repair_plan`
(after an initial non-terminal `accepted`). Two properties matter: `owner_gate_required` is a
first-class *protocol* outcome rather than an error — "my human must decide this" is a normal
answer an agent gives another agent — and `blocked_with_repair_plan` must carry a cause and a
next step, so a failure is actionable by the sender rather than a dead end.

### 7.3 Auditability without a global log

🔵 **DESIGNED** — Each party keeps an append-only, hash-chained local receipt log; each entry
includes the hash of the previous entry, so the holder cannot rewrite history without changing
every subsequent hash. Periodically, parties exchange signed *checkpoints* — "at 10:00 my log
head was `sha256:…`". Two parties who have exchanged checkpoints can each detect if the other
later presents a divergent history.

This gives **pairwise** tamper-evidence, not global consistency, and it is not the same
guarantee a transparency log provides. 📚 The mature comparison: Sigstore's **Rekor** append-only
signature log (v2 reached GA in 2025 on a tile-backed design) and the key-transparency systems
now genuinely deployed — **WhatsApp (April 2023)**, **Apple iMessage Contact Key Verification
(early 2024)**, **Meta Messenger (November 2025)**, and **Signal's Automatic Key Verification
(11 August 2026)**, the last built on an append-only Merkle-tree log with independent audits.
Worth noting for anyone designing here: **there is still no finished IETF key-transparency
RFC** — the work is pre-standardization, and every deployment above is a bespoke Merkle-tree
system. CONIKS (2015) is the foundational academic design these descend from; it is not itself
a running system today.

---

## 8. End-to-end walkthrough

🔵 **DESIGNED** — Alice's agent asks Bob's agent to do something irreversible, with no platform
in the path. Every step is checkable.

**Setup (once per relationship).** Alice and Bob's agents complete a Noise `XX` handshake and
pin each other's static keys; they compare fingerprints out of band, upgrading TOFU to
authenticated. Alice's principal key signs a delegation to her agent (§5.2). Bob's principal
does the same. Neither principal key is on either machine.

**Sending.**

1. Alice's agent forms the intent and normalizes a `work_key`; it acquires a signed lease so a
   second session of Alice's cannot duplicate the request (§6.5).
2. It builds the payload, hashes artifacts, and constructs the envelope (§6.2).
3. It writes an **intent receipt** (§7.1) to the shared plane — including `artifact_hash`,
   `authority_ref`, and the content self-check — **before** transmitting.
4. It seals the payload to Bob's agent key and writes artifacts, envelope, then `.ready`.

**Receiving — Bob's agent, offline-only checks.**

5. The `.ready` marker triggers a **reconciliation scan** — not direct processing (§6.2).
6. Validate envelope schema; verify every artifact's SHA-256. Mismatch → dead-letter + repair
   receipt.
7. Verify the envelope signature against Alice's agent's pinned key.
8. Verify the authority chain by the eight-step algorithm in §5.2 — chain linkage, signatures,
   time-window intersection, attenuation monotonicity, non-delegable set, request match, nonce.
9. Confirm `on_behalf_of` and **render it as "Alice's agent", never as "Alice"** (§4.3).
10. Dedupe by `message_id`; persist durably; write `accepted`.
11. Apply Bob's *own* local policy. A valid authority chain establishes that Alice authorized
    her agent — it says nothing about whether Bob consents. If Bob's policy requires him
    personally, the terminal state is `owner_gate_required`, which is a normal answer.
12. Act, then write **exactly one** terminal receipt, and an **execution receipt** hash-linked
    to Alice's intent receipt.

Note step 11. **Authority is not consent.** A verified chain answers "may this agent ask?" It
does not answer "will I comply?" Systems that conflate the two build a protocol where a
sufficiently well-signed request is self-executing, which is a worse security posture than
having no delegation at all.

---

## 9. What we have not solved

Mandatory section. Without it the rest is marketing.

**9.1 Agent forking.** ⚠️ **OPEN** — §3.5. A copied agent is cryptographically the same agent.
We believe the realistic answer is detection via monotonic counters plus an append-only log, not
prevention — but two forks talking to disjoint peers remain invisible to any pairwise scheme. We
have implemented nothing here. This is the problem we would most like someone else to solve.

**9.2 Metadata.** ⚠️ **OPEN** — Content is sealed; *who talks to whom, how often, how much, and
when* is not. A store-and-forward relay (A3) sees all of it. Mixnets and sealed-sender designs
exist and cost latency and complexity we have not paid. **We do not claim metadata privacy.**

**9.3 Principal key recovery.** ⚠️ **OPEN** — §3.3. If the human loses their root key, we have
no answer better than a second authenticator. Social recovery and M-of-N guardians are candidates
we have not built. A design that assumes humans never lose hardware is not deployable.

**9.4 Revocation propagation to offline peers.** ⚠️ **OPEN** — Fundamental, not incidental:
revocation is news, and offline verifiers get no news. Short expiry converts revocation into
expiry, which works, at the cost of renewal traffic and a residual window we have not closed and
do not think can be closed while keeping G2.

**9.5 Cross-boundary exactly-once.** ⚠️ **OPEN** — §6.5. We suspect it is impossible without
either resource cooperation or a trusted sequencer, and we state that as a conjecture we would
like refuted rather than a theorem.

**9.6 Compromised host.** ⚠️ **OPEN** — §3.4. Hardware-bound keys work and break migration.
We have not chosen.

**9.7 Trust bootstrapping at scale.** ⚠️ **OPEN** — Everything here works beautifully for `n=2`
where a fingerprint can be compared out of band. We have no story for an agent needing to
authenticate a stranger's agent with no prior contact, and we are sceptical of designs that
claim one without reintroducing a registry.

**9.8 Authority expressiveness vs. verifiability.** ⚠️ **OPEN** — The `pol` predicate language
in §5.2 is deliberately tiny. Real authority is contextual in ways a predicate list captures
badly ("may spend up to X *unless the situation is unusual*"). Richer languages become harder to
verify and easier to get wrong. We do not know where the right point on that curve is.

**9.9 The rendering problem.** ⚠️ **OPEN** — §4.3 requires implementations to visually
distinguish "Alice" from "Alice's agent". We can specify it and cannot enforce it, and we expect
this to be where real deployments break first — long before anyone attacks the cryptography.

**9.10 We have not been attacked.** ⚠️ **OPEN** — Nothing in the 🔵 **DESIGNED** portions of this
document has faced an adversary. Designs that have not been attacked should be assumed broken in
ways their authors cannot see. Treat every 🔵 as an invitation.

---

## 10. Relationship to existing standards

Everything below was verified against its primary source on **2026-08-22**, with maturity level
stated. The pattern worth internalizing: **several of the most-cited "standards" in agent
identity are not standards.**

| We use / relate to | Exact status, verified | Role here |
|---|---|---|
| DIDs v1.0 | **W3C Recommendation**, 19 July 2022 (v1.1 is a CR Snapshot, 5 Mar 2026) | Identifier model |
| `did:key`, `did:web` | **W3C Credentials Community Group drafts** — `did:key` v0.9; `did:web` self-labelled `"unofficial"`. Not Recommendations | Wire identifier (`did:key`) |
| Verifiable Credentials 2.0 | **W3C Recommendation**, 15 May 2025 (v1.1 also a valid REC, 3 Mar 2022) | Credential shape |
| SD-JWT | **RFC 9901**, Standards Track, Nov 2025 | Selective disclosure |
| SD-JWT VC | **Internet-Draft** `draft-ietf-oauth-sd-jwt-vc-18` — *not* an RFC | Credential profile (watch) |
| WebAuthn | **Level 2 is a W3C Recommendation**; Level 3 is a **CR Snapshot**, 26 May 2026 | Principal root key |
| SPIFFE / SPIRE | CNCF **graduated** (Sept 2022) spec set + runtime; not IETF/W3C | Host / workload identity |
| X.509 / PKIX | **RFC 5280**, Standards Track, May 2008 | Alternative encoding |
| EdDSA / Ed25519 | **RFC 8032**, IRTF CFRG, **Informational**, Jan 2017 | Signatures |
| JOSE / COSE | **RFC 7515** (JWS), **RFC 7519** (JWT), Standards Track 2015; **RFC 9052** COSE Standards Track / STD 96 + **RFC 9053** Informational, Aug 2022 | Serialization |
| UCAN | Community-maintained (UCAN WG); **v1.0 line** — verify patch level at `ucan-wg/spec` | Delegation chain model |
| ZCAP-LD | **W3C CCG draft v0.4.0** — not a Recommendation | Compared, not adopted |
| Macaroons / Biscuit | NDSS **2014** paper / Eclipse Biscuit project spec — neither is a standard | Attenuation prior art |
| OAuth 2.0 family | **RFC 8693**, **RFC 9068**, **RFC 8705**, **RFC 9449** — all Standards Track | Compared; client-server shaped |
| GNAP | **RFC 9635**, Standards Track, Oct 2024 (+ **RFC 9767**, Apr 2025) | Compared |
| Noise Framework | **Revision 34**, 11 July 2018 — independent spec, not an RFC | Pairwise handshake |
| MLS | **RFC 9420**, Standards Track, July 2023; architecture **RFC 9750**, Informational, 2025 | Group sessions |
| MIMI | IETF WG, **Internet-Drafts only** — no RFCs | Watch |
| Signal X3DH / Double Ratchet / PQXDH / Sesame / SPQR | **Signal-published specs, none are RFCs.** PQXDH adds ML-KEM-1024 to X3DH; SPQR ("Triple Ratchet", 2025) extends PQ protection beyond the handshake | Pairwise ratchet |
| HPKE | **RFC 9180, Informational** (IRTF CFRG), Feb 2022 — *not* Standards Track | Sealed messages |
| ML-KEM / ML-DSA / SLH-DSA | **FIPS 203 / 204 / 205**, NIST, finalized 13 Aug 2024 | PQ hybrid |
| Certificate Transparency | **RFC 6962** and **RFC 9162** — both IETF **Experimental** | Revocation-visibility model |
| Idempotency-Key header | **Internet-Draft** `draft-ietf-httpapi-idempotency-key-header-07` — not an RFC | Dedupe prior art |
| Fencing tokens | Kleppmann, "How to do distributed locking", 8 Feb 2016 (blog post) | Coordination |

**Emerging agent-specific work, with honest maturity labels** — as of 2026-08-22, **nothing in
this space is a finished IETF RFC or a ratified W3C/OpenID standard**:

- **IETF WIMSE** (Workload Identity in Multi-System Environments) — a genuinely chartered IETF
  working group (chartered 2024), actively drafting; Internet-Drafts only. The most
  standards-track-credible work in the area.
- **`draft-ietf-oauth-identity-assertion-authz-grant`** — WG-adopted in the IETF OAuth WG, still
  pre-RFC. Increasingly cited for agent scenarios though not agent-specific by name.
- **A2A (Agent2Agent)** — originated at Google, now hosted by the **Linux Foundation**; reached
  v1.0 in 2026. Real adoption, **foundation-governed, not IETF/W3C**.
- **Model Context Protocol authorization** — an Anthropic-originated open spec; its authorization
  layer builds on OAuth 2.1 and existing RFCs rather than minting new crypto. Project-governed.
- **`draft-klrc-aiagent-auth`**, **`draft-oauth-ai-agents-on-behalf-of-user`** — individual
  Internet-Drafts, not WG-adopted.
- **OpenID Foundation** — the AI Identity Management group is a **Community Group** (pre-WG);
  the AuthZEN WG has approved actual Working Group Drafts, including an MCP tool-authorization
  profile. WG Drafts, not final specs.
- **"Agent passport" / "Agent ID"** products — **vendor terminology**, not standards, sometimes
  built atop the drafts above. Worth using; not worth citing as a standard.

The practical implication for anyone building now: **the standards are not ready, and the
correct response is to compose finished general-purpose standards (Ed25519, JOSE/COSE, VC 2.0,
Noise, MLS, HPKE) rather than to wait, or to adopt a vendor's agent-identity product as though
it were an interoperability layer.**

---

## 11. Falsifiers

Each goal from §2.3, with what would show it failed:

| Goal | Falsifier |
|---|---|
| G1 Mutual auth, no IdP | Any handshake path that requires a third party to be reachable at handshake time |
| G2 Offline verifiability | Any credential a receiver cannot fully validate while airgapped, given the message and the principal's public key |
| G3 Attenuation-only | A chain that passes §5.2 verification and grants more than its root |
| G4 Non-delegable core | A chain that passes verification and authorizes anything under a `non_delegable` prefix |
| G5 Exactly-once | A partition/retry sequence producing two external effects with all gates enabled — or, more likely, a proof that §6.5's conjecture is right and G5 is unachievable without resource cooperation, in which case G5 should be *withdrawn* rather than weakened |
| G6 No unauditable action | Any irreversible action whose intent receipt was not counterparty-readable before it happened |

If you break one of these, that is the most useful contribution anyone can make to this
document, and it will be recorded here rather than quietly removed.

---

## 12. Related work in this organization

Other specs in this repository:
[SPEC-0001](SPEC-0001-inbox-addressing-receipts.md) (inbox, addressing, receipts) and
[SPEC-0002](SPEC-0002-false-negative-monitoring.md) (false-negative monitoring).
The coordination primitives this document critiques in §6.5 are specified in
[fleet-coordination-protocol](https://github.com/starshard-ai/fleet-coordination-protocol),
with a runnable reference at
[agent-continuity-demo](https://github.com/starshard-ai/agent-continuity-demo).

Further work on agent-safety open problems is in progress elsewhere in this organization and
will be linked here once published; no URL is given yet rather than risk a dead link.

---

## 13. Status, and how to disagree

This is **v0 draft**. Field names will change. The ✅ **RUNNING** claims describe code we depend
on daily; the 🔵 **DESIGNED** claims have never met an adversary; the ⚠️ **OPEN** items are
genuinely open, including one (§3.5, agent forking) we consider unsolved by anyone.

The most valuable response is an attack, a falsifier from §11, or a correction to §10 — the
standards landscape moves and a maturity label that was right on 2026-08-22 may be wrong when
you read this. Open an issue.

**License:** Apache-2.0, same as the rest of this repository.
