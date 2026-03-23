# -*- coding: utf-8 -*-
import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "mpd.db"
CSV_PATH = BASE_DIR / "combustible_marzo.csv"


def parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def to_float(x: str):
    if x is None:
        return None
    x = str(x).strip()
    if x == "":
        return None
    x = x.replace("$", "").replace(" ", "")
    x = x.replace(".", "").replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def norm_patente(p: str):
    p = (p or "").strip().upper()
    p = re.sub(r"[^A-Z0-9]", "", p)
    return p


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"No se encontro la base de datos: {DB_PATH}")
    if not CSV_PATH.exists():
        raise SystemExit(f"No se encontro el CSV: {CSV_PATH}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    chofer_map = {
        r["agente"].strip().lower(): r["id"]
        for r in con.execute("SELECT id, agente FROM agentes_intendencia")
        if r["agente"]
    }

    inserted = 0
    skipped = 0
    missing_chofer = set()

    with open(CSV_PATH, newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            fecha = parse_date(row.get("Fecha") or row.get(" Fecha"))
            patente = norm_patente(row.get("Vehiculo-Patente") or row.get("Vehiculo") or "")
            chofer = (row.get("Chofer") or "").strip()
            monto = to_float(row.get("Cantidad en Plata"))
            litros = to_float(row.get("Litros"))
            precio_litro = to_float(row.get("Precio de la Nafta") or row.get("Precio por litro"))
            remito = (row.get("N° de Remito") or row.get("N de Remito") or row.get("Remito") or "").strip()
            km_actual = to_float(row.get("Kilometraje") or row.get("Kilometro actual") or "")

            if not fecha or not patente or litros is None or precio_litro is None or monto is None:
                skipped += 1
                continue

            chofer_id = None
            if chofer:
                chofer_id = chofer_map.get(chofer.lower())
                if chofer_id is None:
                    missing_chofer.add(chofer)

            dup = con.execute(
                """
                SELECT id FROM combustible_cargas
                WHERE fecha=? AND patente=? AND COALESCE(km_actual,0)=COALESCE(?,0)
                  AND COALESCE(remito,'')=COALESCE(?, '')
                """,
                (fecha, patente, km_actual or 0, remito),
            ).fetchone()
            if dup:
                skipped += 1
                continue

            cur.execute(
                """
                INSERT INTO combustible_cargas
                (fecha, patente, chofer_id, remito, km_actual, litros, precio_litro, precio_total, notas)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (fecha, patente, chofer_id, remito, km_actual or 0, litros, precio_litro, monto, ""),
            )
            inserted += 1

    con.commit()
    con.close()

    print(f"Insertados: {inserted}")
    print(f"Omitidos (duplicados o incompletos): {skipped}")
    if missing_chofer:
        print(f"Chofer no encontrado ({len(missing_chofer)}): {', '.join(sorted(missing_chofer))}")


if __name__ == "__main__":
    main()
