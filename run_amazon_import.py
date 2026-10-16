from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect
from smart_commerce.amazon_v62 import importar_reportes


def main() -> int:
    root=Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    parser=argparse.ArgumentParser(description="Importar métricas de Amazon Afiliados a Sportland Smart")
    parser.add_argument("--archivo")
    parser.add_argument("--directorio",default="imports/amazon/reportes")
    parser.add_argument("--mapeo",default="imports/amazon/mapeo_contenido.csv")
    parser.add_argument("--fecha-corte",help="YYYY-MM-DD cuando el CSV no incluya fecha")
    args=parser.parse_args()

    files=[]
    if args.archivo:
        p=Path(args.archivo)
        if p.exists(): files.append(p)
    else:
        d=Path(args.directorio)
        if d.exists(): files.extend(sorted(d.glob("*.csv")))

    if not files:
        print("No se encontraron reportes CSV de Amazon.")
        print("Colócalos en imports/amazon/reportes/")
        return 2

    cutoff=datetime.strptime(args.fecha_corte,"%Y-%m-%d").date() if args.fecha_corte else date.today()
    mapping=Path(args.mapeo) if args.mapeo and Path(args.mapeo).exists() else None

    cfg=MemoryConfig.from_env(str(root / ".env"))
    errors=cfg.validate()
    if errors:
        print("ERROR DE CONFIGURACIÓN:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        apply_migrations(conn)
        stats=importar_reportes(conn,files,cutoff,mapping)

    print("")
    print("Sportland Smart — Amazon 6.2")
    print("Archivos:",stats["files"])
    print("Filas leídas:",stats["rows_read"])
    print("Filas nuevas:",stats["rows_inserted"])
    print("Duplicados omitidos:",stats["rows_skipped"])
    print("Reglas de mapeo:",stats["mapping_rows"])
    return 0


if __name__=="__main__":
    raise SystemExit(main())
