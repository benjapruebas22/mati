import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for


ROUTE_STOPS = {
    "Norte": ["San Salvador", "Tilcara", "Humahuaca", "Abra Pampa", "La Quiaca"],
    "Ramal": ["San Salvador", "Palpala", "San Pedro", "Libertador General San Martin"],
    "San Pedro/Ledesma": ["San Salvador", "San Pedro", "Libertador General San Martin"],
    "Perico/Monterrico": ["San Salvador", "Palpala", "Perico", "Monterrico"],
    "Otra": [],
}

STATUSES = ("Borrador", "Preparado", "En recorrido", "Finalizado", "Cerrado")
MATERIAL_TYPES = (
    "Electricidad",
    "Sanitarios",
    "Ferreteria",
    "Herramientas",
    "Seguridad",
    "Limpieza",
    "Documentacion",
    "Otro",
)
MATERIAL_STATUSES = ("Pendiente", "Preparado", "Entregado", "No utilizado")
ACTIVITY_TYPES = (
    "Relevamiento",
    "Mantenimiento",
    "Entrega de materiales",
    "Retiro de materiales",
    "Verificacion",
    "Gestion administrativa",
    "Otro",
)
ACTIVITY_STATUSES = ("Pendiente", "En curso", "Finalizada", "Cancelada")
ACTIVITY_PRIORITIES = ("Baja", "Media", "Alta")
DEFAULT_KIT = (
    ("Documentacion", "Documentacion del recorrido", 1, "juego"),
    ("Documentacion", "Llaves de acceso", 1, "juego"),
    ("Documentacion", "Combustible", 1, "control"),
    ("Documentacion", "Matafuegos", 1, "unidad"),
    ("Documentacion", "Balizas", 1, "juego"),
    ("Documentacion", "Botiquin", 1, "unidad"),
    ("Herramientas", "Escalera", 1, "unidad"),
    ("Herramientas", "Taladro", 1, "unidad"),
    ("Herramientas", "Amoladora", 1, "unidad"),
    ("Herramientas", "Atornillador", 1, "unidad"),
    ("Herramientas", "Tester", 1, "unidad"),
    ("Electricidad", "Tubos LED", 6, "unidades"),
    ("Electricidad", "Lamparas", 4, "unidades"),
    ("Electricidad", "Cable", 1, "rollo"),
    ("Electricidad", "Termicas", 1, "juego"),
    ("Plomeria", "Flexibles", 2, "unidades"),
    ("Plomeria", "Pegamento", 1, "unidad"),
    ("Plomeria", "Llaves para plomeria", 1, "juego"),
    ("Limpieza", "Insumos", 1, "juego"),
    ("Limpieza", "Bolsas", 1, "paquete"),
    ("Limpieza", "Escobillon", 1, "unidad"),
    ("Mobiliario", "Escritorios", 1, "unidad"),
    ("Mobiliario", "Sillas", 1, "unidad"),
    ("Mobiliario", "Estanterias", 1, "unidad"),
)


def register_recorridos_operativos(app: Flask) -> None:
    if getattr(app, "_recorridos_operativos_registered", False):
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "mpd.db")

    def connect() -> sqlite3.Connection:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def username() -> str:
        return (session.get("username") or "sistema").strip().lower()

    def require_login():
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return None

    def ensure_schema() -> None:
        con = connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS recorridos_operativos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_prevista TEXT NOT NULL,
                    ruta TEXT NOT NULL,
                    destino_sede TEXT,
                    vehiculo_patente TEXT,
                    equipo_operativo TEXT NOT NULL,
                    observacion TEXT,
                    estado TEXT NOT NULL DEFAULT 'Borrador',
                    started_at TEXT,
                    finished_at TEXT,
                    closed_at TEXT,
                    final_note TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recorrido_paradas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorrido_id INTEGER NOT NULL,
                    orden INTEGER NOT NULL,
                    sede_codigo TEXT,
                    nombre TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'Pendiente',
                    started_at TEXT,
                    finished_at TEXT,
                    notas TEXT,
                    FOREIGN KEY(recorrido_id) REFERENCES recorridos_operativos(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS recorridos_kit_base (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL DEFAULT 'Otros',
                    elemento TEXT NOT NULL UNIQUE,
                    cantidad_minima REAL NOT NULL DEFAULT 1,
                    unidad TEXT NOT NULL DEFAULT 'unidades',
                    activo INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS recorrido_kit_check (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorrido_id INTEGER NOT NULL,
                    kit_id INTEGER NOT NULL,
                    cantidad_preparada REAL NOT NULL DEFAULT 0,
                    verificado INTEGER NOT NULL DEFAULT 0,
                    observacion TEXT,
                    UNIQUE(recorrido_id, kit_id),
                    FOREIGN KEY(recorrido_id) REFERENCES recorridos_operativos(id) ON DELETE CASCADE,
                    FOREIGN KEY(kit_id) REFERENCES recorridos_kit_base(id)
                );
                CREATE TABLE IF NOT EXISTS recorrido_materiales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorrido_id INTEGER NOT NULL,
                    parada_id INTEGER,
                    sede_codigo TEXT,
                    elemento TEXT NOT NULL,
                    cantidad REAL NOT NULL DEFAULT 1,
                    tipo TEXT NOT NULL,
                    observacion TEXT,
                    estado TEXT NOT NULL DEFAULT 'Pendiente',
                    FOREIGN KEY(recorrido_id) REFERENCES recorridos_operativos(id) ON DELETE CASCADE,
                    FOREIGN KEY(parada_id) REFERENCES recorrido_paradas(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS recorrido_actividades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorrido_id INTEGER NOT NULL,
                    parada_id INTEGER,
                    sede_codigo TEXT,
                    tipo TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    prioridad TEXT NOT NULL DEFAULT 'Media',
                    tiempo_estimado_min INTEGER,
                    material_asociado TEXT,
                    estado TEXT NOT NULL DEFAULT 'Pendiente',
                    started_at TEXT,
                    finished_at TEXT,
                    observacion TEXT,
                    FOREIGN KEY(recorrido_id) REFERENCES recorridos_operativos(id) ON DELETE CASCADE,
                    FOREIGN KEY(parada_id) REFERENCES recorrido_paradas(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS recorrido_hitos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorrido_id INTEGER NOT NULL,
                    parada_id INTEGER,
                    tipo TEXT NOT NULL,
                    usuario TEXT NOT NULL,
                    fecha_hora TEXT NOT NULL,
                    nota TEXT,
                    FOREIGN KEY(recorrido_id) REFERENCES recorridos_operativos(id) ON DELETE CASCADE,
                    FOREIGN KEY(parada_id) REFERENCES recorrido_paradas(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recorridos_fecha ON recorridos_operativos(fecha_prevista, estado);
                CREATE INDEX IF NOT EXISTS idx_recorrido_paradas ON recorrido_paradas(recorrido_id, orden);
                CREATE INDEX IF NOT EXISTS idx_recorrido_materiales ON recorrido_materiales(recorrido_id, estado);
                CREATE INDEX IF NOT EXISTS idx_recorrido_actividades ON recorrido_actividades(recorrido_id, estado);
                CREATE INDEX IF NOT EXISTS idx_recorrido_hitos ON recorrido_hitos(recorrido_id, fecha_hora);
                """
            )
            kit_columns = {row["name"] for row in con.execute("PRAGMA table_info(recorridos_kit_base)").fetchall()}
            if "categoria" not in kit_columns:
                con.execute("ALTER TABLE recorridos_kit_base ADD COLUMN categoria TEXT NOT NULL DEFAULT 'Otros'")
            activity_columns = {row["name"] for row in con.execute("PRAGMA table_info(recorrido_actividades)").fetchall()}
            if "prioridad" not in activity_columns:
                con.execute("ALTER TABLE recorrido_actividades ADD COLUMN prioridad TEXT NOT NULL DEFAULT 'Media'")
            if "tiempo_estimado_min" not in activity_columns:
                con.execute("ALTER TABLE recorrido_actividades ADD COLUMN tiempo_estimado_min INTEGER")
            if "material_asociado" not in activity_columns:
                con.execute("ALTER TABLE recorrido_actividades ADD COLUMN material_asociado TEXT")
            for category, element, minimum, unit in DEFAULT_KIT:
                con.execute(
                    "INSERT OR IGNORE INTO recorridos_kit_base(categoria, elemento, cantidad_minima, unidad) VALUES(?, ?, ?, ?)",
                    (category, element, minimum, unit),
                )
                con.execute(
                    "UPDATE recorridos_kit_base SET categoria=? WHERE elemento=? AND categoria='Otros'",
                    (category, element),
                )
            con.execute(
                """
                INSERT OR IGNORE INTO recorrido_kit_check(recorrido_id, kit_id, cantidad_preparada)
                SELECT r.id, kb.id, kb.cantidad_minima
                FROM recorridos_operativos r
                CROSS JOIN recorridos_kit_base kb
                WHERE kb.activo = 1
                """
            )
            con.commit()
        finally:
            con.close()

    def table_columns(con: sqlite3.Connection, table: str):
        return {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}

    def load_sedes(con: sqlite3.Connection):
        columns = table_columns(con, "sedes_mpd")
        if not columns:
            return []
        code = "codigo" if "codigo" in columns else "codigo_sede"
        name = "nombre" if "nombre" in columns else code
        city = "ciudad" if "ciudad" in columns else name
        active_filter = "AND COALESCE(activa, 1) = 1" if "activa" in columns else ""
        rows = con.execute(
            f"""
            SELECT {code} AS codigo, {name} AS nombre, {city} AS ciudad
            FROM sedes_mpd
            WHERE COALESCE({code}, '') <> '' AND UPPER({code}) <> 'S09' {active_filter}
            ORDER BY {code}
            """
        ).fetchall()
        return rows

    def load_vehicles(con: sqlite3.Connection):
        if not table_columns(con, "vehiculos"):
            return []
        return con.execute(
            """
            SELECT patente, COALESCE(codigo_interno, '') AS codigo_interno,
                   COALESCE(modelo, tipo, '') AS modelo
            FROM vehiculos WHERE COALESCE(activo, 1) = 1 ORDER BY codigo_interno, patente
            """
        ).fetchall()

    def parse_stops(raw: str):
        seen = set()
        result = []
        for line in (raw or "").replace(",", "\n").splitlines():
            value = line.strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def match_sede(sedes, value: str):
        search = (value or "").strip().casefold()
        for sede in sedes:
            values = (sede["codigo"], sede["nombre"], sede["ciudad"])
            if search in {str(item or "").strip().casefold() for item in values}:
                return sede["codigo"]
        return None

    def seed_trip_kit(con: sqlite3.Connection, trip_id: int) -> None:
        con.execute(
            """
            INSERT OR IGNORE INTO recorrido_kit_check(recorrido_id, kit_id, cantidad_preparada)
            SELECT ?, id, cantidad_minima FROM recorridos_kit_base WHERE activo = 1
            """,
            (trip_id,),
        )

    def record_event(con, trip_id: int, event_type: str, stop_id=None, note=""):
        con.execute(
            """INSERT INTO recorrido_hitos(recorrido_id, parada_id, tipo, usuario, fecha_hora, nota)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (trip_id, stop_id, event_type, username(), now(), note or None),
        )

    def get_trip(con, trip_id: int):
        return con.execute(
            """
            SELECT r.*, COALESCE(s.nombre, r.destino_sede, '') AS destino_nombre,
                   COALESCE(v.codigo_interno || ' - ', '') || COALESCE(v.patente, r.vehiculo_patente, '') AS vehiculo_label
            FROM recorridos_operativos r
            LEFT JOIN sedes_mpd s ON s.codigo = r.destino_sede
            LEFT JOIN vehiculos v ON v.patente = r.vehiculo_patente
            WHERE r.id = ?
            """,
            (trip_id,),
        ).fetchone()

    def duration(start, end=None):
        if not start:
            return "--"
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") if end else datetime.now()
            minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
            hours, minutes = divmod(minutes, 60)
            return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
        except (TypeError, ValueError):
            return "--"

    def format_minutes(minutes: int) -> str:
        hours, remaining = divmod(max(0, minutes), 60)
        return f"{hours} h {remaining:02d} min" if hours else f"{remaining} min"

    ensure_schema()

    @app.route("/sedes/recorridos", endpoint="recorridos_operativos_lista")
    def trip_list():
        auth = require_login()
        if auth:
            return auth
        status_filter = (request.args.get("estado") or "").strip()
        route_filter = (request.args.get("ruta") or "").strip()
        date_from = (request.args.get("desde") or "").strip()
        date_to = (request.args.get("hasta") or "").strip()
        query = (request.args.get("q") or "").strip()
        con = connect()
        try:
            clauses = []
            params = []
            if status_filter in STATUSES:
                clauses.append("r.estado = ?")
                params.append(status_filter)
            if route_filter in ROUTE_STOPS:
                clauses.append("r.ruta = ?")
                params.append(route_filter)
            if date_from:
                clauses.append("r.fecha_prevista >= ?")
                params.append(date_from)
            if date_to:
                clauses.append("r.fecha_prevista <= ?")
                params.append(date_to)
            if query:
                like = f"%{query}%"
                clauses.append(
                    """(
                    r.equipo_operativo LIKE ? OR r.vehiculo_patente LIKE ? OR r.ruta LIKE ?
                    OR s.nombre LIKE ? OR EXISTS (
                        SELECT 1 FROM recorrido_paradas rp
                        WHERE rp.recorrido_id=r.id AND (rp.nombre LIKE ? OR rp.sede_codigo LIKE ?)
                    ))"""
                )
                params.extend([like, like, like, like, like, like])
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            trips = con.execute(
                f"""
                SELECT r.*, COALESCE(s.nombre, r.destino_sede, '') AS destino_nombre,
                       COALESCE(v.codigo_interno || ' - ', '') || COALESCE(v.patente, r.vehiculo_patente, '') AS vehiculo_label,
                       (SELECT COUNT(*) FROM recorrido_paradas p WHERE p.recorrido_id=r.id) AS paradas,
                       (SELECT COUNT(*) FROM recorrido_actividades a WHERE a.recorrido_id=r.id) AS actividades,
                       (SELECT COUNT(*) FROM recorrido_actividades a WHERE a.recorrido_id=r.id AND a.estado='Finalizada') AS actividades_finalizadas,
                       (SELECT COUNT(*) FROM recorrido_materiales m WHERE m.recorrido_id=r.id) AS materiales,
                       (SELECT COUNT(*) FROM recorrido_kit_check kc WHERE kc.recorrido_id=r.id AND kc.verificado=1) AS kit_verificado,
                       (SELECT COUNT(*) FROM recorrido_kit_check kc WHERE kc.recorrido_id=r.id) AS kit_total
                FROM recorridos_operativos r
                LEFT JOIN sedes_mpd s ON s.codigo = r.destino_sede
                LEFT JOIN vehiculos v ON v.patente = r.vehiculo_patente
                {where}
                ORDER BY r.fecha_prevista DESC, r.id DESC
                """,
                tuple(params),
            ).fetchall()
            status_counts = {status: 0 for status in STATUSES}
            for row in con.execute("SELECT estado, COUNT(*) AS total FROM recorridos_operativos GROUP BY estado"):
                status_counts[row["estado"]] = row["total"]
            return render_template(
                "recorridos/recorridos_lista.html",
                trips=trips,
                statuses=STATUSES,
                routes=ROUTE_STOPS,
                status_filter=status_filter,
                route_filter=route_filter,
                date_from=date_from,
                date_to=date_to,
                query=query,
                status_counts=status_counts,
            )
        finally:
            con.close()

    @app.route("/sedes/recorridos/nuevo", methods=["GET", "POST"], endpoint="recorridos_operativos_nuevo")
    @app.route("/sedes/recorridos/<int:trip_id>/editar", methods=["GET", "POST"], endpoint="recorridos_operativos_editar")
    def trip_form(trip_id=None):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            trip = get_trip(con, trip_id) if trip_id else None
            if trip_id and not trip:
                flash("Recorrido no encontrado.", "warning")
                return redirect(url_for("recorridos_operativos_lista"))
            if trip and trip["estado"] not in {"Borrador", "Preparado"}:
                flash("Solo pueden editarse recorridos en borrador o preparados.", "warning")
                return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id))

            sedes = load_sedes(con)
            vehicles = load_vehicles(con)
            current_stops = []
            if trip_id:
                current_stops = [row["nombre"] for row in con.execute(
                    "SELECT nombre FROM recorrido_paradas WHERE recorrido_id = ? ORDER BY orden", (trip_id,)
                ).fetchall()]

            if request.method == "POST":
                date = (request.form.get("fecha_prevista") or "").strip()
                route_name = (request.form.get("ruta") or "Otra").strip()
                destination = (request.form.get("destino_sede") or "").strip()
                vehicle = (request.form.get("vehiculo_patente") or "").strip()
                team = (request.form.get("equipo_operativo") or "").strip()
                observation = (request.form.get("observacion") or "").strip()
                stops = parse_stops(request.form.get("paradas"))
                if not stops and route_name in ROUTE_STOPS:
                    stops = list(ROUTE_STOPS[route_name])
                if not stops and destination:
                    selected_sede = next((item for item in sedes if item["codigo"] == destination), None)
                    if selected_sede:
                        stops = [selected_sede["ciudad"] or selected_sede["nombre"]]
                if not date or not team or route_name not in ROUTE_STOPS or not stops:
                    flash("Complete fecha, ruta, equipo operativo y al menos una parada.", "warning")
                else:
                    timestamp = now()
                    if trip_id:
                        con.execute(
                            """
                            UPDATE recorridos_operativos SET fecha_prevista=?, ruta=?, destino_sede=?,
                                vehiculo_patente=?, equipo_operativo=?, observacion=?, updated_at=? WHERE id=?
                            """,
                            (date, route_name, destination or None, vehicle or None, team, observation or None, timestamp, trip_id),
                        )
                        existing_rows = con.execute(
                            "SELECT id FROM recorrido_paradas WHERE recorrido_id=? ORDER BY orden", (trip_id,)
                        ).fetchall()
                    else:
                        cursor = con.execute(
                            """
                            INSERT INTO recorridos_operativos(fecha_prevista, ruta, destino_sede, vehiculo_patente,
                                equipo_operativo, observacion, created_by, created_at, updated_at)
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (date, route_name, destination or None, vehicle or None, team, observation or None,
                             username(), timestamp, timestamp),
                        )
                        trip_id = cursor.lastrowid
                        existing_rows = []
                    for index, stop in enumerate(stops, start=1):
                        if index <= len(existing_rows):
                            con.execute(
                                "UPDATE recorrido_paradas SET orden=?, sede_codigo=?, nombre=? WHERE id=?",
                                (index, match_sede(sedes, stop), stop, existing_rows[index - 1]["id"]),
                            )
                        else:
                            con.execute(
                                "INSERT INTO recorrido_paradas(recorrido_id, orden, sede_codigo, nombre) VALUES(?, ?, ?, ?)",
                                (trip_id, index, match_sede(sedes, stop), stop),
                            )
                    for obsolete in existing_rows[len(stops):]:
                        con.execute("DELETE FROM recorrido_paradas WHERE id=?", (obsolete["id"],))
                    seed_trip_kit(con, trip_id)
                    con.commit()
                    flash("Recorrido guardado.", "success")
                    return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id))

            form_data = request.form if request.method == "POST" else (dict(trip) if trip else {})
            if request.method == "POST":
                stop_text = request.form.get("paradas", "")
            else:
                stop_text = "\n".join(current_stops or ROUTE_STOPS["Norte"])
            return render_template(
                "recorridos/recorrido_form.html",
                trip=trip,
                form=form_data,
                stop_text=stop_text,
                route_stops=ROUTE_STOPS,
                sedes=sedes,
                vehicles=vehicles,
            )
        finally:
            con.close()

    @app.route("/sedes/recorridos/<int:trip_id>", endpoint="recorridos_operativos_detalle")
    def trip_detail(trip_id):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            trip = get_trip(con, trip_id)
            if not trip:
                flash("Recorrido no encontrado.", "warning")
                return redirect(url_for("recorridos_operativos_lista"))
            stops = con.execute(
                "SELECT * FROM recorrido_paradas WHERE recorrido_id=? ORDER BY orden", (trip_id,)
            ).fetchall()
            kit = con.execute(
                """
                SELECT kc.*, kb.categoria, kb.elemento, kb.cantidad_minima, kb.unidad
                FROM recorrido_kit_check kc JOIN recorridos_kit_base kb ON kb.id=kc.kit_id
                WHERE kc.recorrido_id=? ORDER BY kb.categoria, kb.id
                """,
                (trip_id,),
            ).fetchall()
            materials = con.execute(
                """SELECT m.*, COALESCE(p.nombre, m.sede_codigo, '') AS sede_nombre
                   FROM recorrido_materiales m LEFT JOIN recorrido_paradas p ON p.id=m.parada_id
                   WHERE m.recorrido_id=? ORDER BY m.id DESC""",
                (trip_id,),
            ).fetchall()
            activities = con.execute(
                """SELECT a.*, COALESCE(p.nombre, a.sede_codigo, '') AS sede_nombre
                   FROM recorrido_actividades a LEFT JOIN recorrido_paradas p ON p.id=a.parada_id
                   WHERE a.recorrido_id=? ORDER BY a.id DESC""",
                (trip_id,),
            ).fetchall()
            events = con.execute(
                """SELECT h.*, COALESCE(p.nombre, '') AS parada_nombre FROM recorrido_hitos h
                   LEFT JOIN recorrido_paradas p ON p.id=h.parada_id
                   WHERE h.recorrido_id=? ORDER BY h.fecha_hora DESC, h.id DESC""",
                (trip_id,),
            ).fetchall()
            activity_counts = {}
            material_counts = {}
            for item in activities:
                activity_counts[item["parada_id"]] = activity_counts.get(item["parada_id"], 0) + 1
            for item in materials:
                material_counts[item["parada_id"]] = material_counts.get(item["parada_id"], 0) + 1

            site_minutes = 0
            execution_stops = []
            previous_mark = datetime.strptime(trip["started_at"], "%Y-%m-%d %H:%M:%S") if trip["started_at"] else None
            calculation_end = datetime.strptime(trip["finished_at"], "%Y-%m-%d %H:%M:%S") if trip["finished_at"] else datetime.now()
            stop_views = []
            for row in stops:
                stop = dict(row)
                stop["activity_count"] = activity_counts.get(stop["id"], 0)
                stop["material_count"] = material_counts.get(stop["id"], 0)
                stop["site_duration"] = "--"
                stop["route_before"] = "--"
                if stop["started_at"]:
                    start_dt = datetime.strptime(stop["started_at"], "%Y-%m-%d %H:%M:%S")
                    if previous_mark:
                        stop["route_before"] = format_minutes(int(max(0, (start_dt - previous_mark).total_seconds()) // 60))
                    finish_dt = datetime.strptime(stop["finished_at"], "%Y-%m-%d %H:%M:%S") if stop["finished_at"] else calculation_end
                    stop_minutes = int(max(0, (finish_dt - start_dt).total_seconds()) // 60)
                    site_minutes += stop_minutes
                    stop["site_duration"] = format_minutes(stop_minutes)
                    previous_mark = finish_dt
                if stop["activity_count"]:
                    execution_stops.append(stop)
                stop_views.append(stop)
            stops = stop_views
            total_minutes = 0
            if trip["started_at"]:
                start_trip_dt = datetime.strptime(trip["started_at"], "%Y-%m-%d %H:%M:%S")
                total_minutes = int(max(0, (calculation_end - start_trip_dt).total_seconds()) // 60)
            route_minutes = max(0, total_minutes - site_minutes)
            metrics = {
                "total": duration(trip["started_at"], trip["finished_at"]),
                "sede": format_minutes(site_minutes),
                "ruta": format_minutes(route_minutes),
                "operativo": format_minutes(site_minutes),
                "sedes_visitadas": sum(1 for stop in execution_stops if stop["started_at"]),
                "actividades": len(activities),
                "actividades_finalizadas": sum(1 for item in activities if item["estado"] == "Finalizada"),
                "materiales": len(materials),
                "materiales_entregados": sum(float(item["cantidad"] or 0) for item in materials if item["estado"] == "Entregado"),
            }
            next_execution_stop_id = next(
                (stop["id"] for stop in execution_stops if not stop["finished_at"]),
                None,
            )
            return render_template(
                "recorridos/recorrido_detalle.html",
                trip=trip,
                stops=stops,
                execution_stops=execution_stops,
                next_execution_stop_id=next_execution_stop_id,
                kit=kit,
                materials=materials,
                activities=activities,
                events=events,
                metrics=metrics,
                material_types=MATERIAL_TYPES,
                material_statuses=MATERIAL_STATUSES,
                activity_types=ACTIVITY_TYPES,
                activity_statuses=ACTIVITY_STATUSES,
                activity_priorities=ACTIVITY_PRIORITIES,
            )
        finally:
            con.close()

    @app.post("/sedes/recorridos/<int:trip_id>/kit", endpoint="recorridos_operativos_kit")
    def trip_kit(trip_id):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            for row in con.execute("SELECT * FROM recorrido_kit_check WHERE recorrido_id=?", (trip_id,)).fetchall():
                check_id = row["id"]
                prepared = request.form.get(f"cantidad_{check_id}")
                con.execute(
                    "UPDATE recorrido_kit_check SET cantidad_preparada=?, verificado=?, observacion=? WHERE id=?",
                    (prepared if prepared is not None else row["cantidad_preparada"],
                     1 if request.form.get(f"check_{check_id}") else 0,
                     (request.form.get(f"nota_{check_id}") or "").strip() or None, check_id),
                )
            con.execute(
                "UPDATE recorridos_operativos SET estado='Preparado', updated_at=? WHERE id=? AND estado='Borrador'",
                (now(), trip_id),
            )
            con.commit()
            flash("Checklist actualizado.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#preparacion")

    @app.post("/sedes/recorridos/<int:trip_id>/kit/nuevo", endpoint="recorridos_operativos_kit_nuevo")
    def add_kit_item(trip_id):
        auth = require_login()
        if auth:
            return auth
        element = (request.form.get("elemento") or "").strip()
        if not element:
            flash("Indique el elemento del kit.", "warning")
            return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#preparacion")
        con = connect()
        try:
            con.execute(
                "INSERT OR IGNORE INTO recorridos_kit_base(categoria, elemento, cantidad_minima, unidad) VALUES(?, ?, ?, ?)",
                ((request.form.get("categoria") or "Otros").strip(), element, request.form.get("cantidad_minima") or 1,
                 (request.form.get("unidad") or "unidades").strip()),
            )
            seed_trip_kit(con, trip_id)
            con.commit()
            flash("Elemento agregado al kit permanente.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#preparacion")

    @app.post("/sedes/recorridos/<int:trip_id>/material", endpoint="recorridos_operativos_material")
    def add_material(trip_id):
        auth = require_login()
        if auth:
            return auth
        element = (request.form.get("elemento") or "").strip()
        if not element:
            flash("Indique el material.", "warning")
            return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#materiales")
        con = connect()
        try:
            stop_id = request.form.get("parada_id") or None
            sede = None
            if stop_id:
                row = con.execute("SELECT sede_codigo FROM recorrido_paradas WHERE id=? AND recorrido_id=?", (stop_id, trip_id)).fetchone()
                sede = row["sede_codigo"] if row else None
            con.execute(
                """INSERT INTO recorrido_materiales(recorrido_id, parada_id, sede_codigo, elemento, cantidad, tipo, observacion, estado)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (trip_id, stop_id, sede, element, request.form.get("cantidad") or 1,
                 request.form.get("tipo") if request.form.get("tipo") in MATERIAL_TYPES else "Otro",
                 (request.form.get("observacion") or "").strip() or None,
                 request.form.get("estado") if request.form.get("estado") in MATERIAL_STATUSES else "Pendiente"),
            )
            con.commit()
            flash("Material agregado.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#materiales")

    @app.post("/sedes/recorridos/<int:trip_id>/material/<int:item_id>/estado", endpoint="recorridos_operativos_material_estado")
    def material_status(trip_id, item_id):
        auth = require_login()
        if auth:
            return auth
        status = request.form.get("estado")
        if status in MATERIAL_STATUSES:
            con = connect()
            try:
                con.execute("UPDATE recorrido_materiales SET estado=? WHERE id=? AND recorrido_id=?", (status, item_id, trip_id))
                con.commit()
            finally:
                con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#materiales")

    @app.post("/sedes/recorridos/<int:trip_id>/actividad", endpoint="recorridos_operativos_actividad")
    def add_activity(trip_id):
        auth = require_login()
        if auth:
            return auth
        detail = (request.form.get("detalle") or "").strip()
        if not detail:
            flash("Indique la actividad.", "warning")
            return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#actividades")
        con = connect()
        try:
            stop_id = request.form.get("parada_id") or None
            sede = None
            if stop_id:
                row = con.execute("SELECT sede_codigo FROM recorrido_paradas WHERE id=? AND recorrido_id=?", (stop_id, trip_id)).fetchone()
                sede = row["sede_codigo"] if row else None
            priority = request.form.get("prioridad") if request.form.get("prioridad") in ACTIVITY_PRIORITIES else "Media"
            estimated = request.form.get("tiempo_estimado_min") or None
            con.execute(
                """INSERT INTO recorrido_actividades(recorrido_id, parada_id, sede_codigo, tipo, detalle,
                   prioridad, tiempo_estimado_min, material_asociado, estado, observacion)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trip_id, stop_id, sede,
                 request.form.get("tipo") if request.form.get("tipo") in ACTIVITY_TYPES else "Otro",
                 detail, priority, estimated, (request.form.get("material_asociado") or "").strip() or None,
                 request.form.get("estado") if request.form.get("estado") in ACTIVITY_STATUSES else "Pendiente",
                 (request.form.get("observacion") or "").strip() or None),
            )
            con.commit()
            flash("Actividad agregada.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#actividades")

    @app.post("/sedes/recorridos/<int:trip_id>/actividad/<int:item_id>/estado", endpoint="recorridos_operativos_actividad_estado")
    def activity_status(trip_id, item_id):
        auth = require_login()
        if auth:
            return auth
        status = request.form.get("estado")
        if status in ACTIVITY_STATUSES:
            con = connect()
            try:
                timestamp = now()
                started = timestamp if status == "En curso" else None
                finished = timestamp if status == "Finalizada" else None
                con.execute(
                    """UPDATE recorrido_actividades SET estado=?,
                       started_at=CASE WHEN ? IS NOT NULL THEN COALESCE(started_at, ?) ELSE started_at END,
                       finished_at=CASE WHEN ? IS NOT NULL THEN COALESCE(finished_at, ?) ELSE finished_at END
                       WHERE id=? AND recorrido_id=?""",
                    (status, started, started, finished, finished, item_id, trip_id),
                )
                con.commit()
            finally:
                con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#actividades")

    @app.post("/sedes/recorridos/<int:trip_id>/iniciar", endpoint="recorridos_operativos_iniciar")
    def start_trip(trip_id):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            trip = get_trip(con, trip_id)
            if trip and trip["estado"] in {"Borrador", "Preparado"}:
                planned = con.execute(
                    "SELECT COUNT(DISTINCT parada_id) AS total FROM recorrido_actividades WHERE recorrido_id=? AND parada_id IS NOT NULL AND estado <> 'Cancelada'",
                    (trip_id,),
                ).fetchone()["total"]
                if not planned:
                    flash("Agregue al menos una actividad en una sede antes de iniciar.", "warning")
                    return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#planificacion")
                timestamp = now()
                con.execute("UPDATE recorridos_operativos SET estado='En recorrido', started_at=?, updated_at=? WHERE id=?", (timestamp, timestamp, trip_id))
                record_event(con, trip_id, "Salida a recorrido", note=request.form.get("nota", ""))
                con.commit()
                flash("Recorrido iniciado.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id))

    @app.post("/sedes/recorridos/<int:trip_id>/parada/<int:stop_id>/<action>", endpoint="recorridos_operativos_parada")
    def stop_action(trip_id, stop_id, action):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            stop = con.execute("SELECT * FROM recorrido_paradas WHERE id=? AND recorrido_id=?", (stop_id, trip_id)).fetchone()
            trip = get_trip(con, trip_id)
            if stop and trip and trip["estado"] == "En recorrido":
                activity_total = con.execute(
                    "SELECT COUNT(*) AS total FROM recorrido_actividades WHERE parada_id=? AND estado <> 'Cancelada'",
                    (stop_id,),
                ).fetchone()["total"]
                if not activity_total:
                    flash("Esta sede no tiene actividades programadas.", "warning")
                    return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#ejecucion")
                next_stop = con.execute(
                    """
                    SELECT p.id FROM recorrido_paradas p
                    WHERE p.recorrido_id=? AND p.finished_at IS NULL
                      AND EXISTS (
                        SELECT 1 FROM recorrido_actividades a
                        WHERE a.parada_id=p.id AND a.estado <> 'Cancelada'
                      )
                    ORDER BY p.orden LIMIT 1
                    """,
                    (trip_id,),
                ).fetchone()
                if not next_stop or next_stop["id"] != stop_id:
                    flash("Complete la sede anterior antes de continuar.", "warning")
                    return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#ejecucion")
                timestamp = now()
                note = (request.form.get("nota") or "").strip()
                if action == "iniciar" and not stop["started_at"]:
                    con.execute("UPDATE recorrido_paradas SET estado='En curso', started_at=?, notas=? WHERE id=?", (timestamp, note or None, stop_id))
                    con.execute("UPDATE recorrido_actividades SET estado='En curso', started_at=? WHERE parada_id=? AND estado='Pendiente'", (timestamp, stop_id))
                    record_event(con, trip_id, "Llegada a sede", stop_id, note)
                elif action == "finalizar" and stop["started_at"] and not stop["finished_at"]:
                    con.execute("UPDATE recorrido_paradas SET estado='Finalizada', finished_at=?, notas=COALESCE(?, notas) WHERE id=?", (timestamp, note or None, stop_id))
                    con.execute("UPDATE recorrido_actividades SET estado='Finalizada', finished_at=? WHERE parada_id=? AND estado='En curso'", (timestamp, stop_id))
                    record_event(con, trip_id, "Salida de sede", stop_id, note)
                con.commit()
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#paradas")

    @app.post("/sedes/recorridos/<int:trip_id>/finalizar", endpoint="recorridos_operativos_finalizar")
    def finish_trip(trip_id):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            trip = get_trip(con, trip_id)
            if trip and trip["estado"] == "En recorrido":
                pending = con.execute(
                    """
                    SELECT COUNT(*) AS total FROM recorrido_paradas p
                    WHERE p.recorrido_id=? AND p.finished_at IS NULL
                      AND EXISTS (
                        SELECT 1 FROM recorrido_actividades a
                        WHERE a.parada_id=p.id AND a.estado <> 'Cancelada'
                      )
                    """,
                    (trip_id,),
                ).fetchone()["total"]
                if pending:
                    flash("Complete las sedes programadas antes de finalizar el recorrido.", "warning")
                    return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id) + "#ejecucion")
                timestamp = now()
                note = (request.form.get("nota") or "").strip()
                con.execute("UPDATE recorridos_operativos SET estado='Finalizado', finished_at=?, final_note=?, updated_at=? WHERE id=?", (timestamp, note or None, timestamp, trip_id))
                record_event(con, trip_id, "Fin del recorrido", note=note)
                con.commit()
                flash("Recorrido finalizado.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id))

    @app.post("/sedes/recorridos/<int:trip_id>/cerrar", endpoint="recorridos_operativos_cerrar")
    def close_trip(trip_id):
        auth = require_login()
        if auth:
            return auth
        con = connect()
        try:
            trip = get_trip(con, trip_id)
            if trip and trip["estado"] == "Finalizado":
                timestamp = now()
                note = (request.form.get("nota") or trip["final_note"] or "").strip()
                con.execute("UPDATE recorridos_operativos SET estado='Cerrado', closed_at=?, final_note=?, updated_at=? WHERE id=?", (timestamp, note or None, timestamp, trip_id))
                record_event(con, trip_id, "Cierre administrativo", note=note)
                con.commit()
                flash("Recorrido cerrado.", "success")
        finally:
            con.close()
        return redirect(url_for("recorridos_operativos_detalle", trip_id=trip_id))

    app._recorridos_operativos_registered = True
