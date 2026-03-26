from datetime import date, datetime

from flask import render_template, request, jsonify, session, current_app

from . import bp
from . import helpers as nvd_h

# Exponer helpers localmente (sin cambiar logica)
SEDE_ESTADO_VARS = nvd_h.SEDE_ESTADO_VARS
SEDE_ESTADO_LABELS = nvd_h.SEDE_ESTADO_LABELS
NVD_TIPO_SUBTIPOS = nvd_h.NVD_TIPO_SUBTIPOS
NVD_ESTADOS = nvd_h.NVD_ESTADOS

_table_exists = nvd_h._table_exists
_table_cols = nvd_h._table_cols
_row_value = nvd_h._row_value
_ensure_novedades_catalogo_table = nvd_h._ensure_novedades_catalogo_table
_nvd_tipos_subtipos = nvd_h._nvd_tipos_subtipos
_ensure_novedades_diarias_table = nvd_h._ensure_novedades_diarias_table
_safe_today = nvd_h._safe_today
_norm_nvd_estado = nvd_h._norm_nvd_estado
_novedades_resumen = nvd_h._novedades_resumen
_dashboard_sedes_opts = nvd_h._dashboard_sedes_opts
_dashboard_agentes_opts = nvd_h._dashboard_agentes_opts
_dashboard_vehiculos_simple = nvd_h._dashboard_vehiculos_simple
_dashboard_alertas_criticas = nvd_h._dashboard_alertas_criticas
_dashboard_sede_estado_read = nvd_h._dashboard_sede_estado_read

_ensure_dashboard_vehiculos_manual_table = nvd_h._ensure_dashboard_vehiculos_manual_table
_ensure_dashboard_turnos_choferes_cfg = nvd_h._ensure_dashboard_turnos_choferes_cfg
_ensure_dashboard_vehiculos_cfg = nvd_h._ensure_dashboard_vehiculos_cfg
_ensure_dashboard_turnos_choferes_ack_table = nvd_h._ensure_dashboard_turnos_choferes_ack_table
_ensure_dashboard_rotacion_limpieza_table = nvd_h._ensure_dashboard_rotacion_limpieza_table
_ensure_dashboard_novedades_obra_table = nvd_h._ensure_dashboard_novedades_obra_table


def register_novedades(bp, get_db):
    # Evitar doble registro del blueprint (compatibilidad con legacy_app)
    if getattr(bp, "_novedades_registered", False):
        return bp
    bp._novedades_registered = True

    @bp.route("/", endpoint="dashboard")
    @bp.route("/dashboard", endpoint="dashboard_exec")
    def dashboard_exec():
        return render_template("dashboard_exec.html")

    @bp.route("/dashboard/gestion", endpoint="dashboard_gestion")
    def dashboard_gestion():
        return render_template("dashboard_gestion.html")

    def _dashboard_operativo_data():
        fn = current_app.config.get("DASHBOARD_OPERATIVO_DATA_FN")
        if callable(fn):
            return fn()
        return {}

    @bp.route("/api/dashboard_operativo", methods=["GET"], endpoint="api_dashboard_operativo")
    def api_dashboard_operativo():
        return jsonify(_dashboard_operativo_data())

    @bp.route("/api/dashboard", methods=["GET"], endpoint="api_dashboard_exec")
    def api_dashboard_exec():
        # Compatibilidad retroactiva para pantallas antiguas.
        return jsonify(_dashboard_operativo_data())

    @bp.route("/api/dashboard/control_home", methods=["GET"], endpoint="api_dashboard_control_home")
    def api_dashboard_control_home():
        fecha = (request.args.get("fecha") or "").strip() or _safe_today()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            fecha = _safe_today()

        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_catalogo_table(con)
            sedes = _dashboard_sedes_opts(con)
            agentes = _dashboard_agentes_opts(con)
            tipos_subtipos = _nvd_tipos_subtipos(con)
            vehs = _dashboard_vehiculos_simple(con, fecha)
            resumen = _novedades_resumen(con, fecha)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()

        base = _dashboard_operativo_data()
        alertas = _dashboard_alertas_criticas(base)

        user_name = (session.get("full_name") or session.get("username") or "").strip()
        if user_name and user_name.lower() not in {a.lower() for a in agentes}:
            agentes.insert(0, user_name)

        return jsonify({
            "ok": True,
            "fecha": fecha,
            "agente_actual": user_name,
            "sedes": sedes,
            "agentes": agentes,
            "tipos_subtipos": tipos_subtipos,
            "estados": list(NVD_ESTADOS),
            "vehiculos": vehs,
            "alertas": alertas,
            "resumen_novedades": resumen,
        })

    @bp.route("/api/dashboard/novedades_diarias_list", methods=["GET"], endpoint="api_dashboard_novedades_diarias_list")
    def api_dashboard_novedades_diarias_list():
        fecha = (request.args.get("fecha") or "").strip() or _safe_today()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400

        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            rows = con.execute("""
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(hora,'') AS hora,
                    COALESCE(agente,'') AS agente,
                    COALESCE(sede_codigo,'') AS sede_codigo,
                    COALESCE(tipo,'') AS tipo,
                    COALESCE(subtipo,'') AS subtipo,
                    COALESCE(observacion,'') AS observacion,
                    COALESCE(estado,'Informado') AS estado
                FROM novedades_diarias
                WHERE (
                        date(fecha) = date(?)
                        AND LOWER(COALESCE(estado,'')) IN ('informado', 'en revision', 'en proceso')
                    )
                   OR (
                        date(fecha) < date(?)
                        AND LOWER(COALESCE(estado,'')) IN ('informado', 'en revision', 'en proceso')
                    )
                   OR LOWER(COALESCE(estado,'')) IN ('resuelto', 'cerrado')
                ORDER BY date(fecha) DESC, COALESCE(hora,'') DESC, id DESC
                LIMIT 800
            """, (fecha, fecha)).fetchall()
            base_items = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "hora": (_row_value(r, "hora", "") or "").strip(),
                "agente": (_row_value(r, "agente", "") or "").strip(),
                "sede_codigo": (_row_value(r, "sede_codigo", "") or "").strip().upper(),
                "tipo": (_row_value(r, "tipo", "") or "").strip(),
                "subtipo": (_row_value(r, "subtipo", "") or "").strip(),
                "observacion": (_row_value(r, "observacion", "") or "").strip(),
                "estado": _norm_nvd_estado(_row_value(r, "estado", "Informado") or "Informado"),
            } for r in rows]
            pendientes_dia = []
            pendientes_acumulados = []
            resueltos_informados = []
            for it in base_items:
                est = (it.get("estado") or "").strip().lower()
                es_pendiente = est in ("informado", "en proceso")
                if es_pendiente:
                    if (it.get("fecha") or "") == fecha:
                        pendientes_dia.append(it)
                    else:
                        pendientes_acumulados.append(it)
                else:
                    resueltos_informados.append(it)
            resumen = _novedades_resumen(con, fecha)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({
            "ok": True,
            "fecha": fecha,
            "items": pendientes_dia,
            "pendientes_dia": pendientes_dia,
            "pendientes_acumulados": pendientes_acumulados,
            "resueltos_informados": resueltos_informados,
            "resumen": resumen,
        })

    @bp.route("/api/dashboard/novedades_diarias_historial", methods=["GET"], endpoint="api_dashboard_novedades_diarias_historial")
    def api_dashboard_novedades_diarias_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()
        limit = int(request.args.get("limit") or 100)
        limit = max(1, min(limit, 500))
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            sql = """
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(hora,'') AS hora,
                    COALESCE(agente,'') AS agente,
                    COALESCE(sede_codigo,'') AS sede_codigo,
                    COALESCE(tipo,'') AS tipo,
                    COALESCE(subtipo,'') AS subtipo,
                    COALESCE(observacion,'') AS observacion,
                    COALESCE(estado,'Informado') AS estado
                FROM novedades_diarias
                WHERE 1=1
                  AND LOWER(COALESCE(estado,'')) IN ('resuelto', 'cerrado')
            """
            params = []
            if desde:
                try:
                    datetime.strptime(desde, "%Y-%m-%d")
                    sql += " AND date(fecha) >= date(?) "
                    params.append(desde)
                except Exception:
                    pass
            if hasta:
                try:
                    datetime.strptime(hasta, "%Y-%m-%d")
                    sql += " AND date(fecha) <= date(?) "
                    params.append(hasta)
                except Exception:
                    pass
            sql += " ORDER BY date(fecha) DESC, COALESCE(hora,'') DESC, id DESC LIMIT ? "
            params.append(limit)
            rows = con.execute(sql, tuple(params)).fetchall()
            items = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "hora": (_row_value(r, "hora", "") or "").strip(),
                "agente": (_row_value(r, "agente", "") or "").strip(),
                "sede_codigo": (_row_value(r, "sede_codigo", "") or "").strip().upper(),
                "tipo": (_row_value(r, "tipo", "") or "").strip(),
                "subtipo": (_row_value(r, "subtipo", "") or "").strip(),
                "observacion": (_row_value(r, "observacion", "") or "").strip(),
                "estado": _norm_nvd_estado(_row_value(r, "estado", "Informado") or "Informado"),
            } for r in rows]
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "items": items})

    @bp.route("/api/dashboard/novedades_catalogo_add", methods=["POST"], endpoint="api_dashboard_novedades_catalogo_add")
    def api_dashboard_novedades_catalogo_add():
        payload = request.get_json(silent=True) or {}
        campo = (payload.get("campo") or "").strip().lower()
        valor = (payload.get("valor") or "").strip()
        tipo_ref = (payload.get("tipo_ref") or payload.get("tipo") or "").strip()
        if campo not in ("sede", "tipo", "subtipo"):
            return jsonify({"ok": False, "error": "Campo invalido"}), 400
        if not valor:
            return jsonify({"ok": False, "error": "Valor obligatorio"}), 400
        if campo == "subtipo" and not tipo_ref:
            return jsonify({"ok": False, "error": "Selecciona un tipo para agregar subtipo"}), 400
        if campo != "subtipo":
            tipo_ref = ""
        if campo == "sede":
            valor = valor.upper()
        if len(valor) > 80:
            valor = valor[:80]
        if len(tipo_ref) > 80:
            tipo_ref = tipo_ref[:80]

        con = get_db()
        try:
            _ensure_novedades_catalogo_table(con)
            exists = con.execute("""
                SELECT 1
                FROM dashboard_novedades_catalogo
                WHERE COALESCE(activo,1)=1
                  AND LOWER(COALESCE(grupo,'')) = LOWER(?)
                  AND LOWER(COALESCE(tipo_ref,'')) = LOWER(?)
                  AND LOWER(COALESCE(valor,'')) = LOWER(?)
                LIMIT 1
            """, (campo, tipo_ref, valor)).fetchone()
            if not exists:
                con.execute("""
                    INSERT INTO dashboard_novedades_catalogo(grupo, tipo_ref, valor, activo, creado_en)
                    VALUES (?, ?, ?, 1, ?)
                """, (campo, tipo_ref, valor, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                con.commit()
            tipos_subtipos = _nvd_tipos_subtipos(con)
            sedes = _dashboard_sedes_opts(con)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "tipos_subtipos": tipos_subtipos, "sedes": sedes})

    @bp.route("/api/dashboard/novedades_diarias_save", methods=["POST"], endpoint="api_dashboard_novedades_diarias_save")
    def api_dashboard_novedades_diarias_save():
        payload = request.get_json(silent=True) or {}
        nov_id = int(payload.get("id") or 0)
        fecha = (payload.get("fecha") or "").strip() or _safe_today()
        agente = (payload.get("agente") or "").strip()
        sede_codigo = (payload.get("sede_codigo") or "").strip().upper()
        tipo = (payload.get("tipo") or "").strip()
        subtipo = (payload.get("subtipo") or "").strip()
        observacion = (payload.get("observacion") or "").strip()
        estado = _norm_nvd_estado(payload.get("estado") or "Informado")
        if len(observacion) > 240:
            observacion = observacion[:240]

        if not agente:
            agente = (session.get("full_name") or session.get("username") or "").strip()
        if not agente:
            return jsonify({"ok": False, "error": "Agente obligatorio"}), 400
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400

        now = datetime.now()
        hora = now.strftime("%H:%M")
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_catalogo_table(con)
            tipos_subtipos = _nvd_tipos_subtipos(con)
            if tipo not in tipos_subtipos:
                con.close()
                return jsonify({"ok": False, "error": "Tipo invalido"}), 400
            if not subtipo:
                subtipo = (tipos_subtipos.get(tipo) or ["General"])[0]
            if subtipo not in (tipos_subtipos.get(tipo) or []):
                con.close()
                return jsonify({"ok": False, "error": "Subtipo invalido para el tipo elegido"}), 400
            if nov_id > 0:
                con.execute("""
                    UPDATE novedades_diarias
                    SET fecha=?,
                        agente=?,
                        sede_codigo=?,
                        tipo=?,
                        subtipo=?,
                        observacion=?,
                        estado=?,
                        actualizado_en=?
                    WHERE id=?
                """, (fecha, agente, sede_codigo, tipo, subtipo, observacion, estado, ts, nov_id))
                rid = nov_id
            else:
                cur = con.execute("""
                    INSERT INTO novedades_diarias
                        (fecha, hora, agente, sede_codigo, tipo, subtipo, observacion, estado, creado_en, actualizado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (fecha, hora, agente, sede_codigo, tipo, subtipo, observacion, estado, ts, ts))
                rid = int(cur.lastrowid or 0)
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "id": rid})

    @bp.route("/api/dashboard/novedades_diarias_estado", methods=["POST"], endpoint="api_dashboard_novedades_diarias_estado")
    def api_dashboard_novedades_diarias_estado():
        payload = request.get_json(silent=True) or {}
        nov_id = int(payload.get("id") or 0)
        estado = _norm_nvd_estado(payload.get("estado") or "Informado")
        if nov_id <= 0:
            return jsonify({"ok": False, "error": "ID invalido"}), 400
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            con.execute("""
                UPDATE novedades_diarias
                SET estado=?, actualizado_en=?
                WHERE id=?
            """, (estado, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nov_id))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/turnos_choferes_cfg_save", methods=["POST"], endpoint="api_dashboard_turnos_choferes_cfg_save")
    def api_dashboard_turnos_choferes_cfg_save():
        payload = request.get_json(silent=True) or {}
        tipo = (payload.get("tipo") or "").strip().lower()
        con = get_db()
        try:
            _ensure_dashboard_turnos_choferes_cfg(con)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if tipo == "mensual":
                mes = (payload.get("mes") or "").strip()
                chofer = (payload.get("chofer") or "").strip()
                if not mes or not chofer:
                    con.close()
                    return jsonify({"ok": False, "error": "Mes y chofer son obligatorios"}), 400
                con.execute("""
                    UPDATE dashboard_turnos_choferes_cfg
                    SET mes_mensual=?,
                        chofer_mensual=?,
                        actualizado_en=?
                    WHERE id=1
                """, (mes, chofer, ts))
            elif tipo == "semanal":
                desde = (payload.get("desde") or "").strip()
                hasta = (payload.get("hasta") or "").strip()
                chofer = (payload.get("chofer") or "").strip()
                if not desde or not hasta or not chofer:
                    con.close()
                    return jsonify({"ok": False, "error": "Desde, hasta y chofer son obligatorios"}), 400
                con.execute("""
                    UPDATE dashboard_turnos_choferes_cfg
                    SET semana_desde=?,
                        semana_hasta=?,
                        chofer_semanal=?,
                        actualizado_en=?
                    WHERE id=1
                """, (desde, hasta, chofer, ts))
            else:
                con.close()
                return jsonify({"ok": False, "error": "Tipo invalido"}), 400
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/vehiculos_cfg_save", methods=["POST"], endpoint="api_dashboard_vehiculos_cfg_save")
    def api_dashboard_vehiculos_cfg_save():
        payload = request.get_json(silent=True) or {}
        responsable = (payload.get("responsable_tactico") or "").strip()
        if not responsable:
            return jsonify({"ok": False, "error": "Responsable obligatorio"}), 400
        con = get_db()
        try:
            _ensure_dashboard_vehiculos_cfg(con)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                UPDATE dashboard_vehiculos_cfg
                SET responsable_tactico=?, actualizado_en=?
                WHERE id=1
            """, (responsable, ts))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/vehiculos_manual_save", methods=["POST"], endpoint="api_dashboard_vehiculos_manual_save")
    def api_dashboard_vehiculos_manual_save():
        payload = request.get_json(silent=True) or {}
        mov_id = int(payload.get("id") or 0)
        fecha = (payload.get("fecha") or "").strip()
        vehiculo = (payload.get("vehiculo") or "").strip()
        chofer = (payload.get("chofer") or "").strip()
        destino = (payload.get("destino") or "").strip()
        hora_salida = (payload.get("hora_salida") or "").strip()
        hora_regreso = (payload.get("hora_regreso_estimada") or "").strip()
        estado = (payload.get("estado") or "En uso").strip()
        combustible = (payload.get("combustible") or "").strip()
        materiales = (payload.get("materiales") or "").strip()
        agente_raw = payload.get("agente_traslado")
        if isinstance(agente_raw, list):
            agente_traslado = " | ".join([str(x).strip() for x in agente_raw if str(x).strip()])
        else:
            agente_traslado = str(agente_raw or "").strip()
        observaciones = (payload.get("observaciones") or "").strip()

        if not fecha:
            return jsonify({"ok": False, "error": "Fecha obligatoria"}), 400
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400
        if not vehiculo:
            return jsonify({"ok": False, "error": "Vehiculo obligatorio"}), 400
        if not chofer:
            return jsonify({"ok": False, "error": "Chofer obligatorio"}), 400
        if not destino:
            return jsonify({"ok": False, "error": "Destino obligatorio"}), 400
        if not hora_regreso:
            return jsonify({"ok": False, "error": "Regreso estimado obligatorio"}), 400

        con = get_db()
        try:
            _ensure_dashboard_vehiculos_manual_table(con)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if mov_id > 0:
                con.execute("""
                    UPDATE dashboard_vehiculos_manual
                    SET fecha=?,
                        vehiculo=?,
                        chofer=?,
                        destino=?,
                        hora_salida=?,
                        hora_regreso_estimada=?,
                        estado=?,
                        combustible=?,
                        materiales=?,
                        agente_traslado=?,
                        observaciones=?,
                        actualizado_en=?
                    WHERE id=?
                """, (
                    fecha, vehiculo, chofer, destino, hora_salida, hora_regreso,
                    estado, combustible, materiales, agente_traslado, observaciones, ts, mov_id
                ))
                pid = mov_id
            else:
                cur = con.execute("""
                    INSERT INTO dashboard_vehiculos_manual
                        (fecha, vehiculo, chofer, destino, hora_salida, hora_regreso_estimada, estado, combustible, materiales, agente_traslado, observaciones, actualizado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fecha, vehiculo, chofer, destino, hora_salida, hora_regreso,
                    estado, combustible, materiales, agente_traslado, observaciones, ts
                ))
                pid = int(cur.lastrowid or 0)
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "id": pid})

    @bp.route("/api/dashboard/turnos_choferes_ack", methods=["POST"], endpoint="api_dashboard_turnos_choferes_ack")
    def api_dashboard_turnos_choferes_ack():
        payload = request.get_json(silent=True) or {}
        tipo = (payload.get("tipo") or "").strip().lower()
        if tipo not in ("mensual", "semanal"):
            return jsonify({"ok": False, "error": "Tipo invalido"}), 400

        con = get_db()
        try:
            _ensure_dashboard_turnos_choferes_cfg(con)
            _ensure_dashboard_turnos_choferes_ack_table(con)
            row_cfg = con.execute("""
                SELECT
                    COALESCE(mes_mensual,'') AS mes_mensual,
                    COALESCE(chofer_mensual,'') AS chofer_mensual,
                    COALESCE(semana_desde,'') AS semana_desde,
                    COALESCE(semana_hasta,'') AS semana_hasta,
                    COALESCE(chofer_semanal,'') AS chofer_semanal
                FROM dashboard_turnos_choferes_cfg
                WHERE id=1
            """).fetchone()

            meses_l = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            today = date.today()

            if tipo == "mensual":
                mes_cfg = str(_row_value(row_cfg, "mes_mensual", "") or "").strip().lower()
                chofer = str(_row_value(row_cfg, "chofer_mensual", "") or "").strip()
                if mes_cfg not in meses_l:
                    mes_cfg = meses_l[today.month - 1]
                if not chofer:
                    return jsonify({"ok": False, "error": "Defina chofer mensual antes de aceptar"}), 400
                mm = (meses_l.index(mes_cfg) + 1) if mes_cfg in meses_l else today.month
                periodo_ref = f"{today.year}-{mm:02d}"
            else:
                desde = str(_row_value(row_cfg, "semana_desde", "") or "").strip()
                hasta = str(_row_value(row_cfg, "semana_hasta", "") or "").strip()
                chofer = str(_row_value(row_cfg, "chofer_semanal", "") or "").strip()
                if not (desde and hasta and chofer):
                    return jsonify({"ok": False, "error": "Defina turno semanal completo antes de aceptar"}), 400
                periodo_ref = f"{desde}|{hasta}"

            aceptado_por = (payload.get("aceptado_por") or "Intendencia").strip() or "Intendencia"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                INSERT INTO dashboard_turnos_choferes_ack(tipo, periodo_ref, chofer, aceptado_en, aceptado_por)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tipo, periodo_ref, chofer)
                DO UPDATE SET
                    aceptado_en=excluded.aceptado_en,
                    aceptado_por=excluded.aceptado_por
            """, (tipo, periodo_ref, chofer, ts, aceptado_por))
            con.commit()
            return jsonify({
                "ok": True,
                "tipo": tipo,
                "periodo": periodo_ref,
                "chofer": chofer,
                "aceptadoEn": ts,
                "aceptadoPor": aceptado_por,
            })
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()

    @bp.route("/api/dashboard/rotacion_limpieza_save", methods=["POST"], endpoint="api_dashboard_rotacion_limpieza_save")
    def api_dashboard_rotacion_limpieza_save():
        payload = request.get_json(silent=True) or {}
        sede = (payload.get("sede") or "").strip().upper()
        grupo = (payload.get("grupo") or "").strip().upper()
        agente = (payload.get("agente") or "").strip()
        turno = (payload.get("turno") or "Matutino").strip()
        mes_raw = (payload.get("mes") or "").strip().lower()

        if sede not in ("S01", "S08", "S13", "S14"):
            return jsonify({"ok": False, "error": "Sede invalida"}), 400
        if not agente:
            return jsonify({"ok": False, "error": "Agente obligatorio"}), 400
        if grupo and grupo not in ("GR1", "GR2", "GR3", "GR4"):
            return jsonify({"ok": False, "error": "Grupo invalido"}), 400

        meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        today = date.today()
        mm = meses.get(mes_raw, today.month)
        mes_ref = f"{today.year}-{mm:02d}"
        turno_norm = "Vespertino" if "vesp" in turno.lower() or "tarde" in turno.lower() else "Matutino"

        con = get_db()
        try:
            _ensure_dashboard_rotacion_limpieza_table(con)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                INSERT INTO dashboard_rotacion_limpieza (mes_ref, sede, turno, grupo, agente, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mes_ref, sede, turno)
                DO UPDATE SET
                    grupo = excluded.grupo,
                    agente = excluded.agente,
                    actualizado_en = excluded.actualizado_en
            """, (mes_ref, sede, turno_norm, grupo, agente, ts))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "mes_ref": mes_ref})

    @bp.route("/api/dashboard/vehiculos_manual_delete", methods=["POST"], endpoint="api_dashboard_vehiculos_manual_delete")
    def api_dashboard_vehiculos_manual_delete():
        payload = request.get_json(silent=True) or {}
        mov_id = int(payload.get("id") or 0)
        if mov_id <= 0:
            return jsonify({"ok": False, "error": "ID invalido"}), 400
        con = get_db()
        try:
            _ensure_dashboard_vehiculos_manual_table(con)
            con.execute("DELETE FROM dashboard_vehiculos_manual WHERE id=?", (mov_id,))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/novedades_obra_save", methods=["POST"], endpoint="api_dashboard_novedades_obra_save")
    def api_dashboard_novedades_obra_save():
        payload = request.get_json(silent=True) or {}
        fecha = (payload.get("fecha") or "").strip() or date.today().isoformat()
        texto = (payload.get("texto") or "").strip()
        urgente = 1 if int(payload.get("urgente") or 0) == 1 else 0
        tipo = (payload.get("tipo") or "novedad").strip().lower()
        estado = (payload.get("estado") or "nuevo").strip().lower()
        responsable = (payload.get("responsable") or "").strip()
        nov_id = int(payload.get("id") or 0)
        if not texto:
            return jsonify({"ok": False, "error": "Texto obligatorio"}), 400
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400

        con = get_db()
        try:
            _ensure_dashboard_novedades_obra_table(con)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if nov_id > 0:
                con.execute("""
                    UPDATE dashboard_novedades_obra
                    SET fecha = ?, texto = ?, urgente = ?, tipo = ?, estado = ?, responsable = ?
                    WHERE id = ?
                """, (fecha, texto, urgente, tipo, estado, responsable, nov_id))
                nid = nov_id
            else:
                cur = con.execute("""
                    INSERT INTO dashboard_novedades_obra (fecha, texto, urgente, tipo, estado, responsable, creado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (fecha, texto, urgente, tipo, estado, responsable, ts))
                nid = int(cur.lastrowid or 0)
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "id": nid})

    @bp.route("/api/dashboard/novedades_obra_list", methods=["GET"], endpoint="api_dashboard_novedades_obra_list")
    def api_dashboard_novedades_obra_list():
        fecha = (request.args.get("fecha") or "").strip() or date.today().isoformat()
        tipo_q = (request.args.get("tipo") or "").strip().lower()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400
        con = get_db()
        try:
            _ensure_dashboard_novedades_obra_table(con)
            sql = """
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(texto,'') AS texto,
                    COALESCE(urgente,0) AS urgente,
                    COALESCE(tipo,'novedad') AS tipo,
                    COALESCE(estado,'nuevo') AS estado,
                    COALESCE(responsable,'') AS responsable
                FROM dashboard_novedades_obra
                WHERE date(fecha) = date(?)
            """
            params = [fecha]
            if tipo_q and tipo_q != "todos":
                sql += " AND LOWER(COALESCE(tipo,'novedad')) = ? "
                params.append(tipo_q)
            sql += " ORDER BY id DESC LIMIT 40 "
            rows = con.execute(sql, tuple(params)).fetchall()
            items = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "texto": (_row_value(r, "texto", "") or "").strip(),
                "urgente": int(_row_value(r, "urgente", 0) or 0),
                "tipo": (_row_value(r, "tipo", "novedad") or "novedad").strip(),
                "estado": (_row_value(r, "estado", "nuevo") or "nuevo").strip(),
                "responsable": (_row_value(r, "responsable", "") or "").strip(),
            } for r in rows if (_row_value(r, "texto", "") or "").strip()]
            con.close()
            return jsonify({"ok": True, "fecha": fecha, "items": items})
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/api/dashboard/novedades_obra_historial_full", methods=["GET"], endpoint="api_dashboard_novedades_obra_historial_full")
    def api_dashboard_novedades_obra_historial_full():
        sede_q = (request.args.get("sede") or "").strip().upper()
        tipo_q = (request.args.get("tipo") or "").strip().lower()
        estado_q = (request.args.get("estado") or "").strip().lower()
        resp_q = (request.args.get("responsable") or "").strip().lower()
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()

        con = get_db()
        try:
            _ensure_dashboard_novedades_obra_table(con)
            sql = """
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(texto,'') AS texto,
                    COALESCE(urgente,0) AS urgente,
                    COALESCE(tipo,'novedad') AS tipo,
                    COALESCE(estado,'nuevo') AS estado,
                    COALESCE(responsable,'') AS responsable,
                    COALESCE(creado_en,'') AS creado_en
                FROM dashboard_novedades_obra
                WHERE 1=1
            """
            params = []

            if desde:
                try:
                    datetime.strptime(desde, "%Y-%m-%d")
                    sql += " AND date(fecha) >= date(?) "
                    params.append(desde)
                except Exception:
                    pass
            if hasta:
                try:
                    datetime.strptime(hasta, "%Y-%m-%d")
                    sql += " AND date(fecha) <= date(?) "
                    params.append(hasta)
                except Exception:
                    pass
            if tipo_q and tipo_q != "todos":
                sql += " AND LOWER(COALESCE(tipo,'novedad')) = ? "
                params.append(tipo_q)
            if estado_q and estado_q != "todos":
                sql += " AND LOWER(COALESCE(estado,'nuevo')) = ? "
                params.append(estado_q)
            if resp_q and resp_q != "todos":
                sql += " AND LOWER(COALESCE(responsable,'')) = ? "
                params.append(resp_q)

            # filtro de sede textual dentro del texto (ej: S01, S12)
            if sede_q and sede_q != "TODAS":
                sql += " AND UPPER(COALESCE(texto,'')) LIKE ? "
                params.append(f"%{sede_q}%")

            sql += " ORDER BY date(fecha) DESC, id DESC LIMIT 1000 "
            rows = con.execute(sql, tuple(params)).fetchall()

            items = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "texto": (_row_value(r, "texto", "") or "").strip(),
                "urgente": int(_row_value(r, "urgente", 0) or 0),
                "tipo": (_row_value(r, "tipo", "novedad") or "novedad").strip(),
                "estado": (_row_value(r, "estado", "nuevo") or "nuevo").strip(),
                "responsable": (_row_value(r, "responsable", "") or "").strip(),
                "creado_en": (_row_value(r, "creado_en", "") or "").strip(),
            } for r in rows]

            con.close()
            return jsonify({"ok": True, "items": items})
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/api/dashboard/novedades_obra_delete", methods=["POST"], endpoint="api_dashboard_novedades_obra_delete")
    def api_dashboard_novedades_obra_delete():
        payload = request.get_json(silent=True) or {}
        nov_id = int(payload.get("id") or 0)
        if nov_id <= 0:
            return jsonify({"ok": False, "error": "ID invalido"}), 400
        con = get_db()
        try:
            _ensure_dashboard_novedades_obra_table(con)
            con.execute("DELETE FROM dashboard_novedades_obra WHERE id = ?", (nov_id,))
            con.commit()
            con.close()
            return jsonify({"ok": True})
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/api/dashboard/materiales_quick_create", methods=["POST"], endpoint="api_dashboard_materiales_quick_create")
    def api_dashboard_materiales_quick_create():
        payload = request.get_json(silent=True) or {}
        pedido_id = int(payload.get("pedido_id") or 0)
        fecha = (payload.get("fecha") or "").strip()
        estado = (payload.get("estado") or "Pedir").strip()
        detalle = (payload.get("detalle") or "").strip()
        sede = (payload.get("sede") or "").strip()
        solicitante = (payload.get("solicitante") or "Dashboard").strip()

        if not fecha:
            return jsonify({"ok": False, "error": "Fecha obligatoria"}), 400

        try:
            # valida YYYY-MM-DD
            datetime.strptime(fecha, "%Y-%m-%d")
        except Exception:
            return jsonify({"ok": False, "error": "Fecha invalida"}), 400

        def _norm_estado(e):
            u = (e or "").strip().upper()
            if any(k in u for k in ("GENERADO", "PENDIENTE_INTENDENCIA", "PEDIR", "PENDIENTE", "NUEVO")):
                return "Generado"
            if any(k in u for k in ("EN COMPRAS", "COMPRA", "AUTORIZADO", "PEDIDO")):
                return "En compras"
            if any(k in u for k in ("RECIBIDO",)):
                return "Recibido"
            if any(k in u for k in ("CERRADO", "ENTREGADO", "CIERRE")):
                return "Cerrado"
            return "Generado"

        estado = _norm_estado(estado)
        est_u = estado.upper()

        prioridad = "Media"
        if est_u == "GENERADO":
            prioridad = "Alta"
        elif est_u == "CERRADO":
            prioridad = "Baja"

        con = get_db()
        try:
            cols = _table_cols(con, "calendario_pedidos")
            if not cols:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS calendario_pedidos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fecha TEXT NOT NULL,
                        sede TEXT,
                        solicitante TEXT,
                        detalle TEXT,
                        prioridad TEXT DEFAULT 'Media',
                        estado TEXT DEFAULT 'Pedir'
                    )
                """)
                con.commit()
                cols = _table_cols(con, "calendario_pedidos")
            for c in ("fecha_generado", "fecha_autorizado", "fecha_recibido", "fecha_cerrado"):
                if c not in cols:
                    try:
                        con.execute(f"ALTER TABLE calendario_pedidos ADD COLUMN {c} TEXT")
                    except Exception:
                        pass
            con.commit()
            cols = _table_cols(con, "calendario_pedidos")

            con.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_materiales_historial(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido_id INTEGER,
                    fecha_evento TEXT,
                    estado TEXT,
                    detalle TEXT,
                    sede TEXT,
                    usuario TEXT
                )
            """)

            if pedido_id > 0:
                sets = []
                params = []
                if "fecha" in cols:
                    sets.append("fecha=?")
                    params.append(fecha)
                if "estado" in cols:
                    sets.append("estado=?")
                    params.append(estado)
                if "prioridad" in cols:
                    sets.append("prioridad=?")
                    params.append(prioridad)
                if "detalle" in cols and detalle:
                    sets.append("detalle=?")
                    params.append(detalle)
                if "sede" in cols and sede:
                    sets.append("sede=?")
                    params.append(sede)
                if "solicitante" in cols and solicitante:
                    sets.append("solicitante=?")
                    params.append(solicitante)
                ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if estado == "Generado" and "fecha_generado" in cols:
                    sets.append("fecha_generado=COALESCE(fecha_generado, ?)")
                    params.append(ts_now)
                if estado == "En compras" and "fecha_autorizado" in cols:
                    sets.append("fecha_autorizado=?")
                    params.append(ts_now)
                if estado == "Recibido" and "fecha_recibido" in cols:
                    sets.append("fecha_recibido=?")
                    params.append(ts_now)
                if estado == "Cerrado" and "fecha_cerrado" in cols:
                    sets.append("fecha_cerrado=?")
                    params.append(ts_now)
                if sets:
                    params.append(pedido_id)
                    con.execute(f"UPDATE calendario_pedidos SET {', '.join(sets)} WHERE id=?", params)
                row = con.execute("""
                    SELECT id, COALESCE(detalle,'') AS detalle, COALESCE(sede,'') AS sede
                    FROM calendario_pedidos
                    WHERE id=?
                """, (pedido_id,)).fetchone()
                pid = int(_row_value(row, "id", 0) or 0)
                det_hist = detalle or (_row_value(row, "detalle", "") or "").strip()
                sede_hist = sede or (_row_value(row, "sede", "") or "").strip()
            else:
                # Un pedido debe existir una sola vez: si ya hay uno abierto
                # con mismo sede+detalle, se actualiza ese mismo.
                row_exist = con.execute("""
                    SELECT id
                    FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                      AND UPPER(COALESCE(estado,'GENERADO')) <> 'CERRADO'
                      AND LOWER(TRIM(COALESCE(sede,''))) = LOWER(TRIM(?))
                      AND LOWER(TRIM(COALESCE(detalle,''))) = LOWER(TRIM(?))
                    ORDER BY id DESC
                    LIMIT 1
                """, (sede, detalle)).fetchone()
                exist_id = int(_row_value(row_exist, "id", 0) or 0)
                if exist_id > 0:
                    sets = []
                    params = []
                    if "fecha" in cols:
                        sets.append("fecha=?")
                        params.append(fecha)
                    if "estado" in cols:
                        sets.append("estado=?")
                        params.append(estado)
                    if "prioridad" in cols:
                        sets.append("prioridad=?")
                        params.append(prioridad)
                    if "solicitante" in cols:
                        sets.append("solicitante=?")
                        params.append(solicitante)
                    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if estado == "Generado" and "fecha_generado" in cols:
                        sets.append("fecha_generado=COALESCE(fecha_generado, ?)")
                        params.append(ts_now)
                    if estado == "En compras" and "fecha_autorizado" in cols:
                        sets.append("fecha_autorizado=?")
                        params.append(ts_now)
                    if estado == "Recibido" and "fecha_recibido" in cols:
                        sets.append("fecha_recibido=?")
                        params.append(ts_now)
                    if estado == "Cerrado" and "fecha_cerrado" in cols:
                        sets.append("fecha_cerrado=?")
                        params.append(ts_now)
                    if sets:
                        params.append(exist_id)
                        con.execute(f"UPDATE calendario_pedidos SET {', '.join(sets)} WHERE id=?", params)
                    pid = exist_id
                    det_hist = detalle
                    sede_hist = sede
                else:
                    data = {"fecha": fecha}
                    if "sede" in cols:
                        data["sede"] = sede
                    if "solicitante" in cols:
                        data["solicitante"] = solicitante
                    if "detalle" in cols:
                        data["detalle"] = detalle
                    if "prioridad" in cols:
                        data["prioridad"] = prioridad
                    if "estado" in cols:
                        data["estado"] = estado
                    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if "fecha_generado" in cols:
                        data["fecha_generado"] = ts_now if estado == "Generado" else None
                    if "fecha_autorizado" in cols:
                        data["fecha_autorizado"] = ts_now if estado == "En compras" else None
                    if "fecha_recibido" in cols:
                        data["fecha_recibido"] = ts_now if estado == "Recibido" else None
                    if "fecha_cerrado" in cols:
                        data["fecha_cerrado"] = ts_now if estado == "Cerrado" else None

                    fields = list(data.keys())
                    placeholders = ",".join(["?"] * len(fields))
                    cur = con.execute(
                        f"INSERT INTO calendario_pedidos ({','.join(fields)}) VALUES ({placeholders})",
                        [data[k] for k in fields],
                    )
                    pid = int(cur.lastrowid or 0)
                    det_hist = detalle
                    sede_hist = sede

            con.execute("""
                INSERT INTO dashboard_materiales_historial
                    (pedido_id, fecha_evento, estado, detalle, sede, usuario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), estado, det_hist, sede_hist, solicitante))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500

        con.close()
        return jsonify({"ok": True, "pedido_id": pid})

    @bp.route("/api/dashboard/materiales_flow", methods=["GET"], endpoint="api_dashboard_materiales_flow")
    def api_dashboard_materiales_flow():
        con = get_db()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_materiales_historial(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido_id INTEGER,
                    fecha_evento TEXT,
                    estado TEXT,
                    detalle TEXT,
                    sede TEXT,
                    usuario TEXT
                )
            """)
            con.commit()
        except Exception:
            pass

        abiertos = []
        historial = []
        panel = []
        cerrados_hoy = []
        sedes = []
        try:
            if _table_exists(con, "calendario_pedidos"):
                rows = con.execute("""
                    SELECT
                        id,
                        COALESCE(fecha,'') AS fecha,
                        COALESCE(sede,'') AS sede,
                        COALESCE(detalle,'') AS detalle,
                        COALESCE(estado,'Generado') AS estado
                    FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                      AND UPPER(COALESCE(estado,'GENERADO')) <> 'CERRADO'
                      AND TRIM(COALESCE(sede,'')) <> ''
                      AND TRIM(COALESCE(detalle,'')) <> ''
                    ORDER BY date(fecha) DESC, id DESC
                    LIMIT 120
                """).fetchall()
                dedup = {}
                for r in rows:
                    sede_v = (_row_value(r, "sede", "") or "").strip()
                    det_v = (_row_value(r, "detalle", "") or "").strip()
                    key = (sede_v.lower() + "|" + det_v.lower()).strip("|")
                    item = {
                        "id": int(_row_value(r, "id", 0) or 0),
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "sede": sede_v,
                        "detalle": det_v,
                        "estado": (_row_value(r, "estado", "Generado") or "Generado").strip(),
                    }
                    # Mantener solo el registro mas nuevo por pedido logico.
                    if key not in dedup or item["id"] > dedup[key]["id"]:
                        dedup[key] = item
                abiertos = sorted(list(dedup.values()), key=lambda x: (x.get("fecha", ""), x.get("id", 0)), reverse=True)
                rows_panel = con.execute("""
                    SELECT
                        id,
                        COALESCE(fecha,'') AS fecha,
                        COALESCE(sede,'') AS sede,
                        COALESCE(detalle,'') AS detalle,
                        COALESCE(estado,'Generado') AS estado
                    FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                    ORDER BY date(fecha) DESC, id DESC
                    LIMIT 80
                """).fetchall()
                for r in rows_panel:
                    panel.append({
                        "id": int(_row_value(r, "id", 0) or 0),
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "sede": (_row_value(r, "sede", "") or "").strip(),
                        "detalle": (_row_value(r, "detalle", "") or "").strip(),
                        "estado": (_row_value(r, "estado", "Generado") or "Generado").strip(),
                    })
                if _table_exists(con, "sedes_mpd"):
                    rows_s = con.execute("""
                        SELECT UPPER(COALESCE(codigo,'')) AS codigo
                        FROM sedes_mpd
                        WHERE TRIM(COALESCE(codigo,'')) <> ''
                        ORDER BY codigo
                    """).fetchall()
                    sedes = [(_row_value(r, "codigo", "") or "").strip() for r in rows_s if (_row_value(r, "codigo", "") or "").strip()]
                rows_c_h = con.execute("""
                    SELECT
                        pedido_id,
                        COALESCE(fecha_evento,'') AS fecha_evento,
                        COALESCE(estado,'') AS estado,
                        COALESCE(detalle,'') AS detalle,
                        COALESCE(sede,'') AS sede
                    FROM dashboard_materiales_historial
                    WHERE UPPER(COALESCE(estado,'')) IN ('CERRADO','ENTREGADO')
                      AND date(fecha_evento) = date('now')
                    ORDER BY id DESC
                    LIMIT 50
                """).fetchall()
                seen = set()
                for r in rows_c_h:
                    pid = int(_row_value(r, "pedido_id", 0) or 0)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    cerrados_hoy.append({
                        "pedido_id": pid,
                        "fecha_evento": (_row_value(r, "fecha_evento", "") or "").strip(),
                        "estado": (_row_value(r, "estado", "") or "").strip(),
                        "detalle": (_row_value(r, "detalle", "") or "").strip(),
                        "sede": (_row_value(r, "sede", "") or "").strip(),
                    })
        except Exception:
            pass

        try:
            rows_h = con.execute("""
                SELECT
                    pedido_id,
                    COALESCE(fecha_evento,'') AS fecha_evento,
                    COALESCE(estado,'') AS estado,
                    COALESCE(detalle,'') AS detalle,
                    COALESCE(sede,'') AS sede
                FROM dashboard_materiales_historial
                ORDER BY id DESC
                LIMIT 80
            """).fetchall()
            for r in rows_h:
                historial.append({
                    "pedido_id": int(_row_value(r, "pedido_id", 0) or 0),
                    "fecha_evento": (_row_value(r, "fecha_evento", "") or "").strip(),
                    "estado": (_row_value(r, "estado", "") or "").strip(),
                    "detalle": (_row_value(r, "detalle", "") or "").strip(),
                    "sede": (_row_value(r, "sede", "") or "").strip(),
                })
        except Exception:
            pass

        con.close()
        if not sedes:
            sedes = [f"S{str(i).zfill(2)}" for i in range(1, 21)]
        return jsonify({"abiertos": abiertos, "historial": historial, "panel": panel, "cerrados_hoy": cerrados_hoy, "sedes": sedes})

    @bp.route("/api/dashboard/materiales_flow/reset", methods=["POST"], endpoint="api_dashboard_materiales_flow_reset")
    def api_dashboard_materiales_flow_reset():
        con = get_db()
        try:
            if _table_exists(con, "calendario_pedidos"):
                con.execute("""
                    DELETE FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                """)
            if _table_exists(con, "dashboard_materiales_historial"):
                con.execute("DELETE FROM dashboard_materiales_historial")
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/materiales_historial_full", methods=["GET"], endpoint="api_dashboard_materiales_historial_full")
    def api_dashboard_materiales_historial_full():
        con = get_db()
        rows_out = []
        resumen = []
        try:
            if _table_exists(con, "calendario_pedidos"):
                cols = _table_cols(con, "calendario_pedidos")
                sel = [
                    "id",
                    "COALESCE(fecha,'') AS fecha",
                    "COALESCE(sede,'') AS sede",
                    "COALESCE(detalle,'') AS detalle",
                    "COALESCE(estado,'Generado') AS estado",
                    "COALESCE(solicitante,'') AS solicitante",
                ]
                for c in ("fecha_generado", "fecha_autorizado", "fecha_recibido", "fecha_cerrado"):
                    if c in cols:
                        sel.append(f"COALESCE({c},'') AS {c}")
                    else:
                        sel.append(f"'' AS {c}")
                rows = con.execute(f"""
                    SELECT {", ".join(sel)}
                    FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                    ORDER BY id DESC
                    LIMIT 1200
                """).fetchall()
                for r in rows:
                    rows_out.append({
                        "id": int(_row_value(r, "id", 0) or 0),
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "sede": (_row_value(r, "sede", "") or "").strip(),
                        "detalle": (_row_value(r, "detalle", "") or "").strip(),
                        "estado": (_row_value(r, "estado", "Generado") or "Generado").strip(),
                        "fecha_generado": (_row_value(r, "fecha_generado", "") or "").strip(),
                        "fecha_autorizado": (_row_value(r, "fecha_autorizado", "") or "").strip(),
                        "fecha_recibido": (_row_value(r, "fecha_recibido", "") or "").strip(),
                        "fecha_cerrado": (_row_value(r, "fecha_cerrado", "") or "").strip(),
                    })
                rows_res = con.execute("""
                    SELECT
                        UPPER(COALESCE(sede,'S/D')) AS sede,
                        COUNT(*) AS total
                    FROM calendario_pedidos
                    WHERE UPPER(COALESCE(solicitante,'')) = 'DASHBOARD'
                    GROUP BY UPPER(COALESCE(sede,'S/D'))
                    ORDER BY sede
                """).fetchall()
                for r in rows_res:
                    resumen.append({
                        "sede": (_row_value(r, "sede", "S/D") or "S/D").strip(),
                        "total": int(_row_value(r, "total", 0) or 0),
                    })
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e), "rows": [], "resumen": []}), 500
        con.close()
        return jsonify({"ok": True, "rows": rows_out, "resumen": resumen})

    def _dashboard_sede_estado_read(con):
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_sede_estado(
                    sede_codigo TEXT PRIMARY KEY,
                    relevamiento INTEGER DEFAULT 0,
                    obra_terminada INTEGER DEFAULT 0,
                    matafuegos_recarga INTEGER DEFAULT 0,
                    carteleria INTEGER DEFAULT 0,
                    luces_emergencia INTEGER DEFAULT 0,
                    plano_evac INTEGER DEFAULT 0,
                    orden_limpieza INTEGER DEFAULT 0,
                    senalizacion INTEGER DEFAULT 0,
                    accesibilidad INTEGER DEFAULT 0,
                    riesgo_electrico INTEGER DEFAULT 0,
                    actualizado_en TEXT DEFAULT (datetime('now'))
                )
            """)
            con.commit()
        except Exception:
            pass

        sedes = []
        if _table_exists(con, "sedes_mpd"):
            try:
                rows_s = con.execute("""
                    SELECT UPPER(COALESCE(codigo,'')) AS codigo
                    FROM sedes_mpd
                    WHERE TRIM(COALESCE(codigo,'')) <> ''
                    ORDER BY codigo
                """).fetchall()
                sedes = [(_row_value(r, "codigo", "") or "").strip() for r in rows_s]
            except Exception:
                sedes = []
        if not sedes:
            sedes = [f"S{str(i).zfill(2)}" for i in range(1, 21)]

        for c in sedes:
            if c:
                try:
                    con.execute("INSERT OR IGNORE INTO dashboard_sede_estado(sede_codigo) VALUES (?)", (c,))
                except Exception:
                    pass
        con.commit()

        rows = con.execute(f"""
            SELECT
                UPPER(COALESCE(sede_codigo,'')) AS sede_codigo,
                {",".join([f"COALESCE({v},0) AS {v}" for v in SEDE_ESTADO_VARS])},
                COALESCE(actualizado_en, '') AS actualizado_en
            FROM dashboard_sede_estado
            ORDER BY sede_codigo
        """).fetchall()

        items = []
        for r in rows:
            vals = {v: int(_row_value(r, v, 0) or 0) for v in SEDE_ESTADO_VARS}
            pts = sum(1 if int(vals.get(v, 0)) > 0 else 0 for v in SEDE_ESTADO_VARS)
            pct = int(round((pts / 10.0) * 100))
            items.append({
                "sede": (_row_value(r, "sede_codigo", "") or "").strip() or "-",
                "values": vals,
                "puntos": pts,
                "pct": pct,
                "actualizadoEn": (_row_value(r, "actualizado_en", "") or "").strip(),
            })

        return sedes, items

    @bp.route("/api/dashboard_sede_estado", methods=["GET"], endpoint="api_dashboard_sede_estado")
    def api_dashboard_sede_estado():
        con = get_db()
        sedes, items = _dashboard_sede_estado_read(con)
        con.close()
        return jsonify({
            "variables": [{"key": v, "label": SEDE_ESTADO_LABELS.get(v, v)} for v in SEDE_ESTADO_VARS],
            "sedes": [s for s in sedes if s],
            "items": items,
        })

    @bp.route("/api/dashboard_sede_estado/<sede_codigo>", methods=["POST"], endpoint="api_dashboard_sede_estado_save")
    def api_dashboard_sede_estado_save(sede_codigo):
        sede = (sede_codigo or "").strip().upper()
        if not sede:
            return jsonify({"ok": False, "error": "Sede invalida"}), 400

        payload = request.get_json(silent=True) or {}
        incoming = payload.get("values", payload)
        if not isinstance(incoming, dict):
            return jsonify({"ok": False, "error": "Payload invalido"}), 400

        vals = {}
        for v in SEDE_ESTADO_VARS:
            raw = incoming.get(v, 0)
            vals[v] = 1 if str(raw).strip().lower() in ("1", "true", "si", "on", "x") else 0

        con = get_db()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_sede_estado(
                    sede_codigo TEXT PRIMARY KEY,
                    relevamiento INTEGER DEFAULT 0,
                    obra_terminada INTEGER DEFAULT 0,
                    matafuegos_recarga INTEGER DEFAULT 0,
                    carteleria INTEGER DEFAULT 0,
                    luces_emergencia INTEGER DEFAULT 0,
                    plano_evac INTEGER DEFAULT 0,
                    orden_limpieza INTEGER DEFAULT 0,
                    senalizacion INTEGER DEFAULT 0,
                    accesibilidad INTEGER DEFAULT 0,
                    riesgo_electrico INTEGER DEFAULT 0,
                    actualizado_en TEXT DEFAULT (datetime('now'))
                )
            """)
            con.execute("INSERT OR IGNORE INTO dashboard_sede_estado(sede_codigo) VALUES (?)", (sede,))
            set_sql = ", ".join([f"{v}=?" for v in SEDE_ESTADO_VARS])
            params = [vals[v] for v in SEDE_ESTADO_VARS]
            params.extend([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sede])
            con.execute(f"""
                UPDATE dashboard_sede_estado
                SET {set_sql}, actualizado_en=?
                WHERE sede_codigo=?
            """, params)
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500

        con.close()
        return jsonify({"ok": True, "sede": sede, "values": vals})

    return bp
