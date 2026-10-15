#!/bin/sh
# Запуск стека после перезагрузки на машине без systemd.
# 1) запускает Docker, 2) убирает старые правила iptables-legacy, которые блокируют сети compose,
# 3) поднимает контейнеры. Запускать от root: sudo sh scripts/boot.sh
set -e
cd "$(dirname "$0")/.."
service docker status >/dev/null 2>&1 || service docker start
i=0; until docker info >/dev/null 2>&1; do i=$((i+1)); [ $i -gt 30 ] && { echo "dockerd не запустился"; exit 1; }; sleep 1; done
if command -v iptables-legacy >/dev/null 2>&1; then
  for t in filter nat; do iptables-legacy -t $t -F 2>/dev/null || true; iptables-legacy -t $t -X 2>/dev/null || true; done
  iptables-legacy -P FORWARD ACCEPT 2>/dev/null || true
fi
docker compose up -d
docker compose ps
