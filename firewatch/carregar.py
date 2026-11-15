"""Parte B: leitura dos arquivos de saida/ e recorte por área (o que NÃO é cálculo).

Para a Pessoa C: tudo que o app mostra começa aqui e termina em `firewatch.indicadores`.

    from firewatch import carregar, indicadores as ind

    cel = carregar.celulas_do_territorio("UC-0000.17.1487")      # linhas célula × dia
    ind.termometro(cel, 2024, 9)
    ind.calendario_mensal(cel)

    cel = carregar.celulas_da_geometria(poligono_em_lat_lon)       # área desenhada / círculo
    serie = carregar.serie_do_cerrado()                            # Cerrado inteiro (já por dia)
    serie = carregar.serie_do_brasil()

Por que duas formas (célula × dia e série diária)? Um território tem poucas células; o
Cerrado inteiro tem milhões de linhas célula × dia. Para áreas grandes a soma por dia é
feita no DuckDB e só a série (uma linha por dia) vem para o pandas. As funções de
`indicadores` aceitam as duas formas.

Todas as leituras passam pelo DuckDB com o limite de memória do config.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from firewatch.config import SAIDA, cfg, conectar_duckdb

CELULAS_DIA = SAIDA / "celulas_dia.parquet"
CELULA_TERRITORIO = SAIDA / "celula_territorio.parquet"
DISPONIBILIDADE = SAIDA / "disponibilidade.parquet"
TERRITORIOS = SAIDA / "territorios.geojson"
ALERTA = SAIDA / "alerta_territorios.parquet"
FATORES = SAIDA / "fatores.parquet"
DERIVA = SAIDA / "deriva.csv"

# colunas de celulas_dia que as funções de indicadores usam
COLUNAS_CELULAS = ("gx, gy, data_local, cdev, cdev_min, cdev_max, cdev_modis, fonte, produto, "
                   "ativa_snpp, ativa_n20, ativa_modis, regiao_id, no_cerrado")

# soma por dia feita no DuckDB — mesmas colunas que indicadores.serie_diaria produz
_SQL_SERIE = """
    SELECT data_local,
           sum(cdev)                 AS cdev,
           sum(cdev_min)             AS cdev_min,
           sum(cdev_max)             AS cdev_max,
           sum(ativa_snpp::INT)      AS snpp,
           sum(ativa_n20::INT)       AS n20,
           sum(ativa_modis::INT)     AS modis_bruto,
           sum(cdev_modis)           AS modis_calibrado,
           bool_or(produto = 'nrt')  AS nrt,
           count(*)                  AS celulas_ativas
    FROM '{arquivo}' c {where}
    GROUP BY data_local ORDER BY data_local
"""

# uma conexão DuckDB POR THREAD: o Streamlit atende cada usuário numa thread, e uma
# conexão compartilhada não aguenta consultas simultâneas.
_local = threading.local()


def _conexao():
    con = getattr(_local, "con", None)
    if con is None:
        con = _local.con = conectar_duckdb()
    return con


# --------------------------------------------------------------------------- tabelas inteiras

@lru_cache
def disponibilidade() -> pd.DataFrame:
    """Uma linha por dia: status de cada satélite e `referencia` (snpp/n20/modis/None)."""
    return pd.read_parquet(DISPONIBILIDADE)


@lru_cache
def territorios() -> gpd.GeoDataFrame:
    """Os 811 territórios (UCs e TIs do Cerrado), EPSG:4326, geometria simplificada."""
    return gpd.read_file(TERRITORIOS)


def territorio(id_territorio: str) -> dict:
    """Ficha de um território (as propriedades do geojson) como dict."""
    t = territorios()
    linha = t[t.id_territorio == id_territorio]
    if linha.empty:
        raise KeyError(f"território não encontrado: {id_territorio}")
    return linha.drop(columns="geometry").iloc[0].to_dict()


@lru_cache
def alerta_territorios() -> pd.DataFrame:
    """Painel de alerta: uma linha por território com área >= territorio_area_min_km2."""
    return pd.read_parquet(ALERTA)


@lru_cache
def fatores() -> pd.DataFrame:
    """Fatores MODIS -> VIIRS por (mes, regiao_id)."""
    return pd.read_parquet(FATORES)


@lru_cache
def deriva() -> pd.DataFrame:
    """Erro do MODIS calibrado contra o VIIRS, por ano × mês × área (brasil, cerrado)."""
    return pd.read_csv(DERIVA)


# --------------------------------------------------------------------------- recortes

@lru_cache
def area_entorno_km2(id_territorio: str) -> float:
    """Área do anel de 10 km = número de células `entorno` (1 km² cada)."""
    n = _conexao().execute(
        f"SELECT count(*) FROM '{CELULA_TERRITORIO}' WHERE id_territorio = ? AND zona = 'entorno'",
        [id_territorio]).fetchone()[0]
    return float(n)


def celulas_do_territorio(id_territorio: str, zona: str = "dentro") -> pd.DataFrame:
    """Linhas célula × dia de `celulas_dia` dentro do território (zona='dentro') ou no anel
    de 10 km em volta (zona='entorno'). Territórios com menos de ~2 km² podem não ter
    nenhuma célula 'dentro' (ver README); nesse caso devolve tabela vazia."""
    if zona not in ("dentro", "entorno"):
        raise ValueError("zona deve ser 'dentro' ou 'entorno'")
    return _conexao().execute(f"""
        SELECT {COLUNAS_CELULAS}
        FROM '{CELULAS_DIA}' c
        WHERE EXISTS (SELECT 1 FROM '{CELULA_TERRITORIO}' t
                      WHERE t.gx = c.gx AND t.gy = c.gy
                        AND t.id_territorio = ? AND t.zona = ?)
        ORDER BY data_local, gx, gy
    """, [id_territorio, zona]).df()


def serie_do_territorio(id_territorio: str, zona: str = "dentro") -> pd.DataFrame:
    """Como `celulas_do_territorio`, mas já somado por dia (mais leve)."""
    if zona not in ("dentro", "entorno"):
        raise ValueError("zona deve ser 'dentro' ou 'entorno'")
    where = f"""WHERE EXISTS (SELECT 1 FROM '{CELULA_TERRITORIO}' t
                              WHERE t.gx = c.gx AND t.gy = c.gy
                                AND t.id_territorio = ? AND t.zona = ?)"""
    return _conexao().execute(_SQL_SERIE.format(arquivo=CELULAS_DIA, where=where),
                              [id_territorio, zona]).df()


def _para_shapely(geometria):
    if hasattr(geometria, "geometry") and hasattr(geometria, "crs"):      # GeoDataFrame
        geometria = geometria.geometry
    if hasattr(geometria, "union_all"):                                   # GeoSeries
        if geometria.crs is not None and geometria.crs.to_epsg() != 4326:
            geometria = geometria.to_crs(4326)
        return geometria.union_all()
    if isinstance(geometria, dict):
        return shape(geometria.get("geometry", geometria))
    return geometria


def celulas_da_geometria(geometria) -> pd.DataFrame:
    """Linhas célula × dia cujo CENTRO de célula cai dentro de `geometria` (lat/lon,
    EPSG:4326: shapely, GeoJSON dict, GeoSeries/GeoDataFrame).

    Para áreas muito grandes (um estado inteiro) prefira `serie_da_geometria`.
    """
    geom_m, gx0, gx1, gy0, gy1 = _geometria_em_metros(geometria)
    cand = _conexao().execute(f"""
        SELECT {COLUNAS_CELULAS} FROM '{CELULAS_DIA}'
        WHERE gx BETWEEN ? AND ? AND gy BETWEEN ? AND ?
    """, [gx0, gx1, gy0, gy1]).df()
    if cand.empty:
        return cand
    dentro = _centros_dentro(geom_m, cand["gx"].to_numpy(), cand["gy"].to_numpy())
    return cand[dentro].sort_values(["data_local", "gx", "gy"]).reset_index(drop=True)


def serie_da_geometria(geometria) -> pd.DataFrame:
    """Série diária (uma linha por dia) da área: descobre as células da área uma vez e soma
    no DuckDB. Serve para áreas grandes."""
    geom_m, gx0, gx1, gy0, gy1 = _geometria_em_metros(geometria)
    con = _conexao()
    cel = con.execute(f"""
        SELECT DISTINCT gx, gy FROM '{CELULAS_DIA}'
        WHERE gx BETWEEN ? AND ? AND gy BETWEEN ? AND ?
    """, [gx0, gx1, gy0, gy1]).df()
    if cel.empty:
        return pd.DataFrame(columns=["data_local", "cdev"])
    cel = cel[_centros_dentro(geom_m, cel["gx"].to_numpy(), cel["gy"].to_numpy())]
    con.register("_celulas_area", cel)
    try:
        where = "WHERE (gx, gy) IN (SELECT (gx, gy) FROM _celulas_area)"
        return con.execute(_SQL_SERIE.format(arquivo=CELULAS_DIA, where=where)).df()
    finally:
        con.unregister("_celulas_area")


def serie_do_cerrado() -> pd.DataFrame:
    """Série diária do Cerrado inteiro (células com centro dentro do bioma)."""
    return _conexao().execute(
        _SQL_SERIE.format(arquivo=CELULAS_DIA, where="WHERE no_cerrado")).df()


def serie_do_brasil() -> pd.DataFrame:
    """Série diária do Brasil inteiro."""
    return _conexao().execute(_SQL_SERIE.format(arquivo=CELULAS_DIA, where="")).df()


# --------------------------------------------------------------------------- geometria

def centros_lat_lon(celulas: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta `lon` e `lat` (EPSG:4326) do CENTRO de cada célula, a partir de gx, gy.
    Para desenhar as células no mapa. Ex.: `carregar.centros_lat_lon(cel[cel.data_local == dia])`."""
    from pyproj import Transformer
    L = float(cfg()["celula_m"])
    tr = Transformer.from_crs(cfg()["crs_metros"], 4326, always_xy=True)
    lon, lat = tr.transform(celulas["gx"].to_numpy() * L + L / 2,
                            celulas["gy"].to_numpy() * L + L / 2)
    return celulas.assign(lon=lon, lat=lat)


def _geometria_em_metros(geometria):
    """Geometria em EPSG:5880 e a faixa de índices de célula do seu retângulo envolvente."""
    geom = _para_shapely(geometria)
    if geom is None or geom.is_empty:
        raise ValueError("geometria vazia")
    geom_m = gpd.GeoSeries([geom], crs=4326).to_crs(cfg()["crs_metros"]).iloc[0]
    shapely.prepare(geom_m)
    L = float(cfg()["celula_m"])
    xmin, ymin, xmax, ymax = geom_m.bounds
    return geom_m, int(np.floor(xmin / L)), int(np.floor(xmax / L)), \
        int(np.floor(ymin / L)), int(np.floor(ymax / L))


def _centros_dentro(geom_m, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    L = float(cfg()["celula_m"])
    return shapely.contains_xy(geom_m, gx * L + L / 2, gy * L + L / 2)
