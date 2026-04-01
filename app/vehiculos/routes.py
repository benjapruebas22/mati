import io
import unicodedata
from datetime import date, datetime

import qrcode
from flask import request, redirect, url_for, flash, render_template, session, send_file

from . import bp


def register_vehiculos_control(bp, get_db_connection, ensure_cols, rebuild_eventos_vehiculos):
    ROLE_CHOFER_AUTORIZADO = "chofer_autorizado"
    ROLE_CHOFER_INTENDENCIA = "chofer_intendencia"
    CHOFER_ROLES = {ROLE_CHOFER_AUTORIZADO, ROLE_CHOFER_INTENDENCIA}

    def _ensure_viajes_operativo_cols(conn):
        ensure_cols(conn, "viajes", [
            ("hora_salida", "TEXT"),
            ("hora_regreso_estimada", "TEXT"),
            ("km_ini_informado", "INTEGER DEFAULT 0"),
            ("km_ini_original", "REAL"),
            ("km_ini_informe_en", "TEXT"),
            ("km_ini_informe_por", "INTEGER"),
            ("km_ini_prev_viaje_id", "INTEGER"),
            ("km_ini_prev_chofer_id", "INTEGER"),
        ])
        conn.commit()

    def _normalize_text(value):
        txt = str(value or "").strip().lower()
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        return " ".join(txt.split())

    def _is_driver_role():
        return (session.get("role") or "").strip() in CHOFER_ROLES

    def _can_access_driver_flow():
        # El acceso real al modulo ya lo controla enforce_auth (legacy_app.py)
        # segun permisos por rol. Aqui solo exigimos sesion activa.
        return bool(session.get("user_id"))

    def _is_open_state(value):
        val = _normalize_text(value or "").replace("_", " ")
        return val in {"abierto", "en curso"}

    def _parse_float_local(value):
        txt = str(value or "").strip()
        if not txt:
            return None
        txt = txt.replace(",", ".")
        try:
            return float(txt)
        except Exception:
            return None

    def _open_estado_sql(alias):
        return f"UPPER(REPLACE(TRIM(COALESCE({alias}.estado,'')), '_', ' ')) IN ('ABIERTO', 'EN CURSO')"

    def _get_open_trip_by_patente(conn, patente):
        p = str(patente or "").strip().upper()
        if not p:
            return None
        return conn.execute(
            f"""
            SELECT
                vc.id,
                vc.fecha,
                vc.patente,
                vc.chofer_id,
                vc.personal_id,
                vc.destino_id,
                vc.km_ini,
                vc.km_fin,
                vc.estado,
                v.codigo_interno,
                c.agente AS chofer_nombre,
                ps.nombre_apellido AS personal_nombre,
                d.nombre AS destino_nombre
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            LEFT JOIN personal_sede ps ON ps.id = vc.personal_id
            LEFT JOIN destinos d ON d.id = vc.destino_id
            WHERE UPPER(TRIM(vc.patente)) = ?
              AND {_open_estado_sql("vc")}
            ORDER BY date(vc.fecha) DESC, vc.id DESC
            LIMIT 1
            """,
            (p,),
        ).fetchone()

    def _get_open_trip_by_chofer(conn, chofer_id):
        if not chofer_id:
            return None
        return conn.execute(
            f"""
            SELECT
                vc.id,
                vc.fecha,
                vc.patente,
                vc.chofer_id,
                vc.personal_id,
                vc.destino_id,
                vc.km_ini,
                vc.km_fin,
                vc.estado,
                v.codigo_interno,
                c.agente AS chofer_nombre,
                ps.nombre_apellido AS personal_nombre,
                d.nombre AS destino_nombre
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            LEFT JOIN personal_sede ps ON ps.id = vc.personal_id
            LEFT JOIN destinos d ON d.id = vc.destino_id
            WHERE vc.chofer_id = ?
              AND {_open_estado_sql("vc")}
            ORDER BY date(vc.fecha) DESC, vc.id DESC
            LIMIT 1
            """,
            (chofer_id,),
        ).fetchone()

    def _get_km_ini_from_last_closed(conn, patente):
        p = str(patente or "").strip().upper()
        if not p:
            return 0.0
        row = conn.execute(
            """
            SELECT km_fin, km_ini
            FROM viajes
            WHERE UPPER(TRIM(patente)) = ?
              AND UPPER(REPLACE(TRIM(COALESCE(estado,'')), '_', ' ')) = 'CERRADO'
            ORDER BY date(fecha) DESC, id DESC
            LIMIT 1
            """,
            (p,),
        ).fetchone()
        if not row:
            return 0.0
        km_fin = _parse_float_local(row["km_fin"])
        if km_fin is not None and km_fin >= 0:
            return km_fin
        km_ini = _parse_float_local(row["km_ini"])
        if km_ini is not None and km_ini >= 0:
            return km_ini
        return 0.0

    def _get_last_trip_before_current(conn, patente):
        p = str(patente or "").strip().upper()
        if not p:
            return None
        return conn.execute(
            """
            SELECT id, chofer_id
            FROM viajes
            WHERE UPPER(TRIM(patente)) = ?
            ORDER BY date(fecha) DESC, id DESC
            LIMIT 1
            """,
            (p,),
        ).fetchone()

    def _find_chofer_id_by_name(chofer_rows, *candidates):
        normalized_candidates = [_normalize_text(c) for c in candidates if str(c or "").strip()]
        normalized_candidates = [c for c in normalized_candidates if c]
        if not normalized_candidates:
            return None
        for row in chofer_rows:
            nombre = _normalize_text(row["agente"] if "agente" in row.keys() else row.get("agente"))
            if nombre in normalized_candidates:
                return row["id"] if "id" in row.keys() else row.get("id")
        return None

    def _current_user_chofer_id(conn):
        full_name = (session.get("full_name") or "").strip()
        username = (session.get("username") or "").strip()
        if not full_name and username:
            full_name = username
        if not full_name:
            return None

        row = conn.execute(
            "SELECT id, agente FROM agentes_intendencia WHERE lower(agente) = lower(?)",
            (full_name,),
        ).fetchone()
        if row:
            return row["id"]

        target = _normalize_text(full_name)
        for r in conn.execute("SELECT id, agente FROM agentes_intendencia"):
            if _normalize_text(r["agente"]) == target:
                return r["id"]

        conn.execute(
            "INSERT INTO agentes_intendencia(agente, rubro, activo) VALUES (?,?,1)",
            (full_name, "Chofer autorizado"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM agentes_intendencia WHERE lower(agente) = lower(?)",
            (full_name,),
        ).fetchone()
        return row["id"] if row else None

    def _deny_if_not_owner(conn, viaje_id):
        role = session.get("role") or ""
        if role not in CHOFER_ROLES:
            return None
        user_cid = _current_user_chofer_id(conn)
        user_name = (session.get("full_name") or session.get("username") or "").strip()
        if not user_cid and not user_name:
            return redirect(url_for("access_denied"))
        row = conn.execute(
            """
            SELECT vc.chofer_id, c.agente AS chofer_nombre
            FROM viajes vc
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            WHERE vc.id = ?
            """,
            (viaje_id,),
        ).fetchone()
        if not row:
            return redirect(url_for("access_denied"))
        ok_id = user_cid and row["chofer_id"] == user_cid
        ok_name = user_name and _normalize_text(row["chofer_nombre"] or "") == _normalize_text(user_name)
        if not (ok_id or ok_name):
            return redirect(url_for("access_denied"))
        return None

    def _delete_viaje(conn, viaje_id):
        row = conn.execute("SELECT fecha FROM viajes WHERE id=?", (viaje_id,)).fetchone()
        fecha = row["fecha"] if row else (request.form.get("fecha") or "")
        conn.execute("DELETE FROM viajes WHERE id = ?", (viaje_id,))
        conn.commit()
        return fecha

    @bp.route("/vehiculos", methods=["GET", "POST"], endpoint="vehiculos_home")
    def vehiculos_home():
        return redirect(url_for("vehiculos_control_diario"))

    @bp.route("/viajes/<int:viaje_id>/editar2", methods=["GET", "POST"], endpoint="viaje_editar2")
    def viaje_editar2(viaje_id):
        return redirect(url_for("viaje_editar", viaje_id=viaje_id))

    @bp.route("/vehiculos/viaje/<int:viaje_id>/eliminar", methods=["POST"], endpoint="viaje_eliminar")
    def viaje_eliminar(viaje_id):
        if _is_driver_role():
            return redirect(url_for("access_denied"))
        conn = get_db_connection()

        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        fecha = _delete_viaje(conn, viaje_id)
        conn.close()
        rebuild_eventos_vehiculos()

        flash(f"Viaje #{viaje_id} eliminado.", "success")
        return redirect(url_for("vehiculos_control_diario", fecha=fecha, desde=desde, hasta=hasta))

    @bp.route("/viajes/<int:viaje_id>/cerrar", methods=["GET", "POST"], endpoint="viaje_cerrar")
    def viaje_cerrar(viaje_id):
        conn = get_db_connection()
        deny = _deny_if_not_owner(conn, viaje_id)
        if deny:
            conn.close()
            return deny

        viaje = conn.execute("""
            SELECT
                vc.*,
                v.codigo_interno, v.patente,
                c.agente AS chofer_nombre,
                d.nombre AS destino_nombre
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            LEFT JOIN destinos d ON d.id = vc.destino_id
            WHERE vc.id=?
        """, (viaje_id,)).fetchone()

        if not viaje:
            conn.close()
            flash("Viaje no encontrado.", "error")
            return redirect(url_for("vehiculos_control_diario"))

        if request.method == "POST":
            try:
                km_fin = float(request.form.get("km_fin") or 0)
            except Exception:
                km_fin = 0

            km_ini = float(viaje["km_ini"] or 0)

            if km_fin <= 0:
                conn.close()
                flash("KM final obligatorio.", "error")
                return redirect(url_for("viaje_cerrar", viaje_id=viaje_id))

            if km_fin < km_ini:
                conn.close()
                flash("KM final no puede ser menor que KM inicial.", "error")
                return redirect(url_for("viaje_cerrar", viaje_id=viaje_id))

            recorrido = km_fin - km_ini

            conn.execute("""
                UPDATE viajes
                SET km_fin=?, recorrido_km=?, estado='CERRADO'
                WHERE id=?
            """, (km_fin, recorrido, viaje_id))

            conn.commit()
            conn.close()

            flash(f"✅ Cerrado. Dif KM: {recorrido:.1f}", "success")
            return redirect(url_for("vehiculos_control_diario", fecha=viaje["fecha"]))

        conn.close()
        flash("Cierre manual deshabilitado: usa Editar y completa KM final.", "info")
        return redirect(url_for("viaje_editar", viaje_id=viaje_id, fecha=viaje["fecha"]))

    @bp.route("/vehiculos/viajes/chofer", methods=["GET"], endpoint="viajes_chofer")
    def viajes_chofer():
        if not _can_access_driver_flow():
            return redirect(url_for("access_denied"))

        conn = get_db_connection()
        _ensure_viajes_operativo_cols(conn)

        user_chofer_id = _current_user_chofer_id(conn)
        if not user_chofer_id:
            conn.close()
            return redirect(url_for("access_denied"))

        chofer_row = conn.execute(
            "SELECT id, agente FROM agentes_intendencia WHERE id = ?",
            (user_chofer_id,),
        ).fetchone()
        chofer_nombre = (
            (chofer_row["agente"] if chofer_row else "")
            or (session.get("full_name") or session.get("username") or "")
        ).strip()

        vehiculos_rows = conn.execute(
            """
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE COALESCE(activo,1)=1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()
        vehiculos = [dict(v) for v in vehiculos_rows]

        personal_rows = conn.execute(
            """
            SELECT
                id,
                nombre_apellido,
                dependencia,
                COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
            FROM personal_sede
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre_apellido
            """
        ).fetchall()
        personal = [dict(p) for p in personal_rows]

        destinos_rows = conn.execute(
            """
            SELECT id, nombre
            FROM destinos
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre
            """
        ).fetchall()
        destinos = [dict(d) for d in destinos_rows]

        patentes_activas = {str(v["patente"] or "").strip().upper() for v in vehiculos}
        patente = (request.args.get("patente") or "").strip().upper()
        if patente and patente not in patentes_activas:
            flash("La camioneta seleccionada no esta activa.", "warning")
            patente = ""

        viaje_abierto_chofer = _get_open_trip_by_chofer(conn, user_chofer_id)
        viaje_abierto_chofer = dict(viaje_abierto_chofer) if viaje_abierto_chofer else None

        if not patente and viaje_abierto_chofer:
            patente = str(viaje_abierto_chofer.get("patente") or "").strip().upper()

        viaje_abierto_patente = _get_open_trip_by_patente(conn, patente) if patente else None
        viaje_abierto_patente = dict(viaje_abierto_patente) if viaje_abierto_patente else None

        viaje_abierto_actual = None
        bloqueo_inicio = ""

        if viaje_abierto_patente:
            if str(viaje_abierto_patente.get("chofer_id") or "") == str(user_chofer_id):
                viaje_abierto_actual = viaje_abierto_patente
            else:
                chofer_ocupado = (viaje_abierto_patente.get("chofer_nombre") or "otro chofer").strip()
                bloqueo_inicio = f"La camioneta {patente} ya esta ocupada por {chofer_ocupado}."

        if not bloqueo_inicio and viaje_abierto_chofer:
            patente_abierta = str(viaje_abierto_chofer.get("patente") or "").strip().upper()
            if patente and patente_abierta and patente_abierta != patente:
                bloqueo_inicio = f"Tenes un viaje abierto en {patente_abierta}. Finalizalo para iniciar otro."

        km_ini_sugerido = 0.0
        if viaje_abierto_actual:
            km_ini_sugerido = _parse_float_local(viaje_abierto_actual.get("km_ini")) or 0.0
        elif patente:
            km_ini_sugerido = _get_km_ini_from_last_closed(conn, patente)

        can_start = bool(patente) and not viaje_abierto_actual and not bloqueo_inicio

        conn.close()
        return render_template(
            "vehiculos_viaje_chofer.html",
            chofer_id=user_chofer_id,
            chofer_nombre=chofer_nombre,
            vehiculos=vehiculos,
            personal=personal,
            destinos=destinos,
            patente_seleccionada=patente,
            km_ini_sugerido=km_ini_sugerido,
            bloqueo_inicio=bloqueo_inicio,
            can_start=can_start,
            viaje_abierto_actual=viaje_abierto_actual,
            viaje_abierto_chofer=viaje_abierto_chofer,
        )

    @bp.route("/vehiculos/viajes/chofer/iniciar", methods=["POST"], endpoint="viajes_chofer_iniciar")
    def viajes_chofer_iniciar():
        if not _can_access_driver_flow():
            return redirect(url_for("access_denied"))

        patente = (request.form.get("patente") or "").strip().upper()
        personal_id_txt = (request.form.get("personal_id") or "").strip()
        destino_id_txt = (request.form.get("destino_id") or "").strip()

        conn = get_db_connection()
        _ensure_viajes_operativo_cols(conn)

        user_chofer_id = _current_user_chofer_id(conn)
        if not user_chofer_id:
            conn.close()
            return redirect(url_for("access_denied"))

        if not patente:
            conn.close()
            flash("Selecciona una camioneta para iniciar el viaje.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer"))

        vehiculo = conn.execute(
            """
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE UPPER(TRIM(patente)) = ?
              AND COALESCE(activo,1)=1
            LIMIT 1
            """,
            (patente,),
        ).fetchone()
        if not vehiculo:
            conn.close()
            flash("La camioneta seleccionada no esta activa.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer"))

        if not personal_id_txt or not destino_id_txt:
            conn.close()
            flash("Debes seleccionar persona y destino.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        try:
            personal_id = int(personal_id_txt)
            destino_id = int(destino_id_txt)
        except Exception:
            conn.close()
            flash("Persona o destino invalido.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        personal_row = conn.execute(
            """
            SELECT
                id,
                dependencia,
                COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
            FROM personal_sede
            WHERE id = ?
              AND COALESCE(activo,1)=1
            LIMIT 1
            """,
            (personal_id,),
        ).fetchone()
        if not personal_row:
            conn.close()
            flash("La persona seleccionada no esta disponible.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        destino_row = conn.execute(
            """
            SELECT id
            FROM destinos
            WHERE id = ?
              AND COALESCE(activo,1)=1
            LIMIT 1
            """,
            (destino_id,),
        ).fetchone()
        if not destino_row:
            conn.close()
            flash("El destino seleccionado no esta disponible.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        abierto_patente = _get_open_trip_by_patente(conn, patente)
        if abierto_patente:
            abierto_patente = dict(abierto_patente)
            if str(abierto_patente.get("chofer_id") or "") == str(user_chofer_id):
                flash("Ya tienes un viaje abierto con esta camioneta.", "warning")
            else:
                chofer_ocupado = (abierto_patente.get("chofer_nombre") or "otro chofer").strip()
                flash(f"La camioneta {patente} esta ocupada por {chofer_ocupado}.", "warning")
            conn.close()
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        abierto_chofer = _get_open_trip_by_chofer(conn, user_chofer_id)
        if abierto_chofer:
            abierto_chofer = dict(abierto_chofer)
            patente_abierta = str(abierto_chofer.get("patente") or "").strip().upper()
            conn.close()
            flash(f"Ya tienes un viaje abierto en {patente_abierta}. Finalizalo primero.", "warning")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente_abierta or patente))

        km_ini_sugerido = _get_km_ini_from_last_closed(conn, patente)
        km_ini = km_ini_sugerido
        km_ini_informado = 0
        km_ini_original = None
        km_ini_informe_en = None
        km_ini_informe_por = None
        km_ini_prev_viaje_id = None
        km_ini_prev_chofer_id = None

        km_ini_reportado_txt = (request.form.get("km_ini_reportado_valor") or "").strip()
        if km_ini_reportado_txt:
            km_ini_reportado = _parse_float_local(km_ini_reportado_txt)
            if km_ini_reportado is None or km_ini_reportado < 0:
                conn.close()
                flash("KM informado invalido.", "warning")
                return redirect(url_for("vehiculos.viajes_chofer", patente=patente))
            km_ini = km_ini_reportado
            if abs(km_ini_reportado - (km_ini_sugerido or 0.0)) > 0.0001:
                prev_trip = _get_last_trip_before_current(conn, patente)
                km_ini_informado = 1
                km_ini_original = km_ini_sugerido
                km_ini_informe_en = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                km_ini_informe_por = user_chofer_id
                km_ini_prev_viaje_id = prev_trip["id"] if prev_trip else None
                km_ini_prev_chofer_id = prev_trip["chofer_id"] if prev_trip else None

        fecha = date.today().strftime("%Y-%m-%d")

        row_tramo = conn.execute(
            """
            SELECT MAX(tramo) AS t
            FROM viajes
            WHERE fecha = ? AND patente = ?
            """,
            (fecha, patente),
        ).fetchone()
        ultimo_tramo = row_tramo["t"] if row_tramo and row_tramo["t"] is not None else 0
        tramo = int(ultimo_tramo) + 1

        dependencia = personal_row["dependencia"] or ""
        sector = personal_row["sede"] or ""
        obs = (request.form.get("observaciones") or "").strip()

        conn.execute(
            """
            INSERT INTO viajes
            (fecha, patente, chofer_id, destino_id,
             personal_id, sector, dependencia,
             km_ini, km_fin, recorrido_km,
             observaciones, estado, tramo,
             hora_salida, hora_regreso_estimada,
             km_ini_informado, km_ini_original,
             km_ini_informe_en, km_ini_informe_por,
             km_ini_prev_viaje_id, km_ini_prev_chofer_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fecha,
                patente,
                user_chofer_id,
                destino_id,
                personal_id,
                sector,
                dependencia,
                km_ini,
                None,
                0.0,
                obs,
                "ABIERTO",
                tramo,
                datetime.now().strftime("%H:%M"),
                "",
                km_ini_informado,
                km_ini_original,
                km_ini_informe_en,
                km_ini_informe_por,
                km_ini_prev_viaje_id,
                km_ini_prev_chofer_id,
            ),
        )

        conn.commit()
        conn.close()
        rebuild_eventos_vehiculos()

        flash("Viaje iniciado.", "success")
        return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

    @bp.route(
        "/vehiculos/viajes/chofer/<int:viaje_id>/finalizar",
        methods=["POST"],
        endpoint="viajes_chofer_finalizar",
    )
    def viajes_chofer_finalizar(viaje_id):
        if not _can_access_driver_flow():
            return redirect(url_for("access_denied"))

        conn = get_db_connection()
        _ensure_viajes_operativo_cols(conn)

        deny = _deny_if_not_owner(conn, viaje_id)
        if deny:
            conn.close()
            return deny

        viaje = conn.execute(
            """
            SELECT
                vc.id,
                vc.fecha,
                vc.patente,
                vc.chofer_id,
                vc.km_ini,
                vc.estado,
                v.codigo_interno
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            WHERE vc.id = ?
            """,
            (viaje_id,),
        ).fetchone()
        if not viaje:
            conn.close()
            flash("Viaje no encontrado.", "error")
            return redirect(url_for("vehiculos.viajes_chofer"))

        patente = str(viaje["patente"] or "").strip().upper()
        if not _is_open_state(viaje["estado"]):
            conn.close()
            flash("El viaje ya se encuentra cerrado.", "info")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        km_fin = _parse_float_local(request.form.get("km_fin") or "")
        if km_fin is None or km_fin <= 0:
            conn.close()
            flash("KM final obligatorio.", "error")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        km_ini = _parse_float_local(viaje["km_ini"]) or 0.0
        if km_fin < km_ini:
            conn.close()
            flash("KM final no puede ser menor que KM inicial.", "error")
            return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

        recorrido = km_fin - km_ini
        conn.execute(
            """
            UPDATE viajes
            SET km_fin = ?, recorrido_km = ?, estado = 'CERRADO'
            WHERE id = ?
            """,
            (km_fin, recorrido, viaje_id),
        )
        conn.commit()
        conn.close()
        rebuild_eventos_vehiculos()

        flash(f"Viaje finalizado. Dif KM: {recorrido:.1f}", "success")
        return redirect(url_for("vehiculos.viajes_chofer", patente=patente))

    @bp.route("/vehiculos/qr", methods=["GET"], endpoint="vehiculos_qr")
    def vehiculos_qr():
        if _is_driver_role():
            return redirect(url_for("access_denied"))

        conn = get_db_connection()
        vehiculos_rows = conn.execute(
            """
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE COALESCE(activo,1)=1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()
        conn.close()

        qr_items = []
        for row in vehiculos_rows:
            patente = str(row["patente"] or "").strip().upper()
            if not patente:
                continue
            qr_items.append(
                {
                    "patente": patente,
                    "codigo_interno": row["codigo_interno"] or "-",
                    "target_url": url_for("vehiculos.viajes_chofer", patente=patente, _external=True),
                    "qr_png_url": url_for("vehiculos.vehiculos_qr_png", patente=patente),
                }
            )

        return render_template("vehiculos_qr.html", qr_items=qr_items)

    @bp.route("/vehiculos/qr/<patente>.png", methods=["GET"], endpoint="vehiculos_qr_png")
    def vehiculos_qr_png(patente):
        if _is_driver_role():
            return redirect(url_for("access_denied"))

        patente_norm = str(patente or "").strip().upper()
        conn = get_db_connection()
        row = conn.execute(
            """
            SELECT patente
            FROM vehiculos
            WHERE UPPER(TRIM(patente)) = ?
              AND COALESCE(activo,1)=1
            LIMIT 1
            """,
            (patente_norm,),
        ).fetchone()
        conn.close()

        if not row:
            flash("La camioneta solicitada no existe o no esta activa.", "warning")
            return redirect(url_for("vehiculos.vehiculos_qr"))

        target_url = url_for("vehiculos.viajes_chofer", patente=patente_norm, _external=True)
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")

        stream = io.BytesIO()
        image.save(stream, format="PNG")
        stream.seek(0)
        return send_file(
            stream,
            mimetype="image/png",
            as_attachment=False,
            download_name=f"qr_{patente_norm}.png",
        )

    @bp.route("/vehiculos/control_diario", methods=["GET", "POST"], endpoint="vehiculos_control_diario")
    def vehiculos_control_diario():
        role = session.get("role") or ""
        if role in CHOFER_ROLES:
            patente_redirect = (request.values.get("patente") or "").strip().upper()
            if patente_redirect:
                return redirect(url_for("vehiculos.viajes_chofer", patente=patente_redirect))
            return redirect(url_for("vehiculos.viajes_chofer"))

        conn = get_db_connection()
        _ensure_viajes_operativo_cols(conn)
        is_autorizado = role in CHOFER_ROLES

        fecha_param = (request.args.get("fecha") or date.today().strftime("%Y-%m-%d")).strip()

        vehiculos = conn.execute("""
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE activo=1
            ORDER BY codigo_interno, patente
        """).fetchall()

        choferes = conn.execute("""
            SELECT id, agente
            FROM agentes_intendencia
            WHERE COALESCE(activo,1)=1
              AND (rubro='choferes' OR lower(rubro)='chofer autorizado')
            ORDER BY agente
        """).fetchall()

        user_chofer_id = None
        default_chofer_id = None
        default_chofer_nombre = ""
        user_name = (session.get("full_name") or session.get("username") or "").strip()
        username = (session.get("username") or "").strip()
        if is_autorizado:
            user_chofer_id = _current_user_chofer_id(conn)
            if user_chofer_id:
                choferes = conn.execute(
                    "SELECT id, agente FROM agentes_intendencia WHERE id = ?",
                    (user_chofer_id,),
                ).fetchall()
            default_chofer_id = user_chofer_id
        else:
            default_chofer_id = _find_chofer_id_by_name(choferes, user_name, username)

        if default_chofer_id:
            for c in choferes:
                cid = c["id"] if "id" in c.keys() else c.get("id")
                if str(cid) == str(default_chofer_id):
                    default_chofer_nombre = c["agente"] if "agente" in c.keys() else c.get("agente") or ""
                    break

        personal = conn.execute("""
            SELECT
                id,
                nombre_apellido,
                dependencia,
                COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
            FROM personal_sede
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre_apellido
        """).fetchall()

        destinos = conn.execute("""
            SELECT id, nombre
            FROM destinos
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre
        """).fetchall()

        if request.method == "POST":
            fecha = (request.form.get("fecha") or fecha_param).strip()

            patente = (request.form.get("patente") or "").strip()
            chofer_id = request.form.get("chofer_id") or None
            if is_autorizado:
                if not user_chofer_id:
                    user_chofer_id = _current_user_chofer_id(conn)
                if not user_chofer_id:
                    conn.close()
                    return redirect(url_for("access_denied"))
                chofer_id = str(user_chofer_id)
            elif not chofer_id and default_chofer_id:
                chofer_id = str(default_chofer_id)
            destino_id = request.form.get("destino_id") or None
            personal_id = request.form.get("personal_id") or None

            km_ini_txt = (request.form.get("km_ini") or "").strip()
            km_fin_txt = (request.form.get("km_fin") or "").strip()

            def parse_float(value):
                try:
                    return float(value)
                except Exception:
                    return None

            km_ini = parse_float(km_ini_txt) if km_ini_txt else 0.0
            km_fin = parse_float(km_fin_txt) if km_fin_txt else 0.0

            if km_ini is None or km_fin is None:
                flash("KM invalido: usa solo numeros.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_control_diario", fecha=fecha))

            if km_ini < 0 or km_fin < 0:
                flash("KM invalido: no puede ser negativo.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_control_diario", fecha=fecha))

            if km_fin_txt and not km_ini_txt:
                flash("Para cargar KM final, completa KM inicial.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_control_diario", fecha=fecha))

            if not patente:
                flash("❌ Falta seleccionar vehículo.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_control_diario", fecha=fecha))

            if km_fin > 0 and km_ini > 0 and km_fin < km_ini:
                flash("❌ Error: el KM final no puede ser menor al KM inicial.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_control_diario", fecha=fecha))

            estado = "CERRADO" if (km_fin and km_fin > 0) else "ABIERTO"

            recorrido_km = (km_fin - km_ini) if (km_fin > 0 and km_ini > 0 and km_fin >= km_ini) else 0.0
            obs = (request.form.get("observaciones") or "").strip()

            row_tramo = conn.execute("""
                SELECT MAX(tramo) AS t
                FROM viajes
                WHERE fecha = ? AND patente = ?
            """, (fecha, patente)).fetchone()

            ultimo_tramo = row_tramo["t"] if row_tramo and row_tramo["t"] is not None else 0
            tramo = int(ultimo_tramo) + 1

            sector = ""
            dependencia = ""
            if personal_id:
                pr = conn.execute("""
                    SELECT
                        dependencia,
                        COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
                    FROM personal_sede
                    WHERE id = ?
                """, (personal_id,)).fetchone()
                if pr:
                    dependencia = pr["dependencia"] or ""
                    sector = pr["sede"] or ""

            conn.execute("""
                INSERT INTO viajes
                (fecha, patente, chofer_id, destino_id,
                 personal_id, sector, dependencia,
                 km_ini, km_fin, recorrido_km,
                 observaciones, estado, tramo,
                 hora_salida, hora_regreso_estimada)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fecha, patente, chofer_id, destino_id,
                personal_id, sector, dependencia,
                km_ini, km_fin, recorrido_km,
                obs, estado, tramo,
                "", ""
            ))

            conn.commit()
            conn.close()
            rebuild_eventos_vehiculos()

            flash("✅ Tramo guardado.", "success")
            return redirect(url_for("vehiculos_control_diario", fecha=fecha))

        viajes_sql = """
            SELECT
                vc.id,
                ROW_NUMBER() OVER (ORDER BY date(vc.fecha) ASC, vc.id ASC) AS nro,
                vc.fecha, v.codigo_interno, vc.patente, vc.chofer_id,
                c.agente AS chofer_nombre,
                ps.nombre_apellido AS agente_nombre,
                vc.sector, vc.dependencia,
                d.nombre AS destino_nombre,
                vc.km_ini, vc.km_fin,
                COALESCE(vc.recorrido_km, 0) AS recorrido_km,
                vc.estado, vc.tramo,
                COALESCE(vc.km_ini_informado, 0) AS km_ini_informado,
                vc.km_ini_original,
                vc.km_ini_informe_en,
                vc.km_ini_prev_chofer_id,
                cprev.agente AS km_ini_prev_chofer_nombre
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            LEFT JOIN agentes_intendencia cprev ON cprev.id = vc.km_ini_prev_chofer_id
            LEFT JOIN personal_sede ps ON ps.id = vc.personal_id
            LEFT JOIN destinos d ON d.id = vc.destino_id
        """
        params = []
        if is_autorizado:
            if user_chofer_id and user_name:
                viajes_sql += " WHERE (vc.chofer_id = ? OR lower(c.agente) = lower(?))"
                params.extend([user_chofer_id, user_name])
            elif user_chofer_id:
                viajes_sql += " WHERE vc.chofer_id = ?"
                params.append(user_chofer_id)
            elif user_name:
                viajes_sql += " WHERE lower(c.agente) = lower(?)"
                params.append(user_name)
        viajes_sql += " ORDER BY date(vc.fecha) DESC, vc.id DESC"
        viajes_rows = conn.execute(viajes_sql, params).fetchall()
        viajes = [dict(r) for r in viajes_rows]

        username_now = (session.get("username") or "").strip().lower()
        full_name_now = _normalize_text(session.get("full_name") or "")
        show_km_razonable = username_now in {"mcalderari", "ibaroni"} or full_name_now in {
            "matias calderari",
            "ignacio baroni",
        }

        REFERENCIAS_KM = {
            "san salvador de jujuy": {
                "centro": {"kmMin": 2, "kmMax": 10, "tipo": "urbano"},
                "alto comedero": {"kmMin": 14, "kmMax": 30, "tipo": "urbano"},
                "palpala": {"kmMin": 26, "kmMax": 40, "tipo": "cercano"},
                "perico": {"kmMin": 50, "kmMax": 70, "tipo": "cercano"},
                "san pedro": {"kmMin": 130, "kmMax": 150, "tipo": "ramal"},
                "ledesma": {"kmMin": 230, "kmMax": 260, "tipo": "ramal"},
                "libertador gral. san martin": {"kmMin": 230, "kmMax": 260, "tipo": "ramal"},
                "tilcara": {"kmMin": 170, "kmMax": 190, "tipo": "quebrada"},
                "humahuaca": {"kmMin": 240, "kmMax": 270, "tipo": "quebrada"},
                "abra pampa": {"kmMin": 310, "kmMax": 350, "tipo": "quebrada"},
                "la quiaca": {"kmMin": 560, "kmMax": 620, "tipo": "quebrada"},
                "susques": {"kmMin": 420, "kmMax": 470, "tipo": "puna"},
                "salta": {"kmMin": 240, "kmMax": 280, "tipo": "externo"},
            },
            "san pedro": {
                "san pedro": {"kmMin": 2, "kmMax": 12, "tipo": "urbano"},
                "la mendieta": {"kmMin": 20, "kmMax": 40, "tipo": "ramal"},
                "rodeito": {"kmMin": 30, "kmMax": 50, "tipo": "ramal"},
                "chalican": {"kmMin": 50, "kmMax": 80, "tipo": "ramal"},
                "ledesma": {"kmMin": 60, "kmMax": 90, "tipo": "ramal"},
                "libertador gral. san martin": {"kmMin": 60, "kmMax": 90, "tipo": "ramal"},
                "libertador gral san martin": {"kmMin": 60, "kmMax": 90, "tipo": "ramal"},
                "yuto": {"kmMin": 100, "kmMax": 130, "tipo": "ramal"},
                "santa clara": {"kmMin": 120, "kmMax": 150, "tipo": "ramal"},
                "el talar": {"kmMin": 180, "kmMax": 220, "tipo": "ramal"},
                "palma sola": {"kmMin": 160, "kmMax": 210, "tipo": "ramal"},
                "san salvador de jujuy": {"kmMin": 130, "kmMax": 150, "tipo": "interurbano"},
                "centro": {"kmMin": 130, "kmMax": 150, "tipo": "interurbano"},
            },
        }

        def normalizeDestino(destino):
            txt = _normalize_text(destino or "")
            txt = txt.replace(",", " ").strip()
            txt = " ".join(txt.split())
            alias = {
                "san salvador": "centro",
                "san salvador de jujuy": "centro",
                "centro": "centro",
                "palpala": "palpala",
                "chalican": "chalican",
            }
            return alias.get(txt, txt)

        def normalizeOrigen(origen):
            txt = _normalize_text(origen or "")
            if txt in {"san pedro", "s. pedro"}:
                return "san pedro"
            return "san salvador de jujuy"

        def obtenerOrigenVehiculo(vehiculo):
            pat = (_normalize_text((vehiculo or {}).get("patente") or "") or "").replace(" ", "")
            cod = (_normalize_text((vehiculo or {}).get("codigo_interno") or "") or "").replace(" ", "")
            if pat == "ae856ge" or cod in {"g-02", "g02"}:
                return "san pedro"
            if pat in {"ae856gd", "af277oa", "ag846fr", "ab946vk"} or cod in {"g-01", "g01", "g-03", "g03", "g-04", "g04", "n-01", "n01"}:
                return "san salvador de jujuy"
            return "san salvador de jujuy"

        def obtenerReferenciaKm(origen, destino):
            okey = normalizeOrigen(origen)
            dkey = normalizeDestino(destino)
            return (REFERENCIAS_KM.get(okey) or {}).get(dkey)

        def evaluarKm(difKm, origen, destino):
            ref = obtenerReferenciaKm(origen, destino)
            if not ref:
                return ("Sin ref", "km-none", "Sin referencia para origen/destino")
            km_min = float(ref.get("kmMin") or 0)
            km_max = float(ref.get("kmMax") or 0)
            if difKm < km_min:
                return ("Bajo", "km-low", f"ref {km_min:.1f}-{km_max:.1f} km")
            if difKm > km_max:
                return ("Alto", "km-high", f"ref {km_min:.1f}-{km_max:.1f} km")
            return ("Razonable", "km-ok", f"ref {km_min:.1f}-{km_max:.1f} km")

        for v in viajes:
            v["km_check_label"] = "-"
            v["km_check_class"] = "km-none"
            v["km_check_hint"] = ""
            v["km_ref"] = None
            v["km_ref_n"] = 0
            v["km_ref_txt"] = "ref --"

            estado_u = (v.get("estado") or "").strip().upper()
            if estado_u != "CERRADO":
                continue

            destino = (v.get("destino_nombre") or "").strip()
            if not destino:
                v["km_check_label"] = "Sin destino"
                continue

            try:
                km_real = float(v.get("recorrido_km") or 0)
            except Exception:
                km_real = 0.0

            if km_real <= 0:
                v["km_check_label"] = "Sin km"
                continue

            origen = obtenerOrigenVehiculo(v)
            label, css, hint = evaluarKm(km_real, origen, destino)
            ref = obtenerReferenciaKm(origen, destino)
            v["km_check_label"] = label
            v["km_check_class"] = css
            v["km_check_hint"] = hint
            if ref:
                km_min = float(ref.get("kmMin") or 0)
                km_max = float(ref.get("kmMax") or 0)
                v["km_ref"] = (km_min + km_max) / 2.0
                v["km_ref_n"] = 0
                v["km_ref_txt"] = f"ref {km_min:.1f}-{km_max:.1f} km"

        kpi_sql = """
            SELECT
                COUNT(*) AS tramos,
                ROUND(COALESCE(SUM(vc.recorrido_km), 0), 2) AS km_total
            FROM viajes vc
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
        """
        kpi_params = []
        if is_autorizado:
            if user_chofer_id and user_name:
                kpi_sql += " WHERE (vc.chofer_id = ? OR lower(c.agente) = lower(?))"
                kpi_params.extend([user_chofer_id, user_name])
            elif user_chofer_id:
                kpi_sql += " WHERE vc.chofer_id = ?"
                kpi_params.append(user_chofer_id)
            elif user_name:
                kpi_sql += " WHERE lower(c.agente) = lower(?)"
                kpi_params.append(user_name)
        kpi_control = conn.execute(kpi_sql, kpi_params).fetchone()
        kpi_comb = conn.execute(
            """
            SELECT
                ROUND(COALESCE(SUM(c.importe_real), 0), 2) AS monto_total,
                ROUND(COALESCE(SUM(c.litros), 0), 2) AS litros_total
            FROM combustible c
            """
        ).fetchone()
        kpi_rango = {
            "tramos": int(kpi_control["tramos"] or 0) if kpi_control else 0,
            "km_total": float(kpi_control["km_total"] or 0) if kpi_control else 0.0,
            "monto_total": float(kpi_comb["monto_total"] or 0) if kpi_comb else 0.0,
            "litros_total": float(kpi_comb["litros_total"] or 0) if kpi_comb else 0.0,
        }

        documentos_vinculados_vehiculos = []
        try:
            t_docs = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos'").fetchone()
            t_rel = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos_vehiculos'").fetchone()
            if t_docs and t_rel:
                patentes = sorted({(v["patente"] or "").strip().upper() for v in vehiculos if (v["patente"] or "").strip()})
                if patentes:
                    placeholders = ",".join(["?"] * len(patentes))
                    documentos_vinculados_vehiculos = conn.execute(
                        f"""
                        SELECT
                            d.id_documento,
                            d.titulo,
                            d.tipo_documento,
                            d.estado,
                            d.fecha,
                            d.archivo_url,
                            dv.patente,
                            COALESCE((
                                SELECT GROUP_CONCAT(dt.tag, ', ')
                                FROM documentos_tags dt
                                WHERE dt.id_documento = d.id_documento
                            ), '') AS tags_txt
                        FROM documentos d
                        JOIN documentos_vehiculos dv ON dv.id_documento = d.id_documento
                        WHERE dv.patente IN ({placeholders})
                        ORDER BY COALESCE(d.fecha, d.creado_en) DESC, d.id_documento DESC
                        LIMIT 120
                        """,
                        patentes,
                    ).fetchall()
        except Exception:
            documentos_vinculados_vehiculos = []

        conn.close()

        return render_template(
            "vehiculos_control_diario.html",
            fecha=fecha_param,
            vehiculos=vehiculos,
            choferes=choferes,
            personal=personal,
            destinos=destinos,
            viajes=viajes,
            kpi_rango=kpi_rango,
            documentos_vinculados_vehiculos=documentos_vinculados_vehiculos,
            is_autorizado=is_autorizado,
            user_chofer_id=user_chofer_id,
            default_chofer_id=default_chofer_id,
            default_chofer_nombre=default_chofer_nombre,
            show_km_razonable=show_km_razonable,
        )

    @bp.route("/viajes/<int:viaje_id>/editar", methods=["GET", "POST"], endpoint="viaje_editar")
    def viaje_editar(viaje_id):
        conn = get_db_connection()
        deny = _deny_if_not_owner(conn, viaje_id)
        if deny:
            conn.close()
            return deny
        _ensure_viajes_operativo_cols(conn)

        vehiculos = conn.execute("""
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE activo=1
            ORDER BY codigo_interno, patente
        """).fetchall()

        choferes = conn.execute("""
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro='choferes' AND activo=1
            ORDER BY agente
        """).fetchall()

        personal = conn.execute("""
            SELECT
                id,
                nombre_apellido,
                dependencia,
                COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
            FROM personal_sede
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre_apellido
        """).fetchall()

        destinos = conn.execute("""
            SELECT id, nombre
            FROM destinos
            WHERE activo=1
            ORDER BY nombre
        """).fetchall()

        viaje = conn.execute("""
            SELECT
                vc.*,
                v.codigo_interno,
                c.agente AS chofer_nombre,
                ps.nombre_apellido AS agente_nombre,
                d.nombre AS destino_nombre
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
            LEFT JOIN personal_sede ps ON ps.id = vc.personal_id
            LEFT JOIN destinos d ON d.id = vc.destino_id
            WHERE vc.id=?
        """, (viaje_id,)).fetchone()

        if not viaje:
            conn.close()
            flash("Viaje no encontrado.", "error")
            return redirect(url_for("vehiculos_control_diario"))

        if request.method == "POST":
            fecha = (request.form.get("fecha") or viaje["fecha"] or "").strip()
            patente = (request.form.get("patente") or "").strip()
            chofer_id = request.form.get("chofer_id") or viaje["chofer_id"] or None
            destino_id = request.form.get("destino_id") or viaje["destino_id"] or None
            personal_id = request.form.get("personal_id") or viaje["personal_id"] or None
            obs = (request.form.get("observaciones") or "").strip()

            try:
                km_ini = float((request.form.get("km_ini") or "").strip() or 0)
            except Exception:
                km_ini = 0.0
            try:
                km_fin = float((request.form.get("km_fin") or "").strip() or 0)
            except Exception:
                km_fin = 0.0

            if not fecha or not patente:
                conn.close()
                flash("Falta fecha o vehículo.", "error")
                return redirect(url_for("viaje_editar", viaje_id=viaje_id))

            if km_fin > 0 and km_ini > 0 and km_fin < km_ini:
                conn.close()
                flash("KM final no puede ser menor que KM inicial.", "error")
                return redirect(url_for("viaje_editar", viaje_id=viaje_id))

            recorrido_km = (km_fin - km_ini) if (km_fin > 0 and km_ini > 0 and km_fin >= km_ini) else 0.0

            sector = ""
            dependencia = ""
            if personal_id:
                pr = conn.execute("""
                    SELECT
                        dependencia,
                        COALESCE(NULLIF(TRIM(sede_texto),''), codigo_sede, '') AS sede
                    FROM personal_sede
                    WHERE id=?
                """, (personal_id,)).fetchone()
                if pr:
                    dependencia = pr["dependencia"] or ""
                    sector = pr["sede"] or ""

            estado = "CERRADO" if (km_fin and km_fin > 0) else "ABIERTO"

            conn.execute("""
                UPDATE viajes
                SET fecha=?,
                    patente=?,
                    chofer_id=?,
                    destino_id=?,
                    personal_id=?,
                    sector=?,
                    dependencia=?,
                    km_ini=?,
                    km_fin=?,
                    recorrido_km=?,
                    observaciones=?,
                    estado=?
                WHERE id=?
            """, (
                fecha, patente, chofer_id, destino_id, personal_id,
                sector, dependencia,
                km_ini, km_fin, recorrido_km,
                obs, estado,
                viaje_id
            ))

            conn.commit()
            conn.close()
            rebuild_eventos_vehiculos()
            flash("✅ Viaje actualizado.", "success")
            return redirect(url_for("vehiculos_control_diario", fecha=fecha))

        conn.close()
        return render_template(
            "vehiculos_viaje_editar.html",
            viaje=viaje,
            vehiculos=vehiculos,
            choferes=choferes,
            personal=personal,
            destinos=destinos
        )

    return bp
