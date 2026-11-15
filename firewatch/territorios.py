"""Parte B (passo B7): indicadores que dependem de um território (UC ou TI).

    from firewatch import territorios as terr

    terr.resumo("UC-0000.17.1487")              # ficha + 2026 + termômetro + MIF + dentro × entorno
    terr.dentro_entorno("UC-0000.17.1487", 2024)

Densidade = CDeV por 1.000 km², para comparar territórios de tamanhos diferentes.
  * dentro: denominador = area_km2 do polígono (territorios.geojson).
  * entorno: denominador = número de células do anel de 10 km (1 km² cada), que é a
    única medida da área do anel que existe nos arquivos.
"Dentro × entorno" é uma COMPARAÇÃO, não uma prova de causa: vegetação e uso da terra
mudam na divisa.
"""
from __future__ import annotations

import pandas as pd

from firewatch import carregar
from firewatch import indicadores as ind
from firewatch.config import cfg


def _acumulado_ate(serie: pd.DataFrame, ano: int, data_fim) -> tuple[float, int]:
    """Σ cdev do ano até o mesmo dia-do-ano de `data_fim`; e nº de dias NA no intervalo."""
    s = ind.serie_diaria(serie)
    d = pd.to_datetime(s["data_local"])
    doy = pd.Timestamp(data_fim).day_of_year
    s = s[(d.dt.year.to_numpy() == ano) & (d.dt.day_of_year.to_numpy() <= doy)]
    return float(s["cdev"].sum()), int(s["na"].sum())


def dentro_entorno(id_territorio: str, ano: int, data_fim=None) -> dict:
    """Densidade de fogo dentro do território ÷ densidade no anel de 10 km, no ano
    (até `data_fim`; padrão: 31/12, ou data_fim_dados no ano em curso).

    Devolve: ano, data_fim, cdev_dentro, cdev_entorno, area_dentro_km2, area_entorno_km2,
    densidade_dentro, densidade_entorno, razao (None se o entorno tiver 0), texto.
    razao > 1: mais fogo dentro do que em volta; < 1: o entorno queima mais.
    """
    c = cfg()
    fim_dados = pd.Timestamp(c["data_fim_dados"])
    if data_fim is None:
        data_fim = fim_dados if ano == fim_dados.year else pd.Timestamp(ano, 12, 31)
    info = carregar.territorio(id_territorio)
    area_dentro = float(info["area_km2"])
    area_entorno = carregar.area_entorno_km2(id_territorio)

    cdev_d, _ = _acumulado_ate(carregar.serie_do_territorio(id_territorio, "dentro"), ano, data_fim)
    cdev_e, _ = _acumulado_ate(carregar.serie_do_territorio(id_territorio, "entorno"), ano, data_fim)
    dens_d = ind.densidade(cdev_d, area_dentro)
    dens_e = ind.densidade(cdev_e, area_entorno)
    razao = (dens_d / dens_e) if (dens_d is not None and dens_e) else None
    if razao is None:
        texto = "sem fogo detectado no entorno: razão indefinida"
    elif razao > 1:
        texto = f"em {ano}, a densidade de fogo dentro foi {razao:.1f}× a do entorno"
    else:
        texto = f"em {ano}, o entorno teve {1 / razao:.1f}× a densidade de fogo do interior" \
            if razao > 0 else f"em {ano}, não houve fogo detectado dentro do território"
    return dict(id_territorio=id_territorio, ano=ano, data_fim=pd.Timestamp(data_fim).date(),
                cdev_dentro=cdev_d, cdev_entorno=cdev_e, area_dentro_km2=area_dentro,
                area_entorno_km2=area_entorno, densidade_dentro=dens_d, densidade_entorno=dens_e,
                razao=razao, texto=texto + " (comparação, não causa)")


def resumo(id_territorio: str, ano: int | None = None, mes: int | None = None) -> dict:
    """Tudo de um território numa chamada: ficha, cartão do ano em curso, termômetro do mês,
    ranking, janela crítica, fração tardia e dentro × entorno. Pensado para o boletim."""
    c = cfg()
    ano = int(ano or c["ano_em_curso"])
    fim = pd.Timestamp(c["data_fim_dados"])
    mes = int(mes or (fim.month if ano == fim.year else 9))
    ficha = carregar.territorio(id_territorio)
    serie = carregar.serie_do_territorio(id_territorio, "dentro")
    out = dict(ficha=ficha, area_entorno_km2=carregar.area_entorno_km2(id_territorio),
               avisos=[])
    if ficha.get("limite_aproximado"):
        out["avisos"].append("limite aproximado: o polígono desta UC é uma estimativa")
    if ficha["area_km2"] < float(c["territorio_area_min_km2"]):
        out["avisos"].append(f"território pequeno (< {c['territorio_area_min_km2']} km²): "
                             "estatísticas instáveis")
    if serie.empty:
        out["avisos"].append("nenhuma célula de 1 km cai dentro deste território; "
                             "use focos_da_area com o polígono")
        return out
    out["ano_em_curso"] = ind.ano_em_curso(serie, ano=ano)
    try:
        out["termometro"] = ind.termometro(serie, ano, mes)
    except ValueError:
        out["termometro"] = None
    out["ranking_anos"] = ind.ranking_anos(serie)
    out["janela_critica"] = ind.janela_critica(serie)
    out["fracao_tardia"] = ind.fracao_tardia(serie, ano)
    out["dentro_entorno"] = dentro_entorno(id_territorio, ano)
    out["densidade_ano"] = ind.densidade(out["ano_em_curso"]["valor"], ficha["area_km2"])
    return out
