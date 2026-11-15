"""Dentro × entorno: densidade de fogo no território e no anel de 10 km em volta."""
from __future__ import annotations

import json

import plotly.graph_objects as go
import streamlit as st

import componentes as C
import dados as D
import estilo as E


def _mapa(a: D.Area) -> None:
    fig = C.figura_mapa(a, "satelite", altura=360)
    anel = D.entorno_geojson(a.chave)
    # preenchimentos como traços choropleth (camadas "fill" do mapa não aparecem de forma confiável)
    for gj, cor in ([(anel, "rgba(217,100,30,0.42)")] if anel else []) + [(a.geojson, "rgba(47,95,160,0.42)")]:
        feicao = {"type": "FeatureCollection",
                  "features": [{"type": "Feature", "id": "z", "properties": {}, "geometry": json.loads(gj)}]}
        fig.add_trace(go.Choroplethmap(geojson=feicao, locations=["z"], z=[1], featureidkey="id",
                                       colorscale=[[0, cor], [1, cor]], showscale=False,
                                       marker=dict(line=dict(width=0)), hoverinfo="skip"))
    with st.container(key="cardmapa-entorno"):
        E.grafico(fig, key="mapa_entorno")
        E.html('<div class="fw-escala" style="margin:.1rem .6rem .3rem">'
               + E.legenda_item(E.AZUL, "dentro") + E.legenda_item(E.LARANJA, "entorno 10 km") + "</div>")


def _razao(r) -> None:
    if r is None:
        E.html(C.cartao("Densidade dentro ÷ entorno", "–", ""))
        return
    dmax = max(r.densidade_dentro or 0, r.densidade_entorno or 0) or 1
    barras = ""
    for rot, v, cor in [("Dentro", r.densidade_dentro, E.AZUL), ("Entorno", r.densidade_entorno, E.LARANJA)]:
        barras += (f'<div style="display:grid;grid-template-columns:70px 1fr 64px;gap:.8rem;align-items:center;margin:.55rem 0">'
                   f'<div style="font-weight:700;font-size:.9rem">{rot}</div>'
                   f'<div class="fw-barra" style="height:12px"><div class="fw-barra-fill" '
                   f'style="width:{100 * (v or 0) / dmax}%;background:{cor}"></div></div>'
                   f'<div style="text-align:right;font-weight:800">{E.num(v)}</div></div>')
    valor = "–" if r.razao is None else E.num(r.razao, 2 if r.razao < 1 else 1) + "×"
    leitura = ("mais fogo dentro do que em volta" if r.razao and r.razao > 1 else
               "o entorno queima mais" if r.razao is not None else "sem fogo no entorno")
    sufixo = f" até {D.FIM:%d/%m}" if r.ano == D.ANO_ATUAL else ""
    E.html(C.cartao(f"Dentro ÷ entorno · {r.ano}{sufixo}", valor,
                    f'<div class="fw-sub" style="margin-bottom:.8rem">{leitura}</div>{barras}'
                    '<div class="fw-sub">por 1.000 km²</div>',
                    classe_valor="fw-valor-xl"))


def _por_ano(de) -> None:
    anos = de["ano"].astype(str)
    rot = [f"{a}<br><b>{'–' if r != r or r is None else E.num(r, 1) + '×'}</b>"
           for a, r in zip(anos, de["razao"])]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=rot, y=de["densidade_dentro"], name="dentro",
                         marker=dict(color=E.AZUL, cornerradius=6), hovertemplate="dentro: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=rot, y=de["densidade_entorno"], name="entorno",
                         marker=dict(color=E.LARANJA, cornerradius=6), hovertemplate="entorno: %{y:,.0f}<extra></extra>"))
    E.layout(fig, 300, barmode="group", bargap=0.35, bargroupgap=0.08, hovermode="x unified")
    fig.update_xaxes(tickfont=dict(color=E.TINTA_2))
    with st.container(key="cardporano"):
        E.html(C.titulo_card("Por ano", E.legenda_item(E.AZUL, "dentro") + E.legenda_item(E.LARANJA, "entorno")))
        E.grafico(fig, key="entorno_ano")


def render(a: D.Area, ano: int) -> None:
    with st.spinner("Calculando dentro × entorno…"):
        de = D.dentro_entorno_anos(a.chave)
    linha = de[de.ano == ano]
    r = next(linha.itertuples()) if not linha.empty else None
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        _mapa(a)
    with c2:
        _razao(r)
    _por_ano(de)
    E.html('<div class="fw-rodape">Comparação, não causa · número abaixo do ano = dentro ÷ entorno</div>')
