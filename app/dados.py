"""Camada de dados do app: a área escolhida, leituras com cache e o agrupamento do mapa.

Nenhum indicador é calculado aqui: os números vêm de `firewatch.indicadores` e
`firewatch.territorios`. Este módulo só (1) descobre QUAL recorte ler e (2) agrupa as
células de 1 km em hexágonos para desenhar o mapa.

A área atual é descrita por uma string `chave`, que também vai para a URL (?a=...):
    UC-0000.17.1486 / TI-24801   território (UC ou TI)
    cerrado                      o bioma inteiro
    pt:-10.5,-47.2,25            ponto (lat, lon) + raio em km
    geo:<hash>                   polígono desenhado (guardado no servidor)
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import streamlit as st
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape

from firewatch import carregar, indicadores as ind, territorios as terr
from firewatch.config import RAW, cfg, conectar_duckdb
from firewatch.focos import focos_da_area

from estilo import nome_bonito

CELULAS_DIA = carregar.CELULAS_DIA
CELULA_TERRITORIO = carregar.CELULA_TERRITORIO
CHAVE_PADRAO = "UC-0000.17.1486"          # Parque Estadual do Jalapão
FIM = pd.Timestamp(cfg()["data_fim_dados"])
ANO_ATUAL = int(cfg()["ano_em_curso"])
ANOS = list(range(int(cfg()["periodo_historico"][0]), ANO_ATUAL + 1))

_local = threading.local()


def _con():
    con = getattr(_local, "con", None)
    if con is None:
        con = _local.con = conectar_duckdb()
    return con


# --------------------------------------------------------------------------- a área

@dataclass(frozen=True)
class Area:
    chave: str
    tipo: str               # territorio | cerrado | ponto | desenho
    nome: str
    geojson: str | None     # geometria em lat/lon (string, para servir de chave de cache)
    area_km2: float | None

    @property
    def territorio(self) -> bool:
        return self.tipo == "territorio"


@st.cache_resource
def _geometrias_desenhadas() -> dict:
    """Polígonos desenhados, por hash: assim a URL ?a=geo:<hash> funciona sem guardar o
    polígono inteiro nela."""
    return {}


def guardar_desenho(geojson_geom: dict) -> str:
    texto = json.dumps(geojson_geom, sort_keys=True)
    h = hashlib.sha1(texto.encode()).hexdigest()[:10]
    _geometrias_desenhadas()[h] = texto
    return f"geo:{h}"


def _area_km2(geom) -> float:
    return float(gpd.GeoSeries([geom], crs=4326).to_crs(cfg()["crs_metros"]).area.iloc[0] / 1e6)


def circulo(lat: float, lon: float, raio_km: float):
    p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(cfg()["crs_metros"])
    return p.buffer(raio_km * 1000, quad_segs=24).to_crs(4326).iloc[0]


@st.cache_data(show_spinner=False)
def territorios_lista() -> pd.DataFrame:
    """Territórios para a busca: id, rótulo, tipo, uf, área."""
    t = carregar.territorios().drop(columns="geometry")
    t = t.assign(nome_exib=t["nome"].map(nome_bonito))
    t["rotulo"] = t["nome_exib"] + " · " + t["tipo"] + " · " + t["uf"].fillna("")
    return t.sort_values("nome_exib")[["id_territorio", "rotulo", "nome_exib", "tipo", "uf",
                                       "area_km2"]].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def geojson_territorio(id_territorio: str) -> str:
    t = carregar.territorios()
    return json.dumps(mapping(t.loc[t.id_territorio == id_territorio, "geometry"].iloc[0]))


@st.cache_data(show_spinner=False)
def geojson_cerrado() -> str | None:
    shp = RAW / "biome_border" / "biome_border.shp"
    if not shp.exists():
        return None
    g = gpd.read_file(shp).to_crs(4326)
    # fecha frestas entre partes do polígono e simplifica: só o contorno externo do bioma
    return json.dumps(mapping(g.union_all().buffer(0.05).buffer(-0.05).simplify(0.04)))


def resolver_area(chave: str | None) -> Area:
    """Transforma a chave da URL numa Area. Chave inválida cai no território padrão."""
    chave = chave or CHAVE_PADRAO
    try:
        if chave == "cerrado":
            return Area("cerrado", "cerrado", "Cerrado", geojson_cerrado(), None)
        if chave.startswith("pt:"):
            lat, lon, raio = (float(x) for x in chave[3:].split(","))
            g = circulo(lat, lon, raio)
            return Area(chave, "ponto", f"Raio de {raio:g} km em {lat:.2f}, {lon:.2f}",
                        json.dumps(mapping(g)), _area_km2(g))
        if chave.startswith("geo:"):
            texto = _geometrias_desenhadas()[chave[4:]]
            g = shape(json.loads(texto))
            return Area(chave, "desenho", "Área desenhada", texto, _area_km2(g))
        info = carregar.territorio(chave)
        return Area(chave, "territorio", nome_bonito(info["nome"]), geojson_territorio(chave),
                    float(info["area_km2"]))
    except Exception:
        if chave == CHAVE_PADRAO:
            raise
        return resolver_area(CHAVE_PADRAO)


# --------------------------------------------------------------------------- séries

@st.cache_data(show_spinner=False, max_entries=64)
def serie(chave: str, tipo: str, geojson: str | None, zona: str = "dentro") -> pd.DataFrame:
    """Série diária da área (uma linha por dia com fogo). Entrada de todos os indicadores."""
    if tipo == "territorio":
        return carregar.serie_do_territorio(chave, zona)
    if tipo == "cerrado":
        return carregar.serie_do_cerrado()
    return carregar.serie_da_geometria(json.loads(geojson))


def serie_area(a: Area) -> pd.DataFrame:
    return serie(a.chave, a.tipo, a.geojson)


@st.cache_data(show_spinner=False, max_entries=64)
def ficha(chave: str) -> dict:
    return carregar.territorio(chave)


@st.cache_data(show_spinner=False, max_entries=32)
def dentro_entorno_anos(chave: str) -> pd.DataFrame:
    """terr.dentro_entorno para cada ano (até a data de hoje no ano em curso)."""
    linhas = [terr.dentro_entorno(chave, a) for a in ANOS]
    return pd.DataFrame(linhas)


@st.cache_data(show_spinner=False)
def disponibilidade() -> pd.DataFrame:
    return carregar.disponibilidade()


@st.cache_data(show_spinner=False)
def alerta() -> pd.DataFrame:
    a = carregar.alerta_territorios().copy()
    a["nome_exib"] = a["nome"].map(nome_bonito)
    return a


@st.cache_data(show_spinner=False)
def deriva() -> pd.DataFrame:
    return carregar.deriva()


@st.cache_data(show_spinner=False)
def validacao() -> pd.DataFrame | None:
    """validacao.csv da Pessoa D, se já existir."""
    p = carregar.SAIDA / "validacao.csv"
    return pd.read_csv(p) if p.exists() else None


# --------------------------------------------------------------------------- mapa

def _bloco(a: Area) -> int:
    """Tamanho do bloco de agregação no DuckDB (em células de 1 km)."""
    if a.tipo == "cerrado":
        return 8
    if a.area_km2 and a.area_km2 > 60_000:
        return 4
    return 1


@st.cache_data(show_spinner=False, max_entries=48)
def celulas_mes(chave: str, tipo: str, geojson: str | None, mes: int, ate_dia: int,
                bloco: int) -> pd.DataFrame:
    """Σ cdev por bloco de células × ano, no mês `mes` (dias 1..ate_dia) de todos os anos.
    Só leitura e soma, para desenhar; os indicadores vêm de `firewatch.indicadores`."""
    con = _con()
    sel = f"""SELECT (c.gx // {bloco}) AS bx, (c.gy // {bloco}) AS by,
                     year(c.data_local) AS ano, sum(c.cdev) AS cdev
              FROM '{CELULAS_DIA}' c"""
    filtro = "month(c.data_local) = ? AND day(c.data_local) <= ?"
    if tipo == "territorio":
        sql = f"""{sel} JOIN (SELECT gx, gy FROM '{CELULA_TERRITORIO}'
                              WHERE id_territorio = ? AND zona = 'dentro') t USING (gx, gy)
                  WHERE {filtro} GROUP BY ALL"""
        return con.execute(sql, [chave, mes, ate_dia]).df()
    if tipo == "cerrado":
        return con.execute(f"{sel} WHERE c.no_cerrado AND {filtro} GROUP BY ALL",
                           [mes, ate_dia]).df()
    # geometria: descobre as células da área (centro dentro do polígono) e soma só elas
    geom = shape(json.loads(geojson))
    geom_m = gpd.GeoSeries([geom], crs=4326).to_crs(cfg()["crs_metros"]).iloc[0]
    L = float(cfg()["celula_m"])
    x0, y0, x1, y1 = geom_m.bounds
    cel = con.execute(f"""SELECT DISTINCT gx, gy FROM '{CELULAS_DIA}'
                          WHERE gx BETWEEN ? AND ? AND gy BETWEEN ? AND ?""",
                      [int(x0 // L), int(x1 // L), int(y0 // L), int(y1 // L)]).df()
    if cel.empty:
        return pd.DataFrame(columns=["bx", "by", "ano", "cdev"])
    cel = cel[shapely.contains_xy(geom_m, cel.gx * L + L / 2, cel.gy * L + L / 2)]
    con.register("_area_mapa", cel)
    try:
        return con.execute(f"{sel} JOIN _area_mapa USING (gx, gy) WHERE {filtro} GROUP BY ALL",
                           [mes, ate_dia]).df()
    finally:
        con.unregister("_area_mapa")


_PARA_LATLON = Transformer.from_crs(cfg()["crs_metros"], 4326, always_xy=True)
_PARA_METROS = Transformer.from_crs(4326, cfg()["crs_metros"], always_xy=True)


def hexagonos(df: pd.DataFrame, bloco: int, extensao_m: float, valor: str) -> tuple[dict, pd.DataFrame]:
    """Agrupa os blocos de células em hexágonos (lado adaptado ao tamanho da área).
    Devolve (FeatureCollection GeoJSON, DataFrame id/valor)."""
    if df.empty:
        return {"type": "FeatureCollection", "features": []}, pd.DataFrame(columns=["id", valor])
    L = float(cfg()["celula_m"]) * bloco
    s = max(L * 0.75, extensao_m / 42)                  # raio do hexágono (m)
    x = (df["bx"].to_numpy() + 0.5) * L
    y = (df["by"].to_numpy() + 0.5) * L
    # coordenadas axiais (hexágono "em pé") e arredondamento cúbico
    q = (math.sqrt(3) / 3 * x - y / 3) / s
    r = (2 / 3 * y) / s
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    trocar_x = (dx > dy) & (dx > dz)
    trocar_y = ~trocar_x & (dy > dz)
    rx = np.where(trocar_x, -ry - rz, rx)
    rz = np.where(~trocar_x & ~trocar_y, -rx - ry, rz)
    d = df.assign(hq=rx.astype(int), hr=rz.astype(int))
    g = d.groupby(["hq", "hr"], as_index=False)[valor].sum() if valor in d else d
    g["id"] = g["hq"].astype(str) + "_" + g["hr"].astype(str)
    hx = s * math.sqrt(3) * (g["hq"] + g["hr"] / 2)
    hy = s * 1.5 * g["hr"]
    ang = np.deg2rad(np.arange(6) * 60 + 30)
    vx = hx.to_numpy()[:, None] + s * 0.97 * np.cos(ang)[None, :]
    vy = hy.to_numpy()[:, None] + s * 0.97 * np.sin(ang)[None, :]
    lon, lat = _PARA_LATLON.transform(vx, vy)
    feats = []
    for i, hid in enumerate(g["id"]):
        anel = [[float(lon[i, k]), float(lat[i, k])] for k in range(6)]
        anel.append(anel[0])
        feats.append({"type": "Feature", "id": hid, "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [anel]}})
    return {"type": "FeatureCollection", "features": feats}, g


def mapa_hex(a: Area, ano: int, mes: int, modo: str) -> tuple[dict, pd.DataFrame]:
    """Hexágonos do mês em foco. modo='fogo': Σ cdev no mês do ano escolhido.
    modo='anomalia': valor do ano − mediana do mesmo período em 2019–2025 (sem o ano)."""
    ate_dia = FIM.day if (ano, mes) == (FIM.year, FIM.month) else 31
    bloco = _bloco(a)
    df = celulas_mes(a.chave, a.tipo, a.geojson, mes, ate_dia, bloco)
    ext = extensao_m(a)
    if modo == "fogo":
        return hexagonos(df[df.ano == ano], bloco, ext, "cdev")
    # anomalia: precisa de hexágonos por ano; agrupa primeiro e depois compara
    fc, _ = hexagonos(df, bloco, ext, "cdev")
    if df.empty:
        return fc, pd.DataFrame(columns=["id", "anomalia"])
    por_ano = _hex_por_ano(df, bloco, ext)
    a0, a1 = (int(v) for v in cfg()["periodo_historico"])
    tab = por_ano.pivot_table(index="id", columns="ano", values="cdev", fill_value=0)
    for y in range(a0, a1 + 1):
        if y not in tab:
            tab[y] = 0
    hist = [y for y in range(a0, a1 + 1) if y != ano]
    atual = tab[ano] if ano in tab else 0
    out = pd.DataFrame({"id": tab.index, "atual": np.asarray(atual, dtype=float),
                        "mediana": tab[hist].median(axis=1).to_numpy()})
    out["anomalia"] = out["atual"] - out["mediana"]
    return fc, out[out["anomalia"] != 0]       # hexágonos iguais à mediana ficam sem cor


def _hex_por_ano(df, bloco, ext) -> pd.DataFrame:
    """Σ cdev por hexágono × ano (os ids dos hexágonos são os mesmos em todos os anos)."""
    partes = [hexagonos(sub, bloco, ext, "cdev")[1].assign(ano=y) for y, sub in df.groupby("ano")]
    return pd.concat(partes, ignore_index=True)


@st.cache_data(show_spinner=False)
def _extensao(chave: str, geojson: str | None) -> float:
    if not geojson:
        return 1_500_000.0
    g = gpd.GeoSeries([shape(json.loads(geojson))], crs=4326).to_crs(cfg()["crs_metros"]).iloc[0]
    x0, y0, x1, y1 = g.bounds
    return float(max(x1 - x0, y1 - y0))


def extensao_m(a: Area) -> float:
    return _extensao(a.chave, a.geojson)


def limites(a: Area) -> tuple[float, float, float, float]:
    """(lon0, lat0, lon1, lat1) da área, com o entorno de 10 km nos territórios."""
    if not a.geojson:
        return (-60.5, -24.7, -41.3, -2.3)
    g = shape(json.loads(a.geojson))
    if a.territorio:
        g = entorno_geom(a.chave) or g
    return g.bounds


@st.cache_data(show_spinner=False, max_entries=64)
def _entorno_geojson(chave: str) -> str | None:
    g = shape(json.loads(geojson_territorio(chave)))
    s = gpd.GeoSeries([g], crs=4326).to_crs(cfg()["crs_metros"])
    anel = s.buffer(float(cfg()["territorio_entorno_m"])).difference(s).to_crs(4326).iloc[0]
    return json.dumps(mapping(anel.simplify(0.002)))


def entorno_geom(chave: str):
    t = _entorno_geojson(chave)
    return shape(json.loads(t)) if t else None


def entorno_geojson(chave: str) -> str | None:
    return _entorno_geojson(chave)


@st.cache_data(show_spinner=False, max_entries=16)
def focos(geojson: str, inicio: str, fim: str, limite: int = 200_000) -> pd.DataFrame:
    """Focos originais (todos os satélites) da área e período: CSV e camada "Focos"."""
    return focos_da_area(json.loads(geojson), inicio, fim, limite=limite)


def periodo_mes(ano: int, mes: int) -> tuple[str, str]:
    ini = pd.Timestamp(ano, mes, 1)
    fim = min(ini + pd.offsets.MonthEnd(0), FIM)
    return str(ini.date()), str(fim.date())


# --------------------------------------------------------------------------- indicadores (atalhos com cache)

@st.cache_data(show_spinner=False, max_entries=64)
def pacote(chave: str, tipo: str, geojson: str | None, ano: int, mes: int) -> dict:
    """Os indicadores da tela principal, numa chamada com cache."""
    s = serie(chave, tipo, geojson)
    out = {"vazio": s.empty}
    if s.empty:
        return out
    out["ano_em_curso"] = ind.ano_em_curso(s)
    try:
        out["termometro"] = ind.termometro(s, ano, mes)
    except ValueError:
        out["termometro"] = None
    out["janela"] = ind.janela_critica(s)
    try:
        out["ritmo"] = ind.ritmo_do_ano(s, ANO_ATUAL)
    except ValueError:
        out["ritmo"] = None
    out["mensal"] = ind.calendario_mensal(s)
    out["semanal"] = ind.calendario_semanal(s)
    return out
