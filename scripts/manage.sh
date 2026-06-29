#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# Hybrid RAG System — EC2 Management Script
# Usage: ./scripts/manage.sh [command]
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE="docker compose -f $PROJECT_DIR/docker-compose.yml"
MODEL=${OLLAMA_MODEL:-qwen2.5:7b}

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[RAG]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

require_root() {
  [[ $EUID -eq 0 ]] || { err "Run as root or with sudo"; exit 1; }
}

cmd_install_docker() {
  require_root
  log "Installing Docker on Ubuntu..."
  apt-get update -qq
  apt-get install -y ca-certificates curl gnupg lsb-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  usermod -aG docker ubuntu || true
  systemctl enable --now docker
  log "Docker installed ✓"
}

cmd_setup() {
  log "Setting up project..."
  cd "$PROJECT_DIR"

  # Create .env from example if not exists
  if [[ ! -f .env ]]; then
    cp .env.example .env
    # Generate random secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-me-to-a-strong-random-secret-key-in-production/$SECRET/" .env
    log ".env created with random secret key"
    warn "Review .env and set POSTGRES_PASSWORD before starting"
  else
    log ".env already exists, skipping"
  fi

  # Create data directories
  mkdir -p data/{uploads,documents,qdrant,elasticsearch,postgres,redis}
  log "Data directories created ✓"

  # Increase vm.max_map_count for Elasticsearch
  if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf 2>/dev/null; then
    echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
    sudo sysctl -w vm.max_map_count=262144
    log "vm.max_map_count set for Elasticsearch ✓"
  fi
}

cmd_build() {
  log "Building Docker images..."
  cd "$PROJECT_DIR"
  $COMPOSE build --no-cache
  log "Build complete ✓"
}

cmd_start() {
  log "Starting all services..."
  cd "$PROJECT_DIR"
  $COMPOSE up -d
  log "Services starting. Run './scripts/manage.sh status' to check."
  log "Waiting 30s for services to become healthy..."
  sleep 30
  cmd_pull_model
}

cmd_stop() {
  log "Stopping all services..."
  cd "$PROJECT_DIR"
  $COMPOSE down
  log "Services stopped ✓"
}

cmd_restart() {
  cmd_stop
  sleep 5
  cmd_start
}

cmd_pull_model() {
  log "Pulling LLM model: $MODEL (this may take several minutes on first run)..."
  docker exec rag-ollama ollama pull "$MODEL" || {
    warn "Model pull failed or Ollama not ready yet. Retry with: ./scripts/manage.sh pull-model"
  }
  log "Model ready ✓"
}

cmd_logs() {
  SERVICE="${2:-}"
  cd "$PROJECT_DIR"
  if [[ -n "$SERVICE" ]]; then
    $COMPOSE logs -f "$SERVICE"
  else
    $COMPOSE logs -f
  fi
}

cmd_status() {
  cd "$PROJECT_DIR"
  log "=== Container Status ==="
  $COMPOSE ps
  echo ""
  log "=== Backend Health ==="
  curl -sf http://localhost:8000/health | python3 -m json.tool 2>/dev/null || warn "Backend not responding"
  echo ""
  log "=== Ollama Models ==="
  curl -sf http://localhost:11434/api/tags | python3 -m json.tool 2>/dev/null || warn "Ollama not responding"
}

cmd_reset() {
  warn "This will DESTROY all data. Are you sure? (type 'yes' to confirm)"
  read -r confirm
  [[ "$confirm" == "yes" ]] || { log "Aborted."; exit 0; }
  cd "$PROJECT_DIR"
  $COMPOSE down -v
  rm -rf data/{documents,qdrant,elasticsearch,postgres,redis}
  mkdir -p data/{documents,qdrant,elasticsearch,postgres,redis}
  log "Reset complete ✓"
}

cmd_backup() {
  BACKUP_DIR="$PROJECT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP_DIR"
  log "Backing up PostgreSQL..."
  docker exec rag-postgres pg_dump -U raguser ragdb > "$BACKUP_DIR/postgres.sql"
  log "Backup saved to $BACKUP_DIR"
}

cmd_help() {
  echo "Hybrid RAG System — Management Script"
  echo ""
  echo "Usage: $0 <command>"
  echo ""
  echo "Commands:"
  echo "  install-docker   Install Docker on Ubuntu EC2"
  echo "  setup            Initialize .env and data directories"
  echo "  build            Build Docker images"
  echo "  start            Start all services + pull LLM model"
  echo "  stop             Stop all services"
  echo "  restart          Restart all services"
  echo "  pull-model       Pull/re-pull the Ollama LLM model"
  echo "  logs [service]   Tail logs (optional: service name)"
  echo "  status           Show container and service status"
  echo "  backup           Backup PostgreSQL data"
  echo "  reset            Destroy all data and volumes (DESTRUCTIVE)"
  echo "  help             Show this help"
}

COMMAND="${1:-help}"
case "$COMMAND" in
  install-docker) cmd_install_docker ;;
  setup)          cmd_setup ;;
  build)          cmd_build ;;
  start)          cmd_start ;;
  stop)           cmd_stop ;;
  restart)        cmd_restart ;;
  pull-model)     cmd_pull_model ;;
  logs)           cmd_logs "$@" ;;
  status)         cmd_status ;;
  backup)         cmd_backup ;;
  reset)          cmd_reset ;;
  help|*)         cmd_help ;;
esac
