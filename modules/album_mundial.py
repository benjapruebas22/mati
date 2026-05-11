import os
import re
import sqlite3
import unicodedata
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, session, url_for


DEFAULT_PASSWORD = os.environ.get("ALBUM_MUNDIAL_PASSWORD", "album2026")


DEFAULT_PAISES = [
    "FWC",
    "COCA",
    "MEXICO",
    "SUDÁFRICA",
    "KOREA",
    "REP. CHECA",
    "CANADÁ",
    "BOSNIA",
    "QATAR",
    "SUIZA",
    "BRASIL",
    "MARRUECOS",
    "HAITÍ",
    "ESCOCIA",
    "EE UU",
    "PARAGUAY",
    "AUSTRALIA",
    "TURQUÍA",
    "ALEMANIA",
    "CURAZAO",
    "COSTA DE MARFIL",
    "ECUADOR",
    "HOLANDA",
    "JAPÓN",
    "SUECIA",
    "TÚNEZ",
    "BÉLGICA",
    "EGIPTO",
    "IRÁN",
    "NUEVA ZELANDA",
    "ESPAÑA",
    "CABO VERDE",
    "ARABIA SAUDITA",
    "URUGUAY",
    "FRANCIA",
    "SENEGAL",
    "IRAK",
    "NORUEGA",
    "ARGENTINA",
    "ARGELIA",
    "AUSTRIA",
    "JORDANIA",
    "PORTUGAL",
    "CONGO",
    "UZBEKISTÁN",
    "COLOMBIA",
    "INGLATERRA",
    "CROACIA",
    "GHANA",
    "PANAMÁ",
]


def register_album_mundial(app: Flask) -> None:
    if getattr(app, "_album_mundial_registered", False):
        return
    if "album_mundial_home" in getattr(app, "view_functions", {}):
        app._album_mundial_registered = True
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "album_mundial_2026.db")

    def _connect() -> sqlite3.Connection:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _norm_txt(value: str) -> str:
        txt = str(value or "").strip().lower()
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        return " ".join(txt.split())

    def _make_code(name: str) -> str:
        base = _norm_txt(name).upper()
        base = base.replace(" ", "_")
        base = re.sub(r"[^A-Z0-9_]+", "", base)
        return base[:24] or "PAIS"

    def _ensure_schema() -> None:
        con = _connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS album_paises (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    codigo TEXT NOT NULL UNIQUE,
                    bandera TEXT,
                    orden INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS album_figuritas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pais_id INTEGER NOT NULL,
                    numero INTEGER NOT NULL,
                    nombre TEXT,
                    tipo TEXT,
                    posicion TEXT,
                    estado INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(pais_id, numero),
                    FOREIGN KEY(pais_id) REFERENCES album_paises(id) ON DELETE CASCADE
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_album_figuritas_pais ON album_figuritas(pais_id)"
            )
            con.commit()
        finally:
            con.close()

    def _seed_if_needed() -> None:
        con = _connect()
        try:
            row = con.execute("SELECT COUNT(1) AS n FROM album_paises").fetchone()
            if (row["n"] if row else 0) == 0:
                used_codes = set()
                for idx, nombre in enumerate(DEFAULT_PAISES, start=1):
                    code = _make_code(nombre)
                    base = code
                    i = 2
                    while code in used_codes:
                        code = f"{base}_{i}"
                        i += 1
                    used_codes.add(code)
                    con.execute(
                        """
                        INSERT INTO album_paises(nombre, codigo, bandera, orden)
                        VALUES(?, ?, ?, ?)
                        """,
                        (nombre, code, "", idx),
                    )
                con.commit()

            paises = con.execute("SELECT id FROM album_paises").fetchall()
            now = _now()
            for p in paises:
                for n in range(1, 21):
                    con.execute(
                        """
                        INSERT OR IGNORE INTO album_figuritas(
                            pais_id, numero, nombre, tipo, posicion, estado, updated_at
                        )
                        VALUES(?, ?, '', '', '', 0, ?)
                        """,
                        (p["id"], n, now),
                    )
            con.commit()
        finally:
            con.close()

    def _is_matias() -> bool:
        username = _norm_txt(session.get("username") or "")
        full_name = _norm_txt(session.get("full_name") or "")
        return username == "mcalderari" or full_name == "matias calderari"

    def _has_access() -> bool:
        if _is_matias():
            return True
        if session.get("album_mundial_ok"):
            return True
        key = (request.args.get("key") or "").strip()
        if key and key == DEFAULT_PASSWORD:
            session["album_mundial_ok"] = True
            return True
        return False

    def _load_state():
        con = _connect()
        try:
            pais_rows = con.execute(
                "SELECT id, nombre, codigo, bandera, orden FROM album_paises ORDER BY orden, nombre"
            ).fetchall()
            fig_rows = con.execute(
                """
                SELECT pais_id, numero, nombre, tipo, posicion, estado
                FROM album_figuritas
                ORDER BY pais_id, numero
                """
            ).fetchall()
        finally:
            con.close()

        by_pais: dict[int, dict[int, dict]] = {}
        for r in fig_rows:
            pid = int(r["pais_id"])
            by_pais.setdefault(pid, {})[int(r["numero"])] = {
                "numero": int(r["numero"]),
                "nombre": r["nombre"] or "",
                "tipo": r["tipo"] or "",
                "posicion": r["posicion"] or "",
                "estado": int(r["estado"] or 0),
            }

        paises = []
        totals = {"total": 0, "tiene": 0, "repetidas": 0, "faltan": 0, "completos": 0}
        for p in pais_rows:
            pid = int(p["id"])
            figs = []
            tiene = repetidas = faltan = 0
            for n in range(1, 21):
                f = by_pais.get(pid, {}).get(n) or {"numero": n, "nombre": "", "tipo": "", "posicion": "", "estado": 0}
                figs.append(f)
                if f["estado"] == 0:
                    faltan += 1
                elif f["estado"] == 1:
                    tiene += 1
                else:
                    repetidas += 1

            total = 20
            completos = 1 if faltan == 0 else 0
            pct = round(((tiene + repetidas) / total) * 100, 1)
            paises.append(
                {
                    "id": pid,
                    "nombre": p["nombre"],
                    "codigo": p["codigo"],
                    "bandera": p["bandera"] or "",
                    "orden": int(p["orden"] or 0),
                    "tiene": tiene,
                    "faltan": faltan,
                    "repetidas": repetidas,
                    "pct": pct,
                    "completo": bool(completos),
                    "figuritas": figs,
                }
            )

            totals["total"] += total
            totals["tiene"] += tiene
            totals["repetidas"] += repetidas
            totals["faltan"] += faltan
            totals["completos"] += completos

        totals["pct"] = round(((totals["tiene"] + totals["repetidas"]) / max(totals["total"], 1)) * 100, 1)
        return paises, totals

    @app.route("/album-mundial", methods=["GET", "POST"], endpoint="album_mundial_home")
    def album_mundial_home():
        _ensure_schema()
        _seed_if_needed()

        if not _has_access():
            if request.method == "POST":
                pwd = (request.form.get("password") or "").strip()
                if pwd == DEFAULT_PASSWORD:
                    session["album_mundial_ok"] = True
                    return redirect(url_for("album_mundial_home"))
            return render_template("album_mundial_unlock.html", title="Álbum Mundial 2026")

        paises, totals = _load_state()
        return render_template(
            "album_mundial.html",
            title="Álbum Mundial 2026",
            paises=paises,
            totals=totals,
            album_password_hint=("solo_matias" if _is_matias() else "clave"),
        )

    @app.route("/album-mundial/api/toggle", methods=["POST"], endpoint="album_mundial_toggle")
    def album_mundial_toggle():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        data = request.get_json(silent=True) or {}
        try:
            pais_id = int(data.get("pais_id"))
            numero = int(data.get("numero"))
        except Exception:
            return jsonify({"ok": False, "error": "bad_request"}), 400

        estado = int(data.get("estado", -1))
        if estado not in (0, 1, 2):
            return jsonify({"ok": False, "error": "bad_request"}), 400

        con = _connect()
        try:
            now = _now()
            cur = con.execute(
                """
                UPDATE album_figuritas
                SET estado = ?, updated_at = ?
                WHERE pais_id = ? AND numero = ?
                """,
                (estado, now, pais_id, numero),
            )
            if cur.rowcount == 0:
                con.execute(
                    """
                    INSERT INTO album_figuritas(pais_id, numero, nombre, tipo, posicion, estado, updated_at)
                    VALUES(?, ?, '', '', '', ?, ?)
                    """,
                    (pais_id, numero, estado, now),
                )
            con.commit()
        finally:
            con.close()

        return jsonify({"ok": True, "pais_id": pais_id, "numero": numero, "estado": estado})

    @app.route("/album-mundial/api/figurita", methods=["POST"], endpoint="album_mundial_update_figurita")
    def album_mundial_update_figurita():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        data = request.get_json(silent=True) or {}
        try:
            pais_id = int(data.get("pais_id"))
            numero = int(data.get("numero"))
        except Exception:
            return jsonify({"ok": False, "error": "bad_request"}), 400

        updates = []
        params = []

        if "nombre" in data:
            nombre = (data.get("nombre") or "").strip()
            updates.append("nombre = ?")
            params.append(nombre)
        if "tipo" in data:
            tipo = (data.get("tipo") or "").strip()
            updates.append("tipo = ?")
            params.append(tipo)
        if "posicion" in data:
            posicion = (data.get("posicion") or "").strip()
            updates.append("posicion = ?")
            params.append(posicion)
        if "estado" in data:
            estado = data.get("estado")
            try:
                estado_i = int(estado)
            except Exception:
                return jsonify({"ok": False, "error": "bad_request"}), 400
            if estado_i not in (0, 1, 2):
                return jsonify({"ok": False, "error": "bad_request"}), 400
            updates.append("estado = ?")
            params.append(estado_i)

        if not updates:
            return jsonify({"ok": True, "noop": True})

        updates.append("updated_at = ?")
        params.append(_now())

        params.extend([pais_id, numero])

        con = _connect()
        try:
            con.execute(
                f"""
                UPDATE album_figuritas
                SET {", ".join(updates)}
                WHERE pais_id = ? AND numero = ?
                """,
                tuple(params),
            )
            con.commit()
        finally:
            con.close()

        return jsonify({"ok": True})

    app._album_mundial_registered = True
