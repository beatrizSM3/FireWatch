"""B1 — Passos B2 e B3 do PLANO_DIVIDIDO: regiões de calibração e fatores MODIS -> VIIRS.

Entradas: saida/celulas_base.parquet, saida/disponibilidade.parquet,
          data/raw/biome_border/biome_border.shp (limite do Cerrado)
Saídas:   saida/_tmp/celula_regiao.parquet   (gx, gy, regiao_id, no_cerrado)  -> usado pelo B2
          saida/regioes.geojson              (uma linha por região de 1° x 1°)
          saida/fatores.parquet              (uma linha por mês x região)
          saida/fatores_agregados.csv        (fator do Cerrado e do Brasil por mês)

A ideia (PLANO_DIVIDIDO B.1): em célula-dia de 1 km o MODIS ainda vê menos que o VIIRS.
O fator f(mês, região) = mediana entre os anos de calibração de
    [células-dia do VIIRS de referência] / [células-dia do MODIS]
calculado só nos dias em que MODIS e VIIRS de referência estavam `ok`.

Decisões:
- Região = quadrado de 1° x 1° do centro da célula: regiao_id = "<floor(lat)>_<floor(lon)>".
- Anos de calibração: config calibracao_anos (2019–2022), antes da deriva forte do MODIS.
- Dias com status_modis = 'parcial' (um dos dois satélites fora) ficam FORA (README da Parte A).
- Estrato com menos de estrato_minimo_celulas (200) células-dia MODIS no período, ou com
  menos de 2 anos com razão, usa o fator do Cerrado (se a região toca o Cerrado) ou o
  nacional, do mesmo mês. A coluna `nivel` diz qual foi usado: regiao | cerrado | nacional.
- Incerteza: f_min e f_max = menor e maior razão anual (4 anos).
- Toda região com célula em celulas_base recebe fator para os 12 meses: o JOIN do B2 nunca
  fica sem fator.
"""
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import RAW, SAIDA, TMP, cfg, conectar_duckdb  # noqa: E402

CELULAS_BASE = SAIDA / "celulas_base.parquet"
DISP = SAIDA / "disponibilidade.parquet"
CELULA_REGIAO = TMP / "celula_regiao.parquet"
REGIOES = SAIDA / "regioes.geojson"
FATORES = SAIDA / "fatores.parquet"
AGREGADOS = SAIDA / "fatores_agregados.csv"


def etapa_regioes(con):
    """B2 — regiao_id e no_cerrado para cada célula distinta de celulas_base."""
    c = cfg()
    L = float(c["celula_m"])
    cel = con.execute(f"SELECT DISTINCT gx, gy FROM '{CELULAS_BASE}' ORDER BY gx, gy").df()
    x = cel.gx.to_numpy() * L + L / 2
    y = cel.gy.to_numpy() * L + L / 2
    lon, lat = Transformer.from_crs(c["crs_metros"], 4326, always_xy=True).transform(x, y)
    cel["regiao_id"] = [f"{a}_{b}" for a, b in zip(np.floor(lat).astype(int), np.floor(lon).astype(int))]

    cerrado = gpd.read_file(RAW / "biome_border" / "biome_border.shp")
    cerrado_m = cerrado.to_crs(c["crs_metros"]).geometry.union_all()
    shapely.prepare(cerrado_m)
    cel["no_cerrado"] = shapely.contains_xy(cerrado_m, x, y)
    TMP.mkdir(parents=True, exist_ok=True)
    cel.to_parquet(CELULA_REGIAO, index=False)
    print(f"[B2] {len(cel):,} células distintas, {cel.regiao_id.nunique()} regiões, "
          f"{cel.no_cerrado.sum():,} células no Cerrado")

    # regiões: um quadrado por regiao_id; "no_cerrado" = o quadrado toca o bioma
    reg = cel.groupby("regiao_id", as_index=False).agg(n_celulas=("gx", "size"),
                                                       celulas_no_cerrado=("no_cerrado", "sum"))
    lat0 = reg.regiao_id.str.split("_").str[0].astype(int)
    lon0 = reg.regiao_id.str.split("_").str[1].astype(int)
    geom = [box(lo, la, lo + 1, la + 1) for la, lo in zip(lat0, lon0)]
    g = gpd.GeoDataFrame(reg, geometry=geom, crs=4326)
    cerrado_4326 = cerrado.to_crs(4326).geometry.union_all()
    g["no_cerrado"] = g.intersects(cerrado_4326)
    g.to_file(REGIOES, driver="GeoJSON")
    print(f"[B2] {len(g)} regiões -> {REGIOES} ({g.no_cerrado.sum()} tocam o Cerrado)")
    return cel


def etapa_fatores(con):
    """B3 — fator por (mes, regiao_id) com fallback para Cerrado / nacional."""
    c = cfg()
    a0, a1 = c["calibracao_anos"]
    minimo = int(c["estrato_minimo_celulas"])

    # células-dia VIIRS (referência do dia) e MODIS por mês x região x ano, dias comparáveis
    por_ano = con.execute(f"""
        WITH dias AS (
          SELECT data_local, referencia FROM '{DISP}'
          WHERE status_modis = 'ok' AND referencia IN ('snpp', 'n20')
            AND year(data_local) BETWEEN {a0} AND {a1}
        ),
        base AS (
          SELECT month(b.data_local) AS mes, year(b.data_local) AS ano, r.regiao_id, r.no_cerrado,
                 CASE d.referencia WHEN 'snpp' THEN b.ativa_snpp::INT ELSE b.ativa_n20::INT END AS viirs,
                 b.ativa_modis::INT AS modis
          FROM '{CELULAS_BASE}' b
          JOIN dias d USING (data_local)
          JOIN '{CELULA_REGIAO}' r USING (gx, gy)
        )
        SELECT mes, ano, regiao_id, no_cerrado, sum(viirs) AS viirs, sum(modis) AS modis
        FROM base GROUP BY ALL
    """).df()
    print(f"[B3] dias comparáveis em {a0}–{a1}: "
          f"{con.execute(f'''SELECT count(*) FROM '{DISP}' WHERE status_modis='ok'
              AND referencia IN ('snpp','n20') AND year(data_local) BETWEEN {a0} AND {a1}''').fetchone()[0]}")

    def resumir(df, chaves):
        """Razão por ano -> mediana/min/max por chave; n_anos conta só anos com MODIS > 0."""
        g = df.groupby(chaves + ["ano"], as_index=False)[["viirs", "modis"]].sum()
        g = g[g.modis > 0]
        g["razao"] = g.viirs / g.modis
        out = g.groupby(chaves).agg(f=("razao", "median"), f_min=("razao", "min"),
                                     f_max=("razao", "max"), n_anos=("ano", "size")).reset_index()
        tot = df.groupby(chaves, as_index=False)[["viirs", "modis"]].sum() \
                .rename(columns={"modis": "n_celulas_dia", "viirs": "n_celulas_dia_viirs"})
        return out.merge(tot, on=chaves, how="right")

    nacional = resumir(por_ano, ["mes"]).assign(escopo="brasil")
    cerrado = resumir(por_ano[por_ano.no_cerrado], ["mes"]).assign(escopo="cerrado")
    agregados = pd.concat([nacional, cerrado], ignore_index=True)
    agregados = agregados[["escopo", "mes", "f", "f_min", "f_max", "n_anos",
                           "n_celulas_dia", "n_celulas_dia_viirs"]].sort_values(["escopo", "mes"])
    agregados.to_csv(AGREGADOS, index=False)

    regiao = resumir(por_ano, ["mes", "regiao_id"])
    # grade completa: toda região de celula_regiao x 12 meses
    regioes = pd.read_parquet(CELULA_REGIAO).groupby("regiao_id", as_index=False) \
                .agg(no_cerrado=("no_cerrado", "any"))
    grade = regioes.merge(pd.DataFrame({"mes": range(1, 13)}), how="cross")
    fat = grade.merge(regiao, on=["mes", "regiao_id"], how="left")
    fat["n_celulas_dia"] = fat["n_celulas_dia"].fillna(0).astype(int)
    fat["n_anos"] = fat["n_anos"].fillna(0).astype(int)
    fat["nivel"] = "regiao"
    fraco = (fat.n_celulas_dia < minimo) | (fat.n_anos < 2) | fat.f.isna()

    nac = nacional.set_index("mes")[["f", "f_min", "f_max"]]
    cer = cerrado.set_index("mes")[["f", "f_min", "f_max"]]
    for col in ["f", "f_min", "f_max"]:
        usa_cer = fraco & fat.no_cerrado
        usa_nac = fraco & ~fat.no_cerrado
        fat.loc[usa_cer, col] = fat.loc[usa_cer, "mes"].map(cer[col]).to_numpy()
        fat.loc[usa_nac, col] = fat.loc[usa_nac, "mes"].map(nac[col]).to_numpy()
    fat.loc[fraco & fat.no_cerrado, "nivel"] = "cerrado"
    fat.loc[fraco & ~fat.no_cerrado, "nivel"] = "nacional"
    # se nem o Cerrado tiver fator num mês (não deve acontecer), cai no nacional
    ainda = fat.f.isna()
    for col in ["f", "f_min", "f_max"]:
        fat.loc[ainda, col] = fat.loc[ainda, "mes"].map(nac[col]).to_numpy()
    fat.loc[ainda, "nivel"] = "nacional"

    fat = fat[["mes", "regiao_id", "no_cerrado", "f", "f_min", "f_max", "n_anos",
               "n_celulas_dia", "nivel"]].sort_values(["regiao_id", "mes"])
    assert fat.f.notna().all() and (fat.f > 0).all() and np.isfinite(fat.f).all(), "fator inválido"
    fat.to_parquet(FATORES, index=False)

    print(f"[B3] {len(fat):,} fatores ({fat.regiao_id.nunique()} regiões x 12 meses) -> {FATORES}")
    print("     nível usado:", fat.nivel.value_counts().to_dict())
    print("\nFator nacional e do Cerrado por mês (VIIRS / MODIS):")
    print(agregados.pivot(index="mes", columns="escopo", values="f").round(2).to_string())


def main():
    con = conectar_duckdb()
    t0 = time.time()
    etapa_regioes(con)
    etapa_fatores(con)
    print(f"[B1] pronto em {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
