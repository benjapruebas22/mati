import unicodedata
from datetime import date, datetime
from statistics import median

from flask import request, redirect, url_for, flash, render_template, session

from . import bp


def register_vehiculos_control(bp, get_db_connection, ensure_cols, rebuild_eventos_vehiculos):
    ROLE_CHOFER_AUTORIZADO = "chofer_autorizado"

    def _ensure_viajes_operativo_cols(conn):
        ensure_cols(conn, "viajes", [
            ("hora_salida", "TEXT"),
            ("hora_regreso_estimada", "TEXT"),
        ])
        conn.commit()

    def _normalize_text(value):
        txt = str(value or "").strip().lower()
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        return " ".join(txt.split())

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
        if role != ROLE_CHOFER_AUTORIZADO:
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
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
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

    @bp.route("/vehiculos/control_diario", methods=["GET", "POST"], endpoint="vehiculos_control_diario")
    def vehiculos_control_diario():
        conn = get_db_connection()
        _ensure_viajes_operativo_cols(conn)
        role = session.get("role") or ""
        is_autorizado = role == ROLE_CHOFER_AUTORIZADO

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
        user_name = (session.get("full_name") or session.get("username") or "").strip()
        if is_autorizado:
            user_chofer_id = _current_user_chofer_id(conn)
            if user_chofer_id:
                choferes = conn.execute(
                    "SELECT id, agente FROM agentes_intendencia WHERE id = ?",
                    (user_chofer_id,),
                ).fetchall()

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
                vc.estado, vc.tramo
            FROM viajes vc
            LEFT JOIN vehiculos v ON v.patente = vc.patente
            LEFT JOIN agentes_intendencia c ON c.id = vc.chofer_id
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

        refs_destino = {}
        refs_vehiculo = {}
        refs_vehiculo_destino = {}
        for v in viajes:
            estado_u = (v.get("estado") or "").strip().upper()
            if estado_u != "CERRADO":
                continue
            destino = (v.get("destino_nombre") or "").strip()
            if not destino:
                continue
            try:
                km_v = float(v.get("recorrido_km") or 0)
            except Exception:
                km_v = 0.0
            if km_v <= 0:
                continue
            pat = (v.get("patente") or "").strip().upper()
            dkey = _normalize_text(destino)
            refs_destino.setdefault(dkey, []).append(km_v)
            if pat:
                refs_vehiculo.setdefault(pat, []).append(km_v)
                refs_vehiculo_destino.setdefault((pat, dkey), []).append(km_v)

        def _build_stats(src):
            out = {}
            for key, vals in src.items():
                if not vals:
                    continue
                out[key] = {
                    "km_ref": float(median(vals)),
                    "muestras": len(vals),
                }
            return out

        ref_stats_destino = _build_stats(refs_destino)
        ref_stats_vehiculo = _build_stats(refs_vehiculo)
        ref_stats_vehiculo_destino = _build_stats(refs_vehiculo_destino)

        for v in viajes:
            v["km_check_label"] = "-"
            v["km_check_class"] = "km-none"
            v["km_check_hint"] = ""
            v["km_ref"] = None
            v["km_ref_n"] = 0

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

            pat = (v.get("patente") or "").strip().upper()
            dkey = _normalize_text(destino)
            ref = None
            ref_from = ""
            if pat:
                r_vd = ref_stats_vehiculo_destino.get((pat, dkey))
                if r_vd and int(r_vd.get("muestras") or 0) >= 2:
                    ref = r_vd
                    ref_from = "vehiculo+destino"
            if ref is None and pat:
                r_v = ref_stats_vehiculo.get(pat)
                if r_v and int(r_v.get("muestras") or 0) >= 3:
                    ref = r_v
                    ref_from = "vehiculo"
            if ref is None:
                r_d = ref_stats_destino.get(dkey)
                if r_d and int(r_d.get("muestras") or 0) >= 2:
                    ref = r_d
                    ref_from = "destino"
            if not ref:
                v["km_check_label"] = "Sin base"
                v["km_check_hint"] = "Sin historial suficiente para comparar"
                continue

            km_ref = float(ref.get("km_ref") or 0)
            muestras = int(ref.get("muestras") or 0)
            v["km_ref"] = km_ref
            v["km_ref_n"] = muestras
            low = max(0.0, km_ref * 0.55)
            high = max(km_ref * 1.60, km_ref + 6.0)

            if km_real < low:
                v["km_check_label"] = "Bajo"
                v["km_check_class"] = "km-low"
            elif km_real > high:
                v["km_check_label"] = "Alto"
                v["km_check_class"] = "km-high"
            else:
                v["km_check_label"] = "Razonable"
                v["km_check_class"] = "km-ok"
            v["km_check_hint"] = f"Real {km_real:.1f} km | Ref {km_ref:.1f} km ({muestras}, {ref_from})"

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
