from datetime import date, datetime, timedelta
import base64
import binascii
import os
import sqlite3
import unicodedata
import uuid

from flask import request, redirect, url_for, flash, render_template, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename

def register_vehiculos(app, get_db, get_db_connection, ensure_cols, ensure_combustible_columns, rebuild_eventos_vehiculos):
    MAX_LITROS_CARGA = 150.0
    MAX_PRECIO_LITRO = 10000.0
    MAX_REMITO_IMG_BYTES = 4 * 1024 * 1024
    ALLOWED_REMITO_IMG_EXT = {"jpg", "jpeg", "png", "webp"}
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    REMITOS_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "combustible_remitos")
    os.makedirs(REMITOS_UPLOAD_DIR, exist_ok=True)
    ROLE_CHOFER_INTENDENCIA = "chofer_intendencia"
    ROLE_CHOFER_AUTORIZADO = "chofer_autorizado"
    CHOFERES_INTENDENCIA_PERMITIDOS = (
        "Emiliano P de la Puente",
        "Emiliano Perez de la Puente",
        "Ignacio Baroni",
        "Mauro Vea Murguia",
        "Luis Cardozo",
    )
    def _ensure_viajes_operativo_cols(conn):
        # Campos tacticos para tablero operativo (salida y regreso estimado).
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

    def _parse_float_local(value):
        txt = str(value or "").strip()
        if txt == "":
            return None
        txt = txt.replace("$", "").replace(" ", "")
        has_dot = "." in txt
        has_comma = "," in txt
        if has_dot and has_comma:
            # El separador decimal suele ser el ultimo que aparece.
            if txt.rfind(",") > txt.rfind("."):
                txt = txt.replace(".", "").replace(",", ".")
            else:
                txt = txt.replace(",", "")
        elif has_comma:
            txt = txt.replace(",", ".")
        try:
            return float(txt)
        except Exception:
            return None

    def _save_remito_image_from_request(req):
        file_obj = req.files.get("remito_file")
        if file_obj and getattr(file_obj, "filename", ""):
            filename = secure_filename(file_obj.filename or "")
            ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
            if ext not in ALLOWED_REMITO_IMG_EXT:
                raise ValueError("Formato de imagen no valido. Usar JPG, PNG o WEBP.")
            raw = file_obj.read() or b""
            if not raw:
                raise ValueError("La imagen del remito esta vacia.")
            if len(raw) > MAX_REMITO_IMG_BYTES:
                raise ValueError("Imagen muy pesada. Maximo permitido: 4 MB.")
            out_name = f"remito_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
            out_path = os.path.join(REMITOS_UPLOAD_DIR, out_name)
            with open(out_path, "wb") as fh:
                fh.write(raw)
            return out_name

        data_url = (req.form.get("remito_paste_data") or "").strip()
        if data_url:
            if "," not in data_url or not data_url.startswith("data:image/"):
                raise ValueError("Imagen pegada invalida.")
            header, b64_data = data_url.split(",", 1)
            mime = header.split(";")[0].replace("data:image/", "").strip().lower()
            ext = "jpg" if mime == "jpeg" else mime
            if ext not in ALLOWED_REMITO_IMG_EXT:
                raise ValueError("Formato de imagen pegada no valido.")
            try:
                raw = base64.b64decode(b64_data, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("No se pudo leer la imagen pegada.")
            if not raw:
                raise ValueError("La imagen pegada esta vacia.")
            if len(raw) > MAX_REMITO_IMG_BYTES:
                raise ValueError("Imagen pegada muy pesada. Maximo permitido: 4 MB.")
            out_name = f"remito_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
            out_path = os.path.join(REMITOS_UPLOAD_DIR, out_name)
            with open(out_path, "wb") as fh:
                fh.write(raw)
            return out_name

        return None

    def _delete_local_remito_if_exists(value):
        name = str(value or "").strip()
        if not name or name.startswith("http://") or name.startswith("https://"):
            return
        safe = secure_filename(name)
        if not safe:
            return
        path = os.path.join(REMITOS_UPLOAD_DIR, safe)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except Exception:
                pass

    def _resolve_or_create_chofer_id(conn, chofer_id_raw, chofer_nombre_raw):
        cid_txt = str(chofer_id_raw or "").strip()
        if cid_txt:
            try:
                return int(cid_txt)
            except Exception:
                pass

        nombre = str(chofer_nombre_raw or "").strip()
        if not nombre:
            return None

    def _current_user_chofer_id(conn):
        full_name = (session.get("full_name") or "").strip()
        username = (session.get("username") or "").strip()
        if not full_name and username:
            full_name = username
        if not full_name:
            return None

        # match exact (case-insensitive)
        row = conn.execute(
            "SELECT id, agente FROM agentes_intendencia WHERE lower(agente) = lower(?)",
            (full_name,),
        ).fetchone()
        if row:
            return row["id"]

        # match normalized (sin tildes)
        target = _normalize_text(full_name)
        for r in conn.execute("SELECT id, agente FROM agentes_intendencia"):
            if _normalize_text(r["agente"]) == target:
                return r["id"]

        # crear chofer si no existe
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

        row = conn.execute(
            """
            SELECT id
            FROM agentes_intendencia
            WHERE rubro='choferes' AND LOWER(TRIM(agente)) = LOWER(TRIM(?))
            ORDER BY activo DESC, id ASC
            LIMIT 1
            """,
            (nombre,),
        ).fetchone()
        if row:
            if int(row["id"] or 0) > 0:
                return int(row["id"])

        target = _normalize_text(nombre)
        all_rows = conn.execute(
            """
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro='choferes'
            ORDER BY activo DESC, id ASC
            """
        ).fetchall()
        for r in all_rows:
            if _normalize_text(r["agente"]) == target:
                return int(r["id"])

        conn.execute(
            """
            INSERT INTO agentes_intendencia (agente, rubro, activo)
            VALUES (?, 'choferes', 1)
            """,
            (nombre,),
        )
        new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(new_id["id"]) if new_id else None

    @app.route("/vehiculos/nuevo", methods=["GET", "POST"], endpoint="vehiculos_nuevo")
    def vehiculos_nuevo():
        conn = get_db_connection()

        if request.method == "POST":
            patente = request.form.get("patente","").upper().strip()
            codigo  = request.form.get("codigo_interno","").strip()
            tipo    = request.form.get("tipo","G").strip()
            modelo  = request.form.get("modelo","").strip()
            combustible = request.form.get("combustible","gasoil").strip()
            base_ciudad = request.form.get("base_ciudad","").strip() or "San Salvador de Jujuy"
            color_tag   = request.form.get("color_tag","").strip() or "#5B5BEA"

            conn.execute("""
                INSERT OR REPLACE INTO vehiculos
                    (patente, codigo_interno, tipo, modelo, combustible,
                     base_ciudad, color_tag, activo)
                VALUES (?,?,?,?,?,?,?,1)
            """, (patente, codigo, tipo, modelo, combustible, base_ciudad, color_tag))

            # crear estado vacío si no existe
            conn.execute(
                "INSERT OR IGNORE INTO vehiculo_estado(patente) VALUES (?)",
                (patente,)
            )

            conn.commit()
            conn.close()
            flash("✅ Vehículo guardado correctamente.", "success")
            return redirect(url_for("vehiculos_control_diario"))

        conn.close()
        return render_template("vehiculos_form.html", v=None, modo="nuevo")


    @app.route("/vehiculos/estadisticas", methods=["GET"], endpoint="vehiculos_estadisticas2")
    def vehiculos_estadisticas2():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))

        conn = get_db_connection()

        # -------------------------
        # FILTROS
        # -------------------------
        limites = conn.execute("""
            SELECT MIN(date(fecha)) AS desde_min, MAX(date(fecha)) AS hasta_max
            FROM viajes
        """).fetchone()
        desde_def = (limites["desde_min"] if limites and limites["desde_min"] else date.today().strftime("%Y-%m-%d"))
        hasta_def = (limites["hasta_max"] if limites and limites["hasta_max"] else date.today().strftime("%Y-%m-%d"))

        desde = (request.args.get("desde") or desde_def)
        hasta = (request.args.get("hasta") or hasta_def)
        patente = (request.args.get("patente") or "").strip()
        chofer_id = (request.args.get("chofer_id") or "").strip()
        personal_id = (request.args.get("personal_id") or "").strip()

        # -------------------------
        # COMBOS
        # -------------------------
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

        # Personal para "Persona trasladada"
        personal = conn.execute("""
            SELECT
                id,
                nombre_apellido,
                COALESCE(dependencia,'') AS dependencia,
                COALESCE(sede_texto,'')  AS sede_texto,
                (nombre_apellido || ' — ' || COALESCE(dependencia,'')) AS label
            FROM personal_sede
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre_apellido
        """).fetchall()

        # -------------------------
        # WHERE DINÁMICO
        # -------------------------
        where = ["date(v.fecha) BETWEEN date(?) AND date(?)"]
        params = [desde, hasta]

        if patente:
            where.append("v.patente = ?")
            params.append(patente)

        if chofer_id:
            where.append("v.chofer_id = ?")
            params.append(chofer_id)

        if personal_id:
            where.append("v.personal_id = ?")
            params.append(personal_id)

        where_sql = " AND ".join(where)

        # -------------------------
        # KPI (tramos / km / promedio)
        # -------------------------
        row_kpi = conn.execute(f"""
            SELECT
                COALESCE(COUNT(*),0) AS tramos,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km_total,
                CASE
                  WHEN COUNT(*) > 0 THEN COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) * 1.0 / COUNT(*)
                  ELSE 0
                END AS km_prom_tramo
            FROM viajes v
            WHERE {where_sql}
        """, params).fetchone()

        kpi = {
            "tramos": row_kpi["tramos"] if row_kpi else 0,
            "km_total": row_kpi["km_total"] if row_kpi else 0,
            "km_prom_tramo": row_kpi["km_prom_tramo"] if row_kpi else 0,
        }

        # -------------------------
        # KM POR CHOFER (Top 20)
        # -------------------------
        por_chofer = conn.execute(f"""
            SELECT
                COALESCE(a.agente,'(Sin chofer)') AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN agentes_intendencia a ON a.id = v.chofer_id
            WHERE {where_sql}
            GROUP BY COALESCE(a.agente,'(Sin chofer)')
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        # -------------------------
        # KM POR VEHÍCULO (Top 20)
        # -------------------------
        por_vehiculo = conn.execute(f"""
            SELECT
                (COALESCE(ve.codigo_interno,'') || ' — ' || COALESCE(v.patente,'')) AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN vehiculos ve ON ve.patente = v.patente
            WHERE {where_sql}
            GROUP BY v.patente, ve.codigo_interno
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        # -------------------------
        # KM POR PERSONA TRASLADADA (Top 20)
        # -------------------------
        por_persona = conn.execute(f"""
            SELECT
                COALESCE(p.nombre_apellido,'(Sin persona)') AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN personal_sede p ON p.id = v.personal_id
            WHERE {where_sql}
            GROUP BY COALESCE(p.nombre_apellido,'(Sin persona)')
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        conn.close()

        # -------------------------
        # RENDER
        # -------------------------
        return render_template(
            "vehiculos_estadisticas.html",
            desde=desde, hasta=hasta,
            patente=patente, chofer_id=chofer_id, personal_id=personal_id,
            vehiculos=vehiculos, choferes=choferes, personal=personal,
            kpi=kpi,
            por_chofer=por_chofer,
            por_vehiculo=por_vehiculo,
            por_persona=por_persona
        )


    @app.route("/vehiculos/documentacion", methods=["GET", "POST"], endpoint="vehiculos_documentacion")
    def vehiculos_documentacion():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        from datetime import datetime, timedelta

        conn = get_db_connection()
        hoy = date.today()

        if request.method == "POST":
            tipo_form = (request.form.get("tipo_form") or "").strip()

            if tipo_form == "vehiculo_estado":
                patente = (request.form.get("patente") or "").strip()
                if not patente:
                    flash("Falta seleccionar vehículo.", "error")
                    conn.close()
                    return redirect(url_for("vehiculos_documentacion"))

                def _f(name):
                    v = (request.form.get(name) or "").strip()
                    return v if v else None

                conn.execute("INSERT OR IGNORE INTO vehiculo_estado(patente) VALUES (?)", (patente,))
                conn.execute(
                    """
                    UPDATE vehiculo_estado
                    SET ultimo_service=?,
                        proximo_service=?,
                        ultimo_lavado=?,
                        proximo_lavado=?,
                        seguro_inicio=?,
                        seguro_vencimiento=?,
                        rtv_inicio=?,
                        rtv_vencimiento=?
                    WHERE patente=?
                    """,
                    (
                        _f("ultimo_service"),
                        _f("proximo_service"),
                        _f("ultimo_lavado"),
                        _f("proximo_lavado"),
                        _f("seguro_inicio"),
                        _f("seguro_vencimiento"),
                        _f("rtv_inicio"),
                        _f("rtv_vencimiento"),
                        patente,
                    ),
                )
                conn.commit()
                conn.close()
                rebuild_eventos_vehiculos()
                flash("Documentación del vehículo actualizada.", "success")
                return redirect(url_for("vehiculos_documentacion"))

            if tipo_form == "chofer_doc":
                chofer_id = (request.form.get("chofer_id") or "").strip()
                fecha_venc = (request.form.get("carnet_vencimiento") or "").strip()

                if not chofer_id or not fecha_venc:
                    flash("Falta chofer o fecha de vencimiento.", "error")
                    conn.close()
                    return redirect(url_for("vehiculos_documentacion"))

                row = conn.execute(
                    """
                    SELECT id
                    FROM agentes_documentacion
                    WHERE agente_id = ? AND tipo = 'carnet_conducir'
                    ORDER BY fecha_vencimiento DESC, id DESC
                    LIMIT 1
                    """,
                    (chofer_id,),
                ).fetchone()

                if row:
                    conn.execute(
                        """
                        UPDATE agentes_documentacion
                        SET fecha_vencimiento=?, estado='VIGENTE'
                        WHERE id=?
                        """,
                        (fecha_venc, row["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO agentes_documentacion
                            (agente_id, tipo, fecha_vencimiento, observaciones, estado)
                        VALUES (?, 'carnet_conducir', ?, '', 'VIGENTE')
                        """,
                        (chofer_id, fecha_venc),
                    )

                conn.commit()
                conn.close()
                rebuild_eventos_agentes()
                flash("Carnet de conducir actualizado.", "success")
                return redirect(url_for("vehiculos_documentacion"))

        vehiculos = conn.execute(
            """
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE activo=1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()

        estados_raw = conn.execute(
            """
            SELECT
                v.codigo_interno,
                v.patente,
                e.ultimo_service,
                e.proximo_service,
                e.ultimo_lavado,
                e.proximo_lavado,
                e.seguro_inicio,
                e.seguro_vencimiento,
                e.rtv_inicio,
                e.rtv_vencimiento
            FROM vehiculos v
            LEFT JOIN vehiculo_estado e ON e.patente = v.patente
            WHERE v.activo=1
            ORDER BY v.codigo_interno, v.patente
            """
        ).fetchall()

        def _estado_fecha(f):
            if not f:
                return {"fecha": "", "estado": ""}
            try:
                d = datetime.strptime(f, "%Y-%m-%d").date()
            except Exception:
                return {"fecha": f, "estado": "ok"}
            if d < hoy:
                return {"fecha": f, "estado": "vencido"}
            if d <= (hoy + timedelta(days=45)):
                return {"fecha": f, "estado": "pronto"}
            return {"fecha": f, "estado": "ok"}

        def _estado_venc_top(f):
            if not f:
                return {"fecha": "", "estado": ""}
            try:
                d = datetime.strptime(f, "%Y-%m-%d").date()
            except Exception:
                return {"fecha": f, "estado": "ok"}
            if d < hoy:
                return {"fecha": f, "estado": "vencido"}
            if d <= (hoy + timedelta(days=10)):
                return {"fecha": f, "estado": "vencido"}
            return {"fecha": f, "estado": "ok"}

        estados = []
        for r in estados_raw:
            estados.append({
                "codigo_interno": r["codigo_interno"],
                "patente": r["patente"],
                "ultimo_service": r["ultimo_service"] or "",
                "proximo_service": _estado_fecha(r["proximo_service"]),
                "ultimo_lavado": r["ultimo_lavado"] or "",
                "proximo_lavado": _estado_fecha(r["proximo_lavado"]),
                "seguro_vencimiento": _estado_fecha(r["seguro_vencimiento"]),
                "seguro_top": _estado_venc_top(r["seguro_vencimiento"]),
                "rtv_vencimiento": _estado_fecha(r["rtv_vencimiento"]),
                "rtv_top": _estado_venc_top(r["rtv_vencimiento"]),
                "seguro_inicio": r["seguro_inicio"] or "",
                "rtv_inicio": r["rtv_inicio"] or "",
            })

        choferes = conn.execute(
            """
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro='choferes' AND activo=1
            ORDER BY agente
            """
        ).fetchall()

        chofer_docs_raw = conn.execute(
            """
            SELECT
                ai.id,
                ai.agente,
                (
                  SELECT ad.fecha_vencimiento
                  FROM agentes_documentacion ad
                  WHERE ad.agente_id = ai.id
                    AND ad.tipo = 'carnet_conducir'
                  ORDER BY ad.fecha_vencimiento DESC, ad.id DESC
                  LIMIT 1
                ) AS fecha_vencimiento
            FROM agentes_intendencia ai
            WHERE ai.rubro='choferes' AND ai.activo=1
            ORDER BY ai.agente
            """
        ).fetchall()

        chofer_docs = []
        for r in chofer_docs_raw:
            estado = _estado_fecha(r["fecha_vencimiento"] if r["fecha_vencimiento"] else "")
            chofer_docs.append({
                "id": r["id"],
                "agente": r["agente"],
                "fecha_vencimiento": estado["fecha"],
                "estado": estado["estado"],
            })

        veh_vencidos = 0
        veh_pronto = 0
        for r in estados:
            estados_keys = ("proximo_service", "proximo_lavado", "seguro_vencimiento", "rtv_vencimiento")
            has_vencido = any((r[k]["estado"] == "vencido") for k in estados_keys)
            has_pronto = any((r[k]["estado"] == "pronto") for k in estados_keys)
            if has_vencido:
                veh_vencidos += 1
            elif has_pronto:
                veh_pronto += 1

        chofer_vencidos = sum(1 for c in chofer_docs if c["estado"] == "vencido")
        chofer_pronto = sum(1 for c in chofer_docs if c["estado"] == "pronto")

        conn.close()

        return render_template(
            "vehiculos_documentacion.html",
            vehiculos=vehiculos,
            estados=estados,
            choferes=choferes,
            chofer_docs=chofer_docs,
            alertas={
                "vehiculos_vencidos": veh_vencidos,
                "vehiculos_pronto": veh_pronto,
                "choferes_vencidos": chofer_vencidos,
                "choferes_pronto": chofer_pronto,
            },
            hoy=hoy.isoformat(),
        )



    # =========================================================
    # ESTADÍSTICAS
    # =========================================================

    from flask import request, render_template

    @app.route("/vehiculos/estadisticas", methods=["GET"], endpoint="vehiculos_estadisticas")
    def vehiculos_estadisticas():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        conn = get_db_connection()

        # -------------------------
        # FILTROS
        # -------------------------
        limites = conn.execute("""
            SELECT MIN(date(fecha)) AS desde_min, MAX(date(fecha)) AS hasta_max
            FROM viajes
        """).fetchone()
        desde_def = (limites["desde_min"] if limites and limites["desde_min"] else date.today().strftime("%Y-%m-%d"))
        hasta_def = (limites["hasta_max"] if limites and limites["hasta_max"] else date.today().strftime("%Y-%m-%d"))

        desde = (request.args.get("desde") or desde_def)
        hasta = (request.args.get("hasta") or hasta_def)
        patente = (request.args.get("patente") or "").strip()
        chofer_id = (request.args.get("chofer_id") or "").strip()
        personal_id = (request.args.get("personal_id") or "").strip()

        # -------------------------
        # COMBOS
        # -------------------------
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
                COALESCE(dependencia,'') AS dependencia,
                COALESCE(sede_texto,'')  AS sede_texto,
                (nombre_apellido || ' — ' || COALESCE(dependencia,'')) AS label
            FROM personal_sede
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre_apellido
        """).fetchall()

        # -------------------------
        # WHERE DINÁMICO
        # -------------------------
        where = ["date(v.fecha) BETWEEN date(?) AND date(?)"]
        params = [desde, hasta]

        if patente:
            where.append("v.patente = ?")
            params.append(patente)

        if chofer_id:
            where.append("v.chofer_id = ?")
            params.append(chofer_id)

        if personal_id:
            where.append("v.personal_id = ?")
            params.append(personal_id)

        where_sql = " AND ".join(where)

        # -------------------------
        # KPI
        # -------------------------
        row_kpi = conn.execute(f"""
            SELECT
                COALESCE(COUNT(*),0) AS tramos,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km_total,
                CASE
                  WHEN COUNT(*) > 0 THEN COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) * 1.0 / COUNT(*)
                  ELSE 0
                END AS km_prom_tramo
            FROM viajes v
            WHERE {where_sql}
        """, params).fetchone()

        kpi = {
            "tramos": row_kpi["tramos"] if row_kpi else 0,
            "km_total": row_kpi["km_total"] if row_kpi else 0,
            "km_prom_tramo": row_kpi["km_prom_tramo"] if row_kpi else 0,
        }

        # -------------------------
        # KM POR CHOFER (Top 20)
        # -------------------------
        por_chofer = conn.execute(f"""
            SELECT
                COALESCE(a.agente,'(Sin chofer)') AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN agentes_intendencia a ON a.id = v.chofer_id
            WHERE {where_sql}
            GROUP BY COALESCE(a.agente,'(Sin chofer)')
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        # -------------------------
        # KM POR VEHÍCULO (Top 20)
        # -------------------------
        por_vehiculo = conn.execute(f"""
            SELECT
                (COALESCE(ve.codigo_interno,'') || ' — ' || COALESCE(v.patente,'')) AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN vehiculos ve ON ve.patente = v.patente
            WHERE {where_sql}
            GROUP BY v.patente, ve.codigo_interno
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        # -------------------------
        # KM POR PERSONA (Top 20)
        # -------------------------
        por_persona = conn.execute(f"""
            SELECT
                COALESCE(p.nombre_apellido,'(Sin persona)') AS label,
                COALESCE(SUM(COALESCE(v.recorrido_km,0)),0) AS km,
                COALESCE(COUNT(*),0) AS tramos
            FROM viajes v
            LEFT JOIN personal_sede p ON p.id = v.personal_id
            WHERE {where_sql}
            GROUP BY COALESCE(p.nombre_apellido,'(Sin persona)')
            ORDER BY km DESC
            LIMIT 20
        """, params).fetchall()

        conn.close()

        return render_template(
            "vehiculos_estadisticas.html",
            desde=desde, hasta=hasta,
            patente=patente, chofer_id=chofer_id, personal_id=personal_id,
            vehiculos=vehiculos, choferes=choferes, personal=personal,
            kpi=kpi,
            por_chofer=por_chofer,
            por_vehiculo=por_vehiculo,
            por_persona=por_persona

        )

    # -----------------------------------------
    # SOLO VOS: corregir KM INICIAL (sin login)
    # Restricción por IP (tu PC) + localhost
    # -----------------------------------------
    TU_IP = "192.168.100.9"   # CAMBIÁ por la IP REAL de tu PC (la que usan para entrar)

    @app.route("/viajes/<int:viaje_id>/set_km_ini", methods=["POST"], endpoint="viaje_set_km_ini")
    def viaje_set_km_ini(viaje_id):
        ip = request.remote_addr or ""
        if ip not in ("127.0.0.1", "localhost", TU_IP):
            abort(403)

        conn = get_db_connection()
        row = conn.execute("SELECT id, fecha, estado FROM viajes WHERE id=?", (viaje_id,)).fetchone()
        if not row:
            conn.close()
            abort(404)

        try:
            nuevo = float(request.form.get("km_ini") or 0)
        except Exception:
            nuevo = 0

        if nuevo < 0:
            conn.close()
            flash("KM inicial inválido.", "error")
            return redirect(url_for("vehiculos_control_diario", fecha=row["fecha"]))

        # recalcular dif si ya estaba cerrado con km_fin
        r2 = conn.execute("SELECT km_fin FROM viajes WHERE id=?", (viaje_id,)).fetchone()
        km_fin = float(r2["km_fin"] or 0)
        recorrido = (km_fin - nuevo) if km_fin > 0 and km_fin >= nuevo else 0.0

        conn.execute("""
            UPDATE viajes
            SET km_ini=?, recorrido_km=?
            WHERE id=?
        """, (nuevo, recorrido, viaje_id))

        conn.commit()
        conn.close()

        flash("✅ KM inicial actualizado (solo admin).", "success")
        return redirect(url_for("vehiculos_control_diario", fecha=row["fecha"]))


    # =========================================================
    # COMBUSTIBLE
    # =========================================================

    # -------------------------
    # COMBUSTIBLE - PANTALLA PRINCIPAL
    # -------------------------
    @app.route("/vehiculos/combustible", methods=["GET", "POST"], endpoint="vehiculos_combustible")
    def vehiculos_combustible():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        conn = get_db_connection()
        ensure_combustible_columns(conn)

        # --- Combos de la pantalla ---
        vehiculos = conn.execute(
            """
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE activo = 1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()

        choferes = conn.execute(
            """
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro = 'choferes' AND activo = 1
            ORDER BY agente
            """
        ).fetchall()

        # --- Precios actuales desde combustible_precios (nafta / gasoil) ---
        precios = conn.execute(
            """
            SELECT tipo, precio_litro
            FROM combustible_precios
            """
        ).fetchall()

        precio_nafta = 0.0
        precio_gasoil = 0.0
        for row in precios:
            if row["tipo"] == "nafta":
                precio_nafta = float(row["precio_litro"] or 0)
            elif row["tipo"] == "gasoil":
                precio_gasoil = float(row["precio_litro"] or 0)

        # ----------------- AL GUARDAR CARGA -----------------
        if request.method == "POST":
            fecha = request.form.get("fecha")
            patente = request.form.get("patente")
            chofer_id_raw = request.form.get("chofer_id") or ""
            chofer_nombre_raw = request.form.get("chofer_nombre") or ""
            chofer_id = _resolve_or_create_chofer_id(conn, chofer_id_raw, chofer_nombre_raw)

            km_actual_raw = request.form.get("km_actual")
            litros_raw    = request.form.get("litros")
            precio_unit_raw = request.form.get("precio_unit")
            remito       = request.form.get("remito", "").strip()
            importe_real_raw = request.form.get("importe_real")
            obs          = request.form.get("notas", "").strip()

            if not patente:
                flash("Falta seleccionar vehiculo.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            km_actual = _parse_float_local(km_actual_raw or 0)
            litros = _parse_float_local(litros_raw or 0)
            importe_real = _parse_float_local(importe_real_raw or 0)

            if km_actual is None or litros is None or importe_real is None:
                flash("Valores numericos invalidos.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            if km_actual < 0 or litros <= 0 or importe_real < 0:
                flash("Revisa KM, litros e importe (no pueden ser negativos).", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))
            if litros > MAX_LITROS_CARGA:
                flash(f"Litros fuera de rango (max {int(MAX_LITROS_CARGA)} por carga). Revisar formato decimal.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            v_tipo = conn.execute(
                "SELECT combustible FROM vehiculos WHERE patente = ?",
                (patente,),
            ).fetchone()
            tipo = ((v_tipo["combustible"] if v_tipo else "") or "nafta").strip().lower()
            if tipo not in ("nafta", "gasoil"):
                tipo = "nafta"

            precio_unit = _parse_float_local(precio_unit_raw)
            if precio_unit is None or precio_unit <= 0:
                precio_unit = float(precio_nafta or 0) if tipo == "nafta" else float(precio_gasoil or 0)

            if precio_unit <= 0:
                flash("Precio por litro invalido.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))
            if precio_unit > MAX_PRECIO_LITRO:
                flash(f"Precio por litro fuera de rango (max {int(MAX_PRECIO_LITRO)}). Revisar formato decimal.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            # Importe calculado automático
            importe_calculado = round(litros * precio_unit, 2)

            remito_archivo = (request.form.get("remito_url") or "").strip() or None
            if not remito_archivo:
                try:
                    remito_archivo = _save_remito_image_from_request(request)
                except ValueError as e:
                    flash(str(e), "danger")
                    conn.close()
                    return redirect(url_for("vehiculos_combustible"))

            # Guardar en tabla combustible (OJO: usa chofer_id)
            conn.execute(
                """
                INSERT INTO combustible
                (fecha, patente, chofer_id, tipo,
                 km_actual, litros, precio_unit,
                 importe_calculado, importe_real,
                 nro_remito, observaciones, remito_archivo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fecha, patente, chofer_id, tipo,
                    km_actual, litros, precio_unit,
                    importe_calculado, importe_real,
                    remito, obs, remito_archivo,
                ),
            )
            conn.commit()
            conn.close()

            flash("✅ Carga de combustible registrada.", "success")
            return redirect(url_for("vehiculos_combustible"))

        # ----------------- LISTADO ÚLTIMAS CARGAS -----------------
        cargas = conn.execute(
            """
            SELECT
                c.*,
                v.codigo_interno,
                v.patente,
                a.agente AS chofer_nombre
            FROM combustible c
            LEFT JOIN vehiculos v ON v.patente = c.patente
            LEFT JOIN agentes_intendencia a ON a.id = c.chofer_id
            ORDER BY c.fecha DESC, c.id DESC
            LIMIT 50
            """
        ).fetchall()
        resumen_mensual = conn.execute(
            """
            SELECT
                substr(c.fecha, 1, 7) AS mes,
                ROUND(COALESCE(SUM(c.importe_real), 0), 2) AS monto_total,
                COUNT(*) AS cargas_count
            FROM combustible c
            GROUP BY substr(c.fecha, 1, 7)
            ORDER BY mes ASC
            """
        ).fetchall()
        meses_es = {
            "01": "Enero",
            "02": "Febrero",
            "03": "Marzo",
            "04": "Abril",
            "05": "Mayo",
            "06": "Junio",
            "07": "Julio",
            "08": "Agosto",
            "09": "Septiembre",
            "10": "Octubre",
            "11": "Noviembre",
            "12": "Diciembre",
        }
        resumen_mensual = [
            {
                "mes": r["mes"],
                "label": f"{meses_es.get(str(r['mes'])[5:7], str(r['mes']))} {str(r['mes'])[:4]}",
                "monto_total": float(r["monto_total"] or 0),
                "cargas_count": int(r["cargas_count"] or 0),
            }
            for r in resumen_mensual
        ]

        conn.close()

        return render_template(
            "vehiculos_combustible.html",
            vehiculos=vehiculos,
            choferes=choferes,
            precio_nafta=precio_nafta,
            precio_gasoil=precio_gasoil,
            cargas=cargas,
            resumen_mensual=resumen_mensual,
        )


    @app.route("/vehiculos/combustible/estadisticas", methods=["GET"], endpoint="vehiculos_combustible_estadisticas")
    def vehiculos_combustible_estadisticas():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        conn = get_db_connection()
        ensure_combustible_columns(conn)
        ensure_cols(conn, "vehiculos", [("rendimiento_ref", "REAL")])

        hoy = date.today()
        mes_actual_desde = hoy.replace(day=1).strftime("%Y-%m-%d")
        mes_actual_hasta = hoy.strftime("%Y-%m-%d")
        primer_dia_mes_actual = hoy.replace(day=1)
        ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
        primer_dia_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)
        mes_anterior_desde = primer_dia_mes_anterior.strftime("%Y-%m-%d")
        mes_anterior_hasta = ultimo_dia_mes_anterior.strftime("%Y-%m-%d")
        mes_cerrado_desde = mes_anterior_desde
        mes_cerrado_hasta = mes_anterior_hasta

        desde = request.args.get("desde") or mes_actual_desde
        hasta = request.args.get("hasta") or mes_actual_hasta
        patente = (request.args.get("patente") or "").strip()
        rendimiento_gasoil = request.args.get("rendimiento_gasoil") or "8"
        rendimiento_nafta = request.args.get("rendimiento_nafta") or "10"
        try:
            rendimiento_gasoil = float(str(rendimiento_gasoil).replace(",", "."))
        except Exception:
            rendimiento_gasoil = 8.0
        try:
            rendimiento_nafta = float(str(rendimiento_nafta).replace(",", "."))
        except Exception:
            rendimiento_nafta = 10.0
        if rendimiento_gasoil <= 0:
            rendimiento_gasoil = 8.0
        if rendimiento_nafta <= 0:
            rendimiento_nafta = 10.0
        saldo_inicial_litros = request.args.get("saldo_inicial_litros") or "80"
        try:
            saldo_inicial_litros = float(str(saldo_inicial_litros).replace(",", "."))
        except Exception:
            saldo_inicial_litros = 80.0
        if saldo_inicial_litros < 0:
            saldo_inicial_litros = 80.0

        vehiculos = conn.execute(
            """
            SELECT patente, codigo_interno, combustible, COALESCE(rendimiento_ref, 0) AS rendimiento_ref
            FROM vehiculos
            WHERE activo = 1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()

        where_comb = ["c.fecha BETWEEN ? AND ?"]
        params_comb = [desde, hasta]
        where_via = ["v.fecha BETWEEN ? AND ?"]
        params_via = [desde, hasta]
        if patente:
            where_comb.append("c.patente = ?")
            params_comb.append(patente)
            where_via.append("v.patente = ?")
            params_via.append(patente)

        wsql_comb = " AND ".join(where_comb)
        wsql_via = " AND ".join(where_via)

        rows_comb = conn.execute(
            f"""
            SELECT
                substr(c.fecha, 1, 7) AS mes,
                ROUND(COALESCE(SUM(c.importe_real), 0), 2) AS monto_total,
                ROUND(COALESCE(SUM(c.litros), 0), 2) AS litros_total,
                ROUND(COALESCE(AVG(c.precio_unit), 0), 2) AS precio_prom
            FROM combustible c
            WHERE {wsql_comb}
            GROUP BY substr(c.fecha, 1, 7)
            """,
            params_comb,
        ).fetchall()

        rows_via = conn.execute(
            f"""
            SELECT
                substr(v.fecha, 1, 7) AS mes,
                ROUND(COALESCE(SUM(v.recorrido_km), 0), 2) AS km_recorridos
            FROM viajes v
            WHERE {wsql_via}
            GROUP BY substr(v.fecha, 1, 7)
            """,
            params_via,
        ).fetchall()
        rows_via_mes_pat = conn.execute(
            f"""
            SELECT
                substr(v.fecha, 1, 7) AS mes,
                v.patente AS patente,
                LOWER(TRIM(COALESCE(vh.combustible, 'gasoil'))) AS combustible,
                COALESCE(vh.rendimiento_ref, 0) AS rendimiento_ref,
                ROUND(COALESCE(SUM(v.recorrido_km), 0), 2) AS km_recorridos
            FROM viajes v
            LEFT JOIN vehiculos vh ON vh.patente = v.patente
            WHERE {wsql_via}
            GROUP BY substr(v.fecha, 1, 7), v.patente, LOWER(TRIM(COALESCE(vh.combustible, 'gasoil'))), COALESCE(vh.rendimiento_ref, 0)
            """,
            params_via,
        ).fetchall()
        rows_comb_pat = conn.execute(
            f"""
            SELECT
                c.patente AS patente,
                ROUND(COALESCE(SUM(c.litros), 0), 2) AS litros_total,
                ROUND(COALESCE(SUM(c.importe_real), 0), 2) AS monto_total,
                COUNT(*) AS cargas_count,
                ROUND(COALESCE(MAX(c.litros), 0), 2) AS max_litros
            FROM combustible c
            WHERE {wsql_comb}
            GROUP BY c.patente
            """,
            params_comb,
        ).fetchall()
        rows_via_prev_pat = conn.execute(
            """
            SELECT
                v.patente AS patente,
                ROUND(COALESCE(SUM(v.recorrido_km), 0), 2) AS km_prev
            FROM viajes v
            WHERE v.fecha < ?
            GROUP BY v.patente
            """,
            (desde,),
        ).fetchall()
        rows_comb_prev_pat = conn.execute(
            """
            SELECT
                c.patente AS patente,
                ROUND(COALESCE(SUM(c.litros), 0), 2) AS litros_prev
            FROM combustible c
            WHERE c.fecha < ?
            GROUP BY c.patente
            """,
            (desde,),
        ).fetchall()
        rows_via_pat = conn.execute(
            f"""
            SELECT
                v.patente AS patente,
                COALESCE(vh.codigo_interno, v.patente) AS codigo_interno,
                LOWER(TRIM(COALESCE(vh.combustible, 'gasoil'))) AS combustible,
                COALESCE(vh.rendimiento_ref, 0) AS rendimiento_ref,
                ROUND(COALESCE(SUM(v.recorrido_km), 0), 2) AS km_recorridos
            FROM viajes v
            LEFT JOIN vehiculos vh ON vh.patente = v.patente
            WHERE {wsql_via}
            GROUP BY v.patente, COALESCE(vh.codigo_interno, v.patente), LOWER(TRIM(COALESCE(vh.combustible, 'gasoil'))), COALESCE(vh.rendimiento_ref, 0)
            ORDER BY COALESCE(vh.codigo_interno, v.patente), v.patente
            """,
            params_via,
        ).fetchall()

        comb_by_mes = {
            r["mes"]: {
                "monto_total": float(r["monto_total"] or 0),
                "litros_total": float(r["litros_total"] or 0),
                "precio_prom": float(r["precio_prom"] or 0),
            }
            for r in rows_comb
        }
        via_by_mes = {r["mes"]: float(r["km_recorridos"] or 0) for r in rows_via}
        consumo_esperado_by_mes = {}
        for r in rows_via_mes_pat:
            mes = r["mes"]
            km_v = float(r["km_recorridos"] or 0)
            comb = str(r["combustible"] or "").strip().lower()
            rend_custom = float(r["rendimiento_ref"] or 0)
            rend_ref_v = rend_custom if rend_custom > 0 else (rendimiento_nafta if comb.startswith("naf") else rendimiento_gasoil)
            litros_esp_v = (km_v / rend_ref_v) if rend_ref_v > 0 else 0.0
            consumo_esperado_by_mes[mes] = float(consumo_esperado_by_mes.get(mes, 0.0)) + litros_esp_v
        comb_by_pat = {
            r["patente"]: {
                "litros_total": float(r["litros_total"] or 0),
                "monto_total": float(r["monto_total"] or 0),
                "cargas_count": int(r["cargas_count"] or 0),
                "max_litros": float(r["max_litros"] or 0),
            }
            for r in rows_comb_pat
        }
        km_prev_by_pat = {r["patente"]: float(r["km_prev"] or 0) for r in rows_via_prev_pat}
        litros_prev_by_pat = {r["patente"]: float(r["litros_prev"] or 0) for r in rows_comb_prev_pat}
        meses = sorted(set(comb_by_mes.keys()) | set(via_by_mes.keys()))

        analisis = []
        por_vehiculo = []
        total_monto = 0.0
        total_litros = 0.0
        total_km = 0.0
        for mes in meses:
            rc = comb_by_mes.get(mes, {})
            monto_total = float(rc.get("monto_total", 0))
            litros_total = float(rc.get("litros_total", 0))
            precio_prom = float(rc.get("precio_prom", 0))
            km_recorridos = float(via_by_mes.get(mes, 0))
            consumo_teorico = float(consumo_esperado_by_mes.get(mes, 0.0))
            margen_litros = litros_total - consumo_teorico
            # Porcentaje de desvio sobre litros cargados para evitar valores exagerados por base pequena.
            margen_pct = ((margen_litros / litros_total) * 100.0) if litros_total > 0 else 0.0
            precio_km = (monto_total / km_recorridos) if km_recorridos > 0 else 0.0
            km_litro = (km_recorridos / litros_total) if litros_total > 0 else 0.0
            total_monto += monto_total
            total_litros += litros_total
            total_km += km_recorridos
            analisis.append(
                {
                    "mes": mes,
                    "monto_total": monto_total,
                    "km_recorridos": km_recorridos,
                    "precio_prom": precio_prom,
                    "litros_total": litros_total,
                    "consumo_teorico": consumo_teorico,
                    "margen_litros": margen_litros,
                    "margen_pct": margen_pct,
                    "precio_km": precio_km,
                    "km_litro": km_litro,
                }
            )
        via_by_pat = {
            r["patente"]: {
                "patente": r["patente"],
                "codigo_interno": r["codigo_interno"],
                "combustible": str(r["combustible"] or "").strip().lower(),
                "rendimiento_ref": float(r["rendimiento_ref"] or 0),
                "km_recorridos": float(r["km_recorridos"] or 0),
            }
            for r in rows_via_pat
        }
        veh_meta = {
            v["patente"]: {
                "codigo_interno": v["codigo_interno"] or v["patente"],
                "combustible": str(v["combustible"] or "").strip().lower(),
                "rendimiento_ref": float(v["rendimiento_ref"] or 0),
            }
            for v in vehiculos
        }
        pats = sorted(set(via_by_pat.keys()) | set(comb_by_pat.keys()))
        for pat in pats:
            rv = via_by_pat.get(pat, {})
            meta = veh_meta.get(pat, {})
            km_v = float(rv.get("km_recorridos", 0))
            rc_pat = comb_by_pat.get(pat, {})
            litros_v = float(rc_pat.get("litros_total", 0))
            monto_v = float(rc_pat.get("monto_total", 0))
            cargas_count_v = int(rc_pat.get("cargas_count", 0))
            max_litros_v = float(rc_pat.get("max_litros", 0))
            comb_v = str(rv.get("combustible") or meta.get("combustible") or "gasoil").strip().lower()
            rend_custom_v = float(rv.get("rendimiento_ref") or meta.get("rendimiento_ref") or 0)
            rend_ref_v = rend_custom_v if rend_custom_v > 0 else (rendimiento_nafta if comb_v.startswith("naf") else rendimiento_gasoil)
            litros_esp_v = (km_v / rend_ref_v) if rend_ref_v > 0 else 0.0
            km_litro_v = (km_v / litros_v) if litros_v > 0 else 0.0
            margen_litros_v = litros_v - litros_esp_v
            margen_pct_v = ((margen_litros_v / litros_v) * 100.0) if litros_v > 0 else 0.0
            precio_km_v = (monto_v / km_v) if km_v > 0 else 0.0
            km_prev_v = float(km_prev_by_pat.get(pat, 0))
            litros_prev_v = float(litros_prev_by_pat.get(pat, 0))
            litros_esp_prev_v = (km_prev_v / rend_ref_v) if rend_ref_v > 0 else 0.0
            # Modo simple solicitado: iniciar cada periodo con tanque lleno.
            saldo_anterior_v = float(saldo_inicial_litros)
            litros_disponibles_v = litros_v + max(0.0, saldo_anterior_v)
            faltante_v = max(0.0, litros_esp_v - litros_disponibles_v)
            cobertura_pct_v = ((litros_disponibles_v / litros_esp_v) * 100.0) if litros_esp_v > 0 else 100.0
            saldo_cierre_v = saldo_anterior_v + litros_v - litros_esp_v
            alerta_atipica_v = max_litros_v > 150
            if alerta_atipica_v:
                estado_v = "Carga atipica"
            elif faltante_v > 0 and cargas_count_v == 0 and km_v > 0:
                estado_v = "Falta carga viaje"
            elif faltante_v > 0:
                estado_v = "Revisar cargas"
            else:
                estado_v = "Coherente"
            por_vehiculo.append(
                {
                    "patente": pat,
                    "codigo_interno": rv.get("codigo_interno") or meta.get("codigo_interno") or pat,
                    "combustible": "nafta" if comb_v.startswith("naf") else "gasoil",
                    "km_recorridos": km_v,
                    "litros_total": litros_v,
                    "km_litro": km_litro_v,
                    "rendimiento_ref": rend_ref_v,
                    "litros_esperados": litros_esp_v,
                    "margen_litros": margen_litros_v,
                    "margen_pct": margen_pct_v,
                    "monto_total": monto_v,
                    "precio_km": precio_km_v,
                    "saldo_anterior": saldo_anterior_v,
                    "saldo_cierre": saldo_cierre_v,
                    "faltante_litros": faltante_v,
                    "cobertura_pct": cobertura_pct_v,
                    "cargas_count": cargas_count_v,
                    "alerta_atipica": alerta_atipica_v,
                    "estado": estado_v,
                }
            )
        por_vehiculo.sort(key=lambda x: (str(x.get("codigo_interno") or ""), str(x.get("patente") or "")))

        resumen = {
            "monto_total": round(total_monto, 2),
            "litros_total": round(total_litros, 2),
            "km_total": round(total_km, 2),
            "precio_km": round((total_monto / total_km), 2) if total_km > 0 else 0.0,
            "km_litro": round((total_km / total_litros), 2) if total_litros > 0 else 0.0,
        }

        conn.close()
        return render_template(
            "vehiculos_combustible_estadisticas.html",
            patente=patente,
            vehiculos=vehiculos,
            rendimiento_gasoil=rendimiento_gasoil,
            rendimiento_nafta=rendimiento_nafta,
            analisis=analisis,
            por_vehiculo=por_vehiculo,
            resumen=resumen,
            mes_actual_desde=mes_actual_desde,
            mes_actual_hasta=mes_actual_hasta,
            mes_anterior_desde=mes_anterior_desde,
            mes_anterior_hasta=mes_anterior_hasta,
            mes_cerrado_desde=mes_cerrado_desde,
            mes_cerrado_hasta=mes_cerrado_hasta,
        )


    # -------------------------
    # COMBUSTIBLE - CARGA DESDE VIAJE ("Carga comb.")
    # -------------------------
    @app.route("/vehiculos/combustible/nuevo", methods=["GET", "POST"], endpoint="vehiculos_combustible_nuevo")
    def vehiculos_combustible_nuevo():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        conn = get_db_connection()
        ensure_combustible_columns(conn)

        vehiculos = conn.execute(
            """
            SELECT patente, codigo_interno, combustible
            FROM vehiculos
            WHERE activo = 1
            ORDER BY codigo_interno, patente
            """
        ).fetchall()

        choferes = conn.execute(
            """
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro = 'choferes' AND activo = 1
            ORDER BY agente
            """
        ).fetchall()

        # ---- valores que pueden venir DESDE el viaje (por querystring) ----
        pref_fecha     = request.args.get("fecha") or date.today().isoformat()
        pref_patente   = request.args.get("patente") or ""
        pref_km_actual = request.args.get("km") or ""
        pref_chofer_id = request.args.get("chofer_id") or ""

        if request.method == "POST":
            fecha        = request.form.get("fecha") or date.today().isoformat()
            patente      = request.form.get("patente")
            chofer_id_raw = request.form.get("chofer_id") or ""
            chofer_nombre_raw = request.form.get("chofer_nombre") or ""
            chofer_id = _resolve_or_create_chofer_id(conn, chofer_id_raw, chofer_nombre_raw)
            remito       = request.form.get("remito", "").strip()
            km_actual_raw    = request.form.get("km_actual")
            litros_raw       = request.form.get("litros")
            precio_litro_raw = request.form.get("precio_litro")
            notas        = request.form.get("notas", "").strip() or None

            if not patente:
                flash("Falta seleccionar vehiculo.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            km_actual = _parse_float_local(km_actual_raw or 0)
            litros = _parse_float_local(litros_raw or 0)
            precio_litro = _parse_float_local(precio_litro_raw or 0)

            if km_actual is None or litros is None or precio_litro is None:
                flash("Valores numericos invalidos.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            if km_actual < 0 or litros <= 0 or precio_litro <= 0:
                flash("Revisa KM, litros y precio (no pueden ser negativos).", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))
            if litros > MAX_LITROS_CARGA:
                flash(f"Litros fuera de rango (max {int(MAX_LITROS_CARGA)} por carga). Revisar formato decimal.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))
            if precio_litro > MAX_PRECIO_LITRO:
                flash(f"Precio por litro fuera de rango (max {int(MAX_PRECIO_LITRO)}). Revisar formato decimal.", "danger")
                conn.close()
                return redirect(url_for("vehiculos_combustible"))

            # Tipo de combustible del vehículo (nafta / gasoil)
            vrow = conn.execute(
                "SELECT combustible FROM vehiculos WHERE patente = ?",
                (patente,),
            ).fetchone()
            tipo = (vrow["combustible"] if vrow and vrow["combustible"] else "nafta")

            importe_calculado = round(litros * precio_litro, 2)
            importe_real      = importe_calculado  # si querés después podés editarlo

            remito_archivo = (request.form.get("remito_url") or "").strip() or None
            if not remito_archivo:
                try:
                    remito_archivo = _save_remito_image_from_request(request)
                except ValueError as e:
                    flash(str(e), "danger")
                    conn.close()
                    return redirect(url_for("vehiculos_combustible"))

            conn.execute(
                """
                INSERT INTO combustible
                (fecha, patente, chofer_id, tipo,
                 km_actual, litros, precio_unit,
                 importe_calculado, importe_real,
                 nro_remito, observaciones, remito_archivo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fecha, patente, chofer_id, tipo,
                    km_actual, litros, precio_litro,
                    importe_calculado, importe_real,
                    remito, notas, remito_archivo,
                ),
            )
            conn.commit()
            conn.close()
            rebuild_eventos_vehiculos()

            flash("✅ Carga de combustible guardada.", "success")
            return redirect(url_for("vehiculos_combustible"))

        conn.close()
        return render_template(
            "vehiculos_combustible_nuevo.html",
            vehiculos=vehiculos,
            choferes=choferes,
            pref_fecha=pref_fecha,
            pref_patente=pref_patente,
            pref_km_actual=pref_km_actual,
            pref_chofer_id=pref_chofer_id,
        )
    # =========================
    # REMITOS - VER / DESCARGAR
    # =========================
    @app.route("/vehiculos/combustible/remitos/<path:filename>", endpoint="combustible_remito_ver")
    def combustible_remito_ver(filename):
        if filename.startswith("http://") or filename.startswith("https://"):
            return redirect(filename)
        safe = secure_filename(filename or "")
        if safe:
            abs_path = os.path.join(REMITOS_UPLOAD_DIR, safe)
            if os.path.isfile(abs_path):
                return send_from_directory(REMITOS_UPLOAD_DIR, safe, as_attachment=False)
        return redirect(REMITOS_DRIVE_URL)

    @app.route("/viajes/<int:viaje_id>/editar", methods=["GET", "POST"], endpoint="viaje_editar_legacy")
    def viaje_editar_legacy(viaje_id):
        conn = get_db_connection()
        deny = _deny_if_not_owner(conn, viaje_id)
        if deny:
            conn.close()
            return deny
        _ensure_viajes_operativo_cols(conn)

        # Combos (mismos que control diario)
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

        # Viaje actual
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
            # Si el combo llega vacio, conservar el valor actual para no perder datos
            chofer_id = request.form.get("chofer_id") or viaje["chofer_id"] or None
            destino_id = request.form.get("destino_id") or viaje["destino_id"] or None
            personal_id = request.form.get("personal_id") or viaje["personal_id"] or None
            obs = (request.form.get("observaciones") or "").strip()

            # KM seguros
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

            # Sector y dependencia desde personal_sede (igual que en alta)
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

    @app.route("/viajes/<int:viaje_id>/eliminar", methods=["POST"], endpoint="viajes_delete")
    def viajes_delete(viaje_id):
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        conn = get_db_connection()
        fecha = _delete_viaje(conn, viaje_id)
        conn.close()
        rebuild_eventos_vehiculos()

        flash("Viaje eliminado.", "info")
        return redirect(url_for("vehiculos_control_diario", fecha=fecha))


    @app.route("/vehiculos/checklist", methods=["GET", "POST"], endpoint="vehiculos_checklist")
    def vehiculos_checklist():
        conn = get_db_connection()

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

        items = conn.execute("""
            SELECT id, nombre
            FROM checklist_items
            WHERE activo=1
            ORDER BY id
        """).fetchall()

        if request.method == "POST":
            fecha   = request.form.get("fecha") or date.today().isoformat()
            patente = request.form.get("patente")
            chofer_id = request.form.get("chofer_id") or None
            tipo   = request.form.get("tipo")
            obs    = request.form.get("observaciones","").strip()

            cur = conn.cursor()
            # encabezado
            cur.execute("""
                INSERT INTO checklist_registros
                (fecha, patente, chofer_id, tipo, observaciones)
                VALUES (?,?,?,?,?)
            """, (fecha, patente, chofer_id, tipo, obs))
            reg_id = cur.lastrowid

            # detalle por cada item
            for it in items:
                checked = 1 if request.form.get(f"item_{it['id']}") else 0
                nota = request.form.get(f"nota_{it['id']}", "").strip() or None
                cur.execute("""
                    INSERT INTO checklist_detalle
                    (registro_id, item_id, ok, nota)
                    VALUES (?,?,?,?)
                """, (reg_id, it["id"], checked, nota))

            conn.commit()
            flash("✅ Checklist registrado.", "success")
            return redirect(url_for("vehiculos_checklist"))

        # listado de últimos registros
        registros = conn.execute("""
            SELECT
                r.*,
                v.codigo_interno,
                v.patente,
                c.agente AS chofer_nombre
            FROM checklist_registros r
            LEFT JOIN vehiculos v ON v.patente = r.patente
            LEFT JOIN agentes_intendencia c ON c.id = r.chofer_id
            ORDER BY date(r.fecha) DESC, r.id DESC
        """).fetchall()

        conn.close()
        return render_template(
            "vehiculos_checklist.html",
            vehiculos=vehiculos,
            choferes=choferes,
            items=items,
            registros=registros
        )



    @app.route("/vehiculos/combustible/<int:cid>/editar", methods=["GET", "POST"], endpoint="combustible_editar")
    def combustible_editar(cid):
        conn = get_db_connection()
        ensure_combustible_columns(conn)

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

        carga = conn.execute("""
            SELECT c.*, ai.agente AS chofer_nombre
            FROM combustible c
            LEFT JOIN agentes_intendencia ai ON ai.id = c.chofer_id
            WHERE c.id=?
        """, (cid,)).fetchone()

        if not carga:
            conn.close()
            flash("Carga no encontrada.", "danger")
            return redirect(url_for("vehiculos_combustible"))

        if request.method == "POST":
            def row_get(row, key, default=None):
                try:
                    return row[key]
                except Exception:
                    return default

            remito_url_in = (request.form.get("remito_url") or "").strip()
            remito_clear = (request.form.get("remito_clear") or "").strip() == "1"
            try:
                nuevo_remito = _save_remito_image_from_request(request)
            except ValueError as e:
                conn.close()
                flash(str(e), "danger")
                return redirect(url_for("combustible_editar", cid=cid))

            if remito_clear:
                _delete_local_remito_if_exists(row_get(carga, "remito_archivo"))
                conn.execute("UPDATE combustible SET remito_archivo=NULL WHERE id=?", (cid,))
                conn.commit()
                conn.close()
                rebuild_eventos_vehiculos()
                flash("✅ Remito eliminado.", "success")
                return redirect(url_for("vehiculos_combustible"))

            # Flujo seguro: subir/pegar solo remito, sin tocar el resto de campos.
            if (request.form.get("remito_only") or "").strip() == "1":
                remito_archivo_guardado = remito_url_in or row_get(carga, "remito_archivo")
                if nuevo_remito:
                    _delete_local_remito_if_exists(row_get(carga, "remito_archivo"))
                    remito_archivo_guardado = nuevo_remito
                if not remito_archivo_guardado:
                    conn.close()
                    flash("Subi o pega una imagen del remito.", "danger")
                    return redirect(url_for("combustible_editar", cid=cid))
                conn.execute(
                    "UPDATE combustible SET remito_archivo=? WHERE id=?",
                    (remito_archivo_guardado, cid),
                )
                conn.commit()
                conn.close()
                rebuild_eventos_vehiculos()
                flash("✅ Remito actualizado (sin modificar la carga).", "success")
                return redirect(url_for("vehiculos_combustible"))

            fecha = request.form.get("fecha") or carga["fecha"] or date.today().isoformat()
            patente = request.form.get("patente") or carga["patente"]
            tipo = request.form.get("tipo") or row_get(carga, "tipo") or "nafta"

            chofer_id_raw = request.form.get("chofer_id") or ""
            chofer_nombre_raw = request.form.get("chofer_nombre") or ""
            chofer_id = _resolve_or_create_chofer_id(conn, chofer_id_raw, chofer_nombre_raw)
            if chofer_id is None:
                chofer_id = row_get(carga, "chofer_id")

            def fnum(x, default=0.0):
                val = _parse_float_local(x)
                if val is None:
                    return default
                return val

            km_actual = fnum(request.form.get("km_actual"), fnum(row_get(carga, "km_actual"), 0.0))
            litros = fnum(request.form.get("litros"), fnum(row_get(carga, "litros"), 0.0))
            precio_unit = fnum(request.form.get("precio_unit"), fnum(row_get(carga, "precio_unit"), 0.0))
            importe_real = fnum(request.form.get("importe_real"), fnum(row_get(carga, "importe_real"), 0.0))

            if km_actual < 0 or litros <= 0 or precio_unit <= 0 or importe_real < 0:
                conn.close()
                flash("Revisa KM, litros, precio e importe (no pueden ser negativos).", "danger")
                return redirect(url_for("combustible_editar", cid=cid))

            nro_remito = (request.form.get("remito") or "").strip()
            observaciones = (request.form.get("notas") or "").strip()

            importe_calculado = round(litros * precio_unit, 2)
            remito_archivo_guardado = remito_url_in or row_get(carga, "remito_archivo")
            if nuevo_remito:
                _delete_local_remito_if_exists(row_get(carga, "remito_archivo"))
                remito_archivo_guardado = nuevo_remito

            conn.execute("""
                UPDATE combustible
                SET fecha=?,
                    patente=?,
                    chofer_id=?,
                    tipo=?,
                    km_actual=?,
                    litros=?,
                    precio_unit=?,
                    importe_calculado=?,
                    importe_real=?,
                    nro_remito=?,
                    observaciones=?,
                    remito_archivo=?
                WHERE id=?
            """, (
                fecha, patente, chofer_id, tipo,
                km_actual, litros, precio_unit,
                importe_calculado, importe_real,
                nro_remito, observaciones, remito_archivo_guardado,
                cid
            ))
            conn.commit()
            conn.close()
            rebuild_eventos_vehiculos()

            flash("✅ Carga actualizada.", "success")
            return redirect(url_for("vehiculos_combustible"))

        conn.close()
        return render_template(
            "vehiculos_combustible_editar.html",
            carga=carga,
            vehiculos=vehiculos,
            choferes=choferes
        )


    @app.route("/vehiculos/combustible/<int:cid>/eliminar", methods=["POST"], endpoint="combustible_eliminar")
    def combustible_eliminar(cid):
        conn = get_db_connection()
        ensure_combustible_columns(conn)

        row = conn.execute("SELECT remito_archivo FROM combustible WHERE id=?", (cid,)).fetchone()
        if not row:
            conn.close()
            flash("Carga no encontrada.", "danger")
            return redirect(url_for("vehiculos_combustible"))

        _delete_local_remito_if_exists(row["remito_archivo"])
        conn.execute("DELETE FROM combustible WHERE id=?", (cid,))
        conn.commit()
        conn.close()
        rebuild_eventos_vehiculos()
        flash("🗑️ Carga eliminada.", "info")
        return redirect(url_for("vehiculos_combustible"))




    from flask import request, render_template, redirect, url_for, flash

    # =========================================================
    # BASE DE DATOS - VEHÍCULOS (HOME)
    # =========================================================
    @app.route("/vehiculos/basedatos", endpoint="vehiculos_bd_home")
    def vehiculos_bd_home():
        if (session.get("role") or "") == ROLE_CHOFER_AUTORIZADO:
            return redirect(url_for("access_denied"))
        return render_template("vehiculos_bd_home.html")


    # =========================================================
    # DESTINOS CRUD
    # =========================================================
    @app.route("/vehiculos/basedatos/destinos", methods=["GET", "POST"], endpoint="bd_destinos")
    def bd_destinos():
        con = get_db()

        if request.method == "POST":
            nombre = (request.form.get("nombre") or "").strip()

            if not nombre:
                flash("Nombre obligatorio.", "warning")
            else:
                try:
                    con.execute("""
                        INSERT INTO destinos (nombre)
                        VALUES (?)
                    """, (nombre,))
                    con.commit()
                    flash("Destino agregado.", "success")
                except Exception as e:
                    flash(f"Error: {e}", "error")

        destinos = con.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
        con.close()
        return render_template("bd_destinos.html", destinos=destinos)


    @app.route("/vehiculos/basedatos/destinos/<int:did>/delete", methods=["POST"], endpoint="bd_destinos_delete")
    def bd_destinos_delete(did):
        con = get_db()
        con.execute("DELETE FROM destinos WHERE id=?", (did,))
        con.commit()
        con.close()
        flash("Destino eliminado.", "info")
        return redirect(url_for("bd_destinos"))


    # =========================================================
    # EQUIPO INTERDISCIPLINARIO CRUD
    # =========================================================
    @app.route("/vehiculos/basedatos/equipo", methods=["GET", "POST"], endpoint="bd_equipo")
    def bd_equipo():
        con = get_db()

        if request.method == "POST":
            nombre = (request.form.get("nombre") or "").strip()
            profesion = (request.form.get("profesion") or "").strip()

            if not nombre or not profesion:
                flash("Nombre y profesión obligatorios.", "warning")
            else:
                try:
                    con.execute("""
                        INSERT OR IGNORE INTO equipo_interdisciplinario(nombre, profesion)
                        VALUES (?, ?)
                    """, (nombre, profesion))
                    con.commit()
                    flash("Integrante agregado.", "success")
                except Exception as e:
                    flash(f"Error: {e}", "error")

        equipo = con.execute("""
            SELECT *
            FROM equipo_interdisciplinario
            WHERE activo=1
            ORDER BY profesion, nombre
        """).fetchall()

        con.close()
        return render_template("bd_equipo.html", equipo=equipo)


    @app.route("/vehiculos/basedatos/equipo/<int:eid>/delete", methods=["POST"], endpoint="bd_equipo_delete")
    def bd_equipo_delete(eid):
        con = get_db()
        con.execute("UPDATE equipo_interdisciplinario SET activo=0 WHERE id=?", (eid,))
        con.commit()
        con.close()
        flash("Integrante dado de baja.", "info")
        return redirect(url_for("bd_equipo"))


    from flask import request, render_template, redirect, url_for, flash

    # =========================================================
    # CHOFERES (LISTA GENERAL)  ✅ ESTE ES EL QUE USA CONTROL DIARIO
    # =========================================================
    @app.route("/vehiculos/basedatos/choferes", methods=["GET", "POST"], endpoint="bd_choferes")
    def bd_choferes():
        con = get_db()

        # ALTA
        if request.method == "POST":
            agente = (request.form.get("agente") or "").strip()

            if not agente:
                flash("Nombre obligatorio.", "warning")
                con.close()
                return redirect(url_for("bd_choferes"))

            try:
                con.execute("""
                    INSERT INTO agentes_intendencia (agente, rubro, activo)
                    VALUES (?, 'choferes', 1)
                """, (agente,))
                con.commit()
                flash("Chofer agregado.", "success")
            except Exception as e:
                flash(f"Error: {e}", "error")

            con.close()
            return redirect(url_for("bd_choferes"))

        # LISTA
        choferes = con.execute("""
            SELECT id, agente, COALESCE(activo,1) AS activo
            FROM agentes_intendencia
            WHERE rubro='choferes'
            ORDER BY agente
        """).fetchall()

        con.close()
        return render_template("bd_choferes.html", choferes=choferes)


    # EDITAR (GET muestra form / POST guarda)
    @app.route("/vehiculos/basedatos/choferes/<int:cid>/editar", methods=["GET", "POST"], endpoint="bd_choferes_editar")
    def bd_choferes_editar(cid):
        con = get_db()

        r = con.execute("""
            SELECT id, agente, COALESCE(activo,1) AS activo
            FROM agentes_intendencia
            WHERE id=? AND rubro='choferes'
        """, (cid,)).fetchone()

        if not r:
            con.close()
            flash("Chofer no encontrado.", "error")
            return redirect(url_for("bd_choferes"))

        if request.method == "POST":
            agente = (request.form.get("agente") or "").strip()
            activo = 1 if (request.form.get("activo") == "1") else 0

            if not agente:
                con.close()
                flash("Nombre obligatorio.", "warning")
                return redirect(url_for("bd_choferes_editar", cid=cid))

            con.execute("""
                UPDATE agentes_intendencia
                SET agente=?, activo=?
                WHERE id=? AND rubro='choferes'
            """, (agente, activo, cid))

            con.commit()
            con.close()
            flash("Chofer actualizado.", "success")
            return redirect(url_for("bd_choferes"))

        con.close()
        return render_template("bd_choferes_form.html", r=r)


    # DAR DE BAJA (activo=0)
    @app.route("/vehiculos/basedatos/choferes/<int:cid>/baja", methods=["POST"], endpoint="bd_choferes_baja")
    def bd_choferes_baja(cid):
        con = get_db()
        con.execute("""
            UPDATE agentes_intendencia
            SET activo=0
            WHERE id=? AND rubro='choferes'
        """, (cid,))
        con.commit()
        con.close()

        flash("Chofer dado de baja.", "info")
        return redirect(url_for("bd_choferes"))


    # REACTIVAR (activo=1)
    @app.route("/vehiculos/basedatos/choferes/<int:cid>/alta", methods=["POST"], endpoint="bd_choferes_alta")
    def bd_choferes_alta(cid):
        con = get_db()
        con.execute("""
            UPDATE agentes_intendencia
            SET activo=1
            WHERE id=? AND rubro='choferes'
        """, (cid,))
        con.commit()
        con.close()

        flash("Chofer reactivado.", "success")
        return redirect(url_for("bd_choferes"))

    # =========================================================
    # CHOFERES AUTORIZADOS POR VEHÍCULO (OPCIONAL)
    # =========================================================
    @app.route("/vehiculos/basedatos/choferes-aut", methods=["GET", "POST"], endpoint="bd_choferes_aut")
    def bd_choferes_aut():
        con = get_db()

        vehiculos = con.execute("""
            SELECT patente, codigo_interno
            FROM vehiculos
            WHERE activo=1
            ORDER BY codigo_interno, patente
        """).fetchall()

        choferes = con.execute("""
            SELECT id, agente
            FROM agentes_intendencia
            WHERE rubro='choferes' AND COALESCE(activo,1)=1
            ORDER BY agente
        """).fetchall()

        if request.method == "POST":
            patente = request.form.get("patente")
            chofer_id = request.form.get("chofer_id")

            if not patente or not chofer_id:
                flash("Falta seleccionar vehículo y chofer.", "warning")
            else:
                try:
                    con.execute("""
                        INSERT OR IGNORE INTO vehiculo_choferes(patente, chofer_id, activo)
                        VALUES (?, ?, 1)
                    """, (patente, chofer_id))
                    con.commit()
                    flash("Chofer autorizado agregado.", "success")
                except Exception as e:
                    flash(f"Error: {e}", "error")

        autorizados = con.execute("""
            SELECT vc.id, ve.codigo_interno, vc.patente, ai.agente
            FROM vehiculo_choferes vc
            JOIN vehiculos ve ON ve.patente = vc.patente
            JOIN agentes_intendencia ai ON ai.id = vc.chofer_id
            WHERE COALESCE(vc.activo,1)=1
            ORDER BY ve.codigo_interno, ai.agente
        """).fetchall()

        con.close()
        return render_template(
            "bd_choferes_aut.html",
            vehiculos=vehiculos,
            choferes=choferes,
            autorizados=autorizados
        )


    @app.route("/vehiculos/basedatos/choferes-aut/<int:cid>/delete", methods=["POST"], endpoint="bd_choferes_aut_delete")
    def bd_choferes_aut_delete(cid):
        con = get_db()
        con.execute("UPDATE vehiculo_choferes SET activo=0 WHERE id=?", (cid,))
        con.commit()
        con.close()
        flash("Chofer autorizado eliminado.", "info")
        return redirect(url_for("bd_choferes_aut"))


    # =========================================================
    # PRECIOS COMBUSTIBLE
    # =========================================================
    @app.route("/vehiculos/basedatos/precios", methods=["GET", "POST"], endpoint="bd_precios")
    def bd_precios():
        con = get_db()

        if request.method == "POST":
            nafta = float(request.form.get("nafta") or 0)
            gasoil = float(request.form.get("gasoil") or 0)

            con.execute("UPDATE combustible_precios SET precio_litro=? WHERE tipo='nafta'", (nafta,))
            con.execute("UPDATE combustible_precios SET precio_litro=? WHERE tipo='gasoil'", (gasoil,))
            con.commit()
            flash("Precios actualizados.", "success")

        precios = {r["tipo"]: r["precio_litro"] for r in con.execute("SELECT * FROM combustible_precios").fetchall()}
        con.close()
        return render_template("bd_precios.html", precios=precios)



    @app.route("/vehiculos/eventos/regenerar", endpoint="vehiculos_eventos_regenerar")
    def vehiculos_eventos_regenerar():
        rebuild_eventos_vehiculos()
        flash("Eventos de vehículos regenerados en el calendario.", "success")
        return redirect(url_for("calendario"))
