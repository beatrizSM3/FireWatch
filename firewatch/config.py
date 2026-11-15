"""Carrega o config.yaml e os caminhos padrão do projeto."""
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
SAIDA = RAIZ / "saida"
TMP = SAIDA / "_tmp"


@lru_cache
def cfg() -> dict:
    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def conectar_duckdb():
    """Conexão DuckDB com limite de memória e spill para disco."""
    import duckdb

    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{cfg()['duckdb_memoria']}'")
    con.execute(f"SET temp_directory='{TMP / 'duckdb_spill'}'")
    con.execute("SET preserve_insertion_order=false")
    return con
