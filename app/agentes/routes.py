from flask import Blueprint
from . import bp



from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, send_from_directory, send_file

import sqlite3
import os
from datetime import date, datetime
def register_agentes_routes(bp, get_db, ensure_cols, rebuild_eventos_agentes, allowed_agente_doc, AGENTE_DOCS_FOLDER):


    # ======= DDL BOOTSTRAP (runs ONCE on server start) =======
    _bootstrap_con = get_db()
    _bootstrap_con.execute("""
        CREATE TABLE IF NOT EXISTS agentes_compensatorios_mov(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL,
            dias REAL DEFAULT 0,
            horas REAL DEFAULT 0,
            periodo TEXT,
            desde TEXT,
            hasta TEXT,
            observaciones TEXT
        )
    """)
    ensure_cols(_bootstrap_con, "agentes_compensatorios_mov", [
        ("agente_id", "INTEGER"), ("fecha", "TEXT"), ("tipo", "TEXT"),
        ("dias", "REAL"), ("horas", "REAL"), ("periodo", "TEXT"),
        ("desde", "TEXT"), ("hasta", "TEXT"), ("observaciones", "TEXT"),
    ])
    ensure_cols(_bootstrap_con, "agentes_documentacion", [
        ("archivo", "TEXT"), ("archivo_url", "TEXT")
    ])
    _bootstrap_con.commit()
    _bootstrap_con.close()
    # ======= END DDL BOOTSTRAP =======

    def _get_agente_details(conn, agente_id):
        comp_movs = conn.execute("""
            SELECT
                id,
                fecha,
                tipo,
                dias,
                horas,
                periodo,
                desde,
                hasta,
                observaciones
            FROM agentes_compensatorios_mov
            WHERE agente_id = ?
            ORDER BY date(fecha) DESC, id DESC
        """, (agente_id,)).fetchall()

        total_horas = 0.0
        dias_gen = 0.0
        dias_tom = 0.0
        for m in comp_movs:
            if (m["tipo"] or "").upper() in ("INICIAL", "FERIA"):
                dias_gen += float(m["dias"] or 0)
            elif (m["tipo"] or "").upper() == "TOMA":
                dias_tom += float(m["dias"] or 0)
            elif (m["tipo"] or "").upper() == "HORAS":
                total_horas += float(m["horas"] or 0)

        dias_horas = int(total_horas // 6)
        horas_rem = float(total_horas - (dias_horas * 6))
        comp_saldo = {
            "dias": (dias_gen + dias_horas - dias_tom),
            "horas": horas_rem,
            "dias_generados": dias_gen + dias_horas,
            "dias_tomados": dias_tom,
        }

        documentos = conn.execute("""
            SELECT id, tipo, fecha_vencimiento, estado, observaciones
            FROM agentes_documentacion
            WHERE agente_id = ?
            ORDER BY tipo
        """, (agente_id,)).fetchall()

        entregas_epp = conn.execute("""
            SELECT id, tipo, categoria, fecha_entrega, cantidad, estado, observaciones
            FROM agentes_epp
            WHERE agente_id = ?
            ORDER BY fecha_entrega DESC
        """, (agente_id,)).fetchall()

        incidentes = conn.execute("""
            SELECT id, fecha, tipo, lugar, descripcion, consecuencia, acciones, estado
            FROM agentes_incidentes
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente_id,)).fetchall()

        desempenos = conn.execute("""
            SELECT id, fecha, tipo, periodo, calificacion, observaciones, estado
            FROM agentes_desempeno
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente_id,)).fetchall()

        documentos_vinculados_agente = []
        try:
            t_docs = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos'").fetchone()
            t_rel = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos_agentes'").fetchone()
            if t_docs and t_rel:
                documentos_vinculados_agente = conn.execute("""
                    SELECT
                        d.id_documento,
                        d.titulo,
                        d.tipo_documento,
                        d.estado,
                        d.fecha,
                        d.archivo_url,
                        COALESCE((
                            SELECT GROUP_CONCAT(dt.tag, ', ')
                            FROM documentos_tags dt
                            WHERE dt.id_documento = d.id_documento
                        ), '') AS tags_txt
                    FROM documentos d
                    JOIN documentos_agentes da ON da.id_documento = d.id_documento
                    WHERE da.id_agente = ?
                    ORDER BY COALESCE(d.fecha, d.creado_en) DESC, d.id_documento DESC
                    LIMIT 40
                """, (agente_id,)).fetchall()
        except Exception:
            pass

        return {
            "comp_movs": comp_movs,
            "comp_saldo": comp_saldo,
            "documentos": documentos,
            "entregas_epp": entregas_epp,
            "incidentes": incidentes,
            "desempenos": desempenos,
            "documentos_vinculados_agente": documentos_vinculados_agente,
        }

    @bp.route("/agentes", endpoint="agentes_home")
    def agentes_home():
        con = get_db()
        con.execute("""
            CREATE TABLE IF NOT EXISTS agentes_compensatorios_mov(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agente_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                dias REAL DEFAULT 0,
                horas REAL DEFAULT 0,
                periodo TEXT,
                desde TEXT,
                hasta TEXT,
                observaciones TEXT
            )
        """)
        ensure_cols(con, "agentes_compensatorios_mov", [
            ("agente_id", "INTEGER"),
            ("fecha", "TEXT"),
            ("tipo", "TEXT"),
            ("dias", "REAL"),
            ("horas", "REAL"),
            ("periodo", "TEXT"),
            ("desde", "TEXT"),
            ("hasta", "TEXT"),
            ("observaciones", "TEXT"),
        ])

        # Agentes activos (intendencia / limpieza / mantenimiento / choferes)
        filas = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE activo = 1
              AND (
                    UPPER(TRIM(agente)) IN (
                        'EMILIANO PEREZ DE LA PUENTE',
                        'IGNACIO BARONI'
                    )
                    OR UPPER(TRIM(agente)) LIKE '%FRANCISCO SAVIO%'
                    OR UPPER(TRIM(agente)) LIKE '%MAURO%VEA%MURGUIA%'
                    OR LOWER(TRIM(rubro)) IN ('mantenimiento', 'limpieza')
                  )
            ORDER BY rubro, agente
        """).fetchall()

        # agrupar por rubro para el panel lateral
        grupos = {}
        for r in filas:
            grupos.setdefault(r["rubro"], []).append(r)

        # elegir agente destacado según ?id=
        agente_destacado = None
        id_str = request.args.get("id")

        if id_str:
            try:
                sel_id = int(id_str)
                for r in filas:
                    if r["id"] == sel_id:
                        agente_destacado = r
                        break
            except ValueError:
                pass

        if agente_destacado is None and filas:
            agente_destacado = filas[0]

        comp_movs = []
        comp_saldo = {
            "dias": 0,
            "horas": 0,
            "dias_generados": 0,
            "dias_tomados": 0,
        }
        documentos = []
        entregas_epp = []
        incidentes = []
        desempenos = []
        documentos_vinculados_agente = []

        if agente_destacado is not None:
            details = _get_agente_details(con, agente_destacado["id"])
            comp_movs = details["comp_movs"]
            comp_saldo = details["comp_saldo"]
            documentos = details["documentos"]
            entregas_epp = details["entregas_epp"]
            incidentes = details["incidentes"]
            desempenos = details["desempenos"]
            documentos_vinculados_agente = details["documentos_vinculados_agente"]

        con.close()

        return render_template(
            "agentes_home.html",
            grupos=grupos,
            agente_destacado=agente_destacado,
            comp_movs=comp_movs,
            comp_saldo=comp_saldo,
            documentos=documentos,
            entregas_epp=entregas_epp,
            incidentes=incidentes,
            desempenos=desempenos,
            documentos_vinculados_agente=documentos_vinculados_agente,
        )



    @bp.route("/agentes/<int:agente_id>/licencias/nueva",
               methods=["GET", "POST"],
               endpoint="agente_nueva_licencia")
    def agente_nueva_licencia(agente_id):
        con = get_db()

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ?
        """, (agente_id,)).fetchone()

        if not agente:
            con.close()
            flash("Agente no encontrado.", "warning")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo          = request.form.get("tipo") or ""
            fecha_desde   = request.form.get("fecha_desde") or ""
            fecha_hasta   = request.form.get("fecha_hasta") or ""
            estado        = request.form.get("estado") or "PENDIENTE"
            observaciones = (request.form.get("observaciones") or "").strip() or None

            if not tipo or not fecha_desde or not fecha_hasta:
                flash("Completá tipo y fechas de la licencia.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_nueva_licencia", agente_id=agente_id))

            if fecha_hasta < fecha_desde:
                flash("La fecha hasta no puede ser menor que la fecha desde.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_nueva_licencia", agente_id=agente_id))

            con.execute("""
                INSERT INTO agentes_licencias
                    (agente_id, tipo, fecha_desde, fecha_hasta, observaciones, estado)
                VALUES (?,?,?,?,?,?)
            """, (agente_id, tipo, fecha_desde, fecha_hasta, observaciones, estado))

            con.commit()
            con.close()
            rebuild_eventos_agentes()
            flash("✅ Licencia cargada correctamente.", "success")
            return redirect(url_for("agentes.agentes_home", id=agente_id))

        con.close()
        return render_template("agente_licencia_form.html",
                               agente=agente,
                               licencia=None)



    @bp.route("/agentes/<int:agente_id>/licencias/<int:lic_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_licencia_editar")
    def agente_licencia_editar(agente_id, lic_id):
        con = get_db()

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ?
        """, (agente_id,)).fetchone()

        licencia = con.execute("""
            SELECT *
            FROM agentes_licencias
            WHERE id = ? AND agente_id = ?
        """, (lic_id, agente_id)).fetchone()

        if not agente or not licencia:
            con.close()
            flash("Licencia o agente no encontrado.", "warning")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo          = request.form.get("tipo") or ""
            fecha_desde   = request.form.get("fecha_desde") or ""
            fecha_hasta   = request.form.get("fecha_hasta") or ""
            estado        = request.form.get("estado") or "PENDIENTE"
            observaciones = (request.form.get("observaciones") or "").strip() or None

            if not tipo or not fecha_desde or not fecha_hasta:
                flash("Completá tipo y fechas de la licencia.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_licencia_editar",
                                        agente_id=agente_id, lic_id=lic_id))

            if fecha_hasta < fecha_desde:
                flash("La fecha hasta no puede ser menor que la fecha desde.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_licencia_editar",
                                        agente_id=agente_id, lic_id=lic_id))

            con.execute("""
                UPDATE agentes_licencias
                SET tipo = ?, fecha_desde = ?, fecha_hasta = ?,
                    observaciones = ?, estado = ?
                WHERE id = ? AND agente_id = ?
            """, (tipo, fecha_desde, fecha_hasta, observaciones, estado, lic_id, agente_id))

            con.commit()
            con.close()
            rebuild_eventos_agentes()
            flash("✅ Licencia actualizada.", "success")
            return redirect(url_for("agentes.agentes_home", id=agente_id))

        con.close()
        return render_template("agente_licencia_form.html",
                               agente=agente,
                               licencia=licencia)



    @bp.route("/agentes/<int:agente_id>/licencias/<int:lic_id>/eliminar",
               methods=["POST"],
               endpoint="agente_licencia_eliminar")

    def agente_licencia_eliminar(agente_id, lic_id):
        con = get_db()
        con.execute("""
            DELETE FROM agentes_licencias
            WHERE id = ? AND agente_id = ?
        """, (lic_id, agente_id))
        con.commit()
        con.close()
        rebuild_eventos_agentes()
        flash("🗑️ Licencia eliminada.", "info")
        return redirect(url_for("agentes.agentes_home", id=agente_id))


    @bp.route("/agentes/<int:id>/compensatorios", methods=["GET", "POST"], endpoint="agente_compensatorios")
    def agente_compensatorios(id):
        con = get_db()
        con.execute("""
            CREATE TABLE IF NOT EXISTS agentes_compensatorios_mov(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agente_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                dias REAL DEFAULT 0,
                horas REAL DEFAULT 0,
                periodo TEXT,
                desde TEXT,
                hasta TEXT,
                observaciones TEXT
            )
        """)
        ensure_cols(con, "agentes_compensatorios_mov", [
            ("agente_id", "INTEGER"),
            ("fecha", "TEXT"),
            ("tipo", "TEXT"),
            ("dias", "REAL"),
            ("horas", "REAL"),
            ("periodo", "TEXT"),
            ("desde", "TEXT"),
            ("hasta", "TEXT"),
            ("observaciones", "TEXT"),
        ])

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o est? inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo = (request.form.get("tipo") or "").strip().upper()
            fecha = (request.form.get("fecha") or date.today().isoformat()).strip()
            periodo = (request.form.get("periodo") or "").strip() or None
            dias_txt = (request.form.get("dias") or "").strip()
            horas_txt = (request.form.get("horas") or "").strip()
            desde = (request.form.get("desde") or "").strip() or None
            hasta = (request.form.get("hasta") or "").strip() or None
            observaciones = (request.form.get("observaciones") or "").strip() or None

            def fnum(val):
                try:
                    return float(val)
                except Exception:
                    return 0.0

            dias = fnum(dias_txt)
            horas = fnum(horas_txt)

            if tipo not in ("INICIAL", "FERIA", "HORAS", "TOMA"):
                flash("Seleccion? un tipo v?lido.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorios", id=id))

            if tipo in ("INICIAL", "FERIA") and dias <= 0:
                flash("Ingres? la cantidad de d?as.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorios", id=id))

            if tipo == "HORAS" and horas <= 0:
                flash("Ingres? la cantidad de horas.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorios", id=id))

            if tipo == "TOMA":
                if not desde or not hasta:
                    flash("Ingres? desde y hasta para la toma.", "warning")
                    con.close()
                    return redirect(url_for("agentes.agente_compensatorios", id=id))
                try:
                    d1 = datetime.strptime(desde, "%Y-%m-%d").date()
                    d2 = datetime.strptime(hasta, "%Y-%m-%d").date()
                    if d2 < d1:
                        d1, d2 = d2, d1
                    dias = float((d2 - d1).days + 1)
                    fecha = d1.isoformat()
                    desde = d1.isoformat()
                    hasta = d2.isoformat()
                except Exception:
                    flash("Fechas inv?lidas para la toma.", "warning")
                    con.close()
                    return redirect(url_for("agentes.agente_compensatorios", id=id))

            con.execute("""
                INSERT INTO agentes_compensatorios_mov
                    (agente_id, fecha, tipo, dias, horas, periodo, desde, hasta, observaciones)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (id, fecha, tipo, dias, horas, periodo, desde, hasta, observaciones))
            con.commit()
            con.close()
            rebuild_eventos_agentes()
            flash("Movimiento compensatorio guardado.", "success")
            return redirect(url_for("agentes.agente_compensatorios", id=id))

        comp_movs = con.execute("""
            SELECT
                id, fecha, tipo, dias, horas, periodo, desde, hasta, observaciones
            FROM agentes_compensatorios_mov
            WHERE agente_id = ?
            ORDER BY date(fecha) DESC, id DESC
        """, (id,)).fetchall()

        total_horas = 0.0
        dias_gen = 0.0
        dias_tom = 0.0
        for m in comp_movs:
            if (m["tipo"] or "").upper() in ("INICIAL", "FERIA"):
                dias_gen += float(m["dias"] or 0)
            elif (m["tipo"] or "").upper() == "TOMA":
                dias_tom += float(m["dias"] or 0)
            elif (m["tipo"] or "").upper() == "HORAS":
                total_horas += float(m["horas"] or 0)

        dias_horas = int(total_horas // 6)
        horas_rem = float(total_horas - (dias_horas * 6))
        saldo = {
            "dias": (dias_gen + dias_horas - dias_tom),
            "horas": horas_rem,
            "dias_generados": dias_gen + dias_horas,
            "dias_tomados": dias_tom,
        }

        con.close()
        return render_template(
            "agente_compensatorios_form.html",
            agente=agente,
            comp_movs=comp_movs,
            saldo=saldo,
            hoy=date.today().isoformat(),
        )



    @bp.route("/agentes/<int:agente_id>/compensatorios/<int:mov_id>/eliminar",
               methods=["POST"],
               endpoint="agente_compensatorio_eliminar")
    def agente_compensatorio_eliminar(agente_id, mov_id):
        con = get_db()
        con.execute("""
            DELETE FROM agentes_compensatorios_mov
            WHERE id = ? AND agente_id = ?
        """, (mov_id, agente_id))
        con.commit()
        con.close()
        rebuild_eventos_agentes()
        flash("Movimiento compensatorio eliminado.", "info")
        return redirect(url_for("agentes.agente_compensatorios", id=agente_id))



    @bp.route("/agentes/<int:agente_id>/compensatorios/<int:mov_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_compensatorio_editar")
    def agente_compensatorio_editar(agente_id, mov_id):
        con = get_db()
        con.execute("""
            CREATE TABLE IF NOT EXISTS agentes_compensatorios_mov(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agente_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                dias REAL DEFAULT 0,
                horas REAL DEFAULT 0,
                periodo TEXT,
                desde TEXT,
                hasta TEXT,
                observaciones TEXT
            )
        """)

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (agente_id,)).fetchone()

        mov = con.execute("""
            SELECT id, agente_id, fecha, tipo, dias, horas, periodo, desde, hasta, observaciones
            FROM agentes_compensatorios_mov
            WHERE id = ? AND agente_id = ?
        """, (mov_id, agente_id)).fetchone()

        if not agente or not mov:
            con.close()
            flash("Movimiento no encontrado.", "warning")
            return redirect(url_for("agentes.agente_compensatorios", id=agente_id))

        if request.method == "POST":
            tipo = (request.form.get("tipo") or "").strip().upper()
            fecha = (request.form.get("fecha") or date.today().isoformat()).strip()
            periodo = (request.form.get("periodo") or "").strip() or None
            dias_txt = (request.form.get("dias") or "").strip()
            horas_txt = (request.form.get("horas") or "").strip()
            desde = (request.form.get("desde") or "").strip() or None
            hasta = (request.form.get("hasta") or "").strip() or None
            observaciones = (request.form.get("observaciones") or "").strip() or None

            def fnum(val):
                try:
                    return float(val)
                except Exception:
                    return 0.0

            dias = fnum(dias_txt)
            horas = fnum(horas_txt)

            if tipo not in ("INICIAL", "FERIA", "HORAS", "TOMA"):
                flash("Seleccioná un tipo válido.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorio_editar",
                                        agente_id=agente_id, mov_id=mov_id))

            if tipo in ("INICIAL", "FERIA") and dias <= 0:
                flash("Ingresá la cantidad de días.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorio_editar",
                                        agente_id=agente_id, mov_id=mov_id))

            if tipo == "HORAS" and horas <= 0:
                flash("Ingresá la cantidad de horas.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_compensatorio_editar",
                                        agente_id=agente_id, mov_id=mov_id))

            if tipo == "TOMA":
                if not desde or not hasta:
                    flash("Ingresá desde y hasta para la toma.", "warning")
                    con.close()
                    return redirect(url_for("agentes.agente_compensatorio_editar",
                                            agente_id=agente_id, mov_id=mov_id))
                try:
                    d1 = datetime.strptime(desde, "%Y-%m-%d").date()
                    d2 = datetime.strptime(hasta, "%Y-%m-%d").date()
                    if d2 < d1:
                        d1, d2 = d2, d1
                    dias = float((d2 - d1).days + 1)
                    fecha = d1.isoformat()
                    desde = d1.isoformat()
                    hasta = d2.isoformat()
                except Exception:
                    flash("Fechas inválidas para la toma.", "warning")
                    con.close()
                    return redirect(url_for("agentes.agente_compensatorio_editar",
                                            agente_id=agente_id, mov_id=mov_id))

            con.execute("""
                UPDATE agentes_compensatorios_mov
                SET fecha = ?, tipo = ?, dias = ?, horas = ?, periodo = ?,
                    desde = ?, hasta = ?, observaciones = ?
                WHERE id = ? AND agente_id = ?
            """, (fecha, tipo, dias, horas, periodo, desde, hasta, observaciones, mov_id, agente_id))
            con.commit()
            con.close()
            rebuild_eventos_agentes()
            flash("Movimiento compensatorio actualizado.", "success")
            return redirect(url_for("agentes.agente_compensatorios", id=agente_id))

        con.close()
        return render_template(
            "agente_compensatorios_editar.html",
            agente=agente,
            mov=mov,
        )




    @bp.route("/agentes/<int:id>/desempeno", methods=["GET", "POST"], endpoint="agente_desempeno")
    def agente_desempeno(id):
        con = get_db()

        # datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            fecha = request.form.get("fecha", "").strip()
            tipo = request.form.get("tipo", "").strip()
            periodo = request.form.get("periodo", "").strip()
            calificacion_str = request.form.get("calificacion", "").strip()
            observaciones = request.form.get("observaciones", "").strip()
            estado = request.form.get("estado", "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "warning")
            else:
                try:
                    calificacion = int(calificacion_str) if calificacion_str else None
                except ValueError:
                    calificacion = None

                con.execute("""
                    INSERT INTO agentes_desempeno
                        (agente_id, fecha, tipo, periodo, calificacion, observaciones, estado)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    agente["id"], fecha, tipo, periodo, calificacion, observaciones, estado
                ))
                con.commit()

                # >>> actualizar eventos del calendario
                rebuild_eventos_agentes()

                flash("Registro de desempeño guardado.", "success")



        # traer desempeño del agente
        desempenos = con.execute("""
            SELECT id, fecha, tipo, periodo, calificacion, observaciones, estado
            FROM agentes_desempeno
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente["id"],)).fetchall()

        con.close()

 
        return render_template(
            "agente_desempeno_form.html",
            agente=agente,
            desempenos=desempenos,
            des_editar=None
        )


    @bp.route("/agentes/<int:agente_id>/desempeno/<int:des_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_desempeno_editar")
    def agente_desempeno_editar(agente_id, des_id):
        con = get_db()

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (agente_id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        registro = con.execute("""
            SELECT id, fecha, tipo, periodo, calificacion, observaciones, estado
            FROM agentes_desempeno
            WHERE id = ? AND agente_id = ?
        """, (des_id, agente_id)).fetchone()

        if not registro:
            con.close()
            flash("El registro de desempeño no existe.", "error")
            return redirect(url_for("agentes.agente_desempeno", id=agente_id))

        if request.method == "POST":
            fecha = request.form.get("fecha", "").strip()
            tipo = request.form.get("tipo", "").strip()
            periodo = request.form.get("periodo", "").strip()
            calificacion_str = request.form.get("calificacion", "").strip()
            observaciones = request.form.get("observaciones", "").strip()
            estado = request.form.get("estado", "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "warning")
            else:
                try:
                    calificacion = int(calificacion_str) if calificacion_str else None
                except ValueError:
                    calificacion = None

                con.execute("""
                    UPDATE agentes_desempeno
                    SET fecha = ?, tipo = ?, periodo = ?, calificacion = ?,
                        observaciones = ?, estado = ?
                    WHERE id = ? AND agente_id = ?
                """, (fecha, tipo, periodo, calificacion,
                      observaciones, estado, des_id, agente_id))
                con.commit()
                rebuild_eventos_agentes()
                con.close()
                flash("Registro de desempeño actualizado.", "success")
                return redirect(url_for("agentes.agente_desempeno", id=agente_id))

        desempenos = con.execute("""
            SELECT id, fecha, tipo, periodo, calificacion, observaciones, estado
            FROM agentes_desempeno
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente_id,)).fetchall()

        con.close()
        return render_template(
            "agente_desempeno_form.html",
            agente=agente,
            desempenos=desempenos,
            des_editar=registro
        )



    @bp.route("/agentes/<int:agente_id>/desempeno/<int:des_id>/eliminar",
               methods=["POST"],
               endpoint="agente_desempeno_eliminar")
    def agente_desempeno_eliminar(agente_id, des_id):
        con = get_db()
        con.execute("""
            DELETE FROM agentes_desempeno
            WHERE id = ? AND agente_id = ?
        """, (des_id, agente_id))
        con.commit()
        rebuild_eventos_agentes()
        con.close()

        flash("Registro de desempeño eliminado.", "success")
        return redirect(url_for("agentes.agente_desempeno", id=agente_id))




    @bp.route("/agentes/<int:id>/asignacion", methods=["GET", "POST"], endpoint="agente_asignacion")
    def agente_asignacion(id):
        con = get_db()

        # Traer datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        # Traer sedes para elegir (S01, S02, etc.)  <-- ACA EL CAMBIO
        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        if request.method == "POST":
            sede_codigo = request.form.get("sede_codigo", "").strip()
            fecha_desde = request.form.get("fecha_desde", "").strip()
            observaciones = request.form.get("observaciones", "").strip()

            if not sede_codigo or not fecha_desde:
                flash("Sede y fecha desde son obligatorias.", "warning")
            else:
                con.execute("""
                    INSERT INTO agentes_asignaciones (agente_id, sede_codigo, fecha_desde, observaciones, estado)
                    VALUES (?, ?, ?, ?, 'ACTIVA')
                """, (agente["id"], sede_codigo, fecha_desde, observaciones))
                con.commit()

                # >>> actualizar eventos del calendario
                rebuild_eventos_agentes()

                flash("Asignación guardada.", "success")


        # Historial de asignaciones de este agente
        asignaciones = con.execute("""
            SELECT id, sede_codigo, fecha_desde, fecha_hasta, observaciones, estado
            FROM agentes_asignaciones
            WHERE agente_id = ?
            ORDER BY fecha_desde DESC, id DESC
        """, (agente["id"],)).fetchall()

        con.close()

        return render_template(
            "agente_asignacion_form.html",
            agente=agente,
            sedes=sedes,
            asignaciones=asignaciones
        )




    @bp.route("/agentes/<int:id>/incidentes", methods=["GET", "POST"], endpoint="agente_incidentes")
    def agente_incidentes(id):
        con = get_db()

        # datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            fecha = request.form.get("fecha", "").strip()
            tipo = request.form.get("tipo", "").strip()
            lugar = request.form.get("lugar", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            consecuencia = request.form.get("consecuencia", "").strip()
            acciones = request.form.get("acciones", "").strip()
            estado = request.form.get("estado", "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "warning")
            else:
                con.execute("""
                    INSERT INTO agentes_incidentes
                        (agente_id, fecha, tipo, lugar, descripcion, consecuencia, acciones, estado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    agente["id"], fecha, tipo, lugar, descripcion,
                    consecuencia, acciones, estado
                ))
                con.commit()

                # >>> actualizar eventos del calendario
                rebuild_eventos_agentes()

                flash("Incidente registrado correctamente.", "success")


        # traer incidentes del agente
        incidentes = con.execute("""
            SELECT id, fecha, tipo, lugar, descripcion, consecuencia, acciones, estado
            FROM agentes_incidentes
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente["id"],)).fetchall()

        con.close()

        return render_template(
            "agente_incidentes_form.html",
            agente=agente,
            incidentes=incidentes
        )



    @bp.route("/agentes/<int:id>/sst", methods=["GET", "POST"], endpoint="agente_sst")
    def agente_sst(id):
        con = get_db()

        agente = con.execute("""
            SELECT id, agente, rubro
            FROM agentes_intendencia
            WHERE id = ?
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("Agente no encontrado.", "warning")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            fecha = (request.form.get("fecha") or "").strip()
            tipo = (request.form.get("tipo") or "").strip()
            titulo = (request.form.get("titulo") or "").strip()
            detalle = (request.form.get("detalle") or "").strip()
            estado = (request.form.get("estado") or "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "error")
                return redirect(url_for("agentes.agente_sst", id=id))

            con.execute("""
                INSERT INTO agentes_sst (agente_id, fecha, tipo, titulo, detalle, estado)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id, fecha, tipo, titulo, detalle, estado))
            con.commit()
            con.close()
            rebuild_eventos_agentes()
            flash("Registro SST guardado.", "success")
            return redirect(url_for("agentes.agente_sst", id=id))

        sst_registros = con.execute("""
            SELECT id, fecha, tipo, titulo, detalle, estado
            FROM agentes_sst
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (id,)).fetchall()

        con.close()

        return render_template(
            "agente_sst_form.html",
            agente=agente,
            sst_registros=sst_registros
        )



    @bp.route("/agentes/<int:agente_id>/sst/<int:sst_id>/eliminar",
               methods=["POST"], endpoint="agente_sst_eliminar")
    def agente_sst_eliminar(agente_id, sst_id):
        con = get_db()
        con.execute("""
            DELETE FROM agentes_sst
            WHERE id = ? AND agente_id = ?
        """, (sst_id, agente_id))
        con.commit()
        con.close()
        rebuild_eventos_agentes()
        flash("Registro SST eliminado.", "success")
        return redirect(url_for("agentes.agente_sst", id=agente_id))





    def _seed_sst_control_objetivos(con):
        rows = con.execute("SELECT COUNT(1) AS n FROM sst_control_objetivos").fetchone()
        if rows and rows["n"] > 0:
            return
        defaults = [
            "Carteleria",
            "Ubicacion de matafuegos",
            "Luces de emergencia",
        ]
        for nombre in defaults:
            con.execute("INSERT INTO sst_control_objetivos (nombre) VALUES (?)", (nombre,))
        con.commit()


    def _sst_parse_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None


    def _sst_month_ticks(range_start, range_end):
        if not range_start or not range_end:
            return []
        total_days = (range_end - range_start).days + 1
        if total_days <= 0:
            return []
        ticks = []
        cur = date(range_start.year, range_start.month, 1)
        months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        while cur <= range_end:
            left = (cur - range_start).days / total_days * 100
            label = f"{months[cur.month - 1]} {cur.year}"
            ticks.append({"label": label, "left": round(left, 2)})
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return ticks


    def _sst_bar(range_start, range_end, start_date, end_date):
        if not range_start or not range_end or not start_date or not end_date:
            return None, None
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        total_days = (range_end - range_start).days + 1
        if total_days <= 0:
            return None, None
        start_off = max(0, (start_date - range_start).days)
        end_off = min((end_date - range_start).days, total_days - 1)
        left = start_off / total_days * 100
        width = (end_off - start_off + 1) / total_days * 100
        return round(left, 2), round(width, 2)


    @bp.route("/agentes/<int:id>/epp", methods=["GET", "POST"], endpoint="agente_epp")
    def agente_epp(id):
        con = get_db()

        # datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo          = request.form.get("tipo", "").strip()
            categoria     = request.form.get("categoria", "").strip()
            fecha_entrega = request.form.get("fecha_entrega", "").strip()
            cantidad      = request.form.get("cantidad", "1").strip()
            estado        = request.form.get("estado", "").strip()
            observaciones = request.form.get("observaciones", "").strip()

            if not tipo or not fecha_entrega:
                flash("Tipo y fecha de entrega son obligatorios.", "warning")
            else:
                try:
                    cant_int = int(cantidad)
                except ValueError:
                    cant_int = 1

                con.execute("""
                    INSERT INTO agentes_epp
                        (agente_id, tipo, categoria, fecha_entrega, cantidad,
                         observaciones, estado)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    agente["id"], tipo, categoria, fecha_entrega,
                    cant_int, observaciones, estado
                ))
                con.commit()

                rebuild_eventos_agentes()
                flash("Entrega de EPP / herramienta registrada.", "success")

        # traer todas las entregas del agente para mostrar
        entregas = con.execute("""
            SELECT id, tipo, categoria, fecha_entrega, cantidad, estado, observaciones
            FROM agentes_epp
            WHERE agente_id = ?
            ORDER BY fecha_entrega DESC, id DESC
        """, (agente["id"],)).fetchall()

        con.close()

        return render_template(
            "agente_epp_form.html",
            agente=agente,
            entregas=entregas,
            epp_editar=None
        )



    @bp.route("/agentes/<int:agente_id>/epp/<int:epp_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_epp_editar")
    def agente_epp_editar(agente_id, epp_id):
        con = get_db()

        # agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (agente_id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        # entrega a editar
        entrega = con.execute("""
            SELECT id, tipo, categoria, fecha_entrega, cantidad, estado, observaciones
            FROM agentes_epp
            WHERE id = ? AND agente_id = ?
        """, (epp_id, agente_id)).fetchone()

        if not entrega:
            con.close()
            flash("La entrega de EPP / herramienta no existe.", "error")
            return redirect(url_for("agentes.agente_epp", id=agente_id))

        if request.method == "POST":
            tipo          = request.form.get("tipo", "").strip()
            categoria     = request.form.get("categoria", "").strip()
            fecha_entrega = request.form.get("fecha_entrega", "").strip()
            cantidad      = request.form.get("cantidad", "1").strip()
            estado        = request.form.get("estado", "").strip()
            observaciones = request.form.get("observaciones", "").strip()

            if not tipo or not fecha_entrega:
                flash("Tipo y fecha de entrega son obligatorios.", "warning")
            else:
                try:
                    cant_int = int(cantidad)
                except ValueError:
                    cant_int = 1

                con.execute("""
                    UPDATE agentes_epp
                    SET tipo = ?, categoria = ?, fecha_entrega = ?, cantidad = ?,
                        observaciones = ?, estado = ?
                    WHERE id = ? AND agente_id = ?
                """, (tipo, categoria, fecha_entrega, cant_int,
                      observaciones, estado, epp_id, agente_id))
                con.commit()

                rebuild_eventos_agentes()
                con.close()
                flash("Entrega de EPP / herramienta actualizada.", "success")
                return redirect(url_for("agentes.agente_epp", id=agente_id))

        # recargar listado completo
        entregas = con.execute("""
            SELECT id, tipo, categoria, fecha_entrega, cantidad, estado, observaciones
            FROM agentes_epp
            WHERE agente_id = ?
            ORDER BY fecha_entrega DESC, id DESC
        """, (agente_id,)).fetchall()

        con.close()
        return render_template(
            "agente_epp_form.html",
            agente=agente,
            entregas=entregas,
            epp_editar=entrega
        )



    @bp.route("/agentes/<int:agente_id>/epp/<int:epp_id>/eliminar",
               methods=["POST"],
               endpoint="agente_epp_eliminar")
    def agente_epp_eliminar(agente_id, epp_id):
        con = get_db()
        con.execute("""
            DELETE FROM agentes_epp
            WHERE id = ? AND agente_id = ?
        """, (epp_id, agente_id))
        con.commit()
        rebuild_eventos_agentes()
        con.close()

        flash("Entrega de EPP / herramienta eliminada.", "success")
        return redirect(url_for("agentes.agente_epp", id=agente_id))







    @bp.route("/agentes/<int:id>/documentacion", methods=["GET", "POST"], endpoint="agente_documentacion")
    def agente_documentacion(id):
        con = get_db()
        ensure_cols(con, "agentes_documentacion", [("archivo", "TEXT"), ("archivo_url", "TEXT")])

        # datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (id,)).fetchone()

        if not agente:
            con.close()
            flash("El agente no existe o está inactivo.", "error")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo = request.form.get("tipo", "").strip()
            fecha_venc = request.form.get("fecha_vencimiento", "").strip()
            estado = request.form.get("estado", "").strip()
            observaciones = request.form.get("observaciones", "").strip()
            archivo = request.files.get("archivo")
            archivo_url = request.form.get("archivo_url", "").strip()
            archivo_nombre = None
            archivo_error = False

            if not tipo or not fecha_venc:
                flash("Tipo y fecha de vencimiento son obligatorios.", "warning")
            else:
                if archivo and archivo.filename.strip():
                    if not allowed_agente_doc(archivo.filename):
                        flash("Archivo: formato no permitido. Usa PDF/JPG/PNG.", "warning")
                        archivo_error = True
                    else:
                        nombre_seguro = secure_filename(archivo.filename)
                        _, ext = os.path.splitext(nombre_seguro)
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        archivo_nombre = f"agente_{agente['id']}_{tipo}_{ts}{ext.lower()}"
                        archivo.save(os.path.join(AGENTE_DOCS_FOLDER, archivo_nombre))

                if archivo_error:
                    documentos = con.execute("""
                        SELECT id, tipo, fecha_vencimiento, estado, observaciones, archivo, archivo_url
                        FROM agentes_documentacion
                        WHERE agente_id = ?
                        ORDER BY tipo
                    """, (agente["id"],)).fetchall()
                    con.close()
                    return render_template("agente_documentacion_form.html",
                                           agente=agente,
                                           documentos=documentos)

                con.execute("""
                    INSERT INTO agentes_documentacion
                        (agente_id, tipo, fecha_vencimiento, observaciones, estado, archivo, archivo_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agente_id, tipo) DO UPDATE SET
                        fecha_vencimiento = excluded.fecha_vencimiento,
                        observaciones    = excluded.observaciones,
                        estado           = excluded.estado,
                        archivo          = COALESCE(excluded.archivo, agentes_documentacion.archivo),
                        archivo_url      = COALESCE(excluded.archivo_url, agentes_documentacion.archivo_url)
                """, (agente["id"], tipo, fecha_venc, observaciones, estado, archivo_nombre, archivo_url or None))
                con.commit()

                # >>> actualizar eventos del calendario
                rebuild_eventos_agentes()

                flash("Documentación guardada correctamente.", "success")


            # volvemos al mismo formulario
            documentos = con.execute("""
                SELECT id, tipo, fecha_vencimiento, estado, observaciones, archivo, archivo_url
                FROM agentes_documentacion
                WHERE agente_id = ?
                ORDER BY tipo
            """, (agente["id"],)).fetchall()

            con.close()
            return render_template("agente_documentacion_form.html",
                                   agente=agente,
                                   documentos=documentos)

        # GET: cargar documentos existentes y mostrar el form
        documentos = con.execute("""
            SELECT id, tipo, fecha_vencimiento, estado, observaciones, archivo, archivo_url
            FROM agentes_documentacion
            WHERE agente_id = ?
            ORDER BY tipo
        """, (agente["id"],)).fetchall()
        con.close()

        return render_template("agente_documentacion_form.html",
                               agente=agente,
                               documentos=documentos)

    # =========================
    # DOCUMENTACION: ARCHIVOS
    # =========================

    @bp.route("/agentes/documentacion/archivo/<path:filename>",
               endpoint="agente_documentacion_archivo")
    def agente_documentacion_archivo(filename):
        return send_from_directory(AGENTE_DOCS_FOLDER, filename, as_attachment=False)

    # =========================
    # DOCUMENTOS: EDITAR / ELIMINAR DESDE LA FICHA
    # =========================

    @bp.route("/agentes/<int:agente_id>/documentos/<int:doc_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_documento_editar")
    def agente_documento_editar(agente_id, doc_id):
        con = get_db()
        ensure_cols(con, "agentes_documentacion", [("archivo", "TEXT"), ("archivo_url", "TEXT")])

        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (agente_id,)).fetchone()

        documento = con.execute("""
            SELECT id, tipo, fecha_vencimiento, estado, observaciones, archivo, archivo_url
            FROM agentes_documentacion
            WHERE id = ? AND agente_id = ?
        """, (doc_id, agente_id)).fetchone()

        if not agente or not documento:
            con.close()
            flash("Documento o agente no encontrado.", "warning")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            tipo = (request.form.get("tipo") or "").strip()
            fecha_venc = (request.form.get("fecha_vencimiento") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()
            archivo = request.files.get("archivo")
            archivo_url = (request.form.get("archivo_url") or "").strip()
            archivo_nombre = documento["archivo"]

            if not tipo or not fecha_venc:
                flash("Tipo y fecha de vencimiento son obligatorios.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_documento_editar",
                                        agente_id=agente_id, doc_id=doc_id))

            if archivo and archivo.filename.strip():
                if not allowed_agente_doc(archivo.filename):
                    flash("Archivo: formato no permitido. Usa PDF/JPG/PNG.", "warning")
                    con.close()
                    return redirect(url_for("agentes.agente_documento_editar",
                                            agente_id=agente_id, doc_id=doc_id))
                nombre_seguro = secure_filename(archivo.filename)
                _, ext = os.path.splitext(nombre_seguro)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                archivo_nombre = f"agente_{agente_id}_{tipo}_{ts}{ext.lower()}"
                archivo.save(os.path.join(AGENTE_DOCS_FOLDER, archivo_nombre))

            if not archivo_url:
                archivo_url = documento["archivo_url"]

            con.execute("""
                UPDATE agentes_documentacion
                SET tipo = ?, fecha_vencimiento = ?, estado = ?, observaciones = ?, archivo = ?, archivo_url = ?
                WHERE id = ? AND agente_id = ?
            """, (tipo, fecha_venc, estado, observaciones, archivo_nombre, archivo_url, doc_id, agente_id))
            con.commit()
            con.close()

            # opcional: actualizar calendario, si lo usás para vencimientos
            rebuild_eventos_agentes()

            flash("✅ Documento actualizado correctamente.", "success")
            return redirect(url_for("agentes.agentes_home", id=agente_id))

        con.close()
        return render_template("agente_documento_form.html",
                               agente=agente,
                               documento=documento)



    @bp.route("/agentes/<int:agente_id>/documentos/<int:doc_id>/eliminar",
               methods=["POST"],
               endpoint="agente_documento_eliminar")
    def agente_documento_eliminar(agente_id, doc_id):
        con = get_db()

        con.execute("""
            DELETE FROM agentes_documentacion
            WHERE id = ? AND agente_id = ?
        """, (doc_id, agente_id))
        con.commit()
        con.close()

        # opcional: si los eventos dependen de este registro
        rebuild_eventos_agentes()

        flash("🗑️ Documento eliminado.", "info")
        return redirect(url_for("agentes.agentes_home", id=agente_id))

    # =========================
    # INCIDENTES: EDITAR / ELIMINAR DESDE LA FICHA
    # =========================
    # =========================
    # INCIDENTES: EDITAR / ELIMINAR DESDE LA FICHA
    # =========================

    @bp.route("/agentes/<int:agente_id>/incidentes/<int:inc_id>/editar",
               methods=["GET", "POST"],
               endpoint="agente_incidente_editar")
    def agente_incidente_editar(agente_id, inc_id):
        con = get_db()

        # datos del agente
        agente = con.execute("""
            SELECT id, agente, rubro, dias_feria
            FROM agentes_intendencia
            WHERE id = ? AND activo = 1
        """, (agente_id,)).fetchone()

        # incidente a editar
        incidente = con.execute("""
            SELECT id, fecha, tipo, lugar, descripcion, consecuencia, acciones, estado
            FROM agentes_incidentes
            WHERE id = ? AND agente_id = ?
        """, (inc_id, agente_id)).fetchone()

        # historial para el panel derecho
        incidentes = con.execute("""
            SELECT id, fecha, tipo, lugar, descripcion, consecuencia, acciones, estado
            FROM agentes_incidentes
            WHERE agente_id = ?
            ORDER BY fecha DESC, id DESC
        """, (agente_id,)).fetchall()

        if not agente or not incidente:
            con.close()
            flash("Incidente o agente no encontrado.", "warning")
            return redirect(url_for("agentes.agentes_home"))

        if request.method == "POST":
            fecha        = (request.form.get("fecha") or "").strip()
            tipo         = (request.form.get("tipo") or "").strip()
            lugar        = (request.form.get("lugar") or "").strip()
            descripcion  = (request.form.get("descripcion") or "").strip()
            consecuencia = (request.form.get("consecuencia") or "").strip()
            acciones     = (request.form.get("acciones") or "").strip()
            estado       = (request.form.get("estado") or "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "warning")
                con.close()
                return redirect(url_for("agentes.agente_incidente_editar",
                                        agente_id=agente_id, inc_id=inc_id))

            con.execute("""
                UPDATE agentes_incidentes
                SET fecha = ?, tipo = ?, lugar = ?, descripcion = ?,
                    consecuencia = ?, acciones = ?, estado = ?
                WHERE id = ? AND agente_id = ?
            """, (fecha, tipo, lugar, descripcion,
                  consecuencia, acciones, estado, inc_id, agente_id))
            con.commit()
            con.close()

            rebuild_eventos_agentes()

            flash("✅ Incidente / accidente actualizado.", "success")
            return redirect(url_for("agentes.agentes_home", id=agente_id))

        con.close()
        return render_template(
            "agente_incidente_form.html",   # <--- NOMBRE EXACTO DEL ARCHIVO
            agente=agente,
            incidente=incidente,
            incidentes=incidentes
        )



    @bp.route("/agentes/<int:agente_id>/incidentes/<int:inc_id>/eliminar",
               methods=["POST"],
               endpoint="agente_incidente_eliminar")
    def agente_incidente_eliminar(agente_id, inc_id):
        con = get_db()

        con.execute("""
            DELETE FROM agentes_incidentes
            WHERE id = ? AND agente_id = ?
        """, (inc_id, agente_id))
        con.commit()
        con.close()

        rebuild_eventos_agentes()

        flash("🗑️ Incidente / accidente eliminado.", "info")
        return redirect(url_for("agentes.agentes_home", id=agente_id))

    # -----------------------------------------------------
    # CAPACITACIONES - GANTT (PDF ESTÁTICO)
    # -----------------------------------------------------
