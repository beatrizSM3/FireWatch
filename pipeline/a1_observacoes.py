"""A1 — Passos A2, A3, A4, A5 e A7 do PLANO_DIVIDIDO.

Entrada:  data/raw/nasa/*/*/*.csv (31 arquivos, archive + NRT)
Saídas:   saida/_tmp/bruto.parquet          (todas as linhas, sem filtro; usado pelo A6 / a2_disponibilidade)
          saida/fontes_fixas.parquet        (gx, gy, type_max)
          saida/observacoes/ano=AAAA/parte-MM.parquet  (um arquivo por mês)

Decisões:
- Focos com data_local fora de [data_inicio_dados, data_fim_dados] são descartados
  (ex.: 01/01/2019 00–03h UTC vira 31/12/2018 no horário local).
- Duplicatas por (satellite, latitude, longitude, acq_date, acq_time) removidas (auditoria A11).
- Focos NRT em células de fonte fixa são removidos já em observacoes/.
- observacoes/ inclui gx, gy e as colunas originais do FIRMS, além das do contrato.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import RAW, SAIDA, TMP, cfg, conectar_duckdb  # noqa: E402

BRUTO = TMP / "bruto.parquet"
OBS = SAIDA / "observacoes"
FONTES = SAIDA / "fontes_fixas.parquet"

_TRANSF = None


def projetar(tabela: pa.Table) -> pa.Table:
    """Acrescenta x, y (EPSG:5880, metros) e gx, gy (índice da célula)."""
    global _TRANSF
    if _TRANSF is None:
        _TRANSF = Transformer.from_crs(4326, cfg()["crs_metros"], always_xy=True)
    lon = tabela.column("lon").to_numpy()
    lat = tabela.column("lat").to_numpy()
    x, y = _TRANSF.transform(lon, lat)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("projeção gerou inf/NaN — conferir ordem (lon, lat)")
    celula = cfg()["celula_m"]
    gx = np.floor(x / celula).astype(np.int32)
    gy = np.floor(y / celula).astype(np.int32)
    return (tabela.append_column("x", pa.array(x)).append_column("y", pa.array(y))
            .append_column("gx", pa.array(gx)).append_column("gy", pa.array(gy)))


def etapa_bruto(con):
    """A2 — lê os 31 CSVs como texto e deriva satelite/sensor/produto/datas."""
    csvs = sorted(str(p) for p in (RAW / "nasa").glob("*/*/*.csv"))
    print(f"[A2] {len(csvs)} CSVs")
    fuso = int(cfg()["fuso_horas"])
    lista = "[" + ",".join(f"'{c}'" for c in csvs) + "]"
    con.execute(f"""
        COPY (
          SELECT
            CAST(latitude AS DOUBLE)  AS lat,
            CAST(longitude AS DOUBLE) AS lon,
            latitude AS lat_txt, longitude AS lon_txt,
            CAST(brightness AS DOUBLE) AS brightness,
            CAST(bright_t31 AS DOUBLE) AS bright_t31,
            CAST(scan AS DOUBLE)  AS scan,
            CAST(track AS DOUBLE) AS track,
            CAST(frp AS DOUBLE)   AS frp,
            acq_date, acq_time,
            satellite AS satelite,
            CASE WHEN satellite IN ('Terra','Aqua') THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
            CASE WHEN regexp_extract(filename, '[^/]+$') LIKE 'fire_nrt_%' THEN 'nrt'
                 ELSE 'archive' END AS produto,
            instrument, confidence AS confianca, version, daynight,
            CAST(type AS INTEGER) AS type,
            strptime(acq_date || ' ' || acq_time, '%Y-%m-%d %H%M') AS datetime_utc,
            CAST(strptime(acq_date || ' ' || acq_time, '%Y-%m-%d %H%M')
                 + INTERVAL ({fuso}) HOUR AS DATE) AS data_local
          FROM read_csv({lista}, all_varchar=true, union_by_name=true, filename=true, header=true)
        ) TO '{BRUTO}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n, nulos = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE lat IS NULL OR lon IS NULL) FROM '{BRUTO}'"
    ).fetchone()
    print(f"[A2] {n:,} linhas; {nulos} sem coordenada")
    print(con.execute(f"""
        SELECT satelite, sensor, produto, count(*) n FROM '{BRUTO}'
        GROUP BY ALL ORDER BY ALL""").df().to_string(index=False))


def etapa_fontes_fixas(con):
    """A7 — células com type 2/3 no archive, antes de qualquer filtro."""
    t = con.execute(f"""
        SELECT lat, lon, type FROM '{BRUTO}'
        WHERE produto = 'archive' AND type IN (2, 3)
    """).to_arrow_table()
    t = projetar(t)
    con.register("ff_proj", t)
    con.execute(f"""
        COPY (SELECT gx, gy, max(type) AS type_max FROM ff_proj GROUP BY gx, gy ORDER BY gx, gy)
        TO '{FONTES}' (FORMAT parquet)
    """)
    con.unregister("ff_proj")
    n = con.execute(f"SELECT count(*) FROM '{FONTES}'").fetchone()[0]
    print(f"[A7] {t.num_rows:,} focos type 2/3 -> {n:,} células de fonte fixa")


def etapa_observacoes(con, anos=None):
    """A3 + A4 + A5 — filtra, deduplica, projeta e grava particionado por ano.

    Processa MÊS A MÊS (um arquivo parte-MM.parquet por mês dentro de ano=AAAA/)
    para manter a memória baixa: o ano inteiro em Arrow estourava a RAM (OOM).
    `anos`: lista de anos a (re)gerar; vazio = todos. Só a pasta de cada ano
    processado é apagada.
    """
    import gc
    import shutil

    c = cfg()
    viirs = ",".join(f"'{v}'" for v in c["filtros"]["viirs_confianca"])
    modis_min = int(c["filtros"]["modis_confianca_min"])
    ini, fim = c["data_inicio_dados"], c["data_fim_dados"]
    ano_ini, ano_fim = int(ini[:4]), int(fim[:4])
    anos = anos or list(range(ano_ini, ano_fim + 1))

    con.execute(f"CREATE OR REPLACE TEMP TABLE ff AS SELECT gx, gy FROM '{FONTES}'")

    total_ok = 0
    for ano in anos:
        t_ano = time.time()
        destino = OBS / f"ano={ano}"
        if destino.exists():
            shutil.rmtree(destino)
        destino.mkdir(parents=True, exist_ok=True)
        # contador por satélite, para o id_obs seguir sequencial ao longo do ano
        offsets: dict[str, int] = {}
        n_ano = 0
        for mes in range(1, 13):
            t = con.execute(f"""
                SELECT * EXCLUDE (lat_txt, lon_txt) FROM '{BRUTO}'
                WHERE year(data_local) = {ano} AND month(data_local) = {mes}
                  AND data_local BETWEEN DATE '{ini}' AND DATE '{fim}'
                  AND (produto = 'nrt' OR type = 0)
                  AND ((sensor = 'VIIRS' AND confianca IN ({viirs}))
                       OR (sensor = 'MODIS' AND TRY_CAST(confianca AS INTEGER) >= {modis_min}))
                  AND frp > 0 AND brightness > 0
                QUALIFY row_number() OVER (
                  PARTITION BY satelite, lat_txt, lon_txt, acq_date, acq_time
                  ORDER BY frp DESC) = 1
            """).to_arrow_table()
            if t.num_rows == 0:
                continue
            t = projetar(t)
            con.register("obs_proj", t)
            con.execute("CREATE OR REPLACE TEMP TABLE offs (satelite VARCHAR, base BIGINT)")
            if offsets:
                con.executemany("INSERT INTO offs VALUES (?, ?)", list(offsets.items()))
            arquivo = destino / f"parte-{mes:02d}.parquet"
            con.execute(f"""
                COPY (
                  WITH f AS (
                    SELECT p.* FROM obs_proj p
                    WHERE NOT (p.produto = 'nrt'
                               AND EXISTS (SELECT 1 FROM ff WHERE ff.gx = p.gx AND ff.gy = p.gy))
                  )
                  SELECT
                    f.satelite || '-' || {ano} || '-' || lpad(CAST(coalesce(o.base, 0) +
                        row_number() OVER (PARTITION BY f.satelite
                                           ORDER BY f.datetime_utc, f.lat, f.lon)
                        AS VARCHAR), 8, '0') AS id_obs,
                    f.satelite, sensor, produto, lat, lon, x, y, gx, gy,
                    datetime_utc, data_local, frp, confianca, daynight, scan, track,
                    brightness, bright_t31, acq_date, acq_time, instrument, version, type
                  FROM f LEFT JOIN offs o USING (satelite)
                  ORDER BY data_local, gx, gy
                ) TO '{arquivo}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000)
            """)
            con.unregister("obs_proj")
            for sat, n_sat in con.execute(
                    f"SELECT satelite, count(*) FROM '{arquivo}' GROUP BY 1").fetchall():
                offsets[sat] = offsets.get(sat, 0) + n_sat
            n_ano += con.execute(f"SELECT count(*) FROM '{arquivo}'").fetchone()[0]
            del t
            gc.collect()
        total_ok += n_ano
        print(f"[A5] {ano}: {n_ano:,} gravados ({time.time()-t_ano:.0f}s)", flush=True)

    if len(anos) == ano_fim - ano_ini + 1:
        n_bruto = con.execute(f"SELECT count(*) FROM '{BRUTO}'").fetchone()[0]
        print(f"[A3] mantidas {total_ok:,} de {n_bruto:,} ({100*total_ok/n_bruto:.1f}%)")


def main():
    args = sys.argv[1:]
    anos = [int(a) for a in args if a.isdigit()]
    etapas = [a for a in args if not a.isdigit()] or ["bruto", "fontes", "obs"]
    con = conectar_duckdb()
    t0 = time.time()
    if "bruto" in etapas:
        etapa_bruto(con)
    if "fontes" in etapas:
        etapa_fontes_fixas(con)
    if "obs" in etapas:
        etapa_observacoes(con, anos)
    print(f"concluído em {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
