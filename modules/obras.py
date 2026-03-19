from datetime import date
import sqlite3
import unicodedata

from flask import render_template, request, redirect, url_for, flash, session


def register_obras(app, get_db, rebuild_eventos_obras):
    estimaciones_catalogo = [
        {"label": "Durlock", "keywords": ("durlock", "durlok"), "dias_min": 4.0, "dias_max": 8.0, "personas": 2.0, "materiales": 9.0},
        {"label": "Pintura", "keywords": ("pintura",), "dias_min": 2.0, "dias_max": 4.0, "personas": 1.5, "materiales": 4.0},
        {"label": "Plomeria banos", "keywords": ("plomeria", "banos", "bano"), "dias_min": 2.0, "dias_max": 2.0, "personas": 1.5, "materiales": 4.0},
        {"label": "Humedad techos", "keywords": ("humedad",), "dias_min": 3.0, "dias_max": 6.0, "personas": 2.0, "materiales": 6.0},
        {"label": "Movimiento mobiliario", "keywords": ("movimiento mobiliario", "mobiliario"), "dias_min": 1.0, "dias_max": 1.0, "personas": 2.0, "materiales": 1.5},
        {"label": "Desinfeccion", "keywords": ("desinfeccion",), "dias_min": 1.0, "dias_max": 1.0, "personas": 1.0, "materiales": 1.0},
        {"label": "Albanileria", "keywords": ("albanileria",), "dias_min": 4.0, "dias_max": 8.0, "personas": 2.0, "materiales": 8.0},
        {"label": "Cambio led/balastro/foco", "keywords": ("led", "balastro", "foco"), "dias_min": 1.0, "dias_max": 1.0, "personas": 1.0, "materiales": 2.0},
        {"label": "Electricidad tomas/cortos", "keywords": ("agregar tomas", "toma", "corto", "electr"), "dias_min": 2.0, "dias_max": 4.0, "personas": 1.5, "materiales": 3.0},
        {"label": "Armar puesto electrico", "keywords": ("armar puesto",), "dias_min": 4.0, "dias_max": 6.0, "personas": 2.0, "materiales": 5.0},
        {"label": "Impermeabilizacion", "keywords": ("imperme",), "dias_min": 3.0, "dias_max": 6.0, "personas": 2.0, "materiales": 7.0},
        {"label": "Destrancar caneria", "keywords": ("destrancar", "caneria", "caneria"), "dias_min": 2.0, "dias_max": 2.0, "personas": 1.5, "materiales": 2.0},
        {"label": "Limpiar canaleta", "keywords": ("canaleta",), "dias_min": 2.0, "dias_max": 2.0, "personas": 1.5, "materiales": 1.5},
        {"label": "Colocar/service aire", "keywords": ("aire acondicionado", "service aire", "colocar aire"), "dias_min": 2.0, "dias_max": 2.0, "personas": 2.0, "materiales": 4.0},
        {"label": "Armar repisa", "keywords": ("repisa",), "dias_min": 3.0, "dias_max": 3.0, "personas": 1.5, "materiales": 2.0},
        {"label": "Armar mueble", "keywords": ("armar mueble", "mueble"), "dias_min": 5.0, "dias_max": 7.0, "personas": 2.0, "materiales": 6.0},
    ]

    def _normalizar_texto(texto):
        raw = (texto or "").strip().lower()
        if not raw:
            return ""
        norm = unicodedata.normalize("NFKD", raw)
        return "".join(c for c in norm if not unicodedata.combining(c))

    def _estimar_intervencion(tipo, titulo, descripcion, prioridad):
        texto = " ".join([
            _normalizar_texto(tipo),
            _normalizar_texto(titulo),
            _normalizar_texto(descripcion),
        ]).strip()

        base = {"label": "General", "dias_min": 2.0, "dias_max": 3.0, "personas": 1.5, "materiales": 3.0}
        for item in estimaciones_catalogo:
            if any(k in texto for k in item["keywords"]):
                base = item
                break

        prioridad_norm = _normalizar_texto(prioridad).upper()
        factor_prioridad = {"ALTA": 1.20, "MEDIA": 1.00, "BAJA": 0.85}.get(prioridad_norm, 1.0)

        dias = ((float(base["dias_min"]) + float(base["dias_max"])) / 2.0) * factor_prioridad
        horas_tarea = dias * 8.0
        personas = float(base["personas"])
        horas_persona = horas_tarea * personas
        materiales = float(base["materiales"]) * factor_prioridad

        return {
            "tipo_estandar": base["label"],
            "dias": dias,
            "horas_tarea": horas_tarea,
            "personas": personas,
            "horas_persona": horas_persona,
            "materiales": materiales,
        }

    interv_tipos = [
        ("MATERIAL_DEJADO", "Material dejado"),
        ("HERRAMIENTA_DEJADA", "Herramienta dejada"),
        ("TAREA_REALIZADA", "Tarea realizada"),
        ("TRASLADO_PENDIENTE", "Traslado pendiente"),
        ("OTRO", "Otro"),
    ]
    interv_tipo_labels = {k: v for k, v in interv_tipos}
    interv_estados = [
        ("PENDIENTE", "Pendiente"),
        ("RESUELTO", "Resuelto"),
    ]
    interv_estado_labels = {k: v for k, v in interv_estados}

    def _sanitize_interv_tipo(raw):
        v = (raw or "").strip().upper()
        return v if v in interv_tipo_labels else ""

    def _sanitize_interv_estado(raw):
        v = (raw or "").strip().upper()
        return v if v in interv_estado_labels else ""

    def _sanitize_interv_fecha(raw):
        v = (raw or "").strip()
        if not v:
            return ""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            return ""

    def _ensure_intervenciones_table(con):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS obras_intervenciones_diarias(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                codigo_sede TEXT NOT NULL,
                tipo TEXT NOT NULL,
                detalle TEXT NOT NULL,
                autorizado_por TEXT,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                observacion TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_obras_intervenciones_fecha ON obras_intervenciones_diarias(fecha)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_obras_intervenciones_sede ON obras_intervenciones_diarias(codigo_sede)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_obras_intervenciones_estado ON obras_intervenciones_diarias(estado)"
        )
        con.commit()

        cols = [r["name"] for r in con.execute("PRAGMA table_info(obras_intervenciones_diarias)").fetchall()]
        if "autorizado_por" not in cols:
            con.execute("ALTER TABLE obras_intervenciones_diarias ADD COLUMN autorizado_por TEXT")
        if "estado" not in cols:
            con.execute("ALTER TABLE obras_intervenciones_diarias ADD COLUMN estado TEXT NOT NULL DEFAULT 'PENDIENTE'")
        if "observacion" not in cols:
            con.execute("ALTER TABLE obras_intervenciones_diarias ADD COLUMN observacion TEXT")
        if "created_at" not in cols:
            con.execute("ALTER TABLE obras_intervenciones_diarias ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'))")
        if "updated_at" not in cols:
            con.execute("ALTER TABLE obras_intervenciones_diarias ADD COLUMN updated_at TEXT")
        con.commit()

    def _interv_redirect_args():
        prioridad = (request.args.get("prioridad") or "").strip().upper()
        if prioridad not in ("ALTA", "MEDIA", "BAJA"):
            prioridad = ""

        return {
            "sede": request.args.get("sede") or "",
            "estado": (request.args.get("estado") or "").strip().upper(),
            "prioridad": prioridad,
            "iv_sede": request.args.get("iv_sede") or "",
            "iv_estado": _sanitize_interv_estado(request.args.get("iv_estado")),
            "iv_tipo": _sanitize_interv_tipo(request.args.get("iv_tipo")),
            "iv_fecha": _sanitize_interv_fecha(request.args.get("iv_fecha")),
            "panel": (request.args.get("panel") or "panel-intervenciones").strip() or "panel-intervenciones",
        }

    @app.route("/obras", methods=["GET", "POST"], endpoint="obras_home")
    def obras_home():
        con = get_db()
        _ensure_intervenciones_table(con)

        # listado de sedes para el combo
        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        # si viene ?sede=S01 en la URL, filtramos
        cod_filtro = request.args.get("sede") or ""
        estado_filtro = (request.args.get("estado") or "").strip().upper()
        prioridad_filtro = (request.args.get("prioridad") or "").strip().upper()
        if prioridad_filtro not in ("ALTA", "MEDIA", "BAJA"):
            prioridad_filtro = ""
        iv_sede_filtro = request.args.get("iv_sede") or ""
        iv_estado_filtro = _sanitize_interv_estado(request.args.get("iv_estado"))
        iv_tipo_filtro = _sanitize_interv_tipo(request.args.get("iv_tipo"))
        iv_fecha_filtro = _sanitize_interv_fecha(request.args.get("iv_fecha"))
        active_panel = (request.args.get("panel") or "").strip()

        # ---------- ALTA RÁPIDA DE OBRA DESDE LA MISMA PANTALLA ----------
        if request.method == "POST":
            codigo_sede   = request.form.get("codigo_sede")
            titulo_in     = (request.form.get("titulo") or "").strip()
            tipo          = (request.form.get("tipo") or "").strip()
            prioridad     = request.form.get("prioridad") or "Media"
            fecha_sol     = request.form.get("fecha_solicitud") or date.today().isoformat()
            fecha_inicio  = request.form.get("fecha_inicio") or None
            fecha_prev    = request.form.get("fecha_fin_prevista") or None
            descripcion_tx = (request.form.get("descripcion") or "").strip()
            descripcion    = descripcion_tx or None
            titulo         = titulo_in or (descripcion_tx[:120] if descripcion_tx else "") or tipo

            if not codigo_sede or not titulo:
                flash("Elegi una sede y carga al menos tipo o descripcion.", "warning")
            else:
                con.execute("""
                    INSERT INTO obras_sede
                    (codigo_sede, titulo, tipo, prioridad,
                     estado, fecha_solicitud, fecha_inicio,
                     fecha_fin_prevista, descripcion)
                    VALUES (?,?,?,?, 'PENDIENTE', ?,?,?,?)
                """, (
                    codigo_sede, titulo, tipo, prioridad,
                    fecha_sol, fecha_inicio, fecha_prev, descripcion
                ))
                con.commit()
                rebuild_eventos_obras()
                flash("Obra / trabajo cargado correctamente.", "success")

            return redirect(url_for("obras_home", sede=codigo_sede))

        # ---------- LISTADO DE OBRAS ----------
        sql = """
            SELECT
                o.id,
                o.codigo_sede,
                s.nombre AS sede_nombre,
                s.ciudad AS sede_ciudad,
                o.titulo,
                o.descripcion,
                o.tipo,
                o.prioridad,
                o.estado,
                o.fecha_solicitud,
                o.fecha_inicio,
                o.fecha_fin_prevista,
                o.fecha_fin_real
            FROM obras_sede o
            JOIN sedes_mpd s ON s.codigo = o.codigo_sede
            WHERE 1=1
        """
        params = []

        if cod_filtro:
            sql += " AND o.codigo_sede = ?"
            params.append(cod_filtro)

        if estado_filtro:
            sql += " AND UPPER(TRIM(COALESCE(o.estado, ''))) = ?"
            params.append(estado_filtro)
        else:
            sql += " AND UPPER(TRIM(COALESCE(o.estado, ''))) != 'FINALIZADA'"

        if prioridad_filtro:
            sql += " AND UPPER(TRIM(COALESCE(o.prioridad, ''))) = ?"
            params.append(prioridad_filtro)

        sql += " ORDER BY o.fecha_solicitud DESC, o.id DESC"

        obras = con.execute(sql, params).fetchall()

        totals_sql = """
            SELECT
                COALESCE(SUM(CASE WHEN o.estado = 'PENDIENTE' THEN 1 ELSE 0 END), 0) AS pendientes,
                COALESCE(SUM(CASE WHEN o.estado = 'EN_CURSO' THEN 1 ELSE 0 END), 0) AS en_curso,
                COALESCE(SUM(CASE WHEN o.estado = 'FINALIZADA' THEN 1 ELSE 0 END), 0) AS finalizadas,
                COALESCE(COUNT(*), 0) AS total
            FROM obras_sede o
            WHERE 1=1
        """
        totals_params = []
        if cod_filtro:
            totals_sql += " AND o.codigo_sede = ?"
            totals_params.append(cod_filtro)
        if prioridad_filtro:
            totals_sql += " AND UPPER(TRIM(COALESCE(o.prioridad, ''))) = ?"
            totals_params.append(prioridad_filtro)

        obras_totals = con.execute(totals_sql, totals_params).fetchone()

        pendientes_alta_sql = """
            SELECT COALESCE(COUNT(*), 0) AS total
            FROM obras_sede o
            WHERE UPPER(TRIM(COALESCE(o.estado, ''))) = 'PENDIENTE'
              AND UPPER(TRIM(COALESCE(o.prioridad, ''))) = 'ALTA'
        """
        pendientes_alta_params = []
        if cod_filtro:
            pendientes_alta_sql += " AND o.codigo_sede = ?"
            pendientes_alta_params.append(cod_filtro)
        pendientes_alta_total = con.execute(
            pendientes_alta_sql, pendientes_alta_params
        ).fetchone()["total"]

        stats_sql = """
            SELECT
                o.codigo_sede,
                s.nombre AS sede_nombre,
                s.ciudad AS sede_ciudad,
                COALESCE(COUNT(*), 0) AS total,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(o.estado, '')))='PENDIENTE' THEN 1 ELSE 0 END), 0) AS pendientes,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(o.estado, '')))='EN_CURSO' THEN 1 ELSE 0 END), 0) AS en_curso,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(o.estado, '')))='FINALIZADA' THEN 1 ELSE 0 END), 0) AS finalizadas
            FROM obras_sede o
            JOIN sedes_mpd s ON s.codigo = o.codigo_sede
            WHERE 1=1
        """
        stats_params = []
        if cod_filtro:
            stats_sql += " AND o.codigo_sede = ?"
            stats_params.append(cod_filtro)
        if prioridad_filtro:
            stats_sql += " AND UPPER(TRIM(COALESCE(o.prioridad, ''))) = ?"
            stats_params.append(prioridad_filtro)
        stats_sql += " GROUP BY o.codigo_sede, s.nombre, s.ciudad ORDER BY total DESC, o.codigo_sede"

        stats_rows = con.execute(stats_sql, stats_params).fetchall()

        stats_det_sql = """
            SELECT
                o.codigo_sede,
                o.tipo,
                o.titulo,
                o.descripcion,
                o.prioridad
            FROM obras_sede o
            WHERE 1=1
        """
        stats_det_params = []
        if cod_filtro:
            stats_det_sql += " AND o.codigo_sede = ?"
            stats_det_params.append(cod_filtro)
        if prioridad_filtro:
            stats_det_sql += " AND UPPER(TRIM(COALESCE(o.prioridad, ''))) = ?"
            stats_det_params.append(prioridad_filtro)

        stats_det_rows = con.execute(stats_det_sql, stats_det_params).fetchall()

        obras_stats = []
        stats_idx = {}
        for row in stats_rows:
            item = {
                "codigo_sede": row["codigo_sede"],
                "sede_nombre": row["sede_nombre"],
                "sede_ciudad": row["sede_ciudad"],
                "total": int(row["total"] or 0),
                "pendientes": int(row["pendientes"] or 0),
                "en_curso": int(row["en_curso"] or 0),
                "finalizadas": int(row["finalizadas"] or 0),
                "horas_tarea_est": 0.0,
                "horas_persona_est": 0.0,
                "materiales_est": 0.0,
                "dias_est": 0.0,
            }
            obras_stats.append(item)
            stats_idx[item["codigo_sede"]] = item

        for row in stats_det_rows:
            item = stats_idx.get(row["codigo_sede"])
            if not item:
                continue
            est = _estimar_intervencion(row["tipo"], row["titulo"], row["descripcion"], row["prioridad"])
            item["dias_est"] += est["dias"]
            item["horas_tarea_est"] += est["horas_tarea"]
            item["horas_persona_est"] += est["horas_persona"]
            item["materiales_est"] += est["materiales"]

        total_intervenciones = sum(i["total"] for i in obras_stats)
        total_horas_persona = sum(i["horas_persona_est"] for i in obras_stats)
        total_materiales = sum(i["materiales_est"] for i in obras_stats)

        for item in obras_stats:
            total_item = item["total"] or 0
            item["uso_interv_pct"] = (item["total"] * 100.0 / total_intervenciones) if total_intervenciones else 0.0
            item["uso_horas_pct"] = (item["horas_persona_est"] * 100.0 / total_horas_persona) if total_horas_persona else 0.0
            item["uso_materiales_pct"] = (item["materiales_est"] * 100.0 / total_materiales) if total_materiales else 0.0
            item["pendientes_pct"] = (item["pendientes"] * 100.0 / total_item) if total_item else 0.0
            item["en_curso_pct"] = (item["en_curso"] * 100.0 / total_item) if total_item else 0.0
            item["finalizadas_pct"] = (item["finalizadas"] * 100.0 / total_item) if total_item else 0.0
            item["hs_persona_por_interv"] = (item["horas_persona_est"] / total_item) if total_item else 0.0

        obras_stats.sort(key=lambda x: (x["total"], x["horas_persona_est"]), reverse=True)

        stats_global = {
            "sedes": len(obras_stats),
            "intervenciones": total_intervenciones,
            "horas_persona": total_horas_persona,
            "materiales": total_materiales,
            "prom_hs_interv": (total_horas_persona / total_intervenciones) if total_intervenciones else 0.0,
            "prom_mat_interv": (total_materiales / total_intervenciones) if total_intervenciones else 0.0,
        }

        estimacion_modelo = [
            {"tipo": i["label"], "rango": f"{int(i['dias_min'])}-{int(i['dias_max'])} dias"}
            for i in estimaciones_catalogo
        ]

        interv_sql = """
            SELECT
                i.id,
                i.fecha,
                i.codigo_sede,
                s.nombre AS sede_nombre,
                s.ciudad AS sede_ciudad,
                i.tipo,
                i.detalle,
                i.estado,
                i.autorizado_por,
                i.observacion,
                i.created_at,
                i.updated_at
            FROM obras_intervenciones_diarias i
            JOIN sedes_mpd s ON s.codigo = i.codigo_sede
            WHERE 1=1
        """
        interv_params = []
        if iv_sede_filtro:
            interv_sql += " AND i.codigo_sede = ?"
            interv_params.append(iv_sede_filtro)
        if iv_estado_filtro:
            interv_sql += " AND UPPER(TRIM(COALESCE(i.estado, ''))) = ?"
            interv_params.append(iv_estado_filtro)
        if iv_tipo_filtro:
            interv_sql += " AND UPPER(TRIM(COALESCE(i.tipo, ''))) = ?"
            interv_params.append(iv_tipo_filtro)
        if iv_fecha_filtro:
            interv_sql += " AND date(i.fecha) = date(?)"
            interv_params.append(iv_fecha_filtro)
        interv_sql += " ORDER BY date(i.fecha) DESC, i.id DESC"
        intervenciones = con.execute(interv_sql, interv_params).fetchall()

        interv_totals_sql = """
            SELECT
                COALESCE(COUNT(*), 0) AS total,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(i.estado, '')))='PENDIENTE' THEN 1 ELSE 0 END), 0) AS pendientes,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(i.estado, '')))='RESUELTO' THEN 1 ELSE 0 END), 0) AS resueltos
            FROM obras_intervenciones_diarias i
            WHERE 1=1
        """
        interv_totals_params = []
        if iv_sede_filtro:
            interv_totals_sql += " AND i.codigo_sede = ?"
            interv_totals_params.append(iv_sede_filtro)
        if iv_estado_filtro:
            interv_totals_sql += " AND UPPER(TRIM(COALESCE(i.estado, ''))) = ?"
            interv_totals_params.append(iv_estado_filtro)
        if iv_tipo_filtro:
            interv_totals_sql += " AND UPPER(TRIM(COALESCE(i.tipo, ''))) = ?"
            interv_totals_params.append(iv_tipo_filtro)
        if iv_fecha_filtro:
            interv_totals_sql += " AND date(i.fecha) = date(?)"
            interv_totals_params.append(iv_fecha_filtro)
        interv_totals = con.execute(interv_totals_sql, interv_totals_params).fetchone()
        autorizado_por_default = (session.get("full_name") or session.get("username") or "").strip()

        # ---------- DESINFECCIONES (panel dedicado) ----------
        desinf_where = """
            WHERE (
                LOWER(COALESCE(o.tipo, '')) LIKE '%desinfecc%'
                OR LOWER(COALESCE(o.titulo, '')) LIKE '%desinfecc%'
                OR LOWER(COALESCE(o.descripcion, '')) LIKE '%desinfecc%'
            )
        """
        desinf_params = []
        if cod_filtro:
            desinf_where += " AND o.codigo_sede = ?"
            desinf_params.append(cod_filtro)

        desinfecciones = con.execute(f"""
            SELECT
                o.id,
                o.codigo_sede,
                s.nombre AS sede_nombre,
                s.ciudad AS sede_ciudad,
                o.estado,
                o.tipo,
                o.titulo,
                o.descripcion,
                o.fecha_solicitud,
                o.fecha_inicio,
                o.fecha_fin_real
            FROM obras_sede o
            JOIN sedes_mpd s ON s.codigo = o.codigo_sede
            {desinf_where}
            ORDER BY o.fecha_solicitud DESC, o.id DESC
        """, desinf_params).fetchall()

        desinf_stats = con.execute(f"""
            SELECT
                o.codigo_sede,
                s.nombre AS sede_nombre,
                s.ciudad AS sede_ciudad,
                COUNT(*) AS total,
                SUM(CASE WHEN UPPER(TRIM(COALESCE(o.estado,'')))='FINALIZADA' THEN 1 ELSE 0 END) AS finalizadas,
                MAX(o.fecha_solicitud) AS ultima_fecha
            FROM obras_sede o
            JOIN sedes_mpd s ON s.codigo = o.codigo_sede
            {desinf_where}
            GROUP BY o.codigo_sede, s.nombre, s.ciudad
            ORDER BY o.codigo_sede
        """, desinf_params).fetchall()
        con.close()

        return render_template(
            "obras_home.html",
            sedes=sedes,
            obras=obras,
            cod_filtro=cod_filtro,
            estado_filtro=estado_filtro,
            prioridad_filtro=prioridad_filtro,
            active_panel=active_panel,
            obras_totals=obras_totals,
            pendientes_alta_total=pendientes_alta_total,
            obras_stats=obras_stats,
            stats_global=stats_global,
            estimacion_modelo=estimacion_modelo,
            fecha_hoy=date.today().isoformat(),
            intervenciones=intervenciones,
            interv_totals=interv_totals,
            iv_sede_filtro=iv_sede_filtro,
            iv_estado_filtro=iv_estado_filtro,
            iv_tipo_filtro=iv_tipo_filtro,
            iv_fecha_filtro=iv_fecha_filtro,
            interv_tipos=interv_tipos,
            interv_tipo_labels=interv_tipo_labels,
            interv_estados=interv_estados,
            interv_estado_labels=interv_estado_labels,
            autorizado_por_default=autorizado_por_default,
            desinfecciones=desinfecciones,
            desinf_stats=desinf_stats
        )

    @app.route("/obras/<int:oid>/estado", methods=["POST"], endpoint="obra_cambiar_estado")
    def obra_cambiar_estado(oid):
        nuevo_estado = (request.form.get("estado") or "PENDIENTE").strip().upper()
        hoy_str = date.today().isoformat()

        con = get_db()
        # si pasa a FINALIZADA, guardo fecha_fin_real
        if nuevo_estado == "FINALIZADA":
            con.execute("""
                UPDATE obras_sede
                SET estado = ?, fecha_fin_real = COALESCE(fecha_fin_real, ?)
                WHERE id = ?
            """, (nuevo_estado, hoy_str, oid))
        elif nuevo_estado == "EN_CURSO":
            con.execute("""
                UPDATE obras_sede
                SET estado = ?, fecha_inicio = COALESCE(fecha_inicio, ?), fecha_fin_real = NULL
                WHERE id = ?
            """, (nuevo_estado, hoy_str, oid))
        else:
            con.execute("""
                UPDATE obras_sede
                SET estado = ?, fecha_fin_real = NULL
                WHERE id = ?
            """, (nuevo_estado, oid))

        con.commit()
        con.close()
        rebuild_eventos_obras()
        flash("Estado de la obra actualizado.", "success")
        sede = request.args.get("sede") or ""
        estado = (request.args.get("estado") or "").strip().upper()
        prioridad = (request.args.get("prioridad") or "").strip().upper()
        if prioridad not in ("ALTA", "MEDIA", "BAJA"):
            prioridad = ""
        if nuevo_estado == "FINALIZADA":
            return redirect(url_for("obras_home", sede=sede, estado="FINALIZADA", prioridad=prioridad))
        return redirect(url_for("obras_home", sede=sede, estado=estado, prioridad=prioridad))

    @app.route("/obras/<int:oid>/prioridad", methods=["POST"], endpoint="obra_cambiar_prioridad")
    def obra_cambiar_prioridad(oid):
        raw = (request.form.get("prioridad") or "Media").strip().lower()
        mapping = {
            "alta": "Alta",
            "media": "Media",
            "baja": "Baja",
        }
        nueva_prioridad = mapping.get(raw, "Media")

        con = get_db()
        con.execute("UPDATE obras_sede SET prioridad = ? WHERE id = ?", (nueva_prioridad, oid))
        con.commit()
        con.close()

        rebuild_eventos_obras()
        flash("Prioridad actualizada.", "success")

        sede = request.args.get("sede") or ""
        estado = (request.args.get("estado") or "").strip().upper()
        prioridad = (request.args.get("prioridad") or "").strip().upper()
        if prioridad not in ("ALTA", "MEDIA", "BAJA"):
            prioridad = ""
        return redirect(url_for("obras_home", sede=sede, estado=estado, prioridad=prioridad))

    @app.route("/obras/intervenciones", methods=["POST"], endpoint="obra_intervencion_crear")
    def obra_intervencion_crear():
        con = get_db()
        _ensure_intervenciones_table(con)

        fecha = _sanitize_interv_fecha(request.form.get("fecha")) or date.today().isoformat()
        codigo_sede = (request.form.get("codigo_sede") or "").strip()
        tipo = _sanitize_interv_tipo(request.form.get("tipo"))
        detalle = (request.form.get("detalle") or "").strip()
        autorizado_por = (request.form.get("autorizado_por") or "").strip() or None
        estado = _sanitize_interv_estado(request.form.get("estado")) or "PENDIENTE"
        observacion = (request.form.get("observacion") or "").strip() or None

        if not codigo_sede or not tipo or not detalle:
            flash("Completa sede, tipo y detalle para registrar la intervencion.", "warning")
        else:
            con.execute(
                """
                INSERT INTO obras_intervenciones_diarias
                (fecha, codigo_sede, tipo, detalle, autorizado_por, estado, observacion)
                VALUES (?,?,?,?,?,?,?)
                """,
                (fecha, codigo_sede, tipo, detalle, autorizado_por, estado, observacion),
            )
            con.commit()
            flash("Intervencion diaria registrada.", "success")

        con.close()
        return redirect(url_for("obras_home", **_interv_redirect_args()))

    @app.route(
        "/obras/intervenciones/<int:iid>/estado",
        methods=["POST"],
        endpoint="obra_intervencion_cambiar_estado",
    )
    def obra_intervencion_cambiar_estado(iid):
        nuevo_estado = _sanitize_interv_estado(request.form.get("estado")) or "PENDIENTE"
        con = get_db()
        _ensure_intervenciones_table(con)

        exists = con.execute(
            "SELECT id FROM obras_intervenciones_diarias WHERE id = ?",
            (iid,),
        ).fetchone()
        if not exists:
            con.close()
            flash("Intervencion no encontrada.", "warning")
            return redirect(url_for("obras_home", **_interv_redirect_args()))

        con.execute(
            """
            UPDATE obras_intervenciones_diarias
            SET estado = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (nuevo_estado, iid),
        )
        con.commit()
        con.close()
        flash("Estado de intervencion actualizado.", "success")
        return redirect(url_for("obras_home", **_interv_redirect_args()))

    @app.route(
        "/obras/intervenciones/editar/<int:iid>",
        methods=["GET", "POST"],
        endpoint="obra_intervencion_editar",
    )
    def obra_intervencion_editar(iid):
        con = get_db()
        _ensure_intervenciones_table(con)

        sedes = con.execute(
            """
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
            """
        ).fetchall()

        intervencion = con.execute(
            """
            SELECT
                id, fecha, codigo_sede, tipo, detalle, autorizado_por,
                estado, observacion, created_at, updated_at
            FROM obras_intervenciones_diarias
            WHERE id = ?
            """,
            (iid,),
        ).fetchone()

        if not intervencion:
            con.close()
            flash("Intervencion no encontrada.", "warning")
            return redirect(url_for("obras_home", **_interv_redirect_args()))

        if request.method == "POST":
            fecha = _sanitize_interv_fecha(request.form.get("fecha")) or date.today().isoformat()
            codigo_sede = (request.form.get("codigo_sede") or "").strip()
            tipo = _sanitize_interv_tipo(request.form.get("tipo"))
            detalle = (request.form.get("detalle") or "").strip()
            autorizado_por = (request.form.get("autorizado_por") or "").strip() or None
            estado = _sanitize_interv_estado(request.form.get("estado")) or "PENDIENTE"
            observacion = (request.form.get("observacion") or "").strip() or None

            if not codigo_sede or not tipo or not detalle:
                flash("Completa sede, tipo y detalle para guardar.", "warning")
            else:
                con.execute(
                    """
                    UPDATE obras_intervenciones_diarias
                    SET fecha = ?,
                        codigo_sede = ?,
                        tipo = ?,
                        detalle = ?,
                        autorizado_por = ?,
                        estado = ?,
                        observacion = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (fecha, codigo_sede, tipo, detalle, autorizado_por, estado, observacion, iid),
                )
                con.commit()
                con.close()
                flash("Intervencion diaria actualizada.", "success")
                return redirect(url_for("obras_home", **_interv_redirect_args()))

            intervencion = con.execute(
                """
                SELECT
                    id, fecha, codigo_sede, tipo, detalle, autorizado_por,
                    estado, observacion, created_at, updated_at
                FROM obras_intervenciones_diarias
                WHERE id = ?
                """,
                (iid,),
            ).fetchone()

        back_url = url_for("obras_home", **_interv_redirect_args())
        form_action = url_for("obra_intervencion_editar", iid=iid, **_interv_redirect_args())
        con.close()
        return render_template(
            "intervencion_diaria_editar.html",
            intervencion=intervencion,
            sedes=sedes,
            interv_tipos=interv_tipos,
            interv_estados=interv_estados,
            interv_tipo_labels=interv_tipo_labels,
            interv_estado_labels=interv_estado_labels,
            back_url=back_url,
            form_action=form_action,
        )

    @app.route(
        "/obras/intervenciones/eliminar/<int:iid>",
        methods=["POST"],
        endpoint="obra_intervencion_eliminar",
    )
    def obra_intervencion_eliminar(iid):
        con = get_db()
        _ensure_intervenciones_table(con)
        exists = con.execute(
            "SELECT id FROM obras_intervenciones_diarias WHERE id = ?",
            (iid,),
        ).fetchone()
        if not exists:
            con.close()
            flash("Intervencion no encontrada.", "warning")
            return redirect(url_for("obras_home", **_interv_redirect_args()))

        con.execute("DELETE FROM obras_intervenciones_diarias WHERE id = ?", (iid,))
        con.commit()
        con.close()
        flash("Intervencion eliminada.", "success")
        return redirect(url_for("obras_home", **_interv_redirect_args()))

    @app.route("/obras/editar/<int:oid>", methods=["GET", "POST"])
    def obra_editar(oid):
        con = get_db()

        obra = con.execute("""
            SELECT
                id, codigo_sede, titulo, tipo, prioridad, estado,
                fecha_solicitud, fecha_inicio, fecha_fin_prevista,
                fecha_fin_real, descripcion, observaciones
            FROM obras_sede
            WHERE id = ?
        """, (oid,)).fetchone()

        if not obra:
            con.close()
            flash("Obra no encontrada.", "warning")
            return redirect(url_for("obras_home"))

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        if request.method == "POST":
            codigo_sede = (request.form.get("codigo_sede") or "").strip()
            titulo_in = (request.form.get("titulo") or "").strip()
            tipo = (request.form.get("tipo") or "").strip()
            prioridad = (request.form.get("prioridad") or "Media").strip()
            estado = (request.form.get("estado") or "PENDIENTE").strip().upper()
            fecha_sol = (request.form.get("fecha_solicitud") or "").strip()
            fecha_inicio = (request.form.get("fecha_inicio") or "").strip() or None
            fecha_prev = (request.form.get("fecha_fin_prevista") or "").strip() or None
            fecha_fin_real = (request.form.get("fecha_fin_real") or "").strip() or None
            descripcion_tx = (request.form.get("descripcion") or "").strip()
            descripcion = descripcion_tx or None
            observaciones = (request.form.get("observaciones") or "").strip() or None
            titulo = titulo_in or (descripcion_tx[:120] if descripcion_tx else "") or tipo

            if not codigo_sede or not titulo or not fecha_sol:
                flash("Completa sede, fecha de solicitud y al menos tipo o descripcion.", "warning")
            else:
                if estado == "EN_CURSO" and not fecha_inicio:
                    fecha_inicio = date.today().isoformat()
                if estado != "FINALIZADA":
                    fecha_fin_real = None
                con.execute("""
                    UPDATE obras_sede
                    SET codigo_sede = ?,
                        titulo = ?,
                        tipo = ?,
                        prioridad = ?,
                        estado = ?,
                        fecha_solicitud = ?,
                        fecha_inicio = ?,
                        fecha_fin_prevista = ?,
                        fecha_fin_real = ?,
                        descripcion = ?,
                        observaciones = ?
                    WHERE id = ?
                """, (
                    codigo_sede, titulo, tipo, prioridad, estado, fecha_sol,
                    fecha_inicio, fecha_prev, fecha_fin_real, descripcion,
                    observaciones, oid
                ))
                con.commit()
                con.close()
                rebuild_eventos_obras()
                flash("Obra actualizada.", "success")
                return redirect(url_for("obras_home", sede=codigo_sede))

        con.close()
        return render_template(
            "obra_editar.html",
            obra=obra,
            sedes=sedes,
        )

    @app.route("/obras/eliminar/<int:oid>", methods=["POST"], endpoint="obra_eliminar")
    def obra_eliminar(oid):
        con = get_db()

        # Verificar que exista
        r = con.execute("SELECT id FROM obras_sede WHERE id=?", (oid,)).fetchone()
        if not r:
            con.close()
            flash("Obra no encontrada.", "warning")
            return redirect(url_for("obras_home"))

        # Eliminar
        con.execute("DELETE FROM obras_sede WHERE id=?", (oid,))
        con.commit()
        con.close()
        rebuild_eventos_obras()

        flash("🗑️ Obra eliminada.", "success")

        # Mantener filtros si venían en la URL (?sede=...&estado=...)
        sede = request.args.get("sede") or ""
        estado = request.args.get("estado") or ""
        prioridad = (request.args.get("prioridad") or "").strip().upper()
        if prioridad not in ("ALTA", "MEDIA", "BAJA"):
            prioridad = ""
        return redirect(url_for("obras_home", sede=sede, estado=estado, prioridad=prioridad))
