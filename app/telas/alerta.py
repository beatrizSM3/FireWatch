"""Painel de alerta: os territórios do Cerrado ordenados por 2026 × histórico."""
from __future__ import annotations

import streamlit as st

import componentes as C
import dados as D
import estado
import estilo as E

POR_PAGINA = 15
COLS = [3.6, 0.9, 1.7, 2.2, 0.45]


def _kpis(a) -> None:
    """Quatro blocos chapados, um por situação, com o quadrado amarelo dos slides."""
    cont = a["classificacao"].value_counts()
    for col, chave in zip(st.columns(4, gap="medium"), ["recorde (acima do máximo histórico)", "acima da mediana",
                                          "abaixo da mediana", "abaixo do mínimo histórico"]):
        rotulo, cor = E.classe(chave)
        col.markdown(f'<div class="fw-kpi" style="background:{cor}"><div class="fw-rotulo">{rotulo}</div>'
                     f'<div class="fw-valor">{E.num(cont.get(chave, 0))}</div></div>',
                     unsafe_allow_html=True)


def _filtrar(a):
    c1, c2, c3 = st.columns([3.4, 1.3, 1.2], vertical_alignment="center")
    busca = c1.text_input("Buscar", placeholder="Buscar território", label_visibility="collapsed",
                          icon=":material/search:", key="al_busca")
    tipo = c2.segmented_control("Tipo", ["Todos", "UC", "TI"], default="Todos", required=True,
                                key="al_tipo", label_visibility="collapsed")
    ufs = sorted({u.strip() for s in a["uf"].dropna() for u in s.split(",")})
    uf = c3.selectbox("Estado", ["Estado"] + ufs, key="al_uf", label_visibility="collapsed")
    if busca:
        a = a[a["nome_exib"].str.contains(busca, case=False, regex=False)]
    if tipo != "Todos":
        a = a[a["tipo"] == tipo]
    if uf != "Estado":
        a = a[a["uf"].fillna("").str.split(", ").map(lambda l: uf in l)]
    # recordes primeiro; dentro de cada situação, quem mais se afastou da mediana
    a = a.assign(_r=a["densidade_2026"] / a["densidade_mediana"].where(a["densidade_mediana"] > 0))
    return a.sort_values(["ordem_classificacao", "_r"], ascending=[True, False])


def _linha(r, escala: float) -> None:
    with st.container(key=f"linha-{r.id_territorio}"):
        c = st.columns(COLS, vertical_alignment="center")
        aviso = " · ⚠ limite aproximado" if r.limite_aproximado else ""
        c[0].markdown(f'<div class="fw-tab-nome">{r.nome_exib}</div>'
                      f'<div class="fw-tab-meta">{r.tipo} · {r.uf}{aviso}</div>', unsafe_allow_html=True)
        c[1].markdown(f'<div class="fw-tab-num" style="text-align:right" title="{r.posicao_texto or ""}">'
                      f'{E.num(r.cdev_2026)}</div>', unsafe_allow_html=True)
        c[2].markdown(f'<span title="{r.posicao_texto or ""}">{E.badge(r.classificacao)}</span>',
                      unsafe_allow_html=True)
        _, cor = E.classe(r.classificacao)
        c[3].markdown(
            f'<div title="2026: {E.num(r.densidade_2026, 1)} · mediana: {E.num(r.densidade_mediana, 1)} '
            f'(por 1.000 km²)">{C.barra_com_marca(r.densidade_2026, r.densidade_mediana, cor, escala)}</div>',
            unsafe_allow_html=True)
        c[4].button(":material/arrow_forward:", key=f"abrir-{r.id_territorio}", help="Abrir território",
                    on_click=estado.ir, kwargs=dict(a=r.id_territorio, v="territorio", m=None))


def render() -> None:
    a = D.alerta()
    E.html(f'<div class="fw-titulo">Painel de alerta</div>'
           f'<div>{E.chip("Territórios do Cerrado")}{E.chip(f"{D.ANO_ATUAL} até {D.FIM:%d/%m} × 2019–2025")}</div>')
    _kpis(a)
    f = _filtrar(a)
    pagina = st.session_state.setdefault("al_pagina", 1)
    with st.container(key="cardtabela"):
        cab = st.columns(COLS, vertical_alignment="center")
        for col, (txt, alinh) in zip(cab, [("Território", "left"), ("2026", "right"), ("Situação", "left"),
                                           ("Densidade × mediana", "left"), ("", "left")]):
            col.markdown(f'<div class="fw-tab-cab" style="text-align:{alinh}">{txt}</div>',
                         unsafe_allow_html=True)
        if f.empty:
            st.caption("Nenhum território com esses filtros.")
        # escala comum a todas as linhas (percentil 90 das densidades): barras comparáveis entre si
        escala = float(a[["densidade_2026", "densidade_mediana"]].max(axis=1).quantile(0.9)) or 1.0
        for r in f.head(pagina * POR_PAGINA).itertuples():
            _linha(r, escala)
        if len(f) > pagina * POR_PAGINA:
            if st.button(f"Mostrar mais ({E.num(len(f) - pagina * POR_PAGINA)})", key="al_mais"):
                st.session_state["al_pagina"] = pagina + 1
                st.rerun()
    E.html(f'<div class="fw-rodape">{E.num(len(f))} de {E.num(len(a))} territórios ≥ 10 km² · '
           'traço = mediana 2019–2025 · territórios se sobrepõem: não somar</div>')
