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
DEFAULT_KIT = (
    ("Tubos LED", 6, "unidades"),
    ("Tornillos y tarugos", 1, "juego"),
    ("Herramientas basicas", 1, "juego"),
    ("Gomas para canillas", 4, "unidades"),
    ("Lamparas", 4, "unidades"),
    ("Escalera", 1, "unidad"),
    ("Elementos de proteccion personal", 1, "juego"),
    ("Documentacion del recorrido", 1, "juego"),
    ("Combustible verificado", 1, "control"),
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
            for element, minimum, unit in DEFAULT_KIT:
                con.execute(
                    "INSERT OR IGNORE INTO recorridos_kit_base(elemento, cantidad_minima, unidad) VALUES(?, ?, ?)",
                    (element, minimum, unit),
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
        con = connect()
        try:
            where = "WHERE r.estado = ?" if status_filter in STATUSES else ""
            params = (status_filter,) if where else ()
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
                params,
            ).fetchall()
            return render_template(
                "recorridos/recorridos_lista.html",
                trips=trips,
                statuses=STATUSES,
                status_filter=status_filter,
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
                SELECT kc.*, kb.elemento, kb.cantidad_minima, kb.unidad
                FROM recorrido_kit_check kc JOIN recorridos_kit_base kb ON kb.id=kc.kit_id
                WHERE kc.recorrido_id=? ORDER BY kb.id
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
            site_minutes = 0
            route_minutes = 0
            previous_finish = None
            for stop in stops:
                if stop["started_at"] and stop["finished_at"]:
                    start_dt = datetime.strptime(stop["started_at"], "%Y-%m-%d %H:%M:%S")
                    finish_dt = datetime.strptime(stop["finished_at"], "%Y-%m-%d %H:%M:%S")
                    site_minutes += max(0, int((finish_dt - start_dt).total_seconds() // 60))
                    if previous_finish:
                        route_minutes += max(0, int((start_dt - previous_finish).total_seconds() // 60))
                    previous_finish = finish_dt
            metrics = {
                "total": duration(trip["started_at"], trip["finished_at"]),
                "sede": format_minutes(site_minutes),
                "ruta": format_minutes(route_minutes),
                "actividades": len(activities),
                "actividades_finalizadas": sum(1 for item in activities if item["estado"] == "Finalizada"),
                "materiales": len(materials),
                "materiales_entregados": sum(1 for item in materials if item["estado"] == "Entregado"),
            }
            return render_template(
                "recorridos/recorrido_detalle.html",
                trip=trip,
                stops=stops,
                kit=kit,
                materials=materials,
                activities=activities,
                events=events,
                metrics=metrics,
                material_types=MATERIAL_TYPES,
                material_statuses=MATERIAL_STATUSES,
                activity_types=ACTIVITY_TYPES,
                activity_statuses=ACTIVITY_STATUSES,
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
            for row in con.execute("SELECT id FROM recorrido_kit_check WHERE recorrido_id=?", (trip_id,)).fetchall():
                check_id = row["id"]
                con.execute(
                    "UPDATE recorrido_kit_check SET cantidad_preparada=?, verificado=?, observacion=? WHERE id=?",
                    (request.form.get(f"cantidad_{check_id}", 0), 1 if request.form.get(f"check_{check_id}") else 0,
                     (request.form.get(f"nota_{check_id}") or "").strip() or None, check_id),
                )
                kit_row = con.execute("SELECT kit_id FROM recorrido_kit_check WHERE id=?", (check_id,)).fetchone()
                if kit_row:
                    con.execute(
                        "UPDATE recorridos_kit_base SET cantidad_minima=?, unidad=? WHERE id=?",
                        (request.form.get(f"minimo_{check_id}") or 1,
                         (request.form.get(f"unidad_{check_id}") or "unidades").strip(), kit_row["kit_id"]),
                    )
            total, checked = con.execute(
                "SELECT COUNT(*), SUM(verificado) FROM recorrido_kit_check WHERE recorrido_id=?", (trip_id,)
            ).fetchone()
            if total and total == checked:
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
                "INSERT OR IGNORE INTO recorridos_kit_base(elemento, cantidad_minima, unidad) VALUES(?, ?, ?)",
                (element, request.form.get("cantidad_minima") or 1,
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
            con.execute(
                """INSERT INTO recorrido_actividades(recorrido_id, parada_id, sede_codigo, tipo, detalle, estado, observacion)
                   VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (trip_id, stop_id, sede,
                 request.form.get("tipo") if request.form.get("tipo") in ACTIVITY_TYPES else "Otro",
                 detail, request.form.get("estado") if request.form.get("estado") in ACTIVITY_STATUSES else "Pendiente",
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
                timestamp = now()
                con.execute("UPDATE recorridos_operativos SET estado='En recorrido', started_at=?, updated_at=? WHERE id=?", (timestamp, timestamp, trip_id))
                record_event(con, trip_id, "Inicio del recorrido", note=request.form.get("nota", ""))
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
                timestamp = now()
                note = (request.form.get("nota") or "").strip()
                if action == "iniciar" and not stop["started_at"]:
                    con.execute("UPDATE recorrido_paradas SET estado='En curso', started_at=?, notas=? WHERE id=?", (timestamp, note or None, stop_id))
                    con.execute("UPDATE recorrido_actividades SET estado='En curso', started_at=? WHERE parada_id=? AND estado='Pendiente'", (timestamp, stop_id))
                    record_event(con, trip_id, "Inicio de actividad en sede", stop_id, note)
                elif action == "finalizar" and stop["started_at"] and not stop["finished_at"]:
                    con.execute("UPDATE recorrido_paradas SET estado='Finalizada', finished_at=?, notas=COALESCE(?, notas) WHERE id=?", (timestamp, note or None, stop_id))
                    con.execute("UPDATE recorrido_actividades SET estado='Finalizada', finished_at=? WHERE parada_id=? AND estado='En curso'", (timestamp, stop_id))
                    record_event(con, trip_id, "Fin de actividad en sede", stop_id, note)
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
