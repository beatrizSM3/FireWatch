#!/usr/bin/env bash
# Regenera TODA a pasta saida/ a partir dos dados brutos (Parte A do PLANO_DIVIDIDO).
# Leva ~3-4 min e no máximo ~2 GB de RAM por etapa.
#
#   ./pipeline/rodar_pipeline.sh            # tudo
#   ./pipeline/rodar_pipeline.sh a4 a5      # só algumas etapas (na ordem dada)
#
# Ordem e dependências:
#   a0  extrai as zips do FIRMS               data/raw/zip/nasa -> data/raw/nasa (CSVs)
#   a1  observações + fontes fixas            -> saida/observacoes/, fontes_fixas.parquet, _tmp/bruto.parquet
#   a2  disponibilidade dos satélites         (precisa a1) -> disponibilidade.parquet
#   a3  células-dia por satélite              (precisa a1) -> celulas_base.parquet
#   a4  territórios (UCs e TIs do Cerrado)    -> territorios.geojson, _tmp/territorios_5880.parquet
#   a5  células de cada território            (precisa a4) -> celula_territorio.parquet
set -euo pipefail
cd "$(dirname "$0")/.."

etapas=("$@")
[ ${#etapas[@]} -eq 0 ] && etapas=(a0 a1 a2 a3 a4 a5)

for e in "${etapas[@]}"; do
    case "$e" in
        a0) script=pipeline/a0_extrair_zips.py ;;
        a1) script=pipeline/a1_observacoes.py ;;
        a2) script=pipeline/a2_disponibilidade.py ;;
        a3) script=pipeline/a3_celulas_base.py ;;
        a4) script=pipeline/a4_territorios.py ;;
        a5) script=pipeline/a5_celula_territorio.py ;;
        *) echo "etapa desconhecida: $e (use a0..a5)" >&2; exit 1 ;;
    esac
    echo "=== $e: $script"
    ./rodar.sh "$script"
done
echo "=== pronto. Confira com: ./rodar.sh -m pytest tests -q"
