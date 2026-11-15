"""B3 — Passo B5 do PLANO_DIVIDIDO: deriva do MODIS.

Entradas: saida/celulas_dia.parquet, saida/disponibilidade.parquet
Saída:    saida/deriva.csv

Para cada ano x mês (e para duas áreas: Brasil e Cerrado), nos dias em que MODIS e VIIRS
de referência estavam `ok`:
    cdev_viirs            células-dia do VIIRS de referência
    cdev_modis_bruto      células-dia do MODIS, sem calibrar
    cdev_modis_calibrado  MODIS x fator (calibrado em calibracao_anos)
    erro_pct              (calibrado - viirs) / viirs x 100
    fator_efetivo         viirs / modis_bruto no mês (o "fator que seria preciso")

Esperado: erro pequeno nos anos de calibração e crescente depois. Isso é a deriva medida.
Colunas do contrato: ano, mes, cdev_viirs, cdev_modis_calibrado, erro_pct.
Extras: area, cdev_modis_bruto, fator_efetivo, dias, calibracao (True nos anos usados).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import SAIDA, cfg, conectar_duckdb  # noqa: E402

CELULAS_DIA = SAIDA / "celulas_dia.parquet"
DISP = SAIDA / "disponibilidade.parquet"
DESTINO = SAIDA / "deriva.csv"


def main():
    c = cfg()
    a0, a1 = c["calibracao_anos"]
    h0, h1 = c["periodo_historico"]
    con = conectar_duckdb()
    df = con.execute(f"""
        WITH dias AS (
          SELECT data_local FROM '{DISP}'
          WHERE status_modis = 'ok' AND referencia IN ('snpp', 'n20')
            AND year(data_local) BETWEEN {h0} AND {h1}
        ),
        base AS (
          SELECT year(data_local) AS ano, month(data_local) AS mes, no_cerrado,
                 cdev, ativa_modis::INT AS modis, cdev_modis
          FROM '{CELULAS_DIA}' JOIN dias USING (data_local)
        ),
        brasil  AS (SELECT 'brasil'  AS area, ano, mes, sum(cdev) viirs, sum(modis) bruto,
                           sum(cdev_modis) calibrado FROM base GROUP BY ALL),
        cerrado AS (SELECT 'cerrado' AS area, ano, mes, sum(cdev) viirs, sum(modis) bruto,
                           sum(cdev_modis) calibrado FROM base WHERE no_cerrado GROUP BY ALL),
        ndias AS (SELECT year(data_local) ano, month(data_local) mes, count(*) dias
                  FROM dias GROUP BY ALL)
        SELECT u.area, u.ano, u.mes, u.viirs AS cdev_viirs, u.bruto AS cdev_modis_bruto,
               u.calibrado AS cdev_modis_calibrado,
               (u.calibrado - u.viirs) / u.viirs * 100 AS erro_pct,
               u.viirs / nullif(u.bruto, 0) AS fator_efetivo,
               n.dias, u.ano BETWEEN {a0} AND {a1} AS calibracao
        FROM (SELECT * FROM brasil UNION ALL SELECT * FROM cerrado) u
        JOIN ndias n USING (ano, mes)
        ORDER BY area, ano, mes
    """).df()
    df.to_csv(DESTINO, index=False)
    print(f"[B5] {len(df)} linhas -> {DESTINO}")
    resumo = df.groupby(["area", "ano"]).apply(
        lambda g: (g.cdev_modis_calibrado.sum() - g.cdev_viirs.sum()) / g.cdev_viirs.sum() * 100,
        include_groups=False).unstack("area").round(1)
    print("\nErro anual do MODIS calibrado contra o VIIRS (%; calibrado em "
          f"{a0}–{a1}):\n{resumo.to_string()}")


if __name__ == "__main__":
    main()
