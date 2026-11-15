"""Modo MIF (Manejo Integrado do Fogo): quanto do fogo veio cedo (precoce) ou tarde (tardio)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import componentes as C
import dados as D
import estado
import estilo as E
from firewatch import indicadores as ind

# dias possíveis para o corte: 01/06 a 31/08
DIAS = [f"{d:%m-%d}" for d in pd.date_range("2023-06-01", "2023-08-31")]
ATALHOS = ["06-30", "07-15", "07-31"]


def _rotulo(corte: str) -> str:
    m, d = (int(x) for x in corte.split("-"))
    return f"{d} de {E.MESES_LONGOS[m - 1]}"


@st.cache_data(show_spinner=False, max_entries=64)
def _fracao(chave, tipo, geojson, ano, corte):
    return ind.fracao_tardia(D.serie(chave, tipo, geojson), ano, corte)


def _corte(corte: str) -> None:
    with st.container(key="cardcorte"):
        E.html(f'<div class="fw-rotulo">Data de corte</div><div class="fw-valor">{_rotulo(corte)}</div>')
        k = f"mif_corte_{corte}"
        st.select_slider("Data de corte", DIAS, value=corte, key=k, label_visibility="collapsed",
                         format_func=lambda c: f"{c[3:]}/{c[:2]}",
                         on_change=estado.ir_do_widget, args=(k, "c"))
        k2 = f"mif_atalho_{corte}"
        st.segmented_control("Atalhos", ATALHOS, default=corte if corte in ATALHOS else None,
                             format_func=lambda c: f"{c[3:]}/{c[:2]}", key=k2,
                             label_visibility="collapsed", on_change=estado.ir_do_widget, args=(k2, "c"))


def _resultado(fr: dict) -> None:
    if fr["fracao"] is None:
        E.html(C.cartao(f"Fogo tardio em {fr['ano']}", "–", '<div class="fw-sub">sem fogo no ano</div>'))
        return
    pre = fr["precoce"] / fr["total"] if fr["total"] else 0
    hist = (f"histórico {E.pct(fr['minimo'])}–{E.pct(fr['maximo'])}" if fr["minimo"] is not None
            else "sem histórico")
    rot = f"Fogo tardio em {fr['ano']}" + (" · até agora" if fr["em_curso"] else "")
    extra = (f'<div style="margin:.7rem 0 .8rem">{C.split(fr["precoce"], fr["tardio"])}</div>'
             + E.chip(f"precoce {E.pct(pre)}", "azul") + E.chip(f"tardio {E.pct(fr['fracao'])}", "laranja")
             + E.chip(hist))
    E.html(C.cartao(rot, E.pct(fr["fracao"]), extra, direita=E.badge(fr["classificacao"]),
                    classe_valor="fw-valor-xl"))


def _ranking(fr: dict) -> None:
    pa = fr["por_ano"].dropna(subset=["fracao"]).sort_values("fracao", ascending=False)
    linhas = []
    for r in pa.itertuples():
        atual = r.ano == fr["ano"]
        cor_ano = E.MARCA if atual else E.TINTA_2
        peso = 800 if atual else 600
        linhas.append(
            f'<div style="display:grid;grid-template-columns:48px 1fr 52px;gap:1rem;align-items:center;margin:.45rem 0">'
            f'<div style="color:{cor_ano};font-weight:{peso};font-size:.88rem">{r.ano}</div>'
            f'{C.split(r.precoce, r.tardio, forte=atual)}'
            f'<div style="text-align:right;font-weight:800;font-size:.88rem">{E.pct(r.fracao)}</div></div>')
    with st.container(key="cardranking"):
        E.html(C.titulo_card("Anos pelo fogo tardio") + "".join(linhas))


def render(a: D.Area, ano: int, corte: str) -> None:
    if corte not in DIAS:
        corte = D.cfg()["mif_data_corte"]
    serie = D.serie_area(a)
    if serie.empty:
        st.info("Sem fogo detectado nesta área.", icon=":material/info:")
        return
    fr = _fracao(a.chave, a.tipo, a.geojson, ano, corte)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        _corte(corte)
    with c2:
        _resultado(fr)
    pac = D.pacote(a.chave, a.tipo, a.geojson, ano, 1)
    with st.container(key="cardsemanas"):
        E.html(C.titulo_card("Semana a semana") + C.calendario_semanal(pac["semanal"], corte))
    _ranking(fr)
    aviso = "" if a.tipo == "cerrado" or a.territorio else " · a data de corte é uma convenção do Cerrado"
    E.html(f'<div class="fw-rodape">Época do fogo, não intenção{aviso}</div>')
