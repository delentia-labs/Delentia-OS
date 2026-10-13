#!/usr/bin/env bash
# First-login setup for a fresh Ubuntu 22.04/24.04 server (written for Oracle Always Free Ampere A1, aarch64, but works on x86 too).
# Idempotent: safe to run twice. Run it as the normal login user (ubuntu); it uses sudo. Read it first.
#   curl -fsSLO https://raw.githubusercontent.com/delentia-labs/Delentia-OS/main/deploy/host/ubuntu_arm_setup.sh && less ubuntu_arm_setup.sh && bash ubuntu_arm_setup.sh
# It changes: packages (docker, compose, git, unattended security updates), the docker group of this user, a 2 GB swap file if there is none.
# It does NOT open any port, does NOT touch SSH settings, and does NOT create any secret.
set -euo pipefail

echo "machine: $(uname -m)   os: $(. /etc/os-release && echo "$PRETTY_NAME")   memory: $(free -m | awk '/Mem:/{print $2}') MB"
if [ "$(id -u)" -eq 0 ]; then echo "run this as the normal login user, not root"; exit 1; fi

sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git unattended-upgrades ca-certificates curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades || true

if ! swapon --show | grep -q .; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo
echo "docker:  $(sudo docker --version)"
echo "compose: $(sudo docker compose version)"
sudo docker run --rm hello-world >/dev/null && echo "docker runs containers for this architecture ($(uname -m)): OK"
echo
echo "Log out and in again (so the docker group applies), then follow deploy/host/HOST_RUNBOOK.md section 2. For a trial without a domain use docker-compose.private.yml."
