"""Parte B (passos B1, B6, B7) do PLANO_DIVIDIDO: indicadores do FireWatch.

Funções PURAS: entra uma tabela, sai uma tabela ou um dicionário. Nenhuma lê arquivo
(exceto a disponibilidade, quando não é passada — ver `serie_diaria`). Quem busca os dados
de uma área é `firewatch.carregar`.

Entrada comum (`celulas`): um DataFrame com, no mínimo, `data_local` e `cdev`. Pode ser
  * as linhas de `celulas_dia.parquet` já filtradas pela área (uma linha por célula × dia), ou
  * uma série diária já agregada (como devolvem `carregar.serie_do_cerrado()` etc.).
Toda função começa chamando `serie_diaria()`, que aceita as duas formas.

Vocabulário:
  CDeV      células-dia equivalentes a VIIRS (unidade harmonizada; coluna `cdev`).
  NA        dia em que nenhum satélite de referência estava funcionando: NÃO é zero.
  semana    semana do ano = (dia do ano − 1) // 7 + 1, de 1 a 53 (igual em todos os anos).
  histórico anos completos de periodo_historico (config: 2019–2025).

Classificação (usada por termometro, ano_em_curso e fracao_tardia):
  "recorde (acima do máximo histórico)"  valor > máximo dos outros anos
  "abaixo do mínimo histórico"           valor < mínimo dos outros anos
  "acima da mediana"                     valor > mediana
  "abaixo da mediana"                    valor <= mediana
Posição = "2º de 8" (1º = o maior). Mediana, nunca média; posição, nunca percentil
(só 7 anos de histórico).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from firewatch.config import cfg

# colunas numéricas da série diária e como cada uma é agregada por dia
_SOMAS = ["cdev", "cdev_min", "cdev_max", "snpp", "n20", "modis_bruto", "modis_calibrado",
          "celulas_ativas"]
_COLUNAS_SERIE = ["data_local", "referencia", "na", "nrt"] + _SOMAS

AVISO_HISTORICO_CURTO = "Histórico curto: {n} anos ({ini}–{fim})."
AVISO_AREA_PEQUENA = ("Área pequena: a mediana histórica deste período é menor que {min} CDeV; "
                      "as comparações são instáveis.")
MINIMO_CDEV_ESTAVEL = 5


# --------------------------------------------------------------------------- utilidades

def _anos_historico() -> tuple[int, int]:
    a, b = cfg()["periodo_historico"]
    return int(a), int(b)


def _data_fim_dados() -> date:
    return pd.Timestamp(cfg()["data_fim_dados"]).date()


def semana_do_ano(datas) -> np.ndarray:
    """Semana 1..53: (dia do ano − 1) // 7 + 1. Igual em todos os anos (não é a semana ISO)."""
    doy = pd.DatetimeIndex(pd.to_datetime(datas)).day_of_year.to_numpy()
    return (doy - 1) // 7 + 1


def semana_para_mes(semana: int) -> int:
    """Mês aproximado em que cai o meio da semana (ano não bissexto)."""
    dia = min(int(semana - 1) * 7 + 4, 365)
    return int((pd.Timestamp(2023, 1, 1) + pd.Timedelta(days=dia - 1)).month)


def classificar(valor: float, historico) -> dict:
    """Posição e classificação de `valor` frente aos valores `historico` (outros anos).

    Devolve dict com: posicao (1 = maior), n_anos (histórico + o valor), posicao_texto
    ("2º de 8"), mediana, minimo, maximo, classificacao. Com histórico vazio, tudo None.
    """
    h = pd.Series(historico, dtype="float64").dropna()
    if h.empty or valor is None or pd.isna(valor):
        return dict(posicao=None, n_anos=int(len(h)) + (0 if valor is None or pd.isna(valor) else 1),
                    posicao_texto=None, mediana=None, minimo=None, maximo=None,
                    classificacao="sem histórico comparável")
    mediana, minimo, maximo = float(h.median()), float(h.min()), float(h.max())
    if valor > maximo:
        texto = "recorde (acima do máximo histórico)"
    elif valor < minimo:
        texto = "abaixo do mínimo histórico"
    elif valor > mediana:
        texto = "acima da mediana"
    else:
        texto = "abaixo da mediana"
    posicao = int((h > valor).sum()) + 1
    n = len(h) + 1
    return dict(posicao=posicao, n_anos=n, posicao_texto=f"{posicao}º de {n}",
                mediana=mediana, minimo=minimo, maximo=maximo, classificacao=texto)


def densidade(valor: float, area_km2: float) -> float | None:
    """CDeV por 1.000 km². None se a área for zero/desconhecida."""
    if not area_km2 or pd.isna(area_km2) or area_km2 <= 0:
        return None
    return float(valor) / float(area_km2) * 1000.0


# --------------------------------------------------------------------------- série diária

def _agregar_por_dia(celulas: pd.DataFrame) -> pd.DataFrame:
    """Soma as linhas célula × dia em uma linha por dia (usa as colunas que existirem)."""
    df = celulas
    agg = {"cdev": ("cdev", "sum")}
    if "cdev_min" in df:
        agg["cdev_min"] = ("cdev_min", "sum")
    if "cdev_max" in df:
        agg["cdev_max"] = ("cdev_max", "sum")
    if "ativa_snpp" in df:
        agg["snpp"] = ("ativa_snpp", "sum")
    if "ativa_n20" in df:
        agg["n20"] = ("ativa_n20", "sum")
    if "ativa_modis" in df:
        agg["modis_bruto"] = ("ativa_modis", "sum")
    if "cdev_modis" in df:
        agg["modis_calibrado"] = ("cdev_modis", "sum")
    if "produto" in df:
        df = df.assign(_nrt=df["produto"].eq("nrt"))
        agg["nrt"] = ("_nrt", "any")
    agg["celulas_ativas"] = ("cdev", "size")
    return df.groupby("data_local", as_index=False).agg(**agg)


def serie_diaria(celulas: pd.DataFrame, disponibilidade: pd.DataFrame | None = None,
                 inicio=None, fim=None) -> pd.DataFrame:
    """Série com UMA linha por dia do calendário (data_inicio_dados..data_fim_dados).

    Dias sem fogo ficam com 0; dias sem satélite de referência (NA) ficam com cdev NaN e
    na=True. Se `celulas` já for diária (sem coluna gx), só reindexa no calendário.
    Colunas: data_local, referencia, na, nrt, cdev, cdev_min, cdev_max, snpp, n20,
             modis_bruto, modis_calibrado, celulas_ativas.
    """
    if disponibilidade is None:
        from firewatch import carregar
        disponibilidade = carregar.disponibilidade()
    c = cfg()
    inicio = pd.Timestamp(inicio or c["data_inicio_dados"]).date()
    fim = pd.Timestamp(fim or c["data_fim_dados"]).date()

    cal = disponibilidade.loc[:, ["data_local", "referencia"]].copy()
    cal["data_local"] = pd.to_datetime(cal["data_local"]).dt.date
    cal = cal[(cal.data_local >= inicio) & (cal.data_local <= fim)]

    df = celulas.copy()
    df["data_local"] = pd.to_datetime(df["data_local"]).dt.date
    diaria = df if "gx" not in df.columns else _agregar_por_dia(df)
    diaria = diaria.drop(columns=[c_ for c_ in ("referencia", "na") if c_ in diaria.columns])

    s = cal.merge(diaria, on="data_local", how="left")
    for col in _SOMAS:
        if col not in s:
            s[col] = 0.0
        s[col] = s[col].fillna(0.0).astype("float64")
    s["nrt"] = s["nrt"].fillna(False).astype(bool) if "nrt" in s else False
    s["na"] = s["referencia"].isna()
    s.loc[s["na"], ["cdev", "cdev_min", "cdev_max"]] = np.nan
    return s.sort_values("data_local").reset_index(drop=True)[_COLUNAS_SERIE]


def _com_ano_mes_semana(s: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(s["data_local"])
    return s.assign(ano=d.dt.year.to_numpy(), mes=d.dt.month.to_numpy(),
                    dia=d.dt.day.to_numpy(), semana=semana_do_ano(d))


def _cobertura_reduzida(dias_na: pd.Series, dias: pd.Series) -> pd.Series:
    return (dias_na / dias) > float(cfg()["cobertura_reduzida"])


# --------------------------------------------------------------------------- calendários

def calendario_mensal(celulas: pd.DataFrame, disponibilidade=None) -> pd.DataFrame:
    """Uma linha por (ano, mês) presente no calendário.

    Colunas: ano, mes, cdev, cdev_min, cdev_max, viirs (cdev de dias VIIRS), modis_bruto,
    modis_calibrado, dias, dias_na, dias_nrt, cobertura_reduzida, parcial (mês ainda em
    curso ou cortado em data_fim_dados), completo.
    Para o mapa de calor: `cal.pivot(index="ano", columns="mes", values="cdev")`.
    Meses com cobertura_reduzida devem aparecer hachurados e ficam FORA das medianas.
    """
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    g = s.groupby(["ano", "mes"], as_index=False).agg(
        cdev=("cdev", "sum"), cdev_min=("cdev_min", "sum"), cdev_max=("cdev_max", "sum"),
        modis_bruto=("modis_bruto", "sum"), modis_calibrado=("modis_calibrado", "sum"),
        dias=("data_local", "size"), dias_na=("na", "sum"), dias_nrt=("nrt", "sum"))
    g["viirs"] = g["cdev"]
    g["cobertura_reduzida"] = _cobertura_reduzida(g["dias_na"], g["dias"])
    dias_no_mes = pd.to_datetime(g.ano.astype(str) + "-" + g.mes.astype(str) + "-01").dt.days_in_month
    g["parcial"] = g["dias"] < dias_no_mes.to_numpy()
    g["completo"] = ~g["parcial"] & ~g["cobertura_reduzida"]
    return g


def calendario_semanal(celulas: pd.DataFrame, disponibilidade=None) -> pd.DataFrame:
    """Uma linha por (ano, semana). Mesmas colunas do calendário mensal, com `semana`
    no lugar de `mes` e `data_inicio` (primeiro dia da semana)."""
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    g = s.groupby(["ano", "semana"], as_index=False).agg(
        data_inicio=("data_local", "min"),
        cdev=("cdev", "sum"), cdev_min=("cdev_min", "sum"), cdev_max=("cdev_max", "sum"),
        modis_bruto=("modis_bruto", "sum"), modis_calibrado=("modis_calibrado", "sum"),
        dias=("data_local", "size"), dias_na=("na", "sum"), dias_nrt=("nrt", "sum"))
    g["cobertura_reduzida"] = _cobertura_reduzida(g["dias_na"], g["dias"])
    g["parcial"] = (g["dias"] < 7) & (g["semana"] < 53)
    g["completo"] = ~g["parcial"] & ~g["cobertura_reduzida"]
    return g


def por_sensor(celulas: pd.DataFrame, disponibilidade=None) -> pd.DataFrame:
    """Botão "ver por sensor": séries mensais VIIRS (referência), MODIS bruto e MODIS
    calibrado, só nos dias em que MODIS e VIIRS estavam ambos ativos (comparação justa).
    Colunas: ano, mes, viirs, modis_bruto, modis_calibrado, erro_pct, dias.
    """
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    s = s[~s["na"]]
    g = s.groupby(["ano", "mes"], as_index=False).agg(
        viirs=("cdev", "sum"), modis_bruto=("modis_bruto", "sum"),
        modis_calibrado=("modis_calibrado", "sum"), dias=("data_local", "size"))
    g["erro_pct"] = np.where(g["viirs"] > 0,
                             (g["modis_calibrado"] - g["viirs"]) / g["viirs"] * 100, np.nan)
    return g


# --------------------------------------------------------------------------- comparações

def _historico(valores_por_ano: pd.Series, ano: int, completos: pd.Series | None = None):
    """Valores dos OUTROS anos do período histórico (e completos), para comparar com `ano`."""
    a0, a1 = _anos_historico()
    h = valores_por_ano.drop(index=ano, errors="ignore")
    h = h[(h.index >= a0) & (h.index <= a1)]
    if completos is not None:
        h = h[completos.reindex(h.index).fillna(False).astype(bool)]
    return h


def _avisos(mediana) -> list[str]:
    a0, a1 = _anos_historico()
    avisos = [AVISO_HISTORICO_CURTO.format(n=a1 - a0 + 1, ini=a0, fim=a1)]
    if mediana is not None and mediana < MINIMO_CDEV_ESTAVEL:
        avisos.append(AVISO_AREA_PEQUENA.format(min=MINIMO_CDEV_ESTAVEL))
    return avisos


def termometro(celulas: pd.DataFrame, ano: int, mes: int, disponibilidade=None) -> dict:
    """"Este mês está fora do normal?" — o mês (ano, mes) contra o mesmo mês dos outros anos.

    Se o mês estiver incompleto (ex.: nov/2026 até o dia 14), compara "até o dia D" em
    todos os anos. Meses com cobertura reduzida saem do histórico.
    Devolve: ano, mes, valor, ate_dia, parcial, cobertura_reduzida, nrt, dias_na,
    mediana, minimo, maximo, posicao, posicao_texto, n_anos, anos_comparados,
    classificacao, avisos, por_ano (DataFrame ano, cdev, dias_na, cobertura_reduzida).
    """
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    m = s[s["mes"] == mes]
    atual = m[m["ano"] == ano]
    if atual.empty:
        raise ValueError(f"não há dados para {mes:02d}/{ano}")
    ate_dia = int(atual["dia"].max())
    dias_no_mes = pd.Timestamp(ano, mes, 1).days_in_month
    parcial = ate_dia < dias_no_mes
    m = m[m["dia"] <= ate_dia]
    por_ano = m.groupby("ano").agg(cdev=("cdev", "sum"), dias=("data_local", "size"),
                                   dias_na=("na", "sum"), nrt=("nrt", "any"))
    por_ano["cobertura_reduzida"] = _cobertura_reduzida(por_ano["dias_na"], por_ano["dias"])
    valor = float(por_ano.loc[ano, "cdev"])
    hist = _historico(por_ano["cdev"], ano, ~por_ano["cobertura_reduzida"])
    cl = classificar(valor, hist)
    return dict(ano=ano, mes=mes, valor=valor, ate_dia=ate_dia, parcial=parcial,
                cobertura_reduzida=bool(por_ano.loc[ano, "cobertura_reduzida"]),
                nrt=bool(por_ano.loc[ano, "nrt"]), dias_na=int(por_ano.loc[ano, "dias_na"]),
                anos_comparados=[int(a) for a in hist.index], **cl,
                avisos=_avisos(cl["mediana"]), por_ano=por_ano.reset_index())


def ano_em_curso(celulas: pd.DataFrame, data_fim=None, ano: int | None = None,
                 disponibilidade=None) -> dict:
    """Cartão "2026 até 14/11": acumulado do ano até `data_fim` contra o MESMO intervalo
    (01/01 até o mesmo dia do ano) dos anos históricos.

    data_fim padrão: data_fim_dados do config. ano padrão: ano_em_curso do config.
    Devolve: ano, data_fim, valor, nrt, dias_na, mediana, minimo, maximo, posicao,
    posicao_texto, n_anos, anos_comparados, classificacao, avisos, por_ano.
    """
    c = cfg()
    ano = int(ano or c["ano_em_curso"])
    data_fim = pd.Timestamp(data_fim or c["data_fim_dados"]).date()
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    doy_fim = pd.Timestamp(data_fim).day_of_year
    d = pd.to_datetime(s["data_local"])
    s = s[d.dt.day_of_year.to_numpy() <= doy_fim]
    por_ano = s.groupby("ano").agg(cdev=("cdev", "sum"), dias=("data_local", "size"),
                                   dias_na=("na", "sum"), nrt=("nrt", "any"))
    por_ano["cobertura_reduzida"] = _cobertura_reduzida(por_ano["dias_na"], por_ano["dias"])
    if ano not in por_ano.index:
        raise ValueError(f"não há dados para o ano {ano}")
    valor = float(por_ano.loc[ano, "cdev"])
    hist = _historico(por_ano["cdev"], ano, ~por_ano["cobertura_reduzida"])
    cl = classificar(valor, hist)
    return dict(ano=ano, data_fim=data_fim, valor=valor, nrt=bool(por_ano.loc[ano, "nrt"]),
                dias_na=int(por_ano.loc[ano, "dias_na"]),
                anos_comparados=[int(a) for a in hist.index], **cl,
                avisos=_avisos(cl["mediana"]), por_ano=por_ano.reset_index())


def ranking_anos(celulas: pd.DataFrame, disponibilidade=None) -> pd.DataFrame:
    """Anos ordenados pelo total de CDeV (1º = mais fogo).
    Colunas: ano, cdev, dias_na, completo (ano inteiro e sem cobertura reduzida), posicao.
    O ano em curso aparece, mas marcado completo=False: não compare o total dele."""
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    g = s.groupby("ano", as_index=False).agg(cdev=("cdev", "sum"), dias=("data_local", "size"),
                                            dias_na=("na", "sum"))
    dias_no_ano = pd.to_datetime(g.ano.astype(str) + "-12-31").dt.day_of_year.to_numpy()
    g["completo"] = (g["dias"] == dias_no_ano) & ~_cobertura_reduzida(g["dias_na"], g["dias"])
    g = g.sort_values("cdev", ascending=False).reset_index(drop=True)
    g["posicao"] = np.arange(1, len(g) + 1)
    return g[["ano", "cdev", "dias_na", "completo", "posicao"]]


# --------------------------------------------------------------------------- estação de fogo

def climatologia_semanal(celulas: pd.DataFrame, disponibilidade=None) -> pd.DataFrame:
    """Mediana entre os anos históricos do CDeV de cada semana (semanas com NA no ano
    ficam fora da mediana daquela semana). Colunas: semana, mediana, n_anos, acumulado,
    acumulado_frac (0..1)."""
    a0, a1 = _anos_historico()
    w = calendario_semanal(celulas, disponibilidade)
    w = w[(w.ano >= a0) & (w.ano <= a1) & (w.dias_na == 0)]
    g = w.groupby("semana").agg(mediana=("cdev", "median"), n_anos=("ano", "size")).reset_index()
    g = g.set_index("semana").reindex(range(1, 54)).fillna({"mediana": 0.0, "n_anos": 0}).reset_index()
    g["acumulado"] = g["mediana"].cumsum()
    total = g["acumulado"].iloc[-1]
    g["acumulado_frac"] = g["acumulado"] / total if total > 0 else 0.0
    return g


def janela_critica(celulas: pd.DataFrame, disponibilidade=None,
                   inicio_frac: float = 0.10, fim_frac: float = 0.90) -> dict:
    """"Quando começa e termina a estação de fogo?" — da climatologia semanal: a semana em
    que o acumulado típico passa 10% (início), a semana de pico e a em que passa 90% (fim).
    Devolve: semana_inicio, semana_pico, semana_fim, mes_inicio, mes_pico, mes_fim,
    frac_na_janela, climatologia (DataFrame)."""
    cl = climatologia_semanal(celulas, disponibilidade)
    if cl["mediana"].sum() <= 0:
        return dict(semana_inicio=None, semana_pico=None, semana_fim=None, mes_inicio=None,
                    mes_pico=None, mes_fim=None, frac_na_janela=None, climatologia=cl)
    ini = int(cl.loc[cl.acumulado_frac >= inicio_frac, "semana"].iloc[0])
    fim = int(cl.loc[cl.acumulado_frac >= fim_frac, "semana"].iloc[0])
    pico = int(cl.loc[cl["mediana"].idxmax(), "semana"])
    frac = float(cl.loc[(cl.semana >= ini) & (cl.semana <= fim), "mediana"].sum() / cl["mediana"].sum())
    return dict(semana_inicio=ini, semana_pico=pico, semana_fim=fim,
                mes_inicio=semana_para_mes(ini), mes_pico=semana_para_mes(pico),
                mes_fim=semana_para_mes(fim), frac_na_janela=frac, climatologia=cl)


def ritmo_do_ano(celulas: pd.DataFrame, ano: int, disponibilidade=None, data_fim=None) -> dict:
    """"Este ano está adiantado?" — o acumulado do ano até `data_fim` (padrão: último dia com
    dado) comparado à curva acumulada típica. `semana_tipica` é a semana em que o ano típico
    atinge esse mesmo acumulado. semanas_adiantado > 0 = adiantado; < 0 = atrasado.
    Devolve: ano, semana_atual, acumulado, acumulado_tipico_na_semana, semana_tipica,
    semanas_adiantado, texto."""
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    y = s[s.ano == ano]
    if data_fim is not None:
        y = y[y.data_local <= pd.Timestamp(data_fim).date()]
    y = y[~y["na"]]
    if y.empty:
        raise ValueError(f"não há dados para o ano {ano}")
    semana_atual = int(y["semana"].max())
    acumulado = float(y["cdev"].sum())
    cl = climatologia_semanal(celulas, disponibilidade)
    tipico_na_semana = float(cl.loc[cl.semana == semana_atual, "acumulado"].iloc[0])
    alcanca = cl[cl.acumulado >= acumulado]
    semana_tipica = int(alcanca["semana"].iloc[0]) if not alcanca.empty else 53
    adiant = semana_tipica - semana_atual
    if cl["acumulado"].iloc[-1] <= 0:
        texto = "sem histórico suficiente para comparar o ritmo"
    elif adiant > 0:
        texto = (f"adiantado: na semana {semana_atual}, {ano} já acumulou o que o ano típico "
                 f"só alcança na semana {semana_tipica}")
    elif adiant < 0:
        texto = (f"atrasado: na semana {semana_atual}, {ano} acumulou o que o ano típico "
                 f"já tinha na semana {semana_tipica}")
    else:
        texto = f"no ritmo típico (semana {semana_atual})"
    return dict(ano=ano, semana_atual=semana_atual, acumulado=acumulado,
                acumulado_tipico_na_semana=tipico_na_semana, semana_tipica=semana_tipica,
                semanas_adiantado=int(adiant), texto=texto)


# --------------------------------------------------------------------------- Modo MIF

def fracao_tardia(celulas: pd.DataFrame, ano: int, data_corte: str | None = None,
                  disponibilidade=None, data_fim=None) -> dict:
    """Modo MIF: fração do CDeV do ano que veio DEPOIS da data de corte (config: 07-15).

    precoce = Σ cdev com data_local <= corte; tardio = Σ cdev depois; fracao = tardio/total.
    Dias NA ficam fora. Um ano com > cobertura_reduzida de dias NA em qualquer dos lados é
    marcado e sai do histórico. Para o ano em curso (`data_fim` < 31/12), o histórico é
    calculado no MESMO intervalo (até o mesmo dia do ano) e `em_curso=True`.
    Classifica a ÉPOCA do fogo, não a intenção.
    Devolve: ano, data_corte, precoce, tardio, total, fracao (0..1 ou None), em_curso,
    cobertura_reduzida, mediana, minimo, maximo, posicao, posicao_texto, n_anos,
    anos_comparados, classificacao, avisos, por_ano.
    """
    c = cfg()
    data_corte = data_corte or c["mif_data_corte"]
    mes_c, dia_c = (int(p) for p in str(data_corte).split("-"))
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    fim = pd.Timestamp(data_fim or c["data_fim_dados"]).date()
    em_curso = ano == int(c["ano_em_curso"]) or (fim.year == ano and (fim.month, fim.day) < (12, 31))
    if em_curso:
        doy_fim = pd.Timestamp(fim if fim.year == ano else date(ano, 12, 31)).day_of_year
        s = s[pd.to_datetime(s["data_local"]).dt.day_of_year.to_numpy() <= doy_fim]
    s = s.assign(tardio=(s["mes"] > mes_c) | ((s["mes"] == mes_c) & (s["dia"] > dia_c)))
    g = s.groupby(["ano", "tardio"]).agg(cdev=("cdev", "sum"), dias=("data_local", "size"),
                                         dias_na=("na", "sum"))
    g["cob_red"] = _cobertura_reduzida(g["dias_na"], g["dias"])
    cdev = g["cdev"].unstack("tardio").reindex(columns=[False, True]).fillna(0.0)
    por_ano = pd.DataFrame({"precoce": cdev[False], "tardio": cdev[True],
                            "cobertura_reduzida": g["cob_red"].groupby(level="ano").any()})
    por_ano["total"] = por_ano["precoce"] + por_ano["tardio"]
    por_ano["fracao"] = np.where(por_ano["total"] > 0, por_ano["tardio"] / por_ano["total"], np.nan)
    if ano not in por_ano.index:
        raise ValueError(f"não há dados para o ano {ano}")
    linha = por_ano.loc[ano]
    valor = None if pd.isna(linha["fracao"]) else float(linha["fracao"])
    hist = _historico(por_ano["fracao"], ano, ~por_ano["cobertura_reduzida"]).dropna()
    cl = classificar(valor, hist)
    return dict(ano=ano, data_corte=data_corte, precoce=float(linha["precoce"]),
                tardio=float(linha["tardio"]), total=float(linha["total"]), fracao=valor,
                em_curso=bool(em_curso), cobertura_reduzida=bool(linha["cobertura_reduzida"]),
                anos_comparados=[int(a) for a in hist.index], **cl,
                avisos=_avisos(None) + (["temporada ainda em curso"] if em_curso else []),
                por_ano=por_ano.reset_index())


# --------------------------------------------------------------------------- honestidade

def contagem_honesta(celulas: pd.DataFrame, disponibilidade=None) -> dict:
    """Quanto a soma ingênua dos satélites inflaria a contagem.
    soma_ingenua = células-dia SNPP + N20 + MODIS (cada satélite contado à parte);
    unicas = células-dia distintas com fogo em qualquer satélite; razao = soma / unicas.
    Devolve: soma_ingenua, unicas, razao, por_ano (ano, soma_ingenua, unicas, razao).
    Precisa das colunas ativa_snpp/ativa_n20/ativa_modis (ou snpp/n20/modis_bruto/celulas_ativas).
    """
    s = _com_ano_mes_semana(serie_diaria(celulas, disponibilidade))
    if s[["snpp", "n20", "modis_bruto"]].sum().sum() == 0 and s["celulas_ativas"].sum() > 0:
        raise ValueError("contagem_honesta precisa das colunas ativa_snpp, ativa_n20 e ativa_modis")
    s = s.assign(soma_ingenua=s["snpp"] + s["n20"] + s["modis_bruto"])
    por_ano = s.groupby("ano", as_index=False).agg(soma_ingenua=("soma_ingenua", "sum"),
                                                  unicas=("celulas_ativas", "sum"))
    por_ano["razao"] = np.where(por_ano.unicas > 0, por_ano.soma_ingenua / por_ano.unicas, np.nan)
    soma, unicas = float(s["soma_ingenua"].sum()), float(s["celulas_ativas"].sum())
    return dict(soma_ingenua=soma, unicas=unicas, razao=(soma / unicas if unicas else None),
                por_ano=por_ano)


def lacunas(disponibilidade: pd.DataFrame, inicio=None, fim=None) -> dict:
    """Dias e meses em que o satélite de referência faltou ou foi substituído.
    Devolve: dias_sem_dado (DataFrame: referencia NULL = NA), dias_referencia_alternativa
    (S-NPP fora; N20 ou MODIS no lugar), meses_cobertura_reduzida (ano, mes, dias_na, dias),
    resumo (texto)."""
    c = cfg()
    inicio = pd.Timestamp(inicio or c["data_inicio_dados"]).date()
    fim = pd.Timestamp(fim or c["data_fim_dados"]).date()
    d = disponibilidade.copy()
    d["data_local"] = pd.to_datetime(d["data_local"]).dt.date
    d = d[(d.data_local >= inicio) & (d.data_local <= fim)]
    sem_dado = d[d.referencia.isna()]
    alternativa = d[d.referencia.notna() & (d.referencia != "snpp")]
    m = _com_ano_mes_semana(d.assign(na=d.referencia.isna()))
    meses = m.groupby(["ano", "mes"], as_index=False).agg(dias_na=("na", "sum"), dias=("na", "size"))
    meses = meses[_cobertura_reduzida(meses.dias_na, meses.dias)]
    cols = [c_ for c_ in ["data_local", "status_snpp", "status_n20", "status_modis", "referencia"]
            if c_ in d.columns]
    resumo = (f"{len(sem_dado)} dia(s) sem nenhum satélite de referência; "
              f"{len(alternativa)} dia(s) com o S-NPP fora e outro satélite no lugar; "
              f"{len(meses)} mês(es) com cobertura reduzida.")
    return dict(dias_sem_dado=sem_dado[cols].reset_index(drop=True),
                dias_referencia_alternativa=alternativa[cols].reset_index(drop=True),
                meses_cobertura_reduzida=meses.reset_index(drop=True), resumo=resumo)
