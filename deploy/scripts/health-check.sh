#!/usr/bin/env bash
# health-check.sh — Verify all Delentia OS services are responding
set -euo pipefail

GATEWAY_URL="${DELENTIA_GATEWAY:-http://localhost:8000}"
SERVICES=(
  "Gateway API:8000:/health"
  "Intent Loop:8001:/health"
  "Analysearch:8002:/health"
  "Qdrant:8003:/healthz"
  "Crystallizer:8004:/health"
)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

PASS=0; FAIL=0

echo "Delentia OS Health Check"
echo "========================"

for svc in "${SERVICES[@]}"; do
  NAME=$(echo "$svc" | cut -d: -f1)
  PORT=$(echo "$svc" | cut -d: -f2)
  PATH_=$(echo "$svc" | cut -d: -f3)
  URL="http://localhost:${PORT}${PATH_}"

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$URL" || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    echo -e "  ${GREEN}✓${NC} ${NAME} (${URL})"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}✗${NC} ${NAME} (${URL}) — HTTP ${HTTP_CODE}"
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo -e "  Passed: ${GREEN}${PASS}${NC}  Failed: ${RED}${FAIL}${NC}"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${YELLOW}Tip:${NC} Run 'docker compose logs <service>' for details"
  exit 1
fi
exit 0
