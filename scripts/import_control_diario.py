import csv
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "mpd.db"
CSV_PATH = BASE_DIR / "carga_controldiario_faltantes.csv"


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
    x = (x or "").strip().replace(",", ".")
    if x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


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
    dest_map = {
        r["nombre"].strip().lower(): r["id"]
        for r in con.execute("SELECT id, nombre FROM destinos")
        if r["nombre"]
    }

    inserted = 0
    skipped = 0
    missing_chofer = set()

    with open(CSV_PATH, newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            fecha = parse_date(row.get("Fecha"))
            patente = (row.get("Vehiculo ") or row.get("Vehiculo") or "").strip().upper()
            chofer = (row.get("chofer") or "").strip()
            km_ini = row.get("KM Inicial tramo") or row.get("KM inicial tramo") or ""
            km_fin = row.get("KM final del tramo") or ""
            dif = row.get("Dif de Km") or row.get("Dif de KM") or ""
            agente = (row.get("Agente") or "").strip()
            sector = (row.get("sector") or "").strip()
            dependencia = (row.get("dpto/defensoria") or "").strip()
            destino = (row.get("destino") or "").strip()

            if not fecha or not patente:
                skipped += 1
                continue

            km_ini_f = to_float(km_ini)
            km_fin_f = to_float(km_fin)
            dif_f = to_float(dif)

            chofer_id = None
            if chofer:
                chofer_id = chofer_map.get(chofer.lower())
                if chofer_id is None:
                    missing_chofer.add(chofer)

            destino_id = None
            if destino:
                destino_id = dest_map.get(destino.lower())
                if destino_id is None:
                    cur.execute("INSERT INTO destinos(nombre, activo) VALUES(?,1)", (destino,))
                    destino_id = cur.lastrowid
                    dest_map[destino.lower()] = destino_id

            dup = con.execute(
                """
                SELECT id FROM viajes
                WHERE fecha=? AND patente=?
                  AND COALESCE(km_ini,0)=COALESCE(?,0)
                  AND COALESCE(km_fin,0)=COALESCE(?,0)
                """,
                (fecha, patente, km_ini_f, km_fin_f),
            ).fetchone()
            if dup:
                skipped += 1
                continue

            estado = "CERRADO" if km_fin_f not in (None, 0) else "EN CURSO"
            obs = ""
            if chofer and chofer_id is None:
                obs = f"Chofer: {chofer}"

            cur.execute(
                """
                INSERT INTO viajes
                (fecha, patente, chofer_id, agente_trasladado, destino_id,
                 km_ini, km_fin, recorrido_km, observaciones, estado, sector, dependencia)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fecha,
                    patente,
                    chofer_id,
                    agente,
                    destino_id,
                    km_ini_f,
                    km_fin_f,
                    dif_f,
                    obs,
                    estado,
                    sector,
                    dependencia,
                ),
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
