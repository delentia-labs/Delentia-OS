terraform {
  required_version = ">= 1.6.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

# ── Variables ─────────────────────────────────────────────────────────────────

variable "postgres_password" {
  description = "PostgreSQL password for the delentia user"
  type        = string
  sensitive   = true
}

variable "delentia_api_key" {
  description = "Delentia Gateway API key"
  type        = string
  sensitive   = true
}

variable "delentia_version" {
  description = "Delentia service image tag"
  type        = string
  default     = "2.0"
}

# ── Network ────────────────────────────────────────────────────────────────────

resource "docker_network" "delentia_net" {
  name   = "delentia-net"
  driver = "bridge"
}

# ── Volumes ────────────────────────────────────────────────────────────────────

resource "docker_volume" "pg_data" {
  name = "delentia-pg-data"
}

resource "docker_volume" "qdrant_data" {
  name = "delentia-qdrant-data"
}

# ── PostgreSQL ────────────────────────────────────────────────────────────────

resource "docker_container" "postgres" {
  name  = "delentia-postgres"
  image = "postgres:16-alpine"
  restart = "unless-stopped"

  env = [
    "POSTGRES_USER=delentia",
    "POSTGRES_PASSWORD=${var.postgres_password}",
    "POSTGRES_DB=delentia",
  ]

  volumes {
    volume_name    = docker_volume.pg_data.name
    container_path = "/var/lib/postgresql/data"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U delentia -d delentia"]
    interval = "10s"
    timeout  = "5s"
    retries  = 5
  }
}

# ── Qdrant ─────────────────────────────────────────────────────────────────────

resource "docker_container" "qdrant" {
  name    = "delentia-qdrant"
  image   = "qdrant/qdrant:latest"
  restart = "unless-stopped"

  volumes {
    volume_name    = docker_volume.qdrant_data.name
    container_path = "/qdrant/storage"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
    aliases = ["vector-search"]
  }
}

# ── Gateway API ────────────────────────────────────────────────────────────────

resource "docker_container" "gateway_api" {
  name    = "delentia-gateway"
  image   = "delentia/gateway-api:${var.delentia_version}"
  restart = "unless-stopped"

  env = [
    "DELENTIA_ENV=production",
    "POSTGRES_URL=postgresql://delentia:${var.postgres_password}@postgres:5432/delentia",
    "DELENTIA_API_KEY=${var.delentia_api_key}",
  ]

  ports {
    internal = 8000
    external = 8000
    ip       = "0.0.0.0"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
    aliases = ["gateway-api"]
  }

  depends_on = [docker_container.postgres]
}

# ── Intent Loop ────────────────────────────────────────────────────────────────

resource "docker_container" "intent_loop" {
  name    = "delentia-intent-loop"
  image   = "delentia/intent-loop:${var.delentia_version}"
  restart = "unless-stopped"

  env = [
    "DELENTIA_ENV=production",
    "POSTGRES_URL=postgresql://delentia:${var.postgres_password}@postgres:5432/delentia",
  ]

  ports {
    internal = 8001
    external = 8001
    ip       = "127.0.0.1"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
    aliases = ["intent-loop"]
  }

  depends_on = [docker_container.postgres]
}

# ── Analysearch ────────────────────────────────────────────────────────────────

resource "docker_container" "analysearch" {
  name    = "delentia-analysearch"
  image   = "delentia/analysearch-intent:${var.delentia_version}"
  restart = "unless-stopped"

  env = [
    "DELENTIA_ENV=production",
    "QDRANT_URL=http://vector-search:6333",
  ]

  ports {
    internal = 8002
    external = 8002
    ip       = "127.0.0.1"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
    aliases = ["analysearch-intent"]
  }

  depends_on = [docker_container.qdrant]
}

# ── Crystallizer ──────────────────────────────────────────────────────────────

resource "docker_container" "crystallizer" {
  name    = "delentia-crystallizer"
  image   = "delentia/crystallizer:${var.delentia_version}"
  restart = "unless-stopped"

  env = [
    "DELENTIA_ENV=production",
    "POSTGRES_URL=postgresql://delentia:${var.postgres_password}@postgres:5432/delentia",
  ]

  ports {
    internal = 8004
    external = 8004
    ip       = "127.0.0.1"
  }

  networks_advanced {
    name = docker_network.delentia_net.name
    aliases = ["crystallizer"]
  }

  depends_on = [docker_container.postgres]
}
