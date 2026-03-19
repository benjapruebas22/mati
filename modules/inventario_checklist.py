from datetime import date
import sqlite3

from flask import render_template, request, redirect, url_for, flash


def register_inventario_checklist(app, get_db):
    if "checklist_mobiliario" in app.view_functions:
        return
    @app.route("/checklist/inventario", methods=["GET", "POST"])
    def checklist_inventario():
        con = get_db()
        cur = con.cursor()

        hoy = date.today().isoformat()

        # ===== 1) AGENTES INTENDENCIA (para el combo) =====
        try:
            cur.execute("""
                SELECT id, agente
                FROM agentes_intendencia
                WHERE activo = 1
                ORDER BY agente
            """)
            agentes = cur.fetchall()
        except sqlite3.OperationalError:
            agentes = []

        # ===== 2) DEPÓSITOS / AMBIENTES POR SEDE (Ficha sede) =====
        cur.execute("""
            SELECT
                codigo_sede,
                codigo_local,
                descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """)
        depositos_rows = cur.fetchall()

        # Mapa de inventario oficial por sede + sufijo de depósito (Dxx)
        cur.execute("""
            SELECT
                i.*
            FROM inventario_sede i
            ORDER BY i.sede_codigo, i.deposito_codigo
        """)
        inventario_rows = cur.fetchall()

        def _dep_suffix(dep):
            return (dep or "").split("-")[-1].strip()

        inv_map = {}
        for inv in inventario_rows:
            key = f"{inv['sede_codigo']}|{_dep_suffix(inv['deposito_codigo'])}"
            inv_map[key] = inv

        # ===== 3) SI VIENE POST → GUARDAR CONTROL =====
        if request.method == "POST":
            fecha = request.form.get("fecha") or hoy
            dep_sel = (request.form.get("deposito_sel") or "").strip()
            agente_id = request.form.get("agente_id") or None
            observaciones = request.form.get("observaciones", "").strip()

            if not dep_sel or "|" not in dep_sel:
                flash("Elegí un depósito / ambiente para controlar.", "error")
                return redirect(url_for("checklist_inventario"))

            sede_codigo, deposito_codigo = [p.strip() for p in dep_sel.split("|", 1)]
            dep_suffix = _dep_suffix(deposito_codigo)

            # Buscamos la fila oficial en inventario_sede (si existe)
            cur.execute("""
                SELECT *
                FROM inventario_sede
                WHERE sede_codigo = ?
                  AND (deposito_codigo = ? OR deposito_codigo LIKE ?)
                ORDER BY deposito_codigo
                LIMIT 1
            """, (sede_codigo, deposito_codigo, f"%-{dep_suffix}"))
            inv = cur.fetchone()

            # Función auxiliar para leer números (si está vacío, uso el oficial)
            def _n(name, default_val):
                val = request.form.get(name, "").strip()
                if val == "":
                    return default_val
                try:
                    return int(val)
                except ValueError:
                    return default_val

            aire_off      = inv["aire_marca"] if inv else 0
            esc_off       = inv["escritorio_prof"] if inv else 0
            mesa_off      = inv["mesa_pc"] if inv else 0
            silla_gir_off = inv["silla_giratoria"] if inv else 0
            silla_fija_off= inv["silla_fija"] if inv else 0
            armario_off   = inv["armario_alto"] if inv else 0
            biblio_off    = inv["biblioteca_baja"] if inv else 0
            otros_off     = inv["otros"] if inv else 0

            aire_ctrl      = _n("aire_marca_control",      aire_off)
            esc_ctrl       = _n("escritorio_prof_control", esc_off)
            mesa_ctrl      = _n("mesa_pc_control",         mesa_off)
            silla_gir_ctrl = _n("silla_giratoria_control", silla_gir_off)
            silla_fija_ctrl= _n("silla_fija_control",      silla_fija_off)
            armario_ctrl   = _n("armario_alto_control",    armario_off)
            biblio_ctrl    = _n("biblioteca_baja_control", biblio_off)
            otros_ctrl     = _n("otros_control",           otros_off)

            agente_nombre = None
            if agente_id:
                try:
                    cur.execute("""
                        SELECT agente
                        FROM agentes_intendencia
                        WHERE id = ?
                    """, (agente_id,))
                    row_ag = cur.fetchone()
                    if row_ag:
                        agente_nombre = row_ag["agente"]
                except sqlite3.OperationalError:
                    agente_nombre = None

            cur.execute("""
                INSERT INTO checklist_inventario_control(
                    fecha,
                    inventario_id, sede_codigo, deposito_codigo,
                    agente_id, agente_nombre,

                    -- valores oficiales (inventario_sede)
                    aire_marca_oficial,
                    escritorio_prof_oficial,
                    mesa_pc_oficial,
                    silla_giratoria_oficial,
                    silla_fija_oficial,
                    armario_alto_oficial,
                    biblioteca_baja_oficial,
                    otros_oficial,

                    -- valores del control que carga el agente
                    aire_marca,
                    escritorio_prof,
                    mesa_pc,
                    silla_giratoria,
                    silla_fija,
                    armario_alto,
                    biblioteca_baja,
                    otros,
                    observaciones
                )
                VALUES (?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?)
            """, (
                fecha,
                (inv["id"] if inv else None), sede_codigo, deposito_codigo,
                agente_id, agente_nombre,

                aire_off,
                esc_off,
                mesa_off,
                silla_gir_off,
                silla_fija_off,
                armario_off,
                biblio_off,
                otros_off,

                aire_ctrl,
                esc_ctrl,
                mesa_ctrl,
                silla_gir_ctrl,
                silla_fija_ctrl,
                armario_ctrl,
                biblio_ctrl,
                otros_ctrl,
                observaciones
            ))

            con.commit()
            flash("Checklist de inventario guardado correctamente.", "success")
            return redirect(url_for("checklist_inventario"))

        # ===== 4) ÚLTIMOS CONTROLES REGISTRADOS =====
        cur.execute("""
            SELECT
                c.* 
            FROM checklist_inventario_control c
            ORDER BY c.fecha DESC, c.id DESC
            LIMIT 30
        """)
        controles = cur.fetchall()

        con.close()

        return render_template(
            "checklist_inventario.html",
            hoy=hoy,
            agentes=agentes,
            depositos_rows=depositos_rows,
            inv_map=inv_map,
            controles=controles
        )

    @app.route("/checklist/inventario/<int:cid>/editar", methods=["GET", "POST"],
               endpoint="checklist_inventario_editar")
    def checklist_inventario_editar(cid):
        con = get_db()
        cur = con.cursor()

        # Agentes (combo)
        try:
            cur.execute("""
                SELECT id, agente
                FROM agentes_intendencia
                WHERE activo = 1
                ORDER BY agente
            """)
            agentes = cur.fetchall()
        except sqlite3.OperationalError:
            agentes = []

        # Control existente
        cur.execute("""
            SELECT *
            FROM checklist_inventario_control
            WHERE id = ?
        """, (cid,))
        control = cur.fetchone()
        if not control:
            con.close()
            flash("No se encontró el control seleccionado.", "error")
            return redirect(url_for("checklist_mobiliario"))

        if request.method == "POST":
            fecha = request.form.get("fecha") or control["fecha"]
            agente_id = request.form.get("agente_id") or None
            observaciones = request.form.get("observaciones", "").strip()

            def _n(name, default_val):
                val = request.form.get(name, "").strip()
                if val == "":
                    return default_val
                try:
                    return int(val)
                except ValueError:
                    return default_val

            aire_ctrl      = _n("aire_marca_control",      control["aire_marca"])
            esc_ctrl       = _n("escritorio_prof_control", control["escritorio_prof"])
            mesa_ctrl      = _n("mesa_pc_control",         control["mesa_pc"])
            silla_gir_ctrl = _n("silla_giratoria_control", control["silla_giratoria"])
            silla_fija_ctrl= _n("silla_fija_control",      control["silla_fija"])
            armario_ctrl   = _n("armario_alto_control",    control["armario_alto"])
            biblio_ctrl    = _n("biblioteca_baja_control", control["biblioteca_baja"])
            otros_ctrl     = _n("otros_control",           control["otros"])

            agente_nombre = None
            if agente_id:
                try:
                    cur.execute("""
                        SELECT agente
                        FROM agentes_intendencia
                        WHERE id = ?
                    """, (agente_id,))
                    row_ag = cur.fetchone()
                    if row_ag:
                        agente_nombre = row_ag["agente"]
                except sqlite3.OperationalError:
                    agente_nombre = None

            cur.execute("""
                UPDATE checklist_inventario_control
                SET fecha = ?,
                    agente_id = ?,
                    agente_nombre = ?,
                    aire_marca = ?,
                    escritorio_prof = ?,
                    mesa_pc = ?,
                    silla_giratoria = ?,
                    silla_fija = ?,
                    armario_alto = ?,
                    biblioteca_baja = ?,
                    otros = ?,
                    observaciones = ?
                WHERE id = ?
            """, (
                fecha,
                agente_id, agente_nombre,
                aire_ctrl,
                esc_ctrl,
                mesa_ctrl,
                silla_gir_ctrl,
                silla_fija_ctrl,
                armario_ctrl,
                biblio_ctrl,
                otros_ctrl,
                observaciones,
                cid
            ))

            con.commit()
            con.close()
            flash("Control actualizado.", "success")
            return redirect(url_for("checklist_mobiliario"))

        con.close()
        return render_template(
            "checklist_inventario_edit.html",
            control=control,
            agentes=agentes
        )

    @app.route("/checklist/mobiliario")
    def checklist_mobiliario():
        con = get_db()
        cur = con.cursor()

        cur.execute("""
            SELECT *
            FROM checklist_inventario_control
            ORDER BY fecha DESC, id DESC
            LIMIT 200
        """)
        controles = cur.fetchall()
        con.close()

        return render_template("checklist_mobiliario.html", controles=controles)
