"""FireWatch · Calendário de Atividade de Fogo (Parte C do plano).

Rodar da raiz do projeto:

    .venv/bin/streamlit run app/app.py

Telas: Meu território (principal) · Painel de alerta · Por sensor · Modo MIF ·
Dentro × entorno. Todos os números vêm de `firewatch.indicadores` e `firewatch.territorios`;
o app só escolhe o recorte e desenha.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

st.set_page_config(page_title="FireWatch · Calendário de Fogo", page_icon="🔥", layout="wide",
                   initial_sidebar_state="collapsed")

import dados as D  # noqa: E402
import estado  # noqa: E402
import estilo as E  # noqa: E402
from firewatch import indicadores as ind  # noqa: E402
from telas import alerta, entorno, mif, sensor, territorio  # noqa: E402
from telas.area import seletor_outra_area  # noqa: E402

E.aplicar_css()


# --------------------------------------------------------------------------- estado

p = estado.ler()
area = D.resolver_area(p["a"])
if p["a"] != area.chave:
    estado.ir(a=area.chave)


@st.cache_data(show_spinner=False, max_entries=64)
def _mes_padrao(chave, tipo, geojson) -> str:
    """Mês em foco padrão: o pico típico da estação de fogo da área, no ano em curso."""
    s = D.serie(chave, tipo, geojson)
    mes = D.FIM.month
    if not s.empty:
        pico = ind.janela_critica(s)["mes_pico"]
        if pico and pico <= D.FIM.month:
            mes = pico
    return f"{D.ANO_ATUAL}-{mes:02d}"


meses_validos = [f"{a}-{m:02d}" for a in reversed(D.ANOS) for m in range(12, 0, -1)
                 if (a, m) <= (D.FIM.year, D.FIM.month)]
mes_txt = p["m"] if p["m"] in meses_validos else _mes_padrao(area.chave, area.tipo, area.geojson)
ano, mes = (int(x) for x in mes_txt.split("-"))
corte = p["c"] or D.cfg()["mif_data_corte"]


# --------------------------------------------------------------------------- topo

def topo() -> None:
    """Faixa amarela do topo, como a capa do pitch: marca, navegação, área e mês."""
    with st.container(key="topo"):
        _topo()


def _topo() -> None:
    c_logo, c_nav, c_busca, c_mais, c_mes = st.columns([1.45, 2.4, 2.2, 1.3, 0.95],
                                                       vertical_alignment="center", gap="small")
    with c_logo:
        E.html(f'<div class="fw-logo"><div class="fw-logo-icone">{E.LOGO_SVG}</div>FireWatch</div>')
    with c_nav:
        atual = "alerta" if p["v"] == "alerta" else "territorio"
        st.segmented_control(
            "Tela", ["territorio", "alerta"], default=atual, required=True,
            format_func={"territorio": "Meu território", "alerta": "Painel de alerta"}.get,
            key=f"nav_{atual}", label_visibility="collapsed",
            on_change=estado.ir_do_widget, args=(f"nav_{atual}", "v"))
    with c_busca:
        lista = D.territorios_lista()
        ids = lista["id_territorio"].tolist()
        rotulos = dict(zip(lista["id_territorio"], lista["nome_exib"]))
        k = f"busca_{area.chave}"
        st.selectbox(
            "Território", ids, index=ids.index(area.chave) if area.territorio else None,
            format_func=rotulos.get, placeholder=area.nome,
            key=k, label_visibility="collapsed", on_change=estado.ir_do_widget, args=(k, "a"))
    with c_mais:
        seletor_outra_area()
    with c_mes:
        k = f"mes_{mes_txt}"
        st.selectbox("Mês em foco", meses_validos, index=meses_validos.index(mes_txt),
                     format_func=lambda t: E.mes_ano(int(t[:4]), int(t[5:])), key=k,
                     label_visibility="collapsed", on_change=estado.ir_do_widget, args=(k, "m"),
                     help="Mês em foco")


def cabecalho_detalhe(titulo: str) -> None:
    c1, c2, c3 = st.columns([0.06, 0.76, 0.18], vertical_alignment="center")
    with c1:
        st.button(":material/arrow_back:", key="voltar", on_click=estado.ir,
                  kwargs=dict(v="territorio"), help="Voltar")
    with c2:
        E.html(f'<div class="fw-sobretitulo">{area.nome}</div>'
               f'<div class="fw-titulo" style="font-size:2.6rem;margin:.15rem 0 0">{titulo}</div>')


# --------------------------------------------------------------------------- telas

v = p["v"]
if v in ("sensor", "mif", "entorno"):
    if v == "entorno" and not area.territorio:
        v = "territorio"
if v in ("territorio", "alerta"):
    topo()

if v == "alerta":
    alerta.render()
elif v == "sensor":
    cabecalho_detalhe("Por sensor")
    sensor.render(area)
elif v == "mif":
    cabecalho_detalhe("Modo MIF")
    mif.render(area, ano, corte)
elif v == "entorno":
    cabecalho_detalhe("Dentro × entorno")
    entorno.render(area, ano)
else:
    territorio.render(area, ano, mes, corte)
