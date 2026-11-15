"""A0 — Extrai data/raw/zip/nasa/<SAT>/<nome>.zip para data/raw/nasa/<SAT>/<nome>/."""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firewatch.config import RAW  # noqa: E402


def main():
    zips = sorted((RAW / "zip" / "nasa").glob("*/*.zip"))
    for z in zips:
        destino = RAW / "nasa" / z.parent.name / z.stem
        if destino.exists() and any(destino.glob("*.csv")):
            print(f"já extraído: {destino.relative_to(RAW)}")
            continue
        destino.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(destino)
        print(f"extraído: {destino.relative_to(RAW)}")
    csvs = sorted((RAW / "nasa").glob("*/*/*.csv"))
    print(f"{len(zips)} zips, {len(csvs)} CSVs")


if __name__ == "__main__":
    main()
