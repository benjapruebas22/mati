from datetime import date

from flask import flash, redirect, render_template, request, session, url_for


def register_asignaciones_simple(app, get_db):
    if getattr(app, "_asignaciones_simple_registered", False):
        return
    app._asignaciones_simple_registered = True

    DAILY_DEFAULTS = [
        {"orden": 1, "chofer": "Leo", "vehiculo": "AF277OA", "destino": "Palpala", "solicitante": "", "hora_llegada_aprox": ""},
        {"orden": 2, "chofer": "Manuel", "vehiculo": "AE856GD", "destino": "", "solicitante": "", "hora_llegada_aprox": ""},
        {"orden": 3, "chofer": "Gaston", "vehiculo": "AG846FR", "destino": "", "solicitante": "", "hora_llegada_aprox": ""},
    ]
    ROTACION_VIAJES = [
        (1, "Itinerancia / Susques"),
        (2, "Ledesma / San Pedro"),
        (3, "Perico"),
        (4, "La Quiaca"),
        (5, "Viaje largo general"),
        (6, "Otro especial"),
    ]
    REFERENCIA_DEFAULTS = [
        (1, "Mauro Vea Murguia"),
        (2, "Gaston Villagra"),
        (3, "Jorge Corbacho"),
        (4, "Emiliano Perez"),
    ]

    def _role() -> str:
        return (session.get("role") or "").strip().lower()

    def _username() -> str:
        return (session.get("username") or "").strip().lower()

    def _can_access() -> bool:
        role = _role()
        user = _username()
        if role in {"full", "admin", "dashboard_vehiculos", "dashboard_solo", "operativo_clave", "int_vehiculos", "ejecutivo"}:
            return True
        return user in {"mcalderari", "admi", "ibaroni", "fsavio", "mduran", "cvidaurre"}

    def _deny():
        flash("Acceso restringido a Intendencia.", "warning")
        try:
            return redirect(url_for("dashboard_exec"))
        except Exception:
            return redirect(url_for("dashboard"))

    def _today_iso():
        return date.today().isoformat()

    def _clean_text(v):
        return (str(v or "").strip())

    def _ensure_schema(con):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_simples_diario(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                chofer TEXT,
                vehiculo TEXT,
                destino TEXT,
                solicitante TEXT,
                hora_llegada_aprox TEXT,
                orden INTEGER NOT NULL DEFAULT 999,
                actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_simples_rotacion_ultimo(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viaje_destino TEXT NOT NULL UNIQUE,
                fecha TEXT,
                ultimo_asignado TEXT,
                orden INTEGER NOT NULL DEFAULT 999
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_simples_rotacion_proximo(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viaje_destino TEXT NOT NULL UNIQUE,
                fecha TEXT,
                proximo_asignado TEXT,
                orden INTEGER NOT NULL DEFAULT 999
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_simples_referencia(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden INTEGER NOT NULL DEFAULT 999,
                chofer TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_as_simple_diario_fecha_orden ON asignaciones_simples_diario(fecha, orden)")
        con.commit()

    def _seed_rotacion(con):
        cnt_u = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_rotacion_ultimo").fetchone()["c"] or 0)
        if cnt_u == 0:
            for orden, viaje in ROTACION_VIAJES:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_rotacion_ultimo(viaje_destino, fecha, ultimo_asignado, orden)
                    VALUES (?, '', '', ?)
                    """,
                    (viaje, orden),
                )
        cnt_p = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_rotacion_proximo").fetchone()["c"] or 0)
        if cnt_p == 0:
            for orden, viaje in ROTACION_VIAJES:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_rotacion_proximo(viaje_destino, fecha, proximo_asignado, orden)
                    VALUES (?, '', '', ?)
                    """,
                    (viaje, orden),
                )
        cnt_r = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_referencia").fetchone()["c"] or 0)
        if cnt_r == 0:
            for orden, chofer in REFERENCIA_DEFAULTS:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_referencia(orden, chofer)
                    VALUES (?, ?)
                    """,
                    (orden, chofer),
                )
        con.commit()

    def _reset_diario_for_fecha(con, fecha):
        con.execute("DELETE FROM asignaciones_simples_diario WHERE fecha = ?", (fecha,))
        for row in DAILY_DEFAULTS:
            con.execute(
                """
                INSERT INTO asignaciones_simples_diario(
                    fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox, orden
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    fecha,
                    row["chofer"],
                    row["vehiculo"],
                    row["destino"],
                    row["solicitante"],
                    row["hora_llegada_aprox"],
                    int(row["orden"]),
                ),
            )
        con.commit()

    def _ensure_diario_for_fecha(con, fecha):
        cnt = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM asignaciones_simples_diario WHERE fecha = ?",
                (fecha,),
            ).fetchone()["c"]
            or 0
        )
        if cnt == 0:
            _reset_diario_for_fecha(con, fecha)

    def _list_diario(con, fecha):
        return con.execute(
            """
            SELECT id, fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox, orden
            FROM asignaciones_simples_diario
            WHERE fecha = ?
            ORDER BY COALESCE(orden,999), id
            """,
            (fecha,),
        ).fetchall()

    def _list_rot_ultimo(con):
        return con.execute(
            """
            SELECT id, viaje_destino, fecha, ultimo_asignado, orden
            FROM asignaciones_simples_rotacion_ultimo
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    def _list_rot_proximo(con):
        return con.execute(
            """
            SELECT id, viaje_destino, fecha, proximo_asignado, orden
            FROM asignaciones_simples_rotacion_proximo
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    def _list_referencia(con):
        return con.execute(
            """
            SELECT id, orden, chofer
            FROM asignaciones_simples_referencia
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    @app.route("/asignaciones-simple", endpoint="asignaciones_simple_home")
    def asignaciones_simple_home():
        if not _can_access():
            return _deny()
        con = get_db()
        try:
            _ensure_schema(con)
            _seed_rotacion(con)
            fecha = _clean_text(request.args.get("fecha")) or _today_iso()
            _ensure_diario_for_fecha(con, fecha)
            diario_rows = _list_diario(con, fecha)
            rot_ultimo_rows = _list_rot_ultimo(con)
            rot_proximo_rows = _list_rot_proximo(con)
            referencia_rows = _list_referencia(con)
            return render_template(
                "asignaciones_simple_home.html",
                fecha=fecha,
                diario_rows=diario_rows,
                rot_ultimo_rows=rot_ultimo_rows,
                rot_proximo_rows=rot_proximo_rows,
                referencia_rows=referencia_rows,
            )
        finally:
            con.close()

    @app.route("/asignaciones-simple/guardar", methods=["POST"], endpoint="asignaciones_simple_guardar")
    def asignaciones_simple_guardar():
        if not _can_access():
            return _deny()
        con = get_db()
        try:
            _ensure_schema(con)
            _seed_rotacion(con)
            action = _clean_text(request.form.get("action"))
            fecha = _clean_text(request.form.get("fecha")) or _today_iso()

            if action == "guardar_diario":
                _ensure_diario_for_fecha(con, fecha)
                row_ids = request.form.getlist("row_id")
                choferes = request.form.getlist("chofer")
                vehiculos = request.form.getlist("vehiculo")
                destinos = request.form.getlist("destino")
                solicitantes = request.form.getlist("solicitante")
                horas = request.form.getlist("hora_llegada_aprox")
                ordenes = request.form.getlist("orden")

                n = len(row_ids)
                for i in range(n):
                    rid = int(row_ids[i] or 0)
                    if rid <= 0:
                        continue
                    chofer = _clean_text(choferes[i] if i < len(choferes) else "")
                    vehiculo = _clean_text(vehiculos[i] if i < len(vehiculos) else "")
                    destino = _clean_text(destinos[i] if i < len(destinos) else "")
                    solicitante = _clean_text(solicitantes[i] if i < len(solicitantes) else "")
                    hora = _clean_text(horas[i] if i < len(horas) else "")
                    orden = int((ordenes[i] if i < len(ordenes) else "999") or 999)
                    con.execute(
                        """
                        UPDATE asignaciones_simples_diario
                        SET chofer=?,
                            vehiculo=?,
                            destino=?,
                            solicitante=?,
                            hora_llegada_aprox=?,
                            orden=?,
                            actualizado_en=datetime('now')
                        WHERE id=? AND fecha=?
                        """,
                        (chofer, vehiculo, destino, solicitante, hora, orden, rid, fecha),
                    )
                con.commit()
                flash("Diario guardado.", "success")

            elif action == "guardar_ultimo":
                rid = int(request.form.get("row_id") or 0)
                if rid > 0:
                    con.execute(
                        """
                        UPDATE asignaciones_simples_rotacion_ultimo
                        SET fecha=?,
                            ultimo_asignado=?
                        WHERE id=?
                        """,
                        (
                            _clean_text(request.form.get("fila_fecha")),
                            _clean_text(request.form.get("fila_asignado")),
                            rid,
                        ),
                    )
                    con.commit()
                    flash("Fila de ultimo asignado actualizada.", "success")

            elif action == "guardar_proximo":
                rid = int(request.form.get("row_id") or 0)
                if rid > 0:
                    con.execute(
                        """
                        UPDATE asignaciones_simples_rotacion_proximo
                        SET fecha=?,
                            proximo_asignado=?
                        WHERE id=?
                        """,
                        (
                            _clean_text(request.form.get("fila_fecha")),
                            _clean_text(request.form.get("fila_asignado")),
                            rid,
                        ),
                    )
                    con.commit()
                    flash("Fila de proximo asignado actualizada.", "success")

            elif action == "guardar_referencia":
                rid = int(request.form.get("row_id") or 0)
                if rid > 0:
                    orden = int(request.form.get("orden") or 999)
                    chofer = _clean_text(request.form.get("chofer"))
                    con.execute(
                        """
                        UPDATE asignaciones_simples_referencia
                        SET orden=?, chofer=?
                        WHERE id=?
                        """,
                        (orden, chofer, rid),
                    )
                    con.commit()
                    flash("Referencia actualizada.", "success")

            return redirect(url_for("asignaciones_simple_home", fecha=fecha))
        finally:
            con.close()

    @app.route("/asignaciones-simple/limpiar-dia", methods=["POST"], endpoint="asignaciones_simple_limpiar_dia")
    def asignaciones_simple_limpiar_dia():
        if not _can_access():
            return _deny()
        con = get_db()
        try:
            _ensure_schema(con)
            fecha = _clean_text(request.form.get("fecha")) or _today_iso()
            _reset_diario_for_fecha(con, fecha)
            flash("Diario reiniciado para la fecha seleccionada.", "success")
            return redirect(url_for("asignaciones_simple_home", fecha=fecha))
        finally:
            con.close()
