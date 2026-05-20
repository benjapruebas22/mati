from datetime import date

from flask import abort, flash, redirect, render_template, request, session, url_for


def register_asignaciones_simple(app, get_db):
    if getattr(app, "_asignaciones_simple_registered", False):
        return
    app._asignaciones_simple_registered = True

    DAILY_DEFAULTS = [
        {
            "orden": 1,
            "chofer": "Leo",
            "vehiculo": "AF277OA",
            "destino": "Palpala",
            "solicitante": "",
            "hora_llegada_aprox": "",
            "estado": "Pendiente",
            "observacion": "",
        },
        {
            "orden": 2,
            "chofer": "Manuel",
            "vehiculo": "AE856GD",
            "destino": "",
            "solicitante": "",
            "hora_llegada_aprox": "",
            "estado": "Pendiente",
            "observacion": "",
        },
        {
            "orden": 3,
            "chofer": "Gaston",
            "vehiculo": "AG846FR",
            "destino": "",
            "solicitante": "",
            "hora_llegada_aprox": "",
            "estado": "Pendiente",
            "observacion": "",
        },
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

    DAILY_ESTADOS = ["Pendiente", "Asignado", "Realizado", "Cancelado"]
    ROT_ESTADOS = ["Programado", "Realizado", "Cancelado"]

    def _role() -> str:
        return (session.get("role") or "").strip().lower()

    def _username() -> str:
        return (session.get("username") or "").strip().lower()

    def _can_access() -> bool:
        role = _role()
        user = _username()
        if role in {
            "full",
            "admin",
            "dashboard_vehiculos",
            "dashboard_solo",
            "operativo_clave",
            "int_vehiculos",
            "ejecutivo",
        }:
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
        return str(v or "").strip()

    def _table_cols(con, table):
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r["name"]) for r in rows}

    def _ensure_column(con, table, column, ddl_tail):
        if column not in _table_cols(con, table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_tail}")

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
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                observacion TEXT,
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
                estado TEXT NOT NULL DEFAULT 'Programado',
                observacion TEXT,
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
                estado TEXT NOT NULL DEFAULT 'Programado',
                observacion TEXT,
                orden INTEGER NOT NULL DEFAULT 999
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_simples_referencia(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden INTEGER NOT NULL DEFAULT 999,
                chofer TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                observacion TEXT
            )
            """
        )

        _ensure_column(con, "asignaciones_simples_diario", "estado", "TEXT NOT NULL DEFAULT 'Pendiente'")
        _ensure_column(con, "asignaciones_simples_diario", "observacion", "TEXT")

        _ensure_column(con, "asignaciones_simples_rotacion_ultimo", "estado", "TEXT NOT NULL DEFAULT 'Programado'")
        _ensure_column(con, "asignaciones_simples_rotacion_ultimo", "observacion", "TEXT")

        _ensure_column(con, "asignaciones_simples_rotacion_proximo", "estado", "TEXT NOT NULL DEFAULT 'Programado'")
        _ensure_column(con, "asignaciones_simples_rotacion_proximo", "observacion", "TEXT")

        _ensure_column(con, "asignaciones_simples_referencia", "activo", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(con, "asignaciones_simples_referencia", "observacion", "TEXT")

        con.execute("CREATE INDEX IF NOT EXISTS idx_as_simple_diario_fecha_orden ON asignaciones_simples_diario(fecha, orden)")
        con.commit()

    def _seed_rotacion(con):
        cnt_u = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_rotacion_ultimo").fetchone()["c"] or 0)
        if cnt_u == 0:
            for orden, viaje in ROTACION_VIAJES:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_rotacion_ultimo(
                        viaje_destino, fecha, ultimo_asignado, estado, observacion, orden
                    ) VALUES (?, '', '', 'Programado', '', ?)
                    """,
                    (viaje, orden),
                )

        cnt_p = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_rotacion_proximo").fetchone()["c"] or 0)
        if cnt_p == 0:
            for orden, viaje in ROTACION_VIAJES:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_rotacion_proximo(
                        viaje_destino, fecha, proximo_asignado, estado, observacion, orden
                    ) VALUES (?, '', '', 'Programado', '', ?)
                    """,
                    (viaje, orden),
                )

        cnt_r = int(con.execute("SELECT COUNT(*) AS c FROM asignaciones_simples_referencia").fetchone()["c"] or 0)
        if cnt_r == 0:
            for orden, chofer in REFERENCIA_DEFAULTS:
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_referencia(orden, chofer, activo, observacion)
                    VALUES (?, ?, 1, '')
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
                    fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox,
                    estado, observacion, orden
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    fecha,
                    row["chofer"],
                    row["vehiculo"],
                    row["destino"],
                    row["solicitante"],
                    row["hora_llegada_aprox"],
                    row["estado"],
                    row["observacion"],
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
            SELECT id, fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox,
                   estado, observacion, orden
            FROM asignaciones_simples_diario
            WHERE fecha = ?
            ORDER BY COALESCE(orden,999), id
            """,
            (fecha,),
        ).fetchall()

    def _list_rot_ultimo(con):
        return con.execute(
            """
            SELECT id, viaje_destino, fecha, ultimo_asignado, estado, observacion, orden
            FROM asignaciones_simples_rotacion_ultimo
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    def _list_rot_proximo(con):
        return con.execute(
            """
            SELECT id, viaje_destino, fecha, proximo_asignado, estado, observacion, orden
            FROM asignaciones_simples_rotacion_proximo
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    def _list_referencia(con):
        return con.execute(
            """
            SELECT id, orden, chofer, activo, observacion
            FROM asignaciones_simples_referencia
            ORDER BY COALESCE(orden,999), id
            """
        ).fetchall()

    def _get_row(con, tipo, row_id):
        if tipo == "diario":
            return con.execute(
                """
                SELECT id, fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox,
                       estado, observacion, orden
                FROM asignaciones_simples_diario
                WHERE id=?
                """,
                (row_id,),
            ).fetchone()
        if tipo == "ultimo":
            return con.execute(
                """
                SELECT id, viaje_destino, fecha, ultimo_asignado, estado, observacion, orden
                FROM asignaciones_simples_rotacion_ultimo
                WHERE id=?
                """,
                (row_id,),
            ).fetchone()
        if tipo == "proximo":
            return con.execute(
                """
                SELECT id, viaje_destino, fecha, proximo_asignado, estado, observacion, orden
                FROM asignaciones_simples_rotacion_proximo
                WHERE id=?
                """,
                (row_id,),
            ).fetchone()
        if tipo == "referencia":
            return con.execute(
                """
                SELECT id, orden, chofer, activo, observacion
                FROM asignaciones_simples_referencia
                WHERE id=?
                """,
                (row_id,),
            ).fetchone()
        return None

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

    @app.route("/asignaciones-simple/guardar-dia", methods=["POST"], endpoint="asignaciones_simple_guardar_dia")
    def asignaciones_simple_guardar_dia():
        if not _can_access():
            return _deny()
        con = get_db()
        try:
            _ensure_schema(con)
            fecha = _clean_text(request.form.get("fecha")) or _today_iso()
            _ensure_diario_for_fecha(con, fecha)
            flash("Dia guardado.", "success")
            return redirect(url_for("asignaciones_simple_home", fecha=fecha))
        finally:
            con.close()

    @app.route(
        "/asignaciones-simple/editar/<string:tipo>/<int:row_id>",
        methods=["GET", "POST"],
        endpoint="asignaciones_simple_editar",
    )
    def asignaciones_simple_editar(tipo, row_id):
        if not _can_access():
            return _deny()
        if tipo not in {"diario", "ultimo", "proximo", "referencia"}:
            abort(404)

        con = get_db()
        try:
            _ensure_schema(con)
            _seed_rotacion(con)

            fecha_ctx = _clean_text(request.values.get("fecha")) or _today_iso()
            if tipo == "diario":
                _ensure_diario_for_fecha(con, fecha_ctx)

            row = _get_row(con, tipo, row_id)
            if row is None:
                flash("Registro no encontrado.", "warning")
                return redirect(url_for("asignaciones_simple_home", fecha=fecha_ctx))

            if request.method == "POST":
                if tipo == "diario":
                    nueva_fecha = _clean_text(request.form.get("fecha")) or fecha_ctx
                    con.execute(
                        """
                        UPDATE asignaciones_simples_diario
                        SET fecha=?,
                            chofer=?,
                            vehiculo=?,
                            destino=?,
                            solicitante=?,
                            hora_llegada_aprox=?,
                            estado=?,
                            observacion=?,
                            actualizado_en=datetime('now')
                        WHERE id=?
                        """,
                        (
                            nueva_fecha,
                            _clean_text(request.form.get("chofer")),
                            _clean_text(request.form.get("vehiculo")),
                            _clean_text(request.form.get("destino")),
                            _clean_text(request.form.get("solicitante")),
                            _clean_text(request.form.get("hora_llegada_aprox")),
                            _clean_text(request.form.get("estado")) or "Pendiente",
                            _clean_text(request.form.get("observacion")),
                            row_id,
                        ),
                    )
                    con.commit()
                    flash("Asignacion diaria actualizada.", "success")
                    return redirect(url_for("asignaciones_simple_home", fecha=nueva_fecha))

                if tipo == "ultimo":
                    con.execute(
                        """
                        UPDATE asignaciones_simples_rotacion_ultimo
                        SET viaje_destino=?,
                            fecha=?,
                            ultimo_asignado=?,
                            estado=?,
                            observacion=?
                        WHERE id=?
                        """,
                        (
                            _clean_text(request.form.get("viaje_destino")),
                            _clean_text(request.form.get("fecha")),
                            _clean_text(request.form.get("asignado")),
                            _clean_text(request.form.get("estado")) or "Programado",
                            _clean_text(request.form.get("observacion")),
                            row_id,
                        ),
                    )
                    con.commit()
                    flash("Rotacion (ultimo asignado) actualizada.", "success")
                    return redirect(url_for("asignaciones_simple_home", fecha=fecha_ctx))

                if tipo == "proximo":
                    con.execute(
                        """
                        UPDATE asignaciones_simples_rotacion_proximo
                        SET viaje_destino=?,
                            fecha=?,
                            proximo_asignado=?,
                            estado=?,
                            observacion=?
                        WHERE id=?
                        """,
                        (
                            _clean_text(request.form.get("viaje_destino")),
                            _clean_text(request.form.get("fecha")),
                            _clean_text(request.form.get("asignado")),
                            _clean_text(request.form.get("estado")) or "Programado",
                            _clean_text(request.form.get("observacion")),
                            row_id,
                        ),
                    )
                    con.commit()
                    flash("Rotacion (proximo asignado) actualizada.", "success")
                    return redirect(url_for("asignaciones_simple_home", fecha=fecha_ctx))

                if tipo == "referencia":
                    try:
                        orden = int(request.form.get("orden") or 999)
                    except Exception:
                        orden = 999
                    activo_raw = _clean_text(request.form.get("activo")).lower()
                    activo = 1 if activo_raw in {"1", "si", "true", "activo"} else 0
                    con.execute(
                        """
                        UPDATE asignaciones_simples_referencia
                        SET orden=?,
                            chofer=?,
                            activo=?,
                            observacion=?
                        WHERE id=?
                        """,
                        (
                            orden,
                            _clean_text(request.form.get("chofer")),
                            activo,
                            _clean_text(request.form.get("observacion")),
                            row_id,
                        ),
                    )
                    con.commit()
                    flash("Referencia de chofer actualizada.", "success")
                    return redirect(url_for("asignaciones_simple_home", fecha=fecha_ctx))

            if tipo == "diario":
                titulo = "Editar asignacion diaria"
                subtitulo = "Completa los datos y guarda para volver al listado principal."
            elif tipo == "ultimo":
                titulo = "Editar rotacion ultimo asignado"
                subtitulo = "Actualiza ultimo chofer registrado para ese viaje."
            elif tipo == "proximo":
                titulo = "Editar rotacion proximo asignado"
                subtitulo = "Actualiza proximo chofer programado para ese viaje."
            else:
                titulo = "Editar orden de chofer"
                subtitulo = "Ajusta referencia de orden para rotacion manual."

            return render_template(
                "asignaciones_simple_edit.html",
                tipo=tipo,
                row=row,
                fecha_ctx=fecha_ctx,
                titulo=titulo,
                subtitulo=subtitulo,
                daily_estados=DAILY_ESTADOS,
                rot_estados=ROT_ESTADOS,
            )
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
