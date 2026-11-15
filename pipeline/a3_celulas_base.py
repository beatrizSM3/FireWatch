"""A3 — Passo A8 do PLANO_DIVIDIDO: células-dia por satélite.

Entrada:  saida/observacoes/ano=*/*.parquet   (gerado pelo A1)
Saída:    saida/celulas_base.parquet

Uma linha por (célula de 1 km, dia local) com pelo menos um foco de SNPP, N20 ou MODIS.
Colunas: gx, gy, data_local, ativa_snpp, ativa_n20, ativa_modis, produto

Decisões:
- N21 fica de fora (só conferência; a Pessoa D usa direto de observacoes/).
- A máscara de fontes fixas (A7) já foi aplicada aos focos NRT em observacoes/,
  então aqui não precisa filtrar de novo.
- produto = max(produto): 'nrt' > 'archive' em ordem alfabética, ou seja, se algum foco
  da célula-dia veio do NRT, a célula-dia é marcada como 'nrt'.
- Agregado ano a ano (cada data_local pertence a um único ano) para limitar a memória;
  o resultado vai para um único arquivo, ordenado por data_local, gx, gy.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import SAIDA, TMP, cfg, conectar_duckdb  # noqa: E402

OBS = SAIDA / "observacoes"
DESTINO = SAIDA / "celulas_base.parquet"
PARTES = TMP / "celulas_base_partes"


def main():
    c = cfg()
    ano_ini, ano_fim = int(c["data_inicio_dados"][:4]), int(c["data_fim_dados"][:4])
    con = conectar_duckdb()
    t0 = time.time()

    PARTES.mkdir(parents=True, exist_ok=True)
    for ano in range(ano_ini, ano_fim + 1):
        t1 = time.time()
        parte = PARTES / f"{ano}.parquet"
        con.execute(f"""
            COPY (
              SELECT gx, gy, data_local,
                     bool_or(satelite = 'SNPP')            AS ativa_snpp,
                     bool_or(satelite = 'N20')             AS ativa_n20,
                     bool_or(satelite IN ('Terra','Aqua')) AS ativa_modis,
                     max(produto)                          AS produto
              FROM '{OBS / f"ano={ano}" / "*.parquet"}'
              WHERE satelite <> 'N21'
              GROUP BY gx, gy, data_local
              ORDER BY data_local, gx, gy
            ) TO '{parte}' (FORMAT parquet, COMPRESSION zstd)
        """)
        n = con.execute(f"SELECT count(*) FROM '{parte}'").fetchone()[0]
        print(f"[A8] {ano}: {n:,} células-dia ({time.time()-t1:.0f}s)", flush=True)

    # junta as partes (já ordenadas, e os anos em sequência) num arquivo só.
    # conectar_duckdb() desliga preserve_insertion_order; religamos para a junção
    # manter a ordem das partes sem precisar reordenar tudo.
    con.execute("SET preserve_insertion_order=true")
    arquivos = [str(PARTES / f"{a}.parquet") for a in range(ano_ini, ano_fim + 1)]
    lista = "[" + ",".join(f"'{a}'" for a in arquivos) + "]"
    con.execute(f"""
        COPY (SELECT * FROM read_parquet({lista}))
        TO '{DESTINO}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000)
    """)
    for a in arquivos:
        Path(a).unlink()
    PARTES.rmdir()
    total = con.execute(f"SELECT count(*) FROM '{DESTINO}'").fetchone()[0]
    print(f"[A8] total {total:,} células-dia -> {DESTINO} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
