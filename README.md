# Starshard Communication

An open communication substrate for personal-agent users.

The core claim is simple: the AI-agent-era replacement for closed super-app
chat is probably not another chat app. It is a user-owned layer for inboxes,
addresses, policies, receipts, and channel adapters.

This repository starts with the thinnest useful layer:

```text
message -> local identity -> local policy -> receipt -> audit
```

Memory systems, task ledgers, public/friends/private agents, and rich agent
workflows are extensions. The first protocol should work without them.

## What This Is

- A small protocol draft for inbox, addressing, policy, and receipts.
- A reference JSON shape for `MessageEnvelope` and `Receipt`.
- A tiny local reference implementation that routes one inbound message and
  writes receipts.

## What This Is Not

- Not a hosted service.
- Not a new cryptographic protocol.
- Not a chat-app clone.
- Not a platform scraper.
- Not a claim that every private message should be read by AI.

Transport security should reuse established protocols and libraries. Existing
channels such as email, webhooks, Matrix, SimpleX, ActivityPub, MCP endpoints,
or local inboxes can become adapters.

## Start Here

- [SPEC-0001](docs/SPEC-0001-inbox-addressing-receipts.md)
- [Message envelope example](examples/message-envelope.json)
- [Receipt example](examples/receipt.json)
- [Reference implementation](reference-impl/router.py)

## Run The Demo

```bash
python3 reference-impl/router.py \
  --message examples/message-envelope.json \
  --out /tmp/starshard-communication-demo
```

The demo writes:

- `receipts.jsonl`
- `audit-events.jsonl`

## Six-Month Metric

The useful metric is not stars or agreement. A real win is that a user can move
their active communication graph to non-super-app paths with a receipt loop:

```text
received -> routed -> surfaced/digested/delegated/blocked -> receipt
```

## License

Apache-2.0. See [LICENSE](LICENSE).
