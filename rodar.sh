#!/usr/bin/env bash
# Roda um script Python do projeto com TETO DE MEMÓRIA, para nunca travar a máquina.
#
#   ./rodar.sh pipeline/a5_celula_territorio.py [args...]
#   MEM=3G ./rodar.sh pipeline/a1_observacoes.py obs     # teto diferente (padrão 2G)
#   ./rodar.sh - <<'EOF' ... EOF                          # script pelo stdin
#
# MemoryMax     = limite de RAM do processo.
# MemorySwapMax = 0 -> o processo NÃO usa swap. Ao passar do limite ele é morto na hora
#                 (código 137), em vez de levar o computador inteiro a travar.
#
# Sem systemd (macOS, Windows/Git Bash, alguns WSL) roda o Python direto, SEM teto, e avisa.
set -euo pipefail
cd "$(dirname "$0")"
MEM="${MEM:-2G}"

if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
    PY=.venv/Scripts/python.exe
else
    PY="$(command -v python3 || command -v python)"
fi

if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    exec systemd-run --user --scope -q -p MemoryMax="$MEM" -p MemorySwapMax=0 \
         nice -n 10 "$PY" "$@"
else
    echo "[rodar.sh] systemd indisponível: rodando SEM teto de memória." >&2
    exec "$PY" "$@"
fi
