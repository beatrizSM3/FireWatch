"""Passo A11 do PLANO_DIVIDIDO: focos de uma área e período, para o app (download CSV).

Uso (Pessoa C):

    from firewatch.focos import focos_da_area, focos_csv
    df = focos_da_area(geometria, "2024-09-01", "2024-09-30")
    if df.attrs["truncado"]:
        st.warning(df.attrs["aviso"])
    st.download_button("Baixar CSV", focos_csv(df), "focos.csv", "text/csv")

`geometria` em latitude/longitude (EPSG:4326): shapely, dict GeoJSON (geometry ou Feature)
ou GeoDataFrame/GeoSeries (as geometrias são unidas). Ex.: uma linha de territorios.geojson.

Como funciona (pensado para gastar pouca memória):
1. Só abre os arquivos de observacoes/ dos MESES do período (um parquet por mês).
2. DuckDB filtra datas (os blocos do arquivo estão ordenados por data e são pulados) e o
   RETÂNGULO que envolve a área.
3. O resultado vem em LOTES; cada lote é filtrado pelo POLÍGONO com shapely.intersects_xy
   (vetorizado; focos exatamente na borda entram).
4. Para ao passar de focos_limite_linhas (config: 500 mil) e marca df.attrs["truncado"].

Colunas: as originais do FIRMS (latitude, longitude, brightness, scan, track, acq_date,
acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight, type)
mais satelite, sensor, produto, data_local e id_obs. Ordenadas por data/hora UTC.
Inclui todos os satélites (também N21); filtre com `satelites=[...]` se quiser.
"""
from __future__ import annotations

import warnings
from datetime import date

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from firewatch.config import SAIDA, cfg, conectar_duckdb

OBS = SAIDA / "observacoes"

_COLUNAS_SQL = """
    lat AS latitude, lon AS longitude, brightness, scan, track, acq_date, acq_time,
    satelite AS satellite, instrument, confianca AS confidence, version, bright_t31,
    frp, daynight, type,
    satelite, sensor, produto, data_local, id_obs, datetime_utc
"""

_con = None


def _conexao():
    global _con
    if _con is None:
        _con = conectar_duckdb()
    return _con


def _para_shapely(geometria):
    if hasattr(geometria, "geometry") and hasattr(geometria, "crs"):      # GeoDataFrame
        geometria = geometria.geometry
    if hasattr(geometria, "union_all"):                                   # GeoSeries
        if geometria.crs is not None and geometria.crs.to_epsg() != 4326:
            geometria = geometria.to_crs(4326)
        return geometria.union_all()
    if isinstance(geometria, dict):
        return shape(geometria.get("geometry", geometria))
    return geometria


def _arquivos(ini: date, fim: date) -> list[str]:
    arquivos = []
    for ano in range(ini.year, fim.year + 1):
        m0 = ini.month if ano == ini.year else 1
        m1 = fim.month if ano == fim.year else 12
        for mes in range(m0, m1 + 1):
            p = OBS / f"ano={ano}" / f"parte-{mes:02d}.parquet"
            if p.exists():
                arquivos.append(str(p))
    return arquivos


def focos_da_area(geometria, data_inicio, data_fim, satelites=None,
                  limite: int | None = None) -> pd.DataFrame:
    """Focos dentro de `geometria` (EPSG:4326) com data_local entre data_inicio e data_fim."""
    limite = int(limite or cfg()["focos_limite_linhas"])
    ini, fim = pd.Timestamp(data_inicio).date(), pd.Timestamp(data_fim).date()
    geom = _para_shapely(geometria)
    if geom is None or geom.is_empty:
        raise ValueError("geometria vazia")
    shapely.prepare(geom)
    xmin, ymin, xmax, ymax = geom.bounds

    arquivos = _arquivos(ini, fim)
    vazio = pd.DataFrame(columns=[c.strip().split(" AS ")[-1]
                                  for c in _COLUNAS_SQL.replace("\n", " ").split(",")])
    if not arquivos:
        vazio.attrs.update(truncado=False, aviso="")
        return vazio.drop(columns="datetime_utc")

    filtro_sat = ""
    params = [ini, fim, ymin, ymax, xmin, xmax]
    if satelites:
        filtro_sat = f"AND satelite IN ({','.join('?' * len(satelites))})"
        params += list(satelites)

    lista = "[" + ",".join(f"'{a}'" for a in arquivos) + "]"
    # con.sql (e não con.execute): só assim to_arrow_reader faz streaming de verdade;
    # com execute o DuckDB copia o resultado inteiro antes de entregar os lotes.
    rel = _conexao().sql(f"""
        SELECT {_COLUNAS_SQL}
        FROM read_parquet({lista})
        WHERE data_local BETWEEN ? AND ?
          AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
          {filtro_sat}
    """, params=params)

    partes, n, truncado = [], 0, False
    for lote in rel.to_arrow_reader(100_000):     # leitura em lotes (streaming)
        lon = lote.column("longitude").to_numpy(zero_copy_only=False)
        lat = lote.column("latitude").to_numpy(zero_copy_only=False)
        m = shapely.intersects_xy(geom, lon, lat)
        if not m.any():
            continue
        df = lote.to_pandas()[m]
        partes.append(df)
        n += len(df)
        if n > limite:
            truncado = True
            break

    df = pd.concat(partes, ignore_index=True) if partes else vazio
    df = df.sort_values(["datetime_utc", "satelite"], kind="stable")
    if truncado:
        df = df.head(limite)
    df = df.drop(columns="datetime_utc").reset_index(drop=True)
    # os lotes chegam em ordem arbitrária: ao truncar, a amostra NÃO são "os primeiros"
    aviso = (f"A área e o período têm mais de {limite:,} focos; o arquivo foi cortado em "
             f"{limite:,} linhas e está incompleto. Diminua a área ou o período."
             .replace(",", "."))
    df.attrs.update(truncado=truncado, aviso=aviso if truncado else "")
    if truncado:
        warnings.warn(aviso, stacklevel=2)
    return df


def focos_csv(df: pd.DataFrame) -> bytes:
    """CSV (UTF-8) pronto para st.download_button."""
    return df.to_csv(index=False).encode("utf-8")
