"""Tela principal: o calendário de fogo de uma área."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as C
import dados as D
import estado
import estilo as E
from telas import boletim

AMOSTRA_FOCOS = 20_000


# --------------------------------------------------------------------------- partes

def _titulo(a: D.Area) -> None:
    """Nome em caixa alta (como o título dos slides) e poucas pílulas de contexto."""
    chips = []
    if a.territorio:
        f = D.ficha(a.chave)
        chips += [f["tipo"], f["grupo"] if f["tipo"] == "UC" else (f.get("etnia") or "Terra Indígena"),
                  f.get("uf") or ""]
        if f.get("limite_aproximado"):
            chips.append(("limite aproximado", "aviso"))
    elif a.tipo == "cerrado":
        chips.append("bioma")
    if a.area_km2:
        chips.append(f"{E.num(a.area_km2)} km²")
    if a.area_km2 and a.area_km2 < float(D.cfg()["territorio_area_min_km2"]):
        chips.append(("estatísticas instáveis", "aviso"))
    html_chips = "".join(E.chip(*c) if isinstance(c, tuple) else E.chip(c) for c in chips if c)
    E.html(f'<div class="fw-titulo">{a.nome}</div><div>{html_chips}</div>')


def _posicao(d: dict) -> str:
    """Linha curta "2º de 8" com a mediana no tooltip."""
    return (f'<div class="fw-sub" title="mediana 2019–2025: {E.num(d["mediana"])} células-dia">'
            f'{d["posicao_texto"] or "–"}</div>')


def _cartoes(pac: dict, ano: int, mes: int) -> None:
    ac, tm, jn, rt = pac["ano_em_curso"], pac["termometro"], pac["janela"], pac["ritmo"]
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:      # bloco de destaque, vermelho chapado
        extra = (f'<div style="margin-top:.7rem">{E.badge(ac["classificacao"])}</div>'
                 + C.faixa_pontos(ac["por_ano"], ac["ano"], ac["mediana"], E.AMARELO) + _posicao(ac))
        E.html(C.cartao(f"{ac['ano']} até {D.FIM:%d/%m}", E.num(ac["valor"]), extra, alto=True,
                        destaque=True))
    with c2:
        if tm is None:
            E.html(C.cartao(E.mes_ano(ano, mes), "–", "", alto=True))
        else:
            _, cor = E.classe(tm["classificacao"])
            rot = E.MESES_LONGOS[mes - 1] + f" {ano}" + (f" · até {tm['ate_dia']}" if tm["parcial"] else "")
            extra = (f'<div style="margin-top:.7rem">{E.badge(tm["classificacao"])}</div>'
                     + C.faixa_pontos(tm["por_ano"], ano, tm["mediana"], cor) + _posicao(tm))
            E.html(C.cartao(rot, E.num(tm["valor"]), extra, alto=True))
    with c3:
        if jn["semana_inicio"] is None:
            E.html(C.cartao("Estação de fogo", "–", "", alto=True))
        else:
            valor = f'{E.MESES[jn["mes_inicio"] - 1]} → {E.MESES[jn["mes_fim"] - 1]}'
            ritmo = ""
            if rt and rt["semanas_adiantado"]:
                n = abs(rt["semanas_adiantado"])
                txt = "adiantado" if rt["semanas_adiantado"] > 0 else "atrasado"
                ritmo = E.chip(f"{D.ANO_ATUAL} {txt} {n} sem.",
                               "laranja" if rt["semanas_adiantado"] > 0 else "azul")
            E.html(C.cartao("Estação de fogo", valor,
                            f'<div class="fw-sub">pico em {E.MESES_LONGOS[jn["mes_pico"] - 1]}</div>'
                            f'<div style="margin-top:1.1rem">{ritmo}</div>', alto=True))


def _mapa(a: D.Area, ano: int, mes: int, vazio: bool) -> None:
    with st.container(key="cardmapa"):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        modos = ["fogo", "anomalia", "focos"]
        modo = c1.segmented_control(
            "Camada", modos, default="focos" if vazio else "fogo", required=True,
            format_func={"fogo": "Hexágonos", "anomalia": "Anomalia", "focos": "Focos"}.get,
            key="modo_mapa", label_visibility="collapsed")
        fundo = c2.segmented_control("Fundo", ["satelite", "mapa"], default="satelite", required=True,
                                     format_func={"satelite": "Satélite", "mapa": "Mapa"}.get,
                                     key="fundo_mapa", label_visibility="collapsed")
        fig = C.figura_mapa(a, fundo)
        legenda = ""
        if modo in ("fogo", "anomalia"):
            fc, df = D.mapa_hex(a, ano, mes, modo)
            if modo == "fogo":
                C.camada_hex(fig, fc, df, "cdev", False, "células-dia com fogo")
                grad = ",".join(E.RAMPA)
                legenda = (f'<span class="fw-escala-barra" style="background:linear-gradient(90deg,{grad})"></span>'
                           f'células-dia com fogo · {E.mes_ano(ano, mes)}')
            else:
                C.camada_hex(fig, fc, df, "anomalia", True, "vs. mediana")
                legenda = (f'menos<span class="fw-escala-barra" style="background:linear-gradient(90deg,'
                           f'{E.AZUL},#E9E6E0,{E.MARCA})"></span>mais · {E.mes_ano(ano, mes)} '
                           f'× mediana 2019–2025')
            if df.empty:
                legenda = f"Sem fogo detectado em {E.mes_ano(ano, mes)}"
        else:
            if a.tipo == "cerrado":
                legenda = "Focos: escolha uma área menor que o bioma"
            else:
                ini, fim = D.periodo_mes(ano, mes)
                with st.spinner("Buscando focos…"):
                    f = D.focos(a.geojson, ini, fim)
                f = f[f["satelite"] != "N21"] if not f.empty else f
                mostra = f.sample(AMOSTRA_FOCOS, random_state=0) if len(f) > AMOSTRA_FOCOS else f
                if not mostra.empty:
                    C.camada_focos(fig, mostra)
                amostra = f" (amostra de {E.num(AMOSTRA_FOCOS)})" if len(f) > AMOSTRA_FOCOS else ""
                legenda = (E.legenda_item(C.CORES_SENSOR["VIIRS"], "VIIRS")
                           + E.legenda_item(C.CORES_SENSOR["MODIS"], "MODIS")
                           + f'<span style="margin-left:.6rem">{E.num(len(f))} focos · '
                             f'{E.mes_ano(ano, mes)}{amostra}</span>')
        E.grafico(fig, key="mapa")
        E.html(f'<div class="fw-escala" style="margin:.1rem .6rem .3rem">{legenda}</div>')


def _calendario(pac: dict, ano: int, mes: int) -> None:
    with st.container(key="cardcal"):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(C.titulo_card("Calendário de fogo"), unsafe_allow_html=True)
        modo = c2.segmented_control("Escala", ["mes", "semana"], default="mes", required=True,
                                    format_func={"mes": "Mês", "semana": "Semana"}.get,
                                    key="modo_cal", label_visibility="collapsed")
        if modo == "mes":
            E.html(C.calendario_mensal(pac["mensal"], (ano, mes)))
        else:
            E.html(C.calendario_semanal(pac["semanal"]))


def _acumulado(pac: dict) -> None:
    """Curva acumulada do ano em curso × mediana e faixa dos anos históricos."""
    w = pac["semanal"].copy()
    a0, a1 = (int(x) for x in D.cfg()["periodo_historico"])
    w["acum"] = w.groupby("ano")["cdev"].cumsum()
    hist = w[(w.ano >= a0) & (w.ano <= a1)].pivot(index="semana", columns="ano", values="acum")
    atual = w[w.ano == D.ANO_ATUAL]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist.max(axis=1), mode="lines", line=dict(width=0),
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=hist.index, y=hist.min(axis=1), mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(45,108,176,.10)", hoverinfo="skip"))
    # mediana das curvas acumuladas (e não acumulado das medianas): fica dentro da faixa mín–máx
    fig.add_trace(go.Scatter(x=hist.index, y=hist.median(axis=1), mode="lines",
                             name="mediana 2019–2025", line=dict(color=E.AZUL, width=2, dash="dot"),
                             hovertemplate="mediana: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=atual["semana"], y=atual["acum"], mode="lines", name=str(D.ANO_ATUAL),
                             line=dict(color=E.MARCA, width=2.6),
                             hovertemplate=f"{D.ANO_ATUAL}: %{{y:,.0f}}<extra></extra>"))
    if not atual.empty:
        u = atual.iloc[-1]
        fig.add_trace(go.Scatter(x=[u["semana"]], y=[u["acum"]], mode="markers",
                                 marker=dict(size=10, color=E.MARCA, line=dict(width=2, color="white")),
                                 hoverinfo="skip"))
    ticks = [int(round(i * 52 / 12)) + 1 for i in range(12)]
    E.layout(fig, 260)
    fig.update_xaxes(tickvals=ticks, ticktext=E.MESES, range=[1, 53])
    fig.update_layout(hovermode="x unified")
    fig.update_traces(selector=dict(mode="lines"), hoverlabel=dict(namelength=0))
    with st.container(key="cardacum"):
        E.html(C.titulo_card("Acumulado do ano",
                             E.legenda_item(E.MARCA, str(D.ANO_ATUAL))
                             + E.legenda_item(E.AZUL, "mediana 2019–2025", tracejado=True)
                             + '<span class="fw-leg"><span class="fw-leg-mark" style="height:10px;border:none;'
                               'background:rgba(45,108,176,.2)"></span>mín–máx</span>'))
        E.grafico(fig, key="acumulado")


def _acoes(a: D.Area, ano: int, mes: int, pac: dict) -> None:
    cols = st.columns([1.25, 1.15, 1.6, 1.4, 1.05, 0.55], vertical_alignment="center")
    cols[0].button("Por sensor", icon=":material/show_chart:", on_click=estado.ir,
                   kwargs=dict(v="sensor"), width="stretch")
    cols[1].button("Modo MIF", icon=":material/vertical_split:", on_click=estado.ir,
                   kwargs=dict(v="mif"), width="stretch")
    if a.territorio:
        cols[2].button("Dentro × entorno", icon=":material/radio_button_checked:",
                       on_click=estado.ir, kwargs=dict(v="entorno"), width="stretch")
    cols[4].download_button("Boletim", data=boletim.gerar(a, ano, mes),
                            file_name=f"firewatch_boletim_{a.chave.replace(':', '_')}.html",
                            mime="text/html", icon=":material/description:", width="stretch",
                            help="Página para imprimir ou salvar em PDF")
    with cols[5].popover(":material/download:", help="Baixar dados"):
        st.download_button("Série mensal (CSV)", pac["mensal"].to_csv(index=False).encode(),
                           f"firewatch_serie_{a.chave.replace(':', '_')}.csv", "text/csv",
                           icon=":material/table:", width="stretch")
        if a.tipo == "cerrado":
            st.caption("Focos: escolha uma área menor que o bioma.")
        else:
            ini, fim = D.periodo_mes(ano, mes)
            if st.button(f"Preparar focos de {E.mes_ano(ano, mes)}", icon=":material/scatter_plot:",
                         width="stretch"):
                with st.spinner("Lendo focos…"):
                    f = D.focos(a.geojson, ini, fim, limite=int(D.cfg()["focos_limite_linhas"]))
                if f.attrs.get("truncado"):
                    st.warning(f.attrs["aviso"])
                st.download_button(f"Baixar {E.num(len(f))} focos (CSV)", f.to_csv(index=False).encode(),
                                   f"firewatch_focos_{ini[:7]}.csv", "text/csv", type="primary",
                                   width="stretch")


# --------------------------------------------------------------------------- tela

def render(a: D.Area, ano: int, mes: int, corte: str) -> None:
    with st.spinner("Carregando…"):
        pac = D.pacote(a.chave, a.tipo, a.geojson, ano, mes)
    _titulo(a)
    if pac["vazio"]:
        st.info("Nenhuma célula de 1 km cai inteira dentro desta área. Veja os focos no mapa.",
                icon=":material/info:")
        _mapa(a, ano, mes, vazio=True)
        return
    _cartoes(pac, ano, mes)
    _mapa(a, ano, mes, vazio=False)
    _calendario(pac, ano, mes)
    _acumulado(pac)
    _acoes(a, ano, mes, pac)
    E.html('<div class="fw-rodape">Atividade de fogo detectada por satélite, em células-dia de 1 km · '
           'histórico curto: 2019–2025 · 2026 após julho é preliminar</div>')
