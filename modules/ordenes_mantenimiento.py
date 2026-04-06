import os
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename


def register_ordenes_mantenimiento(app: Flask) -> None:
    if getattr(app, "_ordenes_mantenimiento_registered", False):
        return
    if "ordenes_alerts_count" in getattr(app, "view_functions", {}):
        app._ordenes_mantenimiento_registered = True
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "mpd.db")
    uploads_dir = os.path.join(base_dir, "uploads", "ordenes_mantenimiento")
    os.makedirs(uploads_dir, exist_ok=True)
    allowed_ext = {"jpg", "jpeg", "png", "webp", "pdf"}

    seed_members = ("cvidaurre", "mflores", "mduran", "nguerrero")

    def _connect() -> sqlite3.Connection:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        return con

    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _current_username() -> str:
        return (session.get("username") or "").strip().lower()

    def _current_role() -> str:
        return (session.get("role") or "").strip().lower()

    def _is_admin_or_boss(username: str, role: str) -> bool:
        return username == "mcalderari" or role in {"full", "admin"}

    def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return bool(row)

    def _table_columns(con: sqlite3.Connection, table_name: str):
        if not _table_exists(con, table_name):
            return []
        return [r["name"] for r in con.execute(f"PRAGMA table_info({table_name})").fetchall()]

    def _ensure_schema() -> None:
        con = _connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    sede_id TEXT,
                    deposito_id TEXT,
                    title TEXT NOT NULL,
                    detail TEXT,
                    priority TEXT NOT NULL DEFAULT 'MEDIA',
                    status TEXT NOT NULL DEFAULT 'NUEVA',
                    assign_type TEXT NOT NULL DEFAULT 'GRUPO',
                    assigned_user TEXT,
                    assigned_group_id INTEGER,
                    due_date TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT,
                    attachment_url TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    order_id INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    assigned_to TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ABIERTA',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS purchase_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    sede_id TEXT,
                    deposito_id TEXT,
                    requested_by TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDIENTE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS work_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS work_group_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    FOREIGN KEY(group_id) REFERENCES work_groups(id)
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_orders_type_status ON orders(type, status)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_orders_assigned_user ON orders(assigned_user)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id, created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(alert_type, status, assigned_to)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_purchase_order ON purchase_requests(order_id, status)")
            con.execute("INSERT OR IGNORE INTO work_groups(name, active) VALUES('Equipo mantenimiento', 1)")
            grp = con.execute(
                "SELECT id FROM work_groups WHERE name='Equipo mantenimiento' LIMIT 1"
            ).fetchone()
            if grp:
                gid = int(grp["id"])
                for username in seed_members:
                    con.execute(
                        """
                        INSERT INTO work_group_members(group_id, username)
                        SELECT ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM work_group_members
                            WHERE group_id = ? AND LOWER(COALESCE(username,'')) = LOWER(?)
                        )
                        """,
                        (gid, username, gid, username),
                    )
            con.commit()
        finally:
            con.close()

    def _load_groups(con: sqlite3.Connection):
        return con.execute(
            """
            SELECT
                g.id,
                g.name,
                g.active,
                COUNT(m.id) AS members
            FROM work_groups g
            LEFT JOIN work_group_members m ON m.group_id = g.id
            WHERE COALESCE(g.active, 1) = 1
            GROUP BY g.id, g.name, g.active
            ORDER BY g.name
            """
        ).fetchall()

    def _load_users(con: sqlite3.Connection):
        if not _table_exists(con, "usuarios"):
            return []
        return con.execute(
            """
            SELECT LOWER(COALESCE(username,'')) AS username, COALESCE(full_name, username) AS full_name
            FROM usuarios
            WHERE COALESCE(activo, 1) = 1
            ORDER BY COALESCE(full_name, username)
            """
        ).fetchall()

    def _load_sedes(con: sqlite3.Connection):
        cols = _table_columns(con, "sedes_mpd")
        if not cols:
            fallback = con.execute(
                """
                SELECT DISTINCT TRIM(COALESCE(sede_id,'')) AS sede_id
                FROM orders
                WHERE TRIM(COALESCE(sede_id,'')) <> ''
                ORDER BY sede_id
                """
            ).fetchall()
            return [{"id": r["sede_id"], "label": r["sede_id"]} for r in fallback]

        id_col = "codigo_sede" if "codigo_sede" in cols else ("codigo" if "codigo" in cols else cols[0])
        label_col = "sede" if "sede" in cols else ("nombre" if "nombre" in cols else id_col)
        rows = con.execute(
            f"""
            SELECT DISTINCT
                TRIM(COALESCE({id_col},'')) AS sede_id,
                TRIM(COALESCE({label_col},'')) AS sede_label
            FROM sedes_mpd
            WHERE TRIM(COALESCE({id_col},'')) <> ''
            ORDER BY sede_id
            """
        ).fetchall()
        out = []
        for r in rows:
            sid = (r["sede_id"] or "").strip()
            sname = (r["sede_label"] or "").strip()
            out.append({"id": sid, "label": f"{sid} - {sname}" if sname and sname != sid else sid})
        return out

    def _qi(name: str) -> str:
        return '"' + str(name or "").replace('"', '""') + '"'

    def _pick_column(cols, candidates):
        cols_map = {str(c).strip().lower(): c for c in (cols or [])}
        for c in candidates:
            k = str(c).strip().lower()
            if k in cols_map:
                return cols_map[k]
        return None

    def _list_tables(con: sqlite3.Connection):
        names = set()
        try:
            rows = con.execute("PRAGMA table_list").fetchall()
            for r in rows:
                try:
                    name = (r["name"] or "").strip()
                except Exception:
                    name = (r[1] or "").strip() if len(r) > 1 else ""
                if name:
                    names.add(name)
        except Exception:
            pass
        rows2 = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for r in rows2:
            try:
                name = (r["name"] or "").strip()
            except Exception:
                name = (r[0] or "").strip() if len(r) > 0 else ""
            if name:
                names.add(name)
        return names

    def _ensure_sede_depositos_catalogo(con: sqlite3.Connection):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sede_depositos_catalogo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_id TEXT NOT NULL,
                deposito_id TEXT NOT NULL,
                label TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sede_depositos_catalogo_sede ON sede_depositos_catalogo(sede_id, deposito_id)"
        )
        con.commit()

    def _load_depositos_for_sede(con: sqlite3.Connection, sede_id: str):
        sede_id = (sede_id or "").strip()
        possible_tables = [
            "sedes_depositos",
            "depositos",
            "depositos_mpd",
            "depositos_por_sede",
            "depositos_sede",
        ]
        sede_candidates = [
            "sede_id", "sede", "codigo_sede", "sede_codigo", "id_sede", "codigo"
        ]
        deposito_candidates = [
            "deposito_id", "deposito", "codigo_deposito", "id_deposito",
            "local_id", "codigo_local", "local", "dpto", "dpto_def", "nombre"
        ]
        label_candidates = [
            "label", "nombre", "descripcion", "detalle", "deposito",
            "local", "deposito_id", "codigo_local", "codigo_deposito"
        ]

        tables = _list_tables(con)
        source = None
        for t in possible_tables:
            if t not in tables:
                continue
            cols = _table_columns(con, t)
            sede_col = _pick_column(cols, sede_candidates)
            dep_col = _pick_column(cols, deposito_candidates)
            if not sede_col or not dep_col:
                continue
            label_col = _pick_column(cols, label_candidates) or dep_col
            source = (t, sede_col, dep_col, label_col)
            break

        if source is None:
            _ensure_sede_depositos_catalogo(con)
            source = ("sede_depositos_catalogo", "sede_id", "deposito_id", "label")

        if not sede_id:
            return []

        table_name, sede_col, dep_col, label_col = source
        sql = f"""
            SELECT DISTINCT
                TRIM(COALESCE({_qi(dep_col)}, '')) AS deposito_id,
                TRIM(COALESCE({_qi(label_col)}, {_qi(dep_col)}, '')) AS label
            FROM {_qi(table_name)}
            WHERE TRIM(COALESCE({_qi(dep_col)}, '')) <> ''
              AND LOWER(TRIM(COALESCE({_qi(sede_col)}, ''))) = LOWER(?)
            ORDER BY deposito_id
        """
        rows = con.execute(sql, (sede_id,)).fetchall()
        return [
            {
                "deposito_id": (r["deposito_id"] or "").strip(),
                "label": ((r["label"] or "").strip() or (r["deposito_id"] or "").strip()),
            }
            for r in rows
            if (r["deposito_id"] or "").strip()
        ]

    def _is_group_member(con: sqlite3.Connection, group_id, username: str) -> bool:
        if not group_id or not username:
            return False
        row = con.execute(
            """
            SELECT 1
            FROM work_group_members
            WHERE group_id = ?
              AND LOWER(COALESCE(username,'')) = LOWER(?)
            LIMIT 1
            """,
            (group_id, username),
        ).fetchone()
        return bool(row)

    def _can_view_or_operate(con: sqlite3.Connection, order_row, username: str, is_admin: bool) -> bool:
        if is_admin:
            return True
        if not order_row or not username:
            return False
        if (order_row["created_by"] or "").strip().lower() == username:
            return True
        if (order_row["assigned_user"] or "").strip().lower() == username:
            return True
        if (order_row["assign_type"] or "").strip().upper() == "GRUPO":
            return _is_group_member(con, order_row["assigned_group_id"], username)
        return False

    def _count_open_falta_material(con: sqlite3.Connection) -> int:
        row = con.execute(
            """
            SELECT COUNT(*) AS n
            FROM alerts
            WHERE alert_type = 'FALTA_MATERIAL'
              AND assigned_to = 'mcalderari'
              AND status = 'ABIERTA'
            """
        ).fetchone()
        return int(row["n"] if row else 0)

    def _save_attachment(file_storage):
        if not file_storage or not getattr(file_storage, "filename", ""):
            return ""
        filename = secure_filename(file_storage.filename or "")
        if "." not in filename:
            return ""
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in allowed_ext:
            return ""
        out_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}.{ext}"
        out_path = os.path.join(uploads_dir, out_name)
        file_storage.save(out_path)
        return out_name

    _ensure_schema()

    @app.route("/ordenes/alerts/count", methods=["GET"], endpoint="ordenes_alerts_count")
    def ordenes_alerts_count():
        if not session.get("user_id"):
            return jsonify({"falta_material_abiertas": 0}), 401
        con = _connect()
        try:
            return jsonify({"falta_material_abiertas": _count_open_falta_material(con)})
        finally:
            con.close()

    @app.route("/ordenes/api/depositos", methods=["GET"], endpoint="ordenes_api_depositos")
    def ordenes_api_depositos():
        if not session.get("user_id"):
            return jsonify({"items": []}), 401
        sede_id = (request.args.get("sede_id") or "").strip()
        con = _connect()
        try:
            items = _load_depositos_for_sede(con, sede_id)
            return jsonify({"items": items})
        finally:
            con.close()

    @app.route("/ordenes/uploads/<path:filename>", methods=["GET"], endpoint="ordenes_upload")
    def ordenes_upload(filename):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return send_from_directory(uploads_dir, filename, as_attachment=False)

    @app.route("/ordenes/mantenimiento", methods=["GET"], endpoint="ordenes_mantenimiento_list")
    def ordenes_mantenimiento_list():
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        username = _current_username()
        role = _current_role()
        is_admin = _is_admin_or_boss(username, role)

        status_f = (request.args.get("status") or "").strip().upper()
        sede_f = (request.args.get("sede_id") or "").strip()
        priority_f = (request.args.get("priority") or "").strip().upper()
        assigned_f = (request.args.get("assigned") or "").strip()

        con = _connect()
        try:
            where = ["o.type = 'MANTENIMIENTO'"]
            params = []
            if status_f:
                where.append("o.status = ?")
                params.append(status_f)
            if sede_f:
                where.append("LOWER(COALESCE(o.sede_id,'')) = LOWER(?)")
                params.append(sede_f)
            if priority_f:
                where.append("o.priority = ?")
                params.append(priority_f)
            if assigned_f:
                where.append(
                    """
                    (
                      LOWER(COALESCE(o.assigned_user,'')) = LOWER(?)
                      OR LOWER(COALESCE(wg.name,'')) LIKE LOWER(?)
                    )
                    """
                )
                params.extend([assigned_f, f"%{assigned_f}%"])
            if not is_admin:
                where.append(
                    """
                    (
                      LOWER(COALESCE(o.created_by,'')) = LOWER(?)
                      OR LOWER(COALESCE(o.assigned_user,'')) = LOWER(?)
                      OR EXISTS (
                        SELECT 1
                        FROM work_group_members wgm
                        WHERE wgm.group_id = o.assigned_group_id
                          AND LOWER(COALESCE(wgm.username,'')) = LOWER(?)
                      )
                    )
                    """
                )
                params.extend([username, username, username])

            orders = con.execute(
                f"""
                SELECT
                    o.*,
                    COALESCE(wg.name, '') AS group_name,
                    COALESCE(le.event_type, '') AS last_event_type,
                    COALESCE(le.message, '') AS last_event_message,
                    COALESCE(le.created_at, o.updated_at) AS last_event_at
                FROM orders o
                LEFT JOIN work_groups wg ON wg.id = o.assigned_group_id
                LEFT JOIN order_events le ON le.id = (
                    SELECT e2.id
                    FROM order_events e2
                    WHERE e2.order_id = o.id
                    ORDER BY e2.created_at DESC, e2.id DESC
                    LIMIT 1
                )
                WHERE {" AND ".join(where)}
                ORDER BY o.updated_at DESC, o.id DESC
                """,
                params,
            ).fetchall()

            sedes = _load_sedes(con)
            alerta_count = _count_open_falta_material(con)
            return render_template(
                "ordenes/mantenimiento_list.html",
                orders=orders,
                sedes=sedes,
                status_f=status_f,
                sede_f=sede_f,
                priority_f=priority_f,
                assigned_f=assigned_f,
                alerta_count=alerta_count,
                is_admin=is_admin,
            )
        finally:
            con.close()

    @app.route(
        "/ordenes/mantenimiento/nueva",
        methods=["GET", "POST"],
        endpoint="ordenes_mantenimiento_nueva",
    )
    def ordenes_mantenimiento_nueva():
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        username = _current_username()

        con = _connect()
        try:
            groups = _load_groups(con)
            users = _load_users(con)
            sedes = _load_sedes(con)
            selected_sede = (request.form.get("sede_id") or request.args.get("sede_id") or "").strip()
            depositos = _load_depositos_for_sede(con, selected_sede)

            if request.method == "POST":
                sede_id = (request.form.get("sede_id") or "").strip()
                deposito_id = (request.form.get("deposito_id") or "").strip()
                title = (request.form.get("title") or "").strip()
                detail = (request.form.get("detail") or "").strip()
                priority = (request.form.get("priority") or "MEDIA").strip().upper()
                assign_mode = (request.form.get("assign_mode") or "GRUPO").strip().upper()
                assigned_user = (request.form.get("assigned_user") or "").strip().lower()
                assigned_group_id = (request.form.get("assigned_group_id") or "").strip()
                due_date = (request.form.get("due_date") or "").strip()

                if not sede_id:
                    flash("Debe indicar sede.", "warning")
                    return render_template(
                        "ordenes/mantenimiento_nueva.html",
                        groups=groups,
                        users=users,
                        sedes=sedes,
                        depositos=depositos,
                        form=request.form,
                    )
                if not title:
                    flash("Debe indicar titulo.", "warning")
                    return render_template(
                        "ordenes/mantenimiento_nueva.html",
                        groups=groups,
                        users=users,
                        sedes=sedes,
                        depositos=depositos,
                        form=request.form,
                    )

                now = _now()
                assign_type = "INDIVIDUAL" if assign_mode == "INDIVIDUAL" else "GRUPO"
                group_id_value = None
                user_value = None
                if assign_type == "INDIVIDUAL":
                    if not assigned_user:
                        flash("Debe elegir usuario individual.", "warning")
                        return render_template(
                            "ordenes/mantenimiento_nueva.html",
                            groups=groups,
                            users=users,
                            sedes=sedes,
                            depositos=depositos,
                            form=request.form,
                        )
                    user_value = assigned_user
                else:
                    if assigned_group_id:
                        try:
                            group_id_value = int(assigned_group_id)
                        except Exception:
                            group_id_value = None
                    if group_id_value is None and groups:
                        group_id_value = int(groups[0]["id"])

                cur = con.execute(
                    """
                    INSERT INTO orders(
                        type, sede_id, deposito_id, title, detail, priority, status,
                        assign_type, assigned_user, assigned_group_id, due_date,
                        created_by, created_at, updated_at
                    ) VALUES(
                        'MANTENIMIENTO', ?, ?, ?, ?, ?, 'NUEVA',
                        ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        sede_id,
                        deposito_id or None,
                        title,
                        detail or None,
                        priority if priority in {"BAJA", "MEDIA", "ALTA"} else "MEDIA",
                        assign_type,
                        user_value,
                        group_id_value,
                        due_date or None,
                        username or "sistema",
                        now,
                        now,
                    ),
                )
                order_id = int(cur.lastrowid)
                con.execute(
                    """
                    INSERT INTO order_events(order_id, author, event_type, message, attachment_url, created_at)
                    VALUES(?, ?, 'MENSAJE', ?, NULL, ?)
                    """,
                    (
                        order_id,
                        username or "sistema",
                        f"Orden creada por @{username or 'sistema'}.",
                        now,
                    ),
                )
                con.commit()
                flash("Orden de mantenimiento creada.", "success")
                return redirect(url_for("ordenes_mantenimiento_detalle", order_id=order_id))

            return render_template(
                "ordenes/mantenimiento_nueva.html",
                groups=groups,
                users=users,
                sedes=sedes,
                depositos=depositos,
                form={},
            )
        finally:
            con.close()

    @app.route(
        "/ordenes/mantenimiento/<int:order_id>",
        methods=["GET", "POST"],
        endpoint="ordenes_mantenimiento_detalle",
    )
    def ordenes_mantenimiento_detalle(order_id: int):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))

        username = _current_username()
        role = _current_role()
        is_admin = _is_admin_or_boss(username, role)

        con = _connect()
        try:
            order = con.execute(
                """
                SELECT o.*, COALESCE(wg.name, '') AS group_name
                FROM orders o
                LEFT JOIN work_groups wg ON wg.id = o.assigned_group_id
                WHERE o.id = ? AND o.type = 'MANTENIMIENTO'
                LIMIT 1
                """,
                (order_id,),
            ).fetchone()
            if not order:
                flash("Orden no encontrada.", "warning")
                return redirect(url_for("ordenes_mantenimiento_list"))

            if not _can_view_or_operate(con, order, username, is_admin):
                return redirect(url_for("access_denied"))

            if request.method == "POST":
                accion = (request.form.get("accion") or "").strip().upper()
                comentario = (request.form.get("comentario") or "").strip()
                motivo = (request.form.get("motivo_bloqueo") or "").strip()
                motivo_otro = (request.form.get("motivo_otro") or "").strip()
                now = _now()

                if accion == "CERRAR" and not is_admin:
                    return redirect(url_for("access_denied"))
                if accion != "CERRAR" and not _can_view_or_operate(con, order, username, is_admin):
                    return redirect(url_for("access_denied"))

                event_type = "MENSAJE"
                new_status = None
                msg = comentario
                if accion == "AVANCE":
                    event_type = "AVANCE"
                    new_status = "EN_CURSO"
                    if not msg:
                        msg = "Avance informado."
                elif accion == "BLOQUEADO":
                    if not motivo:
                        flash("Debe indicar motivo de bloqueo.", "warning")
                        return redirect(url_for("ordenes_mantenimiento_detalle", order_id=order_id))
                    motivo_final = motivo_otro if motivo == "OTRO" else motivo
                    if not motivo_final:
                        flash("Debe completar el motivo cuando selecciona Otro.", "warning")
                        return redirect(url_for("ordenes_mantenimiento_detalle", order_id=order_id))
                    event_type = "BLOQUEADO"
                    new_status = "BLOQUEADA"
                    if msg:
                        msg = f"{msg} | Motivo: {motivo_final}"
                    else:
                        msg = f"Bloqueado. Motivo: {motivo_final}"
                elif accion == "FALTA_MATERIAL":
                    event_type = "FALTA_MATERIAL"
                    new_status = "BLOQUEADA"
                    if not msg:
                        msg = "Falta material para continuar."
                    con.execute(
                        """
                        INSERT INTO alerts(alert_type, order_id, severity, assigned_to, status, created_at, resolved_at)
                        VALUES('FALTA_MATERIAL', ?, 'CRIT', 'mcalderari', 'ABIERTA', ?, NULL)
                        """,
                        (order_id, now),
                    )
                    con.execute(
                        """
                        INSERT INTO purchase_requests(
                            order_id, sede_id, deposito_id, requested_by, description, status, created_at, updated_at
                        ) VALUES(?, ?, ?, ?, ?, 'PENDIENTE', ?, ?)
                        """,
                        (
                            order_id,
                            (order["sede_id"] or "").strip(),
                            (order["deposito_id"] or "").strip() or None,
                            username or "sistema",
                            msg,
                            now,
                            now,
                        ),
                    )
                elif accion == "DEJO_MATERIAL":
                    event_type = "DEJO_MATERIAL"
                    if not msg:
                        msg = "Se dejo material/herramienta."
                elif accion == "TERMINADO":
                    event_type = "TERMINADO"
                    new_status = "EN_VERIFICACION"
                    if not msg:
                        msg = "Trabajo marcado como terminado."
                elif accion == "CERRAR":
                    event_type = "MENSAJE"
                    new_status = "CERRADA"
                    if not msg:
                        msg = "Orden cerrada por responsable."
                else:
                    event_type = "MENSAJE"
                    if not msg:
                        msg = "Actualizacion registrada."

                attachment_name = _save_attachment(request.files.get("attachment"))
                attachment_url = (
                    url_for("ordenes_upload", filename=attachment_name) if attachment_name else None
                )

                con.execute(
                    """
                    INSERT INTO order_events(order_id, author, event_type, message, attachment_url, created_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        username or "sistema",
                        event_type,
                        msg,
                        attachment_url,
                        now,
                    ),
                )
                con.execute(
                    """
                    UPDATE orders
                    SET status = COALESCE(?, status),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (new_status, now, order_id),
                )
                con.commit()
                flash("Gestion registrada.", "success")
                return redirect(url_for("ordenes_mantenimiento_detalle", order_id=order_id))

            events = con.execute(
                """
                SELECT id, order_id, author, event_type, message, attachment_url, created_at
                FROM order_events
                WHERE order_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (order_id,),
            ).fetchall()
            return render_template(
                "ordenes/mantenimiento_detalle.html",
                order=order,
                events=events,
                is_admin=is_admin,
            )
        finally:
            con.close()

    app._ordenes_mantenimiento_registered = True
