"""B4 — Passo B7 do PLANO_DIVIDIDO: painel de alerta dos territórios.

Entradas: saida/celulas_dia.parquet, saida/celula_territorio.parquet, saida/territorios.geojson
Saídas:   saida/alerta_territorios.parquet   (uma linha por território com área >= mínimo)
          saida/_tmp/serie_territorios.parquet (série diária de cada território x zona;
                                                 cache para quem quiser evitar o JOIN)

Para cada território com area_km2 >= territorio_area_min_km2 (config: 10):
  cdev_2026, posicao, n_anos, classificacao     cartão "2026 até data_fim_dados" (indicadores.ano_em_curso)
  densidade_2026, densidade_mediana             CDeV por 1.000 km² (2026 e mediana dos anos históricos)
  fracao_tardia_2026 (+ classificacao_mif)      Modo MIF, até data_fim_dados
  razao_dentro_entorno                          densidade dentro / densidade no anel de 10 km em 2026
  cdev_mes_atual, classificacao_mes_atual       termômetro do mês de data_fim_dados
  + ficha (nome, tipo, categoria, grupo, uf, gestor, area_km2, limite_aproximado)
  + ordem_classificacao (0 recorde ... 4 sem histórico) para ordenar o painel.

Regras: não soma territórios (cada linha é um território). Territórios sem célula
'dentro' (< ~2 km²) já ficam fora pelo mínimo de área.
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch import carregar  # noqa: E402
from firewatch import indicadores as ind  # noqa: E402
from firewatch.config import SAIDA, TMP, cfg, conectar_duckdb  # noqa: E402

CELULAS_DIA = SAIDA / "celulas_dia.parquet"
CELULA_TERRITORIO = SAIDA / "celula_territorio.parquet"
SERIES = TMP / "serie_territorios.parquet"
DESTINO = SAIDA / "alerta_territorios.parquet"

ORDEM = {"recorde (acima do máximo histórico)": 0, "acima da mediana": 1,
         "abaixo da mediana": 2, "abaixo do mínimo histórico": 3}


def series_por_territorio(con) -> pd.DataFrame:
    """Soma diária de celulas_dia por (território, zona) — um JOIN só para todos."""
    TMP.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
          SELECT t.id_territorio, t.zona, c.data_local,
                 sum(c.cdev) cdev, sum(c.cdev_min) cdev_min, sum(c.cdev_max) cdev_max,
                 sum(c.ativa_snpp::INT) snpp, sum(c.ativa_n20::INT) n20,
                 sum(c.ativa_modis::INT) modis_bruto, sum(c.cdev_modis) modis_calibrado,
                 bool_or(c.produto = 'nrt') nrt, count(*) celulas_ativas
          FROM '{CELULAS_DIA}' c JOIN '{CELULA_TERRITORIO}' t USING (gx, gy)
          GROUP BY ALL ORDER BY id_territorio, zona, data_local
        ) TO '{SERIES}' (FORMAT parquet, COMPRESSION zstd)
    """)
    return pd.read_parquet(SERIES)


def main():
    c = cfg()
    area_min = float(c["territorio_area_min_km2"])
    ano = int(c["ano_em_curso"])
    fim = pd.Timestamp(c["data_fim_dados"])
    con = conectar_duckdb()
    t0 = time.time()

    series = series_por_territorio(con)
    print(f"[B7] séries diárias de {series.id_territorio.nunique()} territórios ({time.time()-t0:.0f}s)")
    entorno_km2 = con.execute(f"""SELECT id_territorio, count(*) n FROM '{CELULA_TERRITORIO}'
                                  WHERE zona = 'entorno' GROUP BY 1""").df().set_index("id_territorio")["n"]
    disp = carregar.disponibilidade()
    terr = carregar.territorios().drop(columns="geometry")
    terr = terr[terr.area_km2 >= area_min]
    vazio = pd.DataFrame(columns=["data_local", "cdev"])
    grupos = {k: g.drop(columns=["id_territorio", "zona"]) for k, g in series.groupby(["id_territorio", "zona"])}

    linhas = []
    for _, t in terr.iterrows():
        tid = t.id_territorio
        dentro = grupos.get((tid, "dentro"), vazio)
        fora = grupos.get((tid, "entorno"), vazio)
        a = ind.ano_em_curso(dentro, ano=ano, disponibilidade=disp)
        mif = ind.fracao_tardia(dentro, ano, disponibilidade=disp)
        try:
            term = ind.termometro(dentro, ano, fim.month, disponibilidade=disp)
        except ValueError:
            term = None
        # dentro x entorno no ano em curso, mesmo intervalo (01/01 até data_fim_dados)
        e = ind.ano_em_curso(fora, ano=ano, disponibilidade=disp)
        dens_d = ind.densidade(a["valor"], t.area_km2)
        dens_e = ind.densidade(e["valor"], float(entorno_km2.get(tid, 0)))
        razao = dens_d / dens_e if (dens_d is not None and dens_e) else None
        linhas.append(dict(
            id_territorio=tid, nome=t.nome, tipo=t.tipo, categoria=t.categoria, grupo=t.grupo,
            uf=t.uf, gestor=t.gestor, area_km2=t.area_km2, limite_aproximado=bool(t.limite_aproximado),
            cdev_2026=a["valor"], posicao=a["posicao"], posicao_texto=a["posicao_texto"],
            n_anos=a["n_anos"], classificacao=a["classificacao"], mediana_historica=a["mediana"],
            maximo_historico=a["maximo"], nrt=a["nrt"],
            densidade_2026=dens_d, densidade_mediana=ind.densidade(a["mediana"], t.area_km2)
            if a["mediana"] is not None else None,
            fracao_tardia_2026=mif["fracao"], classificacao_mif=mif["classificacao"],
            mediana_fracao_tardia=mif["mediana"],
            cdev_entorno_2026=e["valor"], area_entorno_km2=float(entorno_km2.get(tid, 0)),
            razao_dentro_entorno=razao,
            cdev_mes_atual=None if term is None else term["valor"],
            classificacao_mes_atual=None if term is None else term["classificacao"],
            ordem_classificacao=ORDEM.get(a["classificacao"], 4),
        ))
    out = pd.DataFrame(linhas).sort_values(
        ["ordem_classificacao", "posicao", "densidade_2026"], ascending=[True, True, False],
        na_position="last").reset_index(drop=True)
    out.to_parquet(DESTINO, index=False)
    print(f"[B7] {len(out)} territórios com área >= {area_min:g} km² -> {DESTINO} "
          f"({time.time()-t0:.0f}s)")
    print("\nClassificação de 2026 até", fim.date(), ":")
    print(out.classificacao.value_counts().to_string())
    print("\nTop 10 por densidade entre os recordes/acima da mediana:")
    cols = ["nome", "tipo", "uf", "area_km2", "cdev_2026", "posicao_texto", "classificacao",
            "densidade_2026", "fracao_tardia_2026", "razao_dentro_entorno"]
    print(out[out.ordem_classificacao <= 1].sort_values("densidade_2026", ascending=False)
          .head(10)[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
