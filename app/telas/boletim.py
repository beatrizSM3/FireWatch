"""Boletim: uma página HTML de uma área, para imprimir ou salvar em PDF pelo navegador."""
from __future__ import annotations

import html as _html
from datetime import date

import streamlit as st

import componentes as C
import dados as D
import estilo as E
from firewatch import indicadores as ind

LIMITACOES = [
    "Mostra atividade de fogo <b>detectada por satélite</b>: não mede área queimada e não prevê incêndios.",
    "Fogo sob nuvem ou fumaça densa pode não ser detectado.",
    "Histórico curto: 7 anos (2019–2025). Comparações por posição e mediana, não por percentil.",
    "Dados de 2026 a partir de julho (VIIRS) e setembro (MODIS) são preliminares (NRT) e podem mudar.",
    "Precoce e tardio (Modo MIF) indicam a época do fogo, não a intenção.",
    "Dentro × entorno é comparação, não causa.",
]


def gerar(a: D.Area, ano: int, mes: int) -> str:
    return _gerar(a.chave, a.tipo, a.geojson, a.nome, a.area_km2, ano, mes)


@st.cache_data(show_spinner=False, max_entries=32)
def _gerar(chave, tipo, geojson, nome, area_km2, ano, mes) -> str:
    pac = D.pacote(chave, tipo, geojson, ano, mes)
    if pac["vazio"]:
        return f"<html><body><h1>{_html.escape(nome)}</h1><p>Sem células de 1 km nesta área.</p></body></html>"
    s = D.serie(chave, tipo, geojson)
    ac, tm, jn = pac["ano_em_curso"], pac["termometro"], pac["janela"]
    fr = ind.fracao_tardia(s, D.ANO_ATUAL)
    ch = ind.contagem_honesta(s)

    ficha = ""
    if tipo == "territorio":
        f = D.ficha(chave)
        itens = [("Tipo", f["tipo"]), ("Categoria", f.get("categoria")), ("Grupo", f.get("grupo")),
                 ("Esfera", f.get("esfera")), ("Gestor", f.get("gestor")), ("Etnia", f.get("etnia")),
                 ("Fase", f.get("fase")), ("Plano de manejo", f.get("pl_manejo")), ("UF", f.get("uf")),
                 ("Área", f"{E.num(f['area_km2'])} km²")]
        ficha = "".join(f"<div><span>{k}</span><b>{_html.escape(str(v))}</b></div>"
                        for k, v in itens if v and str(v) != "nan")
        if f.get("limite_aproximado"):
            ficha += "<div><span>Aviso</span><b>limite aproximado</b></div>"

    def bloco(rot, val, sub):
        return f'<div class="b-card"><div class="fw-rotulo">{rot}</div><div class="fw-valor">{val}</div><div class="fw-sub">{sub}</div></div>'

    cards = bloco(f"{ac['ano']} até {D.FIM:%d/%m}", E.num(ac["valor"]),
                  f"{E.badge(ac['classificacao'])} {ac['posicao_texto'] or ''} · mediana {E.num(ac['mediana'])}")
    if tm:
        cards += bloco(E.mes_ano(ano, mes), E.num(tm["valor"]),
                       f"{E.badge(tm['classificacao'])} {tm['posicao_texto'] or ''} · mediana {E.num(tm['mediana'])}")
    if jn["semana_inicio"]:
        cards += bloco("Estação de fogo", f"{E.MESES[jn['mes_inicio'] - 1]} → {E.MESES[jn['mes_fim'] - 1]}",
                       f"pico em {E.MESES_LONGOS[jn['mes_pico'] - 1]}")

    frases = []
    if fr["fracao"] is not None:
        frases.append(f"<b>Modo MIF:</b> em {D.ANO_ATUAL} (até agora), {E.pct(fr['fracao'])} do fogo da área "
                      f"veio depois de {fr['data_corte'][3:]}/{fr['data_corte'][:2]} "
                      f"(histórico 2019–2025: {E.pct(fr['minimo'])}–{E.pct(fr['maximo'])}, mediana {E.pct(fr['mediana'])}).")
    if tipo == "territorio":
        de = D.dentro_entorno_anos(chave)
        r = de[de.ano == D.ANO_ATUAL].iloc[0]
        if r["razao"] is not None and r["razao"] == r["razao"]:
            frases.append(f"<b>Dentro × entorno:</b> {_html.escape(r['texto'])}.")
    if ch.get("razao"):
        frases.append(f"<b>Contagem honesta:</b> somar os satélites contaria {E.num(ch['razao'], 2)}× "
                      "a atividade; aqui cada célula de 1 km conta uma vez por dia.")

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FireWatch · {_html.escape(nome)}</title>{E.CSS}
<style>
body{{background:#fff;max-width:960px;margin:2rem auto;padding:0 1.2rem;color:{E.TINTA}}}
.b-top{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid {E.LINHA};padding-bottom:1rem}}
.b-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin:1.2rem 0}}
.b-card{{border:1px solid {E.LINHA};border-radius:16px;padding:1rem 1.2rem}}
.b-ficha{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.4rem 1.2rem;font-size:.85rem;margin-top:1rem}}
.b-ficha span{{display:block;color:{E.MUTED};font-size:.72rem}}
h2{{font-size:1.1rem;margin:1.6rem 0 .7rem}} p,li{{font-size:.9rem;line-height:1.5}}
.b-print{{position:fixed;right:1rem;top:1rem}} @media print{{.b-print{{display:none}} body{{margin:0}}}}
</style></head><body>
<button class="b-print" onclick="window.print()" style="border-radius:99px;border:1px solid {E.LINHA};padding:.5rem 1rem;background:#fff;font-weight:700;cursor:pointer">Imprimir / PDF</button>
<div class="b-top"><div><div class="fw-logo"><div class="fw-logo-icone">{E.LOGO_SVG}</div>FireWatch · boletim</div>
<div class="fw-titulo">{_html.escape(nome)}</div></div>
<div class="fw-sub">Dados até {D.FIM:%d/%m/%Y} · gerado em {date.today():%d/%m/%Y}</div></div>
<div class="b-ficha">{ficha}</div>
<div class="b-cards">{cards}</div>
<h2>Calendário de fogo (células-dia com fogo por mês)</h2>
{C.calendario_mensal(pac["mensal"], (ano, mes))}
<h2>Destaques</h2>{"".join(f"<p>{x}</p>" for x in frases)}
<h2>Limitações</h2><ul>{"".join(f"<li>{x}</li>" for x in LIMITACOES)}</ul>
<p class="fw-sub">Fontes: NASA FIRMS (MODIS C6.1, VIIRS S-NPP/NOAA-20 C2), CNUC/MMA, FUNAI.
Unidade: células-dia equivalentes a VIIRS (quadrados de 1 km com fogo detectado num dia).</p>
</body></html>"""
