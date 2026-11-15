"""A5 — Passo A10 do PLANO_DIVIDIDO: células de 1 km de cada território.

Entrada:  saida/_tmp/territorios_5880.parquet   (gerado pelo A4; EPSG:5880, SEM simplificar)
Saída:    saida/celula_territorio.parquet

Colunas: gx, gy, id_territorio, zona   (zona = 'dentro' | 'entorno')

RODE SEMPRE COM ./rodar.sh (teto de memória). Uso:
    ./rodar.sh pipeline/a5_celula_territorio.py            # todos
    ./rodar.sh pipeline/a5_celula_territorio.py --teste 5  # só os 5 primeiros (saída em _tmp)

Decisões:
- GRADE COMPLETA: entram todas as células cujo CENTRO (gx*1000+500, gy*1000+500) cai
  dentro do polígono ('dentro') ou a até 10 km dele sem estar dentro ('entorno'), e não só
  as células que aparecem em celulas_base. Motivos:
    1) o "Pronto quando" (nº de células dentro ≈ area_km2) só fecha com a grade completa;
    2) a Pessoa B precisa da ÁREA do entorno para a densidade dentro × entorno, e ela não
       existe em nenhum outro arquivo: aqui ela é a contagem de células 'entorno' (1 km² cada).
  Para o JOIN com celulas_dia nada muda: células sem fogo simplesmente não casam.

- MEMÓRIA (a máquina tem 7,5 GB; buffer() dos polígonos completos travou o computador):
    * NÃO se constrói o anel com buffer(). "Entorno" = centro a <= 10 km do polígono
      (shapely.dwithin) e fora dele. Mesmo resultado de buffer(10 km) − polígono, sem
      criar geometria nova.
    * O teste de distância usa o polígono simplificado em 50 m (erro irrelevante para
      um critério de 10 km em células de 1 km). O teste "dentro" usa o polígono original.
    * A grade é varrida em blocos de 256 × 256 células; blocos longe do território são
      pulados. A memória não depende do tamanho do território.
    * Um território por vez; o resultado vai sendo gravado em disco (ParquetWriter).

- Uma célula pode estar em vários territórios (UCs se sobrepõem) e pode ser 'dentro' de
  um e 'entorno' de outro. Isso é esperado.
- Território pequeno (< ~1 km²) pode não conter nenhum centro de célula: fica sem
  linhas 'dentro' e o script lista quantos são.
"""
import argparse
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import SAIDA, TMP, cfg  # noqa: E402

ENTRADA = TMP / "territorios_5880.parquet"
DESTINO = SAIDA / "celula_territorio.parquet"
BLOCO = 256                 # células por lado de cada bloco da grade
SIMPLIFICAR_DIST_M = 50     # só para o teste de distância do entorno


def celulas_do_territorio(geom, celula: float, dist: float):
    """Retorna (gx, gy, eh_dentro) das células dentro ou a até `dist` metros de geom."""
    geom_dist = shapely.simplify(geom, SIMPLIFICAR_DIST_M, preserve_topology=True)
    shapely.prepare(geom)
    shapely.prepare(geom_dist)

    xmin, ymin, xmax, ymax = geom.bounds
    gx0, gx1 = int(np.floor((xmin - dist) / celula)), int(np.floor((xmax + dist) / celula))
    gy0, gy1 = int(np.floor((ymin - dist) / celula)), int(np.floor((ymax + dist) / celula))

    saida_gx, saida_gy, saida_dentro = [], [], []
    for bx in range(gx0, gx1 + 1, BLOCO):
        for by in range(gy0, gy1 + 1, BLOCO):
            ex, ey = min(bx + BLOCO - 1, gx1), min(by + BLOCO - 1, gy1)
            caixa = shapely.box(bx * celula, by * celula, (ex + 1) * celula, (ey + 1) * celula)
            if not shapely.dwithin(geom_dist, caixa, dist):
                continue            # bloco inteiro a mais de 10 km: pula
            gx = np.arange(bx, ex + 1, dtype=np.int32)
            gy = np.arange(by, ey + 1, dtype=np.int32)
            GX, GY = np.meshgrid(gx, gy)
            GX, GY = GX.ravel(), GY.ravel()
            cx = GX * celula + celula / 2
            cy = GY * celula + celula / 2
            dentro = shapely.contains_xy(geom, cx, cy)
            perto = np.zeros_like(dentro)
            fora = ~dentro
            if fora.any():
                pts = shapely.points(cx[fora], cy[fora])
                perto[fora] = shapely.dwithin(geom_dist, pts, dist)
                del pts
            m = dentro | perto
            if m.any():
                saida_gx.append(GX[m])
                saida_gy.append(GY[m])
                saida_dentro.append(dentro[m])
    if not saida_gx:
        return np.empty(0, np.int32), np.empty(0, np.int32), np.empty(0, bool)
    return np.concatenate(saida_gx), np.concatenate(saida_gy), np.concatenate(saida_dentro)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", type=int, default=0, help="processa só os N primeiros")
    args = ap.parse_args()

    c = cfg()
    celula = float(c["celula_m"])
    dist = float(c["territorio_entorno_m"])
    destino = TMP / "celula_territorio_teste.parquet" if args.teste else DESTINO
    t0 = time.time()

    terr = gpd.read_parquet(ENTRADA, columns=["id_territorio", "area_km2", "geometry"])
    if args.teste:
        terr = terr.head(args.teste)
    print(f"[A10] {len(terr)} territórios -> {destino.name}", flush=True)

    schema = pa.schema([("gx", pa.int32()), ("gy", pa.int32()),
                        ("id_territorio", pa.string()), ("zona", pa.string())])
    total = {"dentro": 0, "entorno": 0}
    sem_dentro = []
    with pq.ParquetWriter(destino, schema, compression="zstd") as escritor:
        for i, (tid, geom) in enumerate(zip(terr["id_territorio"], terr.geometry), 1):
            gx, gy, dentro = celulas_do_territorio(geom, celula, dist)
            n_dentro = int(dentro.sum())
            if n_dentro == 0:
                sem_dentro.append(tid)
            if len(gx):
                escritor.write_table(pa.table({
                    "gx": gx, "gy": gy,
                    "id_territorio": pa.array(np.full(len(gx), tid, dtype=object), pa.string()),
                    "zona": pa.array(np.where(dentro, "dentro", "entorno"), pa.string()),
                }, schema=schema))
            total["dentro"] += n_dentro
            total["entorno"] += len(gx) - n_dentro
            if args.teste or i % 50 == 0:
                print(f"[A10] {i}/{len(terr)} {tid}: {n_dentro:,} dentro, "
                      f"{len(gx) - n_dentro:,} entorno ({time.time()-t0:.0f}s)", flush=True)
            del gx, gy, dentro

    print(f"[A10] {total['dentro']:,} 'dentro' + {total['entorno']:,} 'entorno' "
          f"-> {destino} ({time.time()-t0:.0f}s)")
    print(f"[A10] territórios sem nenhuma célula 'dentro' (área < ~1 km²): {len(sem_dentro)}")


if __name__ == "__main__":
    main()
