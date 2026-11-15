"""B2 — Passo B4 do PLANO_DIVIDIDO: a série harmonizada (CDeV), célula x dia.

Entradas: saida/celulas_base.parquet, saida/disponibilidade.parquet,
          saida/fatores.parquet, saida/_tmp/celula_regiao.parquet (gerado pelo B1)
Saída:    saida/celulas_dia.parquet  — O ARQUIVO QUE O APP INTEIRO USA

Uma linha por (célula de 1 km, dia local) com fogo em algum satélite (as mesmas linhas de
celulas_base), com o valor harmonizado:

  referência do dia   cdev                       fonte
  snpp                1 se ativa_snpp, senão 0   viirs
  n20                 1 se ativa_n20,  senão 0   viirs
  modis               f se ativa_modis, senão 0  modis_calibrado  (cdev_min/max = f_min/f_max)
  NULL (nenhum ok)    NULL                       NULL             (dia NA: não é zero!)

Colunas do contrato: gx, gy, data_local, cdev, cdev_min, cdev_max, fonte, produto,
                     ativa_snpp, ativa_n20, ativa_modis
Colunas extras:      regiao_id, no_cerrado (centro da célula dentro do Cerrado),
                     cdev_modis, cdev_modis_min, cdev_modis_max = MODIS calibrado da
                     célula-dia (f se ativa_modis), para o botão "ver por sensor" e a deriva.

Cuidado: dias em que NENHUM satélite viu fogo numa área não têm linha — isso é zero de
verdade. Dias NA são os que têm referencia NULL em disponibilidade.parquet. Quem monta a
série diária com os zeros e os NAs certos é firewatch.indicadores.serie_diaria.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import SAIDA, TMP, conectar_duckdb  # noqa: E402

CELULAS_BASE = SAIDA / "celulas_base.parquet"
DISP = SAIDA / "disponibilidade.parquet"
FATORES = SAIDA / "fatores.parquet"
CELULA_REGIAO = TMP / "celula_regiao.parquet"
DESTINO = SAIDA / "celulas_dia.parquet"


def main():
    con = conectar_duckdb()
    t0 = time.time()
    con.execute(f"""
        COPY (
          SELECT b.gx, b.gy, b.data_local, r.regiao_id, r.no_cerrado,
                 b.ativa_snpp, b.ativa_n20, b.ativa_modis, b.produto,
                 CASE d.referencia
                      WHEN 'snpp'  THEN 'viirs'
                      WHEN 'n20'   THEN 'viirs'
                      WHEN 'modis' THEN 'modis_calibrado' END                       AS fonte,
                 CASE d.referencia
                      WHEN 'snpp'  THEN b.ativa_snpp::DOUBLE
                      WHEN 'n20'   THEN b.ativa_n20::DOUBLE
                      WHEN 'modis' THEN b.ativa_modis::INT * f.f END                AS cdev,
                 CASE d.referencia
                      WHEN 'snpp'  THEN b.ativa_snpp::DOUBLE
                      WHEN 'n20'   THEN b.ativa_n20::DOUBLE
                      WHEN 'modis' THEN b.ativa_modis::INT * f.f_min END            AS cdev_min,
                 CASE d.referencia
                      WHEN 'snpp'  THEN b.ativa_snpp::DOUBLE
                      WHEN 'n20'   THEN b.ativa_n20::DOUBLE
                      WHEN 'modis' THEN b.ativa_modis::INT * f.f_max END            AS cdev_max,
                 b.ativa_modis::INT * f.f     AS cdev_modis,
                 b.ativa_modis::INT * f.f_min AS cdev_modis_min,
                 b.ativa_modis::INT * f.f_max AS cdev_modis_max
          FROM '{CELULAS_BASE}' b
          JOIN '{CELULA_REGIAO}' r USING (gx, gy)
          JOIN '{FATORES}' f ON f.regiao_id = r.regiao_id AND f.mes = month(b.data_local)
          LEFT JOIN '{DISP}' d USING (data_local)
          ORDER BY b.data_local, b.gx, b.gy
        ) TO '{DESTINO}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000)
    """)
    q = lambda sql: con.execute(sql.replace("CD", f"'{DESTINO}'")).df()  # noqa: E731
    n_base = con.execute(f"SELECT count(*) FROM '{CELULAS_BASE}'").fetchone()[0]
    n = con.execute(f"SELECT count(*) FROM '{DESTINO}'").fetchone()[0]
    assert n == n_base, f"celulas_dia tem {n} linhas, celulas_base tem {n_base}"
    print(f"[B4] {n:,} células-dia -> {DESTINO} ({DESTINO.stat().st_size / 1e6:.0f} MB, "
          f"{time.time() - t0:.0f}s)")
    print("\nFonte:")
    print(q("SELECT fonte, count(*) n FROM CD GROUP BY 1 ORDER BY 1").to_string(index=False))
    print("\nCDeV por ano (Cerrado): deve ficar perto das células-dia do S-NPP")
    print(q("""SELECT year(data_local) ano, round(sum(cdev)) cdev, sum(ativa_snpp::INT) snpp,
                      sum(ativa_n20::INT) n20, sum(ativa_modis::INT) modis_bruto,
                      round(sum(cdev_modis)) modis_calibrado
               FROM CD WHERE no_cerrado GROUP BY 1 ORDER BY 1""").to_string(index=False))


if __name__ == "__main__":
    main()
