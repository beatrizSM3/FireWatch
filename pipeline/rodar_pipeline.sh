#!/usr/bin/env bash
# Regenera TODA a pasta saida/ a partir dos dados brutos (Partes A e B do PLANO_DIVIDIDO).
# Leva ~5 min e no máximo ~2 GB de RAM por etapa.
#
#   ./pipeline/rodar_pipeline.sh            # tudo (A e B)
#   ./pipeline/rodar_pipeline.sh a4 a5      # só algumas etapas (na ordem dada)
#   ./pipeline/rodar_pipeline.sh b1 b2 b3 b4 b5   # só a Parte B
#
# Ordem e dependências:
#   a0  extrai as zips do FIRMS               data/raw/zip/nasa -> data/raw/nasa (CSVs)
#   a1  observações + fontes fixas            -> saida/observacoes/, fontes_fixas.parquet, _tmp/bruto.parquet
#   a2  disponibilidade dos satélites         (precisa a1) -> disponibilidade.parquet
#   a3  células-dia por satélite              (precisa a1) -> celulas_base.parquet
#   a4  territórios (UCs e TIs do Cerrado)    -> territorios.geojson, _tmp/territorios_5880.parquet
#   a5  células de cada território            (precisa a4) -> celula_territorio.parquet
#   b1  regiões + fatores MODIS->VIIRS        (precisa a2 a3) -> fatores.parquet, regioes.geojson, fatores_agregados.csv
#   b2  série harmonizada (CDeV)              (precisa b1) -> celulas_dia.parquet
#   b3  deriva do MODIS                       (precisa b2) -> deriva.csv
#   b4  painel de alerta dos territórios      (precisa b2 a5) -> alerta_territorios.parquet
#   b5  Modo MIF por grupo de território      (precisa b2 a5) -> mif_grupos.csv
set -euo pipefail
cd "$(dirname "$0")/.."

etapas=("$@")
[ ${#etapas[@]} -eq 0 ] && etapas=(a0 a1 a2 a3 a4 a5 b1 b2 b3 b4 b5)

for e in "${etapas[@]}"; do
    case "$e" in
        a0) script=pipeline/a0_extrair_zips.py ;;
        a1) script=pipeline/a1_observacoes.py ;;
        a2) script=pipeline/a2_disponibilidade.py ;;
        a3) script=pipeline/a3_celulas_base.py ;;
        a4) script=pipeline/a4_territorios.py ;;
        a5) script=pipeline/a5_celula_territorio.py ;;
        b1) script=pipeline/b1_fatores.py ;;
        b2) script=pipeline/b2_celulas_dia.py ;;
        b3) script=pipeline/b3_deriva.py ;;
        b4) script=pipeline/b4_alerta_territorios.py ;;
        b5) script=pipeline/b5_mif_grupos.py ;;
        *) echo "etapa desconhecida: $e (use a0..a5, b1..b5)" >&2; exit 1 ;;
    esac
    echo "=== $e: $script"
    ./rodar.sh "$script"
done
echo "=== pronto. Confira com: ./rodar.sh -m pytest tests -q"
