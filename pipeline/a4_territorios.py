"""A4 — Passo A9 do PLANO_DIVIDIDO: territórios (UCs e TIs) do Cerrado.

Entradas: data/raw/unidades_conservacao/cnuc_26_07_31.shp   (CNUC, EPSG:4674)
          data/raw/terras_indigenas/tis_poligonais.shp      (FUNAI, EPSG:4674, ISO-8859-1)
          data/raw/biome_border/biome_border.shp            (limite do Cerrado)
Saídas:   saida/territorios.geojson            (EPSG:4326, simplificado 100 m — para o app)
          saida/_tmp/territorios_5880.parquet  (EPSG:5880, SEM simplificar — para o A10)

Colunas do contrato:
    id_territorio, nome, tipo, categoria, grupo, esfera, gestor, etnia, fase,
    pl_manejo, quali_pol, area_km2, geometria
Colunas extras: uf (siglas, ex. "BA, MA"), limite_aproximado

Decisões:
- Seleção por "toca o Cerrado" (intersects), SEM buffer: dá exatamente 687 UCs + 124 TIs
  = 811, o número do PLANO_DIVIDIDO e do PLANO2. (Com o buffer de 15 km citado na seção 7.3
  do PLANO2 dariam 907.)
- O território entra INTEIRO (não é recortado pelo limite do bioma): o gestor administra
  o polígono todo, e recortar distorceria area_km2 e a densidade.
- area_km2 calculada em EPSG:5880 sobre o polígono original.
- Nenhum território é descartado por área: o mínimo de 10 km² vale só para o painel
  (Pessoa B), o território continua na lista com aviso (PLANO2 §7.3).
- limite_aproximado = quali_pol indica "estimativa" ou "representação esquemática".
- ID pelo código, nunca pelo nome (há 11 nomes de TI repetidos).
"""
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import RAW, SAIDA, TMP, cfg  # noqa: E402

DESTINO = SAIDA / "territorios.geojson"
DESTINO_5880 = TMP / "territorios_5880.parquet"

COLUNAS = ["id_territorio", "nome", "tipo", "categoria", "grupo", "esfera", "gestor",
           "etnia", "fase", "pl_manejo", "quali_pol", "area_km2", "uf",
           "limite_aproximado", "geometry"]


SIGLAS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARÁ": "CE", "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "GOIÁS": "GO",
    "MARANHÃO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARÁ": "PA", "PARAÍBA": "PB", "PARANÁ": "PR",
    "PERNAMBUCO": "PE", "PIAUÍ": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SÃO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def uf_siglas(valor) -> str | None:
    """'BAHIA, MARANHÃO' -> 'BA, MA'; 'TO,PA' -> 'PA, TO'. Siglas ordenadas, ', ' entre elas."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    partes = [p.strip().upper() for p in str(valor).split(",") if p.strip()]
    siglas = []
    for p in partes:
        s = p if len(p) == 2 else SIGLAS.get(p)
        if s is None:
            raise ValueError(f"UF desconhecida: {p!r}")
        siglas.append(s)
    return ", ".join(sorted(set(siglas)))


def ler():
    crs = cfg()["crs_metros"]
    uc = gpd.read_file(RAW / "unidades_conservacao" / "cnuc_26_07_31.shp").to_crs(crs)
    ti = gpd.read_file(RAW / "terras_indigenas" / "tis_poligonais.shp",
                       encoding="ISO-8859-1").to_crs(crs)
    bioma = gpd.read_file(RAW / "biome_border" / "biome_border.shp").to_crs(crs)
    return uc, ti, bioma.geometry.union_all()


def padronizar(uc: gpd.GeoDataFrame, ti: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    u = gpd.GeoDataFrame({
        "id_territorio": "UC-" + uc["cd_cnuc"].astype(str),
        "nome": uc["nome_uc"],
        "tipo": "UC",
        "categoria": uc["categoria"],
        "grupo": uc["grupo"],
        "esfera": uc["esfera"],
        "gestor": uc["org_gestor"],
        "etnia": None,
        "fase": None,
        "pl_manejo": uc["pl_manejo"],
        "quali_pol": uc["quali_pol"],
        "uf": uc["uf"].map(uf_siglas),
        "limite_aproximado": uc["quali_pol"].str.contains(
            "estimativa|esquemática", case=False, na=False),
    }, geometry=uc.geometry, crs=uc.crs)
    t = gpd.GeoDataFrame({
        "id_territorio": "TI-" + ti["terrai_cod"].astype(str),
        "nome": ti["terrai_nom"],
        "tipo": "TI",
        "categoria": ti["modalidade"],
        "grupo": "Terra Indígena",
        "esfera": "Federal",
        "gestor": ti["cr"],
        "etnia": ti["etnia_nome"],
        "fase": ti["fase_ti"],
        "pl_manejo": None,
        "quali_pol": None,
        "uf": ti["uf_sigla"].map(uf_siglas),
        "limite_aproximado": False,
    }, geometry=ti.geometry, crs=ti.crs)
    g = gpd.GeoDataFrame(pd.concat([u, t], ignore_index=True), crs=uc.crs)
    g["area_km2"] = (g.geometry.area / 1e6).round(3)
    return g[COLUNAS]


def main():
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    uc, ti, cerrado = ler()
    print(f"[A9] lidos: {len(uc)} UCs, {len(ti)} TIs")

    uc = uc[uc.intersects(cerrado)]
    ti = ti[ti.intersects(cerrado)]
    print(f"[A9] tocam o Cerrado: {len(uc)} UCs + {len(ti)} TIs = {len(uc) + len(ti)}")

    g = padronizar(uc, ti)
    assert g["id_territorio"].is_unique, "id_territorio repetido"

    # versão completa em metros, para o A10
    g.to_parquet(DESTINO_5880)

    # versão leve para o app: simplifica 100 m em metros, depois vai para lat/lon
    tol = float(cfg()["territorio_simplificar_m"])
    leve = g.copy()
    leve["geometry"] = leve.geometry.simplify(tol, preserve_topology=True)
    leve["geometry"] = leve.geometry.make_valid()
    leve = leve.to_crs(4326)
    if DESTINO.exists():
        DESTINO.unlink()
    leve.to_file(DESTINO, driver="GeoJSON", COORDINATE_PRECISION=5)

    mb = DESTINO.stat().st_size / 1e6
    print(f"[A9] {DESTINO.name}: {len(leve)} territórios, {mb:.1f} MB")
    print(g.groupby(["tipo", "grupo"]).size().to_string())
    print(f"[A9] limite aproximado: {int(g['limite_aproximado'].sum())} | "
          f"área < {cfg()['territorio_area_min_km2']} km²: "
          f"{int((g['area_km2'] < cfg()['territorio_area_min_km2']).sum())}")


if __name__ == "__main__":
    main()
