from datetime import date

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for


def register_asignaciones_simple(app, get_db):
    if getattr(app, "_asignaciones_simple_registered", False):
        return
    app._asignaciones_simple_registered = True

    CHOFERES_INTENDENCIA = [
        "Mauro Vea Murguía",
        "Gastón Villagra",
        "Jorge Corbacho",
        "Emiliano P. de la Puente",
    ]
    CHOFERES_AUTORIZADOS = [
        "Leonardo Avilés",
        "Mauricio Zambrano",
        "Mateo Montiel",
        "Julio Daud",
        "Manuel Flores",
        "Marcos Durán",
    ]
    CHOFER_SIN_ASIGNAR = "Sin asignar"
    VEHICULOS_DISPONIBLES = [
        "AF277OA",
        "AB946VK",
        "AE856GD",
        "AE856GE",
        "AG846FR",
    ]
    VEHICULO_BADGE_CLASS = {
        "AF277OA": "vh-marron",
        "AB946VK": "vh-rojo",
        "AE856GD": "vh-gris",
        "AE856GE": "vh-azulpet",
        "AG846FR": "vh-violeta",
    }

    DAILY_DEFAULTS = [
        {
            "orden": 1,
            "chofer": "Leo",
            "vehiculo": "AF277OA",
            "destino": "Palpalá",
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
            "chofer": "Gastón",
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
        (1, "Mauro Vea Murguía"),
        (2, "Gastón Villagra"),
        (3, "Jorge Corbacho"),
        (4, "Emiliano Pérez"),
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

    def _iso_to_ddmmyyyy(iso_value):
        txt = _clean_text(iso_value)
        parts = txt.split("-")
        if len(parts) == 3 and all(parts):
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return txt or "-"

    def _choferes_opts():
        return {
            "sin_asignar": CHOFER_SIN_ASIGNAR,
            "intendencia": CHOFERES_INTENDENCIA,
            "autorizados": CHOFERES_AUTORIZADOS,
        }

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

    def _informe_operativo_por_fecha(con, fecha):
        fecha_txt = _clean_text(fecha)
        if not fecha_txt:
            return {"estado": "Informe pendiente", "url": "", "doc_id": 0}
        try:
            tiene_docs = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='documentos'"
            ).fetchone()
            if not tiene_docs:
                return {"estado": "Informe pendiente", "url": "", "doc_id": 0}
            row = con.execute(
                """
                SELECT id_documento, COALESCE(archivo_url, '') AS archivo_url
                FROM documentos
                WHERE tipo_documento = 'informe'
                  AND COALESCE(fecha, '') = ?
                ORDER BY id_documento DESC
                LIMIT 1
                """,
                (fecha_txt,),
            ).fetchone()
            if not row:
                return {"estado": "Informe pendiente", "url": "", "doc_id": 0}
            doc_id = int(row["id_documento"] or 0)
            archivo_url = _clean_text(row["archivo_url"])
            return {
                "estado": "Informe cargado",
                "url": archivo_url or url_for("sgi_documentacion_informes", edit=doc_id),
                "doc_id": doc_id,
            }
        except Exception:
            return {"estado": "Informe pendiente", "url": "", "doc_id": 0}

    def _next_orden_diario(con, fecha):
        row = con.execute(
            "SELECT COALESCE(MAX(COALESCE(orden,0)),0) AS max_orden FROM asignaciones_simples_diario WHERE fecha=?",
            (fecha,),
        ).fetchone()
        return int((row["max_orden"] if row else 0) or 0) + 1

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

    def _susques_resumen(con):
        _ensure_schema(con)
        _seed_rotacion(con)
        ultimo = con.execute(
            """
            SELECT id, fecha, ultimo_asignado AS chofer
            FROM asignaciones_simples_rotacion_ultimo
            WHERE LOWER(TRIM(viaje_destino)) = 'itinerancia / susques'
            LIMIT 1
            """
        ).fetchone()
        proximo = con.execute(
            """
            SELECT id, fecha, proximo_asignado AS chofer
            FROM asignaciones_simples_rotacion_proximo
            WHERE LOWER(TRIM(viaje_destino)) = 'itinerancia / susques'
            LIMIT 1
            """
        ).fetchone()
        choferes = [
            row["chofer"]
            for row in con.execute(
                """
                SELECT chofer
                FROM asignaciones_simples_referencia
                WHERE COALESCE(activo, 1) = 1 AND TRIM(COALESCE(chofer, '')) <> ''
                ORDER BY COALESCE(orden, 999), id
                """
            ).fetchall()
        ]
        return {
            "ultimo": {
                "fecha": (ultimo["fecha"] if ultimo else "") or "",
                "chofer": (ultimo["chofer"] if ultimo else "") or "",
            },
            "proximo": {
                "fecha": (proximo["fecha"] if proximo else "") or "",
                "chofer": (proximo["chofer"] if proximo else "") or "",
            },
            "choferes": choferes,
        }

    @app.route("/asignaciones-simple/susques/resumen", endpoint="asignaciones_simple_susques_resumen")
    def asignaciones_simple_susques_resumen():
        if not _can_access():
            return jsonify({"ok": False, "error": "Acceso restringido a Intendencia."}), 403
        con = get_db()
        try:
            return jsonify({"ok": True, **_susques_resumen(con)})
        finally:
            con.close()

    @app.route(
        "/asignaciones-simple/susques/guardar",
        methods=["POST"],
        endpoint="asignaciones_simple_susques_guardar",
    )
    def asignaciones_simple_susques_guardar():
        if not _can_access():
            return jsonify({"ok": False, "error": "Acceso restringido a Intendencia."}), 403
        ultimo_fecha = _clean_text(request.form.get("ultimo_fecha"))
        ultimo_chofer = _clean_text(request.form.get("ultimo_chofer"))
        proximo_fecha = _clean_text(request.form.get("proximo_fecha"))
        proximo_chofer = _clean_text(request.form.get("proximo_chofer"))
        for value in (ultimo_fecha, proximo_fecha):
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return jsonify({"ok": False, "error": "La fecha ingresada no es válida."}), 400

        con = get_db()
        try:
            _ensure_schema(con)
            _seed_rotacion(con)
            con.execute(
                """
                UPDATE asignaciones_simples_rotacion_ultimo
                SET fecha=?, ultimo_asignado=?, estado='Realizado'
                WHERE LOWER(TRIM(viaje_destino)) = 'itinerancia / susques'
                """,
                (ultimo_fecha, ultimo_chofer),
            )
            con.execute(
                """
                UPDATE asignaciones_simples_rotacion_proximo
                SET fecha=?, proximo_asignado=?, estado='Programado'
                WHERE LOWER(TRIM(viaje_destino)) = 'itinerancia / susques'
                """,
                (proximo_fecha, proximo_chofer),
            )
            con.commit()
            return jsonify({"ok": True, **_susques_resumen(con)})
        finally:
            con.close()

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
                fecha_humana=_iso_to_ddmmyyyy(fecha),
                diario_rows=diario_rows,
                informe_operativo=_informe_operativo_por_fecha(con, fecha),
                rot_ultimo_rows=rot_ultimo_rows,
                rot_proximo_rows=rot_proximo_rows,
                referencia_rows=referencia_rows,
                vehiculo_badge_class=VEHICULO_BADGE_CLASS,
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
            flash("Día guardado.", "success")
            return redirect(url_for("asignaciones_simple_home", fecha=fecha))
        finally:
            con.close()

    @app.route("/asignaciones-simple/nueva", methods=["GET", "POST"], endpoint="asignaciones_simple_nuevo_diario")
    def asignaciones_simple_nuevo_diario():
        if not _can_access():
            return _deny()
        con = get_db()
        try:
            _ensure_schema(con)
            fecha_ctx = _clean_text(request.values.get("fecha")) or _today_iso()
            if request.method == "POST":
                fecha = _clean_text(request.form.get("fecha")) or fecha_ctx
                con.execute(
                    """
                    INSERT INTO asignaciones_simples_diario(
                        fecha, chofer, vehiculo, destino, solicitante, hora_llegada_aprox,
                        estado, observacion, orden, actualizado_en
                    ) VALUES (?,?,?,?,?,?,?,?,?, datetime('now'))
                    """,
                    (
                        fecha,
                        _clean_text(request.form.get("chofer")) or CHOFER_SIN_ASIGNAR,
                        _clean_text(request.form.get("vehiculo")),
                        _clean_text(request.form.get("destino")),
                        _clean_text(request.form.get("solicitante")),
                        _clean_text(request.form.get("hora_llegada_aprox")),
                        _clean_text(request.form.get("estado")) or "Pendiente",
                        _clean_text(request.form.get("observacion")),
                        _next_orden_diario(con, fecha),
                    ),
                )
                con.commit()
                flash("Asignación diaria creada.", "success")
                return redirect(url_for("asignaciones_simple_home", fecha=fecha))

            row = {
                "id": 0,
                "fecha": fecha_ctx,
                "chofer": CHOFER_SIN_ASIGNAR,
                "vehiculo": "",
                "destino": "",
                "solicitante": "",
                "hora_llegada_aprox": "",
                "estado": "Pendiente",
                "observacion": "",
            }
            return render_template(
                "asignaciones_simple_edit.html",
                tipo="diario",
                row=row,
                fecha_ctx=fecha_ctx,
                titulo="Nueva asignación diaria",
                subtitulo="Carga un nuevo traslado y vuelve a la tabla diaria.",
                daily_estados=DAILY_ESTADOS,
                rot_estados=ROT_ESTADOS,
                choferes_opts=_choferes_opts(),
                vehiculos_disponibles=VEHICULOS_DISPONIBLES,
                is_new=True,
            )
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
                            _clean_text(request.form.get("chofer")) or CHOFER_SIN_ASIGNAR,
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
                    flash("Asignación diaria actualizada.", "success")
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
                    flash("Rotación (último asignado) actualizada.", "success")
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
                    flash("Rotación (próximo asignado) actualizada.", "success")
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
                titulo = "Editar asignación diaria"
                subtitulo = "Completa los datos y guarda para volver al listado principal."
            elif tipo == "ultimo":
                titulo = "Editar rotación último asignado"
                subtitulo = "Actualiza último chofer registrado para ese viaje."
            elif tipo == "proximo":
                titulo = "Editar rotación próximo asignado"
                subtitulo = "Actualiza próximo chofer programado para ese viaje."
            else:
                titulo = "Editar orden de chofer"
                subtitulo = "Ajusta referencia de orden para rotación manual."

            return render_template(
                "asignaciones_simple_edit.html",
                tipo=tipo,
                row=row,
                fecha_ctx=fecha_ctx,
                titulo=titulo,
                subtitulo=subtitulo,
                daily_estados=DAILY_ESTADOS,
                rot_estados=ROT_ESTADOS,
                choferes_opts=_choferes_opts(),
                vehiculos_disponibles=VEHICULOS_DISPONIBLES,
                is_new=False,
            )
        finally:
            con.close()

    @app.route(
        "/asignaciones-simple/eliminar/<string:tipo>/<int:row_id>",
        methods=["POST"],
        endpoint="asignaciones_simple_eliminar",
    )
    def asignaciones_simple_eliminar(tipo, row_id):
        if not _can_access():
            return _deny()
        if tipo != "diario":
            abort(404)
        con = get_db()
        try:
            _ensure_schema(con)
            fecha_ctx = _clean_text(request.values.get("fecha")) or _today_iso()
            con.execute("DELETE FROM asignaciones_simples_diario WHERE id = ?", (row_id,))
            con.commit()
            flash("Asignación diaria eliminada.", "success")
            return redirect(url_for("asignaciones_simple_home", fecha=fecha_ctx))
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
