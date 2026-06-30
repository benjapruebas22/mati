import argparse
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BASE_DIR / "mpd.db"
DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "matafuegos_pdf_2026-06-30.csv"


def add_year(value):
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    try:
        return parsed.replace(year=parsed.year + 1).isoformat()
    except ValueError:
        return parsed.replace(month=2, day=28, year=parsed.year + 1).isoformat()


def lot_from_hydro(value):
    if not value:
        return "Otro"
    month = datetime.strptime(value, "%Y-%m-%d").month
    return {5: "Mayo", 9: "Septiembre", 12: "Diciembre"}.get(month, "Otro")


def status_from_expiration(value):
    expiration = datetime.strptime(value, "%Y-%m-%d").date()
    days = (expiration - date.today()).days
    if days < 0:
        return "Vencido"
    if days <= 45:
        return "Vence pronto"
    return "OK"


def ensure_schema(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS matafuegos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cod_sede TEXT NOT NULL DEFAULT '', sede TEXT NOT NULL, piso TEXT,
            local TEXT, tipo TEXT NOT NULL DEFAULT '', capacidad_kg REAL,
            numero_serie TEXT, nro_extintor TEXT, ubicacion TEXT,
            fecha_recarga TEXT, fecha_vencimiento TEXT, fecha_prueba_hidro TEXT,
            estado TEXT DEFAULT 'Sin dato', activo INTEGER DEFAULT 1,
            lote_vencimiento TEXT, observaciones TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
        )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(matafuegos)")}
    if "nro_extintor" not in columns:
        connection.execute("ALTER TABLE matafuegos ADD COLUMN nro_extintor TEXT")


def main():
    parser = argparse.ArgumentParser(description="Importa los 40 matafuegos relevados en el PDF del 30/06/2026")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Ruta de mpd.db")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV normalizado incluido en el proyecto")
    parser.add_argument("--dry-run", action="store_true", help="Valida sin guardar")
    args = parser.parse_args()

    connection = sqlite3.connect(Path(args.db))
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    inserted = 0
    updated = 0

    with Path(args.csv).open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            expiration = add_year(row["fecha_recarga"])
            existing = connection.execute(
                "SELECT id FROM matafuegos WHERE UPPER(TRIM(COALESCE(numero_serie,''))) = UPPER(TRIM(?)) AND UPPER(TRIM(COALESCE(sede,''))) = ? AND COALESCE(nro_extintor,'') = ?",
                (row["numero_serie"], row["cod_sede"], row["nro_extintor"]),
            ).fetchone()
            values = (
                row["cod_sede"], row["cod_sede"], row["piso"], row["ubicacion"],
                row["numero_serie"], row["nro_extintor"], row["ubicacion"],
                row["fecha_recarga"], expiration, row["fecha_prueba_hidro"],
                status_from_expiration(expiration), lot_from_hydro(row["fecha_prueba_hidro"]),
                f"PDF 30/06/2026 · Ref.: {row['observaciones']}",
            )
            if existing:
                connection.execute("""
                    UPDATE matafuegos
                    SET cod_sede=?, sede=?, piso=?, local=?, numero_serie=?, nro_extintor=?,
                        ubicacion=?, fecha_recarga=?, fecha_vencimiento=?, fecha_prueba_hidro=?,
                        estado=?, lote_vencimiento=?, observaciones=?, activo=1,
                        tipo=CASE WHEN TRIM(COALESCE(tipo,''))='' THEN 'Sin dato' ELSE tipo END,
                        updated_at=datetime('now','localtime')
                    WHERE id=?
                """, values + (existing["id"],))
                updated += 1
            else:
                connection.execute("""
                    INSERT INTO matafuegos(
                        cod_sede, sede, piso, local, tipo, capacidad_kg, numero_serie,
                        nro_extintor, ubicacion, fecha_recarga, fecha_vencimiento,
                        fecha_prueba_hidro, estado, activo, lote_vencimiento,
                        observaciones, created_at, updated_at
                    ) VALUES (?,?,?,?,'Sin dato',NULL,?,?,?,?,?,?,?,1,?,?,datetime('now','localtime'),datetime('now','localtime'))
                """, (
                    row["cod_sede"], row["cod_sede"], row["piso"], row["ubicacion"],
                    row["numero_serie"], row["nro_extintor"], row["ubicacion"],
                    row["fecha_recarga"], expiration, row["fecha_prueba_hidro"],
                    status_from_expiration(expiration), lot_from_hydro(row["fecha_prueba_hidro"]),
                    f"PDF 30/06/2026 · Ref.: {row['observaciones']}",
                ))
                inserted += 1

    if args.dry_run:
        connection.rollback()
    else:
        connection.commit()
    connection.close()
    print(f"Insertados: {inserted} | Actualizados: {updated} | Modo: {'validación' if args.dry_run else 'guardado'}")


if __name__ == "__main__":
    main()
