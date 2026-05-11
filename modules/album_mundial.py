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

    def _pais_code_variants(code: str) -> set[str]:
        base = (code or "").strip().upper()
        variants = {base}
        variants.add(base.replace("_", ""))
        variants.add(base.replace(".", ""))
        variants.add(base.replace("_", "").replace(".", ""))
        return {v for v in variants if v}

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

    @app.route(
        "/album-mundial/api/import/repetidas",
        methods=["POST"],
        endpoint="album_mundial_import_repetidas",
    )
    def album_mundial_import_repetidas():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        _ensure_schema()
        _seed_if_needed()

        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": True, "updated": [], "unknown": [], "invalid": []})

        con = _connect()
        try:
            rows = con.execute("SELECT id, nombre, codigo FROM album_paises").fetchall()
            code_to_id: dict[str, int] = {}
            for r in rows:
                for v in _pais_code_variants(str(r["codigo"] or "")):
                    code_to_id[v] = int(r["id"])
                name_code = _make_code(str(r["nombre"] or ""))
                for v in _pais_code_variants(name_code):
                    code_to_id[v] = int(r["id"])

            updated: set[tuple[int, int]] = set()
            unknown: list[str] = []
            invalid: list[str] = []

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if ":" not in line:
                    invalid.append(line)
                    continue

                raw_pais, raw_nums = line.split(":", 1)
                pais_code = _make_code(raw_pais)
                pais_id = (
                    code_to_id.get(pais_code)
                    or code_to_id.get(pais_code.replace("_", ""))
                    or code_to_id.get(pais_code.replace(".", ""))
                    or code_to_id.get(pais_code.replace("_", "").replace(".", ""))
                )
                if not pais_id:
                    unknown.append(raw_pais.strip() or line)
                    continue

                nums_part = raw_nums.strip()
                if not nums_part:
                    invalid.append(line)
                    continue

                tokens = re.split(r"[,\s]+", nums_part)
                any_ok = False
                for tok in tokens:
                    t = tok.strip()
                    if not t:
                        continue
                    m = re.match(r"^(?P<num>\d{1,3})(?:x(?P<count>\d{1,2}))?$", t, re.IGNORECASE)
                    if not m:
                        invalid.append(f"{raw_pais.strip()}: {t}")
                        continue
                    try:
                        num = int(m.group("num"))
                    except Exception:
                        invalid.append(f"{raw_pais.strip()}: {t}")
                        continue
                    if num < 1 or num > 20:
                        invalid.append(f"{raw_pais.strip()}: {t}")
                        continue
                    updated.add((int(pais_id), num))
                    any_ok = True

                if not any_ok:
                    invalid.append(line)

            if updated:
                now = _now()
                con.executemany(
                    """
                    UPDATE album_figuritas
                    SET estado = 2, updated_at = ?
                    WHERE pais_id = ? AND numero = ?
                    """,
                    [(now, pid, num) for (pid, num) in sorted(updated)],
                )
                con.commit()

            return jsonify(
                {
                    "ok": True,
                    "updated": [
                        {"pais_id": pid, "numero": num, "estado": 2} for (pid, num) in sorted(updated)
                    ],
                    "unknown": unknown,
                    "invalid": invalid,
                }
            )
        finally:
            con.close()

    @app.route("/album-mundial/api/reset", methods=["POST"], endpoint="album_mundial_reset")
    def album_mundial_reset():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        _ensure_schema()
        _seed_if_needed()

        con = _connect()
        try:
            now = _now()
            con.execute("UPDATE album_figuritas SET estado = 0, updated_at = ?", (now,))
            con.commit()
        finally:
            con.close()

        return jsonify({"ok": True})

    @app.route(
        "/album-mundial/api/backup/export",
        methods=["GET"],
        endpoint="album_mundial_export_backup",
    )
    def album_mundial_export_backup():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        _ensure_schema()
        _seed_if_needed()

        paises, totals = _load_state()
        return jsonify(
            {
                "ok": True,
                "version": 1,
                "exported_at": _now(),
                "paises": paises,
                "totals": totals,
            }
        )

    @app.route(
        "/album-mundial/api/backup/import",
        methods=["POST"],
        endpoint="album_mundial_import_backup",
    )
    def album_mundial_import_backup():
        if not _has_access():
            return jsonify({"ok": False, "error": "forbidden"}), 403

        _ensure_schema()
        _seed_if_needed()

        data = request.get_json(silent=True) or {}
        payload = data.get("backup") if isinstance(data.get("backup"), dict) else data
        paises_payload = payload.get("paises") if isinstance(payload, dict) else None
        if not isinstance(paises_payload, list):
            return jsonify({"ok": False, "error": "bad_request"}), 400

        con = _connect()
        try:
            rows = con.execute("SELECT id, codigo, nombre FROM album_paises").fetchall()
            code_to_id: dict[str, int] = {}
            for r in rows:
                for v in _pais_code_variants(str(r["codigo"] or "")):
                    code_to_id[v] = int(r["id"])
                name_code = _make_code(str(r["nombre"] or ""))
                for v in _pais_code_variants(name_code):
                    code_to_id[v] = int(r["id"])

            now = _now()
            created = 0
            changed = 0

            for p in paises_payload:
                if not isinstance(p, dict):
                    continue
                raw_code = str(p.get("codigo") or p.get("code") or "").strip()
                raw_name = str(p.get("nombre") or p.get("name") or raw_code).strip()
                code = _make_code(raw_code or raw_name)
                if not code:
                    continue

                pais_id = code_to_id.get(code) or code_to_id.get(code.replace("_", ""))
                if not pais_id:
                    con.execute(
                        """
                        INSERT OR IGNORE INTO album_paises(nombre, codigo, bandera, orden)
                        VALUES(?, ?, ?, ?)
                        """,
                        (raw_name or code, code, str(p.get("bandera") or ""), int(p.get("orden") or 0)),
                    )
                    row = con.execute("SELECT id FROM album_paises WHERE codigo = ?", (code,)).fetchone()
                    pais_id = int(row["id"]) if row else None
                    if not pais_id:
                        continue
                    for v in _pais_code_variants(code):
                        code_to_id[v] = int(pais_id)
                    created += 1

                figs = p.get("figuritas")
                if not isinstance(figs, list):
                    continue
                for f in figs:
                    if not isinstance(f, dict):
                        continue
                    try:
                        numero = int(f.get("numero"))
                    except Exception:
                        continue
                    if numero < 1 or numero > 20:
                        continue

                    estado = f.get("estado", 0)
                    try:
                        estado_i = int(estado)
                    except Exception:
                        estado_i = 0
                    if estado_i not in (0, 1, 2):
                        estado_i = 0

                    nombre = str(f.get("nombre") or "").strip()
                    tipo = str(f.get("tipo") or "").strip()
                    posicion = str(f.get("posicion") or "").strip()

                    cur = con.execute(
                        """
                        UPDATE album_figuritas
                        SET nombre = ?, tipo = ?, posicion = ?, estado = ?, updated_at = ?
                        WHERE pais_id = ? AND numero = ?
                        """,
                        (nombre, tipo, posicion, estado_i, now, int(pais_id), numero),
                    )
                    if cur.rowcount == 0:
                        con.execute(
                            """
                            INSERT INTO album_figuritas(pais_id, numero, nombre, tipo, posicion, estado, updated_at)
                            VALUES(?, ?, ?, ?, ?, ?, ?)
                            """,
                            (int(pais_id), numero, nombre, tipo, posicion, estado_i, now),
                        )
                    changed += 1

            con.commit()
        finally:
            con.close()

        return jsonify({"ok": True, "created_paises": created, "changed": changed})

    app._album_mundial_registered = True
