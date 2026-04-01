import json
from datetime import date, datetime
import unicodedata

from flask import render_template, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash

from . import bp
from . import helpers as nvd_h

# Exponer helpers localmente (sin cambiar logica)
SEDE_ESTADO_VARS = nvd_h.SEDE_ESTADO_VARS
SEDE_ESTADO_LABELS = nvd_h.SEDE_ESTADO_LABELS
NVD_TIPO_SUBTIPOS = nvd_h.NVD_TIPO_SUBTIPOS
NVD_ESTADOS = nvd_h.NVD_ESTADOS
NVD_COFFEE_ESTADOS = nvd_h.NVD_COFFEE_ESTADOS

_table_exists = nvd_h._table_exists
_table_cols = nvd_h._table_cols
_row_value = nvd_h._row_value
_ensure_novedades_catalogo_table = nvd_h._ensure_novedades_catalogo_table
_nvd_tipos_subtipos = nvd_h._nvd_tipos_subtipos
_ensure_novedades_diarias_table = nvd_h._ensure_novedades_diarias_table
_ensure_novedades_diarias_chat_table = nvd_h._ensure_novedades_diarias_chat_table
_ensure_coffee_insumos_table = nvd_h._ensure_coffee_insumos_table
_ensure_coffee_logistica_table = nvd_h._ensure_coffee_logistica_table
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

NVD_GESTION_TIPOS = {
    "pedido de materiales",
    "reclamo / mantenimiento",
    "provision de mobiliario",
    "asignacion de tareas",
}
NVD_TIPO_TAREA = "Asignacion de tareas"
FRANCISCO_USERNAMES = {"fsavio", "francisco", "francisco.savio", "franciscosavio"}
NVD_ADMIN_USERNAMES = {"mcalderari", "msorbello", "msorbllo", "msorbell", "mabatedaga"}
NVD_ADMIN_FULLNAMES = {
    "matias calderari",
    "marcos sorbello",
    "marcos a sorbello",
    "maximiliano abatedaga",
    "maxi abatedaga",
}
NVD_ADMIN_USERNAME_PREFIXES = ("mcalderari", "msorb", "mabatedag")
NVD_CHAT_TEAM_USERNAMES = {"mduran", "cvidaurre", "nguerrero", "mflores"}
NVD_CHAT_TEAM_FULLNAMES = {
    "marcos duran",
    "carlos vidaurre",
    "nestor guerrero",
    "manuel flores",
}
NVD_TAREA_GENERAL_LABEL = "Equipo operativo"
NVD_HERRAMIENTAS_PRESET = [
    "Hidrolavadora",
    "Cortadora de pasto",
    "Desmalezadora",
    "Taladro",
    "Amoladora",
    "Soldadora",
    "Escalera",
    "Pala",
    "Carretilla",
    "Llave francesa",
    "Juego de llaves",
    "Pinza",
    "Martillo",
    "Maza",
    "Destornilladores",
]
NVD_HERRAMIENTA_ACCIONES = {
    "vuelve": "Traer de vuelta",
    "queda": "Queda en sede",
}
NVD_TIPO_COFFEE = "Coffee institucional"
NVD_COFFEE_SUBTIPOS = ["Reunion interna", "Evento", "Capacitacion"]
NVD_COFFEE_INSUMOS_DEFAULT = [
    "Cafe",
    "Azucar",
    "Edulcorante",
    "Vasos",
    "Servilletas",
    "Agua",
    "Otros",
]
NVD_COFFEE_ESTADO_ABIERTOS = {"pendiente", "aprobado", "en preparacion", "enviado"}
NVD_COFFEE_ESTADO_CERRADOS = {"finalizado", "rechazado", "cancelado"}
NVD_LUCIANA_USERNAMES = {"lfernandez", "luciana.fernandez", "lucianafernandez"}
NVD_LUCIANA_FULLNAMES = {"luciana fernandez"}
NVD_COFFEE_TURNO_PERSONAL = {
    "manana": ["Miriam Tejerina", "Micaela Aima"],
    "tarde": ["Yolanda Solis", "Mabel Alejo"],
}
NVD_COFFEE_DECISION_COMPRA = {"pendiente", "comprar", "no_necesario"}


def _norm_ci(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    try:
        raw = unicodedata.normalize("NFD", raw)
        raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    except Exception:
        pass
    return " ".join(raw.split())


def _norm_tool_action(value):
    raw = _norm_ci(value)
    if raw in {"queda", "queda en sede", "dejar en sede", "sede"}:
        return "queda"
    return "vuelve"


def _norm_tool_name(value):
    txt = str(value or "").strip()
    if not txt:
        return ""
    txt = " ".join(txt.split())
    if len(txt) > 80:
        txt = txt[:80]
    return txt


def _parse_tarea_herramientas(raw_value):
    if not raw_value:
        return []
    data = raw_value
    if isinstance(raw_value, str):
        try:
            data = json.loads(raw_value)
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out = []
    seen = set()
    for item in data:
        if isinstance(item, dict):
            nombre = _norm_tool_name(item.get("item") or item.get("nombre") or item.get("herramienta") or "")
            accion = _norm_tool_action(item.get("accion") or item.get("destino") or "")
        else:
            nombre = _norm_tool_name(item)
            accion = "vuelve"
        if not nombre:
            continue
        key = _norm_ci(nombre)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "item": nombre,
            "accion": accion,
            "accion_label": NVD_HERRAMIENTA_ACCIONES.get(accion, NVD_HERRAMIENTA_ACCIONES["vuelve"]),
        })
    return out


def _dump_tarea_herramientas(items):
    safe = _parse_tarea_herramientas(items)
    payload = [{"item": it["item"], "accion": it["accion"]} for it in safe]
    return json.dumps(payload, ensure_ascii=False)


def _herramientas_resumen(items):
    safe = _parse_tarea_herramientas(items)
    if not safe:
        return ""
    return "; ".join([f"{it['item']} ({it['accion_label']})" for it in safe])


def _is_matias_actor(username, full_name):
    norm_user = _norm_ci(username)
    norm_name = _norm_ci(full_name)
    return norm_user in {"mcalderari"} or norm_name == "matias calderari"


def _is_novedades_admin_actor(username, full_name):
    norm_user = _norm_ci(username)
    norm_name = _norm_ci(full_name)
    if norm_user in NVD_ADMIN_USERNAMES or norm_name in NVD_ADMIN_FULLNAMES:
        return True
    if norm_user and any(norm_user.startswith(pref) for pref in NVD_ADMIN_USERNAME_PREFIXES):
        return True
    if "marcos" in norm_name and "sorbello" in norm_name:
        return True
    if "abatedaga" in norm_name and ("maxi" in norm_name or "maximiliano" in norm_name):
        return True
    if "matias" in norm_name and "calderari" in norm_name:
        return True
    return False


def _is_francisco_actor(username, full_name):
    norm_user = _norm_ci(username)
    norm_name = _norm_ci(full_name)
    return norm_user in FRANCISCO_USERNAMES or norm_name == "francisco savio"


def _is_luciana_actor(username, full_name):
    norm_user = _norm_ci(username)
    norm_name = _norm_ci(full_name)
    return norm_user in NVD_LUCIANA_USERNAMES or norm_name in NVD_LUCIANA_FULLNAMES


def _is_coffee_tipo(tipo):
    return _norm_ci(tipo) == _norm_ci(NVD_TIPO_COFFEE)


def _norm_coffee_estado(raw):
    v = _norm_ci(raw)
    if v == "pendiente":
        return "Pendiente"
    if v == "aprobado":
        return "Aprobado"
    if v == "rechazado":
        return "Rechazado"
    if v in {"en preparacion"}:
        return "En preparacion"
    if v == "enviado":
        return "Enviado"
    if v == "finalizado":
        return "Finalizado"
    if v == "cancelado":
        return "Cancelado"
    return "Pendiente"


def _coffee_calc_estado(cantidad_necesaria, stock_disponible):
    try:
        cant = int(cantidad_necesaria or 0)
    except Exception:
        cant = 0
    try:
        stock = int(stock_disponible or 0)
    except Exception:
        stock = 0
    return "hay_stock" if stock >= cant else "falta_comprar"


def _coffee_norm_turno(raw):
    v = _norm_ci(raw)
    if v in {"manana", "m"}:
        return "manana"
    if v in {"tarde", "t"}:
        return "tarde"
    return ""


def _is_novedad_abierta(tipo, estado):
    est = _norm_ci(estado)
    if _is_coffee_tipo(tipo):
        return est in NVD_COFFEE_ESTADO_ABIERTOS
    return est in {"informado", "en revision", "en proceso"}


def _is_novedad_cerrada(tipo, estado):
    est = _norm_ci(estado)
    if _is_coffee_tipo(tipo):
        return est in NVD_COFFEE_ESTADO_CERRADOS
    return est in {"resuelto", "cerrado"}


def _can_edit_coffee_estado(actor, estado_objetivo):
    est = _norm_ci(estado_objetivo)
    is_admin = _can_admin_novedades(actor)
    is_matias = bool(actor.get("is_matias"))
    is_francisco = bool(actor.get("is_francisco"))
    if est in {"aprobado", "rechazado"}:
        return is_admin
    if est in {"enviado", "finalizado"}:
        return is_matias
    if est == "en preparacion":
        return bool(is_admin or is_francisco)
    if est in {"pendiente", "cancelado"}:
        return bool(is_admin or is_matias)
    return False


def _ensure_coffee_special_users(con):
    if not _table_exists(con, "usuarios"):
        return
    try:
        row = con.execute(
            "SELECT 1 FROM usuarios WHERE LOWER(COALESCE(username,''))='lfernandez' LIMIT 1"
        ).fetchone()
        if row:
            return
        cols = _table_cols(con, "usuarios")
        data = {
            "username": "lfernandez",
            "full_name": "Luciana Fernandez",
            "role": "dashboard_solo",
            "password_hash": generate_password_hash("654321"),
            "must_change": 1,
            "activo": 1,
        }
        if "rol" in cols:
            data["rol"] = "operador"
        if "password" in cols:
            data["password"] = "654321"
        fields = [k for k in data.keys() if k in cols]
        if not fields:
            return
        placeholders = ",".join(["?"] * len(fields))
        values = [data[k] for k in fields]
        con.execute(
            f"INSERT INTO usuarios({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        con.commit()
    except Exception:
        pass


def _ensure_coffee_defaults_for_novedad(con, novedad_id):
    _ensure_coffee_insumos_table(con)
    _ensure_coffee_logistica_table(con)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in NVD_COFFEE_INSUMOS_DEFAULT:
        con.execute(
            """
            INSERT OR IGNORE INTO coffee_insumos
                (novedad_id, item, cantidad_necesaria, stock_disponible, estado, decision_compra, recibido, actualizado_en, actualizado_por)
            VALUES (?, ?, 0, 0, 'hay_stock', 'pendiente', 0, ?, 'Sistema')
            """,
            (novedad_id, item, ts),
        )
    con.execute(
        """
        INSERT OR IGNORE INTO coffee_logistica
            (novedad_id, chofer, personal, turno, aprobado, aprobado_por, aprobado_en, actualizado_en, actualizado_por)
        VALUES (?, '', '', '', 0, '', '', ?, 'Sistema')
        """,
        (novedad_id, ts),
    )


def _coffee_read_insumos(con, novedad_id):
    _ensure_coffee_defaults_for_novedad(con, novedad_id)
    rows = con.execute(
        """
        SELECT
            id,
            COALESCE(item,'') AS item,
            COALESCE(cantidad_necesaria,0) AS cantidad_necesaria,
            COALESCE(stock_disponible,0) AS stock_disponible,
            COALESCE(estado,'hay_stock') AS estado,
            COALESCE(decision_compra,'pendiente') AS decision_compra,
            COALESCE(recibido,0) AS recibido,
            COALESCE(actualizado_en,'') AS actualizado_en,
            COALESCE(actualizado_por,'') AS actualizado_por
        FROM coffee_insumos
        WHERE novedad_id=?
        ORDER BY id ASC
        """,
        (novedad_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": int(_row_value(r, "id", 0) or 0),
            "item": (_row_value(r, "item", "") or "").strip(),
            "cantidad_necesaria": int(_row_value(r, "cantidad_necesaria", 0) or 0),
            "stock_disponible": int(_row_value(r, "stock_disponible", 0) or 0),
            "estado": (_row_value(r, "estado", "hay_stock") or "hay_stock").strip(),
            "decision_compra": (_row_value(r, "decision_compra", "pendiente") or "pendiente").strip(),
            "recibido": int(_row_value(r, "recibido", 0) or 0) == 1,
            "actualizado_en": (_row_value(r, "actualizado_en", "") or "").strip(),
            "actualizado_por": (_row_value(r, "actualizado_por", "") or "").strip(),
        })
    return out


def _coffee_read_logistica(con, novedad_id):
    _ensure_coffee_defaults_for_novedad(con, novedad_id)
    row = con.execute(
        """
        SELECT
            id,
            COALESCE(chofer,'') AS chofer,
            COALESCE(personal,'') AS personal,
            COALESCE(turno,'') AS turno,
            COALESCE(aprobado,0) AS aprobado,
            COALESCE(aprobado_por,'') AS aprobado_por,
            COALESCE(aprobado_en,'') AS aprobado_en,
            COALESCE(actualizado_en,'') AS actualizado_en,
            COALESCE(actualizado_por,'') AS actualizado_por
        FROM coffee_logistica
        WHERE novedad_id=?
        LIMIT 1
        """,
        (novedad_id,),
    ).fetchone()
    if not row:
        return {}
    return {
        "id": int(_row_value(row, "id", 0) or 0),
        "chofer": (_row_value(row, "chofer", "") or "").strip(),
        "personal": (_row_value(row, "personal", "") or "").strip(),
        "turno": (_row_value(row, "turno", "") or "").strip(),
        "aprobado": int(_row_value(row, "aprobado", 0) or 0) == 1,
        "aprobado_por": (_row_value(row, "aprobado_por", "") or "").strip(),
        "aprobado_en": (_row_value(row, "aprobado_en", "") or "").strip(),
        "actualizado_en": (_row_value(row, "actualizado_en", "") or "").strip(),
        "actualizado_por": (_row_value(row, "actualizado_por", "") or "").strip(),
    }


def _is_tarea_chat_team_actor(actor):
    if not actor:
        return False
    norm_user = _norm_ci(actor.get("username") or "")
    norm_name = _norm_ci(actor.get("full_name") or actor.get("display") or "")
    return (norm_user in NVD_CHAT_TEAM_USERNAMES) or (norm_name in NVD_CHAT_TEAM_FULLNAMES)


def _is_tarea_general_target(raw_name):
    norm = _norm_ci(raw_name)
    return norm in {
        "",
        "equipo operativo",
        "equipo",
        "general",
        "todos",
        "varios",
        "grupo",
        "cuadrilla",
    }


def _session_actor():
    username = (session.get("username") or "").strip()
    full_name = (session.get("full_name") or "").strip()
    display = full_name or username
    role = (session.get("role") or "").strip().lower()
    is_full = role in {"full", "admin"}
    return {
        "username": username,
        "full_name": full_name,
        "display": display,
        "role": role,
        "is_full": is_full,
        "is_matias": _is_matias_actor(username, full_name),
        "is_novedades_admin": _is_novedades_admin_actor(username, full_name),
        "is_francisco": _is_francisco_actor(username, full_name),
        "is_luciana": _is_luciana_actor(username, full_name),
    }


def _tipo_tiene_gestion(tipo):
    return bool(str(tipo or "").strip())


def _can_admin_novedades(actor):
    if not actor:
        return False
    return bool(actor.get("is_novedades_admin"))


def _actor_can_view_gestion(actor, agente_novedad, agente_tarea="", tipo=""):
    if not actor:
        return False
    if _can_admin_novedades(actor):
        return True
    if _is_coffee_tipo(tipo) and bool(actor.get("is_luciana")):
        return True
    if _norm_ci(tipo) == _norm_ci(NVD_TIPO_TAREA) and _is_tarea_chat_team_actor(actor):
        return True
    # Permitir por coincidencia flexible de nombre/usuario para evitar bloqueos
    # cuando el nombre de tarea no coincide 1:1 con el nombre completo del login.
    if _actor_match_name(actor, agente_novedad) or _actor_match_name(actor, agente_tarea):
        return True
    actor_user = _norm_ci(actor.get("username") or "")
    actor_name = _norm_ci(actor.get("full_name") or actor.get("display") or "")
    agentes_vinculados = {
        _norm_ci(agente_novedad),
        _norm_ci(agente_tarea),
    }
    agentes_vinculados = {a for a in agentes_vinculados if a}
    if not agentes_vinculados:
        return False
    return bool(agentes_vinculados.intersection({actor_user, actor_name}))


def _actor_match_name(actor, raw_name):
    val = _norm_ci(raw_name)
    if not val:
        return False
    ids = [
        _norm_ci(actor.get("username") or ""),
        _norm_ci(actor.get("full_name") or ""),
        _norm_ci(actor.get("display") or ""),
    ]
    ids = [x for x in ids if x]
    if not ids:
        return False

    def _parts(txt):
        clean = _norm_ci(txt).replace(",", " ").replace("-", " ")
        return [p for p in clean.split() if len(p) >= 2]

    val_user = val.split("@", 1)[0]
    val_parts = _parts(val)
    for ident in ids:
        ident_user = ident.split("@", 1)[0]
        if val == ident or val == ident_user or val_user == ident or val_user == ident_user:
            return True
        # Match flexible para nombres con segundo nombre/apellido
        if " " in val and " " in ident:
            if val in ident or ident in val:
                return True
            ident_parts = _parts(ident)
            if len(val_parts) >= 2 and len(ident_parts) >= 2:
                if val_parts[0] in ident_parts and val_parts[-1] in ident_parts:
                    return True
                overlap = len(set(val_parts).intersection(set(ident_parts)))
                if overlap >= 2:
                    return True
    return False


def _is_private_novedad_row(row):
    private_flag = int(_row_value(row, "privado_flag", 0) or 0) == 1
    owner_user = _norm_ci(_row_value(row, "privado_owner_username", "") or "")
    owner_name = _norm_ci(_row_value(row, "privado_owner_nombre", "") or "")
    return private_flag or bool(owner_user or owner_name)


def _actor_can_manage_private_novedad(actor, row):
    if not actor or not row:
        return False
    owner_user = _norm_ci(_row_value(row, "privado_owner_username", "") or "")
    owner_name = _norm_ci(_row_value(row, "privado_owner_nombre", "") or "")
    actor_ids = {
        _norm_ci(actor.get("username") or ""),
        _norm_ci(actor.get("full_name") or ""),
        _norm_ci(actor.get("display") or ""),
    }
    actor_ids = {x for x in actor_ids if x}
    owners = {x for x in {owner_user, owner_name} if x}
    if not owners or not actor_ids:
        return False
    return bool(owners.intersection(actor_ids))


def _actor_can_view_novedad(actor, row):
    if not _is_private_novedad_row(row):
        return True
    return _actor_can_manage_private_novedad(actor, row)


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

    def _fetch_novedad(con, nov_id):
        return con.execute("""
            SELECT
                id,
                COALESCE(fecha,'') AS fecha,
                COALESCE(hora,'') AS hora,
                COALESCE(agente,'') AS agente,
                COALESCE(sede_codigo,'') AS sede_codigo,
                COALESCE(tipo,'') AS tipo,
                COALESCE(subtipo,'') AS subtipo,
                COALESCE(observacion,'') AS observacion,
                COALESCE(estado,'Informado') AS estado,
                COALESCE(tarea_asignada,'') AS tarea_asignada,
                COALESCE(tarea_estado,'') AS tarea_estado,
                COALESCE(tarea_sede_codigo,'') AS tarea_sede_codigo,
                COALESCE(tarea_deposito_codigo,'') AS tarea_deposito_codigo,
                COALESCE(tarea_deposito_nombre,'') AS tarea_deposito_nombre,
                COALESCE(tarea_agente,'') AS tarea_agente,
                COALESCE(tarea_herramientas_json,'') AS tarea_herramientas_json,
                COALESCE(tarea_asignado_por,'') AS tarea_asignado_por,
                COALESCE(tarea_asignado_por_username,'') AS tarea_asignado_por_username,
                COALESCE(tarea_asignado_en,'') AS tarea_asignado_en,
                COALESCE(tarea_actualizado_en,'') AS tarea_actualizado_en,
                COALESCE(coffee_cantidad_personas,0) AS coffee_cantidad_personas,
                COALESCE(coffee_fecha_evento,'') AS coffee_fecha_evento,
                COALESCE(coffee_horario_evento,'') AS coffee_horario_evento,
                COALESCE(coffee_sede_destino,'') AS coffee_sede_destino,
                COALESCE(coffee_logistica_aprobada,0) AS coffee_logistica_aprobada,
                COALESCE((
                    SELECT c.autor
                    FROM novedades_diarias_chat c
                    WHERE c.novedad_id = novedades_diarias.id
                      AND COALESCE(c.es_sistema,0)=0
                    ORDER BY c.id DESC
                    LIMIT 1
                ),'') AS chat_ult_autor,
                COALESCE((
                    SELECT c.autor_username
                    FROM novedades_diarias_chat c
                    WHERE c.novedad_id = novedades_diarias.id
                      AND COALESCE(c.es_sistema,0)=0
                    ORDER BY c.id DESC
                    LIMIT 1
                ),'') AS chat_ult_autor_username,
                COALESCE((
                    SELECT c.creado_en
                    FROM novedades_diarias_chat c
                    WHERE c.novedad_id = novedades_diarias.id
                      AND COALESCE(c.es_sistema,0)=0
                    ORDER BY c.id DESC
                    LIMIT 1
                ),'') AS chat_ult_creado_en,
                COALESCE(privado_flag,0) AS privado_flag,
                COALESCE(privado_owner_username,'') AS privado_owner_username,
                COALESCE(privado_owner_nombre,'') AS privado_owner_nombre
            FROM novedades_diarias
            WHERE id=?
            LIMIT 1
        """, (nov_id,)).fetchone()

    def _depositos_por_sede(con, sede_codigo):
        sede = (sede_codigo or "").strip().upper()
        if not sede or not _table_exists(con, "sedes_depositos"):
            return []
        try:
            rows = con.execute("""
                SELECT
                    UPPER(COALESCE(codigo_local,'')) AS codigo,
                    COALESCE(descripcion,'') AS descripcion,
                    COALESCE(nombre,'') AS nombre,
                    COALESCE(ubicacion,'') AS ubicacion
                FROM sedes_depositos
                WHERE UPPER(COALESCE(codigo_sede,'')) = UPPER(?)
                ORDER BY codigo
            """, (sede,)).fetchall()
        except Exception:
            return []
        out = []
        seen = set()
        for r in rows:
            codigo = (_row_value(r, "codigo", "") or "").strip().upper()
            if not codigo or codigo in seen:
                continue
            seen.add(codigo)
            descripcion = (_row_value(r, "descripcion", "") or "").strip()
            if not descripcion:
                descripcion = (_row_value(r, "nombre", "") or "").strip()
            if not descripcion:
                descripcion = (_row_value(r, "ubicacion", "") or "").strip()
            out.append({
                "codigo": codigo,
                "descripcion": descripcion or codigo,
            })
        return out

    def _alertas_tareas_agente(con, actor):
        if not actor:
            return []
        out = []
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            rows = con.execute("""
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(tipo,'') AS tipo,
                    COALESCE(sede_codigo,'') AS sede_codigo,
                    COALESCE(tarea_asignada,'') AS tarea_asignada,
                    COALESCE(tarea_estado,'') AS tarea_estado,
                    COALESCE(tarea_sede_codigo,'') AS tarea_sede_codigo,
                    COALESCE(tarea_deposito_codigo,'') AS tarea_deposito_codigo,
                    COALESCE(tarea_deposito_nombre,'') AS tarea_deposito_nombre,
                    COALESCE(tarea_agente,'') AS tarea_agente,
                    COALESCE(tarea_herramientas_json,'') AS tarea_herramientas_json,
                    COALESCE(tarea_asignado_por,'') AS tarea_asignado_por,
                    COALESCE(tarea_asignado_por_username,'') AS tarea_asignado_por_username,
                    COALESCE(tarea_asignado_en,'') AS tarea_asignado_en,
                    COALESCE((
                        SELECT c.autor
                        FROM novedades_diarias_chat c
                        WHERE c.novedad_id = novedades_diarias.id
                          AND COALESCE(c.es_sistema,0)=0
                        ORDER BY c.id DESC
                        LIMIT 1
                    ),'') AS chat_ult_autor,
                    COALESCE((
                        SELECT c.autor_username
                        FROM novedades_diarias_chat c
                        WHERE c.novedad_id = novedades_diarias.id
                          AND COALESCE(c.es_sistema,0)=0
                        ORDER BY c.id DESC
                        LIMIT 1
                    ),'') AS chat_ult_autor_username,
                    COALESCE(privado_flag,0) AS privado_flag,
                    COALESCE(privado_owner_username,'') AS privado_owner_username,
                    COALESCE(privado_owner_nombre,'') AS privado_owner_nombre
                FROM novedades_diarias
                WHERE TRIM(COALESCE(tarea_asignada,'')) <> ''
                ORDER BY date(COALESCE(tarea_asignado_en, actualizado_en, fecha)) DESC, id DESC
                LIMIT 500
            """).fetchall()
            actor_user = _norm_ci(actor.get("username") or "")
            for r in rows:
                if not _actor_can_view_novedad(actor, r):
                    continue
                tarea_agente = (_row_value(r, "tarea_agente", "") or "").strip()
                is_general = _is_tarea_general_target(tarea_agente)
                if not _actor_match_name(actor, tarea_agente):
                    if not (is_general and _is_tarea_chat_team_actor(actor)):
                        continue
                if is_general:
                    tarea_agente = NVD_TAREA_GENERAL_LABEL
                if not tarea_agente:
                    continue
                by_user = _row_value(r, "tarea_asignado_por_username", "") or ""
                by_name = _row_value(r, "tarea_asignado_por", "") or ""
                by_admin = _is_novedades_admin_actor(by_user, by_name)
                by_self_private = (_is_private_novedad_row(r) and _actor_can_manage_private_novedad(actor, r))
                if not by_admin and not by_self_private:
                    continue
                tarea_estado = (_row_value(r, "tarea_estado", "") or "").strip() or "Pendiente"
                if _norm_ci(tarea_estado) in {"completada", "resuelto", "cerrado"}:
                    continue
                base_item = {
                    "novedad_id": int(_row_value(r, "id", 0) or 0),
                    "fecha": (_row_value(r, "fecha", "") or "").strip(),
                    "tipo": (_row_value(r, "tipo", "") or "").strip(),
                    "tarea": (_row_value(r, "tarea_asignada", "") or "").strip(),
                    "estado": tarea_estado,
                    "sede_codigo": ((_row_value(r, "tarea_sede_codigo", "") or "").strip().upper() or (_row_value(r, "sede_codigo", "") or "").strip().upper()),
                    "deposito_codigo": (_row_value(r, "tarea_deposito_codigo", "") or "").strip().upper(),
                    "deposito_nombre": (_row_value(r, "tarea_deposito_nombre", "") or "").strip(),
                    "asignado_en": (_row_value(r, "tarea_asignado_en", "") or "").strip(),
                }
                out.append({
                    **base_item,
                    "alerta_tipo": "tarea",
                })
                chat_ult_autor = (_row_value(r, "chat_ult_autor", "") or "").strip()
                chat_ult_autor_username = (_row_value(r, "chat_ult_autor_username", "") or "").strip()
                es_chat_propio = False
                if chat_ult_autor_username and _norm_ci(chat_ult_autor_username) == actor_user:
                    es_chat_propio = True
                elif chat_ult_autor and _actor_match_name(actor, chat_ult_autor):
                    es_chat_propio = True
                if (chat_ult_autor or chat_ult_autor_username) and not es_chat_propio:
                    out.append({
                        **base_item,
                        "alerta_tipo": "respuesta",
                    })
                if len(out) >= 20:
                    break
        except Exception:
            return []
        return out

    def _serialize_novedad(row, actor):
        tipo = (_row_value(row, "tipo", "") or "").strip()
        is_coffee = _is_coffee_tipo(tipo)
        agente = (_row_value(row, "agente", "") or "").strip()
        tarea_agente = (_row_value(row, "tarea_agente", "") or "").strip()
        tarea_general = _is_tarea_general_target(tarea_agente)
        tarea_herramientas = _parse_tarea_herramientas(_row_value(row, "tarea_herramientas_json", "") or "")
        tarea_herramientas_resumen = _herramientas_resumen(tarea_herramientas)
        estado_raw = _row_value(row, "estado", "Informado") or "Informado"
        estado_norm = _norm_coffee_estado(estado_raw) if is_coffee else _norm_nvd_estado(estado_raw)
        es_privada = _is_private_novedad_row(row)
        es_duenio_privada = _actor_can_manage_private_novedad(actor, row)
        puede_ver_novedad = _actor_can_view_novedad(actor, row)
        gestion_habilitada = _tipo_tiene_gestion(tipo)
        puede_ver_gestion = (
            bool(puede_ver_novedad)
            and gestion_habilitada
            and _actor_can_view_gestion(actor, agente, tarea_agente, tipo)
        )
        es_matias = bool(actor.get("is_matias"))
        is_team_actor = _is_tarea_chat_team_actor(actor)
        can_autoassign = bool(
            puede_ver_novedad
            and not es_privada
            and _norm_ci(tipo) == _norm_ci(NVD_TIPO_TAREA)
            and is_team_actor
            and bool((_row_value(row, "tarea_asignada", "") or "").strip())
            and tarea_general
        )
        puede_gestionar_tarea = bool(
            puede_ver_novedad and (_can_admin_novedades(actor) or (es_privada and es_duenio_privada))
        )
        if is_coffee and _norm_ci(estado_norm) != "aprobado":
            puede_gestionar_tarea = False
            can_autoassign = False
        chat_ult_autor = (_row_value(row, "chat_ult_autor", "") or "").strip()
        chat_ult_autor_username = (_row_value(row, "chat_ult_autor_username", "") or "").strip()
        chat_ult_creado_en = (_row_value(row, "chat_ult_creado_en", "") or "").strip()
        gestion_turno = "sin_mensajes"
        gestion_turno_label = "Sin mensajes"
        if chat_ult_autor or chat_ult_autor_username:
            es_propio_ultimo = False
            actor_user = _norm_ci(actor.get("username") or "")
            if chat_ult_autor_username and _norm_ci(chat_ult_autor_username) == actor_user:
                es_propio_ultimo = True
            elif chat_ult_autor and _actor_match_name(actor, chat_ult_autor):
                es_propio_ultimo = True
            if es_propio_ultimo:
                gestion_turno = "esperando"
                gestion_turno_label = "Esperando respuesta"
            else:
                gestion_turno = "tu_respuesta"
                gestion_turno_label = "Tu respuesta"
        can_estado_coffee = bool(
            is_coffee
            and (bool(actor.get("is_matias")) or bool(actor.get("is_francisco")) or _can_admin_novedades(actor))
        )
        can_insumos_edit = bool(
            is_coffee and (bool(actor.get("is_francisco")) or bool(actor.get("is_matias")) or _can_admin_novedades(actor))
        )
        can_compra_decision = bool(
            is_coffee and (bool(actor.get("is_luciana")) or bool(actor.get("is_matias")) or _can_admin_novedades(actor))
        )
        can_mark_recibido = bool(is_coffee and bool(actor.get("is_francisco")))
        can_logistica_edit = bool(
            is_coffee and (bool(actor.get("is_francisco")) or bool(actor.get("is_matias")) or _can_admin_novedades(actor))
        )
        can_logistica_approve = bool(is_coffee and bool(actor.get("is_matias")))
        return {
            "id": int(_row_value(row, "id", 0) or 0),
            "fecha": (_row_value(row, "fecha", "") or "").strip(),
            "hora": (_row_value(row, "hora", "") or "").strip(),
            "agente": agente,
            "sede_codigo": (_row_value(row, "sede_codigo", "") or "").strip().upper(),
            "tipo": tipo,
            "es_coffee": is_coffee,
            "subtipo": (_row_value(row, "subtipo", "") or "").strip(),
            "observacion": (_row_value(row, "observacion", "") or "").strip(),
            "estado": estado_norm,
            "estados_disponibles": (list(NVD_COFFEE_ESTADOS) if is_coffee else list(NVD_ESTADOS)),
            "coffee_cantidad_personas": int(_row_value(row, "coffee_cantidad_personas", 0) or 0),
            "coffee_fecha_evento": (_row_value(row, "coffee_fecha_evento", "") or "").strip(),
            "coffee_horario_evento": (_row_value(row, "coffee_horario_evento", "") or "").strip(),
            "coffee_sede_destino": (_row_value(row, "coffee_sede_destino", "") or "").strip(),
            "coffee_logistica_aprobada": int(_row_value(row, "coffee_logistica_aprobada", 0) or 0) == 1,
            "tarea_asignada": (_row_value(row, "tarea_asignada", "") or "").strip(),
            "tarea_estado": (_row_value(row, "tarea_estado", "") or "").strip(),
            "tarea_sede_codigo": (_row_value(row, "tarea_sede_codigo", "") or "").strip().upper(),
            "tarea_deposito_codigo": (_row_value(row, "tarea_deposito_codigo", "") or "").strip().upper(),
            "tarea_deposito_nombre": (_row_value(row, "tarea_deposito_nombre", "") or "").strip(),
            "tarea_agente": (NVD_TAREA_GENERAL_LABEL if tarea_general else tarea_agente),
            "tarea_general": tarea_general,
            "tarea_herramientas": tarea_herramientas,
            "tarea_herramientas_resumen": tarea_herramientas_resumen,
            "tarea_asignado_por": (_row_value(row, "tarea_asignado_por", "") or "").strip(),
            "tarea_asignado_por_username": (_row_value(row, "tarea_asignado_por_username", "") or "").strip(),
            "tarea_asignado_en": (_row_value(row, "tarea_asignado_en", "") or "").strip(),
            "tarea_actualizado_en": (_row_value(row, "tarea_actualizado_en", "") or "").strip(),
            "chat_ult_autor": chat_ult_autor,
            "chat_ult_autor_username": chat_ult_autor_username,
            "chat_ult_creado_en": chat_ult_creado_en,
            "gestion_turno": gestion_turno,
            "gestion_turno_label": gestion_turno_label,
            "es_privada": es_privada,
            "privado_owner_username": (_row_value(row, "privado_owner_username", "") or "").strip(),
            "privado_owner_nombre": (_row_value(row, "privado_owner_nombre", "") or "").strip(),
            "gestion_habilitada": gestion_habilitada,
            "puede_ver_gestion": puede_ver_gestion,
            "puede_cambiar_estado": (can_estado_coffee if is_coffee else (puede_gestionar_tarea if gestion_habilitada else True)),
            "puede_cerrar": (can_estado_coffee if is_coffee else (puede_gestionar_tarea if gestion_habilitada else True)),
            "puede_asignar_tarea": (puede_gestionar_tarea if gestion_habilitada else False),
            "puede_autoasignar": can_autoassign,
            "puede_editar_coffee_insumos": can_insumos_edit,
            "puede_decidir_compra": can_compra_decision,
            "puede_marcar_recibido": can_mark_recibido,
            "puede_editar_logistica": can_logistica_edit,
            "puede_aprobar_logistica": can_logistica_approve,
        }

    def _novedades_resumen_visible(con, fecha_iso, actor):
        out = {"total": 0, "informado": 0, "en_proceso": 0, "resuelto": 0}
        try:
            rows = con.execute("""
                SELECT
                    COALESCE(tipo,'') AS tipo,
                    LOWER(COALESCE(estado,'informado')) AS estado,
                    COALESCE(privado_flag,0) AS privado_flag,
                    COALESCE(privado_owner_username,'') AS privado_owner_username,
                    COALESCE(privado_owner_nombre,'') AS privado_owner_nombre
                FROM novedades_diarias
                WHERE date(fecha) = date(?)
            """, (fecha_iso,)).fetchall()
            for r in rows:
                if not _actor_can_view_novedad(actor, r):
                    continue
                est = (_row_value(r, "estado", "") or "").strip()
                est_norm = _norm_ci(est)
                tipo = (_row_value(r, "tipo", "") or "").strip()
                out["total"] += 1
                if _is_coffee_tipo(tipo):
                    if est_norm in {"pendiente"}:
                        out["informado"] += 1
                    elif est_norm in {"aprobado", "en preparacion", "enviado"}:
                        out["en_proceso"] += 1
                    elif est_norm in {"finalizado", "rechazado", "cancelado"}:
                        out["resuelto"] += 1
                    continue
                if est_norm in {"informado"}:
                    out["informado"] += 1
                elif est_norm in {"en revision", "en proceso", "proceso"}:
                    out["en_proceso"] += 1
                elif est_norm in {"resuelto", "cerrado"}:
                    out["resuelto"] += 1
        except Exception:
            pass
        return out

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
        actor = _session_actor()

        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_catalogo_table(con)
            _ensure_coffee_insumos_table(con)
            _ensure_coffee_logistica_table(con)
            _ensure_coffee_special_users(con)
            sedes = _dashboard_sedes_opts(con)
            agentes = _dashboard_agentes_opts(con)
            tipos_subtipos = _nvd_tipos_subtipos(con)
            vehs = _dashboard_vehiculos_simple(con, fecha)
            resumen = _novedades_resumen_visible(con, fecha, actor)
            alertas_tareas_asignadas = _alertas_tareas_agente(con, actor)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()

        base = _dashboard_operativo_data()
        alertas = _dashboard_alertas_criticas(base)

        user_name = (actor.get("display") or "").strip()
        if user_name and user_name.lower() not in {a.lower() for a in agentes}:
            agentes.insert(0, user_name)

        return jsonify({
            "ok": True,
            "fecha": fecha,
            "agente_actual": user_name,
            "usuario_actual": {
                "username": actor.get("username") or "",
                "full_name": actor.get("full_name") or "",
                "role": actor.get("role") or "",
                "is_full": bool(actor.get("is_full")),
                "is_matias": bool(actor.get("is_matias")),
                "is_novedades_admin": bool(actor.get("is_novedades_admin")),
                "is_francisco": bool(actor.get("is_francisco")),
                "is_luciana": bool(actor.get("is_luciana")),
            },
            "is_full": bool(actor.get("is_full")),
            "is_matias": bool(actor.get("is_matias")),
            "is_novedades_admin": bool(actor.get("is_novedades_admin")),
            "is_francisco": bool(actor.get("is_francisco")),
            "is_luciana": bool(actor.get("is_luciana")),
            "puede_editar_agente": _can_admin_novedades(actor),
            "sedes": sedes,
            "agentes": agentes,
            "tipos_subtipos": tipos_subtipos,
            "estados": list(NVD_ESTADOS),
            "vehiculos": vehs,
            "alertas": alertas,
            "alertas_tareas_asignadas": alertas_tareas_asignadas,
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
            _ensure_novedades_diarias_chat_table(con)
            actor = _session_actor()
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
                    COALESCE(estado,'Informado') AS estado,
                    COALESCE(tarea_asignada,'') AS tarea_asignada,
                    COALESCE(tarea_estado,'') AS tarea_estado,
                    COALESCE(tarea_sede_codigo,'') AS tarea_sede_codigo,
                    COALESCE(tarea_deposito_codigo,'') AS tarea_deposito_codigo,
                    COALESCE(tarea_deposito_nombre,'') AS tarea_deposito_nombre,
                    COALESCE(tarea_agente,'') AS tarea_agente,
                    COALESCE(tarea_herramientas_json,'') AS tarea_herramientas_json,
                    COALESCE(tarea_asignado_por,'') AS tarea_asignado_por,
                    COALESCE(tarea_asignado_por_username,'') AS tarea_asignado_por_username,
                    COALESCE(tarea_asignado_en,'') AS tarea_asignado_en,
                    COALESCE(tarea_actualizado_en,'') AS tarea_actualizado_en,
                    COALESCE((
                        SELECT c.autor
                        FROM novedades_diarias_chat c
                        WHERE c.novedad_id = novedades_diarias.id
                          AND COALESCE(c.es_sistema,0)=0
                        ORDER BY c.id DESC
                        LIMIT 1
                    ),'') AS chat_ult_autor,
                    COALESCE((
                        SELECT c.autor_username
                        FROM novedades_diarias_chat c
                        WHERE c.novedad_id = novedades_diarias.id
                          AND COALESCE(c.es_sistema,0)=0
                        ORDER BY c.id DESC
                        LIMIT 1
                    ),'') AS chat_ult_autor_username,
                    COALESCE((
                        SELECT c.creado_en
                        FROM novedades_diarias_chat c
                        WHERE c.novedad_id = novedades_diarias.id
                          AND COALESCE(c.es_sistema,0)=0
                        ORDER BY c.id DESC
                        LIMIT 1
                    ),'') AS chat_ult_creado_en,
                    COALESCE(privado_flag,0) AS privado_flag,
                    COALESCE(privado_owner_username,'') AS privado_owner_username,
                    COALESCE(privado_owner_nombre,'') AS privado_owner_nombre
                FROM novedades_diarias
                WHERE (
                        date(fecha) = date(?)
                        AND LOWER(COALESCE(estado,'')) IN ('informado', 'en revision', 'en proceso', 'pendiente', 'aprobado', 'en preparacion', 'en preparación', 'enviado')
                    )
                   OR (
                        date(fecha) < date(?)
                        AND LOWER(COALESCE(estado,'')) IN ('informado', 'en revision', 'en proceso', 'pendiente', 'aprobado', 'en preparacion', 'en preparación', 'enviado')
                    )
                   OR LOWER(COALESCE(estado,'')) IN ('resuelto', 'cerrado', 'finalizado', 'cancelado', 'rechazado')
                ORDER BY date(fecha) DESC, COALESCE(hora,'') DESC, id DESC
                LIMIT 800
            """, (fecha, fecha)).fetchall()
            base_items = []
            for r in rows:
                if not _actor_can_view_novedad(actor, r):
                    continue
                base_items.append(_serialize_novedad(r, actor))
            pendientes_dia = []
            pendientes_acumulados = []
            resueltos_informados = []
            tareas_asignadas = []
            solicitudes_recibidas = []
            for it in base_items:
                es_pendiente = _is_novedad_abierta(it.get("tipo") or "", it.get("estado") or "")
                if es_pendiente:
                    if (it.get("fecha") or "") == fecha:
                        pendientes_dia.append(it)
                    else:
                        pendientes_acumulados.append(it)
                else:
                    resueltos_informados.append(it)
                tipo_norm = _norm_ci(it.get("tipo") or "")
                tiene_tarea = bool((it.get("tarea_asignada") or "").strip())
                by_admin = _is_novedades_admin_actor(
                    it.get("tarea_asignado_por_username") or "",
                    it.get("tarea_asignado_por") or "",
                )
                es_tarea = (tipo_norm == _norm_ci(NVD_TIPO_TAREA)) or (tiene_tarea and by_admin)
                if not es_pendiente:
                    continue
                if es_tarea:
                    if not tiene_tarea:
                        continue
                    agente_obj = (it.get("tarea_agente") or it.get("agente") or "").strip()
                    is_general = _is_tarea_general_target(agente_obj)
                    if _can_admin_novedades(actor) or _actor_match_name(actor, agente_obj) or (is_general and _is_tarea_chat_team_actor(actor)):
                        if is_general:
                            it = dict(it)
                            it["tarea_agente"] = NVD_TAREA_GENERAL_LABEL
                        tareas_asignadas.append(it)
                else:
                    if _can_admin_novedades(actor) or _actor_match_name(actor, it.get("agente") or ""):
                        solicitudes_recibidas.append(it)
            resumen = _novedades_resumen_visible(con, fecha, actor)
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
            "tareas_asignadas": tareas_asignadas,
            "solicitudes_recibidas": solicitudes_recibidas,
            "resumen": resumen,
        })

    @bp.route("/api/dashboard/novedades_diarias_historial", methods=["GET"], endpoint="api_dashboard_novedades_diarias_historial")
    def api_dashboard_novedades_diarias_historial():
        desde = (request.args.get("desde") or "").strip()
        hasta = (request.args.get("hasta") or "").strip()
        limit = int(request.args.get("limit") or 100)
        limit = max(1, min(limit, 500))
        actor = _session_actor()
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
                    COALESCE(estado,'Informado') AS estado,
                    COALESCE(privado_flag,0) AS privado_flag,
                    COALESCE(privado_owner_username,'') AS privado_owner_username,
                    COALESCE(privado_owner_nombre,'') AS privado_owner_nombre
                FROM novedades_diarias
                WHERE 1=1
                  AND LOWER(COALESCE(estado,'')) IN ('resuelto', 'cerrado', 'finalizado', 'cancelado', 'rechazado')
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
            items = []
            for r in rows:
                if not _actor_can_view_novedad(actor, r):
                    continue
                items.append({
                    "id": int(_row_value(r, "id", 0) or 0),
                    "fecha": (_row_value(r, "fecha", "") or "").strip(),
                    "hora": (_row_value(r, "hora", "") or "").strip(),
                    "agente": (_row_value(r, "agente", "") or "").strip(),
                    "sede_codigo": (_row_value(r, "sede_codigo", "") or "").strip().upper(),
                    "tipo": (_row_value(r, "tipo", "") or "").strip(),
                    "subtipo": (_row_value(r, "subtipo", "") or "").strip(),
                    "observacion": (_row_value(r, "observacion", "") or "").strip(),
                    "estado": (
                        _norm_coffee_estado(_row_value(r, "estado", "Pendiente") or "Pendiente")
                        if _is_coffee_tipo(_row_value(r, "tipo", "") or "")
                        else _norm_nvd_estado(_row_value(r, "estado", "Informado") or "Informado")
                    ),
                })
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
        coffee_cantidad_personas_raw = payload.get("cantidad_personas")
        coffee_fecha_evento = (payload.get("fecha_evento") or "").strip()
        coffee_horario_evento = (payload.get("horario_evento") or "").strip()
        coffee_sede_destino = (payload.get("sede_destino") or "").strip().upper()
        actor = _session_actor()
        if len(observacion) > 240:
            observacion = observacion[:240]
        try:
            coffee_cantidad_personas = int(coffee_cantidad_personas_raw or 0)
        except Exception:
            coffee_cantidad_personas = 0
        coffee_cantidad_personas = max(0, coffee_cantidad_personas)
        if len(coffee_horario_evento) > 40:
            coffee_horario_evento = coffee_horario_evento[:40]

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
            _ensure_novedades_diarias_chat_table(con)
            _ensure_coffee_insumos_table(con)
            _ensure_coffee_logistica_table(con)
            _ensure_coffee_special_users(con)
            tipos_subtipos = _nvd_tipos_subtipos(con)
            if tipo not in tipos_subtipos:
                con.close()
                return jsonify({"ok": False, "error": "Tipo invalido"}), 400
            if not subtipo:
                subtipo = (tipos_subtipos.get(tipo) or ["General"])[0]
            if subtipo not in (tipos_subtipos.get(tipo) or []):
                con.close()
                return jsonify({"ok": False, "error": "Subtipo invalido para el tipo elegido"}), 400
            is_coffee = _is_coffee_tipo(tipo)
            if is_coffee:
                if subtipo not in NVD_COFFEE_SUBTIPOS:
                    con.close()
                    return jsonify({"ok": False, "error": "Subtipo invalido para Coffee institucional"}), 400
                if coffee_cantidad_personas <= 0:
                    con.close()
                    return jsonify({"ok": False, "error": "Cantidad de personas obligatoria para Coffee"}), 400
                if not coffee_fecha_evento:
                    con.close()
                    return jsonify({"ok": False, "error": "Fecha del evento obligatoria para Coffee"}), 400
                try:
                    datetime.strptime(coffee_fecha_evento, "%Y-%m-%d")
                except Exception:
                    con.close()
                    return jsonify({"ok": False, "error": "Fecha del evento invalida"}), 400
                if not coffee_horario_evento:
                    con.close()
                    return jsonify({"ok": False, "error": "Horario del evento obligatorio para Coffee"}), 400
                if not coffee_sede_destino:
                    coffee_sede_destino = sede_codigo
                if not coffee_sede_destino:
                    con.close()
                    return jsonify({"ok": False, "error": "Sede destino obligatoria para Coffee"}), 400
            else:
                coffee_cantidad_personas = 0
                coffee_fecha_evento = ""
                coffee_horario_evento = ""
                coffee_sede_destino = ""
            existing = None
            if nov_id > 0:
                existing = _fetch_novedad(con, nov_id)
                if not existing:
                    con.close()
                    return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
                if not _actor_can_view_novedad(actor, existing):
                    con.close()
                    return jsonify({"ok": False, "error": "No autorizado para editar esta novedad"}), 403
                estado_prev = _row_value(existing, "estado", "Informado") or "Informado"
                estado = (_norm_coffee_estado(estado_prev) if is_coffee else _norm_nvd_estado(estado_prev))
            else:
                estado = "Pendiente" if is_coffee else "Informado"

            if not _can_admin_novedades(actor):
                if nov_id > 0:
                    agente = (_row_value(existing, "agente", "") or "").strip() or (actor.get("display") or "").strip()
                else:
                    agente = (actor.get("display") or "").strip()
            elif not agente:
                agente = (actor.get("display") or "").strip()

            if not agente:
                con.close()
                return jsonify({"ok": False, "error": "Agente obligatorio"}), 400

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
                        coffee_cantidad_personas=?,
                        coffee_fecha_evento=?,
                        coffee_horario_evento=?,
                        coffee_sede_destino=?,
                        actualizado_en=?
                    WHERE id=?
                """, (
                    fecha,
                    agente,
                    sede_codigo,
                    tipo,
                    subtipo,
                    observacion,
                    estado,
                    coffee_cantidad_personas,
                    coffee_fecha_evento,
                    coffee_horario_evento,
                    coffee_sede_destino,
                    ts,
                    nov_id,
                ))
                rid = nov_id
            else:
                cur = con.execute("""
                    INSERT INTO novedades_diarias
                        (fecha, hora, agente, sede_codigo, tipo, subtipo, observacion, estado,
                         coffee_cantidad_personas, coffee_fecha_evento, coffee_horario_evento, coffee_sede_destino,
                         creado_en, actualizado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fecha,
                    hora,
                    agente,
                    sede_codigo,
                    tipo,
                    subtipo,
                    observacion,
                    estado,
                    coffee_cantidad_personas,
                    coffee_fecha_evento,
                    coffee_horario_evento,
                    coffee_sede_destino,
                    ts,
                    ts,
                ))
                rid = int(cur.lastrowid or 0)
            if is_coffee and rid > 0:
                _ensure_coffee_defaults_for_novedad(con, rid)
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "id": rid})

    @bp.route("/api/dashboard/tareas_asignadas_save", methods=["POST"], endpoint="api_dashboard_tareas_asignadas_save")
    def api_dashboard_tareas_asignadas_save():
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        can_admin_novedades = _can_admin_novedades(actor)
        is_francisco = bool(actor.get("is_francisco"))
        if not can_admin_novedades and not is_francisco:
            return jsonify({"ok": False, "error": "No autorizado para crear tareas asignadas"}), 403
        fecha = (payload.get("fecha") or "").strip() or _safe_today()
        agente = (payload.get("agente") or payload.get("agente_asignado") or "").strip()
        agente_norm = _norm_ci(agente)
        sede_codigo = (payload.get("sede_codigo") or "").strip().upper()
        deposito_codigo = (payload.get("deposito_codigo") or "").strip().upper()
        deposito_nombre = (payload.get("deposito_nombre") or "").strip()
        tarea = (payload.get("tarea") or payload.get("tarea_asignada") or "").strip()
        privado_flag = 1 if (is_francisco and not can_admin_novedades) else 0
        privado_owner_username = (actor.get("username") or "").strip() if privado_flag else ""
        privado_owner_nombre = (actor.get("display") or "").strip() if privado_flag else ""
        if privado_flag:
            agente = (actor.get("display") or actor.get("full_name") or actor.get("username") or "").strip()
        elif agente_norm in {"__equipo__", "equipo operativo", "equipo", "general", "todos"}:
            agente = NVD_TAREA_GENERAL_LABEL
        if len(tarea) > 280:
            tarea = tarea[:280]
        if not agente:
            return jsonify({"ok": False, "error": "Selecciona agente asignado"}), 400
        if not sede_codigo:
            return jsonify({"ok": False, "error": "Selecciona sede"}), 400
        if not tarea:
            return jsonify({"ok": False, "error": "Escribe la tarea"}), 400
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
            _ensure_novedades_diarias_chat_table(con)
            deps = _depositos_por_sede(con, sede_codigo)
            if deps:
                if not deposito_codigo:
                    con.close()
                    return jsonify({"ok": False, "error": "Selecciona deposito/local"}), 400
                dep_map = {str(d.get("codigo") or "").strip().upper(): str(d.get("descripcion") or "").strip() for d in deps}
                if deposito_codigo not in dep_map:
                    con.close()
                    return jsonify({"ok": False, "error": "Deposito invalido para la sede"}), 400
                if not deposito_nombre:
                    deposito_nombre = dep_map.get(deposito_codigo, "")
            else:
                deposito_codigo = ""
                deposito_nombre = ""
            cur = con.execute("""
                INSERT INTO novedades_diarias
                    (fecha, hora, agente, sede_codigo, tipo, subtipo, observacion, estado,
                     tarea_asignada, tarea_estado, tarea_sede_codigo, tarea_deposito_codigo, tarea_deposito_nombre,
                     tarea_agente, tarea_herramientas_json, tarea_asignado_por, tarea_asignado_por_username, tarea_asignado_en, tarea_actualizado_en,
                     privado_flag, privado_owner_username, privado_owner_nombre, creado_en, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Informado',
                        ?, 'Pendiente', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fecha,
                hora,
                agente,
                sede_codigo,
                NVD_TIPO_TAREA,
                ("Recordatorio personal" if privado_flag else (deposito_codigo or "General")),
                tarea,
                tarea,
                sede_codigo,
                deposito_codigo,
                deposito_nombre,
                agente,
                "[]",
                actor.get("display") or ("Matias" if can_admin_novedades else "Sistema"),
                actor.get("username") or "",
                ts,
                ts,
                privado_flag,
                privado_owner_username,
                privado_owner_nombre,
                ts,
                ts,
            ))
            rid = int(cur.lastrowid or 0)
            msg_dep = deposito_codigo if deposito_codigo else "-"
            actor_name = (actor.get("display") or actor.get("username") or "Sistema").strip() or "Sistema"
            if privado_flag:
                msg = f"{actor_name} cargo recordatorio privado: {tarea} (Sede {sede_codigo} / Deposito {msg_dep} / Estado Pendiente)."
            else:
                msg = f"{actor_name} asigno tarea a {agente}: {tarea} (Sede {sede_codigo} / Deposito {msg_dep} / Estado Pendiente)."
            con.execute("""
                INSERT INTO novedades_diarias_chat
                    (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                VALUES (?, 'Sistema', ?, ?, 1, ?)
            """, (rid, actor.get("username") or "", msg, ts))
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
        estado_raw = payload.get("estado") or "Informado"
        if nov_id <= 0:
            return jsonify({"ok": False, "error": "ID invalido"}), 400
        actor = _session_actor()
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            _ensure_coffee_logistica_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            if not _actor_can_view_novedad(actor, row):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para ver esta novedad"}), 403
            tipo_row = _row_value(row, "tipo", "") or ""
            is_coffee = _is_coffee_tipo(tipo_row)
            estado = _norm_coffee_estado(estado_raw) if is_coffee else _norm_nvd_estado(estado_raw)
            gestion_habilitada = _tipo_tiene_gestion(_row_value(row, "tipo", "") or "")
            can_manage_private = _actor_can_manage_private_novedad(actor, row)
            if is_coffee:
                if not _can_edit_coffee_estado(actor, estado):
                    con.close()
                    return jsonify({"ok": False, "error": "No autorizado para ese estado Coffee"}), 403
                if _norm_ci(estado) in {"enviado", "finalizado"}:
                    log_row = con.execute(
                        "SELECT COALESCE(aprobado,0) AS aprobado FROM coffee_logistica WHERE novedad_id=? LIMIT 1",
                        (nov_id,),
                    ).fetchone()
                    aprobado = int(_row_value(log_row, "aprobado", 0) or 0) == 1
                    if not aprobado:
                        con.close()
                        return jsonify({"ok": False, "error": "Primero Matias debe aprobar la logistica"}), 400
            elif gestion_habilitada and not (_can_admin_novedades(actor) or can_manage_private):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para cambiar estado en esta novedad"}), 403
            estado_prev_raw = _row_value(row, "estado", "Informado") or "Informado"
            estado_prev = _norm_coffee_estado(estado_prev_raw) if is_coffee else _norm_nvd_estado(estado_prev_raw)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                UPDATE novedades_diarias
                SET estado=?, actualizado_en=?
                WHERE id=?
            """, (estado, ts, nov_id))
            if is_coffee and estado == "Aprobado":
                sede_destino = (_row_value(row, "coffee_sede_destino", "") or "").strip().upper()
                if not sede_destino:
                    sede_destino = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                tarea_actual = (_row_value(row, "tarea_asignada", "") or "").strip()
                if not tarea_actual:
                    subtipo = (_row_value(row, "subtipo", "") or "").strip() or "General"
                    cant = int(_row_value(row, "coffee_cantidad_personas", 0) or 0)
                    tarea_actual = f"Coffee institucional - {subtipo} - {cant} personas"
                con.execute("""
                    UPDATE novedades_diarias
                    SET tarea_asignada=?,
                        tarea_estado='Pendiente',
                        tarea_sede_codigo=?,
                        tarea_deposito_codigo='',
                        tarea_deposito_nombre='',
                        tarea_agente='Francisco Savio',
                        tarea_asignado_por=?,
                        tarea_asignado_por_username=?,
                        tarea_asignado_en=?,
                        tarea_actualizado_en=?,
                        actualizado_en=?
                    WHERE id=?
                """, (
                    tarea_actual,
                    sede_destino,
                    actor.get("display") or actor.get("username") or "Sistema",
                    actor.get("username") or "",
                    ts,
                    ts,
                    ts,
                    nov_id,
                ))
            if gestion_habilitada and estado_prev != estado:
                actor_name = (actor.get("display") or "Sistema").strip() or "Sistema"
                con.execute("""
                    INSERT INTO novedades_diarias_chat
                        (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                    VALUES (?, 'Sistema', ?, ?, 1, ?)
                """, (nov_id, actor.get("username") or "", f"{actor_name} cambio el estado a '{estado}'.", ts))
                if is_coffee and estado == "Aprobado":
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        "Asignacion automatica Coffee: tarea derivada a Francisco Savio.",
                        ts,
                    ))
                if is_coffee and estado == "Enviado":
                    sede_dest = (_row_value(row, "coffee_sede_destino", "") or "").strip().upper()
                    if not sede_dest:
                        sede_dest = (_row_value(row, "sede_codigo", "") or "").strip().upper() or "-"
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        f"Coffee enviado a sede {sede_dest}.",
                        ts,
                    ))
                if is_coffee and estado == "Finalizado":
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        "Coffee institucional finalizado.",
                        ts,
                    ))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True})

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>", methods=["GET"], endpoint="api_dashboard_novedades_diarias_gestion")
    def api_dashboard_novedades_diarias_gestion(nov_id):
        actor = _session_actor()
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            _ensure_novedades_catalogo_table(con)
            _ensure_coffee_insumos_table(con)
            _ensure_coffee_logistica_table(con)
            _ensure_coffee_special_users(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            if not _actor_can_view_novedad(actor, row):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para ver esta gestion"}), 403
            item = _serialize_novedad(row, actor)
            if not bool(item.get("gestion_habilitada")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no tiene gestion interna"}), 400
            if not bool(item.get("puede_ver_gestion")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para ver esta gestion"}), 403
            rows = con.execute("""
                SELECT
                    id,
                    COALESCE(autor,'') AS autor,
                    COALESCE(autor_username,'') AS autor_username,
                    COALESCE(mensaje,'') AS mensaje,
                    COALESCE(es_sistema,0) AS es_sistema,
                    COALESCE(creado_en,'') AS creado_en
                FROM novedades_diarias_chat
                WHERE novedad_id=?
                ORDER BY id ASC
                LIMIT 500
            """, (nov_id,)).fetchall()
            actor_user = _norm_ci(actor.get("username") or "")
            actor_name = _norm_ci(actor.get("display") or "")
            mensajes = []
            for r in rows:
                autor = (_row_value(r, "autor", "") or "").strip()
                autor_username = (_row_value(r, "autor_username", "") or "").strip()
                es_propio = False
                if _norm_ci(autor_username) and _norm_ci(autor_username) == actor_user:
                    es_propio = True
                elif _norm_ci(autor) and _norm_ci(autor) == actor_name:
                    es_propio = True
                mensajes.append({
                    "id": int(_row_value(r, "id", 0) or 0),
                    "autor": autor,
                    "autor_username": autor_username,
                    "mensaje": (_row_value(r, "mensaje", "") or "").strip(),
                    "es_sistema": int(_row_value(r, "es_sistema", 0) or 0) == 1,
                    "creado_en": (_row_value(r, "creado_en", "") or "").strip(),
                    "es_propio": es_propio,
                })
            sedes = _dashboard_sedes_opts(con)
            agentes = _dashboard_agentes_opts(con)
            user_name = (actor.get("display") or "").strip()
            if user_name and user_name.lower() not in {a.lower() for a in agentes}:
                agentes.insert(0, user_name)
            sede_tarea = (item.get("tarea_sede_codigo") or item.get("sede_codigo") or "").strip().upper()
            depositos = _depositos_por_sede(con, sede_tarea)
            coffee_insumos = []
            coffee_logistica = {}
            if bool(item.get("es_coffee")):
                coffee_insumos = _coffee_read_insumos(con, nov_id)
                coffee_logistica = _coffee_read_logistica(con, nov_id)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({
            "ok": True,
            "novedad": item,
            "mensajes": mensajes,
            "herramientas_preset": list(NVD_HERRAMIENTAS_PRESET),
            "is_full": bool(actor.get("is_full")),
            "is_matias": bool(actor.get("is_matias")),
            "is_novedades_admin": bool(actor.get("is_novedades_admin")),
            "is_luciana": bool(actor.get("is_luciana")),
            "estados": (item.get("estados_disponibles") or list(NVD_ESTADOS)),
            "sedes": sedes,
            "agentes": agentes,
            "depositos_sede": depositos,
            "coffee_insumos": coffee_insumos,
            "coffee_logistica": coffee_logistica,
            "coffee_turnos_personal": dict(NVD_COFFEE_TURNO_PERSONAL),
        })

    @bp.route("/api/dashboard/novedades_depositos_por_sede", methods=["GET"], endpoint="api_dashboard_novedades_depositos_por_sede")
    def api_dashboard_novedades_depositos_por_sede():
        sede_codigo = (request.args.get("sede_codigo") or request.args.get("sede") or "").strip().upper()
        if not sede_codigo:
            return jsonify({"ok": True, "sede_codigo": "", "depositos": []})
        con = get_db()
        try:
            depositos = _depositos_por_sede(con, sede_codigo)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e), "depositos": []}), 500
        con.close()
        return jsonify({"ok": True, "sede_codigo": sede_codigo, "depositos": depositos})

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>/mensaje", methods=["POST"], endpoint="api_dashboard_novedades_diarias_gestion_mensaje")
    def api_dashboard_novedades_diarias_gestion_mensaje(nov_id):
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        mensaje = (payload.get("mensaje") or "").strip()
        if not mensaje:
            return jsonify({"ok": False, "error": "Mensaje obligatorio"}), 400
        if len(mensaje) > 1000:
            mensaje = mensaje[:1000]
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            if not _actor_can_view_novedad(actor, row):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para responder esta gestion"}), 403
            item = _serialize_novedad(row, actor)
            if not bool(item.get("gestion_habilitada")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no tiene gestion interna"}), 400
            if not bool(item.get("puede_ver_gestion")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para responder esta gestion"}), 403
            autor = (actor.get("display") or actor.get("username") or "").strip()
            if not autor:
                con.close()
                return jsonify({"ok": False, "error": "Usuario invalido"}), 403
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = con.execute("""
                INSERT INTO novedades_diarias_chat
                    (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (nov_id, autor, actor.get("username") or "", mensaje, ts))
            con.commit()
            msg_id = int(cur.lastrowid or 0)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({
            "ok": True,
            "mensaje": {
                "id": msg_id,
                "autor": autor,
                "autor_username": actor.get("username") or "",
                "mensaje": mensaje,
                "es_sistema": False,
                "creado_en": ts,
                "es_propio": True,
            },
        })

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>/estado", methods=["POST"], endpoint="api_dashboard_novedades_diarias_gestion_estado")
    def api_dashboard_novedades_diarias_gestion_estado(nov_id):
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        estado_raw = payload.get("estado") or "Informado"
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            _ensure_coffee_logistica_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            if not _actor_can_view_novedad(actor, row):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para cambiar estado"}), 403
            item = _serialize_novedad(row, actor)
            if not bool(item.get("gestion_habilitada")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no tiene gestion interna"}), 400
            is_coffee = bool(item.get("es_coffee"))
            estado = _norm_coffee_estado(estado_raw) if is_coffee else _norm_nvd_estado(estado_raw)
            if is_coffee:
                if not _can_edit_coffee_estado(actor, estado):
                    con.close()
                    return jsonify({"ok": False, "error": "No autorizado para ese estado Coffee"}), 403
                if _norm_ci(estado) in {"enviado", "finalizado"}:
                    log_row = con.execute(
                        "SELECT COALESCE(aprobado,0) AS aprobado FROM coffee_logistica WHERE novedad_id=? LIMIT 1",
                        (nov_id,),
                    ).fetchone()
                    aprobado = int(_row_value(log_row, "aprobado", 0) or 0) == 1
                    if not aprobado:
                        con.close()
                        return jsonify({"ok": False, "error": "Primero Matias debe aprobar la logistica"}), 400
            elif not bool(item.get("puede_cambiar_estado")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para cambiar estado"}), 403
            estado_prev = (
                _norm_coffee_estado(_row_value(row, "estado", "Pendiente") or "Pendiente")
                if is_coffee else _norm_nvd_estado(_row_value(row, "estado", "Informado") or "Informado")
            )
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                UPDATE novedades_diarias
                SET estado=?, actualizado_en=?
                WHERE id=?
            """, (estado, ts, nov_id))
            if is_coffee and estado == "Aprobado":
                sede_destino = (_row_value(row, "coffee_sede_destino", "") or "").strip().upper()
                if not sede_destino:
                    sede_destino = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                tarea_actual = (_row_value(row, "tarea_asignada", "") or "").strip()
                if not tarea_actual:
                    subtipo = (_row_value(row, "subtipo", "") or "").strip() or "General"
                    cant = int(_row_value(row, "coffee_cantidad_personas", 0) or 0)
                    tarea_actual = f"Coffee institucional - {subtipo} - {cant} personas"
                con.execute("""
                    UPDATE novedades_diarias
                    SET tarea_asignada=?,
                        tarea_estado='Pendiente',
                        tarea_sede_codigo=?,
                        tarea_deposito_codigo='',
                        tarea_deposito_nombre='',
                        tarea_agente='Francisco Savio',
                        tarea_asignado_por=?,
                        tarea_asignado_por_username=?,
                        tarea_asignado_en=?,
                        tarea_actualizado_en=?,
                        actualizado_en=?
                    WHERE id=?
                """, (
                    tarea_actual,
                    sede_destino,
                    actor.get("display") or actor.get("username") or "Sistema",
                    actor.get("username") or "",
                    ts,
                    ts,
                    ts,
                    nov_id,
                ))
            if estado_prev != estado:
                actor_name = (actor.get("display") or actor.get("username") or "Sistema").strip() or "Sistema"
                con.execute("""
                    INSERT INTO novedades_diarias_chat
                        (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                    VALUES (?, 'Sistema', ?, ?, 1, ?)
                """, (nov_id, actor.get("username") or "", f"{actor_name} cambio el estado a '{estado}'.", ts))
                if is_coffee and estado == "Aprobado":
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        "Asignacion automatica Coffee: tarea derivada a Francisco Savio.",
                        ts,
                    ))
                if is_coffee and estado == "Enviado":
                    sede_dest = (_row_value(row, "coffee_sede_destino", "") or "").strip().upper()
                    if not sede_dest:
                        sede_dest = (_row_value(row, "sede_codigo", "") or "").strip().upper() or "-"
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        f"Coffee enviado a sede {sede_dest}.",
                        ts,
                    ))
                if is_coffee and estado == "Finalizado":
                    con.execute("""
                        INSERT INTO novedades_diarias_chat
                            (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                        VALUES (?, 'Sistema', ?, ?, 1, ?)
                    """, (
                        nov_id,
                        actor.get("username") or "",
                        "Coffee institucional finalizado.",
                        ts,
                    ))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "estado": estado})

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>/tarea", methods=["POST"], endpoint="api_dashboard_novedades_diarias_gestion_tarea")
    def api_dashboard_novedades_diarias_gestion_tarea(nov_id):
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        tarea = (payload.get("tarea") or "").strip()
        tarea_estado = (payload.get("estado") or "").strip() or "Pendiente"
        tarea_sede_codigo = (payload.get("sede_codigo") or payload.get("tarea_sede_codigo") or "").strip().upper()
        tarea_agente = (payload.get("agente") or payload.get("tarea_agente") or "").strip()
        tarea_deposito_codigo = (payload.get("deposito_codigo") or payload.get("tarea_deposito_codigo") or "").strip().upper()
        tarea_deposito_nombre = (payload.get("deposito_nombre") or payload.get("tarea_deposito_nombre") or "").strip()
        tarea_herramientas = _parse_tarea_herramientas(
            payload.get("herramientas") or payload.get("tarea_herramientas") or []
        )
        solo_herramientas = str(payload.get("solo_herramientas") or "").strip().lower() in {"1", "true", "si", "yes"}
        auto_asignar = str(payload.get("auto_asignar") or "").strip().lower() in {"1", "true", "si", "yes"}
        limpiar = str(payload.get("limpiar") or "").strip().lower() in {"1", "true", "si", "yes"}
        if len(tarea) > 280:
            tarea = tarea[:280]
        if limpiar:
            tarea = ""
            tarea_estado = ""
            tarea_sede_codigo = ""
            tarea_agente = ""
            tarea_deposito_codigo = ""
            tarea_deposito_nombre = ""
            tarea_herramientas = []
        if tarea and tarea_estado not in {"Pendiente", "En curso", "Completada"}:
            tarea_estado = "Pendiente"
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            if not _actor_can_view_novedad(actor, row):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para editar tarea"}), 403
            item = _serialize_novedad(row, actor)
            if not bool(item.get("gestion_habilitada")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no tiene gestion interna"}), 400
            is_coffee = bool(item.get("es_coffee"))
            if is_coffee and _norm_ci(item.get("estado") or "") != "aprobado":
                con.close()
                return jsonify({"ok": False, "error": "La tarea Coffee solo se puede asignar cuando esta Aprobado"}), 400
            can_tools_only = bool(item.get("puede_ver_gestion")) and bool((item.get("tarea_asignada") or "").strip())
            can_autoassign = bool(item.get("puede_autoasignar"))
            preserve_assignador = False
            if solo_herramientas:
                if not can_tools_only:
                    con.close()
                    return jsonify({"ok": False, "error": "No autorizado para actualizar herramientas"}), 403
                limpiar = False
                preserve_assignador = True
                tarea = (item.get("tarea_asignada") or "").strip()
                tarea_estado = (item.get("tarea_estado") or "").strip() or "Pendiente"
                tarea_sede_codigo = (item.get("tarea_sede_codigo") or item.get("sede_codigo") or "").strip().upper()
                tarea_agente = (item.get("tarea_agente") or item.get("agente") or "").strip()
                tarea_deposito_codigo = (item.get("tarea_deposito_codigo") or "").strip().upper()
                tarea_deposito_nombre = (item.get("tarea_deposito_nombre") or "").strip()
            elif auto_asignar:
                if not can_autoassign:
                    con.close()
                    return jsonify({"ok": False, "error": "No autorizado para autoasignarte esta tarea"}), 403
                limpiar = False
                preserve_assignador = True
                tarea = (item.get("tarea_asignada") or "").strip()
                if not tarea:
                    con.close()
                    return jsonify({"ok": False, "error": "La tarea no tiene contenido para autoasignar"}), 400
                tarea_estado = (item.get("tarea_estado") or "").strip() or "Pendiente"
                tarea_sede_codigo = (item.get("tarea_sede_codigo") or item.get("sede_codigo") or "").strip().upper()
                tarea_deposito_codigo = (item.get("tarea_deposito_codigo") or "").strip().upper()
                tarea_deposito_nombre = (item.get("tarea_deposito_nombre") or "").strip()
                tarea_herramientas = _parse_tarea_herramientas(item.get("tarea_herramientas") or [])
                tarea_agente = (actor.get("display") or actor.get("full_name") or actor.get("username") or "").strip()
            elif not bool(item.get("puede_asignar_tarea")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para editar tarea"}), 403
            es_privada_propia = _actor_can_manage_private_novedad(actor, row)
            if not limpiar and not solo_herramientas:
                if _norm_ci(tarea_agente) in {"__equipo__", "equipo operativo", "equipo", "general", "todos"}:
                    tarea_agente = NVD_TAREA_GENERAL_LABEL
                if is_coffee:
                    tarea_agente = "Francisco Savio"
                    if not tarea_sede_codigo:
                        tarea_sede_codigo = (item.get("coffee_sede_destino") or item.get("sede_codigo") or "").strip().upper()
                    tarea_deposito_codigo = ""
                    tarea_deposito_nombre = ""
                else:
                    if not tarea_sede_codigo:
                        tarea_sede_codigo = (item.get("sede_codigo") or "").strip().upper()
                    if es_privada_propia:
                        tarea_agente = (actor.get("display") or actor.get("full_name") or actor.get("username") or "").strip()
                    elif not tarea_agente:
                        tarea_agente = (item.get("agente") or "").strip()
                if not tarea_sede_codigo:
                    con.close()
                    return jsonify({"ok": False, "error": "Selecciona sede para la tarea"}), 400
                if not tarea_agente:
                    con.close()
                    return jsonify({"ok": False, "error": "Selecciona agente asignado"}), 400
                deps = _depositos_por_sede(con, tarea_sede_codigo)
                if deps and not is_coffee:
                    if not tarea_deposito_codigo:
                        con.close()
                        return jsonify({"ok": False, "error": "Selecciona deposito de la sede"}), 400
                    dep_map = {str(d.get("codigo") or "").strip().upper(): str(d.get("descripcion") or "").strip() for d in deps}
                    if tarea_deposito_codigo not in dep_map:
                        con.close()
                        return jsonify({"ok": False, "error": "Deposito invalido para la sede seleccionada"}), 400
                    if not tarea_deposito_nombre:
                        tarea_deposito_nombre = dep_map.get(tarea_deposito_codigo, "")
                else:
                    tarea_deposito_codigo = ""
                    tarea_deposito_nombre = ""
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                UPDATE novedades_diarias
                SET tarea_asignada=?,
                    tarea_estado=?,
                    tarea_sede_codigo=?,
                    tarea_deposito_codigo=?,
                    tarea_deposito_nombre=?,
                    tarea_agente=?,
                    tarea_herramientas_json=?,
                    tarea_asignado_por=?,
                    tarea_asignado_por_username=?,
                    tarea_asignado_en=?,
                    tarea_actualizado_en=?,
                    actualizado_en=?
                WHERE id=?
            """, (
                tarea,
                tarea_estado,
                tarea_sede_codigo,
                tarea_deposito_codigo,
                tarea_deposito_nombre,
                tarea_agente,
                _dump_tarea_herramientas(tarea_herramientas),
                ((item.get("tarea_asignado_por") or "") if preserve_assignador else ((actor.get("display") or actor.get("username") or "Sistema") if tarea else "")),
                ((item.get("tarea_asignado_por_username") or "") if preserve_assignador else ((actor.get("username") or "") if tarea else "")),
                ((item.get("tarea_asignado_en") or "") if preserve_assignador else (ts if not limpiar else "")),
                ts,
                ts,
                nov_id,
            ))
            actor_name = (actor.get("display") or actor.get("username") or "Sistema").strip() or "Sistema"
            if tarea:
                sede_txt = tarea_sede_codigo or "-"
                dep_txt = tarea_deposito_codigo if tarea_deposito_codigo else "-"
                tools_txt = _herramientas_resumen(tarea_herramientas)
                if solo_herramientas:
                    if tools_txt:
                        msg = f"{actor_name} actualizo herramientas de la tarea: {tools_txt}."
                    else:
                        msg = f"{actor_name} limpio el listado de herramientas de la tarea."
                elif auto_asignar:
                    msg = (
                        f"{actor_name} se autoasigno la tarea: {tarea} "
                        f"(Sede {sede_txt} / Deposito {dep_txt} / Estado {tarea_estado})."
                    )
                else:
                    msg = (
                        f"{actor_name} asigno tarea a {tarea_agente}: {tarea} "
                        f"(Sede {sede_txt} / Deposito {dep_txt} / Estado {tarea_estado})."
                    )
                    if tools_txt:
                        msg += f" Herramientas: {tools_txt}."
            else:
                msg = f"{actor_name} elimino la tarea asignada."
            con.execute("""
                INSERT INTO novedades_diarias_chat
                    (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                VALUES (?, 'Sistema', ?, ?, 1, ?)
            """, (nov_id, actor.get("username") or "", msg, ts))
            con.commit()
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({
            "ok": True,
            "tarea": tarea,
            "estado": tarea_estado,
            "sede_codigo": tarea_sede_codigo,
            "deposito_codigo": tarea_deposito_codigo,
            "deposito_nombre": tarea_deposito_nombre,
            "agente": tarea_agente,
            "herramientas": tarea_herramientas,
            "herramientas_resumen": _herramientas_resumen(tarea_herramientas),
            "solo_herramientas": solo_herramientas,
            "auto_asignar": auto_asignar,
        })

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>/coffee_insumos", methods=["POST"], endpoint="api_dashboard_novedades_diarias_gestion_coffee_insumos")
    def api_dashboard_novedades_diarias_gestion_coffee_insumos(nov_id):
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        insumos_payload = payload.get("insumos")
        if not isinstance(insumos_payload, list):
            single = payload.get("insumo")
            if isinstance(single, dict):
                insumos_payload = [single]
            else:
                return jsonify({"ok": False, "error": "Insumos invalidos"}), 400
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            _ensure_coffee_insumos_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            item = _serialize_novedad(row, actor)
            if not bool(item.get("es_coffee")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no es Coffee institucional"}), 400
            if not bool(item.get("puede_ver_gestion")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado"}), 403
            can_edit_base = bool(item.get("puede_editar_coffee_insumos"))
            can_decide = bool(item.get("puede_decidir_compra"))
            can_recibir = bool(item.get("puede_marcar_recibido"))
            if not (can_edit_base or can_decide or can_recibir):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para actualizar insumos"}), 403
            actuales = _coffee_read_insumos(con, nov_id)
            by_id = {int(x.get("id") or 0): x for x in actuales if int(x.get("id") or 0) > 0}
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed_base = False
            changed_decision = False
            changed_recibido = False
            for ent in insumos_payload:
                if not isinstance(ent, dict):
                    continue
                iid = int(ent.get("id") or 0)
                if iid <= 0 or iid not in by_id:
                    continue
                old = by_id[iid]
                item_txt = str(old.get("item") or "").strip()
                cant = int(old.get("cantidad_necesaria") or 0)
                stock = int(old.get("stock_disponible") or 0)
                decision = str(old.get("decision_compra") or "pendiente").strip().lower()
                recibido = 1 if bool(old.get("recibido")) else 0
                if can_edit_base:
                    item_txt = str(ent.get("item") or item_txt).strip()[:80] or item_txt
                    try:
                        cant = max(0, int(ent.get("cantidad_necesaria")))
                    except Exception:
                        cant = max(0, cant)
                    try:
                        stock = max(0, int(ent.get("stock_disponible")))
                    except Exception:
                        stock = max(0, stock)
                    changed_base = True
                if can_decide:
                    dec_in = _norm_ci(ent.get("decision_compra") or decision).replace(" ", "_")
                    if dec_in in NVD_COFFEE_DECISION_COMPRA:
                        decision = dec_in
                        changed_decision = True
                if can_recibir:
                    recibido_in = str(ent.get("recibido") or "").strip().lower() in {"1", "true", "si", "yes", "on"}
                    if recibido_in:
                        recibido = 1
                        changed_recibido = True
                estado_stock = _coffee_calc_estado(cant, stock)
                con.execute("""
                    UPDATE coffee_insumos
                    SET item=?,
                        cantidad_necesaria=?,
                        stock_disponible=?,
                        estado=?,
                        decision_compra=?,
                        recibido=?,
                        actualizado_en=?,
                        actualizado_por=?
                    WHERE id=? AND novedad_id=?
                """, (
                    item_txt,
                    cant,
                    stock,
                    estado_stock,
                    decision,
                    recibido,
                    ts,
                    actor.get("display") or actor.get("username") or "Sistema",
                    iid,
                    nov_id,
                ))
            msg = ""
            actor_name = (actor.get("display") or actor.get("username") or "Sistema").strip() or "Sistema"
            if changed_recibido:
                msg = f"{actor_name} marco recepcion de insumos Coffee."
            elif changed_decision:
                msg = f"{actor_name} marco decision de compra para Coffee."
            elif changed_base:
                msg = f"{actor_name} cargo/actualizo insumos Coffee."
            if msg:
                con.execute("""
                    INSERT INTO novedades_diarias_chat
                        (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                    VALUES (?, 'Sistema', ?, ?, 1, ?)
                """, (nov_id, actor.get("username") or "", msg, ts))
            con.commit()
            result = _coffee_read_insumos(con, nov_id)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "insumos": result})

    @bp.route("/api/dashboard/novedades_diarias_gestion/<int:nov_id>/coffee_logistica", methods=["POST"], endpoint="api_dashboard_novedades_diarias_gestion_coffee_logistica")
    def api_dashboard_novedades_diarias_gestion_coffee_logistica(nov_id):
        actor = _session_actor()
        payload = request.get_json(silent=True) or {}
        con = get_db()
        try:
            _ensure_novedades_diarias_table(con)
            _ensure_novedades_diarias_chat_table(con)
            _ensure_coffee_logistica_table(con)
            row = _fetch_novedad(con, nov_id)
            if not row:
                con.close()
                return jsonify({"ok": False, "error": "Novedad inexistente"}), 404
            item = _serialize_novedad(row, actor)
            if not bool(item.get("es_coffee")):
                con.close()
                return jsonify({"ok": False, "error": "La novedad no es Coffee institucional"}), 400
            if not bool(item.get("puede_ver_gestion")):
                con.close()
                return jsonify({"ok": False, "error": "No autorizado"}), 403
            can_edit = bool(item.get("puede_editar_logistica"))
            can_approve = bool(item.get("puede_aprobar_logistica"))
            if not can_edit and not can_approve:
                con.close()
                return jsonify({"ok": False, "error": "No autorizado para logistica"}), 403

            actual = _coffee_read_logistica(con, nov_id)
            chofer = str(actual.get("chofer") or "").strip()
            personal = str(actual.get("personal") or "").strip()
            turno = str(actual.get("turno") or "").strip()
            aprobado = 1 if bool(actual.get("aprobado")) else 0
            aprobado_por = str(actual.get("aprobado_por") or "").strip()
            aprobado_en = str(actual.get("aprobado_en") or "").strip()
            changed_data = False
            changed_approve = False

            if can_edit:
                if "chofer" in payload:
                    chofer = str(payload.get("chofer") or "").strip()[:80]
                    changed_data = True
                if "turno" in payload:
                    t = _coffee_norm_turno(payload.get("turno"))
                    turno = t
                    changed_data = True
                if "personal" in payload:
                    personal = str(payload.get("personal") or "").strip()[:80]
                    changed_data = True
                if turno and personal:
                    validos = NVD_COFFEE_TURNO_PERSONAL.get(turno, [])
                    if personal not in validos:
                        con.close()
                        return jsonify({"ok": False, "error": "Personal no valido para el turno seleccionado"}), 400

            if "aprobar" in payload:
                aprobar = str(payload.get("aprobar") or "").strip().lower() in {"1", "true", "si", "yes", "on"}
                if aprobar:
                    if not can_approve:
                        con.close()
                        return jsonify({"ok": False, "error": "Solo Matias puede aprobar logistica"}), 403
                    if not chofer or not personal or not turno:
                        con.close()
                        return jsonify({"ok": False, "error": "Completa chofer, personal y turno antes de aprobar"}), 400
                    aprobado = 1
                    aprobado_por = actor.get("display") or actor.get("username") or "Matias Calderari"
                    aprobado_en = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    changed_approve = True
                elif can_approve:
                    aprobado = 0
                    aprobado_por = ""
                    aprobado_en = ""
                    changed_approve = True

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute("""
                UPDATE coffee_logistica
                SET chofer=?,
                    personal=?,
                    turno=?,
                    aprobado=?,
                    aprobado_por=?,
                    aprobado_en=?,
                    actualizado_en=?,
                    actualizado_por=?
                WHERE novedad_id=?
            """, (
                chofer,
                personal,
                turno,
                aprobado,
                aprobado_por,
                aprobado_en,
                ts,
                actor.get("display") or actor.get("username") or "Sistema",
                nov_id,
            ))
            con.execute("""
                UPDATE novedades_diarias
                SET coffee_logistica_aprobada=?,
                    actualizado_en=?
                WHERE id=?
            """, (aprobado, ts, nov_id))

            actor_name = (actor.get("display") or actor.get("username") or "Sistema").strip() or "Sistema"
            msg = ""
            if changed_approve and aprobado == 1:
                msg = f"{actor_name} aprobo logistica Coffee."
            elif changed_approve and aprobado == 0:
                msg = f"{actor_name} desmarco aprobacion de logistica Coffee."
            elif changed_data:
                msg = f"{actor_name} actualizo logistica Coffee (turno {turno or '-'})."
            if msg:
                con.execute("""
                    INSERT INTO novedades_diarias_chat
                        (novedad_id, autor, autor_username, mensaje, es_sistema, creado_en)
                    VALUES (?, 'Sistema', ?, ?, 1, ?)
                """, (nov_id, actor.get("username") or "", msg, ts))
            con.commit()
            result = _coffee_read_logistica(con, nov_id)
        except Exception as e:
            con.close()
            return jsonify({"ok": False, "error": str(e)}), 500
        con.close()
        return jsonify({"ok": True, "logistica": result})

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
