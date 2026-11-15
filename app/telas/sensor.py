"""Por sensor: VIIRS × MODIS bruto × MODIS calibrado, deriva do MODIS e satélite por dia."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as C
import dados as D
import estilo as E
from firewatch import indicadores as ind

STATUS = {"ok": 1, "parcial": 2, "ausente": 3}
REF = {"snpp": 4, "n20": 5, "modis": 6}


def _discreta(cores: list[str]) -> list[list]:
    """Escala plotly em degraus: o código i (1..n, com zmin=1, zmax=n) recebe cores[i-1]."""
    n = len(cores)
    escala = []
    for i, cor in enumerate(cores):
        escala += [[i / n, cor], [(i + 1) / n, cor]]
    return escala


@st.cache_data(show_spinner=False, max_entries=32)
def _por_sensor(chave, tipo, geojson):
    s = D.serie(chave, tipo, geojson)
    return ind.por_sensor(s), ind.contagem_honesta(s)


def _series(ps: pd.DataFrame) -> None:
    x = pd.to_datetime(ps["ano"].astype(str) + "-" + ps["mes"].astype(str) + "-01")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=ps["modis_bruto"], name="MODIS bruto", mode="lines",
                             line=dict(color=E.CINZA, width=2, dash="dot"),
                             hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=x, y=ps["viirs"], name="VIIRS", mode="lines",
                             line=dict(color=E.AZUL, width=2.6), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=x, y=ps["modis_calibrado"], name="MODIS calibrado", mode="lines",
                             line=dict(color=E.LARANJA, width=2), hovertemplate="%{y:,.0f}"))
    a0, a1 = (int(v) for v in D.cfg()["calibracao_anos"])
    fig.add_vrect(x0=f"{a0}-01-01", x1=f"{a1}-12-31", fillcolor=E.CHIP, opacity=0.5, line_width=0,
                  layer="below")
    fig.add_annotation(x=f"{a0}-01-15", y=1, yref="paper", text="calibração", showarrow=False,
                       xanchor="left", yanchor="top", font=dict(size=11, color=E.MUTED))
    E.layout(fig, 330)
    with st.container(key="cardsensor"):
        E.html(C.titulo_card("MODIS calibrado acompanha o VIIRS",
                             E.legenda_item(E.AZUL, "VIIRS") + E.legenda_item(E.CINZA, "MODIS bruto", True)
                             + E.legenda_item(E.LARANJA, "MODIS calibrado")))
        E.grafico(fig, key="sensor_series")


def _kpis(ps: pd.DataFrame, honesta: dict) -> None:
    a0, a1 = (int(v) for v in D.cfg()["calibracao_anos"])
    cal = ps[(ps.ano >= a0) & (ps.ano <= a1)]
    teste = ps[ps.ano == int(D.cfg()["periodo_historico"][1])]
    ver = cal["modis_bruto"].sum() / cal["viirs"].sum() if cal["viirs"].sum() else None
    erro = lambda d: (d["modis_calibrado"].sum() - d["viirs"].sum()) / d["viirs"].sum() * 100 \
        if d["viirs"].sum() else None   # noqa: E731
    e_cal, e_teste = erro(cal), erro(teste)
    sinal = lambda v: "–" if v is None else ("+" if v > 0 else "") + E.num(v, 1) + "%"   # noqa: E731
    ano_teste = int(teste.ano.max()) if not teste.empty else ""
    itens = [
        ("MODIS vê do VIIRS", f"~{E.pct(ver)}" if ver else "–"),
        (f"Erro {a0}–{str(a1)[2:]}", sinal(e_cal)),
        (f"Erro {ano_teste} · deriva", sinal(e_teste)),
        ("Soma dos satélites", f"{E.num(honesta['razao'], 2)}×" if honesta.get("razao") else "–"),
    ]
    val = D.validacao()
    if val is not None and "erro_pct" in val:
        itens[1] = ("Erro · ano deixado de fora", sinal(float(val["erro_pct"].abs().median())))
    for col, (rot, v) in zip(st.columns(4, gap="medium"), itens):
        col.markdown(C.cartao(rot, v), unsafe_allow_html=True)


def _deriva() -> None:
    d = D.deriva()
    d = d[d.area == "cerrado"].groupby(["ano", "calibracao"], as_index=False)[
        ["cdev_viirs", "cdev_modis_calibrado"]].sum()
    d["erro"] = (d["cdev_modis_calibrado"] - d["cdev_viirs"]) / d["cdev_viirs"] * 100
    cores = np.where(d["calibracao"], E.CINZA, E.LARANJA)
    fig = go.Figure(go.Bar(x=d["ano"].astype(str), y=d["erro"], marker=dict(color=cores, cornerradius=5),
                           text=[("+" if v > 0 else "") + E.num(v, 1) + "%" for v in d["erro"]],
                           textposition="outside", textfont=dict(size=11, color=E.TINTA_2),
                           hovertemplate="%{x}: %{y:+.1f}%<extra></extra>", width=0.55))
    E.layout(fig, 250, hovermode="closest")
    fig.update_xaxes(type="category")
    fig.update_yaxes(rangemode="normal", ticksuffix="%", zeroline=True, zerolinecolor=E.TINTA,
                     zerolinewidth=1)
    lim = float(d["erro"].abs().max()) * 1.35
    fig.update_yaxes(range=[-lim, lim])
    with st.container(key="cardderiva"):
        E.html(C.titulo_card("Deriva do MODIS · Cerrado",
                             E.legenda_item(E.CINZA, "calibração") + E.legenda_item(E.LARANJA, "teste")))
        E.grafico(fig, key="deriva")
        E.html('<div class="fw-sub">Erro do MODIS calibrado × VIIRS. Cresce após 2022: '
               'o horário de passagem mudou.</div>')


def _satelites() -> None:
    disp = D.disponibilidade().copy()
    disp["data_local"] = pd.to_datetime(disp["data_local"])
    with st.container(key="cardsat"):
        c1, c2 = st.columns([2, 1], vertical_alignment="center")
        c1.markdown(C.titulo_card("Satélite usado por dia"), unsafe_allow_html=True)
        ano = c2.selectbox("Ano", D.ANOS, index=D.ANOS.index(2022), key="sat_ano",
                           label_visibility="collapsed")
        d = disp[disp.data_local.dt.year == ano]
        z = np.vstack([d["status_snpp"].map(STATUS), d["status_n20"].map(STATUS),
                       d["status_modis"].map(STATUS), d["referencia"].map(REF).fillna(7)])
        # códigos 1..7: ok, parcial, ausente | ref. S-NPP, ref. NOAA-20, ref. MODIS, sem dado
        escala = _discreta(["#9DB8DD", "#F2C14E", "#D9D3C7", E.AZUL, "#7B5EA7", E.LARANJA, "#FFFFFF"])
        texto = np.vstack([d["status_snpp"], d["status_n20"], d["status_modis"],
                           d["referencia"].fillna("sem dado")])
        fig = go.Figure(go.Heatmap(
            z=z, x=d["data_local"], y=["S-NPP", "NOAA-20", "MODIS", "Referência"], zmin=1, zmax=7,
            colorscale=escala, showscale=False, xgap=0, ygap=8, text=texto,
            hovertemplate="%{y} · %{x|%d/%m}: %{text}<extra></extra>"))
        E.layout(fig, 210, hovermode="closest")
        fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=E.TINTA, size=12))
        inicios = pd.date_range(f"{ano}-01-01", periods=12, freq="MS")
        fig.update_xaxes(tickvals=inicios, ticktext=E.MESES, showline=False)
        E.grafico(fig, key="satelites")
        leg = (E.legenda_item("#9DB8DD", "ok") + E.legenda_item("#F2C14E", "parcial")
               + E.legenda_item("#D9D3C7", "fora do ar") + E.legenda_item(E.AZUL, "ref. S-NPP")
               + E.legenda_item("#7B5EA7", "ref. NOAA-20"))
        lac = ind.lacunas(disp.assign(data_local=disp.data_local.dt.date),
                          inicio=f"{ano}-01-01", fim=min(pd.Timestamp(f"{ano}-12-31"), D.FIM))
        n_alt = len(lac["dias_referencia_alternativa"])
        n_na = len(lac["dias_sem_dado"])
        resumo = f"{n_alt} dias com o NOAA-20 no lugar do S-NPP · {n_na} dias sem satélite"
        E.html(f'<div style="margin-left:-.35rem">{leg}</div><div class="fw-sub">{resumo}</div>')


def render(a: D.Area) -> None:
    with st.spinner("Calculando…"):
        ps, honesta = _por_sensor(a.chave, a.tipo, a.geojson)
    if ps.empty or ps["viirs"].sum() == 0:
        st.info("Sem fogo detectado nesta área para comparar os sensores.", icon=":material/info:")
    else:
        _series(ps)
        _kpis(ps, honesta)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        _deriva()
    with c2:
        _satelites()
