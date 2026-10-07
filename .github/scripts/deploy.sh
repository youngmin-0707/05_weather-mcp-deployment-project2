#!/usr/bin/env bash
set -euo pipefail

service="${1:-}"
case "$service" in
  backend|frontend|mcp_server) ;;
  *) echo 'Usage: deploy.sh backend|frontend|mcp_server' >&2; exit 2 ;;
esac

for name in AWS_HOST AWS_USER AWS_SSH_PRIVATE_KEY AWS_SSH_KNOWN_HOSTS; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing environment secret: $name" >&2
    exit 1
  fi
done

key_file=$(mktemp)
known_hosts_file=$(mktemp)
bundle=$(mktemp --suffix=.tar.gz)
trap 'rm -f "$key_file" "$known_hosts_file" "$bundle"' EXIT
chmod 600 "$key_file" "$known_hosts_file"
printf '%s\n' "$AWS_SSH_PRIVATE_KEY" | tr -d '\r' > "$key_file"
printf '%s\n' "$AWS_SSH_KNOWN_HOSTS" | tr -d '\r' > "$known_hosts_file"

# Checkout contains tracked source and examples only. Server-side secrets stay in place.
tar -czf "$bundle" "$service"
archive_name="weather-${service}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.tar.gz"
remote="${AWS_USER}@${AWS_HOST}"
ssh_options=(-i "$key_file" -o BatchMode=yes -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_hosts_file"
  -o ServerAliveInterval=30 -o ServerAliveCountMax=20)

scp "${ssh_options[@]}" "$bundle" "${remote}:~/${archive_name}"
ssh "${ssh_options[@]}" "$remote" "bash -se -- '$service' '$archive_name'" <<'REMOTE'
set -euo pipefail
service="$1"
archive="$HOME/$2"
deploy_dir="$HOME/weather-mcp-deployment"
trap 'rm -f "$archive"' EXIT
mkdir -p "$deploy_dir/$service/config"
tar -xzf "$archive" -C "$deploy_dir"
cd "$deploy_dir/$service"

if [[ ! -f config/.env.docker ]]; then
  cp config/.env.docker.example config/.env.docker
fi
if [[ "$service" == backend && ! -f config/.env ]]; then
  echo "Missing server environment file: $PWD/config/.env" >&2
  exit 1
fi

# Keep application URLs on the shared Docker network, preserving other server settings.
case "$service" in
  backend)
    if grep -q '^WEATHER_MCP_URL=' config/.env.docker; then
      sed -i 's|^WEATHER_MCP_URL=.*|WEATHER_MCP_URL=http://weather-mcp:8010/mcp|' config/.env.docker
    else
      printf '\nWEATHER_MCP_URL=http://weather-mcp:8010/mcp\n' >> config/.env.docker
    fi
    ;;
  frontend)
    if grep -q '^BACKEND_URL=' config/.env.docker; then
      sed -i 's|^BACKEND_URL=.*|BACKEND_URL=http://backend:8000|' config/.env.docker
    else
      printf '\nBACKEND_URL=http://backend:8000\n' >> config/.env.docker
    fi
    ;;
esac
chmod 600 config/.env.docker

# Only startup is serialized. Health checks run outside the lock so dependencies can start.
flock -w 300 "$deploy_dir/.deploy.lock" bash -ec '
  docker network inspect weather-local >/dev/null 2>&1 || docker network create weather-local
  docker compose -f deploy/compose.yml config --quiet
  docker compose -f deploy/compose.yml up -d --build
'
wait_for_health() {
  for attempt in {1..60}; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    if (( attempt % 6 == 0 )); then
      echo "Waiting for $service health check ($attempt/60 attempts)..."
    fi
    sleep 10
  done
  compose_service="$service"
  if [[ "$service" == mcp_server ]]; then compose_service=weather-mcp; fi
  docker compose -f deploy/compose.yml ps
  docker compose -f deploy/compose.yml logs --tail=60 "$compose_service" || true
  "$@"
}
case "$service" in
  backend) wait_for_health curl --fail --silent --show-error http://127.0.0.1:8000/health/ready ;;
  frontend)
    wait_for_health curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
    wait_for_health docker compose -f deploy/compose.yml exec -T frontend python -c \
      "import os, urllib.request; urllib.request.urlopen(os.environ['BACKEND_URL'] + '/health/ready', timeout=10)"
    ;;
  mcp_server) wait_for_health curl --fail --silent --show-error http://127.0.0.1:8010/health ;;
esac
echo "$service deployment and health check passed."
REMOTE
