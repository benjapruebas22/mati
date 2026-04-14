import argparse
import re
import sqlite3
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "mpd.db"


def _normalize_text(value: str) -> str:
    txt = str(value or "").strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return " ".join(txt.split())


_DESTINO_PREFIXES = {"barrio", "b", "bo", "bda", "barr"}

_DESTINO_ALIAS = {
    "centro": "CENTRO",
    "san salvador": "SAN SALVADOR DE JUJUY",
    "san salvador de jujuy": "SAN SALVADOR DE JUJUY",
    "palpala": "PALPALA",
    "gorriti": "GORRITI",
    "coronel arias": "CORONEL ARIAS",
    "ciudad de nieva": "CIUDAD DE NIEVA",
    "chijra": "CHIJRA",
    "huaico": "HUAYCO",
    "huayco": "HUAYCO",
    "san cayetano": "SAN CAYETANO",
    "mariano moreno": "MARIANO MORENO",
    "malvinas": "MALVINAS",
    "campo verde": "CAMPO VERDE",
    "alto comedero": "ALTO COMEDERO",
    "alto padilla": "ALTO PADILLA",
    "alto la vina": "ALTO LA VINA",
    "bajo la vina": "BAJO LA VINA",
    "villa san martin": "VILLA SAN MARTIN",
    "belgrano": "BELGRANO",
    "punta diamante": "PUNTA DIAMANTE",
    "los perales": "LOS PERALES",
    "san pedrito": "SAN PEDRITO",
    "alte brown": "ALTE BROWN",
    "azopardo": "AZOPARDO",
    "el chingo": "EL CHINGO",
    "altos de zapla": "ALTOS DE ZAPLA",
    "libertador": "LIBERTADOR",
    "libertador gral san martin": "LIBERTADOR",
    "ledesma": "LEDESMA",
    "san pedro": "SAN PEDRO",
    "rodeito": "RODEITO",
    "chalican": "CHALICAN",
    "yala": "YALA",
    "perico": "PERICO",
    "el carmen": "EL CARMEN",
    "monterrico": "MONTERRICO",
    "monte rico": "MONTERRICO",
    "lozano": "LOZANO",
    "san antonio": "SAN ANTONIO",
    "san pablo de reyes": "SAN PABLO DE REYES",
    "pampa blanca": "PAMPA BLANCA",
    "santa clara": "SANTA CLARA",
    "palma sola": "PALMA SOLA",
    "el talar": "EL TALAR",
    "la mendieta": "LA MENDIETA",
    "tilcara": "TILCARA",
    "humahuaca": "HUMAHUACA",
    "abra pampa": "ABRA PAMPA",
    "la quiaca": "LA QUIACA",
    "susques": "SUSQUES",
    "salta": "SALTA",
    "gueme": "GUEMES",
    "guemes": "GUEMES",
}


def _clean_destino_text(value: str):
    raw = str(value or "").strip()
    base = _normalize_text(raw)
    base = re.sub(r"[^\w\s]", " ", base)
    base = base.replace("_", " ")
    base = " ".join(base.split())
    parts = base.split()
    while parts and parts[0] in _DESTINO_PREFIXES:
        parts = parts[1:]
    base = " ".join(parts).strip()
    return raw, base


def normalize_destino(destino: str):
    raw, cleaned = _clean_destino_text(destino)
    if not cleaned:
        return {"raw": raw, "cleaned": "", "canon": "", "key": ""}
    canon = _DESTINO_ALIAS.get(cleaned)
    if not canon:
        if cleaned.startswith("libertador"):
            canon = "LIBERTADOR"
        else:
            canon = cleaned.upper()
    key = _normalize_text(canon)
    return {"raw": raw, "cleaned": cleaned, "canon": canon, "key": key}


def normalize_base_operativa(origen: str) -> str:
    txt = _normalize_text(origen or "").replace(".", " ").strip()
    txt = " ".join(txt.split())
    if txt in {"san pedro", "s pedro", "s. pedro", "san pedro de jujuy"}:
        return "san pedro"
    if txt in {"san salvador", "san salvador de jujuy", "ssj"}:
        return "san salvador de jujuy"
    if not txt:
        return "san salvador de jujuy"
    return txt


_DEST_ZONA_LONG = {"tilcara", "humahuaca", "abra pampa", "la quiaca", "susques", "salta"}
_DEST_ZONA_RAMAL = {"san pedro", "ledesma", "libertador", "santa clara", "palma sola", "el talar", "la mendieta", "rodeito", "chalican", "yuto"}
_DEST_ZONA_CERCANA = {"yala", "palpala", "perico", "el carmen", "monterrico", "monte rico", "lozano", "san antonio", "san pablo de reyes", "pampa blanca", "altos de zapla", "los alisos", "guerrero"}


def _guess_zona(dest_key: str) -> str:
    k = _normalize_text(dest_key or "")
    if k in _DEST_ZONA_LONG:
        return "larga"
    if k in _DEST_ZONA_RAMAL:
        return "ramal"
    if k in _DEST_ZONA_CERCANA:
        return "cercano"
    return "urbano"


def guess_ref_range(base_key: str, dest_key: str):
    b = normalize_base_operativa(base_key)
    d = _normalize_text(dest_key or "")
    zona = _guess_zona(d)

    defaults = {
        "san salvador de jujuy": {"urbano": (2.0, 12.0), "cercano": (20.0, 50.0), "ramal": (130.0, 200.0), "larga": (180.0, 240.0)},
        "san pedro": {"urbano": (2.0, 12.0), "cercano": (20.0, 60.0), "ramal": (60.0, 150.0), "larga": (220.0, 320.0)},
    }
    km_min, km_max = (defaults.get(b) or defaults["san salvador de jujuy"]).get(zona, (20.0, 50.0))

    overrides = {
        ("san salvador de jujuy", "centro"): (2.0, 10.0, "urbano"),
        ("san salvador de jujuy", "alto comedero"): (14.0, 30.0, "urbano"),
        ("san salvador de jujuy", "yala"): (10.0, 25.0, "cercano"),
        ("san salvador de jujuy", "palpala"): (26.0, 45.0, "cercano"),
        ("san salvador de jujuy", "perico"): (50.0, 90.0, "cercano"),
        ("san salvador de jujuy", "el carmen"): (30.0, 70.0, "cercano"),
        ("san salvador de jujuy", "monterrico"): (50.0, 90.0, "cercano"),
        ("san salvador de jujuy", "san pedro"): (130.0, 160.0, "ramal"),
        ("san salvador de jujuy", "ledesma"): (230.0, 300.0, "ramal"),
        ("san salvador de jujuy", "libertador"): (230.0, 300.0, "ramal"),
        ("san salvador de jujuy", "tilcara"): (170.0, 200.0, "larga"),
        ("san salvador de jujuy", "humahuaca"): (240.0, 280.0, "larga"),
        ("san salvador de jujuy", "abra pampa"): (310.0, 360.0, "larga"),
        ("san salvador de jujuy", "la quiaca"): (560.0, 630.0, "larga"),
        ("san salvador de jujuy", "susques"): (420.0, 480.0, "larga"),
        ("san salvador de jujuy", "salta"): (240.0, 290.0, "larga"),
        ("san pedro", "san pedro"): (2.0, 12.0, "urbano"),
        ("san pedro", "centro"): (130.0, 160.0, "interurbano"),
        ("san pedro", "san salvador de jujuy"): (130.0, 160.0, "interurbano"),
        ("san pedro", "la mendieta"): (20.0, 40.0, "cercano"),
        ("san pedro", "rodeito"): (30.0, 50.0, "cercano"),
        ("san pedro", "chalican"): (50.0, 80.0, "cercano"),
        ("san pedro", "ledesma"): (60.0, 90.0, "ramal"),
        ("san pedro", "libertador"): (60.0, 90.0, "ramal"),
        ("san pedro", "santa clara"): (120.0, 150.0, "ramal"),
        ("san pedro", "palma sola"): (160.0, 210.0, "ramal"),
        ("san pedro", "el talar"): (180.0, 220.0, "ramal"),
        ("san pedro", "yuto"): (100.0, 130.0, "ramal"),
    }
    ov = overrides.get((b, d))
    if ov:
        return ov[2], float(ov[0]), float(ov[1])
    return zona, float(km_min), float(km_max)


def _ensure_destinos_referencia_table(con: sqlite3.Connection):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS destinos_referencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destino_original TEXT,
            destino_normalizado TEXT NOT NULL,
            destino_key TEXT NOT NULL,
            zona_operativa TEXT NOT NULL DEFAULT '',
            km_ref_min REAL,
            km_ref_max REAL,
            base_operativa TEXT NOT NULL DEFAULT '',
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_destinos_referencia_key_base ON destinos_referencia(destino_key, base_operativa)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_destinos_referencia_activo ON destinos_referencia(activo)")
    con.commit()


def _vehiculos_has_base_col(con: sqlite3.Connection) -> bool:
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(vehiculos)").fetchall()]
        return "base_operativa" in cols
    except Exception:
        return False


def infer_base_operativa(patente: str, codigo_interno: str, base_operativa: str) -> str:
    if base_operativa and str(base_operativa).strip():
        return normalize_base_operativa(base_operativa)
    pat = _normalize_text(patente or "").replace(" ", "")
    cod = _normalize_text(codigo_interno or "").replace(" ", "")
    if pat == "ae856ge" or cod in {"g-02", "g02"}:
        return "san pedro"
    return "san salvador de jujuy"


def _iqr_trim_range(values):
    vals = sorted([float(v) for v in values if v is not None and float(v) > 0])
    if not vals:
        return None
    n = len(vals)
    if n < 3:
        return (round(vals[0], 1), round(vals[-1], 1))
    q1 = vals[int(0.25 * (n - 1))]
    q3 = vals[int(0.75 * (n - 1))]
    iqr = q3 - q1
    lo = max(vals[0], q1 - 1.5 * iqr)
    hi = min(vals[-1], q3 + 1.5 * iqr)
    lo = max(2.0, lo)
    hi = max(lo, hi)
    return (round(lo, 1), round(hi, 1))


def backfill(force: bool = False, min_samples: int = 3):
    if not DB_PATH.exists():
        raise SystemExit(f"No se encontro la base de datos: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    _ensure_destinos_referencia_table(con)

    has_base_col = _vehiculos_has_base_col(con)
    base_select = "COALESCE(NULLIF(TRIM(v.base_operativa),''),'') AS base_operativa" if has_base_col else "'' AS base_operativa"

    rows = con.execute(
        f"""
        SELECT
            vc.patente,
            v.codigo_interno,
            {base_select},
            d.nombre AS destino_nombre,
            COALESCE(vc.recorrido_km, 0) AS recorrido_km
        FROM viajes vc
        LEFT JOIN vehiculos v ON v.patente = vc.patente
        LEFT JOIN destinos d ON d.id = vc.destino_id
        WHERE UPPER(REPLACE(TRIM(COALESCE(vc.estado,'')), '_', ' ')) = 'CERRADO'
          AND COALESCE(vc.recorrido_km, 0) > 0
          AND TRIM(COALESCE(d.nombre,'')) <> ''
        """
    ).fetchall()

    groups = {}
    meta = {}
    for r in rows:
        destino_raw = (r["destino_nombre"] or "").strip()
        dest_norm = normalize_destino(destino_raw)
        if not dest_norm["key"]:
            continue
        base_key = infer_base_operativa(r["patente"], r["codigo_interno"], r["base_operativa"] if has_base_col else "")
        key = (base_key, dest_norm["key"])
        groups.setdefault(key, []).append(float(r["recorrido_km"] or 0))
        meta.setdefault(key, {"canon": dest_norm["canon"], "destino_original": destino_raw})

    inserted = 0
    updated = 0
    skipped = 0
    for (base_key, dest_key), vals in groups.items():
        rng = _iqr_trim_range(vals)
        zona, def_min, def_max = guess_ref_range(base_key, dest_key)
        if rng and len(vals) >= min_samples:
            km_min, km_max = rng
        else:
            km_min, km_max = def_min, def_max

        exists = con.execute(
            "SELECT id, km_ref_min, km_ref_max FROM destinos_referencia WHERE destino_key=? AND base_operativa=? LIMIT 1",
            (dest_key, normalize_base_operativa(base_key)),
        ).fetchone()
        if exists and not force:
            skipped += 1
            continue
        if exists:
            con.execute(
                """
                UPDATE destinos_referencia
                SET destino_normalizado=?, zona_operativa=?, km_ref_min=?, km_ref_max=?, activo=1
                WHERE id=?
                """,
                (meta[(base_key, dest_key)]["canon"], zona, float(km_min), float(km_max), int(exists["id"])),
            )
            updated += 1
        else:
            con.execute(
                """
                INSERT INTO destinos_referencia
                (destino_original, destino_normalizado, destino_key, zona_operativa, km_ref_min, km_ref_max, base_operativa, activo)
                VALUES (?,?,?,?,?,?,?,1)
                """,
                (
                    meta[(base_key, dest_key)]["destino_original"],
                    meta[(base_key, dest_key)]["canon"],
                    dest_key,
                    zona,
                    float(km_min),
                    float(km_max),
                    normalize_base_operativa(base_key),
                ),
            )
            inserted += 1

    # Completa destinos sin historia (catalogo) con defaults, sin pisar manual
    bases = ["san salvador de jujuy", "san pedro"]
    dest_catalog = con.execute(
        "SELECT nombre FROM destinos WHERE COALESCE(activo,1)=1 AND TRIM(COALESCE(nombre,'')) <> ''"
    ).fetchall()
    for drow in dest_catalog:
        nombre = (drow["nombre"] or "").strip()
        dn = normalize_destino(nombre)
        if not dn["key"]:
            continue
        for b in bases:
            zona, km_min, km_max = guess_ref_range(b, dn["key"])
            con.execute(
                """
                INSERT OR IGNORE INTO destinos_referencia
                (destino_original, destino_normalizado, destino_key, zona_operativa, km_ref_min, km_ref_max, base_operativa, activo)
                VALUES (?,?,?,?,?,?,?,1)
                """,
                (nombre, dn["canon"], dn["key"], zona, float(km_min), float(km_max), normalize_base_operativa(b)),
            )

    con.commit()
    con.close()
    print(f"OK backfill destinos_referencia | inserted={inserted} updated={updated} skipped={skipped} force={force}")


def main():
    ap = argparse.ArgumentParser(description="Backfill de destinos_referencia (KM razonable) desde historial de viajes.")
    ap.add_argument("--force", action="store_true", help="Recalcula y pisa referencias existentes.")
    ap.add_argument("--min-samples", type=int, default=3, help="Minimo de muestras para usar rango por historial (default 3).")
    args = ap.parse_args()
    backfill(force=bool(args.force), min_samples=int(args.min_samples))


if __name__ == "__main__":
    main()

