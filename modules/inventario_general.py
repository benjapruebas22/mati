import sqlite3

from flask import render_template, request, redirect, url_for, flash


def register_inventario_general(app, get_db, get_db_connection, ensure_luminarias_columns):
    @app.route("/sedes/<codigo>/inventario", methods=["GET", "POST"])
    def sede_inventario(codigo):
        con = get_db_connection()

        # 1) Datos básicos de la sede
        sede = con.execute(
            "SELECT * FROM sedes_mpd WHERE codigo = ?",
            (codigo,)
        ).fetchone()

        if not sede:
            con.close()
            flash("Sede no encontrada.", "error")
            return redirect(url_for("dashboard"))

        # 2) Infraestructura (tabla: sedes_infraestructura)
        infra = con.execute("""
            SELECT oficinas,
                   salas_entrevistas,
                   banios,
                   espacios_comunes,
                   depositos,
                   personas,
                   m2_totales,
                   m2_por_persona,
                   personas_por_oficina
            FROM sedes_infraestructura
            WHERE sede_codigo = ?
        """, (codigo,)).fetchone()


        # Si no hay registro de infraestructura, devuelvo todo en 0
        if infra is None:
            infra = {
                "oficinas": 0,
                "salas_entrevistas": 0,
                "banios": 0,
                "espacios_comunes": 0,
                "depositos": 0,
                "personas": 0,
                "m2_totales": 0,
                "m2_por_persona": 0,
                "personas_por_oficina": 0,
            }

        # 3) Lista de depósitos / ambientes de esta sede
        depositos = con.execute("""
            SELECT id, codigo_local, descripcion
            FROM sedes_depositos
            WHERE codigo_sede = ?
            ORDER BY codigo_local
        """, (codigo,)).fetchall()

        # 4) Si viene POST: alta / edición de inventario_sede
        if request.method == "POST":
            inv_id = request.form.get("inv_id")  # vacío = alta

            deposito_codigo = request.form.get("deposito_codigo", "").strip()

            aire_marca      = int(request.form.get("aire_marca") or 0)
            escritorio_prof = int(request.form.get("escritorio_prof") or 0)
            mesa_pc         = int(request.form.get("mesa_pc") or 0)
            silla_giratoria = int(request.form.get("silla_giratoria") or 0)
            silla_fija      = int(request.form.get("silla_fija") or 0)
            armario_alto    = int(request.form.get("armario_alto") or 0)
            biblioteca_baja = int(request.form.get("biblioteca_baja") or 0)
            otros           = int(request.form.get("otros") or 0)
            otros_detalle   = request.form.get("otros_detalle", "").strip()

            if not deposito_codigo:
                flash("Debés elegir un depósito / ambiente.", "error")
                con.close()
                return redirect(url_for("sede_inventario", codigo=codigo))

            if inv_id:  # EDITAR
                con.execute("""
                    UPDATE inventario_sede
                    SET deposito_codigo = ?,
                        aire_marca      = ?,
                        escritorio_prof = ?,
                        mesa_pc         = ?,
                        silla_giratoria = ?,
                        silla_fija      = ?,
                        armario_alto    = ?,
                        biblioteca_baja = ?,
                        otros           = ?,
                        otros_detalle   = ?
                    WHERE id = ? AND sede_codigo = ?
                """, (
                    deposito_codigo,
                    aire_marca, escritorio_prof, mesa_pc,
                    silla_giratoria, silla_fija, armario_alto,
                    biblioteca_baja, otros, otros_detalle,
                    inv_id, codigo
                ))
            else:       # ALTA
                con.execute("""
                    INSERT INTO inventario_sede (
                        sede_codigo,
                        deposito_codigo,
                        aire_marca,
                        escritorio_prof,
                        mesa_pc,
                        silla_giratoria,
                        silla_fija,
                        armario_alto,
                        biblioteca_baja,
                        otros,
                        otros_detalle
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    codigo,
                    deposito_codigo,
                    aire_marca,
                    escritorio_prof,
                    mesa_pc,
                    silla_giratoria,
                    silla_fija,
                    armario_alto,
                    biblioteca_baja,
                    otros,
                    otros_detalle
                ))

            con.commit()
            con.close()
            flash("Registro de inventario guardado.", "ok")
            return redirect(url_for("sede_inventario", codigo=codigo))

        # 5) Listado de inventario de esta sede
        registros = con.execute("""
            SELECT i.*,
                   d.descripcion
            FROM inventario_sede AS i
            LEFT JOIN sedes_depositos AS d
              ON d.codigo_sede = i.sede_codigo
             AND d.codigo_local = i.deposito_codigo
            WHERE i.sede_codigo = ?
            ORDER BY i.deposito_codigo
        """, (codigo,)).fetchall()

        # 5 bis) Totales de mobiliario por sede (para el resumen)
        totales = {
            "aire_marca": 0,
            "escritorio_prof": 0,
            "mesa_pc": 0,
            "silla_giratoria": 0,
            "silla_fija": 0,
            "armario_alto": 0,
            "biblioteca_baja": 0,
            "otros": 0,
        }
        for r in registros:
            for campo in totales.keys():
                valor = r[campo] or 0
                totales[campo] += valor

        # 6) Si viene edit_id en la URL, cargamos ese registro
        edit_id = request.args.get("edit_id")
        edit_registro = None
        if edit_id:
            edit_registro = con.execute("""
                SELECT *
                FROM inventario_sede
                WHERE id = ? AND sede_codigo = ?
            """, (edit_id, codigo)).fetchone()

        con.close()

        plano_url = None  # por ahora

        return render_template(
            "sede_inventario.html",
            sede=sede,
            infra=infra,
            registros=registros,
            edit_registro=edit_registro,
            plano_url=plano_url,
            depositos=depositos,
            totales=totales,   # resumen para el dashboard
        )



    @app.route("/inventario_sede/<int:inv_id>/borrar", methods=["POST"])
    def inventario_sede_borrar(inv_id):
        sede_codigo = request.form.get("sede_codigo")

        con = get_db_connection()
        con.execute("DELETE FROM inventario_sede WHERE id = ?", (inv_id,))
        con.commit()
        con.close()

        flash("Registro de inventario eliminado.", "ok")
        return redirect(url_for("sede_inventario", codigo=sede_codigo))



    @app.route("/inventario/dashboard", endpoint="inventario_dashboard")
    def inventario_dashboard():
        ensure_luminarias_columns()
        con = get_db()
        resumen = con.execute("""
            SELECT
                s.codigo AS cod_sede,
                s.nombre AS sede,
                COALESCE(m.aire_marca,0) AS aire_marca,
                COALESCE(m.escritorio_prof,0) AS escritorio_prof,
                COALESCE(m.mesa_pc,0) AS mesa_pc,
                COALESCE(m.silla_giratoria,0) AS silla_giratoria,
                COALESCE(m.silla_fija,0) AS silla_fija,
                COALESCE(m.armario_alto,0) AS armario_alto,
                COALESCE(m.biblioteca_baja,0) AS biblioteca_baja,
                COALESCE(m.otros,0) AS otros,
                COALESCE(a.aires_total,0) AS aires_total,
                COALESCE(l.luminarias_total,0) AS luminarias_total,
                COALESCE(l.puestos_trabajo,0) AS puestos_trabajo
            FROM sedes_mpd s
            LEFT JOIN (
                SELECT
                    codigo_sede,
                    COALESCE(SUM(COALESCE(aire_marca,0)),0) AS aire_marca,
                    COALESCE(SUM(COALESCE(escritorio_prof,0)),0) AS escritorio_prof,
                    COALESCE(SUM(COALESCE(mesa_pc,0)),0) AS mesa_pc,
                    COALESCE(SUM(COALESCE(silla_giratoria,0)),0) AS silla_giratoria,
                    COALESCE(SUM(COALESCE(silla_fija,0)),0) AS silla_fija,
                    COALESCE(SUM(COALESCE(armario_alto,0)),0) AS armario_alto,
                    COALESCE(SUM(COALESCE(biblioteca_baja,0)),0) AS biblioteca_baja,
                    COALESCE(SUM(COALESCE(otros,0)),0) AS otros
                FROM mobiliario_sede
                WHERE COALESCE(activo,1)=1
                GROUP BY codigo_sede
            ) m ON m.codigo_sede = s.codigo
            LEFT JOIN (
                SELECT sede_codigo, COALESCE(COUNT(*),0) AS aires_total
                FROM aires_mpd
                WHERE NULLIF(TRIM(marca),'') IS NOT NULL
                GROUP BY sede_codigo
            ) a ON a.sede_codigo = s.codigo
            LEFT JOIN (
                SELECT
                    codigo_sede,
                    COALESCE(SUM(
                        COALESCE(tubo_led_fria,0) +
                        COALESCE(tubo_led_calido,0) +
                        COALESCE(foco_comun,0) +
                        COALESCE(panel_led,0)
                    ),0) AS luminarias_total,
                    COALESCE(SUM(COALESCE(puestos_trabajo,0)),0) AS puestos_trabajo
                FROM luminarias_sede
                WHERE COALESCE(activo,1)=1
                GROUP BY codigo_sede
            ) l ON l.codigo_sede = s.codigo
            ORDER BY s.codigo
        """).fetchall()
        con.close()

        return render_template("inventario_dashboard.html", resumen=resumen)


