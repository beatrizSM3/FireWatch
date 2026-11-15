"""Peças visuais reutilizadas pelas telas (HTML e figuras plotly). Só desenham."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import estilo as E
from dados import ANO_ATUAL, ANOS, FIM, Area, entorno_geojson, limites

SATELITE = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/"
            "tile/{z}/{y}/{x}")


# --------------------------------------------------------------------------- cartões

def cartao(rotulo: str, valor: str, extra: str = "", direita: str = "", classe_valor="fw-valor",
           alto: bool = False, destaque: bool = False) -> str:
    topo = (f'<div class="fw-linha-titulo"><div class="fw-rotulo">{rotulo}</div>{direita}</div>'
            if direita else f'<div class="fw-rotulo">{rotulo}</div>')
    classes = "fw-card-html" + (" fw-alto" if alto else "") + (" fw-card-hero" if destaque else "")
    return f'<div class="{classes}">{topo}<div class="{classe_valor}">{valor}</div>{extra}</div>'


def faixa_pontos(por_ano: pd.DataFrame, ano: int, mediana: float | None, cor: str) -> str:
    """Faixa horizontal: um ponto por ano (cinza), o ano escolhido em destaque e um traço na
    mediana. Mostra de relance onde o valor está no histórico."""
    if por_ano is None or por_ano.empty:
        return ""
    v = por_ano.set_index("ano")["cdev"]
    vmax = float(v.max()) or 1.0
    pos = lambda x: 3 + 94 * float(x) / vmax   # noqa: E731
    partes = ['<div class="fw-faixa"><div class="fw-faixa-trilho"></div>']
    if mediana is not None:
        partes.append(f'<div class="fw-faixa-mediana" style="left:{pos(mediana)}%" '
                      f'title="mediana {E.num(mediana)}"></div>')
    for a_, x in v.items():
        if a_ == ano:
            continue
        partes.append(f'<div class="fw-faixa-ponto" style="left:{pos(x)}%" '
                      f'title="{a_}: {E.num(x)}"></div>')
    if ano in v.index:
        partes.append(f'<div class="fw-faixa-ponto fw-faixa-atual" style="left:{pos(v[ano])}%;'
                      f'background:{cor}" title="{ano}: {E.num(v[ano])}"></div>')
    partes.append("</div>")
    return "".join(partes)


def titulo_card(titulo: str, direita: str = "") -> str:
    return (f'<div class="fw-linha-titulo"><p class="fw-titulo-card">{titulo}</p>'
            f'<div>{direita}</div></div>')


# --------------------------------------------------------------------------- calendário

def calendario_mensal(mensal: pd.DataFrame, foco: tuple[int, int] | None) -> str:
    """Grade ano × mês. Cor = células-dia com fogo; hachura = sem satélite suficiente;
    tracejado = mês ainda sem dado; contorno = mês em foco."""
    m = mensal.set_index(["ano", "mes"])
    vmax = float(mensal["cdev"].max() or 0)
    cols = "46px repeat(12, minmax(0,1fr))"
    h = [f'<div class="fw-cal" style="grid-template-columns:{cols}"><div></div>']
    h += [f'<div class="fw-cal-mes">{n}</div>' for n in E.MESES]
    for ano in ANOS:
        atual = " atual" if ano == ANO_ATUAL else ""
        h.append(f'<div class="fw-cal-ano{atual}">{ano}</div>')
        for mes in range(1, 13):
            classes, estilo, dica = ["fw-cal-cel"], "", E.mes_ano(ano, mes)
            if (ano, mes) not in m.index:
                classes.append("fw-futuro")
                dica += " · ainda sem dado"
            else:
                r = m.loc[(ano, mes)]
                if bool(r["cobertura_reduzida"]):
                    classes.append("fw-hachura")
                    dica += " · satélite fora do ar em parte do mês"
                else:
                    estilo = f"background:{E.cor_valor(r['cdev'], vmax)}"
                    dica += f" · {E.num(r['cdev'])} células-dia com fogo"
                if bool(r["parcial"]):
                    dica += f" (até {FIM.day:02d}/{FIM.month:02d})"
                if r.get("dias_nrt", 0) > 0:
                    dica += " · preliminar"
            if foco == (ano, mes):
                classes.append("fw-foco")
            h.append(f'<div class="{" ".join(classes)}" style="{estilo}" title="{dica}"></div>')
    h.append("</div>")
    return "".join(h) + escala(vmax)


def _cabecalho_semanas() -> list[str]:
    h = []
    for i, nome in enumerate(E.MESES):
        ini = int(round(i * 52 / 12)) + 2
        h.append(f'<div class="fw-cal-mes" style="grid-column:{ini} / span 4;text-align:left">{nome}</div>')
    return h


def semana_do_corte(corte: str) -> int:
    mes, dia = (int(p) for p in corte.split("-"))
    doy = pd.Timestamp(2023, mes, dia).day_of_year
    return (doy - 1) // 7 + 1


def calendario_semanal(semanal: pd.DataFrame, corte: str | None = None) -> str:
    """Grade ano × semana. Com `corte` (Modo MIF), semanas até o corte em azul (precoce) e
    depois em laranja (tardio), com uma linha na semana do corte."""
    w = semanal.set_index(["ano", "semana"])
    s_corte = semana_do_corte(corte) if corte else None
    if s_corte:
        pre = semanal[semanal.semana <= s_corte]["cdev"].max() or 0
        pos = semanal[semanal.semana > s_corte]["cdev"].max() or 0
    vmax = float(semanal["cdev"].max() or 0)
    cols = "46px repeat(53, minmax(0,1fr))"
    h = [f'<div class="fw-cal fw-cal-sem" style="grid-template-columns:{cols};gap:3px"><div></div>']
    h += _cabecalho_semanas()
    for ano in ANOS:
        atual = " atual" if ano == ANO_ATUAL else ""
        h.append(f'<div class="fw-cal-ano{atual}" style="grid-column:1">{ano}</div>')
        for sem in range(1, 54):
            classes, estilo = ["fw-cal-cel"], ""
            dica = f"{ano} · semana {sem}"
            if (ano, sem) not in w.index:
                classes.append("fw-futuro")
            else:
                r = w.loc[(ano, sem)]
                if bool(r["cobertura_reduzida"]):
                    classes.append("fw-hachura")
                    dica += " · satélite fora do ar"
                else:
                    if s_corte:
                        cor = (E.cor_valor(r["cdev"], pre, E.RAMPA_PRECOCE) if sem <= s_corte
                               else E.cor_valor(r["cdev"], pos, E.RAMPA_TARDIO))
                    else:
                        cor = E.cor_valor(r["cdev"], vmax)
                    estilo = f"background:{cor}"
                    dica += f" · {E.num(r['cdev'])}"
            if s_corte and sem == s_corte:
                estilo += f";box-shadow:3px 0 0 0 {E.TINTA}"
            h.append(f'<div class="{" ".join(classes)}" style="{estilo}" title="{dica}"></div>')
    h.append("</div>")
    if s_corte:
        leg = (f'<div class="fw-escala">'
               f'<span class="fw-escala-barra" style="background:linear-gradient(90deg,{",".join(E.RAMPA_PRECOCE)})"></span>precoce'
               f'<span class="fw-escala-barra" style="margin-left:.8rem;background:linear-gradient(90deg,{",".join(E.RAMPA_TARDIO)})"></span>tardio'
               f'<span class="fw-escala-hach fw-hachura" style="margin-left:.8rem"></span>sem satélite</div>')
        return "".join(h) + leg
    return "".join(h) + escala(vmax)


def escala(vmax: float) -> str:
    grad = ",".join(E.RAMPA)
    return (f'<div class="fw-escala">0<span class="fw-escala-barra" '
            f'style="background:linear-gradient(90deg,{E.VAZIO},{grad})"></span>{E.num(vmax)}'
            f'<span style="margin-left:.9rem" class="fw-escala-hach fw-hachura"></span>sem satélite'
            f'<span style="margin-left:.9rem" class="fw-escala-hach fw-futuro"></span>sem dado ainda</div>')


# --------------------------------------------------------------------------- barras HTML

def barra_com_marca(valor: float, referencia: float | None, cor: str, maximo: float) -> str:
    """Barra do valor com um traço na referência (ex.: densidade 2026 × mediana)."""
    maximo = maximo or 1.0
    w = min(100.0, 100.0 * (valor or 0) / maximo)
    tick = ("" if referencia is None or pd.isna(referencia) else
            f'<div class="fw-barra-tick" style="left:{min(100.0, 100.0 * referencia / maximo)}%"></div>')
    return (f'<div class="fw-barra"><div class="fw-barra-fill" style="width:{w}%;background:{cor}">'
            f'</div>{tick}</div>')


def split(precoce: float, tardio: float, forte: bool = True) -> str:
    """Barra dividida precoce (azul) | tardio (laranja)."""
    tot = (precoce or 0) + (tardio or 0)
    if tot <= 0:
        return '<div class="fw-split"><div style="flex:1;background:#ECE8E1"></div></div>'
    a, b = (E.AZUL, E.LARANJA) if forte else ("#8FA8CC", "#EDAA80")
    return (f'<div class="fw-split"><div style="flex:{precoce};background:{a}"></div>'
            f'<div style="flex:{tardio};background:{b}"></div></div>')


# --------------------------------------------------------------------------- mapa

def _zoom(lon0, lat0, lon1, lat1, largura=1100, altura=520) -> tuple[float, dict]:
    dlon = max(lon1 - lon0, 0.01)
    dlat = max(lat1 - lat0, 0.01)
    z = min(math.log2(largura * 360 / (256 * dlon)), math.log2(altura * 170 / (256 * dlat)))
    return max(min(z - 0.35, 13), 3), dict(lon=(lon0 + lon1) / 2, lat=(lat0 + lat1) / 2)


def figura_mapa(a: Area, fundo: str = "satelite", altura: int = 520) -> go.Figure:
    """Mapa base com o contorno da área (e o anel do entorno nos territórios)."""
    # traço invisível: sem nenhum traço de mapa, o plotly desenha eixos cartesianos
    fig = go.Figure(go.Scattermap(lon=[], lat=[], hoverinfo="skip"))
    camadas = []
    if fundo == "satelite":
        camadas.append(dict(below="traces", sourcetype="raster", source=[SATELITE], opacity=0.92))
    contorno = "#FFFFFF" if fundo == "satelite" else E.TINTA
    if a.geojson:
        camadas.append(dict(sourcetype="geojson", source=json.loads(a.geojson), type="line",
                            color=contorno, line=dict(width=1.3 if a.tipo == "cerrado" else 2.2)))
    if a.territorio:
        anel = entorno_geojson(a.chave)
        if anel:
            camadas.append(dict(sourcetype="geojson", source=json.loads(anel), type="line",
                                color=contorno, opacity=0.8, line=dict(width=1.2, dash=[2, 2])))
    z, centro = _zoom(*limites(a), altura=altura)
    fig.update_layout(
        map=dict(style="white-bg" if fundo == "satelite" else "carto-positron",
                 center=centro, zoom=z, layers=camadas),
        height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False, font=dict(family="Nunito, sans-serif"),
        hoverlabel=dict(bgcolor=E.SUPERFICIE, font=dict(family="Nunito, sans-serif", color=E.TINTA)),
    )
    return fig


def camada_hex(fig: go.Figure, fc: dict, df: pd.DataFrame, coluna: str, divergente: bool,
               rotulo: str) -> None:
    if df.empty:
        return
    z = df[coluna].astype(float)
    if divergente:
        lim = float(np.nanmax(np.abs(z))) or 1.0
        escala, zmin, zmax = E.DIVERGENTE, -lim, lim
        dica = "%{z:+,.0f} " + rotulo + "<extra></extra>"
    else:
        # raiz quadrada na cor (como no calendário): a rampa recebe sqrt(z)
        escala, zmin, zmax = E.escala_plotly(E.RAMPA), 0, math.sqrt(float(z.max()) or 1)
        df = df.assign(_cor=np.sqrt(z))
        dica = "%{customdata:,.0f} " + rotulo + "<extra></extra>"
    fig.add_trace(go.Choroplethmap(
        geojson=fc, locations=df["id"], featureidkey="id",
        z=df["_cor"] if not divergente else z, customdata=z,
        colorscale=escala, zmin=zmin, zmax=zmax, showscale=False,
        marker=dict(opacity=0.88, line=dict(width=0.6, color="rgba(255,255,255,.75)")),
        hovertemplate=dica))


CORES_SENSOR = {"VIIRS": "#F7B538", "MODIS": "#E8467C"}


def camada_focos(fig: go.Figure, df: pd.DataFrame) -> None:
    for sensor, cor in CORES_SENSOR.items():
        d = df[df["sensor"] == sensor]
        if d.empty:
            continue
        fig.add_trace(go.Scattermap(
            lon=d["longitude"], lat=d["latitude"], mode="markers", name=sensor,
            marker=dict(size=6, color=cor, opacity=0.9),
            customdata=np.stack([d["satelite"], d["data_local"].astype(str), d["frp"]], axis=-1),
            hovertemplate="%{customdata[0]} · %{customdata[1]}<br>FRP %{customdata[2]} MW<extra></extra>"))
