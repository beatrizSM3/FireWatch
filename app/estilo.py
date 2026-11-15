"""Identidade visual do app: cores, CSS, tema dos gráficos e formatação de números.

Segue o modelo do slide de pitch: fundo creme, vermelho profundo e amarelo, títulos pesados
em caixa alta, rótulos em pílula e blocos chapados (sem sombra). Tudo que é "aparência" mora
aqui, para as telas ficarem só com o conteúdo.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------- cores da marca

CREME = "#FFF3E2"          # fundo da página (o creme dos slides)
SUPERFICIE = "#FFFBF4"     # blocos
VERMELHO = "#9E2622"       # vermelho dos slides: títulos, bloco de destaque, botões ativos
AMARELO = "#FFD263"        # amarelo dos slides: pílulas, faixa do topo, botões
AMARELO_2 = "#FBE7B5"      # amarelo claro (trilhos e pílulas neutras)
TINTA = "#2A1A17"
TINTA_2 = "#5A4540"
MUTED = "#8C756C"
LINHA = "#F1DFC6"
MARCA = VERMELHO
FUNDO = CREME
CHIP = AMARELO_2

# séries (identidade): azul = VIIRS / dentro / precoce; laranja = MODIS calibrado / entorno / tardio
# (par validado para daltonismo contra o fundo dos blocos)
AZUL = "#2D6CB0"
LARANJA = "#E0672E"
CINZA = "#A8968A"          # MODIS bruto: sempre pontilhado (segunda codificação além da cor)

# classificação no histórico (escala divergente em torno da mediana; sempre com texto)
CLASSE = {
    "recorde (acima do máximo histórico)": ("recorde", "#5C1A2E"),
    "acima da mediana": ("acima da mediana", "#C8372D"),
    "abaixo da mediana": ("abaixo da mediana", "#4A86C5"),
    "abaixo do mínimo histórico": ("abaixo do mínimo", "#1F4E86"),
    "sem histórico comparável": ("sem histórico", "#A8968A"),
}

# rampa sequencial "fogo" (amarelo -> vermelho -> vinho), no calendário e nos hexágonos
RAMPA = ["#FFE9AE", "#FFD263", "#F7A946", "#E8722F", "#C8372D", "#9E2622", "#5C1A2E"]
VAZIO = "#F6E6CC"          # zero fogo (diferente de "sem dado", que é hachurado)
# rampas do Modo MIF
RAMPA_PRECOCE = ["#DCE8F6", "#A9C6E8", "#6E9FD6", "#3F78BD", "#24558F"]
RAMPA_TARDIO = ["#FFE3A6", "#FBB65C", "#EC7E35", "#C8372D", "#7A1F24"]
# anomalia: azul (menos que o normal) - creme neutro - vermelho (mais que o normal)
DIVERGENTE = [[0.0, "#2D6CB0"], [0.5, "#F3E6D2"], [1.0, "#C8372D"]]

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                "setembro", "outubro", "novembro", "dezembro"]


def classe(texto: str) -> tuple[str, str]:
    """(rótulo curto, cor) de uma classificação de `indicadores.classificar`."""
    return CLASSE.get(texto, (texto, CINZA))


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def interpolar(rampa: list[str], t: float) -> str:
    """Cor da rampa na posição t (0..1)."""
    t = min(max(float(t), 0.0), 1.0) * (len(rampa) - 1)
    i = min(int(t), len(rampa) - 2)
    f = t - i
    a, b = _hex_rgb(rampa[i]), _hex_rgb(rampa[i + 1])
    return "#" + "".join(f"{round(a[k] + (b[k] - a[k]) * f):02X}" for k in range(3))


def escala_plotly(rampa: list[str]) -> list[list]:
    return [[i / (len(rampa) - 1), c] for i, c in enumerate(rampa)]


def cor_valor(valor: float, maximo: float, rampa=RAMPA) -> str:
    """Cor de um valor na rampa, com raiz quadrada (os meses chuvosos não somem)."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return VAZIO
    if valor <= 0 or not maximo:
        return VAZIO
    return interpolar(rampa, 0.08 + 0.92 * math.sqrt(valor / maximo))


# --------------------------------------------------------------------------- números

def num(v, casas: int = 0) -> str:
    """Número no formato brasileiro: 3.120 / 2,5."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v, casas: int = 0) -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{num(v * 100, casas)}%"


def mes_ano(ano: int, mes: int) -> str:
    return f"{MESES[mes - 1]}/{ano}"


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "na", "no", "nas", "nos"}
_ROMANOS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
_SIGLAS = {"APA", "RPPN", "ARIE", "RDS", "FLONA", "RESEX", "REBIO", "ESEC", "PE", "PN", "TI",
           "UC", "RVS", "MONA", "PARNA"}


def nome_bonito(nome: str) -> str:
    """'PARQUE ESTADUAL DO JALAPÃO' -> 'Parque Estadual do Jalapão'. Nomes já em caixa mista
    (as TIs) ficam como estão."""
    if not isinstance(nome, str) or not nome.isupper():
        return nome
    partes = []
    for i, p in enumerate(nome.split()):
        if p in _ROMANOS or p in _SIGLAS:
            partes.append(p)
        elif i > 0 and p.lower() in _MINUSCULAS:
            partes.append(p.lower())
        else:
            partes.append("-".join(s.capitalize() for s in p.split("-")))
    return " ".join(partes)


# --------------------------------------------------------------------------- HTML

def badge(texto_classificacao: str, prefixo: str = "") -> str:
    rotulo, cor = classe(texto_classificacao)
    return f'<span class="fw-badge" style="background:{cor}">{prefixo}{rotulo}</span>'


def chip(texto: str, tom: str = "neutro") -> str:
    return f'<span class="fw-chip fw-chip-{tom}">{texto}</span>'


def legenda_item(cor: str, texto: str, tracejado: bool = False) -> str:
    estilo = f"border-top:2px dotted {cor};background:none" if tracejado else f"background:{cor}"
    return (f'<span class="fw-leg"><span class="fw-leg-mark" style="{estilo}"></span>'
            f"{texto}</span>")


def html(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


# --------------------------------------------------------------------------- gráficos

CONFIG_PLOTLY = {"displayModeBar": False, "scrollZoom": False, "locale": "pt-BR"}
FONTE = "Lexend, system-ui, sans-serif"


def layout(fig: go.Figure, altura: int = 300, **kw) -> go.Figure:
    """Tema comum: fundo transparente, grade em fio, fonte do app, sem legenda interna
    (a legenda fica no cabeçalho do bloco, como pílulas)."""
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, size=12, color=MUTED),
        showlegend=False, hovermode="x unified",
        hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=LINHA,
                        font=dict(family=FONTE, color=TINTA, size=12)),
        separators=",.",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINHA, ticks="",
                     tickfont=dict(color=MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=LINHA, gridwidth=1, zeroline=False,
                     ticks="", tickfont=dict(color=MUTED), rangemode="tozero")
    fig.update_layout(**kw)
    return fig


def grafico(fig: go.Figure, key: str | None = None) -> None:
    st.plotly_chart(fig, config=CONFIG_PLOTLY, key=key, width="stretch")


# --------------------------------------------------------------------------- CSS

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700;800;900&display=swap');

html, body, .stApp, button, input, textarea, select {{
  font-family: 'Lexend', system-ui, -apple-system, sans-serif !important;
}}
.stApp {{ background: {CREME}; color: {TINTA}; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ max-width: 1240px; padding: 1.8rem 2rem 4rem; }}
/* respiro entre blocos */
[data-testid="stMain"] [data-testid="stVerticalBlock"] {{ gap: 1.6rem; }}
h1, h2, h3 {{ font-family: 'Lexend', sans-serif !important; color: {VERMELHO}; }}
a {{ color: {VERMELHO}; }}

/* ---------- blocos: containers com key começando por "card" (chapados, sem sombra) */
[class*="st-key-card"] {{
  background: {SUPERFICIE}; border-radius: 28px; padding: 1.7rem 1.9rem 1.6rem;
  border: 2px solid {LINHA};
}}
[class*="st-key-card"] [data-testid="stVerticalBlock"] {{ gap: 1rem; }}
[class*="st-key-cardmapa"] {{ padding: .8rem; }}
.fw-card-html {{
  background: {SUPERFICIE}; border-radius: 28px; padding: 1.6rem 1.8rem; height: 100%;
  border: 2px solid {LINHA};
}}
.fw-alto {{ min-height: 230px; }}
/* o Streamlit puxa o markdown 1rem para cima: devolve o respiro abaixo dos blocos HTML */
.fw-card-html, .fw-kpi {{ margin-bottom: 1rem; }}
/* bloco de destaque: vermelho chapado com texto creme, como a faixa dos slides */
.fw-card-hero {{ background: {VERMELHO}; border-color: {VERMELHO}; color: {CREME}; }}
.fw-card-hero .fw-rotulo {{ color: {AMARELO}; }}
.fw-card-hero .fw-valor, .fw-card-hero .fw-valor-xl {{ color: {CREME}; }}
.fw-card-hero .fw-sub {{ color: #F6CFC0; }}
.fw-card-hero .fw-faixa-trilho {{ background: rgba(255,243,226,.25); }}
.fw-card-hero .fw-faixa-ponto {{ background: rgba(255,243,226,.55); border-color: {VERMELHO}; }}
.fw-card-hero .fw-faixa-mediana {{ background: {CREME}; }}
.fw-card-hero .fw-faixa-atual {{ background: {AMARELO} !important; border-color: {VERMELHO}; }}
.fw-card-hero .fw-badge {{ background: {AMARELO} !important; color: {VERMELHO}; }}

.fw-rotulo {{ font-size: .72rem; color: {VERMELHO}; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; margin-bottom: .45rem; }}
.fw-valor {{ font-size: 2.6rem; line-height: 1.05; font-weight: 800; color: {TINTA}; letter-spacing: -0.03em; }}
.fw-valor-xl {{ font-size: 3.8rem; line-height: 1; font-weight: 900; color: {TINTA}; letter-spacing: -0.04em; }}
.fw-sub {{ font-size: .8rem; color: {MUTED}; margin-top: .55rem; }}
.fw-titulo-card {{ font-size: .95rem; font-weight: 800; color: {VERMELHO}; margin: 0; text-transform: uppercase;
  letter-spacing: .04em; display:flex; align-items:center; }}
.fw-titulo-card::before {{ content:""; width:12px; height:12px; background:{AMARELO}; border-radius:3px;
  margin-right:.6rem; flex:none; }}
.fw-linha-titulo {{ display:flex; align-items:center; justify-content:space-between; gap:.8rem; flex-wrap:wrap; }}
.fw-rodape {{ font-size: .74rem; color: {MUTED}; text-align:center; margin-top: .4rem; }}

/* ---------- pílulas */
.fw-badge {{ display:inline-block; color:#fff; font-weight:700; font-size:.66rem; padding:.3rem .8rem;
  border-radius:999px; white-space:nowrap; text-transform:uppercase; letter-spacing:.06em; }}
.fw-chip {{ display:inline-block; font-size:.7rem; font-weight:600; padding:.32rem .9rem; border-radius:999px;
  background:{AMARELO}; color:{VERMELHO}; white-space:nowrap; margin:0 .35rem .35rem 0;
  text-transform:uppercase; letter-spacing:.05em; }}
.fw-chip-aviso {{ background:{VERMELHO}; color:{AMARELO}; }}
.fw-chip-azul {{ background:#DCE8F6; color:#1F4E86; }}
.fw-chip-laranja {{ background:#FDE0C6; color:{VERMELHO}; }}
.fw-chip-neutro {{ background:{AMARELO}; color:{VERMELHO}; }}
.fw-leg {{ display:inline-flex; align-items:center; gap:.45rem; font-size:.68rem; font-weight:600;
  color:{TINTA_2}; background:{AMARELO_2}; border-radius:999px; padding:.28rem .8rem; margin-left:.35rem;
  text-transform:uppercase; letter-spacing:.05em; }}
.fw-leg-mark {{ display:inline-block; width:14px; height:0; border-top:3px solid; border-radius:2px; }}
.fw-leg-mark[style*="background"] {{ height:3px; border:none; }}

/* ---------- topo (faixa amarela) */
[class*="st-key-topo"] {{ background:{AMARELO}; border-radius:28px; padding:.9rem 1.2rem .9rem 1.5rem; }}
.fw-logo {{ display:flex; align-items:center; gap:.5rem; font-weight:900; font-size:1.3rem; color:{VERMELHO};
  letter-spacing:-0.02em; text-transform:uppercase; line-height:1; }}
.fw-logo-icone {{ display:grid; place-items:center; }}
.fw-titulo {{ font-size: clamp(2rem, 4.2vw, 3.6rem); font-weight: 900; letter-spacing: -0.03em; line-height:.98;
  margin: .2rem 0 .8rem; color:{VERMELHO}; text-transform: uppercase; }}
.fw-sobretitulo {{ font-size:.74rem; color:{VERMELHO}; font-weight:700; text-transform:uppercase; letter-spacing:.08em; }}

/* ---------- calendário (grade HTML) */
.fw-cal {{ display:grid; gap:5px; align-items:center; }}
.fw-cal-cel {{ border-radius:8px; height:28px; }}
.fw-cal-sem .fw-cal-cel {{ border-radius:4px; height:20px; }}
.fw-cal-ano {{ font-size:.78rem; color:{TINTA_2}; font-weight:500; padding-right:.4rem; }}
.fw-cal-ano.atual {{ color:{VERMELHO}; font-weight:800; }}
.fw-cal-mes {{ font-size:.68rem; color:{MUTED}; text-align:center; text-transform:uppercase; letter-spacing:.05em; }}
.fw-hachura {{ background: repeating-linear-gradient(135deg, #E9D5B5 0 3px, {SUPERFICIE} 3px 7px) !important; }}
.fw-futuro {{ background: transparent !important; border: 1.5px dashed #E4CDA9; }}
.fw-foco {{ box-shadow: 0 0 0 2px {SUPERFICIE}, 0 0 0 4px {VERMELHO}; }}
.fw-escala {{ display:flex; align-items:center; gap:.5rem; font-size:.7rem; color:{MUTED}; margin-top:.9rem; flex-wrap:wrap; }}
.fw-escala-barra {{ width:100px; height:8px; border-radius:99px; }}
.fw-escala-hach {{ width:18px; height:12px; border-radius:3px; }}

/* ---------- faixa de pontos (posição no histórico) */
.fw-faixa {{ position:relative; height:26px; margin:.8rem 0 .1rem; }}
.fw-faixa-trilho {{ position:absolute; top:12px; left:0; right:0; height:2px; background:{LINHA}; border-radius:2px; }}
.fw-faixa-ponto {{ position:absolute; top:8px; width:10px; height:10px; border-radius:50%; background:#DCC6A6;
  transform:translateX(-50%); border:2px solid {SUPERFICIE}; }}
.fw-faixa-atual {{ top:4px; width:18px; height:18px; border:3px solid {SUPERFICIE}; }}
.fw-faixa-mediana {{ position:absolute; top:4px; width:2px; height:18px; background:{TINTA}; transform:translateX(-50%); }}

/* ---------- barras HTML (painel, MIF, entorno) */
.fw-barra {{ position:relative; height:10px; border-radius:99px; background:{LINHA}; }}
.fw-barra-fill {{ position:absolute; left:0; top:0; bottom:0; border-radius:99px; }}
.fw-barra-tick {{ position:absolute; top:-4px; width:2.5px; height:18px; background:{TINTA}; border-radius:2px; transform:translateX(-50%); }}
.fw-split {{ display:flex; gap:3px; height:14px; }}
.fw-split > div {{ border-radius:99px; min-width:4px; }}

/* ---------- tabela do painel */
[class*="st-key-linha-"] {{ border-bottom: 1.5px solid {LINHA}; padding: .5rem 0 .6rem; }}
[class*="st-key-linha-"]:hover {{ background: #FFF6E6; }}
[class*="st-key-cardtabela"] [data-testid="stVerticalBlock"] {{ gap: .2rem; }}
.fw-tab-cab {{ font-size:.68rem; font-weight:700; color:{VERMELHO}; text-transform:uppercase; letter-spacing:.07em; }}
.fw-tab-nome {{ font-weight:600; color:{TINTA}; font-size:.92rem; line-height:1.3; }}
.fw-tab-meta {{ font-size:.72rem; color:{MUTED}; margin-top:.1rem; }}
.fw-tab-num {{ font-weight:800; color:{TINTA}; font-size:1rem; }}
.fw-tab-txt {{ color:{TINTA_2}; font-size:.88rem; }}
/* blocos do resumo do painel: cor chapada da classificação, com o quadrado amarelo dos slides */
.fw-kpi {{ border-radius:28px; padding:1.4rem 1.6rem; color:{CREME}; position:relative; overflow:hidden; }}
.fw-kpi .fw-rotulo {{ color:{CREME}; opacity:.9; }}
.fw-kpi .fw-valor {{ color:{CREME}; font-size:3rem; font-weight:900; }}
.fw-kpi::after {{ content:""; position:absolute; right:-14px; top:-14px; width:56px; height:56px;
  background:{AMARELO}; border-radius:10px; }}

/* ---------- widgets */
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button, [data-testid="stPopover"] button {{
  border-radius: 999px !important; border: none !important; background: {AMARELO} !important;
  color: {VERMELHO} !important; font-weight: 700 !important; padding: .5rem 1.2rem !important;
  box-shadow: none !important;
}}
[data-testid="stButton"] button p, [data-testid="stDownloadButton"] button p, [data-testid="stPopover"] button p {{
  font-weight: 700 !important; text-transform: uppercase; letter-spacing: .05em; font-size: .78rem;
}}
[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] button:hover, [data-testid="stPopover"] button:hover {{
  background: #FFC93F !important;
}}
[data-testid="stButton"] button[kind="primary"], [data-testid="stDownloadButton"] button[kind="primary"] {{
  background: {VERMELHO} !important; color: {AMARELO} !important;
}}
[class*="st-key-topo"] [data-testid="stButton"] button, [class*="st-key-topo"] [data-testid="stPopover"] button {{
  background: {CREME} !important;
}}
/* botões só de ícone (voltar, abrir território): círculo fixo, sem preenchimento lateral */
[class*="st-key-voltar"] button, [class*="st-key-abrir-"] button {{ width: 48px; height: 48px; min-width: 0;
  padding: 0 !important; display:grid; place-items:center; }}
[class*="st-key-voltar"] button {{ width: 54px; height: 54px; background: {VERMELHO} !important; }}
[class*="st-key-voltar"] button p {{ color: {AMARELO} !important; }}
[class*="st-key-voltar"] span[role="img"], [class*="st-key-abrir-"] span[role="img"] {{ font-size: 1.35rem !important; }}
[data-baseweb="select"] > div {{
  border-radius: 999px !important; background: {SUPERFICIE} !important; border: 2px solid {LINHA} !important;
}}
[class*="st-key-topo"] [data-baseweb="select"] > div {{ background: {CREME} !important; border: none !important; }}
[class*="st-key-card"] [data-baseweb="select"] > div {{ background: {AMARELO_2} !important; border: none !important; }}
[data-testid="stTextInputRootElement"] {{ border-radius: 999px !important; background: {SUPERFICIE} !important;
  border: 2px solid {LINHA} !important; padding-left: .6rem; }}
[data-testid="stTextInputRootElement"] input {{ background: transparent !important; }}
/* controles segmentados em pílula: trilho amarelo-claro, opção ativa vermelha */
[data-testid="stButtonGroup"] [role="radiogroup"] {{
  background:{AMARELO_2}; border-radius:999px; padding:4px; gap:2px; display:inline-flex; width:auto; flex-wrap:nowrap;
}}
[class*="st-key-topo"] [data-testid="stButtonGroup"] [role="radiogroup"] {{ background:{CREME}; }}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"] {{
  border:none !important; background:transparent !important; border-radius:999px !important;
  color:{TINTA_2} !important; padding:.32rem 1rem !important; min-height:0; box-shadow:none !important;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-checked="true"] {{
  background:{VERMELHO} !important; color:{AMARELO} !important;
}}
[data-testid="stButtonGroup"] button p {{ font-weight:600 !important; font-size:.74rem; text-transform:uppercase;
  letter-spacing:.03em; color:inherit !important; white-space:nowrap; }}
/* ícones Material são ligaduras: caixa alta ou espaçamento quebram o desenho */
[data-testid="stIconMaterial"], span[translate="no"] {{ text-transform:none !important; letter-spacing:0 !important; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; }}
div[data-testid="stAlert"] {{ border-radius: 20px; }}

@media (max-width: 700px) {{
  .block-container {{ padding: 1rem 1rem 2rem; }}
  .fw-valor {{ font-size: 2.1rem; }}
  .fw-valor-xl {{ font-size: 2.8rem; }}
  .fw-cal-mes {{ font-size: .5rem; letter-spacing: 0; white-space: nowrap; overflow: hidden; }}
  .fw-cal {{ gap: 3px; }}
}}
</style>
"""

LOGO_SVG = f"""<svg width="26" height="26" viewBox="0 0 24 24" fill="{VERMELHO}"><path d="M12 23c4.4 0 8-3
 8-7.6 0-3.9-2.4-6.6-4.3-8.8-.4 2.2-1.6 3.6-3 4.3.4-3-.7-6.3-3.4-7.9-.2 3.6-2.4 5.6-3.9 7.6C4.2 12.3 4
 13.6 4 15.4 4 20 7.6 23 12 23zm0-2c-1.9 0-3.2-1.3-3.2-3 0-1.6 1-2.6 2-3.8.3 1 .9 1.6 1.6 1.9 0-1.3.4-2.5
 1.3-3.4.8 1.4 1.5 2.9 1.5 4.6 0 2.1-1.4 3.7-3.2 3.7z"/></svg>"""


def aplicar_css() -> None:
    html(CSS)
