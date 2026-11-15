"""B5 — Passo B8 do PLANO_DIVIDIDO: Modo MIF por grupo de território (para a Pessoa D).

Entradas: saida/celulas_dia.parquet, saida/celula_territorio.parquet, saida/territorios.geojson
Saída:    saida/mif_grupos.csv

Compara a fração tardia (fogo depois da data de corte) entre grupos:
  Proteção Integral x Uso Sustentável x Terra Indígena
  UC com plano de manejo x UC sem plano de manejo
e para três datas de corte (sensibilidade): 06-30, 07-15 (config), 07-31.

Regra: NÃO soma territórios. O grupo é a UNIÃO das células 'dentro' dos seus territórios
(uma célula em duas UCs sobrepostas conta uma vez).
Colunas: grupo, data_corte, ano, precoce, tardio, total, fracao, cobertura_reduzida,
         n_territorios, n_celulas.
Lembrete: fração tardia classifica a ÉPOCA do fogo, não a intenção. Se os grupos não
diferirem, isso também é resultado.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch import carregar  # noqa: E402
from firewatch import indicadores as ind  # noqa: E402
from firewatch.config import SAIDA, cfg, conectar_duckdb  # noqa: E402

CELULAS_DIA = SAIDA / "celulas_dia.parquet"
CELULA_TERRITORIO = SAIDA / "celula_territorio.parquet"
DESTINO = SAIDA / "mif_grupos.csv"
CORTES = ["06-30", "07-15", "07-31"]


def grupos_de_territorios(terr: pd.DataFrame) -> dict[str, pd.Series]:
    uc = terr[terr.tipo == "UC"]
    return {
        "Proteção Integral": uc.loc[uc.grupo == "Proteção Integral", "id_territorio"],
        "Uso Sustentável": uc.loc[uc.grupo == "Uso Sustentável", "id_territorio"],
        "Terra Indígena": terr.loc[terr.tipo == "TI", "id_territorio"],
        "UC com plano de manejo": uc.loc[uc.pl_manejo == "Sim", "id_territorio"],
        "UC sem plano de manejo": uc.loc[uc.pl_manejo != "Sim", "id_territorio"],
    }


def main():
    c = cfg()
    h0, h1 = c["periodo_historico"]
    con = conectar_duckdb()
    terr = carregar.territorios().drop(columns="geometry")
    disp = carregar.disponibilidade()
    cortes = sorted(set(CORTES) | {str(c["mif_data_corte"])})
    linhas = []
    for nome, ids in grupos_de_territorios(terr).items():
        con.register("_ids", pd.DataFrame({"id_territorio": ids}))
        n_cel = con.execute(f"""SELECT count(*) FROM (SELECT DISTINCT gx, gy FROM '{CELULA_TERRITORIO}'
            WHERE zona = 'dentro' AND id_territorio IN (SELECT id_territorio FROM _ids))""").fetchone()[0]
        serie = con.execute(carregar._SQL_SERIE.format(
            arquivo=CELULAS_DIA,
            where=f"""WHERE (gx, gy) IN (SELECT DISTINCT (gx, gy) FROM '{CELULA_TERRITORIO}'
                      WHERE zona = 'dentro' AND id_territorio IN (SELECT id_territorio FROM _ids))""")).df()
        con.unregister("_ids")
        for corte in cortes:
            for ano in range(int(h0), int(h1) + 1):
                r = ind.fracao_tardia(serie, ano, data_corte=corte, disponibilidade=disp)
                linhas.append(dict(grupo=nome, data_corte=corte, ano=ano, precoce=r["precoce"],
                                   tardio=r["tardio"], total=r["total"], fracao=r["fracao"],
                                   cobertura_reduzida=r["cobertura_reduzida"],
                                   n_territorios=len(ids), n_celulas=n_cel))
        print(f"[B8] {nome}: {len(ids)} territórios, {n_cel:,} células")
    out = pd.DataFrame(linhas)
    out.to_csv(DESTINO, index=False)
    print(f"[B8] {len(out)} linhas -> {DESTINO}\n")
    print("Mediana da fração tardia por grupo e data de corte (anos", h0, "a", h1, "):")
    print((out.groupby(["grupo", "data_corte"]).fracao.median().unstack("data_corte") * 100)
          .round(1).to_string())


if __name__ == "__main__":
    main()
