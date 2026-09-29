#!/usr/bin/env bash
# install.sh — Delentia OS Community One-Line Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.sh | bash
# Supports: Ubuntu 22.04+, Debian 12+, macOS 13+

set -euo pipefail

DELENTIA_VERSION="2.0"
MIN_DOCKER_VERSION=24
MIN_PYTHON_VERSION="3.10"
MIN_NODE_VERSION=20
INSTALL_DIR="${DELENTIA_HOME:-$HOME/.delentia}"
GATEWAY_URL="http://localhost:8000"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Banner ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ██████╗ ███████╗██╗     ███████╗███╗   ██╗████████╗██╗ █████╗ "
echo "  ██╔══██╗██╔════╝██║     ██╔════╝████╗  ██║╚══██╔══╝██║██╔══██╗"
echo "  ██║  ██║█████╗  ██║     █████╗  ██╔██╗ ██║   ██║   ██║███████║"
echo "  ██║  ██║██╔══╝  ██║     ██╔══╝  ██║╚██╗██║   ██║   ██║██╔══██║"
echo "  ██████╔╝███████╗███████╗███████╗██║ ╚████║   ██║   ██║██║  ██║"
echo "  ╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═╝"
echo ""
echo "  Delentia OS v${DELENTIA_VERSION} — Community Install"
echo ""

# ── Prerequisite Checks ────────────────────────────────────────────────────────
info "Checking prerequisites..."

# Docker
if ! command -v docker &>/dev/null; then
  error "Docker not found. Install Docker >= ${MIN_DOCKER_VERSION}: https://docs.docker.com/get-docker/"
fi
DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1 || echo 0)
if [[ "$DOCKER_VER" -lt "$MIN_DOCKER_VERSION" ]]; then
  error "Docker >= ${MIN_DOCKER_VERSION} required (found ${DOCKER_VER})"
fi
success "Docker ${DOCKER_VER}.x"

# Docker Compose plugin
if ! docker compose version &>/dev/null; then
  error "Docker Compose plugin not found. Install with: sudo apt-get install docker-compose-plugin"
fi
success "Docker Compose plugin"

# Python
if ! command -v python3 &>/dev/null; then
  error "Python >= ${MIN_PYTHON_VERSION} required: https://python.org"
fi
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
  error "Python >= ${MIN_PYTHON_VERSION} required (found ${PYTHON_VER})"
fi
success "Python ${PYTHON_VER}"

# Node.js
if ! command -v node &>/dev/null; then
  warn "Node.js not found (optional, required for Delentia GUI)"
else
  NODE_VER=$(node --version | sed 's/v//' | cut -d. -f1)
  if [[ "$NODE_VER" -lt "$MIN_NODE_VERSION" ]]; then
    warn "Node.js >= ${MIN_NODE_VERSION} recommended (found ${NODE_VER})"
  else
    success "Node.js ${NODE_VER}.x"
  fi
fi

# ── Install Directory ──────────────────────────────────────────────────────────
info "Creating install directory: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# ── Download docker-compose files ─────────────────────────────────────────────
REPO_BASE="https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main"

info "Downloading docker-compose.yml..."
curl -fsSL "${REPO_BASE}/docker/docker-compose.yml" -o "${INSTALL_DIR}/docker-compose.yml"

info "Downloading .env.example..."
curl -fsSL "${REPO_BASE}/docker/.env.example" -o "${INSTALL_DIR}/.env.example"

# ── Generate secrets ──────────────────────────────────────────────────────────
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  info "Generating secure credentials..."

  if command -v openssl &>/dev/null; then
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    DELENTIA_API_KEY=$(openssl rand -base64 32)
  else
    POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    DELENTIA_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  fi

  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  # Use Python for portable in-place substitution
  python3 - <<EOF
import re, pathlib
env = pathlib.Path("${INSTALL_DIR}/.env")
text = env.read_text()
text = re.sub(r'POSTGRES_PASSWORD=.*', f'POSTGRES_PASSWORD=${POSTGRES_PASSWORD}', text)
text = re.sub(r'DELENTIA_API_KEY=.*', f'DELENTIA_API_KEY=${DELENTIA_API_KEY}', text)
env.write_text(text)
EOF
  success "Credentials generated and saved to ${INSTALL_DIR}/.env"
else
  info ".env already exists, skipping credential generation"
fi

# ── Install Python SDK ─────────────────────────────────────────────────────────
info "Installing delentia-os Python SDK..."
pip3 install --quiet "delentia-os>=${DELENTIA_VERSION}" || warn "SDK install failed — continuing"

# ── Pull Images ────────────────────────────────────────────────────────────────
info "Pulling Delentia OS images (this may take a few minutes)..."
cd "${INSTALL_DIR}"
docker compose pull

# ── Start Services ─────────────────────────────────────────────────────────────
info "Starting Delentia OS services..."
docker compose up -d

# ── Health Check ───────────────────────────────────────────────────────────────
info "Waiting for services to be healthy..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until curl -sf "${GATEWAY_URL}/health" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [[ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]]; then
    error "Gateway did not become healthy after ${MAX_ATTEMPTS} attempts. Run: docker compose logs"
  fi
  sleep 3
done

# Check all ports 8000-8004
for PORT in 8000 8001 8002 8004; do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    success "Port ${PORT} healthy"
  else
    warn "Port ${PORT} did not respond (service may still be starting)"
  fi
done

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
success "Delentia OS v${DELENTIA_VERSION} installed successfully!"
echo ""
echo "  Gateway API:    ${GATEWAY_URL}"
echo "  Intent Loop:    http://localhost:8001"
echo "  Analysearch:    http://localhost:8002"
echo "  Crystallizer:   http://localhost:8004"
echo ""
echo "  API Key:        ${INSTALL_DIR}/.env"
echo "  Logs:           docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
echo "  Stop:           docker compose -f ${INSTALL_DIR}/docker-compose.yml down"
echo ""
echo "  Docs:           https://github.com/delentia-labs/delentia-infra-public"
echo ""
