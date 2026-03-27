from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from datetime import date, datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import sqlite3, os, calendar
from functools import wraps
from flask import redirect, url_for
import os
from flask import request, render_template, redirect, url_for, flash
import os
from datetime import date
from flask import request, render_template, redirect, url_for, flash, send_from_directory
from modules.auditorias import register_auditorias
from modules.obras import register_obras
from modules.agentes import register_agentes
from modules.mapa import register_mapa
from modules.vehiculos import register_vehiculos
from modules.inventario_checklist import register_inventario_checklist
from modules.inventario_general import register_inventario_general
from modules.sst import register_sst
from werkzeug.utils import secure_filename

# =========================
# REMITOS - CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REMITOS_DRIVE_URL = "https://drive.google.com/drive/folders/1XS7Zd3Jolxie8XQEsikgAvgN5_qb3Zsd"

ALLOWED_REMITO_EXT = {"pdf", "jpg", "jpeg", "png"}

AGENTE_DOCS_FOLDER = os.path.join(BASE_DIR, "uploads", "agentes_documentacion")
os.makedirs(AGENTE_DOCS_FOLDER, exist_ok=True)

ALLOWED_AGENTE_DOC_EXT = {"pdf", "jpg", "jpeg", "png"}

def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_REMITO_EXT

def allowed_agente_doc(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_AGENTE_DOC_EXT


# =========================
# AUTH
# =========================
ROLE_FULL = "full"
ROLE_SEDE_VEHICULOS = "sede_vehiculos"
ROLE_SST_VEHICULOS = "sst_vehiculos"
ROLE_OBRAS_VEHICULOS = "obras_vehiculos"
ROLE_DASH_OBRAS = "dashboard_obras"
ROLE_DASH_VEHICULOS = "dashboard_vehiculos"
ROLE_DASH_SOLO = "dashboard_solo"
ROLE_EJECUTIVO = "ejecutivo"
ROLE_CHOFER_INTENDENCIA = "chofer_intendencia"
ROLE_CHOFER_AUTORIZADO = "chofer_autorizado"
ROLE_OPERATIVO_CLAVE = "operativo_clave"
ROLE_CONTROL_SEDES = "control_sedes"
ROLE_INT_VEHICULOS = "int_vehiculos"
ROLE_INT_OBRAS = "int_obras"
ROLE_INT_OBRAS_RELEV = "int_obras_relev"
ROLE_INT_OBRAS_SEDES = "int_obras_sedes"
_AUTH_TABLES_READY = False


def ensure_auth_tables(con):
    global _AUTH_TABLES_READY
    if _AUTH_TABLES_READY:
        return
    con.execute("""
        CREATE TABLE IF NOT EXISTS usuarios(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            must_change INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1
        )
    """)
    con.commit()
    cols = [r["name"] for r in con.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "full_name" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN full_name TEXT")
    if "role" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN role TEXT")
    if "password_hash" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT")
    if "must_change" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN must_change INTEGER DEFAULT 1")
    if "activo" not in cols:
        con.execute("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1")
    con.commit()

    default_users = [
        ("mcalderari", "Matias Calderari", ROLE_FULL),
        ("ibaroni", "Ignacio Baroni", ROLE_FULL),
        ("fsavio", "Francisco Savio", ROLE_OPERATIVO_CLAVE),
        ("mvea", "Mauro Vea Murguia", ROLE_INT_VEHICULOS),
        ("eperez", "Emiliano Perez de la Puente", ROLE_OPERATIVO_CLAVE),
        ("cvidaurre", "Carlos Vidaurre", ROLE_DASH_SOLO),
        ("mduran", "Marcos Duran", ROLE_DASH_VEHICULOS),
        ("nguerrero", "Nestor Guerrero", ROLE_DASH_SOLO),
        ("mflores", "Manuel Flores", ROLE_DASH_VEHICULOS),
        ("mabatedaga", "Maximiliano Abatedaga", ROLE_FULL),
        ("mluna", "Matias Luna", ROLE_EJECUTIVO),
        ("gburgos", "G. Burgos", ROLE_EJECUTIVO),
        # Choferes autorizados (otras areas) - acceso limitado a control diario
        ("nmatorras", "Nabil Matorras", ROLE_CHOFER_AUTORIZADO),
        ("mmontiel", "Mateo Montiel", ROLE_CHOFER_AUTORIZADO),
        ("mzambrano", "Mauricio Zambrano", ROLE_CHOFER_AUTORIZADO),
        ("laviles", "Leonardo Aviles", ROLE_CHOFER_AUTORIZADO),
        ("bburgos", "Benjamin Burgos", ROLE_CHOFER_AUTORIZADO),
        ("jdaud", "Julio Daud", ROLE_CHOFER_AUTORIZADO),
        ("agonzalez", "Agustin Gonzalez", ROLE_CHOFER_AUTORIZADO),
        ("jvaldivia", "Javier Valdivia", ROLE_CHOFER_AUTORIZADO),
        ("fgiuletti", "Giuletti", ROLE_CHOFER_AUTORIZADO),
        ("dzamar", "Diego Zamar", ROLE_CHOFER_AUTORIZADO),
        ("jcorbacho", "Jorge Corbacho", ROLE_CHOFER_AUTORIZADO),
        ("ndaje", "Nicolas Daje", ROLE_CHOFER_AUTORIZADO),
    ]
    has_legacy_password = "password" in cols
    has_legacy_role = "rol" in cols
    for username, full_name, role in default_users:
        legacy_role = "admin" if role == ROLE_FULL else "operador"
        row = con.execute("SELECT id FROM usuarios WHERE username = ?", (username,)).fetchone()
        if not row:
            if has_legacy_password and has_legacy_role:
                con.execute("""
                    INSERT INTO usuarios(username, full_name, role, rol, password_hash, must_change, activo, password)
                    VALUES (?,?,?,?,?,1,1,?)
                """, (username, full_name, role, legacy_role, generate_password_hash("654321"), "654321"))
            elif has_legacy_password:
                con.execute("""
                    INSERT INTO usuarios(username, full_name, role, password_hash, must_change, activo, password)
                    VALUES (?,?,?,?,1,1,?)
                """, (username, full_name, role, generate_password_hash("654321"), "654321"))
            elif has_legacy_role:
                con.execute("""
                    INSERT INTO usuarios(username, full_name, role, rol, password_hash, must_change, activo)
                    VALUES (?,?,?,?,?,1,1)
                """, (username, full_name, role, legacy_role, generate_password_hash("654321")))
            else:
                con.execute("""
                    INSERT INTO usuarios(username, full_name, role, password_hash, must_change, activo)
                    VALUES (?,?,?,?,1,1)
                """, (username, full_name, role, generate_password_hash("654321")))
        else:
            con.execute("""
                UPDATE usuarios
                SET full_name = ?,
                    role = ?,
                    password_hash = COALESCE(password_hash, ?),
                    activo = COALESCE(activo, 1),
                    must_change = COALESCE(must_change, 1)
                WHERE username = ?
            """, (full_name, role, generate_password_hash("654321"), username))
            if has_legacy_role:
                con.execute("""
                    UPDATE usuarios
                    SET rol = COALESCE(rol, ?)
                    WHERE username = ?
                """, (legacy_role, username))
            if has_legacy_password:
                con.execute("""
                    UPDATE usuarios
                    SET password = COALESCE(password, ?)
                    WHERE username = ?
                """, ("654321", username))
    con.commit()
    _AUTH_TABLES_READY = True


def module_from_path(path: str) -> str:
    if path == "/" or path.startswith("/dashboard"):
        return "dashboard"
    if path.startswith("/api/dashboard"):
        return "dashboard"
    if path.startswith("/vehiculos"):
        return "vehiculos"
    if path.startswith("/viajes"):
        return "vehiculos"
    if path.startswith("/auditoria") or path.startswith("/relevamientos"):
        return "relevamientos"
    if path.startswith("/obras"):
        return "obras"
    if path.startswith("/sst"):
        return "sst"
    if path.startswith("/agentes"):
        return "agentes"
    if path.startswith("/sedes") or path.startswith("/sede"):
        return "sedes"
    if path.startswith("/eventos"):
        return "eventos"
    return "other"


def role_allows(role: str, module: str) -> bool:
    perms = {
        ROLE_FULL: {"dashboard", "vehiculos", "obras", "sst", "agentes", "sedes", "eventos", "other", "relevamientos"},
        "admin": {"dashboard", "vehiculos", "obras", "sst", "agentes", "sedes", "eventos", "other", "relevamientos"},
        ROLE_SEDE_VEHICULOS: {"sedes", "vehiculos", "eventos"},
        ROLE_SST_VEHICULOS: {"sst", "vehiculos", "eventos"},
        ROLE_OBRAS_VEHICULOS: {"obras", "vehiculos", "eventos"},
        ROLE_DASH_OBRAS: {"dashboard", "obras", "eventos"},
        ROLE_DASH_VEHICULOS: {"dashboard", "vehiculos", "eventos"},
        ROLE_DASH_SOLO: {"dashboard", "eventos"},
        ROLE_EJECUTIVO: {"dashboard", "obras", "vehiculos", "sedes", "sst", "other", "eventos", "relevamientos"},
        ROLE_CHOFER_INTENDENCIA: {"vehiculos", "eventos"},
        ROLE_CHOFER_AUTORIZADO: {"vehiculos", "eventos"},
        ROLE_OPERATIVO_CLAVE: {"sedes", "vehiculos", "eventos", "dashboard"},
        ROLE_CONTROL_SEDES: {"sedes", "eventos"},
        ROLE_INT_VEHICULOS: {"vehiculos", "eventos", "dashboard"},
        ROLE_INT_OBRAS: {"obras", "eventos"},
        ROLE_INT_OBRAS_RELEV: {"obras", "relevamientos", "eventos", "vehiculos"},
        ROLE_INT_OBRAS_SEDES: {"obras", "sedes", "eventos", "vehiculos"},
    }
    return module in perms.get(role or "", set())


def default_redirect_for_role(role: str):
    if role == ROLE_EJECUTIVO:
        return url_for("dashboard_ejecutivo")
    if role == ROLE_DASH_OBRAS:
        return url_for("dashboard")
    if role == ROLE_DASH_VEHICULOS:
        return url_for("dashboard")
    if role == ROLE_DASH_SOLO:
        return url_for("dashboard_exec")
    if role == ROLE_OPERATIVO_CLAVE:
        return url_for("dashboard_exec")
    if role == ROLE_CONTROL_SEDES:
        return url_for("sedes_resumen_mpd")
    if role == ROLE_SEDE_VEHICULOS:
        return url_for("sede_ficha", codigo="S01", home=1)
    if role == ROLE_SST_VEHICULOS:
        return url_for("sst_general")
    if role == ROLE_OBRAS_VEHICULOS:
        return url_for("obras_home")
    if role == ROLE_INT_OBRAS:
        return url_for("obras_home")
    if role == ROLE_INT_OBRAS_RELEV:
        return url_for("obras_home")
    if role == ROLE_INT_OBRAS_SEDES:
        return url_for("obras_home")
    if role == ROLE_CHOFER_INTENDENCIA or role == ROLE_CHOFER_AUTORIZADO:
        return url_for("vehiculos_control_diario")
    if role == ROLE_INT_VEHICULOS:
        return url_for("vehiculos_control_diario")
    return url_for("dashboard")


# =========================
# DB - asegurar columnas
# =========================
def ensure_combustible_columns(conn):
    """
    Agrega columnas faltantes en la tabla combustible (SQLite).
    No rompe si ya existen.
    """
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(combustible)").fetchall()]

    def add_col(sql):
        conn.execute(sql)

    # Guardar nombre de archivo del remito
    if "remito_archivo" not in cols:
        add_col("ALTER TABLE combustible ADD COLUMN remito_archivo TEXT")

    # (opcional) si alguna vez tu tabla usó otros nombres, podés agregar más acá
    conn.commit()







# =========================
# COLORES OFICIALES FUEROS
# =========================
FUERO_COLORS = {
    # Fuero viejo (como está guardado en la tabla) → color
    "Penal": "#5B5BEA",
    "Menores": "#65BFF4",
    "Civil": "#EC4899",
    "Familia": "#65BFF4",
    "Administración": "#64748b",          # lo dejamos gris
    "Equipo interdisciplinario": "#64748b",

    # Códigos nuevos que usamos en los seeds nuevos (por las dudas)
    "penal": "#5B5BEA",                    # violeta
    "juridico_social": "#F64B94",          # rosa (Gorriti 791)
    "menores_incapaces": "#65BFF4",        # celeste (San Martín 271)
    "civil": "#EC4899",
    "familia": "#65BFF4",
    "unificado": "#EC4899",
}

# =====================================================
# COLORES PARA EVENTOS EN EL CALENDARIO
# =====================================================

CAL_COLORS = {
    # ===== VEHÍCULOS =====
    "service": "#EF4444",             # rojo
    "lavado": "#3B82F6",              # azul
    "seguro": "#F59E0B",              # ámbar
    "rtv": "#A855F7",                 # violeta
    "carga_combustible": "#22C55E",   # verde
    "viaje": "#0EA5E9",               # celeste
    "viaje_largo": "#1D4ED8",         # azul fuerte
    "checklist_novedad": "#F97316",   # naranja

    # ===== AGENTES =====
    "licencia": "#f97316",          # Naranja
    "obra": "#3b82f6",              # Azul
    "documentacion": "#6366f1",     # Violeta
    "incidente": "#dc2626",         # Rojo
    "desinfeccion": "#22c55e",      # Verde
    "uso_salon": "#0ea5e9",         # Celeste
    "sst_prevencion": "#0ea5e9",    # Celeste
    "sst_no_conformidad": "#f97316",# Naranja
    "sst_informe": "#22c55e",       # Verde
    "otro": "#64748b",              # Gris por defecto


    # ===== OBRAS =====
    "obra_solicitada": "#F97316",     # naranja
    "obra_en_curso": "#EAB308",       # amarillo fuerte
    "obra_finalizada": "#22C55E",     # verde
    "pedido_materiales": "#193023",   # verde oscuro

    # ===== INVENTARIO / MOBILIARIO =====
    "mobiliario_mov": "#a78bfa",      # lila
    "mobiliario_alta": "#c4b5fd",     # lila claro
    "inventario_control": "#0ea5e9",  # celeste

    # ===== SEGURIDAD / LIMPIEZA =====
    "matafuego_recarga": "#f97316",      # naranja
    "matafuego_vencimiento": "#ef4444",  # rojo fuerte
    "desinfeccion": "#22c55e",           # verde
    "desinfeccion_prox": "#16a34a",      # verde oscuro
    "limpieza_insumos": "#0ea5e9",       # celeste

    # ===== USO DE SALÓN / REUNIONES =====
    "uso_salon": "#0f766e",           # verde petróleo
}




def _cal_event(fecha, titulo, detalle, fuente, ref_id, tipo):
    """
    Crea un diccionario estándar de evento para el calendario.
    - fecha: 'YYYY-MM-DD'
    - titulo: texto corto
    - detalle: texto más largo
    - fuente: módulo origen ('licencias', 'documentacion', 'incidente', etc.)
    - ref_id: id de la tabla original (para ubicar rápido)
    - tipo: clave de CAL_COLORS
    """
    return {
        "fecha": fecha,
        "titulo": titulo,
        "detalle": detalle,
        "fuente": fuente,
        "ref_id": ref_id,
        "tipo": tipo,
        "color": CAL_COLORS.get(tipo, CAL_COLORS["otro"]),
    }

# =====================================================
# FUNCIONES GENÉRICAS PARA CREAR EVENTOS
# =====================================================
def add_evento(fecha, titulo, detalle="", color="#3B82F6", fuente="sistema", ref_id=None, con=None):
    """
    Inserta un evento en la tabla 'eventos' (calendario general).
    Limita el tamaño de título y detalle.
    """
    if not fecha:
        return

    own_con = con is None
    if own_con:
        con = get_db()

    con.execute("""
        INSERT INTO eventos(fecha, titulo, detalle, color, fuente, ref_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        fecha,
        (titulo or "")[:120],
        (detalle or "")[:500],
        color,
        fuente,
        str(ref_id) if ref_id is not None else None,
    ))
    if own_con:
        con.commit()
        con.close()


def add_evento_tipo(fecha, tipo, titulo, detalle="", fuente="sistema", ref_id=None, con=None):
    """
    Usa CAL_COLORS según el 'tipo' de evento (licencias, obras, matafuegos, etc.).
    """
    if not fecha:
        return
    color = CAL_COLORS.get(tipo, "#3B82F6")
    add_evento(fecha, titulo, detalle, color=color, fuente=fuente, ref_id=ref_id, con=con)
    


# =====================================================
# REGENERAR EVENTOS DESDE TABLAS - AGENTES
# =====================================================

def rebuild_eventos_agentes():
    """
    Borra los eventos de fuente 'agentes' y los vuelve a generar
    a partir de las tablas:
      - agentes_licencias
      - agentes_documentacion (tipo = carnet_conducir)
      - agentes_epp
      - agentes_incidentes
      - agentes_asignaciones
      - agentes_desempeno (capacitaciones)
    """
    con = get_db()
    cur = con.cursor()

    # 1) Limpiar eventos viejos de agentes
    cur.execute("DELETE FROM eventos WHERE fuente = 'agentes'")
    con.commit()

 
    # --------------------------------------------------
    # LICENCIAS  ->  UN EVENTO POR CADA DÍA DEL RANGO
    # --------------------------------------------------
    cur.execute("""
        SELECT al.id, al.agente_id, al.tipo, al.fecha_desde, al.fecha_hasta, al.estado,
               ai.agente
        FROM agentes_licencias al
        JOIN agentes_intendencia ai ON ai.id = al.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        lic_id = row["id"]
        agente = row["agente"]
        tipo = (row["tipo"] or "").capitalize()
        estado = (row["estado"] or "").capitalize()
        f_desde = row["fecha_desde"]
        f_hasta = row["fecha_hasta"]

        if not f_desde or not f_hasta:
            continue

        # convierto a date
        d_desde = datetime.strptime(f_desde, "%Y-%m-%d").date()
        d_hasta = datetime.strptime(f_hasta, "%Y-%m-%d").date()

        dia = d_desde
        while dia <= d_hasta:
            add_evento_tipo(
                fecha=dia.isoformat(),
                tipo="licencia",
                titulo=f"Licencia – {agente}",
                detalle=f"{tipo} ({estado})",
                fuente="agentes",
                ref_id=f"LIC-{lic_id}"      # mismo ref para todo el rango
            )
            dia += timedelta(days=1)

    # --------------------------------------------------
    # CARNET DE CONDUCIR (documentación)
    # --------------------------------------------------
      
    # --------------------------------------------------
    # DOCUMENTACIÓN (todos los tipos)
    # --------------------------------------------------
    # COMPENSATORIOS FERIA -> EVENTO INFORMATIVO
    try:
        cur.execute("""
            SELECT
                cm.id,
                cm.agente_id,
                ai.agente,
                cm.fecha,
                cm.dias,
                cm.periodo,
                cm.observaciones
            FROM agentes_compensatorios_mov cm
            JOIN agentes_intendencia ai ON ai.id = cm.agente_id
            WHERE cm.tipo = 'FERIA'
        """)
        for row in cur.fetchall():
            fecha = row["fecha"]
            if not fecha:
                continue
            detalle = f"Compensatorio feria: {int(row['dias'] or 0)} dias"
            if row["periodo"]:
                detalle += f" | Periodo: {row['periodo']}"
            if row["observaciones"]:
                detalle += f" | {row['observaciones']}"
            add_evento_tipo(
                fecha=fecha,
                tipo="licencia",
                titulo=f"Feria trabajada - {row['agente']}",
                detalle=detalle,
                fuente="agentes",
                ref_id=f"FERIA-{row['id']}"
            )
    except Exception:
        pass

    # COMPENSATORIOS TOMADOS -> EVENTO POR CADA DIA DEL RANGO
    try:
        cur.execute("""
            SELECT
                cm.id,
                cm.agente_id,
                ai.agente,
                cm.desde,
                cm.hasta,
                cm.dias,
                cm.periodo,
                cm.observaciones
            FROM agentes_compensatorios_mov cm
            JOIN agentes_intendencia ai ON ai.id = cm.agente_id
            WHERE cm.tipo = 'TOMA'
        """)
        for row in cur.fetchall():
            cid = row["id"]
            agente = row["agente"]
            desde = row["desde"] or row["hasta"]
            hasta = row["hasta"] or row["desde"]
            if not desde or not hasta:
                continue
            try:
                d1 = datetime.strptime(desde, "%Y-%m-%d").date()
                d2 = datetime.strptime(hasta, "%Y-%m-%d").date()
            except Exception:
                continue
            if d2 < d1:
                d1, d2 = d2, d1
            detalle = f"Compensatorio tomado ({int(row['dias'] or 0)} dias)"
            if row["periodo"]:
                detalle += f" | Periodo: {row['periodo']}"
            if row["observaciones"]:
                detalle += f" | {row['observaciones']}"
            cur_day = d1
            while cur_day <= d2:
                add_evento_tipo(
                    fecha=cur_day.isoformat(),
                    tipo="licencia",
                    titulo=f"Compensatorio - {agente}",
                    detalle=detalle,
                    fuente="agentes",
                    ref_id=f"COMP-{cid}"
                )
                cur_day = cur_day + timedelta(days=1)
    except Exception:
        pass

    cur.execute("""
        SELECT ad.id, ad.agente_id, ad.tipo, ad.fecha_vencimiento, ad.estado,
               ai.agente
        FROM agentes_documentacion ad
        JOIN agentes_intendencia ai ON ai.id = ad.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        doc_id   = row["id"]
        agente   = row["agente"]
        tipo_doc = (row["tipo"] or "").strip()
        f_venc   = row["fecha_vencimiento"]
        estado   = (row["estado"] or "").upper()  # VIGENTE / VENCIDO / ...

        if not f_venc:
            continue

        tipo_lower = tipo_doc.lower()

        # Si es carnet de conducir, usamos el color específico
        if tipo_lower == "carnet_conducir":
            tipo_evento = "carnet_conducir"
            titulo = f"Vencimiento carnet – {agente}"
        else:
            # Cualquier otra documentación: ART, examen médico, etc.
            tipo_evento = "documentacion"
            titulo = f"Vence {tipo_doc} – {agente}"

        detalle = f"Estado actual: {estado}"

        add_evento_tipo(
            fecha=f_venc,
            tipo=tipo_evento,
            titulo=titulo,
            detalle=detalle,
            fuente="agentes",
            ref_id=f"DOC-{doc_id}"
        )

    # ---------------------------
    # SEGURIDAD: MATAFUEGOS
    # ---------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS seguridad_matafuegos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_sede TEXT NOT NULL,      -- S01, S02, ...
        ubicacion TEXT,                 -- Pasillo, Oficina 2, etc.
        identificador TEXT,             -- N° de serie / etiqueta
        fecha_carga TEXT,               -- YYYY-MM-DD
        fecha_vencimiento TEXT,         -- YYYY-MM-DD
        fecha_recarga TEXT,             -- próxima recarga programada
        observaciones TEXT,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
    )
    """)

    # ---------------------------
    # SEGURIDAD: DESINFECCIONES
    # ---------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS seguridad_desinfecciones(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_sede TEXT NOT NULL,
        empresa TEXT,
        fecha_ultima TEXT,              -- última desinfección
        fecha_proxima TEXT,             -- próxima programada
        tipo TEXT,                      -- desratización, desinfección, etc.
        observaciones TEXT,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
    )
    """)

    # ---------------------------
    # SEGURIDAD: VISITAS A SEDES
    # ---------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS seguridad_visitas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_sede TEXT NOT NULL,
        fecha TEXT NOT NULL,            -- YYYY-MM-DD
        responsable TEXT,               -- quién visitó / inspeccionó
        motivo TEXT,                    -- inspección, relevamiento, etc.
        observaciones TEXT,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
    )
    """)

    # --------------------------------------------------
    # EPP / HERRAMIENTAS ENTREGADOS
    # --------------------------------------------------
    cur.execute("""
        SELECT e.id, e.agente_id, e.tipo, e.categoria, e.fecha_entrega, e.cantidad, e.estado,
               ai.agente
        FROM agentes_epp e
        JOIN agentes_intendencia ai ON ai.id = e.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        epp_id = row["id"]
        agente = row["agente"]
        tipo = row["tipo"] or ""
        categoria = row["categoria"] or ""
        f_entrega = row["fecha_entrega"]
        cant = row["cantidad"] or 1
        estado = row["estado"] or ""

        titulo = f"EPP/herramienta – {agente}"
        detalle = f"{categoria} - {tipo} (x{cant}) – Estado: {estado}"

        add_evento_tipo(
            fecha=f_entrega,
            tipo="epp",
            titulo=titulo,
            detalle=detalle,
            fuente="agentes",
            ref_id=f"EPP-{epp_id}"
        )

    # --------------------------------------------------
    # INCIDENTES / ACCIDENTES
    # --------------------------------------------------
    cur.execute("""
        SELECT inc.id, inc.agente_id, inc.fecha, inc.tipo, inc.lugar,
               inc.descripcion, inc.consecuencia, inc.estado,
               ai.agente
        FROM agentes_incidentes inc
        JOIN agentes_intendencia ai ON ai.id = inc.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        inc_id = row["id"]
        agente = row["agente"]
        fecha = row["fecha"]
        tipo = row["tipo"] or ""
        lugar = row["lugar"] or ""
        consecuencia = row["consecuencia"] or ""
        estado = row["estado"] or ""

        partes = []
        if lugar:
            partes.append(f"Lugar: {lugar}")
        if consecuencia:
            partes.append(f"Consecuencia: {consecuencia}")
        if estado:
            partes.append(f"Estado: {estado}")

        detalle = " | ".join(partes)

        add_evento_tipo(
            fecha=fecha,
            tipo="incidente",
            titulo=f"Incidente/accidente – {agente} ({tipo})",
            detalle=detalle,
            fuente="agentes",
            ref_id=f"INC-{inc_id}"
        )

    # --------------------------------------------------
    # SST (Prevencion / No conformidades / Informes)
    # --------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agentes_sst(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agente_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,          -- YYYY-MM-DD
        tipo TEXT NOT NULL,           -- prevencion / no_conformidad / informe
        titulo TEXT,
        detalle TEXT,
        estado TEXT,                  -- ABIERTO / CERRADO / EN_REVISION
        FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
    )
    """)
    cur.execute("""
        SELECT s.id, s.agente_id, s.fecha, s.tipo, s.titulo, s.detalle, s.estado,
               ai.agente
        FROM agentes_sst s
        JOIN agentes_intendencia ai ON ai.id = s.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        sst_id = row["id"]
        agente = row["agente"]
        fecha = row["fecha"]
        tipo = (row["tipo"] or "").strip().lower()
        titulo = row["titulo"] or "Registro SST"
        detalle = row["detalle"] or ""
        estado = row["estado"] or ""

        partes = []
        if estado:
            partes.append(f"Estado: {estado}")
        if detalle:
            partes.append(detalle)

        tipo_evento = f"sst_{tipo}" if tipo else "sst_prevencion"

        add_evento_tipo(
            fecha=fecha,
            tipo=tipo_evento,
            titulo=f"SST {tipo or 'registro'} - {agente} - {titulo}",
            detalle=" | ".join(partes),
            fuente="agentes",
            ref_id=f"SST-{sst_id}"
        )


 

    # --------------------------------------------------
    # ASIGNACIONES A SEDES
    # --------------------------------------------------
    cur.execute("""
        SELECT asg.id, asg.agente_id, asg.sede_codigo, asg.fecha_desde, asg.fecha_hasta,
               asg.estado, asg.observaciones,
               ai.agente
        FROM agentes_asignaciones asg
        JOIN agentes_intendencia ai ON ai.id = asg.agente_id
        WHERE ai.activo = 1
    """)
    for row in cur.fetchall():
        asg_id = row["id"]
        agente = row["agente"]
        sede = row["sede_codigo"]
        f_desde = row["fecha_desde"]
        f_hasta = row["fecha_hasta"]
        estado = row["estado"] or ""
        obs = row["observaciones"] or ""

        # Inicio asignación
        add_evento_tipo(
            fecha=f_desde,
            tipo="asignacion",
            titulo=f"Asignación a sede {sede} – {agente}",
            detalle=f"Inicio asignación. Estado: {estado}. {obs}",
            fuente="agentes",
            ref_id=f"ASIG-{asg_id}-INI"
        )

        # Fin asignación (si tiene fecha)
        if f_hasta:
            add_evento_tipo(
                fecha=f_hasta,
                tipo="asignacion",
                titulo=f"Fin asignación sede {sede} – {agente}",
                detalle=f"Fin asignación. Estado: {estado}. {obs}",
                fuente="agentes",
                ref_id=f"ASIG-{asg_id}-FIN"
            )

    # --------------------------------------------------
    # CAPACITACIONES / DESEMPEÑO (solo los que sean 'capacitacion')
    # --------------------------------------------------
    cur.execute("""
        SELECT d.id, d.agente_id, d.fecha, d.tipo, d.periodo,
               d.calificacion, d.observaciones,
               ai.agente
        FROM agentes_desempeno d
        JOIN agentes_intendencia ai ON ai.id = d.agente_id
        WHERE ai.activo = 1
          AND LOWER(d.tipo) = 'capacitacion'
    """)
    for row in cur.fetchall():
        cap_id = row["id"]
        agente = row["agente"]
        fecha = row["fecha"]
        periodo = row["periodo"] or ""
        calif = row["calificacion"]
        obs = row["observaciones"] or ""

        partes = []
        if periodo:
            partes.append(f"Período: {periodo}")
        if calif is not None:
            partes.append(f"Calificación: {calif}")
        if obs:
            partes.append(obs)

        detalle = " | ".join(partes)

        add_evento_tipo(
            fecha=fecha,
            tipo="capacitacion",
            titulo=f"Capacitación – {agente}",
            detalle=detalle,
            fuente="agentes",
            ref_id=f"CAP-{cap_id}"
        )

    con.commit()
    con.commit()
    con.close()





# =====================================================
# REGENERAR EVENTOS DESDE TABLAS - VEHÍCULOS
# =====================================================

def rebuild_eventos_vehiculos():
    """
    Borra los eventos de fuente 'vehiculos' y los vuelve a generar
    a partir de:
      - vehiculo_estado (service, lavado, seguro, rtv)
      - viajes
      - combustible_cargas
    """
    con = get_db()
    cur = con.cursor()

    # 1) Limpiar eventos viejos de vehículos
    cur.execute("DELETE FROM eventos WHERE fuente = 'vehiculos'")
    con.commit()

    # ===== ESTADO GLOBAL (service / lavado / seguro / rtv) =====
    cur.execute("""
        SELECT
            v.patente,
            v.codigo_interno,
            e.ultimo_service,
            e.proximo_service,
            e.ultimo_lavado,
            e.proximo_lavado,
            e.seguro_inicio,
            e.seguro_vencimiento,
            e.rtv_inicio,
            e.rtv_vencimiento
        FROM vehiculos v
        LEFT JOIN vehiculo_estado e ON e.patente = v.patente
        WHERE v.activo = 1
    """)
    for row in cur.fetchall():
        patente = row["patente"]
        cod_int = row["codigo_interno"] or patente

        # ----- SERVICE -----
        if row["ultimo_service"]:
            add_evento_tipo(
                fecha=row["ultimo_service"],
                tipo="service",
                titulo=f"Service realizado – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"SERV-{patente}-ULT",
                con=con,
            )
        if row["proximo_service"]:
            add_evento_tipo(
                fecha=row["proximo_service"],
                tipo="service",
                titulo=f"Próximo service – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"SERV-{patente}-PROX",
                con=con,
            )

        # ----- LAVADO -----
        if row["ultimo_lavado"]:
            add_evento_tipo(
                fecha=row["ultimo_lavado"],
                tipo="lavado",
                titulo=f"Lavado realizado – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"LAVA-{patente}-ULT",
                con=con,
            )
        if row["proximo_lavado"]:
            add_evento_tipo(
                fecha=row["proximo_lavado"],
                tipo="lavado",
                titulo=f"Próximo lavado – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"LAVA-{patente}-PROX",
                con=con,
            )

        # ----- SEGURO -----
        if row["seguro_inicio"]:
            add_evento_tipo(
                fecha=row["seguro_inicio"],
                tipo="seguro",
                titulo=f"Inicio póliza seguro – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"SEG-{patente}-INI",
                con=con,
            )
        if row["seguro_vencimiento"]:
            add_evento_tipo(
                fecha=row["seguro_vencimiento"],
                tipo="seguro",
                titulo=f"Vencimiento seguro – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"SEG-{patente}-VENC",
                con=con,
            )

        # ----- RTV / VTV -----
        if row["rtv_inicio"]:
            add_evento_tipo(
                fecha=row["rtv_inicio"],
                tipo="rtv",
                titulo=f"Inicio RTV/VTV – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"RTV-{patente}-INI",
                con=con,
            )
        if row["rtv_vencimiento"]:
            add_evento_tipo(
                fecha=row["rtv_vencimiento"],
                tipo="rtv",
                titulo=f"Vencimiento RTV/VTV – {cod_int}",
                detalle=f"Patente {patente}",
                fuente="vehiculos",
                ref_id=f"RTV-{patente}-VENC",
                con=con,
            )

    # ===== VIAJES =====
    cur.execute("""
        SELECT
            vj.id,
            vj.fecha,
            vj.patente,
            vj.recorrido_km,
            vj.largo,
            vj.agente_trasladado,
            d.nombre AS destino_nombre,
            vh.codigo_interno
        FROM viajes vj
        JOIN vehiculos vh ON vh.patente = vj.patente
        LEFT JOIN destinos d ON d.id = vj.destino_id
    """)
    for row in cur.fetchall():
        viaje_id = row["id"]
        cod_int = row["codigo_interno"] or row["patente"]
        fecha = row["fecha"]
        km = row["recorrido_km"] or 0
        largo = row["largo"] or 0
        agente = row["agente_trasladado"] or ""
        destino = row["destino_nombre"] or ""

        if largo == 1 or km >= 100:
            tipo_evt = "viaje_largo"
            etiqueta = "Viaje largo"
        else:
            tipo_evt = "viaje"
            etiqueta = "Viaje"

        titulo = f"{etiqueta} – {cod_int}"
        partes = []
        if destino:
            partes.append(f"Destino: {destino}")
        if agente:
            partes.append(f"Agente: {agente}")
        if km:
            partes.append(f"Recorrido: {km} km")
        detalle = " | ".join(partes)

        add_evento_tipo(
            fecha=fecha,
            tipo=tipo_evt,
            titulo=titulo,
            detalle=detalle,
            fuente="vehiculos",
            ref_id=f"VIAJE-{viaje_id}",
                con=con,
        )

    # ===== CARGAS DE COMBUSTIBLE =====
    cur.execute("""
        SELECT
            c.id,
            c.fecha,
            c.patente,
            c.litros,
            c.precio_total,
            c.km_actual,
            vh.codigo_interno
        FROM combustible_cargas c
        JOIN vehiculos vh ON vh.patente = c.patente
    """)
    for row in cur.fetchall():
        carg_id = row["id"]
        fecha = row["fecha"]
        cod_int = row["codigo_interno"] or row["patente"]
        litros = row["litros"] or 0
        importe = row["precio_total"] or 0
        km = row["km_actual"] or 0

        titulo = f"Carga combustible – {cod_int}"
        detalle = f"{litros} l – ${importe:,.0f} – km {km}".replace(",", ".")

        add_evento_tipo(
            fecha=fecha,
            tipo="carga_combustible",
            titulo=titulo,
            detalle=detalle,
            fuente="vehiculos",
            ref_id=f"COMB-{carg_id}",
                con=con,
        )

    con.close()

def rebuild_eventos_seguridad_limpieza():
    """
    Regenera SOLO los eventos de SEGURIDAD a partir de la tabla REAL: matafuegos_sede.
    Crea dos eventos por matafuego:
      - matafuego_recarga       (fecha_recarga)
      - matafuego_vencimiento   (fecha_vencimiento)
    """
    con = get_db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1) Borrar eventos anteriores de seguridad
    cur.execute("DELETE FROM eventos WHERE fuente = 'seguridad'")
    con.commit()

    # 2) Traer TODOS los matafuegos de la tabla matafuegos_sede
    cur.execute("""
        SELECT id, cod_sede, numero_serie, ubicacion,
               peso_kg, fecha_recarga, fecha_vencimiento
        FROM matafuegos_sede
    """)
    matafuegos = cur.fetchall()

    for m in matafuegos:
        ref_id = f"MF-{m['id']}"

        partes = [f"Sede {m['cod_sede']}"]
        if m["ubicacion"]:
            partes.append(m["ubicacion"])
        if m["peso_kg"] is not None:
            partes.append(f"{m['peso_kg']} kg")
        if m["numero_serie"]:
            partes.append(f"Serie {m['numero_serie']}")

        detalle_base = " · ".join(partes)

        # Evento: RECARGA
        if m["fecha_recarga"]:
            add_evento_tipo(
                fecha=m["fecha_recarga"],
                tipo="matafuego_recarga",
                titulo="Matafuego – Recarga",
                detalle=detalle_base,
                fuente="seguridad",
                ref_id=ref_id,
            )

        # Evento: VENCIMIENTO
        if m["fecha_vencimiento"]:
            add_evento_tipo(
                fecha=m["fecha_vencimiento"],
                tipo="matafuego_vencimiento",
                titulo="Matafuego – Vencimiento",
                detalle=detalle_base,
                fuente="seguridad",
                ref_id=ref_id,
            )

    con.commit()
    con.close()

# =====================================================
# REGENERAR EVENTOS DESDE TABLAS - OBRAS
# =====================================================

def rebuild_eventos_obras():
    """
    Regenera eventos en la tabla 'eventos' a partir de la tabla 'obras_sede'.

    Crea hasta 3 eventos por obra:
      - obra_solicitada  (fecha_solicitud)
      - obra_en_curso    (fecha_inicio)
      - obra_finalizada  (fecha_fin_real)
    """
    con = get_db()
    cur = con.cursor()

    # Borrar eventos anteriores de obras
    cur.execute("DELETE FROM eventos WHERE fuente = 'obras'")
    con.commit()

    cur.execute("""
        SELECT
            o.id,
            o.codigo_sede,
            o.titulo,
            o.tipo,
            o.prioridad,
            o.estado,
            o.fecha_solicitud,
            o.fecha_inicio,
            o.fecha_fin_prevista,
            o.fecha_fin_real,
            s.nombre AS sede_nombre,
            s.ciudad AS sede_ciudad
        FROM obras_sede o
        JOIN sedes_mpd s ON s.codigo = o.codigo_sede
    """)
    for row in cur.fetchall():
        oid = row["id"]
        sede = row["codigo_sede"]
        sede_nombre = row["sede_nombre"]
        ciudad = row["sede_ciudad"]
        titulo = row["titulo"]
        tipo = row["tipo"] or ""
        prioridad = row["prioridad"] or ""
        estado = row["estado"] or ""
        f_sol = row["fecha_solicitud"]
        f_ini = row["fecha_inicio"]
        f_fin = row["fecha_fin_real"]
        f_prev = row["fecha_fin_prevista"]

        base_detalle = f"Sede {sede} – {sede_nombre} ({ciudad}) | Tipo: {tipo} | Prioridad: {prioridad}"

        # Obra solicitada
        if f_sol:
            add_evento_tipo(
                fecha=f_sol,
                tipo="obra_solicitada",
                titulo=f"Obra solicitada – {titulo}",
                detalle=base_detalle,
                fuente="obras",
                ref_id=f"OBRA-{oid}-SOL"
            )

        # Obra en curso
        if f_ini:
            det_ini = base_detalle
            if f_prev:
                det_ini += f" | Fecha prevista: {f_prev}"
            add_evento_tipo(
                fecha=f_ini,
                tipo="obra_en_curso",
                titulo=f"Obra en curso – {titulo}",
                detalle=det_ini,
                fuente="obras",
                ref_id=f"OBRA-{oid}-CUR"
            )

        # Obra finalizada
        if f_fin:
            add_evento_tipo(
                fecha=f_fin,
                tipo="obra_finalizada",
                titulo=f"Obra finalizada – {titulo}",
                detalle=base_detalle,
                fuente="obras",
                ref_id=f"OBRA-{oid}-FIN"
            )

    con.close()
def ensure_cols(con, table, cols_sql):
    """
    cols_sql: lista de tuplas (col_name, col_def_sql)
    ejemplo: [("codigo_sede","TEXT"), ("deposito_codigo","TEXT")]
    """
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    existentes = {r[1] for r in cur.fetchall()}
    for name, defsql in cols_sql:
        if name not in existentes:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {defsql}")
    con.commit()

def ensure_sedes_mpd_cols(con):
    try:
        ensure_cols(con, "sedes_mpd", [
            ("url_planos_drive", "TEXT"),
            ("url_punto_encuentro", "TEXT"),
            ("telefono_sede", "TEXT"),
            ("num_serv_edsa", "TEXT"),
            ("num_serv_gasnor", "TEXT"),
            ("internet_sedes", "TEXT"),
            ("agua_sedes", "TEXT"),
            ("responsable_ejesa", "TEXT"),
            ("protocolo_corte_luz_url", "TEXT"),
            ("protocolo_corte_luz_texto", "TEXT"),
        ])
    except Exception:
        # Si la tabla no existe o hay un error de compatibilidad, seguimos.
        pass


def migrate_taller_depositos():
    con = get_db()

    # 1) Asegurar columnas nuevas (compatibles)
    ensure_cols(con, "taller_items", [
        ("codigo_sede", "TEXT"),
        ("deposito_codigo", "TEXT")  # ej: S08-P00-D08
    ])

    ensure_cols(con, "depositos_items", [
        ("codigo_sede", "TEXT"),
        ("deposito_codigo", "TEXT")  # ej: S08-P00-D09 / S12-P02-D26
    ])

    con.close()

def rebuild_eventos_inventario():
    """
    Regenera eventos en la tabla 'eventos' a partir de:
      - movimientos_mobiliario
    (Más adelante se pueden sumar controles de stock, altas, etc.)
    """
    con = get_db()
    cur = con.cursor()

    # Borrar eventos anteriores de inventario
    cur.execute("DELETE FROM eventos WHERE fuente = 'inventario'")
    con.commit()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventario_sede (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        sede_codigo     TEXT NOT NULL,
        deposito_codigo TEXT NOT NULL,
        aire_marca      INTEGER DEFAULT 0,
        escritorio_prof INTEGER DEFAULT 0,
        mesa_pc         INTEGER DEFAULT 0,
        silla_giratoria INTEGER DEFAULT 0,
        silla_fija      INTEGER DEFAULT 0,
        armario_alto    INTEGER DEFAULT 0,
        biblioteca_baja INTEGER DEFAULT 0,
        otros           INTEGER DEFAULT 0
    );
    """)


    # ---------------------------
    # CHECKLIST VISITAS INTERIOR
    # ---------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checklist_visitas_interior(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        chofer TEXT,
        vehiculo TEXT,
        -- horarios estimativos / reales por tramo
        tilcara_hora TEXT,
        humapenal_hora TEXT,
        humacivil_hora TEXT,
        abrapampa_hora TEXT,
        laquiaca_hora TEXT,
        -- día previo: verificación general
        doc_ok INTEGER DEFAULT 0,
        vehiculo_ok INTEGER DEFAULT 0,
        materiales_ok INTEGER DEFAULT 0,
        herramientas_ok INTEGER DEFAULT 0,
        insumos_ok INTEGER DEFAULT 0,
        expediente_ok INTEGER DEFAULT 0,
        -- tareas de intendencia
        tareas_previstas TEXT,
        tareas_realizadas TEXT,
        observaciones TEXT,
        -- cierre de viaje
        hora_regreso_s08 TEXT,
        check_reg_vehiculo_ok INTEGER DEFAULT 0
    )
    """)

    # ---------------------------
    # CHECKLIST CONTROL INVENTARIO / MOBILIARIO
    # ---------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checklist_inventario_control(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,              -- día del control

        inventario_id INTEGER NOT NULL,   -- fila de inventario_sede
        sede_codigo   TEXT NOT NULL,      -- S01, S02, ...
        deposito_codigo TEXT NOT NULL,    -- P00-D01, etc.

        agente_id     INTEGER,            -- id de agentes_intendencia (opcional)
        agente_nombre TEXT,               -- nombre del agente al momento del control

        -- snapshot inventario OFICIAL al momento del control
        aire_marca_oficial      INTEGER DEFAULT 0,
        escritorio_prof_oficial INTEGER DEFAULT 0,
        mesa_pc_oficial         INTEGER DEFAULT 0,
        silla_giratoria_oficial INTEGER DEFAULT 0,
        silla_fija_oficial      INTEGER DEFAULT 0,
        armario_alto_oficial    INTEGER DEFAULT 0,
        biblioteca_baja_oficial INTEGER DEFAULT 0,
        otros_oficial           INTEGER DEFAULT 0,

        -- recuento REAL del día del control
        aire_marca_control      INTEGER DEFAULT 0,
        escritorio_prof_control INTEGER DEFAULT 0,
        mesa_pc_control         INTEGER DEFAULT 0,
        silla_giratoria_control INTEGER DEFAULT 0,
        silla_fija_control      INTEGER DEFAULT 0,
        armario_alto_control    INTEGER DEFAULT 0,
        biblioteca_baja_control INTEGER DEFAULT 0,
        otros_control           INTEGER DEFAULT 0,

        observaciones TEXT,

        FOREIGN KEY(inventario_id) REFERENCES inventario_sede(id)
    )
    """)


    # -----------------------------------------------
    # MOVIMIENTOS DE MOBILIARIO
    # -----------------------------------------------
    cur.execute("""
        SELECT
            id,
            fecha,
            item,
            cantidad,
            sede_origen,
            deposito_origen,
            sede_destino,
            deposito_destino,
            observaciones
        FROM movimientos_mobiliario
    """)
    for row in cur.fetchall():
        mid = row["id"]
        fecha = row["fecha"]
        item = row["item"]
        cant = row["cantidad"] or 1
        so = row["sede_origen"] or ""
        do = row["deposito_origen"] or ""
        sd = row["sede_destino"] or ""
        dd = row["deposito_destino"] or ""
        obs = row["observaciones"] or ""

        partes = [f"Item: {item} (x{cant})"]
        if so or sd:
            partes.append(f"{so or 'sin sede'} ({do}) → {sd or 'sin sede'} ({dd})")
        if obs:
            partes.append(obs)

        detalle = " | ".join(partes)

        add_evento_tipo(
            fecha=fecha,
            tipo="mobiliario_mov",
            titulo=f"Movimiento mobiliario – {item}",
            detalle=detalle,
            fuente="inventario",
            ref_id=f"MOVMOB-{mid}"
        )

    con.close()




def init_tabla_calendario_eventos():
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendario_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,          -- '2025-12-01'
            titulo TEXT NOT NULL,         -- 'Licencia – Emiliano...'
            detalle TEXT,                 -- texto largo con info
            area TEXT,                    -- 'AGENTES', 'OBRAS', 'SEGURIDAD/LIMPIEZA', etc.
            tipo_evento TEXT,             -- 'licencia', 'matafuego_recarga', etc.
            ref_id TEXT,                  -- ID de referencia al módulo origen (LIC-2, MF-3…)
            fuente TEXT                   -- 'agentes', 'obras', 'seguridad', etc.
        )
    """)
    con.commit()
    con.close()


app = Flask(__name__)
app.secret_key = "mpd-intendencia-2025"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads", "remitos")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mpd.db")

PROTOCOLOS_DIR = os.path.join(BASE_DIR, "static", "protocolos_limpieza")
os.makedirs(PROTOCOLOS_DIR, exist_ok=True)
PROTOCOLOS_LIMPIEZA_POR_SEDE = {
    "S13": "https://docs.google.com/document/d/1nig-ryH4y5oIJwdMwi3YkDDL4PCYRhfjFjwEqHBJ__Y/edit?usp=sharing",
    "S08": "https://docs.google.com/document/d/1E_-a465MCRTWwkVMfi8tVpUdXhQD1Z7a3lAEbWpFI6E/edit?usp=drive_link",
    "S01": "https://docs.google.com/document/d/1YAYhnbibJtmxvudKA2jdO7zoEroKfeiIAnwONEXFDkQ/edit?usp=sharing",
    "S14": "https://docs.google.com/document/d/1b-6KQyekm2Gfev7nkS-dn7NAbKxDVOPtarXb2HYIzzk/edit?usp=sharing",
}

FOTOS_DRIVE_URL = "https://drive.google.com/drive/folders/1rQfUwlcFmLJ-AnRj8GC2lCAvfzK5X4SU"

# --------- CARPETA PARA PLANOS (PDF/IMÁGENES) ----------
PLANOS_DIR = os.path.join(BASE_DIR, "static", "planos_sedes")
os.makedirs(PLANOS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS_PLANOS = {"pdf", "jpg", "jpeg", "png"}

def plano_permitido(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS_PLANOS


def plano_permitido(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS_PLANOS

def get_db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 10000")
    return con

def get_db_connection():
    return get_db()


# =========================
# AUTH BLUEPRINT (refactor seguro)
# =========================
from app.auth import bp as auth_bp
from app.auth.routes import register_auth
register_auth(auth_bp, get_db, ensure_auth_tables, default_redirect_for_role)
app.register_blueprint(auth_bp)
# Compatibilidad: alias de endpoints sin blueprint
if "auth.login" in app.view_functions:
    app.view_functions.setdefault("login", app.view_functions["auth.login"])
    app.add_url_rule(
        "/login",
        endpoint="login",
        view_func=app.view_functions["auth.login"],
        methods=["GET", "POST"],
    )
if "auth.logout" in app.view_functions:
    app.view_functions.setdefault("logout", app.view_functions["auth.logout"])
    app.add_url_rule(
        "/logout",
        endpoint="logout",
        view_func=app.view_functions["auth.logout"],
        methods=["GET"],
    )
if "auth.password_change" in app.view_functions:
    app.view_functions.setdefault("password_change", app.view_functions["auth.password_change"])
    app.add_url_rule(
        "/password",
        endpoint="password_change",
        view_func=app.view_functions["auth.password_change"],
        methods=["GET", "POST"],
    )
if "auth.access_denied" in app.view_functions:
    app.view_functions.setdefault("access_denied", app.view_functions["auth.access_denied"])
    app.add_url_rule(
        "/acceso-denegado",
        endpoint="access_denied",
        view_func=app.view_functions["auth.access_denied"],
        methods=["GET"],
    )

# Alias sedes_home -> sedes_resumen_mpd (compatibilidad url_for)
if "sedes_resumen_mpd" in app.view_functions:
    app.view_functions.setdefault("sedes_home", app.view_functions["sedes_resumen_mpd"])

# =========================
# NOVEDADES / DASHBOARD BLUEPRINT (refactor seguro)
# =========================
from app.novedades import bp as novedades_bp
from app.novedades.routes import register_novedades
register_novedades(novedades_bp, get_db)
app.register_blueprint(novedades_bp)
# Compatibilidad: alias de endpoints de dashboard sin blueprint
if "novedades.dashboard" in app.view_functions:
    app.view_functions.setdefault("dashboard", app.view_functions["novedades.dashboard"])
    app.add_url_rule(
        "/",
        endpoint="dashboard",
        view_func=app.view_functions["novedades.dashboard"],
        methods=["GET"],
    )
if "novedades.dashboard_exec" in app.view_functions:
    app.view_functions.setdefault("dashboard_exec", app.view_functions["novedades.dashboard_exec"])
    app.add_url_rule(
        "/dashboard",
        endpoint="dashboard_exec",
        view_func=app.view_functions["novedades.dashboard_exec"],
        methods=["GET"],
    )
if "novedades.dashboard_gestion" in app.view_functions:
    app.view_functions.setdefault("dashboard_gestion", app.view_functions["novedades.dashboard_gestion"])
    app.add_url_rule(
        "/dashboard/gestion",
        endpoint="dashboard_gestion",
        view_func=app.view_functions["novedades.dashboard_gestion"],
        methods=["GET"],
    )

# =========================
# VEHICULOS CONTROL DIARIO (blueprint parcial)
# =========================
from app.vehiculos import bp as vehiculos_bp
from app.vehiculos.routes import register_vehiculos_control
register_vehiculos_control(vehiculos_bp, get_db_connection, ensure_cols, rebuild_eventos_vehiculos)
app.register_blueprint(vehiculos_bp)
try:
    # Alias de endpoints sin blueprint para compatibilidad con url_for existentes
    if "vehiculos.vehiculos_control_diario" in app.view_functions:
        app.view_functions.setdefault(
            "vehiculos_control_diario",
            app.view_functions["vehiculos.vehiculos_control_diario"],
        )
        app.add_url_rule(
            "/vehiculos/control_diario",
            endpoint="vehiculos_control_diario",
            view_func=app.view_functions["vehiculos.vehiculos_control_diario"],
            methods=["GET", "POST"],
        )
    if "vehiculos.vehiculos_home" in app.view_functions:
        app.view_functions.setdefault("vehiculos_home", app.view_functions["vehiculos.vehiculos_home"])
        app.add_url_rule(
            "/vehiculos",
            endpoint="vehiculos_home",
            view_func=app.view_functions["vehiculos.vehiculos_home"],
            methods=["GET", "POST"],
        )
    if "vehiculos.viaje_editar" in app.view_functions:
        app.view_functions.setdefault("viaje_editar", app.view_functions["vehiculos.viaje_editar"])
        app.add_url_rule(
            "/viajes/<int:viaje_id>/editar",
            endpoint="viaje_editar",
            view_func=app.view_functions["vehiculos.viaje_editar"],
            methods=["GET", "POST"],
        )
    if "vehiculos.viaje_editar2" in app.view_functions:
        app.view_functions.setdefault("viaje_editar2", app.view_functions["vehiculos.viaje_editar2"])
        app.add_url_rule(
            "/viajes/<int:viaje_id>/editar2",
            endpoint="viaje_editar2",
            view_func=app.view_functions["vehiculos.viaje_editar2"],
            methods=["GET", "POST"],
        )
    if "vehiculos.viaje_cerrar" in app.view_functions:
        app.view_functions.setdefault("viaje_cerrar", app.view_functions["vehiculos.viaje_cerrar"])
        app.add_url_rule(
            "/viajes/<int:viaje_id>/cerrar",
            endpoint="viaje_cerrar",
            view_func=app.view_functions["vehiculos.viaje_cerrar"],
            methods=["GET", "POST"],
        )
    if "vehiculos.viaje_eliminar" in app.view_functions:
        app.view_functions.setdefault("viaje_eliminar", app.view_functions["vehiculos.viaje_eliminar"])
        app.add_url_rule(
            "/vehiculos/viaje/<int:viaje_id>/eliminar",
            endpoint="viaje_eliminar",
            view_func=app.view_functions["vehiculos.viaje_eliminar"],
            methods=["POST"],
        )
except Exception:
    # No bloquear el arranque por alias
    pass



@app.before_request
def enforce_auth():
    if request.path.startswith("/static"):
        return None
    if request.endpoint in {"login", "logout", "password_change", "access_denied",
                            "auth.login", "auth.logout", "auth.password_change", "auth.access_denied"}:
        return None

    con = get_db()
    try:
        ensure_auth_tables(con)
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "database is locked" in msg or "database table is locked" in msg:
            row = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'"
            ).fetchone()
            if not row:
                con.close()
                raise
        else:
            con.close()
            raise
    finally:
        try:
            con.close()
        except Exception:
            pass

    if not session.get("user_id"):
        return redirect(url_for("login", next=request.path))

    if session.get("must_change") and request.endpoint not in {"password_change", "auth.password_change"}:
        return redirect(url_for("password_change"))

    role = session.get("role")
    module = module_from_path(request.path)
    if not role_allows(role, module):
        if role == ROLE_DASH_OBRAS:
            return redirect(url_for("dashboard"))
        if role == ROLE_DASH_VEHICULOS:
            return redirect(url_for("dashboard"))
        if role == ROLE_DASH_SOLO:
            return redirect(url_for("dashboard_exec"))
        if role == ROLE_OPERATIVO_CLAVE:
            return redirect(url_for("dashboard_exec"))
        if role == ROLE_CONTROL_SEDES:
            return redirect(url_for("sedes_resumen_mpd"))
        if role == ROLE_SEDE_VEHICULOS:
            return redirect(url_for("sede_ficha", codigo="S01", home=1))
        if role == ROLE_SST_VEHICULOS:
            return redirect(url_for("sst_general"))
        if role == ROLE_OBRAS_VEHICULOS:
            return redirect(url_for("obras_home"))
        if role == ROLE_INT_OBRAS:
            return redirect(url_for("obras_home"))
        if role == ROLE_INT_OBRAS_RELEV:
            return redirect(url_for("obras_home"))
        if role == ROLE_INT_OBRAS_SEDES:
            return redirect(url_for("obras_home"))
        if role == ROLE_INT_VEHICULOS:
            return redirect(url_for("vehiculos_control_diario"))
        return redirect(url_for("access_denied"))

    return None

@app.context_processor
def inject_auth_context():
    current_user = None
    if session.get("user_id"):
        current_user = {
            "username": session.get("username"),
            "full_name": session.get("full_name"),
            "role": session.get("role"),
        }

    def can_access(module: str) -> bool:
        return role_allows(session.get("role"), module)

    return {
        "current_user": current_user,
        "user_role": session.get("role"),
        "can_access": can_access,
    }



def ensure_sedes_metricas_table():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sedes_metricas (
            sede_codigo TEXT PRIMARY KEY,
            m2_totales REAL,
            personas INTEGER,
            oficinas INTEGER,
            depositos INTEGER,
            actualizado_en TEXT
        )
    """)
    con.commit()
    con.close()

def ensure_evacuacion_responsables_table():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evacuacion_responsables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sede_codigo TEXT NOT NULL,
            piso TEXT NOT NULL,
            responsable TEXT,
            UNIQUE(sede_codigo, piso)
        )
    """)
    con.commit()
    con.close()

def ensure_sedes_particularidades_table():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sedes_particularidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sede_codigo TEXT NOT NULL,
            titulo TEXT,
            detalle TEXT,
            creado_en TEXT DEFAULT (datetime('now')),
            actualizado_en TEXT
        )
    """)
    con.commit()
    con.close()


def ensure_luminarias_columns():
    con = get_db()
    cur = con.cursor()
    cols = [r["name"] for r in cur.execute("PRAGMA table_info(luminarias_sede)").fetchall()]
    if "puestos_trabajo" not in cols:
        cur.execute("ALTER TABLE luminarias_sede ADD COLUMN puestos_trabajo INTEGER DEFAULT 0")
    con.commit()
    con.close()




register_auditorias(app, get_db)
register_obras(app, get_db, rebuild_eventos_obras)
register_agentes(app, get_db, ensure_cols, rebuild_eventos_agentes, allowed_agente_doc, AGENTE_DOCS_FOLDER)
register_mapa(app, get_db)
register_vehiculos(app, get_db, get_db_connection, ensure_cols, ensure_combustible_columns, rebuild_eventos_vehiculos)
register_inventario_checklist(app, get_db)
register_inventario_general(app, get_db, get_db_connection, ensure_luminarias_columns)
rebuild_eventos_limpieza_sede = register_sst(
    app,
    get_db,
    ensure_cols,
    ensure_sedes_mpd_cols,
    CAL_COLORS,
    ensure_auth_tables,
    default_redirect_for_role,
)

def ensure_materiales_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS materiales_stock(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            item TEXT NOT NULL,
            unidad TEXT NOT NULL,
            cantidad REAL DEFAULT 0,
            objetivo REAL,
            observaciones TEXT,
            creado_en TEXT DEFAULT (datetime('now'))
        )
    """)
    con.commit()


@app.route("/capacitaciones/gantt")
def capacitaciones_gantt():
    pdf_path = os.path.join(app.root_path, "static", "docs", "capacitaciones_gantt_sgi.pdf")
    return send_file(pdf_path, as_attachment=False)




@app.route("/checklist/vehiculos-mensual")
def checklist_vehiculos_mensual():
    return render_template("checklist_vehiculos_mensual.html")


@app.route("/checklist/tareas-especificas")
def checklist_tareas_especificas():
    return render_template("checklist_tareas_especificas.html")


@app.route("/checklist/seguridad")
def checklist_seguridad_general():
    return render_template("checklist_seguridad_general.html")


@app.route("/sedes/<codigo>/seguridad/checklist", methods=["GET","POST"],
           endpoint="checklist_seguridad_form")
def checklist_seguridad_form(codigo):
    con = get_db()
    con.row_factory = sqlite3.Row

    sede = con.execute("SELECT * FROM sedes_mpd WHERE codigo = ?", (codigo,)).fetchone()
    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        con.execute("""
            INSERT INTO checklist_seguridad
            (cod_sede, fecha, matafuegos_ok, senaletica_ok, luces_ok,
             botiquin_ok, evacuacion_ok, orden_ok, observaciones)
            VALUES (?, DATE('now'), ?, ?, ?, ?, ?, ?, ?)
        """, (
            codigo,
            1 if request.form.get("matafuegos_ok") else 0,
            1 if request.form.get("senaletica_ok") else 0,
            1 if request.form.get("luces_ok") else 0,
            1 if request.form.get("botiquin_ok") else 0,
            1 if request.form.get("evacuacion_ok") else 0,
            1 if request.form.get("orden_ok") else 0,
            request.form.get("observaciones")
        ))

        con.commit()
        con.close()
        flash("Checklist registrado", "success")
        return redirect(url_for("sede_seguridad", codigo=codigo))

    con.close()
    return render_template("checklist_seguridad_form.html", sede=sede)

from datetime import date  # arriba ya lo tenés, si está no lo repitas


@app.route("/checklist/luminarias", methods=["GET", "POST"], endpoint="checklist_luminarias")
def checklist_luminarias():
    conn = get_db_connection()
    cur = conn.cursor()

    # 1) Tabla checklist + columna cantidad
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checklist_luminarias(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        sede_codigo TEXT NOT NULL,
        ambiente TEXT,
        tipo TEXT NOT NULL,        -- tubo_led / panel_led / foco_comun / otro
        color_luz TEXT NOT NULL,   -- fria / calida
        potencia TEXT,
        motivo TEXT,
        instalado_por TEXT,
        observaciones TEXT
        -- columna cantidad se agrega aparte
    )
    """)
    # Asegurar columna 'cantidad'
    cur.execute("PRAGMA table_info(checklist_luminarias)")
    cols = [c[1] for c in cur.fetchall()]
    if "cantidad" not in cols:
        cur.execute("ALTER TABLE checklist_luminarias ADD COLUMN cantidad INTEGER DEFAULT 1")

    # 2) Tabla de movimientos de stock de luminarias
    cur.execute("""
    CREATE TABLE IF NOT EXISTS luminarias_stock_mov(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        tipo TEXT NOT NULL,
        color_luz TEXT,
        potencia TEXT,
        movimiento TEXT NOT NULL,      -- ingreso / egreso
        cantidad INTEGER NOT NULL,
        origen TEXT,
        ref_id INTEGER,
        observaciones TEXT
    )
    """)

    # 3) Sedes para el combo
    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    from datetime import date as _date

    # 4) Alta de checklist + egreso automático de stock
    if request.method == "POST":
        fecha = request.form.get("fecha") or _date.today().isoformat()
        sede_codigo = request.form.get("sede_codigo") or ""
        ambiente = request.form.get("ambiente") or ""
        tipo = request.form.get("tipo") or ""
        color_luz = request.form.get("color_luz") or ""
        potencia = request.form.get("potencia") or ""
        motivo = request.form.get("motivo") or ""
        instalado_por = request.form.get("instalado_por") or ""
        observaciones = request.form.get("observaciones") or ""
        cantidad_raw = request.form.get("cantidad") or "1"

        try:
            cantidad = int(cantidad_raw)
            if cantidad <= 0:
                cantidad = 1
        except ValueError:
            cantidad = 1

        if not (fecha and sede_codigo and tipo and color_luz):
            flash("⚠️ Completá al menos fecha, sede, tipo y color de luz.", "warning")
        else:
            # Inserto el checklist
            cur.execute("""
                INSERT INTO checklist_luminarias
                    (fecha, sede_codigo, ambiente, tipo, color_luz, potencia,
                     motivo, instalado_por, observaciones, cantidad)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                fecha, sede_codigo, ambiente, tipo, color_luz, potencia,
                motivo, instalado_por, observaciones, cantidad
            ))
            # id del checklist recién creado
            cur.execute("SELECT last_insert_rowid()")
            check_id = cur.fetchone()[0]

            # Egreso automático de stock
            cur.execute("""
                INSERT INTO luminarias_stock_mov
                    (fecha, tipo, color_luz, potencia, movimiento,
                     cantidad, origen, ref_id, observaciones)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                fecha, tipo, color_luz, potencia,
                "egreso",
                cantidad,
                "checklist_luminarias",
                check_id,
                f"Sede {sede_codigo} - {ambiente or ''} - Motivo: {motivo or ''}"
            ))

            conn.commit()
            flash("✅ Cambio de luminaria registrado y stock actualizado.", "success")
            return redirect(url_for("checklist_luminarias"))

    # 5) Historial + filtro por sede
    sede_filtro = request.args.get("sede_filtro", "").strip()
    base_query = "SELECT * FROM checklist_luminarias"
    params = []

    if sede_filtro:
        base_query += " WHERE sede_codigo = ?"
        params.append(sede_filtro)

    base_query += " ORDER BY date(fecha) DESC, id DESC LIMIT 200"
    registros = cur.execute(base_query, params).fetchall()

    # 6) KPIs (totales, mes actual, top sedes, top motivos)
    hoy = _date.today()
    mes_actual = hoy.strftime("%Y-%m")

    total_cambios = cur.execute(
        "SELECT COUNT(*) FROM checklist_luminarias"
    ).fetchone()[0] or 0

    cambios_mes = cur.execute(
        "SELECT COUNT(*) FROM checklist_luminarias WHERE strftime('%Y-%m', fecha)=?",
        (mes_actual,)
    ).fetchone()[0] or 0

    # top sedes
    top_sedes = cur.execute("""
        SELECT sede_codigo, COUNT(*) AS total
        FROM checklist_luminarias
        GROUP BY sede_codigo
        ORDER BY total DESC
        LIMIT 5
    """).fetchall()

    # top motivos
    top_motivos = cur.execute("""
        SELECT motivo, COUNT(*) AS total
        FROM checklist_luminarias
        WHERE motivo IS NOT NULL AND motivo <> ''
        GROUP BY motivo
        ORDER BY total DESC
        LIMIT 5
    """).fetchall()

    # top tipos
    top_tipos = cur.execute("""
        SELECT tipo, COUNT(*) AS total
        FROM checklist_luminarias
        GROUP BY tipo
        ORDER BY total DESC
    """).fetchall()

    conn.close()

    hoy_str = hoy.isoformat()

    return render_template(
        "checklist_luminarias.html",
        sedes=sedes,
        registros=registros,
        sede_filtro=sede_filtro,
        hoy=hoy_str,
        total_cambios=total_cambios,
        cambios_mes=cambios_mes,
        top_sedes=top_sedes,
        top_motivos=top_motivos,
        top_tipos=top_tipos,
        mes_actual=mes_actual
    )



@app.route("/inventario/luminarias-stock", methods=["GET", "POST"], endpoint="luminarias_stock")
def luminarias_stock():
    conn = get_db_connection()
    cur = conn.cursor()

    # Aseguro tabla de movimientos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS luminarias_stock_mov(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        tipo TEXT NOT NULL,
        color_luz TEXT,
        potencia TEXT,
        movimiento TEXT NOT NULL,      -- ingreso / egreso
        cantidad INTEGER NOT NULL,
        origen TEXT,
        ref_id INTEGER,
        observaciones TEXT
    )
    """)



    # Alta de movimiento manual (compra / ajuste)
    if request.method == "POST":
        fecha = request.form.get("fecha") or _date.today().isoformat()
        tipo = request.form.get("tipo") or ""
        color_luz = request.form.get("color_luz") or ""
        potencia = request.form.get("potencia") or ""
        movimiento = request.form.get("movimiento") or "ingreso"
        cantidad_raw = request.form.get("cantidad") or "1"
        observaciones = request.form.get("observaciones") or ""

        try:
            cantidad = int(cantidad_raw)
            if cantidad <= 0:
                cantidad = 1
        except ValueError:
            cantidad = 1

        if not tipo:
            flash("⚠️ Indicá al menos el tipo de luminaria.", "warning")
        else:
            cur.execute("""
                INSERT INTO luminarias_stock_mov
                    (fecha, tipo, color_luz, potencia, movimiento,
                     cantidad, origen, ref_id, observaciones)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                fecha, tipo, color_luz, potencia,
                movimiento,
                cantidad,
                "manual",
                None,
                observaciones
            ))
            conn.commit()
            flash("✅ Movimiento de stock registrado.", "success")
            return redirect(url_for("luminarias_stock"))

    # Stock actual por tipo + color + potencia
    stock_rows = cur.execute("""
        SELECT
          tipo,
          COALESCE(color_luz, '') AS color_luz,
          COALESCE(potencia, '') AS potencia,
          SUM(
            CASE
              WHEN movimiento = 'ingreso' THEN cantidad
              ELSE -cantidad
            END
          ) AS stock_actual
        FROM luminarias_stock_mov
        GROUP BY tipo, COALESCE(color_luz, ''), COALESCE(potencia, '')
        HAVING stock_actual <> 0
        ORDER BY tipo, color_luz, potencia
    """).fetchall()

    # Últimos movimientos
    movimientos = cur.execute("""
        SELECT *
        FROM luminarias_stock_mov
        ORDER BY date(fecha) DESC, id DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    hoy = _date.today().isoformat()

    return render_template(
        "luminarias_stock.html",
        stock_rows=stock_rows,
        movimientos=movimientos,
        hoy=hoy
    )


@app.route("/checklist/tareas")
def checklist_tareas():
    return render_template("checklist_tareas.html")



@app.route("/checklist/espacios-comunes")
def checklist_espacios_comunes():
    return render_template("checklist_espacios_comunes.html")


@app.route("/checklist/matafuegos", methods=["GET", "POST"])
def checklist_matafuegos():
    con = get_db_connection()
    cur = con.cursor()

    # Sedes para el combo
    sedes = cur.execute("SELECT codigo, nombre FROM sedes ORDER BY codigo").fetchall()

    if request.method == "POST":
        fecha        = request.form.get("fecha")
        cod_sede     = request.form.get("cod_sede")
        responsable  = request.form.get("responsable", "").strip()
        estado       = request.form.get("estado")    # ok / faltan / reemplazar
        observaciones = request.form.get("observaciones", "").strip()

        cur.execute("""
            INSERT INTO checklist_matafuegos (fecha, cod_sede, responsable, estado, observaciones)
            VALUES (?,?,?,?,?)
        """, (fecha, cod_sede, responsable, estado, observaciones))
        con.commit()
        flash("Control de matafuegos registrado.", "success")

    # Últimos controles (para que veas cómo venís)
    controles = cur.execute("""
        SELECT c.*, s.nombre AS sede_nombre
        FROM checklist_matafuegos c
        LEFT JOIN sedes s ON s.codigo = c.cod_sede
        ORDER BY fecha DESC, cod_sede
        LIMIT 30
    """).fetchall()

    con.close()
    return render_template(
        "checklist_matafuegos.html",
        sedes=sedes,
        controles=controles
    )



@app.route("/materiales", methods=["GET", "POST"], endpoint="materiales_home")
def materiales_home():
    con = get_db()
    ensure_materiales_table(con)

    if request.method == "POST":
        categoria = (request.form.get("categoria") or "").strip()
        item = (request.form.get("item") or "").strip()
        unidad = (request.form.get("unidad") or "").strip()
        cantidad = (request.form.get("cantidad") or "").strip()
        objetivo = (request.form.get("objetivo") or "").strip()
        observaciones = (request.form.get("observaciones") or "").strip()

        if not categoria or not item or not unidad:
            flash("Categoria, item y unidad son obligatorios.", "warning")
        else:
            try:
                cant_val = float(cantidad) if cantidad != "" else 0
            except Exception:
                cant_val = 0
            try:
                obj_val = float(objetivo) if objetivo != "" else None
            except Exception:
                obj_val = None
            con.execute("""
                INSERT INTO materiales_stock
                    (categoria, item, unidad, cantidad, objetivo, observaciones)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (categoria, item, unidad, cant_val, obj_val, observaciones))
            con.commit()
            flash("Material agregado.", "success")

    materiales = con.execute("""
        SELECT *
        FROM materiales_stock
        ORDER BY categoria, item
    """).fetchall()
    con.close()

    return render_template("materiales_home.html", materiales=materiales)



@app.route("/materiales/<int:mid>/ajustar", methods=["POST"], endpoint="materiales_ajustar")
def materiales_ajustar(mid):
    delta = (request.form.get("delta") or "").strip()
    try:
        delta_val = float(delta)
    except Exception:
        delta_val = 0
    con = get_db()
    ensure_materiales_table(con)
    con.execute("""
        UPDATE materiales_stock
        SET cantidad = COALESCE(cantidad, 0) + ?
        WHERE id = ?
    """, (delta_val, mid))
    con.commit()
    con.close()
    flash("Cantidad actualizada.", "success")
    return redirect(url_for("materiales_home"))



@app.route("/materiales/<int:mid>/editar", methods=["POST"], endpoint="materiales_editar")
def materiales_editar(mid):
    categoria = (request.form.get("categoria") or "").strip()
    item = (request.form.get("item") or "").strip()
    unidad = (request.form.get("unidad") or "").strip()
    cantidad = (request.form.get("cantidad") or "").strip()
    objetivo = (request.form.get("objetivo") or "").strip()
    observaciones = (request.form.get("observaciones") or "").strip()

    try:
        cant_val = float(cantidad) if cantidad != "" else 0
    except Exception:
        cant_val = 0
    try:
        obj_val = float(objetivo) if objetivo != "" else None
    except Exception:
        obj_val = None

    con = get_db()
    ensure_materiales_table(con)
    con.execute("""
        UPDATE materiales_stock
        SET categoria = ?,
            item = ?,
            unidad = ?,
            cantidad = ?,
            objetivo = ?,
            observaciones = ?
        WHERE id = ?
    """, (categoria, item, unidad, cant_val, obj_val, observaciones, mid))
    con.commit()
    con.close()
    flash("Material actualizado.", "success")
    return redirect(url_for("materiales_home"))



@app.route("/materiales/<int:mid>/eliminar", methods=["POST"], endpoint="materiales_eliminar")
def materiales_eliminar(mid):
    con = get_db()
    ensure_materiales_table(con)
    con.execute("DELETE FROM materiales_stock WHERE id = ?", (mid,))
    con.commit()
    con.close()
    flash("Material eliminado.", "success")
    return redirect(url_for("materiales_home"))



@app.route("/checklist/pavas-caloventores")
def checklist_pavas_caloventores():
    return render_template("checklist_pavas_caloventores.html")


@app.route("/checklist/higiene-sedes")
def checklist_higiene_sedes():
    return render_template("checklist_higiene_sedes.html")

# =========================
# LICENCIAS DE AGENTES
# =========================

# =========================
# EPP / HERRAMIENTAS
# =========================

@app.route("/sedes/<codigo>/fotos", methods=["GET", "POST"], endpoint="sede_fotos")
def sede_fotos(codigo):
    # Registro fotografico ahora se gestiona en Drive para evitar peso en el servidor.
    con = get_db()
    sede = con.execute("""
        SELECT url_planos_drive
        FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()
    con.close()
    drive_url = (sede["url_planos_drive"] if sede else None) or FOTOS_DRIVE_URL
    return redirect(drive_url)

# =========================
# FICHA BÁSICA DE SEDE
# =========================

# =========================
# PLANOS E INFRAESTRUCTURA
# =========================




# ------------------------------------------------
# RUTA: LIMPIEZA Y PROTOCOLO POR SEDE
# ------------------------------------------------
@app.route("/sedes/<codigo>/limpieza", methods=["GET", "POST"])
def sede_limpieza(codigo):
    codigo_norm = (codigo or "").strip().upper()
    con = get_db_connection()

    # 1) Datos basicos de la sede
    sede = con.execute(
        "SELECT * FROM sedes_mpd WHERE codigo = ?",
        (codigo_norm,)
    ).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "error")
        return redirect(url_for("dashboard"))

    # 2) Agentes de limpieza (combo)
    agentes_limpieza = con.execute("""
        SELECT id, agente, telefono
        FROM agentes
        WHERE rubro = 'Limpieza'
        ORDER BY agente
    """).fetchall()

    # -------------------- POST: GUARDAR ASIGNACION / PROTOCOLO --------------------
    if request.method == "POST":
        accion = request.form.get("accion", "")

        # 2.a) Nueva asignacion de limpieza
        if accion == "asignar_limpieza":
            agente_id = request.form.get("agente_id") or None
            turno = (request.form.get("turno") or "").strip()
            frecuencia = (request.form.get("frecuencia") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()
            fecha_desde = (request.form.get("fecha_desde") or "").strip()
            fecha_hasta = (request.form.get("fecha_hasta") or "").strip()

            responsable = None

            if agente_id:
                fila_ag = con.execute(
                    "SELECT agente FROM agentes WHERE id = ?",
                    (agente_id,)
                ).fetchone()
                if fila_ag:
                    responsable = fila_ag["agente"]

            # Si no encontro agente, al menos guardamos el responsable como texto
            if not responsable:
                responsable = "s/d"

            hoy = date.today().isoformat()

            con.execute("""
                INSERT INTO sedes_limpieza (
                    cod_sede,
                    responsable,
                    turno,
                    frecuencia,
                    observaciones,
                    protocolo_url,
                    agente_id,
                    fecha_actualizacion,
                    fecha_desde,
                    fecha_hasta
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                codigo_norm,
                responsable,
                turno,
                frecuencia,
                observaciones,
                None,              # protocolo_url (no se toca aca)
                agente_id,
                hoy,
                fecha_desde or None,
                fecha_hasta or None
            ))

            con.commit()
            con.close()

            # Regenerar eventos de limpieza en el calendario general
            rebuild_eventos_limpieza_sede()

            flash("Asignacion de limpieza guardada.", "ok")
            return redirect(url_for("sede_limpieza", codigo=codigo_norm))

    # -------------------- GET: ARMAR PANTALLA --------------------

    # 3) Resumen actual (chips superiores) -> ultimos 3 registros
    resumen = con.execute("""
        SELECT responsable, turno, frecuencia
        FROM sedes_limpieza
        WHERE cod_sede = ?
        ORDER BY id DESC
        LIMIT 3
    """, (codigo_norm,)).fetchall()

    # 4) Ultima actualizacion
    fila_ultima = con.execute("""
        SELECT fecha_actualizacion
        FROM sedes_limpieza
        WHERE cod_sede = ?
        ORDER BY id DESC
        LIMIT 1
    """, (codigo_norm,)).fetchone()
    ultima_actualizacion = fila_ultima["fecha_actualizacion"] if fila_ultima else None

    # 5) Historial completo (con id, contacto y fechas)
    limpieza_lista = con.execute("""
        SELECT
            l.id,
            l.responsable,
            l.turno,
            l.frecuencia,
            l.observaciones,
            COALESCE(a.telefono, 's/t') AS contacto,
            l.fecha_desde,
            l.fecha_hasta
        FROM sedes_limpieza AS l
        LEFT JOIN agentes AS a
          ON a.id = l.agente_id
        WHERE l.cod_sede = ?
        ORDER BY l.id DESC
    """, (codigo_norm,)).fetchall()

    # 6) Protocolo actual (ultimo no nulo)
    fila_prot = con.execute("""
        SELECT protocolo_url
        FROM sedes_limpieza
        WHERE cod_sede = ?
          AND protocolo_url IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
    """, (codigo_norm,)).fetchone()
    protocolo_url = fila_prot["protocolo_url"] if fila_prot else None
    if not protocolo_url:
        protocolo_url = PROTOCOLOS_LIMPIEZA_POR_SEDE.get(codigo_norm)

    con.close()

    return render_template(
        "sede_limpieza.html",
        sede=sede,
        agentes_limpieza=agentes_limpieza,
        resumen=resumen,
        limpieza_lista=limpieza_lista,
        ultima_actualizacion=ultima_actualizacion,
        protocolo_url=protocolo_url,
    )

@app.route("/sedes/limpieza/<int:lid>/borrar", methods=["POST"])

def sede_limpieza_borrar(lid):
    con = get_db_connection()
    con.row_factory = sqlite3.Row

    # Busco la fila para saber a qué sede pertenece
    fila = con.execute("""
        SELECT cod_sede
        FROM sedes_limpieza
        WHERE id = ?
    """, (lid,)).fetchone()

    codigo = fila["cod_sede"] if fila else request.args.get("codigo", "")

    if fila:
        con.execute("DELETE FROM sedes_limpieza WHERE id = ?", (lid,))
        con.commit()
        flash("Asignación de limpieza eliminada.", "ok")
    else:
        flash("No se encontró la asignación de limpieza.", "error")

    con.close()

    # Si por algún motivo no tengo código, vuelvo al dashboard
    if not codigo:
        return redirect(url_for("dashboard"))

    return redirect(url_for("sede_limpieza", codigo=codigo))



@app.route("/sedes/<codigo>/planos", methods=["GET", "POST"], endpoint="sede_planos")
def sede_planos(codigo):
    # 1) Aseguramos que existan las tablas necesarias
    asegurar_tablas_planos()

    # 2) Conexión para esta vista
    con = get_db()
    con.row_factory = sqlite3.Row

    # 3) Datos de la sede
    sede = con.execute("""
        SELECT *
        FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    # 4) Si viene un POST, guardamos archivos
    if request.method == "POST":
        # Carpeta física para los planos de ESTA sede
        carpeta_sede = os.path.join(PLANOS_DIR, codigo)
        os.makedirs(carpeta_sede, exist_ok=True)

        campos = [
            ("analisis",   "archivo_analisis"),
            ("depositos",  "archivo_depositos"),
            ("evacuacion", "archivo_evacuacion"),
        ]

        for tipo, field_name in campos:
            f = request.files.get(field_name)
            if not f or not f.filename:
                continue  # nada subido en ese campo

            if not plano_permitido(f.filename):
                flash(f"El archivo de {tipo} tiene una extensión no permitida.", "warning")
                continue

            _, ext = os.path.splitext(f.filename)
            ext = ext.lower()

            # Nombre limpio y estándar: S01_depositos.pdf, S01_evacuacion.pdf, etc.
            filename = secure_filename(f"{codigo}_{tipo}{ext}")
            ruta_final = os.path.join(carpeta_sede, filename)
            f.save(ruta_final)

            # Borramos registros viejos de ese tipo para esta sede
            con.execute(
                "DELETE FROM sedes_planos WHERE cod_sede = ? AND tipo = ?",
                (codigo, tipo)
            )

            # Insertamos registro nuevo
            con.execute("""
                INSERT INTO sedes_planos (cod_sede, tipo, archivo, fecha_carga)
                VALUES (?, ?, ?, date('now'))
            """, (codigo, tipo, filename))

        con.commit()
        flash("Planos guardados correctamente.", "success")
        con.close()
        return redirect(url_for("sede_planos", codigo=codigo))

    # 5) Si es GET, buscamos qué planos hay cargados
    filas = con.execute("""
        SELECT tipo, archivo
        FROM sedes_planos
        WHERE cod_sede = ?
    """, (codigo,)).fetchall()

    con.close()

    plano_analisis_url = None
    plano_depositos_url = None
    plano_evacuacion_url = None

    for row in filas:
        url = url_for("static", filename=f"planos_sedes/{codigo}/{row['archivo']}")
        if row["tipo"] == "analisis":
            plano_analisis_url = url
        elif row["tipo"] == "depositos":
            plano_depositos_url = url
        elif row["tipo"] == "evacuacion":
            plano_evacuacion_url = url

    # 6) Infraestructura (por ahora números en 0, como venías usando)
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

    return render_template(
        "sede_planos.html",
        sede=sede,
        infra=infra,
        plano_analisis_url=plano_analisis_url,
        plano_depositos_url=plano_depositos_url,
        plano_evacuacion_url=plano_evacuacion_url,
    )


# =========================================================
# MOVIMIENTOS DE MOBILIARIO
# =========================================================
@app.route("/movimientos", methods=["GET", "POST"], endpoint="movimientos_home")
def movimientos_home():
    con = get_db()
    sede_origen_pref = (request.args.get("sede_origen") or "").upper().strip()
    sede_destino_pref = (request.args.get("sede_destino") or "").upper().strip()
    dep_origen_pref = (request.args.get("deposito_origen") or "").upper().strip()
    dep_destino_pref = (request.args.get("deposito_destino") or "").upper().strip()

    # Combos de sedes
    sedes = con.execute("""
        SELECT codigo, nombre
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    # Lista de depósitos para combos (agrupados por sede)
    depositos = con.execute("""
        SELECT codigo_sede, codigo_local, descripcion
        FROM sedes_depositos
        ORDER BY codigo_sede, codigo_local
    """).fetchall()

    # ---- GUARDAR MOVIMIENTO ----
    if request.method == "POST":
        fecha   = request.form.get("fecha") or date.today().isoformat()
        item    = (request.form.get("item") or "").strip()
        cant    = float(request.form.get("cantidad") or 0)

        sede_ori    = request.form.get("sede_origen") or None
        dep_ori     = request.form.get("deposito_origen") or None
        sede_dest   = request.form.get("sede_destino") or None
        dep_dest    = request.form.get("deposito_destino") or None
        obs         = (request.form.get("observaciones") or "").strip() or None

        if not item or cant == 0:
            flash("Cargá al menos un ítem y cantidad.", "warning")
        else:
            con.execute("""
                INSERT INTO movimientos_mobiliario
                    (fecha, item, cantidad,
                     sede_origen, deposito_origen,
                     sede_destino, deposito_destino,
                     observaciones)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                fecha, item, cant,
                sede_ori, dep_ori,
                sede_dest, dep_dest,
                obs
            ))
            con.commit()
            flash("Movimiento guardado.", "success")
            con.close()
            return redirect(url_for("movimientos_home"))

    # ---- LISTADO ÚLTIMOS MOVIMIENTOS ----
    movimientos = con.execute("""
        SELECT *
        FROM movimientos_mobiliario
        ORDER BY date(fecha) DESC, id DESC
        LIMIT 50
    """).fetchall()

    con.close()

    return render_template(
        "movimientos_home.html",
        sedes=sedes,
        depositos=depositos,
        movimientos=movimientos,
        sede_origen_pref=sede_origen_pref,
        sede_destino_pref=sede_destino_pref,
        dep_origen_pref=dep_origen_pref,
        dep_destino_pref=dep_destino_pref,
    )

# =========================
# SEGURIDAD: MATAFUEGOS + DESINFECCIONES
# =========================
# =========================
# SEGURIDAD: MATAFUEGOS + DESINFECCIONES
# =========================
@app.route("/sedes/<codigo>/seguridad", endpoint="sede_seguridad")
def sede_seguridad(codigo):
    con = get_db()
    con.row_factory = sqlite3.Row

    # Sede
    sede = con.execute("""
        SELECT * FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    # Matafuegos de la sede
    matafuegos = con.execute("""
        SELECT *
        FROM matafuegos_sede
        WHERE cod_sede = ?
        ORDER BY fecha_vencimiento ASC
    """, (codigo,)).fetchall()

    # Desinfecciones
    desinfecciones = con.execute("""
        SELECT *
        FROM desinfecciones_sede
        WHERE cod_sede = ?
        ORDER BY fecha DESC
    """, (codigo,)).fetchall()

    con.close()

    return render_template(
        "sede_seguridad.html",
        sede=sede,
        matafuegos=matafuegos,
        desinfecciones=desinfecciones
    )

@app.route(
    "/sedes/<codigo>/seguridad/matafuegos/nuevo",
    methods=["GET", "POST"],
    endpoint="matafuego_nuevo"
)
def matafuego_nuevo(codigo):
    con = get_db()
    con.row_factory = sqlite3.Row

    sede = con.execute("""
        SELECT * FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        numero_serie      = (request.form.get("nro_serie") or "").strip()
        ubicacion         = (request.form.get("ubicacion") or "").strip()
        peso_kg           = request.form.get("peso_kg") or 0
        fecha_recarga     = request.form.get("fecha_recarga") or None
        fecha_vencimiento = request.form.get("fecha_vencimiento") or None
        observaciones     = (request.form.get("observaciones") or "").strip() or None

        if not numero_serie and not ubicacion:
            con.close()
            flash("Cargá al menos N° de serie o ubicación.", "warning")
            return redirect(url_for("matafuego_nuevo", codigo=codigo))

        con.execute("""
            INSERT INTO matafuegos_sede
            (cod_sede, numero_serie, ubicacion, peso_kg,
             fecha_recarga, fecha_vencimiento, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            codigo,
            numero_serie,
            ubicacion,
            int(peso_kg) if peso_kg else 0,
            fecha_recarga,
            fecha_vencimiento,
            observaciones
        ))
        con.commit()
        con.close()

        # Regenerar eventos del calendario
        rebuild_eventos_seguridad_limpieza()

        flash("Matafuego cargado correctamente.", "success")
        return redirect(url_for("sede_seguridad", codigo=codigo))

    # GET
    con.close()
    return render_template("matafuego_form.html", sede=sede, matafuego=None)




@app.route(
    "/sedes/<codigo>/seguridad/desinfecciones/<int:did>/borrar",
    methods=["POST"],
    endpoint="desinfeccion_borrar"
)
def desinfeccion_borrar(codigo, did):
    con = get_db()

    con.execute("""
        DELETE FROM desinfecciones_sede
        WHERE id = ? AND cod_sede = ?
    """, (did, codigo))

    con.commit()
    con.close()
    flash("Desinfección eliminada.", "info")
    return redirect(url_for("sede_seguridad", codigo=codigo))

# -------------------------------------------------
# EDITAR MATAFUEGO
# -------------------------------------------------
@app.route(
    "/sedes/<codigo>/seguridad/matafuegos/<int:mid>/editar",
    methods=["GET", "POST"],
    endpoint="matafuego_editar"
)
def matafuego_editar(codigo, mid):
    con = get_db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    sede = cur.execute("""
        SELECT * FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    matafuego = cur.execute("""
        SELECT *
        FROM matafuegos_sede
        WHERE id = ? AND cod_sede = ?
    """, (mid, codigo)).fetchone()

    if not matafuego:
        con.close()
        flash("Matafuego no encontrado.", "warning")
        return redirect(url_for("sede_seguridad", codigo=codigo))

    if request.method == "POST":
        numero_serie      = (request.form.get("nro_serie") or "").strip()
        ubicacion         = (request.form.get("ubicacion") or "").strip()
        peso_kg           = request.form.get("peso_kg") or 0
        fecha_recarga     = request.form.get("fecha_recarga") or None
        fecha_vencimiento = request.form.get("fecha_vencimiento") or None
        observaciones     = (request.form.get("observaciones") or "").strip() or None

        cur.execute("""
            UPDATE matafuegos_sede
            SET numero_serie = ?, ubicacion = ?, peso_kg = ?,
                fecha_recarga = ?, fecha_vencimiento = ?, observaciones = ?
            WHERE id = ? AND cod_sede = ?
        """, (
            numero_serie,
            ubicacion,
            int(peso_kg) if peso_kg else 0,
            fecha_recarga,
            fecha_vencimiento,
            observaciones,
            mid,
            codigo
        ))
        con.commit()
        con.close()

        rebuild_eventos_seguridad_limpieza()

        flash("Matafuego actualizado.", "success")
        return redirect(url_for("sede_seguridad", codigo=codigo))

    # GET: mostrar formulario con datos cargados
    con.close()
    return render_template("matafuego_form.html",
                           sede=sede,
                           matafuego=matafuego)



# -------------------------------------------------
# BORRAR MATAFUEGO
# -------------------------------------------------
@app.route(
    "/sedes/<codigo>/seguridad/matafuegos/<int:mid>/borrar",
    methods=["POST"],
    endpoint="matafuego_borrar"
)
def matafuego_borrar(codigo, mid):
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        DELETE FROM matafuegos_sede
        WHERE id = ? AND cod_sede = ?
    """, (mid, codigo))
    con.commit()
    con.close()

    rebuild_eventos_seguridad_limpieza()

    flash("Matafuego eliminado.", "success")
    return redirect(url_for("sede_seguridad", codigo=codigo))


@app.route(
    "/sedes/<codigo>/seguridad/desinfecciones/nueva",
    methods=["GET", "POST"],
    endpoint="desinfeccion_nueva"
)
def desinfeccion_nueva(codigo):
    con = get_db()

    # Buscar sede
    sede = con.execute("""
        SELECT *
        FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        fecha         = request.form.get("fecha") or None
        empresa       = (request.form.get("empresa") or "").strip()
        observaciones = (request.form.get("observaciones") or "").strip() or None

        if not fecha:
            con.close()
            flash("La fecha de desinfección es obligatoria.", "warning")
            return redirect(url_for("desinfeccion_nueva", codigo=codigo))

        # Insert en tabla de desinfecciones de la sede
        cur = con.execute("""
            INSERT INTO desinfecciones_sede
            (cod_sede, fecha, empresa, observaciones)
            VALUES (?, ?, ?, ?)
        """, (
            codigo,
            fecha,
            empresa,
            observaciones
        ))
        desinf_id = cur.lastrowid

        # ---------- Evento para el calendario (desinfección realizada) ----------
        titulo  = f"Desinfección – {empresa or 'Empresa s/d'}"
        detalle = f"Sede {codigo}"

        con.execute("""
            INSERT INTO calendario_eventos
            (fecha, titulo, detalle, area, tipo_evento, ref_id, fuente)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            fecha,
            titulo,
            detalle,
            "Seguridad",
            "desinfeccion",
            str(desinf_id),
            "seguridad_desinfecciones"
        ))

        con.commit()
        con.close()
        flash("Desinfección cargada correctamente.", "success")
        return redirect(url_for("sede_seguridad", codigo=codigo))

    # GET → mostrar formulario
    con.close()
    return render_template("desinfeccion_form.html", sede=sede)






@app.route("/calendario", methods=["GET", "POST"], endpoint="calendario")
def calendario():
    conn = get_db_connection()
    modo_carga = (request.args.get("cargar") == "1")

    # ----- fecha seleccionada -----
    fecha_str = request.args.get("fecha")
    if fecha_str:
        fecha_sel = date.fromisoformat(fecha_str)
    else:
        fecha_sel = date.today()

    # ----- si viene POST -> nuevo pedido / novedad -----
    if request.method == "POST":
        f           = request.form.get("fecha") or fecha_sel.isoformat()
        sede        = (request.form.get("sede") or "").strip()
        solicitante = (request.form.get("solicitante") or "").strip()
        detalle     = (request.form.get("detalle") or "").strip()
        prioridad   = request.form.get("prioridad") or "Media"
        estado      = (request.form.get("estado") or "Pedir").strip()
        if estado not in ("Pedir", "Pedido", "Entregado"):
            estado = "Pedir"

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(calendario_pedidos)").fetchall()}
        if "estado" in cols:
            conn.execute(
                """
                INSERT INTO calendario_pedidos (fecha, sede, solicitante, detalle, prioridad, estado)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f, sede, solicitante, detalle, prioridad, estado),
            )
        else:
            conn.execute(
                """
                INSERT INTO calendario_pedidos (fecha, sede, solicitante, detalle, prioridad)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f, sede, solicitante, detalle, prioridad),
            )
        conn.commit()
        flash("✅ Pedido / novedad guardado en el calendario.", "success")
        conn.close()
        return redirect(url_for("calendario", fecha=f, cargar="1") + "#nuevo-pedido")

    # ----- armo semana para la grilla -----
    inicio_semana = fecha_sel - timedelta(days=fecha_sel.weekday())  # lunes
    semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    # ----- pedidos de ese día -----
    pedidos = conn.execute(
        """
        SELECT id, fecha, sede, solicitante, detalle, prioridad, estado
        FROM calendario_pedidos
        WHERE fecha = ?
        ORDER BY prioridad DESC, id DESC
        """,
        (fecha_sel.isoformat(),),
    ).fetchall()

    # ----- eventos de vehículos de ese día (tabla eventos) -----
    eventos_dia = conn.execute(
        """
        SELECT
            fecha,
            titulo,
            detalle,
            color,
            fuente,
            ref_id
        FROM eventos
        WHERE fecha = ?
          AND fuente = 'vehiculos'
        """,
        (fecha_sel.isoformat(),),
    ).fetchall()

    conn.close()

    return render_template(
        "calendario.html",
        fecha_sel=fecha_sel,
        semana=semana,
        pedidos=pedidos,
        eventos_dia=eventos_dia,
        modo_carga=modo_carga,
    )



@app.route("/api/eventos/borrar/<int:eid>", methods=["DELETE"])
def api_eventos_borrar(eid):
    con = get_db()
    con.execute("DELETE FROM eventos WHERE id=?", (eid,))
    con.commit(); con.close()
    return jsonify({"ok": True})

# =====================================================
# RUTAS DEBUG PARA REGENERAR EVENTOS
# =====================================================

@app.route("/debug/regen_eventos_agentes")
def debug_regen_eventos_agentes():
    rebuild_eventos_agentes()
    flash("Eventos de agentes regenerados en el calendario.", "success")
    return redirect(url_for("dashboard"))




@app.route("/debug/regen_eventos_obras")
def debug_regen_eventos_obras():
    rebuild_eventos_obras()
    flash("Eventos de obras regenerados en el calendario.", "success")
    return redirect(url_for("dashboard"))

@app.route("/debug/regen_eventos_inventario")
def debug_regen_eventos_inventario():
    rebuild_eventos_inventario()
    flash("Eventos de inventario regenerados en el calendario.", "success")
    return redirect(url_for("dashboard"))

@app.route("/debug/regen_eventos_seguridad")
def debug_regen_eventos_seguridad():
    rebuild_eventos_seguridad_limpieza()
    flash("Eventos de seguridad (matafuegos) regenerados en el calendario.", "success")
    return redirect(url_for("dashboard"))





@app.route("/eventos/nuevo", methods=["POST"])
def eventos_nuevo():
    fecha = request.form.get("fecha")
    titulo = request.form.get("titulo")
    detalle = request.form.get("detalle")
    tipo = request.form.get("tipo") or "manual"

    if not fecha or not titulo:
        flash("Fecha y título son obligatorios para crear un evento.", "error")
        return redirect(url_for("dashboard"))

    # Si el tipo existe en CAL_COLORS usamos add_evento_tipo; si no, color gris
    if tipo in CAL_COLORS:
        add_evento_tipo(
            fecha=fecha,
            tipo=tipo,
            titulo=titulo,
            detalle=detalle,
            fuente="manual",
            ref_id=None,
        )
    else:
        add_evento(
            fecha,
            titulo,
            detalle,
            color="#4b5563",
            fuente="manual",
            ref_id=None,
        )

    # volvemos al mes de ese evento
    mes = fecha[:7]
    return redirect(url_for("dashboard", mes=mes, fecha=fecha))

@app.route("/taller")
def taller_home():
    con = get_db()
    con.row_factory = sqlite3.Row
    items = con.execute("SELECT * FROM taller_items ORDER BY id DESC").fetchall()
    con.close()
    return render_template("taller_home.html", items=items)

@app.route("/taller/agregar", methods=["POST"])
def taller_agregar():
    sector = request.form.get("sector")
    item = request.form.get("item")
    cantidad = request.form.get("cantidad")
    estado = request.form.get("estado")
    observ = request.form.get("observaciones")

    con = get_db()
    con.execute("""
        INSERT INTO taller_items (sector,item,cantidad,estado,observaciones)
        VALUES (?,?,?,?,?)
    """, (sector, item, cantidad, estado, observ))
    con.commit()
    con.close()

    flash("Ítem agregado al Taller.", "ok")
    return redirect(url_for("taller_home"))

@app.route("/taller/<int:tid>/eliminar", methods=["POST"])
def taller_eliminar(tid):
    con = get_db()
    con.execute("DELETE FROM taller_items WHERE id=?", (tid,))
    con.commit()
    con.close()
    flash("Ítem eliminado.", "ok")
    return redirect(url_for("taller_home"))

# =========================
# DEPÓSITOS (Stock general)
# =========================

@app.route("/depositos", endpoint="depositos_home")
def depositos_home():
    con = get_db()
    con.row_factory = sqlite3.Row

    ensure_cols(con, "depositos_items", [
        ("categoria", "TEXT"),
    ])
    con.execute("""
        UPDATE depositos_items
        SET categoria = 'Herramientas'
        WHERE categoria IS NULL OR TRIM(categoria) = ''
    """)
    con.commit()

    # 1) Combo de depósitos (solo Taller/Depósito)
    sedes_deps = con.execute("""
        SELECT
            codigo_local AS codigo,
            descripcion
        FROM sedes_depositos
        WHERE descripcion LIKE 'Taller%' OR descripcion LIKE 'Depósito%'
        ORDER BY descripcion
    """).fetchall()

    # 2) Items (con descripción del depósito)
    items = con.execute("""
        SELECT
            di.*,
            di.deposito AS deposito_codigo,
            sd.descripcion AS deposito_desc
        FROM depositos_items di
        LEFT JOIN sedes_depositos sd
               ON sd.codigo_local = di.deposito
        ORDER BY COALESCE(sd.descripcion, di.deposito), di.id DESC
    """).fetchall()

    con.close()
    return render_template("depositos_home.html", items=items, sedes_deps=sedes_deps)


@app.route("/depositos/agregar", methods=["POST"], endpoint="depositos_agregar")
def depositos_agregar():
    # OJO: tu form manda "deposito_codigo"
    deposito = request.form.get("deposito_codigo")
    item = request.form.get("item")
    cantidad = request.form.get("cantidad") or 1
    estado = request.form.get("estado")
    observ = request.form.get("observaciones")
    categoria = (request.form.get("categoria") or "Herramientas").strip()

    if not deposito or not item:
        flash("⚠️ Completá Depósito e Ítem.", "warning")
        return redirect(url_for("depositos_home"))

    con = get_db()
    ensure_cols(con, "depositos_items", [
        ("categoria", "TEXT"),
    ])
    con.execute("""
        INSERT INTO depositos_items (deposito, item, cantidad, estado, observaciones, categoria)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (deposito, item, cantidad, estado, observ, categoria))
    con.commit()
    con.close()

    flash("Ítem agregado al Depósito.", "ok")
    return redirect(url_for("depositos_home"))


@app.route("/depositos/editar/<int:did>", methods=["GET", "POST"], endpoint="depositos_editar")
def depositos_editar(did):
    con = get_db()
    con.row_factory = sqlite3.Row
    ensure_cols(con, "depositos_items", [
        ("categoria", "TEXT"),
    ])

    sedes_deps = con.execute("""
        SELECT codigo_local AS codigo, descripcion
        FROM sedes_depositos
        WHERE descripcion LIKE 'Taller%' OR descripcion LIKE 'Depósito%'
        ORDER BY descripcion
    """).fetchall()

    reg = con.execute("SELECT * FROM depositos_items WHERE id=?", (did,)).fetchone()
    if not reg:
        con.close()
        flash("Registro no encontrado.", "warning")
        return redirect(url_for("depositos_home"))

    if request.method == "POST":
        deposito = request.form.get("deposito_codigo")
        item = request.form.get("item")
        cantidad = request.form.get("cantidad") or 1
        estado = request.form.get("estado")
        observ = request.form.get("observaciones")
        categoria = (request.form.get("categoria") or "Herramientas").strip()

        con.execute("""
            UPDATE depositos_items
            SET deposito=?, item=?, cantidad=?, estado=?, observaciones=?, categoria=?
            WHERE id=?
        """, (deposito, item, cantidad, estado, observ, categoria, did))
        con.commit()
        con.close()

        flash("Cambios guardados.", "ok")
        return redirect(url_for("depositos_home"))

    con.close()
    return render_template("depositos_edit.html", reg=reg, sedes_deps=sedes_deps)


@app.route("/depositos/borrar/<int:did>", methods=["POST"], endpoint="depositos_borrar")
def depositos_borrar(did):
    con = get_db()
    con.execute("DELETE FROM depositos_items WHERE id=?", (did,))
    con.commit()
    con.close()
    flash("Ítem eliminado.", "ok")
    return redirect(url_for("depositos_home"))




@app.route("/sedes/fuero/<fuero_slug>")
def sedes_por_fuero(fuero_slug):
    # Traducción del slug a la clave real de la base
    mapa_fuero = {
        "penal": "penal",
        "menores": "menores_incapaces",
        "ajs": "juridico_social",
        "civil": "civil",
        "adm": "administracion",
    }

    fuero_real = mapa_fuero.get(fuero_slug)
    if not fuero_real:
        # si viene algo raro, volvemos al inicio
        return redirect(url_for("dashboard"))

    # OJO: usá acá la forma en que vos traés las sedes
    # si usás SQLite:
    # sedes_todas = query_db("SELECT * FROM sedes_mpd")
    sedes_todas = obtener_sedes_mpd()   # o como se llame tu función

    sedes_filtradas = [s for s in sedes_todas if s["fuero"] == fuero_real]

    return render_template(
        "sedes_fuero.html",
        sedes=sedes_filtradas,
        fuero_slug=fuero_slug,
        fuero_real=fuero_real,
    )
from flask import jsonify

@app.route("/vehiculos/asistidos/mapa")
def vehiculos_asistidos_mapa():
    return render_template("vehiculos_asistidos_mapa.html")

@app.route("/api/asistidos")
def api_asistidos():
    con = get_db()
    rows = con.execute("""
      SELECT id,nombre,barrio,direccion,referencia,telefono,lat,lng,estado
      FROM asistidos
      ORDER BY id DESC
    """).fetchall()
    con.close()

    data = []
    for r in rows:
        d = dict(r)
        if d.get("lat") and d.get("lng"):
            d["link_maps"] = f"https://www.google.com/maps?q={d['lat']},{d['lng']}"
        else:
            d["link_maps"] = None
        data.append(d)
    return jsonify(data)

@app.route("/asistidos/nuevo", methods=["POST"])
def asistidos_nuevo():
    body = request.get_json(force=True) or {}
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "Falta nombre"}), 400

    def f(x):
        try: return float(x)
        except: return None

    con = get_db()
    con.execute("""
      INSERT INTO asistidos(nombre,barrio,direccion,referencia,telefono,lat,lng,estado)
      VALUES (?,?,?,?,?,?,?,?)
    """, (
      nombre,
      (body.get("barrio") or "").strip(),
      (body.get("direccion") or "").strip(),
      (body.get("referencia") or "").strip(),
      (body.get("telefono") or "").strip(),
      f(body.get("lat")),
      f(body.get("lng")),
      (body.get("estado") or "NO_REALIZADA").strip().upper()
    ))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.get("/api/puntos_mapa")
def api_puntos_mapa():
    con = get_db_connection()
    rows = con.execute("SELECT * FROM puntos_mapa").fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])

@app.post("/puntos_mapa/nuevo")
def puntos_mapa_nuevo():
    data = request.get_json(force=True)

    tipo = (data.get("tipo") or "OTRO").upper()
    nombre = (data.get("nombre") or "").strip()
    lat = data.get("lat")
    lng = data.get("lng")

    if not nombre:
      return jsonify(ok=False, error="Falta nombre"), 400
    if lat in (None,"") or lng in (None,""):
      return jsonify(ok=False, error="Falta lat/lng"), 400

    con = get_db_connection()
    con.execute("""
      INSERT INTO puntos_mapa (tipo,nombre,descripcion,telefono,direccion,barrio,lat,lng,estado)
      VALUES (?,?,?,?,?,?,?,?,?)
    """, (
      tipo,
      nombre,
      (data.get("descripcion") or "").strip(),
      (data.get("telefono") or "").strip(),
      (data.get("direccion") or "").strip(),
      (data.get("barrio") or "").strip(),
      float(lat),
      float(lng),
      (data.get("estado") or None)
    ))
    con.commit()
    con.close()
    return jsonify(ok=True)

from flask import jsonify  # si no lo tenés ya

@app.get("/api/sedes_mpd")
def api_sedes_mpd():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT codigo, nombre, ciudad, direccion, lat, lng
        FROM sedes_mpd
        
                        WHERE codigo <> 'S09'
        ORDER BY codigo;
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

import sqlite3

# ============================================================
# MIGRACIÓN SEGURA: asegurar columnas piso/activo sin romper
# ============================================================
def ensure_personal_schema():
    con = get_db()
    cur = con.cursor()

    cols = [r["name"] for r in cur.execute("PRAGMA table_info(personal_sede)").fetchall()]

    # piso
    if "piso" not in cols:
        cur.execute("ALTER TABLE personal_sede ADD COLUMN piso TEXT DEFAULT 'PB';")

    # activo
    if "activo" not in cols:
        cur.execute("ALTER TABLE personal_sede ADD COLUMN activo INTEGER DEFAULT 1;")

    # normalizar nulos/vacíos
    cur.execute("UPDATE personal_sede SET piso='PB' WHERE piso IS NULL OR TRIM(piso)='';")
    cur.execute("UPDATE personal_sede SET activo=1 WHERE activo IS NULL;")

    con.commit()
    con.close()


# ============================================================
# 1) ALIAS PARA NO ROMPER EL MENÚ VIEJO (personal_sede_home)
# ============================================================
@app.route("/personal-sede", methods=["GET"], endpoint="personal_sede_home")
def personal_sede_alias():
    return redirect(url_for("personal_home"))


# ============================================================
# 2) HOME PERSONAL: LISTADO + FILTROS
#    /personal?sede=S04&piso=PB&q=troncoso
# ============================================================
@app.route("/personal", methods=["GET"], endpoint="personal_home")
def personal_home():
    ensure_personal_schema()

    con = get_db()
    cur = con.cursor()

    # Combo sedes
    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    # Filtros
    cod_sede = (request.args.get("sede") or "").strip()
    piso = (request.args.get("piso") or "").strip()
    q = (request.args.get("q") or "").strip()

    where = []
    params = []

    if cod_sede:
        where.append("p.codigo_sede = ?")
        params.append(cod_sede)

    if piso:
        where.append("COALESCE(p.piso,'PB') = ?")
        params.append(piso)

    if q:
        like = f"%{q}%"
        where.append("""
            (p.nombre_apellido LIKE ?
             OR p.dependencia LIKE ?
             OR p.codigo_local LIKE ?
             OR p.email_admin LIKE ?)
        """)
        params.extend([like, like, like, like])

    sql = """
        SELECT
            p.id,
            p.codigo_sede,
            COALESCE(p.piso,'PB') AS piso,
            p.codigo_local,
            p.nombre_apellido,
            p.dependencia,
            p.sede_texto,
            p.email_admin,
            COALESCE(p.activo,1) AS activo,
            s.nombre AS sede_nombre,
            s.ciudad
        FROM personal_sede p
        JOIN sedes_mpd s ON s.codigo = p.codigo_sede
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += """
        ORDER BY
            p.codigo_sede,
            COALESCE(p.piso,'PB'),
            p.codigo_local,
            p.nombre_apellido
    """

    filas = cur.execute(sql, params).fetchall()
    con.close()

    return render_template(
        "personal_home.html",
        sedes=sedes,
        filas=filas,
        cod_sede=cod_sede,
        piso=piso,
        q=q
    )


# ============================================================
# 3) NUEVO PERSONAL
# ============================================================
@app.route("/personal/nuevo", methods=["GET", "POST"], endpoint="personal_nuevo")
def personal_nuevo():
    ensure_personal_schema()

    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    # Prefill por querystring (desde ficha sede)
    pre = {
        "codigo_sede": (request.args.get("sede") or "").strip(),
        "piso": (request.args.get("piso") or "PB").strip(),
        "codigo_local": (request.args.get("local") or "").strip().upper(),
        "activo": "1",
    }

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip()
        piso = (request.form.get("piso") or "PB").strip()
        codigo_local = (request.form.get("codigo_local") or "").strip().upper()
        nombre_apellido = (request.form.get("nombre_apellido") or "").strip()
        dependencia = (request.form.get("dependencia") or "").strip()
        sede_texto = (request.form.get("sede_texto") or "").strip()
        email_admin = (request.form.get("email_admin") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not nombre_apellido or not codigo_local:
            con.close()
            flash("Sede, Local y Nombre y apellido son obligatorios.", "warning")
            return render_template("personal_form.html", modo="nuevo", sedes=sedes, r=request.form)

        cur.execute("""
            INSERT INTO personal_sede
            (codigo_sede, piso, codigo_local, nombre_apellido, dependencia, sede_texto, email_admin, activo)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            codigo_sede, piso, codigo_local,
            nombre_apellido, dependencia, sede_texto,
            email_admin, activo
        ))

        con.commit()
        con.close()

        flash("Personal agregado correctamente.", "success")
        # volvemos filtrado a la misma sede/piso
        return redirect(url_for("personal_home", sede=codigo_sede, piso=piso))

    con.close()
    return render_template("personal_form.html", modo="nuevo", sedes=sedes, r=pre)


# ============================================================
# 4) EDITAR PERSONAL
# ============================================================
@app.route("/personal/<int:id>/editar", methods=["GET", "POST"], endpoint="personal_editar")
def personal_editar(id):
    ensure_personal_schema()

    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    r = cur.execute("""
        SELECT
            id,
            codigo_sede,
            COALESCE(piso,'PB') AS piso,
            codigo_local,
            nombre_apellido,
            dependencia,
            sede_texto,
            email_admin,
            COALESCE(activo,1) AS activo
        FROM personal_sede
        WHERE id = ?
    """, (id,)).fetchone()

    if not r:
        con.close()
        flash("Registro inexistente.", "error")
        return redirect(url_for("personal_home"))

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip()
        piso = (request.form.get("piso") or "PB").strip()
        codigo_local = (request.form.get("codigo_local") or "").strip().upper()
        nombre_apellido = (request.form.get("nombre_apellido") or "").strip()
        dependencia = (request.form.get("dependencia") or "").strip()
        sede_texto = (request.form.get("sede_texto") or "").strip()
        email_admin = (request.form.get("email_admin") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not nombre_apellido or not codigo_local:
            con.close()
            flash("Sede, Local y Nombre y apellido son obligatorios.", "warning")
            return render_template("personal_form.html", modo="editar", sedes=sedes, r=request.form, id=id)

        cur.execute("""
            UPDATE personal_sede
            SET
                codigo_sede=?,
                piso=?,
                codigo_local=?,
                nombre_apellido=?,
                dependencia=?,
                sede_texto=?,
                email_admin=?,
                activo=?
            WHERE id=?
        """, (
            codigo_sede, piso, codigo_local,
            nombre_apellido, dependencia, sede_texto,
            email_admin, activo, id
        ))

        con.commit()
        con.close()

        flash("Personal actualizado correctamente.", "success")
        return redirect(url_for("personal_home", sede=codigo_sede, piso=piso))

    con.close()
    return render_template("personal_form.html", modo="editar", sedes=sedes, r=r, id=id)


# ============================================================
# 5) ELIMINAR PERSONAL
# ============================================================
@app.route("/personal/<int:id>/eliminar", methods=["POST"], endpoint="personal_eliminar")
def personal_eliminar(id):
    ensure_personal_schema()

    con = get_db()
    cur = con.cursor()

    # para volver filtrado a la sede/piso del registro
    r = cur.execute("SELECT codigo_sede, COALESCE(piso,'PB') AS piso FROM personal_sede WHERE id=?", (id,)).fetchone()

    cur.execute("DELETE FROM personal_sede WHERE id = ?", (id,))
    con.commit()
    con.close()

    flash("Registro eliminado.", "success")
    if r:
        return redirect(url_for("personal_home", sede=r["codigo_sede"], piso=r["piso"]))
    return redirect(url_for("personal_home"))

import os
from flask import request, render_template, redirect, url_for, flash

@app.route("/sedes/<codigo>", endpoint="sede_ficha")
def sede_ficha(codigo):
    db = get_db()
    codigo = (codigo or "").upper().strip()
    ensure_sedes_metricas_table()
    ensure_luminarias_columns()
    ensure_sedes_mpd_cols(db)
    ensure_sedes_particularidades_table()

    # -------------------------
    # PARAMETROS
    # -------------------------
    piso = (request.args.get("piso") or "PB").upper().strip()
    local_raw = (request.args.get("local") or "").strip()
    tab = (request.args.get("tab") or "personal").lower().strip()

    if piso == "2P":
        piso = "P2"
    if piso == "1P":
        piso = "P1"

    home_mode = (request.args.get("home") or "").lower() in ("1", "true", "si", "yes")
    fecha_45d = db.execute("SELECT date('now','+45 day') AS f").fetchone()["f"]

    # -------------------------
    # HELPERS
    # -------------------------
    def has_col(table: str, col: str) -> bool:
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == col for r in rows)

    def where_piso_activo(alias: str, table: str, piso_value: str):
        where = []
        params = []
        if has_col(table, "activo"):
            where.append(f"COALESCE({alias}.activo,1)=1")
        if has_col(table, "piso"):
            where.append(f"COALESCE({alias}.piso,'PB') = ?")
            params.append(piso_value)
        return where, params

    def normalize_local_code(code: str) -> str:
        code = (code or "").upper().strip()
        if "-" in code:
            tail = code.split("-")[-1]
            if tail.startswith("D") and len(tail) == 3 and tail[1:].isdigit():
                return tail
        return code

    def local_sort_key(code: str):
        if code.startswith("D") and code[1:].isdigit():
            return (0, int(code[1:]))
        return (1, code)

    def aires_valid_where(alias: str) -> str:
        return (
            f"((NULLIF(TRIM({alias}.marca),'') IS NOT NULL "
            f"AND UPPER(TRIM({alias}.marca)) NOT IN ('-','PENDIENTE')) "
            f"OR (NULLIF(TRIM({alias}.estado),'') IS NOT NULL) "
            f"OR {alias}.fecha_limpieza IS NOT NULL "
            f"OR {alias}.fecha_ultimo_service IS NOT NULL "
            f"OR {alias}.observaciones IS NOT NULL)"
        )

    # Normalize to Dxx to match personal/mobiliario/luminarias codes.
    local = normalize_local_code(local_raw)

    # -------------------------
    # SEDE
    # -------------------------
    sede = db.execute("""
        SELECT codigo, nombre, ciudad, direccion, fuero, url_maps, foto_frente, url_punto_encuentro,
               url_planos_drive, telefono_sede, num_serv_edsa, num_serv_gasnor, internet_sedes, agua_sedes,
               responsable_ejesa, protocolo_corte_luz_url, protocolo_corte_luz_texto
        FROM sedes_mpd
        WHERE codigo = ?
    """, (codigo,)).fetchone()

    protocolo_limpieza_url = None
    try:
        fila_prot = db.execute("""
            SELECT protocolo_url
            FROM sedes_limpieza
            WHERE cod_sede = ?
              AND protocolo_url IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
        """, (codigo,)).fetchone()
        protocolo_limpieza_url = fila_prot["protocolo_url"] if fila_prot else None
    except Exception:
        protocolo_limpieza_url = None

    sedes_nav = db.execute("""
        SELECT codigo
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    if not sede:
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    # -------------------------
    # KPIs BASE
    # -------------------------
    infra = db.execute("""
        SELECT oficinas, salas_entrevistas, banios, espacios_comunes, depositos, personas,
               m2_totales, m2_por_persona, personas_por_oficina
        FROM sedes_infraestructura
        WHERE sede_codigo = ?
    """, (codigo,)).fetchone()
    # -------------------------
    # METRICAS SEDE (carga manual)
    # -------------------------
    metricas_row = db.execute("""
        SELECT sede_codigo, m2_totales, personas, oficinas, depositos, actualizado_en
        FROM sedes_metricas
        WHERE sede_codigo = ?
    """, (codigo,)).fetchone()



    metricas_row = dict(metricas_row) if metricas_row else {}
    m2_totales = metricas_row.get("m2_totales")
    personas_m = metricas_row.get("personas")
    oficinas_m = metricas_row.get("oficinas")
    depositos_m = metricas_row.get("depositos")

    m2_por_persona = None
    if m2_totales is not None and personas_m:
        try:
            m2_por_persona = round(float(m2_totales) / float(personas_m), 2)
        except Exception:
            m2_por_persona = None

    personas_por_oficina = None
    if personas_m and oficinas_m:
        try:
            personas_por_oficina = round(float(personas_m) / float(oficinas_m), 2)
        except Exception:
            personas_por_oficina = None

    ocupacion_pct = None
    if personas_m and oficinas_m:
        base = float(oficinas_m) * 2.5
        if base:
            ocupacion_pct = round((float(personas_m) / base) * 100.0, 1)

    metricas = {
        "m2_totales": m2_totales,
        "personas": personas_m,
        "oficinas": oficinas_m,
        "depositos": depositos_m,
        "m2_por_persona": m2_por_persona,
        "personas_por_oficina": personas_por_oficina,
        "ocupacion_pct": ocupacion_pct,
        "actualizado_en": metricas_row.get("actualizado_en"),
    }

    # Depositos KPI: preferimos metrica manual, luego tabla depositos, luego infra
    if depositos_m is not None:
        depositos_kpi = depositos_m
    else:
        try:
            depositos_kpi = db.execute(
                "SELECT COUNT(*) AS c FROM sedes_depositos WHERE codigo_sede = ?",
                (codigo,)
            ).fetchone()["c"]
        except Exception:
            depositos_kpi = 0


    obras_kpi = db.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN estado='PENDIENTE'  THEN 1 ELSE 0 END), 0) AS pendientes,
          COALESCE(SUM(CASE WHEN estado='EN_CURSO'   THEN 1 ELSE 0 END), 0) AS en_curso,
          COALESCE(SUM(CASE WHEN estado='FINALIZADA' THEN 1 ELSE 0 END), 0) AS finalizadas
        FROM obras_sede
        WHERE codigo_sede = ?
    """, (codigo,)).fetchone()

    inv_kpi = db.execute("""
        SELECT COALESCE(COUNT(*),0) AS depositos_cargados
        FROM inventario_sede
        WHERE sede_codigo = ?
    """, (codigo,)).fetchone()

    per_kpi = db.execute("""
        SELECT COALESCE(COUNT(*),0) AS personas
        FROM personal_sede
        WHERE codigo_sede = ?
          AND COALESCE(activo,1)=1
    """, (codigo,)).fetchone()

    seg_vencen = db.execute("""
        SELECT COALESCE(COUNT(*),0) AS vencen_pronto
        FROM matafuegos_sede
        WHERE cod_sede = ?
          AND COALESCE(activo,1)=1
          AND fecha_vencimiento IS NOT NULL
          AND date(fecha_vencimiento) <= date('now','+45 day')
    """, (codigo,)).fetchone()

    eventos_sede = db.execute("""
        SELECT fecha, titulo, detalle, color, fuente, ref_id
        FROM eventos
        WHERE sede_codigo = ?
        ORDER BY fecha DESC
        LIMIT 40
    """, (codigo,)).fetchall()

    ensure_evacuacion_responsables_table()
    evac_rows = db.execute("""
        SELECT piso, responsable
        FROM evacuacion_responsables
        WHERE sede_codigo = ?
    """, (codigo,)).fetchall()
    evac_responsables = {r["piso"]: (r["responsable"] or "") for r in evac_rows}

    # -------------------------
    # PLANOS
    # -------------------------
    planos_dir = os.path.join(app.root_path, "static", "planos", codigo)

    def _exists_static(rel):
        return os.path.exists(os.path.join(app.root_path, "static", rel.replace("/", os.sep)))

    def _pick_plan_file(cod, base_name):
        if not os.path.isdir(planos_dir):
            return None

        wanted = (base_name or "").strip()
        if not wanted:
            return None

        for ext in ("png", "jpg", "jpeg", "webp"):
            rel = f"planos/{cod}/{wanted}.{ext}"
            if _exists_static(rel):
                return rel

        for fn in os.listdir(planos_dir):
            base, ext = os.path.splitext(fn)
            if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                if base.lower() == wanted.lower():
                    return f"planos/{cod}/{fn}"

        return None

    def _norm_piso(p):
        p = (p or "").upper().strip()
        if p == "2P":
            return "P2"
        if p == "1P":
            return "P1"
        return p

    pisos_disponibles = []
    if os.path.isdir(planos_dir):
        tmp = []
        for fn in os.listdir(planos_dir):
            base, ext = os.path.splitext(fn)
            if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                b = _norm_piso(base)
                if b == "PB" or (b.startswith("P") and b[1:].isdigit()):
                    tmp.append(b)

        def _sort_key(x):
            if x == "PB":
                return (0, 0)
            if x.startswith("P") and x[1:].isdigit():
                return (1, int(x[1:]))
            return (9, 999)

        pisos_disponibles = sorted(set(tmp), key=_sort_key)

    if pisos_disponibles and piso not in pisos_disponibles:
        piso = pisos_disponibles[0]

    plano_base = piso
    if tab == "luminarias":
        c = f"{piso}_iluminacion"
        if _pick_plan_file(codigo, c):
            plano_base = c
    elif tab == "matafuegos":
        c = f"{piso}_seg"
        if _pick_plan_file(codigo, c):
            plano_base = c
    elif tab == "evacuacion":
        c = f"{piso}_eva"
        if _pick_plan_file(codigo, c):
            plano_base = c
    elif tab == "aires":
        c = f"{piso}_aires"
        if _pick_plan_file(codigo, c):
            plano_base = c

    plano_rel = _pick_plan_file(codigo, plano_base) or "planos/placeholder.png"
    plano_url = url_for("static", filename=plano_rel)

    # -------------------------
    # LOCALES (para filtros debajo del plano)
    # -------------------------
    try:
        locales_rows = db.execute("""
            SELECT codigo_local
            FROM sedes_depositos
            WHERE codigo_sede = ?
            ORDER BY codigo_local
        """, (codigo,)).fetchall()
        locales = sorted(
            {normalize_local_code(r["codigo_local"]) for r in locales_rows if r["codigo_local"]},
            key=local_sort_key,
        )
    except Exception:
        locales = []

    # -------------------------
    # PANEL: defaults (SIEMPRE)
    # -------------------------
    personal_rows = []
    mobiliario_rows = []
    depositos_rows = []

    luminarias_rows = []
    luminarias_kpi = {"tubo_fria": 0, "tubo_calido": 0, "foco": 0, "panel": 0, "puestos_trabajo": 0}

    matafuegos_rows = []
    matafuegos_kpi = {"total": 0, "vencen_pronto": 0}

    aires_rows = []
    aires_kpi = {"total": 0, "operativos": 0, "fuera_servicio": 0}
    resumen_sedes_rows = []
    resumen_sedes_totals = {
        "mesa_pc": 0,
        "escritorio_prof": 0,
        "silla_giratoria": 0,
        "silla_fija": 0,
        "armario_alto": 0,
        "biblioteca_baja": 0,
        "aires_total": 0,
        "luminarias_total": 0,
        "puestos_trabajo": 0,
    }
    parti_rows = db.execute("""
        SELECT id, titulo, detalle
        FROM sedes_particularidades
        WHERE sede_codigo = ?
        ORDER BY id DESC
    """, (codigo,)).fetchall()

    # -------------------------
    # RESUMEN SEDES
    # -------------------------
    if tab == "resumen":
        sedes_rows = db.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        def safe_scalar(sql, params=()):
            try:
                r = db.execute(sql, params).fetchone()
                return (r[0] if r and r[0] is not None else 0)
            except Exception:
                return 0

        for s in sedes_rows:
            cod = s["codigo"]
            resumen_sedes_rows.append({
                "codigo": cod,
                "nombre": s["nombre"],
                "mesa_pc": safe_scalar("""
                    SELECT COALESCE(SUM(COALESCE(mesa_pc,0)),0)
                    FROM mobiliario_sede
                    WHERE codigo_sede = ? AND COALESCE(activo,1)=1
                """, (cod,)),
                "escritorio_prof": safe_scalar("""
                    SELECT COALESCE(SUM(COALESCE(escritorio_prof,0)),0)
                    FROM mobiliario_sede
                    WHERE codigo_sede = ? AND COALESCE(activo,1)=1
                """, (cod,)),
                "aires_total": safe_scalar("""
                    SELECT COALESCE(COUNT(*),0)
                    FROM aires_sede
                    WHERE sede_codigo = ?
                      AND {aires_valid}
                """.format(aires_valid=aires_valid_where("aires_sede")), (cod,)),
                "luminarias_total": safe_scalar("""
                    SELECT COALESCE(SUM(
                        COALESCE(tubo_led_fria,0) +
                        COALESCE(tubo_led_calido,0) +
                        COALESCE(foco_comun,0) +
                        COALESCE(panel_led,0)
                    ),0)
                    FROM luminarias_sede
                    WHERE codigo_sede = ?
                """, (cod,)),
                "puestos_trabajo": safe_scalar("""
                    SELECT COALESCE(SUM(COALESCE(puestos_trabajo,0)),0)
                    FROM luminarias_sede
                    WHERE codigo_sede = ?
                """, (cod,)),
            })

        for r in resumen_sedes_rows:
            resumen_sedes_totals["mesa_pc"] += r["mesa_pc"] or 0
            resumen_sedes_totals["escritorio_prof"] += r["escritorio_prof"] or 0
            resumen_sedes_totals["aires_total"] += r["aires_total"] or 0
            resumen_sedes_totals["luminarias_total"] += r["luminarias_total"] or 0
            resumen_sedes_totals["puestos_trabajo"] += r["puestos_trabajo"] or 0

    # -------------------------
    # PERSONAL
    # -------------------------
    if tab == "personal":
        where = ["p.codigo_sede = ?"]
        params = [codigo]

        w2, p2 = where_piso_activo("p", "personal_sede", piso)
        where += w2
        params += p2

        if local:
            where.append("p.codigo_local = ?")
            params.append(local)

        personal_rows = db.execute(f"""
            SELECT
                p.id,
                p.codigo_sede,
                p.codigo_local,
                p.nombre_apellido,
                p.dependencia,
                p.email_admin
            FROM personal_sede p
            WHERE {" AND ".join(where)}
            ORDER BY p.codigo_local, p.nombre_apellido
        """, params).fetchall()

    # -------------------------
    # MOBILIARIO
    # -------------------------
    if tab == "mobiliario":
        where = ["m.codigo_sede = ?"]
        params = [codigo]

        w2, p2 = where_piso_activo("m", "mobiliario_sede", piso)
        where += w2
        params += p2

        if local:
            where.append("m.codigo_local = ?")
            params.append(local)

        mobiliario_rows = db.execute(f"""
            SELECT
                m.id,
                m.codigo_sede,
                m.codigo_local,
                m.descripcion,
                COALESCE(m.aire_marca,0) AS aire_marca,
                COALESCE(m.escritorio_prof,0) AS escritorio_prof,
                COALESCE(m.mesa_pc,0) AS mesa_pc,
                COALESCE(m.silla_giratoria,0) AS silla_giratoria,
                COALESCE(m.silla_fija,0) AS silla_fija,
                COALESCE(m.armario_alto,0) AS armario_alto,
                COALESCE(m.biblioteca_baja,0) AS biblioteca_baja,
                COALESCE(m.otros,0) AS otros,
                m.otros_detalle
            FROM mobiliario_sede m
            WHERE {" AND ".join(where)}
            ORDER BY m.codigo_local, m.descripcion
        """, params).fetchall()

    # -------------------------
    # DEPOSITOS
    # -------------------------
    if tab == "depositos":
        rows = db.execute("""
            SELECT codigo_sede, codigo_local, descripcion
            FROM sedes_depositos
            WHERE codigo_sede = ?
            ORDER BY codigo_local
        """, (codigo,)).fetchall()
        depositos_rows = [{
            "codigo_sede": r["codigo_sede"],
            "codigo_local": normalize_local_code(r["codigo_local"]),
            "descripcion": r["descripcion"],
        } for r in rows]
        depositos_rows.sort(key=lambda d: local_sort_key(d["codigo_local"]))

    # -------------------------
    # LUMINARIAS
    # -------------------------
    if tab == "luminarias":
        where = ["l.codigo_sede = ?"]
        params = [codigo]

        w2, p2 = where_piso_activo("l", "luminarias_sede", piso)
        where += w2
        params += p2

        if local and has_col("luminarias_sede", "codigo_local"):
            where.append("l.codigo_local = ?")
            params.append(local)

        luminarias_rows = db.execute(f"""
            SELECT
                l.id,
                l.codigo_sede,
                COALESCE(l.piso,'PB') AS piso,
                l.codigo_local,
                COALESCE(l.tubo_led_fria,0)   AS tubo_led_fria,
                COALESCE(l.tubo_led_calido,0) AS tubo_led_calido,
                COALESCE(l.foco_comun,0)      AS foco_comun,
                COALESCE(l.panel_led,0)       AS panel_led,
                COALESCE(l.puestos_trabajo,0) AS puestos_trabajo,
                l.otros_detalle
            FROM luminarias_sede l
            WHERE {" AND ".join(where)}
            ORDER BY l.codigo_local
        """, params).fetchall()

        k = db.execute(f"""
            SELECT
                COALESCE(SUM(COALESCE(l.tubo_led_fria,0)),0)    AS tubo_fria,
                COALESCE(SUM(COALESCE(l.tubo_led_calido,0)),0)  AS tubo_calido,
                COALESCE(SUM(COALESCE(l.foco_comun,0)),0)       AS foco,
                COALESCE(SUM(COALESCE(l.panel_led,0)),0)        AS panel,
                COALESCE(SUM(COALESCE(l.puestos_trabajo,0)),0)  AS puestos_trabajo
            FROM luminarias_sede l
            WHERE {" AND ".join(where)}
        """, params).fetchone()

        if k:
            luminarias_kpi = dict(k)

    # -------------------------
    # MATAFUEGOS
    # -------------------------
    if tab == "matafuegos":
        where = ["m.cod_sede = ?", "COALESCE(m.activo,1)=1", "COALESCE(m.piso,'PB') = ?"]
        params = [codigo, piso]

        if local:
            where.append("m.codigo_local = ?")
            params.append(local)

        matafuegos_rows = db.execute(f"""
            SELECT
                m.id,
                m.cod_sede,
                COALESCE(m.piso,'PB') AS piso,
                m.codigo_local,
                m.ubicacion,
                m.numero_serie,
                m.numero_matafuego,
                m.tipo,
                m.capacidad_kg,
                m.estado,
                m.fecha_recarga,
                m.fecha_vencimiento,
                m.fecha_prueba_hidro,
                m.observaciones
            FROM matafuegos_sede m
            WHERE {" AND ".join(where)}
            ORDER BY COALESCE(m.codigo_local,''), COALESCE(m.ubicacion,''), COALESCE(m.numero_serie,'')
        """, params).fetchall()

        k = db.execute(f"""
            SELECT
              COALESCE(COUNT(*),0) AS total,
              COALESCE(SUM(
                CASE
                  WHEN m.fecha_vencimiento IS NOT NULL
                   AND date(m.fecha_vencimiento) <= date('now','+45 day')
                  THEN 1 ELSE 0
                END
              ),0) AS vencen_pronto
            FROM matafuegos_sede m
            WHERE {" AND ".join(where)}
        """, params).fetchone()

        if k:
            matafuegos_kpi = dict(k)

    # -------------------------
    # AIRES
    # -------------------------
    if tab == "aires":
        where = ["a.sede_codigo = ?"]
        params = [codigo]

        if has_col("aires_sede", "piso"):
            where.append("COALESCE(a.piso,'PB') = ?")
            params.append(piso)

        where.append(aires_valid_where("a"))

        aires_rows = db.execute(f"""
            SELECT
                a.id,
                a.sede_codigo,
                COALESCE(a.piso,'PB') AS piso,
                a.ambiente_codigo,
                a.ambiente_desc,
                COALESCE(NULLIF(TRIM(a.ambiente_desc),''), NULLIF(TRIM(a.ambiente_codigo),''), '-') AS ambiente,
                a.marca,
                a.estado,
                a.fecha_limpieza,
                a.fecha_ultimo_service,
                a.observaciones
            FROM aires_sede a
            WHERE {" AND ".join(where)}
            ORDER BY COALESCE(a.ambiente_codigo,''), COALESCE(a.marca,'')
        """, params).fetchall()

        k = db.execute(f"""
            SELECT
                COALESCE(COUNT(*),0) AS total,
                COALESCE(SUM(CASE WHEN lower(COALESCE(a.estado,'')) = 'operativo' THEN 1 ELSE 0 END),0) AS operativos,
                COALESCE(SUM(CASE WHEN lower(COALESCE(a.estado,'')) LIKE 'fuera%' THEN 1 ELSE 0 END),0) AS fuera_servicio
            FROM aires_sede a
            WHERE {" AND ".join(where)}
        """, params).fetchone()

        if k:
            aires_kpi = dict(k)

    # -------------------------
    # KPIs TOTALES (SIN FILTRO piso/local)
    # -------------------------
    aires_total_kpi = {"total": 0, "operativos": 0, "fuera_servicio": 0}
    mobiliario_total_kpi = {
        "aire_marca": 0,
        "escritorio_prof": 0,
        "mesa_pc": 0,
        "silla_giratoria": 0,
        "silla_fija": 0,
        "armario_alto": 0,
        "biblioteca_baja": 0,
        "otros": 0,
    }
    luminarias_total_kpi = {"tubo_fria": 0, "tubo_calido": 0, "foco": 0, "panel": 0, "puestos_trabajo": 0}

    # AIRES total
    try:
        if has_col("aires_sede", "sede_codigo"):
            k = db.execute("""
                SELECT
                    COALESCE(COUNT(*),0) AS total,
                    COALESCE(SUM(CASE WHEN lower(COALESCE(estado,'')) = 'operativo' THEN 1 ELSE 0 END),0) AS operativos,
                    COALESCE(SUM(CASE WHEN lower(COALESCE(estado,'')) LIKE 'fuera%' THEN 1 ELSE 0 END),0) AS fuera_servicio
                FROM aires_sede
                WHERE sede_codigo = ?
                  AND {aires_valid}
            """.format(aires_valid=aires_valid_where("aires_sede")), (codigo,)).fetchone()
            if k:
                aires_total_kpi = dict(k)
    except Exception:
        pass

    # MOBILIARIO total
    try:
        if has_col("mobiliario_sede", "codigo_sede"):
            k = db.execute("""
                SELECT
                    COALESCE(SUM(COALESCE(aire_marca,0)),0) AS aire_marca,
                    COALESCE(SUM(COALESCE(escritorio_prof,0)),0) AS escritorio_prof,
                    COALESCE(SUM(COALESCE(mesa_pc,0)),0) AS mesa_pc,
                    COALESCE(SUM(COALESCE(silla_giratoria,0)),0) AS silla_giratoria,
                    COALESCE(SUM(COALESCE(silla_fija,0)),0) AS silla_fija,
                    COALESCE(SUM(COALESCE(armario_alto,0)),0) AS armario_alto,
                    COALESCE(SUM(COALESCE(biblioteca_baja,0)),0) AS biblioteca_baja,
                    COALESCE(SUM(COALESCE(otros,0)),0) AS otros
                FROM mobiliario_sede
                WHERE codigo_sede = ?
                  AND COALESCE(activo,1)=1
            """, (codigo,)).fetchone()
            if k:
                mobiliario_total_kpi = dict(k)
    except Exception:
        pass

    # LUMINARIAS total
    try:
        if has_col("luminarias_sede", "codigo_sede"):
            k = db.execute("""
                SELECT
                    COALESCE(SUM(COALESCE(tubo_led_fria,0)),0)    AS tubo_fria,
                    COALESCE(SUM(COALESCE(tubo_led_calido,0)),0)  AS tubo_calido,
                    COALESCE(SUM(COALESCE(foco_comun,0)),0)       AS foco,
                    COALESCE(SUM(COALESCE(panel_led,0)),0)        AS panel,
                    COALESCE(SUM(COALESCE(puestos_trabajo,0)),0)  AS puestos_trabajo
                FROM luminarias_sede
                WHERE codigo_sede = ?
                  AND COALESCE(activo,1)=1
            """, (codigo,)).fetchone()
            if k:
                luminarias_total_kpi = dict(k)
    except Exception:
        pass

    # TOTAL de mobiliario para tu KPI "Mobiliario (total)"
    mobiliario_total_items = (
        (mobiliario_total_kpi.get("aire_marca", 0) or 0)
        + (mobiliario_total_kpi.get("escritorio_prof", 0) or 0)
        + (mobiliario_total_kpi.get("mesa_pc", 0) or 0)
        + (mobiliario_total_kpi.get("silla_giratoria", 0) or 0)
        + (mobiliario_total_kpi.get("silla_fija", 0) or 0)
        + (mobiliario_total_kpi.get("armario_alto", 0) or 0)
        + (mobiliario_total_kpi.get("biblioteca_baja", 0) or 0)
        + (mobiliario_total_kpi.get("otros", 0) or 0)
    )

    # -------------------------
    # HOME MODE (calendario + resumen diario)
    # -------------------------
    mes = None
    fecha_dia = None
    q_cal = ""
    cal_weeks = []
    eventos_mes = []
    eventos_por_dia = {}
    eventos_por_dia_resumen = {}
    eventos_dia = []
    home_cards = []
    cal_legend = []

    if home_mode:
        mes = request.args.get("mes") or date.today().strftime("%Y-%m")
        fecha_dia = request.args.get("fecha") or date.today().strftime("%Y-%m-%d")
        q_cal = request.args.get("q_cal", "").strip()

        lic_hoy = db.execute("""
            SELECT al.agente_id, ai.agente
            FROM agentes_licencias al
            JOIN agentes_intendencia ai ON ai.id = al.agente_id
            WHERE ai.activo = 1
              AND al.fecha_desde <= ?
              AND al.fecha_hasta >= ?
              AND UPPER(COALESCE(al.estado, '')) != 'RECHAZADA'
        """, (fecha_dia, fecha_dia)).fetchall()

        params = [mes]
        filtro_sql = ""
        if q_cal:
            filtro_sql = """
              AND (
                    titulo  LIKE ?
                 OR detalle LIKE ?
                 OR fuente  LIKE ?
                 OR ref_id  LIKE ?
              )
            """
            like = f"%{q_cal}%"
            params.extend([like, like, like, like])

        eventos_mes = db.execute(f"""
            SELECT id, fecha, titulo, detalle, color, fuente, ref_id
            FROM eventos
            WHERE substr(fecha, 1, 7) = ?
            {filtro_sql}
            ORDER BY fecha ASC, id ASC
        """, params).fetchall()

        def _event_label(ev):
            ref = (ev.get("ref_id") or "")
            fuente = (ev.get("fuente") or "").lower()
            titulo = (ev.get("titulo") or "").lower()
            if ref.startswith("OBRA-"):
                if "finalizada" in titulo:
                    return "Obra finalizada"
                if "en curso" in titulo:
                    return "Obra en curso"
                return "Obra solicitada"
            if ref.startswith("VIAJE-"):
                return "Viaje"
            if ref.startswith("COMB-"):
                return "Combustible"
            if ref.startswith(("SERV-", "LAVA-", "SEG-", "RTV-")):
                return "Documentacion vehiculo"
            if ref.startswith("LIC-"):
                return "Licencia"
            if ref.startswith("DOC-"):
                return "Documentacion"
            if ref.startswith("INC-"):
                return "Incidente"
            if ref.startswith("SST-"):
                return "SST"
            if ref.startswith("EPP-"):
                return "EPP"
            if ref.startswith("ASIG-"):
                return "Asignacion"
            if ref.startswith("CAP-"):
                return "Capacitacion"
            if ref.startswith("MF-"):
                return "Matafuego"
            if ref.startswith("MOVMOB-"):
                return "Inventario"
            if fuente == "manual":
                return "Recordatorio"
            if fuente:
                return fuente.capitalize()
            return "Evento"

        def _event_link(ev):
            ref = (ev.get("ref_id") or "")
            fuente = (ev.get("fuente") or "").lower()
            if ref.startswith("OBRA-"):
                return url_for("obras_home")
            if ref.startswith("VIAJE-"):
                try:
                    vid = int(ref.split("-")[1])
                    return url_for("viaje_editar", viaje_id=vid)
                except Exception:
                    return url_for("vehiculos_control_diario")
            if ref.startswith("COMB-"):
                try:
                    cid = int(ref.split("-")[1])
                    return url_for("combustible_editar", cid=cid)
                except Exception:
                    return url_for("vehiculos_combustible")
            if ref.startswith(("SERV-", "LAVA-", "SEG-", "RTV-")):
                return url_for("vehiculos_documentacion")
            if fuente == "vehiculos":
                return url_for("vehiculos_control_diario")
            if fuente == "obras":
                return url_for("obras_home")
            if fuente == "agentes":
                return url_for("agentes_home")
            if fuente == "seguridad":
                return url_for("matafuegos_home")
            return None

        eventos_mes = [
            {**dict(ev), "label": _event_label(dict(ev)), "link": _event_link(dict(ev))}
            for ev in eventos_mes
        ]

        eventos_por_dia = defaultdict(list)
        for ev in eventos_mes:
            eventos_por_dia[ev["fecha"]].append(ev)

        eventos_dia = eventos_por_dia.get(fecha_dia, [])
        eventos_por_dia_resumen = {}
        color_labels = {}
        for ev in eventos_mes:
            color = ev.get("color") or "#64748b"
            label = ev.get("label") or "Evento"
            if color not in color_labels:
                color_labels[color] = label
            elif color_labels[color] != label:
                color_labels[color] = "Mixto"
        for fecha, evs in eventos_por_dia.items():
            color_counts = {}
            color_titles = {}
            for ev in evs:
                color = ev.get("color") or "#64748b"
                color_counts[color] = color_counts.get(color, 0) + 1
                if ev.get("titulo"):
                    color_titles.setdefault(color, [])
                    if len(color_titles[color]) < 3:
                        color_titles[color].append(ev["titulo"])
            eventos_por_dia_resumen[fecha] = [
                {
                    "color": color,
                    "count": count,
                    "label": color_labels.get(color, "Evento"),
                    "titles": color_titles.get(color, []),
                }
                for color, count in color_counts.items()
            ]

        anio = int(mes[:4])
        mes_num = int(mes[5:7])
        cal = calendar.Calendar(firstweekday=0)
        cal_weeks = cal.monthdayscalendar(anio, mes_num)

        lic_names = [r["agente"] for r in lic_hoy if r["agente"]][:5]
        lic_extra = max(0, len(lic_hoy) - len(lic_names))

        manual_events = [e for e in eventos_dia if (e.get("fuente") or "").lower() == "manual"]
        obra_events = [e for e in eventos_dia if (e.get("fuente") or "").lower() == "obras"]
        ev_titles = [e.get("titulo") for e in manual_events if e.get("titulo")]
        obra_titles = [e.get("titulo") for e in obra_events if e.get("titulo")]
        home_cards = [
            {
                "label": "Licencias hoy",
                "value": len(lic_hoy),
                "hint": "Agentes",
                "names": lic_names,
                "extra": lic_extra,
                "tone": "warn",
            },
            {
                "label": "Eventos hoy",
                "value": len(manual_events),
                "hint": "Recordatorios",
                "names": ev_titles[:5],
                "extra": max(0, len(ev_titles) - 5),
                "tone": "info",
            },
            {
                "label": "Obras hoy",
                "value": len(obra_events),
                "hint": "Mantenimiento",
                "names": obra_titles[:5],
                "extra": max(0, len(obra_titles) - 5),
                "tone": "accent",
            },
        ]

        cal_legend = [
            {"label": "Viajes", "color": CAL_COLORS["viaje"]},
            {"label": "Uso salon", "color": CAL_COLORS["uso_salon"]},
            {"label": "Licencias", "color": CAL_COLORS["licencia"]},
            {"label": "Documentacion", "color": CAL_COLORS["documentacion"]},
            {"label": "Incidentes", "color": CAL_COLORS["incidente"]},
            {"label": "Obra solicitada", "color": CAL_COLORS["obra_solicitada"]},
            {"label": "Obra en curso", "color": CAL_COLORS["obra_en_curso"]},
            {"label": "Obra finalizada", "color": CAL_COLORS["obra_finalizada"]},
            {"label": "Vencimientos", "color": CAL_COLORS["seguro"]},
            {"label": "SST", "color": CAL_COLORS["sst_prevencion"]},
        ]

    documentos_vinculados_sede = []
    try:
        t_docs = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos'").fetchone()
        t_rel = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos_sedes'").fetchone()
        if t_docs and t_rel:
            documentos_vinculados_sede = db.execute("""
                SELECT
                    d.id_documento,
                    d.titulo,
                    d.tipo_documento,
                    d.estado,
                    d.fecha,
                    d.archivo_url,
                    d.autor,
                    COALESCE((
                        SELECT GROUP_CONCAT(dt.tag, ', ')
                        FROM documentos_tags dt
                        WHERE dt.id_documento = d.id_documento
                    ), '') AS tags_txt
                FROM documentos d
                JOIN documentos_sedes ds ON ds.id_documento = d.id_documento
                WHERE ds.sede_codigo = ?
                ORDER BY COALESCE(d.fecha, d.creado_en) DESC, d.id_documento DESC
                LIMIT 40
            """, (codigo,)).fetchall()
    except Exception:
        documentos_vinculados_sede = []

    # -------------------------
    # RENDER
    # -------------------------
    return render_template(
        "sede_ficha.html",
        sede=sede,
        sedes_nav=sedes_nav,
        infra=infra,
        obras_kpi=obras_kpi,
        inv_kpi=inv_kpi,
        per_kpi=per_kpi,
        seg_vencen=seg_vencen,
        metricas=metricas,
        depositos_kpi=depositos_kpi,
        eventos_sede=eventos_sede,
        evac_responsables=evac_responsables,
        pisos=pisos_disponibles,
        piso_sel=piso,
        plano_url=plano_url,
        locales=locales,
        tab=tab,
        local=local,
        fecha_45d=fecha_45d,

        personal_rows=personal_rows,
        mobiliario_rows=mobiliario_rows,
        depositos_rows=depositos_rows,
        luminarias_rows=luminarias_rows,
        luminarias_kpi=luminarias_kpi,
        matafuegos_rows=matafuegos_rows,
        matafuegos_kpi=matafuegos_kpi,
        aires_rows=aires_rows,
        aires_kpi=aires_kpi,
        resumen_sedes_rows=resumen_sedes_rows,
        resumen_sedes_totals=resumen_sedes_totals,
        parti_rows=parti_rows,

        # Totales arriba
        aires_total_kpi=aires_total_kpi,
        mobiliario_total_kpi=mobiliario_total_kpi,
        luminarias_total_kpi=luminarias_total_kpi,
        mobiliario_total_items=mobiliario_total_items,

        # Home mode
        home_mode=home_mode,
        mes=mes,
        fecha_dia=fecha_dia,
        q_cal=q_cal,
        cal_weeks=cal_weeks,
        eventos_mes=eventos_mes,
        eventos_por_dia=eventos_por_dia,
        eventos_por_dia_resumen=eventos_por_dia_resumen,
        eventos_dia=eventos_dia,
        home_cards=home_cards,
        cal_legend=cal_legend if home_mode else [],
        protocolo_limpieza_url=protocolo_limpieza_url,
        documentos_vinculados_sede=documentos_vinculados_sede,
    )


@app.post("/sedes/<codigo>/servicios", endpoint="sede_servicios_guardar")
def sede_servicios_guardar(codigo):
    con = get_db()
    ensure_sedes_mpd_cols(con)

    codigo = (codigo or "").upper().strip()
    telefono_sede = (request.form.get("telefono_sede") or "").strip()
    num_serv_edsa = (request.form.get("num_serv_edsa") or "").strip()
    num_serv_gasnor = (request.form.get("num_serv_gasnor") or "").strip()
    internet_sedes = (request.form.get("internet_sedes") or "").strip()
    agua_sedes = (request.form.get("agua_sedes") or "").strip()

    con.execute("""
        UPDATE sedes_mpd
        SET telefono_sede = ?,
            num_serv_edsa = ?,
            num_serv_gasnor = ?,
            internet_sedes = ?,
            agua_sedes = ?
        WHERE codigo = ?
    """, (telefono_sede, num_serv_edsa, num_serv_gasnor, internet_sedes, agua_sedes, codigo))
    con.commit()
    con.close()

    flash("Servicios actualizados.", "success")
    next_url = request.form.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("sede_ficha", codigo=codigo, view="resumen"))


@app.post("/sedes/<codigo>/particularidades", endpoint="sede_particularidad_agregar")
def sede_particularidad_agregar(codigo):
    con = get_db()
    ensure_sedes_particularidades_table()

    codigo = (codigo or "").upper().strip()
    titulo = (request.form.get("titulo") or "").strip()
    detalle = (request.form.get("detalle") or "").strip()

    if not titulo and not detalle:
        flash("Ingresá al menos un título o un detalle.", "warning")
    else:
        con.execute("""
            INSERT INTO sedes_particularidades (sede_codigo, titulo, detalle)
            VALUES (?, ?, ?)
        """, (codigo, titulo, detalle))
        con.commit()
        flash("Particularidad agregada.", "success")

    con.close()
    next_url = request.form.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("sede_ficha", codigo=codigo))


@app.post("/sedes/<codigo>/particularidades/<int:pid>/editar", endpoint="sede_particularidad_editar")
def sede_particularidad_editar(codigo, pid):
    con = get_db()
    ensure_sedes_particularidades_table()

    codigo = (codigo or "").upper().strip()
    titulo = (request.form.get("titulo") or "").strip()
    detalle = (request.form.get("detalle") or "").strip()

    con.execute("""
        UPDATE sedes_particularidades
        SET titulo = ?, detalle = ?, actualizado_en = datetime('now')
        WHERE id = ? AND sede_codigo = ?
    """, (titulo, detalle, pid, codigo))
    con.commit()
    con.close()

    flash("Particularidad actualizada.", "success")
    next_url = request.form.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("sede_ficha", codigo=codigo))


@app.post("/sedes/<codigo>/particularidades/<int:pid>/eliminar", endpoint="sede_particularidad_eliminar")
def sede_particularidad_eliminar(codigo, pid):
    con = get_db()
    ensure_sedes_particularidades_table()

    codigo = (codigo or "").upper().strip()
    con.execute("""
        DELETE FROM sedes_particularidades
        WHERE id = ? AND sede_codigo = ?
    """, (pid, codigo))
    con.commit()
    con.close()

    flash("Particularidad eliminada.", "success")
    next_url = request.form.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("sede_ficha", codigo=codigo))


@app.route("/sedes/<codigo>/depositos/editar", methods=["GET", "POST"], endpoint="sede_depositos_edit")
def sede_depositos_edit(codigo):
    db = get_db()
    codigo = (codigo or "").upper().strip()

    sede = db.execute(
        "SELECT codigo, nombre FROM sedes_mpd WHERE codigo = ?",
        (codigo,),
    ).fetchone()

    sedes_nav = db.execute("""
        SELECT codigo
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()
    if not sede:
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    def normalize_local_code(code: str) -> str:
        code = (code or "").upper().strip()
        if "-" in code:
            tail = code.split("-")[-1]
            if tail.startswith("D") and tail[1:].isdigit():
                return tail
        if code.startswith("D") and code[1:].isdigit():
            return code
        return code

    def local_sort_key(code: str):
        if code.startswith("D") and code[1:].isdigit():
            return (0, int(code[1:]))
        return (1, code)

    def build_storage_code(sede_codigo: str, local_norm: str) -> str:
        return f"{sede_codigo}-P00-{local_norm}"

    def cleanup_duplicates():
        rows = db.execute("""
            SELECT id, codigo_local, descripcion
            FROM sedes_depositos
            WHERE codigo_sede = ?
        """, (codigo,)).fetchall()

        groups = {}
        for r in rows:
            norm = normalize_local_code(r["codigo_local"])
            groups.setdefault(norm, []).append(r)

        keep_ids = set()
        delete_ids = []
        sede_prefix = f"{codigo}-"

        for norm, items in groups.items():
            if len(items) == 1:
                keep_ids.add(items[0]["id"])
                continue

            preferred = [r for r in items if r["codigo_local"].startswith(sede_prefix)]
            if preferred:
                keep = max(preferred, key=lambda r: len((r["descripcion"] or "").strip()))
            else:
                keep = max(items, key=lambda r: len((r["descripcion"] or "").strip()))

            keep_ids.add(keep["id"])
            for r in items:
                if r["id"] != keep["id"]:
                    delete_ids.append(r["id"])

        if delete_ids:
            db.executemany("DELETE FROM sedes_depositos WHERE id = ?", [(i,) for i in delete_ids])
            db.commit()
        return len(delete_ids)

    def fetch_depositos():
        rows = db.execute("""
            SELECT id, codigo_local, descripcion
            FROM sedes_depositos
            WHERE codigo_sede = ?
        """, (codigo,)).fetchall()
        dep_rows = []
        for r in rows:
            dep_rows.append({
                "id": r["id"],
                "codigo_local": normalize_local_code(r["codigo_local"]),
                "descripcion": r["descripcion"],
            })
        dep_rows.sort(key=lambda d: local_sort_key(d["codigo_local"]))
        return dep_rows

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()

        if action == "add":
            local_in = request.form.get("codigo_local", "")
            descripcion = (request.form.get("descripcion") or "").strip()
            local_norm = normalize_local_code(local_in)

            if not (local_norm and local_norm.startswith("D") and local_norm[1:].isdigit()):
                flash("Codigo de local invalido (usar D01, D02, etc.).", "warning")
                return redirect(url_for("sede_depositos_edit", codigo=codigo))

            existing = fetch_depositos()
            if any(d["codigo_local"] == local_norm for d in existing):
                flash("Ese local ya existe para esta sede.", "warning")
                return redirect(url_for("sede_depositos_edit", codigo=codigo))

            codigo_local_db = build_storage_code(codigo, local_norm)
            try:
                db.execute(
                    "INSERT INTO sedes_depositos (codigo_sede, codigo_local, descripcion) VALUES (?,?,?)",
                    (codigo, codigo_local_db, descripcion),
                )
                db.commit()
                flash("Deposito agregado.", "success")
            except Exception:
                flash("No se pudo agregar el deposito (codigo duplicado).", "error")

            return redirect(url_for("sede_depositos_edit", codigo=codigo))

        if action == "update":
            dep_id = request.form.get("dep_id")
            local_in = request.form.get("codigo_local", "")
            descripcion = (request.form.get("descripcion") or "").strip()
            local_norm = normalize_local_code(local_in)

            if not dep_id:
                flash("Falta el ID del deposito.", "error")
                return redirect(url_for("sede_depositos_edit", codigo=codigo))

            if not (local_norm and local_norm.startswith("D") and local_norm[1:].isdigit()):
                flash("Codigo de local invalido (usar D01, D02, etc.).", "warning")
                return redirect(url_for("sede_depositos_edit", codigo=codigo))

            existing = fetch_depositos()
            for d in existing:
                if d["codigo_local"] == local_norm and str(d["id"]) != str(dep_id):
                    flash("Ese local ya existe para esta sede.", "warning")
                    return redirect(url_for("sede_depositos_edit", codigo=codigo))

            codigo_local_db = build_storage_code(codigo, local_norm)
            try:
                db.execute(
                    "UPDATE sedes_depositos SET codigo_local = ?, descripcion = ? WHERE id = ? AND codigo_sede = ?",
                    (codigo_local_db, descripcion, dep_id, codigo),
                )
                db.commit()
                flash("Deposito actualizado.", "success")
            except Exception:
                flash("No se pudo actualizar el deposito.", "error")

            return redirect(url_for("sede_depositos_edit", codigo=codigo))

        if action == "cleanup":
            removed = cleanup_duplicates()
            flash(f"Duplicados eliminados: {removed}.", "success")
            return redirect(url_for("sede_depositos_edit", codigo=codigo))

        flash("Accion no valida.", "warning")
        return redirect(url_for("sede_depositos_edit", codigo=codigo))

    depositos = fetch_depositos()
    return render_template(
        "sede_depositos_edit.html",
        sede=sede,
        depositos=depositos,
    )


@app.route("/sedes/depositos/<int:dep_id>/borrar", methods=["POST"], endpoint="sede_depositos_borrar")
def sede_depositos_borrar(dep_id):
    db = get_db()
    row = db.execute(
        "SELECT codigo_sede FROM sedes_depositos WHERE id = ?",
        (dep_id,),
    ).fetchone()
    codigo = (row["codigo_sede"] if row else "").upper().strip()
    if not codigo:
        flash("Deposito no encontrado.", "warning")
        return redirect(url_for("dashboard"))

    db.execute("DELETE FROM sedes_depositos WHERE id = ?", (dep_id,))
    db.commit()
    flash("Deposito eliminado.", "success")
    return redirect(url_for("sede_depositos_edit", codigo=codigo))



@app.route("/sedes/<codigo>/metricas", methods=["GET", "POST"], endpoint="sede_metricas_edit")
def sede_metricas_edit(codigo):
    ensure_sedes_metricas_table()

    con = get_db()
    cur = con.cursor()
    codigo = (codigo or "").upper().strip()

    sede = cur.execute(
        "SELECT codigo, nombre, ciudad FROM sedes_mpd WHERE codigo = ?",
        (codigo,)
    ).fetchone()
    if not sede:
        con.close()
        flash("Sede no encontrada.", "warning")
        return redirect(url_for("dashboard"))

    r = cur.execute(
        "SELECT m2_totales, personas, oficinas, depositos, actualizado_en FROM sedes_metricas WHERE sede_codigo = ?",
        (codigo,)
    ).fetchone()

    def to_int(v):
        v = (v or "").strip()
        digits = "".join(ch for ch in v if ch.isdigit())
        return int(digits) if digits else None

    def to_float(v):
        v = (v or "").strip().replace(",", ".")
        try:
            return float(v) if v else None
        except Exception:
            return None

    if request.method == "POST":
        m2_totales = to_float(request.form.get("m2_totales"))
        personas = to_int(request.form.get("personas"))
        oficinas = to_int(request.form.get("oficinas"))
        depositos = to_int(request.form.get("depositos"))
        actualizado_en = date.today().isoformat()

        cur.execute(
            """
            INSERT INTO sedes_metricas (sede_codigo, m2_totales, personas, oficinas, depositos, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sede_codigo) DO UPDATE SET
                m2_totales=excluded.m2_totales,
                personas=excluded.personas,
                oficinas=excluded.oficinas,
                depositos=excluded.depositos,
                actualizado_en=excluded.actualizado_en
            """,
            (codigo, m2_totales, personas, oficinas, depositos, actualizado_en),
        )
        con.commit()
        con.close()
        flash("Metricas guardadas.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo))

    con.close()
    return render_template("sede_metricas_form.html", sede=sede, r=r)


@app.route("/sedes/<codigo>/evacuacion/responsables", methods=["GET", "POST"])
def eva_responsables_edit(codigo):
    ensure_evacuacion_responsables_table()
    con = get_db()
    cur = con.cursor()

    # Sede
    sede = cur.execute("SELECT * FROM sedes_mpd WHERE codigo = ?", (codigo,)).fetchone()
    if not sede:
        con.close()
        flash("Sede no encontrada.", "danger")
        return redirect(url_for("dashboard"))

    # Pisos: si ya los tenés calculados en tu app, usá eso.
    # Fallback simple:
    pisos = ["PB", "P1", "P2"]

    # Cargar responsables actuales
    rows = cur.execute("""
        SELECT piso, responsable
        FROM evacuacion_responsables
        WHERE sede_codigo = ?
    """, (codigo,)).fetchall()
    evac_responsables = {r["piso"]: (r["responsable"] or "") for r in rows}

    if request.method == "POST":
        for p in pisos:
            val = (request.form.get(f"resp_{p}") or "").strip()
            # Si está vacío: lo dejamos vacío (o podés borrarlo si querés)
            cur.execute("""
                INSERT INTO evacuacion_responsables (sede_codigo, piso, responsable)
                VALUES (?, ?, ?)
                ON CONFLICT(sede_codigo, piso) DO UPDATE SET responsable=excluded.responsable
            """, (codigo, p, val))

        con.commit()
        con.close()
        flash("Responsables guardados.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo, tab="evacuacion"))

    con.close()
    return render_template(
        "eva_responsables_edit.html",
        sede=sede,
        pisos=pisos,
        evac_responsables=evac_responsables
    )


@app.route(
    "/sedes/<codigo>/evacuacion/punto-encuentro",
    methods=["POST"],
    endpoint="sede_evacuacion_punto_encuentro",
)
def sede_evacuacion_punto_encuentro(codigo):
    codigo = (codigo or "").upper().strip()
    url = (request.form.get("url_punto_encuentro") or "").strip()
    piso = (request.form.get("piso") or "PB").upper().strip()
    local = (request.form.get("local") or "").strip()

    con = get_db()
    ensure_sedes_mpd_cols(con)
    con.execute(
        "UPDATE sedes_mpd SET url_punto_encuentro = ? WHERE codigo = ?",
        (url or None, codigo),
    )
    con.commit()
    con.close()

    flash("Punto de encuentro actualizado.", "success")
    return redirect(url_for("sede_ficha", codigo=codigo, tab="evacuacion", piso=piso, local=local))

@app.route("/sedes/resumen")
def sedes_resumen():
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("SELECT codigo, nombre, ciudad, fuero FROM sedes ORDER BY codigo").fetchall()

    # helpers seguros (si alguna tabla no existe aún, no rompe: devolvemos 0)
    def safe_scalar(sql, params=()):
        try:
            r = cur.execute(sql, params).fetchone()
            return (r[0] if r and r[0] is not None else 0)
        except Exception:
            return 0

    rows = []
    tot = {
        "personal": 0,
        "aires": 0,
        "mobiliario_total": 0,
        "luminarias_total": 0,
        "matafuegos_total": 0,
        "matafuegos_vencen_45d": 0
    }

    for s in sedes:
        codigo = s["codigo"]

        personal = safe_scalar("SELECT COUNT(*) FROM personal WHERE codigo_sede = ?", (codigo,))
        aires = safe_scalar("SELECT COUNT(*) FROM aires WHERE codigo_sede = ?", (codigo,))

        # Mobiliario: suma de columnas típicas
        mobiliario_total = safe_scalar("""
            SELECT
              COALESCE(SUM(aire_marca),0)+
              COALESCE(SUM(escritorio_prof),0)+
              COALESCE(SUM(mesa_pc),0)+
              COALESCE(SUM(silla_giratoria),0)+
              COALESCE(SUM(silla_fija),0)+
              COALESCE(SUM(armario_alto),0)+
              COALESCE(SUM(biblioteca_baja),0)+
              COALESCE(SUM(otros),0)
            FROM mobiliario_sede
            WHERE codigo_sede = ? AND COALESCE(activo,1)=1
        """, (codigo,))

        luminarias_total = safe_scalar("""
            SELECT
              COALESCE(SUM(tubo_led_fria),0)+
              COALESCE(SUM(tubo_led_calido),0)+
              COALESCE(SUM(foco_comun),0)+
              COALESCE(SUM(panel_led),0)
            FROM luminarias
            WHERE codigo_sede = ?
        """, (codigo,))

        matafuegos_total = safe_scalar("SELECT COUNT(*) FROM matafuegos WHERE codigo_sede = ?", (codigo,))

        # vencen 45d (si tenés fechas como texto YYYY-MM-DD)
        vencen_45d = safe_scalar("""
            SELECT COUNT(*)
            FROM matafuegos
            WHERE codigo_sede = ?
              AND fecha_vencimiento IS NOT NULL
              AND fecha_vencimiento <= DATE('now', '+45 day')
        """, (codigo,))

        rows.append({
            "codigo": codigo,
            "nombre": s["nombre"],
            "ciudad": s["ciudad"],
            "fuero": s["fuero"],
            "personal": personal,
            "aires": aires,
            "mobiliario_total": mobiliario_total,
            "luminarias_total": luminarias_total,
            "matafuegos_total": matafuegos_total,
            "matafuegos_vencen_45d": vencen_45d
        })

        tot["personal"] += personal
        tot["aires"] += aires
        tot["mobiliario_total"] += mobiliario_total
        tot["luminarias_total"] += luminarias_total
        tot["matafuegos_total"] += matafuegos_total
        tot["matafuegos_vencen_45d"] += vencen_45d

    con.close()
    return render_template("sede_resumen.html", rows=rows, tot=tot)

@app.route("/sedes/resumen-mpd", endpoint="sedes_resumen_mpd")
def sedes_resumen_mpd():
    db = get_db()

    def aires_valid_where(alias: str) -> str:
        return (
            f"((NULLIF(TRIM({alias}.marca),'') IS NOT NULL "
            f"AND UPPER(TRIM({alias}.marca)) NOT IN ('-','PENDIENTE')) "
            f"OR (NULLIF(TRIM({alias}.estado),'') IS NOT NULL) "
            f"OR {alias}.fecha_limpieza IS NOT NULL "
            f"OR {alias}.fecha_ultimo_service IS NOT NULL "
            f"OR {alias}.observaciones IS NOT NULL)"
        )

    sedes_rows = db.execute("""
        SELECT codigo, nombre
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    def safe_scalar(sql, params=()):
        try:
            r = db.execute(sql, params).fetchone()
            return (r[0] if r and r[0] is not None else 0)
        except Exception:
            return 0

    resumen_sedes_rows = []
    resumen_sedes_totals = {
        "mesa_pc": 0,
        "escritorio_prof": 0,
        "aires_total": 0,
        "luminarias_total": 0,
        "puestos_trabajo": 0,
    }

    for s in sedes_rows:
        cod = s["codigo"]
        resumen_sedes_rows.append({
            "codigo": cod,
            "nombre": s["nombre"],
            "mesa_pc": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(mesa_pc,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "escritorio_prof": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(escritorio_prof,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "silla_giratoria": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(silla_giratoria,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "silla_fija": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(silla_fija,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "armario_alto": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(armario_alto,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "biblioteca_baja": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(biblioteca_baja,0)),0)
                FROM mobiliario_sede
                WHERE codigo_sede = ? AND COALESCE(activo,1)=1
            """, (cod,)),
            "aires_total": safe_scalar("""
                SELECT COALESCE(COUNT(*),0)
                FROM aires_sede
                WHERE sede_codigo = ?
                  AND {aires_valid}
            """.format(aires_valid=aires_valid_where("aires_sede")), (cod,)),
            "luminarias_total": safe_scalar("""
                SELECT COALESCE(SUM(
                    COALESCE(tubo_led_fria,0) +
                    COALESCE(tubo_led_calido,0) +
                    COALESCE(foco_comun,0) +
                    COALESCE(panel_led,0)
                ),0)
                FROM luminarias_sede
                WHERE codigo_sede = ?
            """, (cod,)),
            "puestos_trabajo": safe_scalar("""
                SELECT COALESCE(SUM(COALESCE(puestos_trabajo,0)),0)
                FROM luminarias_sede
                WHERE codigo_sede = ?
            """, (cod,)),
        })

    def safe_row_val(row, key):
        try:
            return row[key]
        except Exception:
            return 0

    for k in (
        "mesa_pc",
        "escritorio_prof",
        "silla_giratoria",
        "silla_fija",
        "armario_alto",
        "biblioteca_baja",
        "aires_total",
        "luminarias_total",
        "puestos_trabajo",
    ):
        resumen_sedes_totals.setdefault(k, 0)

    for r in resumen_sedes_rows:
        resumen_sedes_totals["mesa_pc"] += safe_row_val(r, "mesa_pc") or 0
        resumen_sedes_totals["escritorio_prof"] += safe_row_val(r, "escritorio_prof") or 0
        resumen_sedes_totals["silla_giratoria"] += safe_row_val(r, "silla_giratoria") or 0
        resumen_sedes_totals["silla_fija"] += safe_row_val(r, "silla_fija") or 0
        resumen_sedes_totals["armario_alto"] += safe_row_val(r, "armario_alto") or 0
        resumen_sedes_totals["biblioteca_baja"] += safe_row_val(r, "biblioteca_baja") or 0
        resumen_sedes_totals["aires_total"] += safe_row_val(r, "aires_total") or 0
        resumen_sedes_totals["luminarias_total"] += safe_row_val(r, "luminarias_total") or 0
        resumen_sedes_totals["puestos_trabajo"] += safe_row_val(r, "puestos_trabajo") or 0

    return render_template(
        "sedes_resumen_mpd.html",
        rows=resumen_sedes_rows,
        totals=resumen_sedes_totals,
    )

# ============================================================
# MOBILIARIO: NUEVO
# ============================================================
@app.route("/mobiliario/nuevo", methods=["GET", "POST"], endpoint="mobiliario_nuevo")
def mobiliario_nuevo():
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip().upper()
        piso = (request.form.get("piso") or "PB").strip().upper()
        if piso == "2P":
            piso = "P2"
        if piso == "P00":
            piso = "PB"

        codigo_local = (request.form.get("codigo_local") or "").strip().upper()
        descripcion = (request.form.get("descripcion") or "").strip()

        def i(name):
            v = (request.form.get(name) or "0").strip()
            return int(v) if v.isdigit() else 0

        aire_marca = i("aire_marca")
        escritorio_prof = i("escritorio_prof")
        mesa_pc = i("mesa_pc")
        silla_giratoria = i("silla_giratoria")
        silla_fija = i("silla_fija")
        armario_alto = i("armario_alto")
        biblioteca_baja = i("biblioteca_baja")
        otros = i("otros")
        otros_detalle = (request.form.get("otros_detalle") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not codigo_local:
            con.close()
            flash("Sede y Local son obligatorios.", "warning")
            return render_template("mobiliario_form.html", modo="nuevo", sedes=sedes, r=request.form)

        existing = cur.execute("""
            SELECT id
            FROM mobiliario_sede
            WHERE codigo_sede = ? AND COALESCE(piso,'PB') = ? AND codigo_local = ?
        """, (codigo_sede, piso, codigo_local)).fetchone()

        if existing:
            cur.execute("""
                UPDATE mobiliario_sede
                SET descripcion=?,
                    aire_marca=?, escritorio_prof=?, mesa_pc=?, silla_giratoria=?, silla_fija=?,
                    armario_alto=?, biblioteca_baja=?, otros=?, otros_detalle=?, activo=?
                WHERE id=?
            """, (
                descripcion,
                aire_marca, escritorio_prof, mesa_pc, silla_giratoria, silla_fija,
                armario_alto, biblioteca_baja, otros, otros_detalle, activo,
                existing["id"]
            ))
        else:
            cur.execute("""
                INSERT INTO mobiliario_sede
                (codigo_sede, piso, codigo_local, descripcion,
                 aire_marca, escritorio_prof, mesa_pc, silla_giratoria, silla_fija,
                 armario_alto, biblioteca_baja, otros, otros_detalle, activo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                codigo_sede, piso, codigo_local, descripcion,
                aire_marca, escritorio_prof, mesa_pc, silla_giratoria, silla_fija,
                armario_alto, biblioteca_baja, otros, otros_detalle, activo
            ))
        con.commit()
        con.close()

        flash("Mobiliario agregado correctamente.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo_sede, piso=piso, tab="mobiliario", local=codigo_local))

    sede_codigo = (request.args.get("codigo_sede") or "").strip().upper()
    piso = (request.args.get("piso") or "PB").strip().upper()
    if piso == "2P":
        piso = "P2"
    if piso == "1P":
        piso = "P1"
    codigo_local = (request.args.get("codigo_local") or "").strip().upper()

    con.close()
    return render_template("mobiliario_form.html", modo="nuevo", sedes=sedes, r=None,
                           sede_codigo=sede_codigo, piso=piso, codigo_local=codigo_local)


# ============================================================
# MOBILIARIO: EDITAR
# ============================================================
@app.route("/mobiliario/<int:id>/editar", methods=["GET", "POST"], endpoint="mobiliario_editar")
def mobiliario_editar(id):
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    r = cur.execute("""
        SELECT
          id, codigo_sede, COALESCE(piso,'PB') AS piso, codigo_local, descripcion,
          COALESCE(aire_marca,0) AS aire_marca,
          COALESCE(escritorio_prof,0) AS escritorio_prof,
          COALESCE(mesa_pc,0) AS mesa_pc,
          COALESCE(silla_giratoria,0) AS silla_giratoria,
          COALESCE(silla_fija,0) AS silla_fija,
          COALESCE(armario_alto,0) AS armario_alto,
          COALESCE(biblioteca_baja,0) AS biblioteca_baja,
          COALESCE(otros,0) AS otros,
          COALESCE(otros_detalle,'') AS otros_detalle,
          COALESCE(activo,1) AS activo
        FROM mobiliario_sede
        WHERE id = ?
    """, (id,)).fetchone()

    if not r:
        con.close()
        flash("Registro inexistente.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip().upper()
        piso = (request.form.get("piso") or "PB").strip().upper()
        if piso == "2P":
            piso = "P2"
        if piso == "P00":
            piso = "PB"
        codigo_local = (request.form.get("codigo_local") or "").strip().upper()
        descripcion = (request.form.get("descripcion") or "").strip()

        def i(name):
            v = (request.form.get(name) or "0").strip()
            return int(v) if v.isdigit() else 0

        aire_marca = i("aire_marca")
        escritorio_prof = i("escritorio_prof")
        mesa_pc = i("mesa_pc")
        silla_giratoria = i("silla_giratoria")
        silla_fija = i("silla_fija")
        armario_alto = i("armario_alto")
        biblioteca_baja = i("biblioteca_baja")
        otros = i("otros")
        otros_detalle = (request.form.get("otros_detalle") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not codigo_local:
            con.close()
            flash("Sede y Local son obligatorios.", "warning")
            return render_template("mobiliario_form.html", modo="editar", sedes=sedes, r=request.form, id=id)

        cur.execute("""
            UPDATE mobiliario_sede
            SET codigo_sede=?, piso=?, codigo_local=?, descripcion=?,
                aire_marca=?, escritorio_prof=?, mesa_pc=?, silla_giratoria=?, silla_fija=?,
                armario_alto=?, biblioteca_baja=?, otros=?, otros_detalle=?, activo=?
            WHERE id=?
        """, (
            codigo_sede, piso, codigo_local, descripcion,
            aire_marca, escritorio_prof, mesa_pc, silla_giratoria, silla_fija,
            armario_alto, biblioteca_baja, otros, otros_detalle, activo, id
        ))
        con.commit()
        con.close()

        flash("Mobiliario actualizado correctamente.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo_sede, piso=piso, tab="mobiliario", local=codigo_local))

    con.close()
    return render_template("mobiliario_form.html", modo="editar", sedes=sedes, r=r, id=id)


# ============================================================
# MOBILIARIO: ELIMINAR
# ============================================================
@app.route("/mobiliario/<int:id>/eliminar", methods=["POST"], endpoint="mobiliario_eliminar")
def mobiliario_eliminar(id):
    con = get_db()
    cur = con.cursor()

    r = cur.execute(
        "SELECT codigo_sede, COALESCE(piso,'PB') AS piso, codigo_local FROM mobiliario_sede WHERE id = ?",
        (id,)
    ).fetchone()

    cur.execute("DELETE FROM mobiliario_sede WHERE id = ?", (id,))
    con.commit()
    con.close()

    flash("Registro eliminado.", "success")
    if r:
        return redirect(url_for(
            "sede_ficha",
            codigo=r["codigo_sede"],
            piso=r["piso"],
            tab="mobiliario",
            local=r["codigo_local"],
        ))
    return redirect(url_for("dashboard"))


# ============================================================
# LUMINARIAS: NUEVO
# ============================================================
@app.route("/luminarias/nuevo", methods=["GET", "POST"], endpoint="luminarias_nuevo")
def luminarias_nuevo():
    ensure_luminarias_columns()
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip().upper()
        piso = (request.form.get("piso") or "PB").strip().upper()
        if piso == "2P":
            piso = "P2"
        if piso == "1P":
            piso = "P1"
        codigo_local = (request.form.get("codigo_local") or "").strip().upper()

        def i(name):
            v = (request.form.get(name) or "0").strip()
            return int(v) if v.isdigit() else 0

        tubo_led_fria = i("tubo_led_fria")
        tubo_led_calido = i("tubo_led_calido")
        foco_comun = i("foco_comun")
        panel_led = i("panel_led")
        puestos_trabajo = i("puestos_trabajo")
        otros_detalle = (request.form.get("otros_detalle") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not codigo_local:
            con.close()
            flash("Sede y Local son obligatorios.", "warning")
            return render_template("luminarias_form.html", modo="nuevo", sedes=sedes, r=request.form)

        cur.execute("""
            INSERT INTO luminarias_sede
            (codigo_sede, piso, codigo_local, tubo_led_fria, tubo_led_calido, foco_comun, panel_led,
             puestos_trabajo, otros_detalle, activo)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            codigo_sede, piso, codigo_local, tubo_led_fria, tubo_led_calido, foco_comun, panel_led,
            puestos_trabajo, otros_detalle, activo
        ))
        con.commit()
        con.close()

        flash("Luminaria agregada correctamente.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo_sede, piso=piso, tab="luminarias", local=codigo_local))

    sede_codigo = (request.args.get("codigo_sede") or "").strip().upper()
    piso = (request.args.get("piso") or "PB").strip().upper()
    if piso == "2P":
        piso = "P2"
    if piso == "1P":
        piso = "P1"
    codigo_local = (request.args.get("codigo_local") or "").strip().upper()

    con.close()
    return render_template(
        "luminarias_form.html",
        modo="nuevo",
        sedes=sedes,
        r=None,
        sede_codigo=sede_codigo,
        piso=piso,
        codigo_local=codigo_local,
    )


# ============================================================
# LUMINARIAS: EDITAR
# ============================================================
@app.route("/luminarias/<int:id>/editar", methods=["GET", "POST"], endpoint="luminarias_editar")
def luminarias_editar(id):
    ensure_luminarias_columns()
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    r = cur.execute("""
        SELECT
          id, codigo_sede, COALESCE(piso,'PB') AS piso, codigo_local,
          COALESCE(tubo_led_fria,0) AS tubo_led_fria,
          COALESCE(tubo_led_calido,0) AS tubo_led_calido,
          COALESCE(foco_comun,0) AS foco_comun,
          COALESCE(panel_led,0) AS panel_led,
          COALESCE(puestos_trabajo,0) AS puestos_trabajo,
          COALESCE(otros_detalle,'') AS otros_detalle,
          COALESCE(activo,1) AS activo
        FROM luminarias_sede
        WHERE id = ?
    """, (id,)).fetchone()

    if not r:
        con.close()
        flash("Registro inexistente.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        codigo_sede = (request.form.get("codigo_sede") or "").strip().upper()
        piso = (request.form.get("piso") or "PB").strip().upper()
        if piso == "2P":
            piso = "P2"
        if piso == "1P":
            piso = "P1"
        codigo_local = (request.form.get("codigo_local") or "").strip().upper()

        def i(name):
            v = (request.form.get(name) or "0").strip()
            return int(v) if v.isdigit() else 0

        tubo_led_fria = i("tubo_led_fria")
        tubo_led_calido = i("tubo_led_calido")
        foco_comun = i("foco_comun")
        panel_led = i("panel_led")
        puestos_trabajo = i("puestos_trabajo")
        otros_detalle = (request.form.get("otros_detalle") or "").strip()
        activo = 1 if request.form.get("activo") == "1" else 0

        if not codigo_sede or not codigo_local:
            con.close()
            flash("Sede y Local son obligatorios.", "warning")
            return render_template("luminarias_form.html", modo="editar", sedes=sedes, r=request.form, id=id)

        cur.execute("""
            UPDATE luminarias_sede
            SET codigo_sede=?, piso=?, codigo_local=?,
                tubo_led_fria=?, tubo_led_calido=?, foco_comun=?, panel_led=?,
                puestos_trabajo=?, otros_detalle=?, activo=?
            WHERE id=?
        """, (
            codigo_sede, piso, codigo_local,
            tubo_led_fria, tubo_led_calido, foco_comun, panel_led,
            puestos_trabajo, otros_detalle, activo, id
        ))
        con.commit()
        con.close()

        flash("Luminaria actualizada correctamente.", "success")
        return redirect(url_for("sede_ficha", codigo=codigo_sede, piso=piso, tab="luminarias", local=codigo_local))

    con.close()
    return render_template("luminarias_form.html", modo="editar", sedes=sedes, r=r, id=id)


# ============================================================
# LUMINARIAS: ELIMINAR
# ============================================================
@app.route("/luminarias/<int:id>/eliminar", methods=["POST"], endpoint="luminarias_eliminar")
def luminarias_eliminar(id):
    con = get_db()
    cur = con.cursor()

    r = cur.execute(
        "SELECT codigo_sede, COALESCE(piso,'PB') AS piso, codigo_local FROM luminarias_sede WHERE id = ?",
        (id,)
    ).fetchone()

    cur.execute("DELETE FROM luminarias_sede WHERE id = ?", (id,))
    con.commit()
    con.close()

    flash("Registro eliminado.", "success")
    if r:
        return redirect(url_for(
            "sede_ficha",
            codigo=r["codigo_sede"],
            piso=r["piso"],
            tab="luminarias",
            local=r["codigo_local"],
        ))
    return redirect(url_for("dashboard"))


# ============================================================
# AIRES (SEDE): EDITAR
# ============================================================
@app.route("/aires/<int:id>/editar", methods=["GET", "POST"], endpoint="aires_sede_editar")
def aires_sede_editar(id):
    con = get_db()
    cur = con.cursor()

    sedes = cur.execute("""
        SELECT codigo, nombre, ciudad
        FROM sedes_mpd
        ORDER BY codigo
    """).fetchall()

    r = cur.execute("""
        SELECT
          id,
          sede_codigo,
          COALESCE(piso,'PB') AS piso,
          ambiente_codigo,
          ambiente_desc,
          marca,
          estado,
          fecha_limpieza,
          fecha_ultimo_service,
          observaciones
        FROM aires_sede
        WHERE id = ?
    """, (id,)).fetchone()

    if not r:
        con.close()
        flash("Registro inexistente.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
        piso = (request.form.get("piso") or "PB").strip().upper()
        if piso == "2P":
            piso = "P2"
        if piso == "1P":
            piso = "P1"
        if piso == "P00":
            piso = "PB"
        ambiente_codigo = (request.form.get("ambiente_codigo") or "").strip().upper() or None
        ambiente_desc = (request.form.get("ambiente_desc") or "").strip()
        marca = (request.form.get("marca") or "").strip()
        estado = (request.form.get("estado") or "").strip()
        fecha_limpieza = request.form.get("fecha_limpieza") or None
        fecha_ultimo_service = request.form.get("fecha_ultimo_service") or None
        observaciones = (request.form.get("observaciones") or "").strip()

        if not sede_codigo:
            con.close()
            flash("Sede es obligatoria.", "warning")
            return render_template("aires_sede_form.html", modo="editar", sedes=sedes, r=request.form, id=id)

        cur.execute("""
            UPDATE aires_sede
            SET sede_codigo=?, piso=?, ambiente_codigo=?, ambiente_desc=?, marca=?, estado=?,
                fecha_limpieza=?, fecha_ultimo_service=?, observaciones=?
            WHERE id=?
        """, (
            sede_codigo, piso, ambiente_codigo, ambiente_desc, marca, estado,
            fecha_limpieza, fecha_ultimo_service, observaciones, id
        ))
        con.commit()
        con.close()

        flash("Aire actualizado correctamente.", "success")
        return redirect(url_for("sede_ficha", codigo=sede_codigo, piso=piso, tab="aires", local=ambiente_codigo))

    con.close()
    return render_template("aires_sede_form.html", modo="editar", sedes=sedes, r=r, id=id)
@app.route("/matafuegos", methods=["GET","POST"], endpoint="matafuegos_home")
def matafuegos_home():
    db = get_db()

    # filtros
    sede = (request.args.get("sede") or "").upper().strip()
    piso = (request.args.get("piso") or "PB").upper().strip()
    q    = (request.args.get("q") or "").strip()
    edit = request.args.get("edit")

    # normalización
    if piso == "2P": piso = "P2"
    if piso == "1P": piso = "P1"

    # 45 días
    fecha_45d = db.execute("SELECT date('now','+45 day') AS f").fetchone()["f"]

    # -------------------------
    # GUARDAR / ELIMINAR
    # -------------------------
    if request.method == "POST":
        accion = (request.form.get("accion") or "guardar").lower()
        rid = (request.form.get("id") or "").strip()

        # OJO: en tu tabla la columna es cod_sede
        cod_sede = (request.form.get("codigo_sede") or sede or "").upper().strip()
        piso_f   = (request.form.get("piso") or piso or "PB").upper().strip()
        codigo_local = (request.form.get("codigo_local") or "").upper().strip() or None

        estado = (request.form.get("estado") or "OK").upper().strip()
        tipo   = (request.form.get("tipo") or "").strip()
        capacidad_kg = request.form.get("capacidad_kg")
        nro_serie = (request.form.get("nro_serie") or "").strip()
        ubicacion = (request.form.get("ubicacion") or "").strip()
        fecha_recarga = request.form.get("fecha_recarga") or None
        fecha_vencimiento = request.form.get("fecha_vencimiento") or None
        fecha_prueba_hidro = request.form.get("fecha_prueba_hidro") or None
        observaciones = (request.form.get("observaciones") or "").strip()

        activo = 1 if request.form.get("activo") == "1" else 0

        # si te mandan piso "2P/1P"
        if piso_f == "2P": piso_f = "P2"
        if piso_f == "1P": piso_f = "P1"

        if accion == "eliminar" and rid:
            db.execute("UPDATE matafuegos_sede SET activo=0 WHERE id=?", (rid,))
            db.commit()
            flash("Matafuego dado de baja (activo=0).", "success")
            return redirect(url_for("matafuegos_home", sede=cod_sede, piso=piso_f, q=q))

        # guardar (insert/update)
        if rid:
            db.execute("""
                UPDATE matafuegos_sede
                SET cod_sede=?,
                    piso=?,
                    codigo_local=?,
                    ubicacion=?,
                    numero_serie=?,
                    tipo=?,
                    capacidad_kg=?,
                    estado=?,
                    fecha_recarga=?,
                    fecha_vencimiento=?,
                    fecha_prueba_hidro=?,
                    observaciones=?,
                    activo=?
                WHERE id=?
            """, (
                cod_sede, piso_f, codigo_local, ubicacion, nro_serie,
                tipo, capacidad_kg, estado,
                fecha_recarga, fecha_vencimiento, fecha_prueba_hidro,
                observaciones, activo, rid
            ))
        else:
            db.execute("""
                INSERT INTO matafuegos_sede(
                    cod_sede, piso, codigo_local, ubicacion,
                    numero_serie, tipo, capacidad_kg, estado,
                    fecha_recarga, fecha_vencimiento, fecha_prueba_hidro,
                    observaciones, activo
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                cod_sede, piso_f, codigo_local, ubicacion,
                nro_serie, tipo, capacidad_kg, estado,
                fecha_recarga, fecha_vencimiento, fecha_prueba_hidro,
                observaciones, activo
            ))

        db.commit()
        flash("Matafuego guardado.", "success")
        return redirect(url_for("matafuegos_home", sede=cod_sede, piso=piso_f, q=q))

    # -------------------------
    # EDIT ROW
    # -------------------------
    edit_row = None
    if edit:
        edit_row = db.execute("""
            SELECT
                id,
                cod_sede AS codigo_sede,   -- alias para tu template
                COALESCE(piso,'PB') AS piso,
                codigo_local,
                ubicacion,
                numero_serie AS nro_serie, -- alias para tu template
                tipo,
                capacidad_kg,
                estado,
                fecha_recarga,
                fecha_vencimiento,
                fecha_prueba_hidro,
                observaciones,
                COALESCE(activo,1) AS activo
            FROM matafuegos_sede
            WHERE id=?
        """, (edit,)).fetchone()

        # si edita uno, setea filtros
        if edit_row:
            sede = (edit_row["codigo_sede"] or sede)
            piso = (edit_row["piso"] or piso)

    # -------------------------
    # LISTA + KPI
    # -------------------------
    where = ["COALESCE(m.activo,1)=1"]
    params = []

    if sede:
        where.append("m.cod_sede = ?")
        params.append(sede)

    if piso:
        where.append("COALESCE(m.piso,'PB') = ?")
        params.append(piso)

    if q:
        where.append("""(
            COALESCE(m.codigo_local,'') LIKE ?
            OR COALESCE(m.tipo,'') LIKE ?
            OR COALESCE(m.numero_serie,'') LIKE ?
            OR COALESCE(m.ubicacion,'') LIKE ?
        )""")
        like = f"%{q}%"
        params.extend([like, like, like, like])

    rows = db.execute(f"""
        SELECT
            m.id,
            m.cod_sede AS codigo_sede,      -- alias
            COALESCE(m.piso,'PB') AS piso,
            m.codigo_local,
            m.tipo,
            m.capacidad_kg,
            m.ubicacion,
            m.numero_serie AS nro_serie,    -- alias
            m.fecha_vencimiento,
            m.estado
        FROM matafuegos_sede m
        WHERE {" AND ".join(where)}
        ORDER BY COALESCE(m.codigo_local,''), COALESCE(m.ubicacion,''), COALESCE(m.numero_serie,'')
    """, params).fetchall()

    kpi = db.execute(f"""
        SELECT
          COALESCE(COUNT(*),0) AS total,
          COALESCE(SUM(
            CASE
              WHEN m.fecha_vencimiento IS NOT NULL
               AND date(m.fecha_vencimiento) <= date('now','+45 day')
              THEN 1 ELSE 0
            END
          ),0) AS vencen_pronto
        FROM matafuegos_sede m
        WHERE {" AND ".join(where)}
    """, params).fetchone()

    return render_template(
        "matafuegos_home.html",
        sede=sede,
        piso=piso,
        q=q,
        rows=rows,
        kpi=kpi,
        edit_row=edit_row,
        fecha_45d=fecha_45d
    )
@app.route("/remitos/<path:filename>")
def ver_remito(filename):
    return redirect(url_for("combustible_remito_ver", filename=filename))

@app.route("/maestranza")
def maestranza_home():
    return render_template("placeholder.html", titulo="Maestranza")

# =========================
# ADMIN - USUARIOS
# =========================

@app.route("/admin/usuarios")
def admin_usuarios():
    # Solo accesible para el rol FULL (full) o 'admin'
    if session.get("role") not in [ROLE_FULL, "admin"]:
        return redirect(url_for("access_denied"))
    
    con = get_db()
    # Traemos todos los usuarios, manejando la inconsistencia de columnas 'role' y 'rol'
    # y devolviendo 'Sin rol' si ambos son nulos.
    users = con.execute("""
        SELECT 
            id, 
            username, 
            full_name, 
            COALESCE(role, rol) as role, 
            password, 
            activo
        FROM usuarios
        ORDER BY username
    """).fetchall()
    con.close()
    return render_template("usuarios.html", users=users)

@app.route("/admin/usuarios/<int:uid>/edit", methods=["POST"])
def admin_usuarios_edit(uid):
    if session.get("role") not in [ROLE_FULL, "admin"]:
        return redirect(url_for("access_denied"))
    
    new_password = request.form.get("new_password", "").strip()
    new_role = request.form.get("new_role", "").strip()
    must_change = 1 if request.form.get("force_change") else 0
    
    con = get_db()
    
    # Actualizamos el rol si se proporcionó
    if new_role:
        con.execute("UPDATE usuarios SET role = ?, rol = ? WHERE id = ?", (new_role, new_role, uid))
    
    # Actualizamos la contraseña solo si se proporcionó una nueva
    if new_password:
        con.execute("""
            UPDATE usuarios 
            SET password_hash = ?, 
                password = ?, 
                must_change = ? 
            WHERE id = ?
        """, (generate_password_hash(new_password), new_password, must_change, uid))
    
    con.commit()
    con.close()
    
    flash("Usuario actualizado correctamente.", "success")
    return redirect(url_for("admin_usuarios"))

if __name__ == "__main__":
    init_tabla_calendario_eventos()  # crea tabla eventos si no existe

    with app.app_context():
        rebuild_eventos_agentes()
        rebuild_eventos_vehiculos()
        rebuild_eventos_obras()
        rebuild_eventos_inventario()
        rebuild_eventos_seguridad_limpieza()
        rebuild_eventos_limpieza_sede()


        app.run(host="0.0.0.0", debug=True)
