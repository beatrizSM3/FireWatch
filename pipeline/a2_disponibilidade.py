"""A2 — Passo A6 do PLANO_DIVIDIDO: disponibilidade diária de cada satélite.

Entrada:  saida/_tmp/bruto.parquet   (todas as linhas do FIRMS, SEM filtro; gerado pelo A1)
Saída:    saida/disponibilidade.parquet

Uma linha por dia local, de data_inicio_dados a data_fim_dados (calendário completo).

Colunas do contrato:
    data_local, status_snpp, status_n20, status_modis, referencia
Colunas extras (para conferência e para as Pessoas B/C/D):
    n_snpp, n_n20, n_modis, n_terra, n_aqua, n_n21,
    status_terra, status_aqua, status_n21

Decisões:
- Conta no BRASIL INTEIRO e no bruto (sem filtro de confiança/type/FRP): a pergunta
  aqui é "o satélite estava mandando dados?", não "havia fogo de vegetação?".
  Filtrar antes diminuiria a contagem em dias fracos e criaria "parciais" falsos.
- Dia agregado por data_local (UTC-3), o mesmo usado em todo o projeto.
- ausente  = 0 focos.
  parcial  = < limiar_parcial × focos do irmão (SNPP <-> N20), quando o irmão tem
             >= minimo_irmao focos. O N21 também tem como irmão o N20.
  ok       = demais casos.
  MODIS = Terra + Aqua juntos. status_terra/status_aqua = 'ausente' se 0 focos, senão 'ok'.
  status_modis = 'ausente' se os dois estão ausentes; 'parcial' se só UM está ausente
  (ex.: Aqua fora de 01-16/04/2022) — DESVIO do plano, que só previa ausente/ok: sem isso
  a soma Terra+Aqua nunca zera e as lacunas da auditoria (A1) ficariam escondidas,
  e a Pessoa B usaria dias com metade do MODIS na calibração e na deriva.
- referencia = 'snpp' se SNPP ok; senão 'n20' se N20 ok; senão 'modis' se MODIS ok;
  senão NULL (NA).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import SAIDA, TMP, cfg, conectar_duckdb  # noqa: E402

BRUTO = TMP / "bruto.parquet"
SAIDA_ARQ = SAIDA / "disponibilidade.parquet"


def status_sql(n: str, irmao: str, limiar: float, minimo: int) -> str:
    return f"""CASE WHEN {n} = 0 THEN 'ausente'
                    WHEN {irmao} >= {minimo} AND {n} < {limiar} * {irmao} THEN 'parcial'
                    ELSE 'ok' END"""


def main():
    c = cfg()
    ini, fim = c["data_inicio_dados"], c["data_fim_dados"]
    limiar = float(c["disponibilidade"]["limiar_parcial"])
    minimo = int(c["disponibilidade"]["minimo_irmao"])
    con = conectar_duckdb()

    con.execute(f"""
        COPY (
          WITH cal AS (
            SELECT CAST(d AS DATE) AS data_local
            FROM range(DATE '{ini}', DATE '{fim}' + INTERVAL 1 DAY, INTERVAL 1 DAY) t(d)
          ),
          cont AS (
            SELECT data_local,
                   count(*) FILTER (WHERE satelite = 'SNPP')  AS n_snpp,
                   count(*) FILTER (WHERE satelite = 'N20')   AS n_n20,
                   count(*) FILTER (WHERE satelite = 'N21')   AS n_n21,
                   count(*) FILTER (WHERE satelite = 'Terra') AS n_terra,
                   count(*) FILTER (WHERE satelite = 'Aqua')  AS n_aqua
            FROM '{BRUTO}'
            WHERE data_local BETWEEN DATE '{ini}' AND DATE '{fim}'
            GROUP BY data_local
          ),
          d AS (
            SELECT cal.data_local,
                   coalesce(n_snpp, 0)  AS n_snpp,
                   coalesce(n_n20, 0)   AS n_n20,
                   coalesce(n_terra, 0) + coalesce(n_aqua, 0) AS n_modis,
                   coalesce(n_terra, 0) AS n_terra,
                   coalesce(n_aqua, 0)  AS n_aqua,
                   coalesce(n_n21, 0)   AS n_n21
            FROM cal LEFT JOIN cont USING (data_local)
          ),
          s AS (
            SELECT *,
                   {status_sql('n_snpp', 'n_n20', limiar, minimo)} AS status_snpp,
                   {status_sql('n_n20', 'n_snpp', limiar, minimo)} AS status_n20,
                   CASE WHEN n_terra = 0 AND n_aqua = 0 THEN 'ausente'
                        WHEN n_terra = 0 OR n_aqua = 0 THEN 'parcial'
                        ELSE 'ok' END AS status_modis,
                   CASE WHEN n_terra = 0 THEN 'ausente' ELSE 'ok' END AS status_terra,
                   CASE WHEN n_aqua = 0 THEN 'ausente' ELSE 'ok' END AS status_aqua,
                   {status_sql('n_n21', 'n_n20', limiar, minimo)} AS status_n21
            FROM d
          )
          SELECT data_local, status_snpp, status_n20, status_modis,
                 CASE WHEN status_snpp = 'ok' THEN 'snpp'
                      WHEN status_n20 = 'ok' THEN 'n20'
                      WHEN status_modis = 'ok' THEN 'modis' END AS referencia,
                 n_snpp, n_n20, n_modis, n_terra, n_aqua, n_n21,
                 status_terra, status_aqua, status_n21
          FROM s ORDER BY data_local
        ) TO '{SAIDA_ARQ}' (FORMAT parquet)
    """)

    q = lambda sql: con.execute(sql.replace("DISP", f"'{SAIDA_ARQ}'")).df()  # noqa: E731
    print(q("SELECT count(*) dias, min(data_local) ini, max(data_local) fim FROM DISP")
          .to_string(index=False))
    print("\nDias por status:")
    print(q("""SELECT s.sat, s.status, count(*) dias FROM (
                 UNPIVOT DISP ON status_snpp, status_n20, status_modis
                 INTO NAME sat VALUE status) s GROUP BY ALL ORDER BY ALL""").to_string(index=False))
    print("\nReferência:")
    print(q("SELECT referencia, count(*) dias FROM DISP GROUP BY ALL ORDER BY ALL")
          .to_string(index=False))
    print("\nDias com SNPP/N20/MODIS não-ok:")
    print(q("""SELECT data_local, status_snpp, status_n20, status_modis, referencia,
                      n_snpp, n_n20, n_terra, n_aqua FROM DISP
               WHERE status_snpp <> 'ok' OR status_n20 <> 'ok' OR status_modis <> 'ok'
               ORDER BY data_local""").to_string(index=False))


if __name__ == "__main__":
    main()
