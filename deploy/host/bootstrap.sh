#!/usr/bin/env bash
# First-time set-up of the host secrets and the first person's token. Run once, in this folder, after `docker compose build`.
#
#   ./bootstrap.sh alice
#
# Why a script: the keys must be created by the same unprivileged uid that will read them (audit key: 10001, the runtime; notary key: 10002,
# the notary), the notary and the runtime must share one token that neither can mint for the other, and `delentia serve` refuses to start on
# a public address until at least one person's token exists. Found by actually running the kit (Round 55): without this order the notary
# could not read its key and the runtime refused to start.
#
# Single-tenant host assumed: the notary token is readable by both containers' uids through mode 0644, so any other login on the host could
# read it. Keys are 0600 and owned by their own uid.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${IMAGE:-delentia-host:latest}"
FIRST_USER="${1:?usage: ./bootstrap.sh <first-user-name>}"
export MSYS_NO_PATHCONV=1                              # Git Bash on Windows would otherwise rewrite /out
SECRETS="$(pwd)/secrets"
if [ -e "$SECRETS/audit.pem" ] || [ -e "$SECRETS/notary.pem" ]; then
  echo "secrets/ already holds keys: not overwriting them (move them away first if you really want new ones)" >&2
  exit 1
fi
mkdir -p "$SECRETS"
chmod 777 "$SECRETS"                                   # temporary: lets uid 10001 and 10002 write; tightened at the end
docker run --rm --user 10001:10001 -v "$SECRETS:/out" "$IMAGE" delentia audit-chain keygen --out /out/audit.pem
docker run --rm --user 10002:10002 -v "$SECRETS:/out" "$IMAGE" delentia notary keygen --out /out/notary.pem
python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$SECRETS/notary_token" 2>/dev/null \
  || head -c 36 /dev/urandom | base64 | tr -d '\n=+/' > "$SECRETS/notary_token"
chmod 644 "$SECRETS/notary_token"
chmod 755 "$SECRETS"

# The first token, written into the data volume the runtime will use (HOME=/data/home inside the container).
VOLUME="${COMPOSE_PROJECT_NAME:-delentia-host}_delentia-data"
docker volume create "$VOLUME" >/dev/null
echo
echo "First person's token (shown once; only its hash is stored):"
docker run --rm --user 10001:10001 -e HOME=/data/home -e DELENTIA_HOME=/data -v "$VOLUME:/data" "$IMAGE" delentia tokens create "$FIRST_USER"
echo
echo "Next: docker compose up -d   then   docker compose exec delentia delentia host-check"
