"""Confere a Parte B: arquivos de saida/ gerados pelos scripts b1..b5 (contrato + "Pronto
quando" do PLANO_DIVIDIDO) e as funções de firewatch.indicadores (com dados sintéticos e
reais).

    ./rodar.sh -m pytest tests -q
"""
import duckdb
import numpy as np
import pandas as pd
import pytest

from firewatch import carregar
from firewatch import indicadores as ind
from firewatch import territorios as terr
from firewatch.config import SAIDA, cfg

CANTAO = "UC-0000.17.1487"   # Parque Estadual do Cantão (TO), 1.006 km²


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.execute("SET memory_limit='1GB'")
    return c


def colunas(con, arquivo):
    return set(con.execute(f"DESCRIBE SELECT * FROM '{arquivo}'").df().column_name)


# --------------------------------------------------------------------------- contrato

CONTRATO = {
    "fatores.parquet": "mes regiao_id f f_min f_max n_anos n_celulas_dia nivel",
    "celulas_dia.parquet": "gx gy data_local cdev cdev_min cdev_max fonte produto "
                           "ativa_snpp ativa_n20 ativa_modis",
    "deriva.csv": "ano mes cdev_viirs cdev_modis_calibrado erro_pct",
    "alerta_territorios.parquet": "id_territorio cdev_2026 posicao n_anos classificacao "
                                  "densidade_2026 densidade_mediana fracao_tardia_2026 "
                                  "razao_dentro_entorno",
}


@pytest.mark.parametrize("arquivo,cols", CONTRATO.items(), ids=list(CONTRATO))
def test_colunas_do_contrato(con, arquivo, cols):
    assert set(cols.split()) <= colunas(con, SAIDA / arquivo)


# --------------------------------------------------------------------------- B3 fatores

def test_fatores_validos_e_completos(con):
    f = pd.read_parquet(SAIDA / "fatores.parquet")
    assert (f.f > 0).all() and np.isfinite(f.f).all() and (f.f_min <= f.f).all() and (f.f <= f.f_max).all()
    assert f.groupby("regiao_id").mes.nunique().eq(12).all()           # 12 meses por região
    assert set(f.nivel) <= {"regiao", "cerrado", "nacional"}
    nac = pd.read_csv(SAIDA / "fatores_agregados.csv").query("escopo == 'brasil'")
    assert 1.5 <= nac.f.median() <= 3.5                                 # MODIS vê cerca de metade


# --------------------------------------------------------------------------- B4 celulas_dia

def test_celulas_dia_mesmas_linhas_de_celulas_base(con):
    n_base = con.execute(f"SELECT count(*) FROM '{SAIDA}/celulas_base.parquet'").fetchone()[0]
    n, nulos, fora = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE cdev IS NULL),
               count(*) FILTER (WHERE fonte = 'viirs' AND cdev NOT IN (0, 1))
        FROM '{SAIDA}/celulas_dia.parquet'""").fetchone()
    assert n == n_base and nulos == 0 and fora == 0


def test_celulas_dia_cdev_segue_a_referencia(con):
    # em dia com referencia snpp, cdev == ativa_snpp; em dia n20, cdev == ativa_n20
    ruins = con.execute(f"""
        SELECT count(*) FROM '{SAIDA}/celulas_dia.parquet' c
        JOIN '{SAIDA}/disponibilidade.parquet' d USING (data_local)
        WHERE (d.referencia = 'snpp' AND c.cdev <> c.ativa_snpp::INT)
           OR (d.referencia = 'n20'  AND c.cdev <> c.ativa_n20::INT)""").fetchone()[0]
    assert ruins == 0


def test_celulas_dia_cerrado_perto_do_snpp(con):
    # "Pronto quando" do B4: soma de cdev por ano no Cerrado ~ células-dia do S-NPP
    df = con.execute(f"""SELECT year(data_local) ano, sum(cdev) cdev, sum(ativa_snpp::INT) snpp
                         FROM '{SAIDA}/celulas_dia.parquet' WHERE no_cerrado GROUP BY 1""").df()
    assert ((df.cdev / df.snpp).between(0.95, 1.10)).all()


# --------------------------------------------------------------------------- B5 deriva

def test_deriva_pequena_na_calibracao_e_maior_depois():
    d = pd.read_csv(SAIDA / "deriva.csv").query("area == 'brasil'")
    anual = d.groupby("ano").apply(
        lambda g: (g.cdev_modis_calibrado.sum() - g.cdev_viirs.sum()) / g.cdev_viirs.sum() * 100,
        include_groups=False)
    a0, a1 = cfg()["calibracao_anos"]
    cal = anual[(anual.index >= a0) & (anual.index <= a1)]
    depois = anual[anual.index > a1]
    assert cal.abs().max() < 5
    assert depois.abs().mean() > cal.abs().mean()


# --------------------------------------------------------------------------- B7 alerta

def test_alerta_um_por_territorio_grande():
    a = pd.read_parquet(SAIDA / "alerta_territorios.parquet")
    t = carregar.territorios()
    assert len(a) == (t.area_km2 >= cfg()["territorio_area_min_km2"]).sum()
    assert a.id_territorio.is_unique
    assert set(a.classificacao) <= {"recorde (acima do máximo histórico)", "acima da mediana",
                                    "abaixo da mediana", "abaixo do mínimo histórico",
                                    "sem histórico comparável"}
    assert a.fracao_tardia_2026.dropna().between(0, 1).all()


# --------------------------------------------------------------------------- indicadores (sintético)

def _disp(dias, na=()):
    d = pd.DataFrame({"data_local": pd.to_datetime(dias).date})
    d["referencia"] = ["snpp"] * len(d)
    d.loc[d.data_local.isin(pd.to_datetime(list(na)).date), "referencia"] = None
    return d


def test_classificar():
    assert ind.classificar(10, [1, 2, 3])["classificacao"].startswith("recorde")
    assert ind.classificar(0, [1, 2, 3])["classificacao"] == "abaixo do mínimo histórico"
    r = ind.classificar(2.5, [1, 2, 3])
    assert r["classificacao"] == "acima da mediana" and r["posicao_texto"] == "2º de 4"
    assert ind.classificar(2, [1, 2, 3])["classificacao"] == "abaixo da mediana"
    assert ind.classificar(5, [])["classificacao"] == "sem histórico comparável"


def test_serie_diaria_zero_e_na_sao_diferentes():
    dias = pd.date_range("2019-01-01", "2019-01-05")
    disp = _disp(dias, na=["2019-01-03"])
    cel = pd.DataFrame({"gx": [1, 1, 2], "gy": [1, 1, 1],
                        "data_local": pd.to_datetime(["2019-01-01", "2019-01-01", "2019-01-05"]).date,
                        "cdev": [1.0, 1.0, 1.0]})
    s = ind.serie_diaria(cel, disp, "2019-01-01", "2019-01-05")
    assert list(s.cdev.fillna(-1)) == [2.0, 0.0, -1.0, 0.0, 1.0]       # dia 2 = zero, dia 3 = NA
    assert list(s.na) == [False, False, True, False, False]
    assert list(s.celulas_ativas) == [2, 0, 0, 0, 1]


def test_fracao_tardia_e_ano_em_curso_sinteticos(monkeypatch):
    dias = pd.date_range("2019-01-01", "2021-12-31")
    disp = _disp(dias)
    # 2019: 10 antes do corte, 10 depois; 2020: 10 antes, 30 depois; 2021: 10 antes, 20 depois
    linhas = []
    for ano, depois in [(2019, 10), (2020, 30), (2021, 20)]:
        linhas += [(f"{ano}-03-01", 10.0), (f"{ano}-09-01", float(depois))]
    cel = pd.DataFrame(linhas, columns=["data_local", "cdev"])
    cel["data_local"] = pd.to_datetime(cel.data_local).dt.date
    cel["gx"] = 0; cel["gy"] = 0
    monkeypatch.setitem(cfg(), "periodo_historico", [2019, 2021])
    monkeypatch.setitem(cfg(), "data_inicio_dados", "2019-01-01")
    monkeypatch.setitem(cfg(), "data_fim_dados", "2021-12-31")
    monkeypatch.setitem(cfg(), "ano_em_curso", 2021)
    r = ind.fracao_tardia(cel, 2020, disponibilidade=disp)
    assert r["fracao"] == pytest.approx(0.75) and r["classificacao"].startswith("recorde")
    a = ind.ano_em_curso(cel, data_fim="2021-06-30", ano=2021, disponibilidade=disp)
    assert a["valor"] == 10 and a["mediana"] == 10 and a["classificacao"] == "abaixo da mediana"


# --------------------------------------------------------------------------- indicadores (real)

def test_cerrado_setembro_2024_recorde():
    s = carregar.serie_do_cerrado()
    t = ind.termometro(s, 2024, 9)
    assert t["posicao"] == 1 and t["classificacao"].startswith("recorde")
    assert 1.3 <= ind.contagem_honesta(s)["razao"] <= 1.7                 # auditoria: 1,33–1,67


def test_termometro_mes_parcial_compara_ate_o_mesmo_dia():
    s = carregar.serie_do_cerrado()
    t = ind.termometro(s, 2026, 11)
    assert t["parcial"] and t["ate_dia"] == 14 and t["nrt"]
    assert (t["por_ano"].dias == 14).all()


def test_territorio_cantao():
    cel = carregar.celulas_do_territorio(CANTAO)
    assert len(cel) > 0 and {"cdev", "ativa_snpp", "produto"} <= set(cel.columns)
    de = terr.dentro_entorno(CANTAO, 2024)
    assert de["razao"] is not None and de["area_entorno_km2"] > 0
    r = terr.resumo(CANTAO)
    assert r["ficha"]["nome"].startswith("PARQUE ESTADUAL DO CANT")
    assert r["ano_em_curso"]["n_anos"] == 8
