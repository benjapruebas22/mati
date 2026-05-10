from datetime import date
import sqlite3

from flask import render_template, request, redirect, url_for, flash


def register_auditorias(app, get_db):
    MOBILIARIO_ITEM_PAIRS = [
        ("aire_marca", "Aires acondicionados"),
        ("escritorio_prof", "Escritorios profesionales"),
        ("mesa_pc", "Mesas de PC"),
        ("silla_giratoria", "Sillas giratorias"),
        ("silla_fija", "Sillas fijas"),
        ("armario_alto", "Armarios altos"),
        ("biblioteca_baja", "Bibliotecas bajas"),
        ("otros", "Otros"),
    ]
    AIRES_ITEM_PAIRS = [
        ("total", "Equipos de aire"),
    ]
    LUMINARIAS_ITEM_PAIRS = [
        ("tubo_fria", "Tubo frío"),
        ("tubo_calido", "Tubo cálido"),
        ("foco", "Foco"),
        ("panel", "Panel"),
        ("puestos_trabajo", "Puesto de trabajo"),
        ("otros", "Otros"),
    ]
    OPERATIVA_RUBROS = [
        ("materiales", "Materiales"),
        ("mobiliario", "Mobiliario"),
        ("herramientas", "Herramientas"),
        ("vehiculos_estado", "Vehiculos - estado general"),
        ("vehiculos_documentacion", "Vehiculos - documentacion y seguridad"),
    ]
    OPERATIVA_ITEMS_BY_RUBRO = {
        "materiales": [
            ("coincide_registro_sgi", "Coincide con registro SGI", False),
            ("ubicacion_coincide", "Ubicacion real coincide", False),
            ("cantidad_coincide", "Cantidad real coincide", False),
            ("estado_fisico", "Estado fisico", False),
            ("identificacion_codigo", "Tiene identificacion/codigo", False),
            ("movimiento_registrado", "Movimiento registrado (alta/baja/traslado)", False),
            ("responsable_asignado", "Responsable asignado", False),
            ("evidencia_foto", "Evidencia foto cargada", False),
        ],
        "mobiliario": [
            ("coincide_registro_sgi", "Coincide con registro SGI", False),
            ("ubicacion_coincide", "Ubicacion real coincide", False),
            ("cantidad_coincide", "Cantidad real coincide", False),
            ("estado_fisico", "Estado fisico", False),
            ("identificacion_codigo", "Tiene identificacion/codigo", False),
            ("movimiento_registrado", "Movimiento registrado (alta/baja/traslado)", False),
            ("responsable_asignado", "Responsable asignado", False),
            ("evidencia_foto", "Evidencia foto cargada", False),
        ],
        "herramientas": [
            ("coincide_registro_sgi", "Coincide con registro SGI", False),
            ("ubicacion_coincide", "Ubicacion real coincide", False),
            ("cantidad_coincide", "Cantidad real coincide", False),
            ("estado_fisico", "Estado fisico", False),
            ("identificacion_codigo", "Tiene identificacion/codigo", False),
            ("movimiento_registrado", "Movimiento registrado (alta/baja/traslado)", False),
            ("responsable_asignado", "Responsable asignado", False),
            ("evidencia_foto", "Evidencia foto cargada", False),
        ],
        "vehiculos_estado": [
            ("chapa_carroceria", "Chapa / carroceria", False),
            ("tapizados_cabina", "Tapizados y cabina", False),
            ("luces_funcionando", "Luces funcionando", True),
            ("neumaticos_estado", "Neumaticos (estado/presion)", True),
            ("nivel_aceite", "Nivel de aceite", False),
            ("nivel_refrigerante_agua", "Nivel de agua/refrigerante", False),
            ("frenos_direccion", "Frenos y direccion", True),
            ("limpieza_orden", "Limpieza y orden general", False),
            ("tablero_sin_alertas_criticas", "Tablero sin alertas criticas", True),
        ],
        "vehiculos_documentacion": [
            ("cedula_vehiculo", "Cedula del vehiculo", True),
            ("seguro_vigente", "Seguro vigente", True),
            ("rto_vtv_vigente", "RTO/VTV vigente (si aplica)", True),
            ("licencia_conductor", "Licencia habilitante del conductor", True),
            ("matafuego_vigente", "Matafuego vigente y accesible", True),
            ("balizas", "Balizas reglamentarias", True),
            ("chaleco_reflectivo", "Chaleco reflectivo", False),
            ("botiquin", "Botiquin", False),
            ("rueda_auxilio", "Rueda de auxilio", True),
            ("cricket_llave_rueda", "Cricket y llave de rueda", True),
        ],
    }

    def ensure_auditoria_operativa_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_operativa(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                local_codigo TEXT,
                rubro TEXT NOT NULL,
                activo_codigo TEXT,
                auditor_nombre TEXT,
                responsable_area TEXT,
                observaciones_generales TEXT,
                estado_general TEXT NOT NULL DEFAULT 'verde',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_operativa_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                item_codigo TEXT NOT NULL,
                item_descripcion TEXT NOT NULL,
                resultado INTEGER NOT NULL,
                hallazgo TEXT,
                severidad TEXT,
                accion_correctiva TEXT,
                responsable_accion TEXT,
                fecha_compromiso TEXT,
                fecha_cierre TEXT,
                estado_accion TEXT,
                evidencia_url TEXT,
                bloquea_uso INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_operativa_fecha_sede_rubro
            ON auditoria_operativa(fecha, sede_codigo, rubro)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_operativa_items_auditoria
            ON auditoria_operativa_items(auditoria_id)
        """)

    def ensure_auditoria_herramientas_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_herramientas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                deposito TEXT,
                responsable TEXT,
                observaciones TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_herramientas_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                presente INTEGER DEFAULT 0,
                cantidad REAL
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_herramientas_fecha_sede_dep
            ON auditoria_herramientas(fecha, sede_codigo, deposito)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_herramientas_items_auditoria
            ON auditoria_herramientas_items(auditoria_id)
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_herramientas_catalogo(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                activo INTEGER DEFAULT 1,
                orden INTEGER DEFAULT 0
            )
        """)

    def ensure_auditoria_mobiliario_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_mobiliario(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                deposito TEXT,
                responsable TEXT,
                observaciones TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_mobiliario_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                cantidad REAL
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_mobiliario_fecha_sede_dep
            ON auditoria_mobiliario(fecha, sede_codigo, deposito)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_mobiliario_items_auditoria
            ON auditoria_mobiliario_items(auditoria_id)
        """)

    def ensure_auditoria_aires_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_aires(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                deposito TEXT,
                responsable TEXT,
                observaciones TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_aires_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                cantidad REAL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_aires_equipos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                ambiente TEXT,
                marca TEXT,
                gas TEXT,
                frigorias INTEGER,
                estado TEXT,
                fecha_ultima_limpieza TEXT,
                fecha_ultimo_service TEXT,
                frecuencia_meses INTEGER,
                observaciones TEXT
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_aires_fecha_sede_dep
            ON auditoria_aires(fecha, sede_codigo, deposito)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_aires_items_auditoria
            ON auditoria_aires_items(auditoria_id)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_aires_equipos_auditoria
            ON auditoria_aires_equipos(auditoria_id)
        """)

    def ensure_auditoria_luminarias_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_luminarias(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                deposito TEXT,
                responsable TEXT,
                observaciones TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_luminarias_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auditoria_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                cantidad REAL
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_luminarias_fecha_sede_dep
            ON auditoria_luminarias(fecha, sede_codigo, deposito)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_auditoria_luminarias_items_auditoria
            ON auditoria_luminarias_items(auditoria_id)
        """)

    @app.route("/auditoria/herramientas", methods=["GET", "POST"], endpoint="auditoria_herramientas")
    def auditoria_herramientas():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_herramientas_tables(con)
        cur = con.cursor()

        today = date.today().isoformat()

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            WHERE codigo IN ('S08', 'S12')
            ORDER BY codigo
        """).fetchall()

        depositos = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            WHERE (codigo_sede = 'S08' AND codigo_local = 'D08')
               OR (codigo_sede = 'S12' AND codigo_local = 'D02')
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        cur.execute("SELECT COUNT(*) AS c FROM auditoria_herramientas_catalogo")
        if (cur.fetchone()["c"] or 0) == 0:
            base_items = [
                ("Amoladora", 1),
                ("Taladro", 1),
                ("Atornilladora Eléctrica", 1),
                ("Pinza Amperometrica", 1),
                ("Caja herramienta KANUP", 1),
                ("Caja de Herramienta Gandic", 1),
                ("Atornilladora Inalambrica Garden", 1),
                ("LLave Inglesa 24", 1),
                ("LLave Inglesa 23", 1),
                ("LLave Inglesa 22", 1),
                ("LLave Inglesa 19", 1),
                ("LLave Inglesa 17", 1),
                ("LLave Inglesa 10", 1),
                ("Caja de Herramienta Makita", 1),
                ("Lima sin mango chica", 1),
                ("Lima sin mango mediana", 1),
                ("Cuchara de albañil", 1),
                ("Llana plana", 1),
                ("Llana plana", 1),
                ("Kit de destornilladores mezclado", 1),
                ("Tarraja", 1),
                ("Disco de amoladora", 1),
                ("Pistola silicona", 1),
                ("Lima con mango", 1),
                ("Lima con mango", 1),
                ("Lima con mango", 1),
                ("Kit de destornilladores mezclados", 1),
                ("Kit de destornillador Bremen", 1),
                ("Pico de loro", 1),
                ("Pinza mango naranja", 1),
                ("Pinza mango rojo", 1),
                ("Pinza mango amarillo", 1),
                ("Tijera pa chapa", 1),
                ("Remachadora", 1),
                ("Tenaza", 1),
                ("Herramienta fabricada", 1),
                ("Stilson", 1),
                ("Francesa grande", 1),
                ("Martillo mango negro", 0),
                ("Martillo chico", 1),
                ("Martillo mediano", 1),
                ("Martillo grande", 1),
                ("Maquina de corta pasto", 1),
                ("Rastrilo", 1),
                ("Bolso", 1),
                ("Pico", 1),
                ("Hidrolavadora", 1),
                ("Lustraspiradora", 1),
                ("Aspiradora industrial", 1),
                ("Cajon de herrajes", 1),
                ("Ventilador plasticos etc", 0),
                ("Cajon de pegamentos siliconas etc", 1),
                ("Compresor", 1),
                ("Bidon de nafta 4 lt", 1),
                ("Bidon de aceite", 1),
                ("Productos de desinfeccion", 1),
                ("Caja de herramienta negra", 1),
                ("Caja de herramienta azul", 1),
                ("Caja de herramienta chica negra", 1),
                ("Fumigadora", 1),
                ("Conos", 1),
                ("Cintas metrica", 1),
            ]
            cur.executemany("""
                INSERT INTO auditoria_herramientas_catalogo (nombre, activo, orden)
                VALUES (?,?,?)
            """, [(n, a, i + 1) for i, (n, a) in enumerate(base_items)])
            con.commit()

        catalogo = con.execute("""
            SELECT id, nombre, activo, orden
            FROM auditoria_herramientas_catalogo
            ORDER BY orden, nombre
        """).fetchall()

        items = [r["nombre"] for r in catalogo if (r["activo"] or 0) == 1]

        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip()
            deposito = (request.form.get("deposito") or "").strip().upper() or None
            fecha = request.form.get("fecha") or today
            responsable = (request.form.get("responsable") or "").strip() or None
            observaciones = (request.form.get("observaciones") or "").strip() or None

            if not sede_codigo or not deposito:
                flash("Elegi sede y deposito.", "warning")
                return redirect(url_for("auditoria_herramientas"))

            cur.execute("""
                INSERT INTO auditoria_herramientas (fecha, sede_codigo, deposito, responsable, observaciones)
                VALUES (?,?,?,?,?)
            """, (fecha, sede_codigo, deposito, responsable, observaciones))
            auditoria_id = cur.lastrowid

            for idx, label in enumerate(items):
                pres = 1 if request.form.get(f"pres_{idx}") else 0
                qty_raw = (request.form.get(f"qty_{idx}") or "").strip()
                if qty_raw == "" and pres == 0:
                    continue
                try:
                    qty = float(qty_raw) if qty_raw != "" else None
                except ValueError:
                    qty = None
                cur.execute("""
                    INSERT INTO auditoria_herramientas_items (auditoria_id, item, presente, cantidad)
                    VALUES (?,?,?,?)
                """, (auditoria_id, label, pres, qty))

            otro_item = (request.form.get("otro_item") or "").strip()
            otro_qty_raw = (request.form.get("otro_qty") or "").strip()
            if otro_item:
                try:
                    otro_qty = float(otro_qty_raw) if otro_qty_raw != "" else None
                except ValueError:
                    otro_qty = None
                cur.execute("""
                    INSERT INTO auditoria_herramientas_items (auditoria_id, item, presente, cantidad)
                    VALUES (?,?,?,?)
                """, (auditoria_id, otro_item, 1, otro_qty))

            con.commit()
            flash("Auditoria de herramientas guardada.", "success")
            return redirect(url_for("auditoria_herramientas"))

        auditorias = con.execute("""
            SELECT *
            FROM auditoria_herramientas
            ORDER BY fecha DESC, id DESC
            LIMIT 50
        """).fetchall()

        con.close()
        return render_template(
            "auditoria_herramientas.html",
            sedes=sedes,
            depositos=depositos,
            items=items,
            catalogo=catalogo,
            today=today,
            auditorias=auditorias
        )

    @app.route("/auditoria/herramientas/catalogo/agregar", methods=["POST"],
               endpoint="auditoria_herramientas_catalogo_agregar")
    def auditoria_herramientas_catalogo_agregar():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_herramientas_tables(con)

        nombre = (request.form.get("nombre") or "").strip()
        activo = 1 if request.form.get("activo") else 0
        orden_raw = (request.form.get("orden") or "").strip()
        try:
            orden = int(orden_raw) if orden_raw != "" else 0
        except ValueError:
            orden = 0

        if nombre:
            con.execute("""
                INSERT INTO auditoria_herramientas_catalogo (nombre, activo, orden)
                VALUES (?,?,?)
            """, (nombre, activo, orden))
            con.commit()

        con.close()
        return redirect(url_for("auditoria_herramientas"))

    @app.route("/auditoria/herramientas/catalogo/<int:cid>/editar", methods=["POST"],
               endpoint="auditoria_herramientas_catalogo_editar")
    def auditoria_herramientas_catalogo_editar(cid):
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_herramientas_tables(con)

        nombre = (request.form.get("nombre") or "").strip()
        activo = 1 if request.form.get("activo") else 0
        orden_raw = (request.form.get("orden") or "").strip()
        try:
            orden = int(orden_raw) if orden_raw != "" else 0
        except ValueError:
            orden = 0

        if nombre:
            con.execute("""
                UPDATE auditoria_herramientas_catalogo
                SET nombre = ?, activo = ?, orden = ?
                WHERE id = ?
            """, (nombre, activo, orden, cid))
            con.commit()

        con.close()
        return redirect(url_for("auditoria_herramientas"))

    @app.route("/auditoria/herramientas/catalogo/<int:cid>/borrar", methods=["POST"],
               endpoint="auditoria_herramientas_catalogo_borrar")
    def auditoria_herramientas_catalogo_borrar(cid):
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_herramientas_tables(con)
        con.execute("DELETE FROM auditoria_herramientas_catalogo WHERE id = ?", (cid,))
        con.commit()
        con.close()
        return redirect(url_for("auditoria_herramientas"))

    @app.route("/auditoria/mobiliario", methods=["GET", "POST"], endpoint="auditoria_mobiliario")
    def auditoria_mobiliario():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_mobiliario_tables(con)
        cur = con.cursor()

        today = date.today().isoformat()

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        depositos = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        items = MOBILIARIO_ITEM_PAIRS
        item_labels = {k: lbl for k, lbl in items}
        item_by_label = {lbl: k for k, lbl in items}

        edit_id_raw = (request.args.get("edit") or "").strip()
        edit_id = None
        if edit_id_raw.isdigit():
            edit_id = int(edit_id_raw)

        edit_row = None
        edit_items = {}
        if edit_id:
            edit_row = con.execute("""
                SELECT *
                FROM auditoria_mobiliario
                WHERE id = ?
            """, (edit_id,)).fetchone()
            if edit_row:
                item_rows = con.execute("""
                    SELECT item, cantidad
                    FROM auditoria_mobiliario_items
                    WHERE auditoria_id = ?
                """, (edit_id,)).fetchall()
                for r in item_rows:
                    item_key = item_by_label.get((r["item"] or "").strip())
                    if item_key:
                        edit_items[item_key] = r["cantidad"]
                    else:
                        edit_items["otro_item"] = (r["item"] or "").strip()
                        edit_items["otro_qty"] = r["cantidad"]

        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip()
            deposito = (request.form.get("deposito") or "").strip().upper() or None
            fecha = request.form.get("fecha") or today
            responsable = (request.form.get("responsable") or "").strip() or None
            observaciones = (request.form.get("observaciones") or "").strip() or None
            auditoria_id_raw = (request.form.get("auditoria_id") or "").strip()
            auditoria_id = int(auditoria_id_raw) if auditoria_id_raw.isdigit() else None

            if not sede_codigo or not deposito:
                flash("Elegi sede y deposito.", "warning")
                if auditoria_id:
                    return redirect(url_for("auditoria_mobiliario", edit=auditoria_id))
                return redirect(url_for("auditoria_mobiliario"))

            if auditoria_id:
                cur.execute("""
                    UPDATE auditoria_mobiliario
                    SET fecha = ?, sede_codigo = ?, deposito = ?, responsable = ?, observaciones = ?
                    WHERE id = ?
                """, (fecha, sede_codigo, deposito, responsable, observaciones, auditoria_id))
                cur.execute("DELETE FROM auditoria_mobiliario_items WHERE auditoria_id = ?", (auditoria_id,))
            else:
                cur.execute("""
                    INSERT INTO auditoria_mobiliario (fecha, sede_codigo, deposito, responsable, observaciones)
                    VALUES (?,?,?,?,?)
                """, (fecha, sede_codigo, deposito, responsable, observaciones))
                auditoria_id = cur.lastrowid

            for key, label in items:
                qty_raw = (request.form.get(f"qty_{key}") or "").strip()
                if qty_raw == "":
                    continue
                try:
                    qty = float(qty_raw)
                except ValueError:
                    qty = None
                cur.execute("""
                    INSERT INTO auditoria_mobiliario_items (auditoria_id, item, cantidad)
                    VALUES (?,?,?)
                """, (auditoria_id, label, qty))

            otro_item = (request.form.get("otro_item") or "").strip()
            otro_qty_raw = (request.form.get("otro_qty") or "").strip()
            if otro_item:
                try:
                    otro_qty = float(otro_qty_raw) if otro_qty_raw != "" else None
                except ValueError:
                    otro_qty = None
                cur.execute("""
                    INSERT INTO auditoria_mobiliario_items (auditoria_id, item, cantidad)
                    VALUES (?,?,?)
                """, (auditoria_id, otro_item, otro_qty))

            con.commit()
            flash("Auditoria de mobiliario actualizada." if auditoria_id_raw else "Auditoria de mobiliario guardada.", "success")
            return redirect(url_for("auditoria_mobiliario"))

        auditorias = con.execute("""
            SELECT *
            FROM auditoria_mobiliario
            ORDER BY fecha DESC, id DESC
            LIMIT 50
        """).fetchall()

        con.close()
        return render_template(
            "auditoria_mobiliario.html",
            sedes=sedes,
            depositos=depositos,
            items=items,
            item_labels=item_labels,
            today=today,
            auditorias=auditorias,
            edit_row=edit_row,
            edit_items=edit_items,
            allow_otros=True,
        )

    @app.route("/auditoria/aires", methods=["GET", "POST"], endpoint="auditoria_aires")
    def auditoria_aires():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_aires_tables(con)
        cur = con.cursor()

        today = date.today().isoformat()
        items = AIRES_ITEM_PAIRS
        item_labels = [label for _, label in items]

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()
        depositos = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        edit_row = None
        edit_items = {}
        edit_equipos = []
        auditoria_id_raw = (request.args.get("edit") or "").strip()
        auditoria_id = int(auditoria_id_raw) if auditoria_id_raw.isdigit() else None
        if auditoria_id:
            edit_row = con.execute("SELECT * FROM auditoria_aires WHERE id = ?", (auditoria_id,)).fetchone()
            if edit_row:
                rows = con.execute("SELECT item, cantidad FROM auditoria_aires_items WHERE auditoria_id = ?", (auditoria_id,)).fetchall()
                for r in rows:
                    edit_items[(r["item"] or "").strip()] = r["cantidad"]
                edit_equipos = con.execute("""
                    SELECT *
                    FROM auditoria_aires_equipos
                    WHERE auditoria_id = ?
                    ORDER BY id
                """, (auditoria_id,)).fetchall()

        if request.method == "POST":
            fecha = (request.form.get("fecha") or today).strip() or today
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            deposito = (request.form.get("deposito") or "").strip().upper() or None
            responsable = (request.form.get("responsable") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()

            auditoria_id_raw = (request.form.get("auditoria_id") or "").strip()
            auditoria_id = int(auditoria_id_raw) if auditoria_id_raw.isdigit() else None

            if not sede_codigo:
                flash("Completa sede para guardar el relevamiento.", "warning")
                return redirect(url_for("auditoria_aires", edit=auditoria_id) if auditoria_id else url_for("auditoria_aires"))

            if auditoria_id:
                cur.execute("""
                    UPDATE auditoria_aires
                    SET fecha = ?, sede_codigo = ?, deposito = ?, responsable = ?, observaciones = ?
                    WHERE id = ?
                """, (fecha, sede_codigo, deposito, responsable, observaciones, auditoria_id))
                cur.execute("DELETE FROM auditoria_aires_items WHERE auditoria_id = ?", (auditoria_id,))
                cur.execute("DELETE FROM auditoria_aires_equipos WHERE auditoria_id = ?", (auditoria_id,))
            else:
                cur.execute("""
                    INSERT INTO auditoria_aires (fecha, sede_codigo, deposito, responsable, observaciones)
                    VALUES (?,?,?,?,?)
                """, (fecha, sede_codigo, deposito, responsable, observaciones))
                auditoria_id = cur.lastrowid

            # Equipos relevados (detalle)
            ambientes = request.form.getlist("eq_ambiente")
            marcas = request.form.getlist("eq_marca")
            gases = request.form.getlist("eq_gas")
            frigorias_list = request.form.getlist("eq_frigorias")
            estados = request.form.getlist("eq_estado")
            limpiezas = request.form.getlist("eq_fecha_ultima_limpieza")
            services = request.form.getlist("eq_fecha_ultimo_service")
            frecs = request.form.getlist("eq_frecuencia_meses")
            obs_list = request.form.getlist("eq_observaciones")

            total_rows = max(
                len(ambientes), len(marcas), len(gases), len(frigorias_list),
                len(estados), len(limpiezas), len(services), len(frecs), len(obs_list),
            )
            equipos_insertados = 0
            for i in range(total_rows):
                ambiente = (ambientes[i] if i < len(ambientes) else "").strip() or None
                marca = (marcas[i] if i < len(marcas) else "").strip() or None
                gas = (gases[i] if i < len(gases) else "").strip() or None
                estado = (estados[i] if i < len(estados) else "").strip() or None
                fecha_ultima_limpieza = (limpiezas[i] if i < len(limpiezas) else "").strip() or None
                fecha_ultimo_service = (services[i] if i < len(services) else "").strip() or None
                observaciones_eq = (obs_list[i] if i < len(obs_list) else "").strip() or None

                frig_raw = (frigorias_list[i] if i < len(frigorias_list) else "").strip()
                frigorias = None
                if frig_raw != "":
                    try:
                        frigorias = int(float(frig_raw))
                    except Exception:
                        frigorias = None

                frec_raw = (frecs[i] if i < len(frecs) else "").strip()
                frecuencia_meses = None
                if frec_raw != "":
                    try:
                        frecuencia_meses = int(float(frec_raw))
                    except Exception:
                        frecuencia_meses = None

                if not any([
                    ambiente, marca, gas, frig_raw, estado,
                    fecha_ultima_limpieza, fecha_ultimo_service, frec_raw, observaciones_eq,
                ]):
                    continue

                cur.execute("""
                    INSERT INTO auditoria_aires_equipos (
                        auditoria_id, ambiente, marca, gas, frigorias, estado,
                        fecha_ultima_limpieza, fecha_ultimo_service, frecuencia_meses, observaciones
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    auditoria_id, ambiente, marca, gas, frigorias, estado,
                    fecha_ultima_limpieza, fecha_ultimo_service, frecuencia_meses, observaciones_eq
                ))
                equipos_insertados += 1

            # Back-compat: guardamos total en la tabla de items (1 fila)
            if equipos_insertados > 0:
                try:
                    label_total = items[0][1]
                except Exception:
                    label_total = "Equipos de aire"
                cur.execute("""
                    INSERT INTO auditoria_aires_items (auditoria_id, item, cantidad)
                    VALUES (?,?,?)
                """, (auditoria_id, label_total, float(equipos_insertados)))

            con.commit()
            flash("Relevamiento de aires guardado." if not auditoria_id_raw else "Relevamiento de aires actualizado.", "success")
            return redirect(url_for("auditoria_aires"))

        auditorias = con.execute("""
            SELECT *
            FROM auditoria_aires
            ORDER BY fecha DESC, id DESC
            LIMIT 50
        """).fetchall()
        con.close()
        return render_template(
            "auditoria_aires.html",
            sedes=sedes,
            depositos=depositos,
            items=items,
            item_labels=item_labels,
            today=today,
            auditorias=auditorias,
            edit_row=edit_row,
            edit_items=edit_items,
            edit_equipos=edit_equipos,
            allow_otros=False,
        )

    @app.route("/auditoria/luminarias", methods=["GET", "POST"], endpoint="auditoria_luminarias")
    def auditoria_luminarias():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_luminarias_tables(con)
        cur = con.cursor()

        today = date.today().isoformat()
        items = LUMINARIAS_ITEM_PAIRS
        item_labels = [label for _, label in items]

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()
        depositos = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        edit_row = None
        edit_items = {}
        auditoria_id_raw = (request.args.get("edit") or "").strip()
        auditoria_id = int(auditoria_id_raw) if auditoria_id_raw.isdigit() else None
        if auditoria_id:
            edit_row = con.execute("SELECT * FROM auditoria_luminarias WHERE id = ?", (auditoria_id,)).fetchone()
            if edit_row:
                rows = con.execute("SELECT item, cantidad FROM auditoria_luminarias_items WHERE auditoria_id = ?", (auditoria_id,)).fetchall()
                for r in rows:
                    edit_items[(r["item"] or "").strip()] = r["cantidad"]

        if request.method == "POST":
            fecha = (request.form.get("fecha") or today).strip() or today
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            deposito = (request.form.get("deposito") or "").strip().upper()
            responsable = (request.form.get("responsable") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()

            auditoria_id_raw = (request.form.get("auditoria_id") or "").strip()
            auditoria_id = int(auditoria_id_raw) if auditoria_id_raw.isdigit() else None

            if not sede_codigo or not deposito:
                flash("Completa sede y deposito para guardar el relevamiento.", "warning")
                return redirect(url_for("auditoria_luminarias", edit=auditoria_id) if auditoria_id else url_for("auditoria_luminarias"))

            if auditoria_id:
                cur.execute("""
                    UPDATE auditoria_luminarias
                    SET fecha = ?, sede_codigo = ?, deposito = ?, responsable = ?, observaciones = ?
                    WHERE id = ?
                """, (fecha, sede_codigo, deposito, responsable, observaciones, auditoria_id))
                cur.execute("DELETE FROM auditoria_luminarias_items WHERE auditoria_id = ?", (auditoria_id,))
            else:
                cur.execute("""
                    INSERT INTO auditoria_luminarias (fecha, sede_codigo, deposito, responsable, observaciones)
                    VALUES (?,?,?,?,?)
                """, (fecha, sede_codigo, deposito, responsable, observaciones))
                auditoria_id = cur.lastrowid

            for key, label in items:
                qty_raw = (request.form.get(f"qty_{key}") or "").strip()
                if qty_raw == "":
                    continue
                try:
                    qty = float(qty_raw)
                except Exception:
                    qty = 0
                cur.execute("""
                    INSERT INTO auditoria_luminarias_items (auditoria_id, item, cantidad)
                    VALUES (?,?,?)
                """, (auditoria_id, label, qty))

            con.commit()
            flash("Relevamiento de luminarias guardado." if not auditoria_id_raw else "Relevamiento de luminarias actualizado.", "success")
            return redirect(url_for("auditoria_luminarias"))

        auditorias = con.execute("""
            SELECT *
            FROM auditoria_luminarias
            ORDER BY fecha DESC, id DESC
            LIMIT 50
        """).fetchall()
        con.close()
        return render_template(
            "auditoria_luminarias.html",
            sedes=sedes,
            depositos=depositos,
            items=items,
            item_labels=item_labels,
            today=today,
            auditorias=auditorias,
            edit_row=edit_row,
            edit_items=edit_items,
            allow_otros=False,
        )

    @app.route("/auditoria/mobiliario/<int:aid>/borrar", methods=["POST"], endpoint="auditoria_mobiliario_borrar")
    def auditoria_mobiliario_borrar(aid):
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_mobiliario_tables(con)
        con.execute("DELETE FROM auditoria_mobiliario_items WHERE auditoria_id = ?", (aid,))
        con.execute("DELETE FROM auditoria_mobiliario WHERE id = ?", (aid,))
        con.commit()
        con.close()
        flash("Relevamiento eliminado.", "info")
        return redirect(url_for("auditoria_mobiliario"))

    @app.route("/auditoria/aires/<int:aid>/borrar", methods=["POST"], endpoint="auditoria_aires_borrar")
    def auditoria_aires_borrar(aid):
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_aires_tables(con)
        con.execute("DELETE FROM auditoria_aires_items WHERE auditoria_id = ?", (aid,))
        con.execute("DELETE FROM auditoria_aires_equipos WHERE auditoria_id = ?", (aid,))
        con.execute("DELETE FROM auditoria_aires WHERE id = ?", (aid,))
        con.commit()
        con.close()
        flash("Relevamiento eliminado.", "info")
        return redirect(url_for("auditoria_aires"))

    @app.route("/auditoria/luminarias/<int:aid>/borrar", methods=["POST"], endpoint="auditoria_luminarias_borrar")
    def auditoria_luminarias_borrar(aid):
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_luminarias_tables(con)
        con.execute("DELETE FROM auditoria_luminarias_items WHERE auditoria_id = ?", (aid,))
        con.execute("DELETE FROM auditoria_luminarias WHERE id = ?", (aid,))
        con.commit()
        con.close()
        flash("Relevamiento eliminado.", "info")
        return redirect(url_for("auditoria_luminarias"))

    def _comparativa_render(tipo):
        con = get_db()
        con.row_factory = sqlite3.Row

        if tipo == "aires":
            ensure_auditoria_aires_tables(con)
            item_pairs = AIRES_ITEM_PAIRS
            auditoria_tabla = "auditoria_aires"
            auditoria_items = "auditoria_aires_items"
            oficiales_sql = """
                SELECT
                    sede_codigo AS sede_codigo,
                    CASE
                      WHEN UPPER(COALESCE(TRIM(ambiente),'')) GLOB 'D[0-9][0-9]*'
                        THEN UPPER(SUBSTR(TRIM(ambiente), 1, 3))
                      ELSE 'GENERAL'
                    END AS deposito_codigo,
                    COUNT(*) AS total
                FROM aires_mpd
                GROUP BY sede_codigo, deposito_codigo
            """
            tipo_label = "Aires"
        elif tipo == "luminarias":
            ensure_auditoria_luminarias_tables(con)
            item_pairs = LUMINARIAS_ITEM_PAIRS
            auditoria_tabla = "auditoria_luminarias"
            auditoria_items = "auditoria_luminarias_items"
            oficiales_sql = """
                SELECT
                    codigo_sede AS sede_codigo,
                    codigo_local AS deposito_codigo,
                    COALESCE(SUM(COALESCE(tubo_led_fria, 0)), 0) AS tubo_fria,
                    COALESCE(SUM(COALESCE(tubo_led_calido, 0)), 0) AS tubo_calido,
                    COALESCE(SUM(COALESCE(foco_comun, 0)), 0) AS foco,
                    COALESCE(SUM(COALESCE(panel_led, 0)), 0) AS panel,
                    COALESCE(SUM(COALESCE(puestos_trabajo, 0)), 0) AS puestos_trabajo,
                    0 AS otros
                FROM luminarias_sede
                GROUP BY codigo_sede, codigo_local
            """
            tipo_label = "Luminarias"
        else:
            ensure_auditoria_mobiliario_tables(con)
            item_pairs = MOBILIARIO_ITEM_PAIRS
            auditoria_tabla = "auditoria_mobiliario"
            auditoria_items = "auditoria_mobiliario_items"
            oficiales_sql = """
                SELECT
                    codigo_sede AS sede_codigo,
                    codigo_local AS deposito_codigo,
                    COALESCE(SUM(COALESCE(aire_marca, 0)), 0) AS aire_marca,
                    COALESCE(SUM(COALESCE(escritorio_prof, 0)), 0) AS escritorio_prof,
                    COALESCE(SUM(COALESCE(mesa_pc, 0)), 0) AS mesa_pc,
                    COALESCE(SUM(COALESCE(silla_giratoria, 0)), 0) AS silla_giratoria,
                    COALESCE(SUM(COALESCE(silla_fija, 0)), 0) AS silla_fija,
                    COALESCE(SUM(COALESCE(armario_alto, 0)), 0) AS armario_alto,
                    COALESCE(SUM(COALESCE(biblioteca_baja, 0)), 0) AS biblioteca_baja,
                    COALESCE(SUM(COALESCE(otros, 0)), 0) AS otros
                FROM mobiliario_sede
                GROUP BY codigo_sede, codigo_local
            """
            tipo_label = "Mobiliario"

        keys = [k for k, _ in item_pairs]
        label_to_key = {label: key for key, label in item_pairs}

        q_sede = (request.args.get("sede") or "").strip().upper()
        q_deposito = (request.args.get("deposito") or "").strip().upper()
        q_fecha_desde = (request.args.get("desde") or "").strip()
        q_fecha_hasta = (request.args.get("hasta") or "").strip()

        where = []
        params = []
        if q_sede:
            where.append("a.sede_codigo = ?")
            params.append(q_sede)
        if q_fecha_desde:
            where.append("date(a.fecha) >= date(?)")
            params.append(q_fecha_desde)
        if q_fecha_hasta:
            where.append("date(a.fecha) <= date(?)")
            params.append(q_fecha_hasta)

        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        auditorias = con.execute(f"""
            SELECT a.id, a.fecha, a.sede_codigo, a.deposito, a.responsable, a.observaciones
            FROM {auditoria_tabla} a
            {sql_where}
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 120
        """, tuple(params)).fetchall()

        audit_ids = [r["id"] for r in auditorias]
        items_by_auditoria = {}
        if audit_ids:
            marks = ",".join("?" for _ in audit_ids)
            item_rows = con.execute(f"""
                SELECT auditoria_id, item, cantidad
                FROM {auditoria_items}
                WHERE auditoria_id IN ({marks})
            """, tuple(audit_ids)).fetchall()
            for r in item_rows:
                aid = r["auditoria_id"]
                key = label_to_key.get((r["item"] or "").strip())
                if not key:
                    continue
                items_by_auditoria.setdefault(aid, {})[key] = float(r["cantidad"] or 0)

        depositos_rows = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
        """).fetchall()
        desc_to_codigo = {}
        for d in depositos_rows:
            sede = (d["codigo_sede"] or "").upper()
            desc = (d["descripcion"] or "").strip().upper()
            cod = (d["codigo_local"] or "").upper()
            if sede and desc and cod:
                desc_to_codigo[(sede, desc)] = cod

        oficiales_map = {}
        try:
            oficiales_rows = con.execute(oficiales_sql).fetchall()
            for r in oficiales_rows:
                sede = (r["sede_codigo"] or "").upper()
                depo = (r["deposito_codigo"] or "").upper()
                if not sede or not depo:
                    continue
                oficiales_map[(sede, depo)] = {k: float(r[k] or 0) for k in keys}
        except Exception:
            oficiales_map = {}

        filas = []
        for a in auditorias:
            sede = (a["sede_codigo"] or "").upper()
            depo_raw = (a["deposito"] or "").strip().upper()
            depo_code = depo_raw
            if not depo_code.startswith("D"):
                depo_code = desc_to_codigo.get((sede, depo_raw), depo_raw)
            if q_deposito and depo_code != q_deposito:
                continue

            oficial = oficiales_map.get((sede, depo_code))
            if oficial is None and tipo == "aires":
                oficial = oficiales_map.get((sede, "GENERAL"))
            if oficial is None:
                oficial = {k: 0.0 for k in keys}
            real = items_by_auditoria.get(a["id"], {})
            detalle = []
            for key, label in item_pairs:
                r = real.get(key)
                o = float(oficial.get(key, 0))
                delta = None if r is None else float(r) - o
                detalle.append({
                    "key": key,
                    "label": label,
                    "oficial": o,
                    "real": r,
                    "delta": delta,
                })
            filas.append({
                "id": a["id"],
                "fecha": a["fecha"],
                "sede_codigo": sede,
                "deposito": depo_code or depo_raw or "-",
                "responsable": a["responsable"] or "-",
                "observaciones": a["observaciones"] or "-",
                "detalle": detalle,
            })

        sedes = con.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()
        depositos = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        con.close()
        return render_template(
            "auditoria_comparativa.html",
            filas=filas,
            sedes=sedes,
            depositos=depositos,
            q_sede=q_sede,
            q_deposito=q_deposito,
            q_fecha_desde=q_fecha_desde,
            q_fecha_hasta=q_fecha_hasta,
            tipo_label=tipo_label,
        )

    @app.route("/auditoria/mobiliario/supervisor", methods=["GET"], endpoint="auditoria_mobiliario_supervisor")
    def auditoria_mobiliario_supervisor():
        return _comparativa_render("mobiliario")

    @app.route("/relevamientos/comparativa", methods=["GET"], endpoint="relevamientos_comparativa")
    def relevamientos_comparativa():
        tipo = (request.args.get("tipo") or "mobiliario").strip().lower()
        if tipo not in ("mobiliario", "aires", "luminarias"):
            tipo = "mobiliario"
        return _comparativa_render(tipo)

    @app.route("/auditoria/operativa", methods=["GET", "POST"], endpoint="auditoria_operativa")
    def auditoria_operativa():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_auditoria_operativa_tables(con)
        cur = con.cursor()

        today = date.today().isoformat()
        rubro_values = {k for k, _ in OPERATIVA_RUBROS}

        sedes = con.execute("""
            SELECT codigo, nombre, ciudad
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()
        locales = con.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()

        q_rubro = (request.args.get("rubro") or "").strip().lower()
        if q_rubro not in rubro_values:
            q_rubro = "materiales"

        if request.method == "POST":
            fecha = (request.form.get("fecha") or today).strip() or today
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            local_codigo = (request.form.get("local_codigo") or "").strip().upper() or None
            rubro = (request.form.get("rubro") or "").strip().lower()
            activo_codigo = (request.form.get("activo_codigo") or "").strip().upper() or None
            auditor_nombre = (request.form.get("auditor_nombre") or "").strip() or None
            responsable_area = (request.form.get("responsable_area") or "").strip() or None
            observaciones_generales = (request.form.get("observaciones_generales") or "").strip() or None

            if rubro not in rubro_values:
                rubro = q_rubro

            item_defs = OPERATIVA_ITEMS_BY_RUBRO.get(rubro, [])
            if not sede_codigo or not rubro or not item_defs:
                con.close()
                flash("Completa sede y rubro para guardar la auditoria.", "warning")
                return redirect(url_for("auditoria_operativa", rubro=rubro or q_rubro))

            missing_labels = []
            parsed_items = []
            resultados = []
            for item_codigo, item_descripcion, is_critical in item_defs:
                resultado_raw = (request.form.get(f"resultado__{item_codigo}") or "").strip()
                if resultado_raw not in {"0", "1", "2"}:
                    missing_labels.append(item_descripcion)
                    continue
                resultado = int(resultado_raw)
                hallazgo = (request.form.get(f"hallazgo__{item_codigo}") or "").strip() or None
                severidad = (request.form.get(f"severidad__{item_codigo}") or "").strip().lower() or None
                accion_correctiva = (request.form.get(f"accion__{item_codigo}") or "").strip() or None
                responsable_accion = (request.form.get(f"resp_accion__{item_codigo}") or "").strip() or None
                fecha_compromiso = (request.form.get(f"fecha_comp__{item_codigo}") or "").strip() or None
                fecha_cierre = (request.form.get(f"fecha_cierre__{item_codigo}") or "").strip() or None
                estado_accion = (request.form.get(f"estado_accion__{item_codigo}") or "").strip().lower() or None
                evidencia_url = (request.form.get(f"evidencia__{item_codigo}") or "").strip() or None
                bloquea_uso = 1 if (resultado == 0 and is_critical) else 0

                parsed_items.append((
                    item_codigo,
                    item_descripcion,
                    resultado,
                    hallazgo,
                    severidad,
                    accion_correctiva,
                    responsable_accion,
                    fecha_compromiso,
                    fecha_cierre,
                    estado_accion,
                    evidencia_url,
                    bloquea_uso,
                ))
                resultados.append(resultado)

            if missing_labels:
                con.close()
                flash("Completa resultado (OK/Obs/NC) en todos los items del checklist.", "warning")
                return redirect(url_for("auditoria_operativa", rubro=rubro))

            if any(r == 0 for r in resultados):
                estado_general = "rojo"
            elif any(r == 1 for r in resultados):
                estado_general = "amarillo"
            else:
                estado_general = "verde"

            cur.execute("""
                INSERT INTO auditoria_operativa (
                    fecha, sede_codigo, local_codigo, rubro, activo_codigo, auditor_nombre,
                    responsable_area, observaciones_generales, estado_general
                ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                fecha, sede_codigo, local_codigo, rubro, activo_codigo, auditor_nombre,
                responsable_area, observaciones_generales, estado_general
            ))
            auditoria_id = cur.lastrowid

            cur.executemany("""
                INSERT INTO auditoria_operativa_items (
                    auditoria_id, item_codigo, item_descripcion, resultado, hallazgo, severidad,
                    accion_correctiva, responsable_accion, fecha_compromiso, fecha_cierre,
                    estado_accion, evidencia_url, bloquea_uso
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                (
                    auditoria_id,
                    item_codigo,
                    item_descripcion,
                    resultado,
                    hallazgo,
                    severidad,
                    accion_correctiva,
                    responsable_accion,
                    fecha_compromiso,
                    fecha_cierre,
                    estado_accion,
                    evidencia_url,
                    bloquea_uso,
                )
                for (
                    item_codigo, item_descripcion, resultado, hallazgo, severidad, accion_correctiva,
                    responsable_accion, fecha_compromiso, fecha_cierre, estado_accion, evidencia_url,
                    bloquea_uso
                ) in parsed_items
            ])

            con.commit()
            con.close()
            flash("Auditoria operativa guardada.", "success")
            return redirect(url_for("auditoria_operativa", rubro=rubro))

        item_defs = OPERATIVA_ITEMS_BY_RUBRO.get(q_rubro, [])
        auditorias = con.execute("""
            SELECT
                a.id,
                a.fecha,
                a.sede_codigo,
                a.local_codigo,
                a.rubro,
                a.activo_codigo,
                a.auditor_nombre,
                a.estado_general,
                COALESCE(SUM(CASE WHEN i.resultado = 0 THEN 1 ELSE 0 END), 0) AS nc_count,
                COALESCE(SUM(CASE WHEN i.resultado = 1 THEN 1 ELSE 0 END), 0) AS obs_count,
                COALESCE(SUM(CASE WHEN i.bloquea_uso = 1 THEN 1 ELSE 0 END), 0) AS bloqueo_count
            FROM auditoria_operativa a
            LEFT JOIN auditoria_operativa_items i ON i.auditoria_id = a.id
            GROUP BY a.id
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 60
        """).fetchall()

        con.close()
        return render_template(
            "auditoria_operativa.html",
            today=today,
            sedes=sedes,
            locales=locales,
            rubros=OPERATIVA_RUBROS,
            q_rubro=q_rubro,
            item_defs=item_defs,
            auditorias=auditorias,
        )

