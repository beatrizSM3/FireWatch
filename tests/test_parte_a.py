"""Confere os arquivos da Parte A (saida/) contra o contrato de dados e o "Pronto quando"
de cada passo do PLANO_DIVIDIDO. Leve em memória: o DuckDB conta direto no disco.

    ./rodar.sh -m pytest tests -q
"""
import json

import duckdb
import pytest
from shapely.geometry import box

from firewatch.config import SAIDA, cfg

OBS = f"'{SAIDA}/observacoes/*/*.parquet'"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.execute("SET memory_limit='1GB'")
    return c


def colunas(con, arquivo):
    return set(con.execute(f"DESCRIBE SELECT * FROM {arquivo}").df().column_name)


def um(con, sql):
    return con.execute(sql).fetchone()


CONTRATO = {
    OBS: "id_obs satelite sensor produto lat lon x y datetime_utc data_local frp "
         "confianca daynight scan track",
    f"'{SAIDA}/disponibilidade.parquet'": "data_local status_snpp status_n20 status_modis referencia",
    f"'{SAIDA}/fontes_fixas.parquet'": "gx gy type_max",
    f"'{SAIDA}/celulas_base.parquet'": "gx gy data_local ativa_snpp ativa_n20 ativa_modis produto",
    f"'{SAIDA}/celula_territorio.parquet'": "gx gy id_territorio zona",
}


@pytest.mark.parametrize("arquivo,cols", CONTRATO.items(), ids=lambda v: str(v)[-30:])
def test_colunas_do_contrato(con, arquivo, cols):
    assert set(cols.split()) <= colunas(con, arquivo)


# A3/A5 — observações
def test_observacoes_anos_e_datas(con):
    ini, fim = cfg()["data_inicio_dados"], cfg()["data_fim_dados"]
    dmin, dmax, anos = um(con, f"""SELECT min(data_local), max(data_local),
        count(DISTINCT year(data_local)) FROM {OBS}""")
    assert str(dmin) == ini and str(dmax) == fim
    assert anos == int(fim[:4]) - int(ini[:4]) + 1


def test_observacoes_fracao_mantida(con):
    n = um(con, f"SELECT count(*) FROM {OBS}")[0]
    assert 0.85 * 28.4e6 <= n <= 0.91 * 28.4e6       # ~85-90% de 28,4 milhões


def test_observacoes_id_unico_e_sem_coordenada_ruim(con):
    n, ids, ruins = um(con, f"""SELECT count(*), count(DISTINCT id_obs),
        count(*) FILTER (WHERE NOT isfinite(x) OR NOT isfinite(y)) FROM {OBS}""")
    assert n == ids and ruins == 0


# A6 — disponibilidade
def test_disponibilidade_calendario_completo(con):
    n, ini, fim = um(con, f"SELECT count(*), min(data_local), max(data_local) "
                          f"FROM '{SAIDA}/disponibilidade.parquet'")
    assert (fim - ini).days + 1 == n


def test_disponibilidade_lacuna_snpp_2022(con):
    ok, total = um(con, f"""SELECT count(*) FILTER (WHERE status_snpp='ausente' AND referencia='n20'),
        count(*) FROM '{SAIDA}/disponibilidade.parquet'
        WHERE data_local BETWEEN '2022-07-27' AND '2022-08-10'""")
    assert ok == total == 15


# A7 — fontes fixas
def test_fontes_fixas_dezenas_de_milhares(con):
    assert 10_000 <= um(con, f"SELECT count(*) FROM '{SAIDA}/fontes_fixas.parquet'")[0] <= 100_000


# A8 — células-dia
def test_celulas_base_unicas_e_com_satelite(con):
    n, unicas, sem_sat = um(con, f"""SELECT count(*), count(DISTINCT (gx, gy, data_local)),
        count(*) FILTER (WHERE NOT (ativa_snpp OR ativa_n20 OR ativa_modis))
        FROM '{SAIDA}/celulas_base.parquet'""")
    assert n == unicas and sem_sat == 0


# A9 — territórios
def test_territorios_geojson():
    g = json.load(open(SAIDA / "territorios.geojson", encoding="utf-8"))
    props = [f["properties"] for f in g["features"]]
    assert len(props) == 811
    assert sum(p["tipo"] == "UC" for p in props) == 687
    assert len({p["id_territorio"] for p in props}) == 811
    pedidas = set("id_territorio nome tipo categoria grupo esfera gestor etnia fase "
                  "pl_manejo quali_pol area_km2".split())
    assert pedidas <= set(props[0])
    assert (SAIDA / "territorios.geojson").stat().st_size < 10e6


# A10 — células de cada território
def test_celula_territorio_dentro_parecido_com_area(con):
    g = json.load(open(SAIDA / "territorios.geojson", encoding="utf-8"))
    area = {f["properties"]["id_territorio"]: f["properties"]["area_km2"] for f in g["features"]}
    df = con.execute(f"""SELECT id_territorio, count(*) n FROM '{SAIDA}/celula_territorio.parquet'
                         WHERE zona='dentro' GROUP BY 1""").df()
    df["area"] = df.id_territorio.map(area)
    grandes = df[df.area >= 100]
    razao = (grandes.n / grandes.area).median()
    assert 0.97 <= razao <= 1.03


# A11 — focos da área
def test_focos_da_area_50km_setembro_2024():
    from firewatch.focos import focos_da_area
    df = focos_da_area(box(-46.9, -10.6, -46.45, -10.15), "2024-09-01", "2024-09-30")
    assert len(df) > 0 and not df.attrs["truncado"]
    assert df.data_local.min().isoformat() >= "2024-09-01"
    assert {"latitude", "longitude", "satelite", "sensor", "produto", "data_local"} <= set(df.columns)
