#!/usr/bin/env bash
# Demo: SPEC-0002 false-negative monitoring scenario
#
# This script routes 4 messages through the monitoring router, generates
# a filtered-message digest, and scans for false-negative signals.
#
# Expected outcomes:
# - msg-01: colleague@example.com gets AI score 0.35 → standard tier → digested
# - msg-02: person@example.com is known priority contact → surfaced (no AI needed)
# - msg-03: same colleague resends similar message → also digested, but triggers FN alert on msg-01
# - msg-04: unknown sender, low AI confidence (0.40 < 0.60 threshold) → uncertainty escalation → priority instead of standard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROUTER="$REPO_DIR/reference-impl/monitor.py"
OUT="/tmp/starshard-fn-monitoring-demo"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "=== SPEC-0002 False-Negative Monitoring Demo ==="
echo ""

echo "--- 1. Route msg-01 (colleague, AI score 0.35, will be filtered) ---"
python3 "$ROUTER" route \
  --message "$SCRIPT_DIR/msg-01-filtered.json" \
  --out "$OUT"
echo ""

echo "--- 2. Route msg-02 (known priority contact, policy lookup) ---"
python3 "$ROUTER" route \
  --message "$SCRIPT_DIR/msg-02-known-priority.json" \
  --out "$OUT"
echo ""

echo "--- 3. Route msg-03 (colleague resends — similar subject) ---"
python3 "$ROUTER" route \
  --message "$SCRIPT_DIR/msg-03-resend.json" \
  --out "$OUT"
echo ""

echo "--- 4. Route msg-04 (unknown sender, LOW confidence → uncertainty escalation) ---"
python3 "$ROUTER" route \
  --message "$SCRIPT_DIR/msg-04-low-confidence.json" \
  --out "$OUT"
echo ""

echo "--- 5. Generate filtered-message digest (last 24h) ---"
python3 "$ROUTER" digest \
  --out "$OUT" \
  --period-start "2026-06-11T00:00:00Z" \
  --period-end "2026-06-12T00:00:00Z"
echo ""

echo "--- 6. Scan for false-negative signals ---"
python3 "$ROUTER" scan-fn \
  --out "$OUT" \
  --messages "$SCRIPT_DIR"
echo ""

echo "=== Output files ==="
echo "Receipts:        $OUT/receipts.jsonl"
echo "Audit events:    $OUT/audit-events.jsonl"
echo "Decision traces: $OUT/decision-traces.jsonl"
echo "Digests:         $OUT/filtered-digests.jsonl"
echo ""
echo "=== Done ==="
