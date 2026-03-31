from datetime import date


SEDE_ESTADO_VARS = [
    "relevamiento",
    "obra_terminada",
    "matafuegos_recarga",
    "carteleria",
    "luces_emergencia",
    "plano_evac",
    "orden_limpieza",
    "senalizacion",
    "accesibilidad",
    "riesgo_electrico",
]

SEDE_ESTADO_LABELS = {
    "relevamiento": "Relevamiento",
    "obra_terminada": "Obra terminada",
    "matafuegos_recarga": "Matafuegos recarga",
    "carteleria": "Carteleria",
    "luces_emergencia": "Luces emergencia",
    "plano_evac": "Plano evacuacion",
    "orden_limpieza": "Orden / limpieza",
    "senalizacion": "Senalizacion",
    "accesibilidad": "Accesibilidad",
    "riesgo_electrico": "Riesgo electrico",
}

NVD_TIPO_SUBTIPOS = {
    "Licencia": ["Particular", "Compensatorio", "Horas extra", "Cambio de horario", "Otro"],
    "Pedido de materiales": [
        "Pintura", "Durlock", "Construccion", "Plomeria", "Albanileria",
        "Aire acondicionado", "Desinfeccion", "Humedad", "Limpieza", "Electricidad",
        "Mobiliario", "Herreria", "Mudanza", "Otros",
    ],
    "Uso de salon": ["Reserva", "Cambio de fecha", "Armado de mesas", "Cantidad de personas"],
    "Reclamo / mantenimiento": [
        "Iluminacion", "Agua", "Bano", "Electricidad", "Cerradura",
        "Humedad", "Mobiliario", "Limpieza", "Otro",
    ],
    "Gestion operativa": [
        "Cargar horario especial",
        "Cargar por sistema",
        "Pedir por sistema",
        "Solicitud especial",
        "Reunion / recordar",
        "Te busco / coordinacion",
        "Otro",
    ],
    "Vehiculo": [
        "Guardar vehiculo (patente)",
        "Mecanico / necesita arreglo",
        "Necesita arreglo urgente",
        "Necesita reparacion",
        "Carga por sistema",
        "Otro",
    ],
    "Vehiculos": [
        "Guardar vehiculo (patente)",
        "Mecanico / necesita arreglo",
        "Necesita arreglo urgente",
        "Necesita reparacion",
        "Carga por sistema",
        "Otro",
    ],
    "Aviso general": ["Novedad diaria", "Reorganizacion", "Cambio operativo", "Otro"],
    "Otro": ["General"],
}

NVD_ESTADOS = ["Informado", "En proceso", "Resuelto"]


def _table_exists(con, table_name):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _table_cols(con, table_name):
    try:
        rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {r["name"] for r in rows}
    except Exception:
        return set()


def _row_value(row, key, default=0):
    try:
        if row is None:
            return default
        return row[key]
    except Exception:
        return default


def _ensure_novedades_catalogo_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_novedades_catalogo(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT NOT NULL,             -- sede | tipo | subtipo
            tipo_ref TEXT DEFAULT '',        -- requerido cuando grupo=subtipo
            valor TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            creado_en TEXT
        )
    """)
    cols = _table_cols(con, "dashboard_novedades_catalogo")
    for name, sql_type in (
        ("grupo", "TEXT"),
        ("tipo_ref", "TEXT DEFAULT ''"),
        ("valor", "TEXT"),
        ("activo", "INTEGER DEFAULT 1"),
        ("creado_en", "TEXT"),
    ):
        if name not in cols:
            try:
                con.execute(f"ALTER TABLE dashboard_novedades_catalogo ADD COLUMN {name} {sql_type}")
            except Exception:
                pass
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_nvd_cat_grupo
        ON dashboard_novedades_catalogo(grupo, tipo_ref, activo)
    """)
    con.commit()


def _append_unique_ci(items, value):
    v = (value or "").strip()
    if not v:
        return
    lk = v.lower()
    for x in items:
        if (x or "").strip().lower() == lk:
            return
    items.append(v)


def _nvd_tipos_subtipos(con):
    out = {k: list(v) for k, v in (NVD_TIPO_SUBTIPOS or {}).items()}
    try:
        _ensure_novedades_catalogo_table(con)
        rows = con.execute("""
            SELECT
                LOWER(COALESCE(grupo,'')) AS grupo,
                COALESCE(tipo_ref,'') AS tipo_ref,
                COALESCE(valor,'') AS valor
            FROM dashboard_novedades_catalogo
            WHERE COALESCE(activo,1)=1
            ORDER BY id
        """).fetchall()
        for r in rows:
            grupo = (_row_value(r, "grupo", "") or "").strip().lower()
            tipo_ref = (_row_value(r, "tipo_ref", "") or "").strip()
            valor = (_row_value(r, "valor", "") or "").strip()
            if not valor:
                continue
            if grupo == "tipo":
                if valor not in out:
                    out[valor] = ["General"]
                continue
            if grupo == "subtipo":
                if not tipo_ref:
                    continue
                if tipo_ref not in out:
                    out[tipo_ref] = ["General"]
                _append_unique_ci(out[tipo_ref], valor)
    except Exception:
        pass
    return out


def _ensure_novedades_diarias_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS novedades_diarias(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            agente TEXT,
            sede_codigo TEXT,
            tipo TEXT NOT NULL,
            subtipo TEXT,
            observacion TEXT,
            estado TEXT DEFAULT 'Informado',
            tarea_asignada TEXT DEFAULT '',
            tarea_estado TEXT DEFAULT '',
            tarea_sede_codigo TEXT DEFAULT '',
            tarea_deposito_codigo TEXT DEFAULT '',
            tarea_deposito_nombre TEXT DEFAULT '',
            tarea_agente TEXT DEFAULT '',
            tarea_herramientas_json TEXT DEFAULT '',
            tarea_asignado_por TEXT DEFAULT '',
            tarea_asignado_por_username TEXT DEFAULT '',
            tarea_asignado_en TEXT,
            tarea_actualizado_en TEXT,
            privado_flag INTEGER DEFAULT 0,
            privado_owner_username TEXT DEFAULT '',
            privado_owner_nombre TEXT DEFAULT '',
            creado_en TEXT,
            actualizado_en TEXT
        )
    """)
    cols = _table_cols(con, "novedades_diarias")
    for name, sql_type in (
        ("hora", "TEXT"),
        ("agente", "TEXT"),
        ("sede_codigo", "TEXT"),
        ("subtipo", "TEXT"),
        ("observacion", "TEXT"),
        ("estado", "TEXT DEFAULT 'Informado'"),
        ("tarea_asignada", "TEXT DEFAULT ''"),
        ("tarea_estado", "TEXT DEFAULT ''"),
        ("tarea_sede_codigo", "TEXT DEFAULT ''"),
        ("tarea_deposito_codigo", "TEXT DEFAULT ''"),
        ("tarea_deposito_nombre", "TEXT DEFAULT ''"),
        ("tarea_agente", "TEXT DEFAULT ''"),
        ("tarea_herramientas_json", "TEXT DEFAULT ''"),
        ("tarea_asignado_por", "TEXT DEFAULT ''"),
        ("tarea_asignado_por_username", "TEXT DEFAULT ''"),
        ("tarea_asignado_en", "TEXT"),
        ("tarea_actualizado_en", "TEXT"),
        ("privado_flag", "INTEGER DEFAULT 0"),
        ("privado_owner_username", "TEXT DEFAULT ''"),
        ("privado_owner_nombre", "TEXT DEFAULT ''"),
        ("creado_en", "TEXT"),
        ("actualizado_en", "TEXT"),
    ):
        if name not in cols:
            try:
                con.execute(f"ALTER TABLE novedades_diarias ADD COLUMN {name} {sql_type}")
            except Exception:
                pass
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_novedades_diarias_fecha
        ON novedades_diarias(fecha)
    """)
    con.commit()


def _ensure_novedades_diarias_chat_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS novedades_diarias_chat(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            novedad_id INTEGER NOT NULL,
            autor TEXT NOT NULL,
            autor_username TEXT,
            mensaje TEXT NOT NULL,
            es_sistema INTEGER DEFAULT 0,
            creado_en TEXT NOT NULL
        )
    """)
    cols = _table_cols(con, "novedades_diarias_chat")
    for name, sql_type in (
        ("novedad_id", "INTEGER NOT NULL"),
        ("autor", "TEXT NOT NULL"),
        ("autor_username", "TEXT"),
        ("mensaje", "TEXT NOT NULL"),
        ("es_sistema", "INTEGER DEFAULT 0"),
        ("creado_en", "TEXT NOT NULL"),
    ):
        if name not in cols:
            try:
                con.execute(f"ALTER TABLE novedades_diarias_chat ADD COLUMN {name} {sql_type}")
            except Exception:
                pass
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_novedades_diarias_chat_novedad
        ON novedades_diarias_chat(novedad_id, id)
    """)
    con.commit()


def _safe_today():
    return date.today().isoformat()


def _norm_nvd_estado(raw):
    v = (raw or "").strip().lower()
    if v in ("resuelto", "cerrado"):
        return "Resuelto"
    if v in ("en revision", "en revisión", "revision", "revisión", "en proceso", "proceso"):
        return "En proceso"
    if v in ("informado",):
        return "Informado"
    return "Informado"


def _novedades_resumen(con, fecha_iso):
    out = {"total": 0, "informado": 0, "en_proceso": 0, "resuelto": 0}
    try:
        rows = con.execute("""
            SELECT LOWER(COALESCE(estado,'informado')) AS estado, COUNT(*) AS n
            FROM novedades_diarias
            WHERE date(fecha) = date(?)
            GROUP BY LOWER(COALESCE(estado,'informado'))
        """, (fecha_iso,)).fetchall()
        total = 0
        for r in rows:
            est = (_row_value(r, "estado", "") or "").strip()
            n = int(_row_value(r, "n", 0) or 0)
            total += n
            if est in ("informado",):
                out["informado"] += n
            elif est in ("en revision", "en revisión", "en proceso", "proceso"):
                out["en_proceso"] += n
            elif est in ("resuelto", "cerrado"):
                out["resuelto"] += n
        out["total"] = total
    except Exception:
        pass
    return out


def _dashboard_sedes_opts(con):
    sedes = []
    try:
        _ensure_novedades_catalogo_table(con)
        sedes.append({"codigo": "OTRO", "nombre": "Fuera de sede / General"})
        if not _table_exists(con, "sedes_mpd"):
            pass
        else:
            cols = _table_cols(con, "sedes_mpd")
            if "codigo" in cols:
                nombre_col = "nombre" if "nombre" in cols else ("nombre_sede" if "nombre_sede" in cols else "''")
                rows = con.execute(f"""
                    SELECT
                        COALESCE(codigo,'') AS codigo,
                        COALESCE({nombre_col},'') AS nombre
                    FROM sedes_mpd
                    ORDER BY codigo
                """).fetchall()
                for r in rows:
                    c = (_row_value(r, "codigo", "") or "").strip().upper()
                    if not c or c == "OTRO":
                        continue
                    n = (_row_value(r, "nombre", "") or "").strip()
                    sedes.append({"codigo": c, "nombre": n or c})

        rows_custom = con.execute("""
            SELECT COALESCE(valor,'') AS valor
            FROM dashboard_novedades_catalogo
            WHERE COALESCE(activo,1)=1 AND LOWER(COALESCE(grupo,''))='sede'
            ORDER BY id
        """).fetchall()
        seen = {((x.get("codigo") or "").strip().upper()) for x in sedes}
        for r in rows_custom:
            v = (_row_value(r, "valor", "") or "").strip().upper()
            if not v or v in seen:
                continue
            seen.add(v)
            sedes.append({"codigo": v, "nombre": v})
    except Exception:
        pass
    return sedes


def _dashboard_agentes_opts(con):
    vals = []
    seen = set()
    try:
        if _table_exists(con, "agentes_intendencia"):
            cols = _table_cols(con, "agentes_intendencia")
            activo_expr = "COALESCE(activo,1)=1" if "activo" in cols else "1=1"
            rows = con.execute(f"""
                SELECT COALESCE(agente,'') AS agente
                FROM agentes_intendencia
                WHERE {activo_expr}
                ORDER BY agente
            """).fetchall()
            for r in rows:
                a = (_row_value(r, "agente", "") or "").strip()
                k = a.lower()
                if not a or k in seen:
                    continue
                seen.add(k)
                vals.append(a)
    except Exception:
        pass
    return vals


def _dashboard_vehiculos_simple(con, fecha_iso):
    out = []
    try:
        if not _table_exists(con, "vehiculos"):
            return out
        vcols = _table_cols(con, "vehiculos")
        tcols = _table_cols(con, "viajes")
        if "patente" not in vcols:
            return out
        alias_expr = "COALESCE(v.codigo_interno,'')" if "codigo_interno" in vcols else "''"
        activo_expr = "COALESCE(v.activo,1)" if "activo" in vcols else "1"
        join_sql = ""
        params = []
        if _table_exists(con, "viajes") and {"patente", "fecha"}.issubset(tcols):
            estado_expr = "UPPER(COALESCE(estado,''))" if "estado" in tcols else "''"
            join_sql = f"""
                LEFT JOIN (
                    SELECT
                        patente,
                        MAX(CASE WHEN {estado_expr} IN ('ABIERTO','EN CURSO','EN_CURSO','PENDIENTE CIERRE','PENDIENTE_CIERRE') THEN 1 ELSE 0 END) AS has_open,
                        MAX(CASE WHEN date(fecha) = date(?) THEN 1 ELSE 0 END) AS has_trip
                    FROM viajes
                    GROUP BY patente
                ) h ON h.patente = v.patente
            """
            params.append(fecha_iso)
        rows = con.execute(f"""
            SELECT
                COALESCE(v.patente,'') AS patente,
                {alias_expr} AS alias,
                {activo_expr} AS activo,
                COALESCE(h.has_open, 0) AS has_open,
                COALESCE(h.has_trip, 0) AS has_trip
            FROM vehiculos v
            {join_sql}
            WHERE COALESCE({activo_expr},1)=1
            ORDER BY alias, patente
        """, tuple(params)).fetchall()
        for r in rows:
            pat = (_row_value(r, "patente", "") or "").strip().upper()
            if not pat:
                continue
            alias = (_row_value(r, "alias", "") or "").strip().upper()
            has_open = int(_row_value(r, "has_open", 0) or 0)
            estado = "En uso" if has_open else "Disponible"
            out.append({
                "patente": pat,
                "codigo": alias or pat,
                "estado": estado,
            })
    except Exception:
        pass
    return out


def _dashboard_alertas_criticas(data):
    kws = (
        "venc", "vence", "vtv", "rtv", "seguro", "carnet",
        "matafuego", "service", "servicio", "licencia",
    )
    fuentes_criticas = ("obras", "seguridad", "calendario_pedidos", "limpieza_sede")
    items = []
    seen = set()

    def _add(txt, fuente):
        t = (txt or "").strip()
        if not t:
            return
        k = t.lower()
        if k in seen:
            return
        seen.add(k)
        items.append({"texto": t, "fuente": fuente})

    def _ev_es_critico(ev):
        titulo = str(ev.get("titulo") or "").strip()
        detalle = str(ev.get("detalle") or "").strip()
        fuente = str(ev.get("fuente") or "").strip().lower()
        raw = (titulo + " " + detalle).lower()
        if any(k in raw for k in kws):
            return True
        if fuente in fuentes_criticas:
            return True
        if "prioridad: alta" in raw:
            return True
        return False

    def _ev_txt(ev):
        fecha = str(ev.get("fecha") or "").strip()
        titulo = str(ev.get("titulo") or "").strip()
        base = (fecha + " - " + titulo).strip(" -")
        return base

    for ev in (data.get("calendario", {}) or {}).get("hoy", []) or []:
        _add(_ev_txt(ev), "Calendario")

    for ev in (data.get("calendario", {}) or {}).get("proximos7", []) or []:
        if _ev_es_critico(ev):
            _add(_ev_txt(ev), "Calendario")

    for r in data.get("recordatorios", []) or []:
        raw = str(r or "").lower()
        if any(k in raw for k in kws):
            _add(str(r), "Recordatorio")

    for v in (data.get("vehiculos", {}) or {}).get("topAsignacion", []) or []:
        est = str(v.get("estado") or "").lower()
        if "pendiente cierre" in est:
            _add(f"{v.get('patente','-')} pendiente de cierre de viaje", "Vehiculos")

    return items[:50]


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


def _ensure_dashboard_vehiculos_manual_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_vehiculos_manual(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            vehiculo TEXT NOT NULL,
            chofer TEXT,
            destino TEXT,
            hora_salida TEXT,
            hora_regreso_estimada TEXT,
            estado TEXT DEFAULT 'En uso',
            combustible TEXT,
            materiales TEXT,
            actualizado_en TEXT
        )
    """)
    cols = _table_cols(con, "dashboard_vehiculos_manual")
    for c in ("agente_traslado", "observaciones"):
        if c not in cols:
            try:
                con.execute(f"ALTER TABLE dashboard_vehiculos_manual ADD COLUMN {c} TEXT")
            except Exception:
                pass
    con.commit()


def _ensure_dashboard_turnos_choferes_cfg(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_turnos_choferes_cfg(
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mes_mensual TEXT,
            chofer_mensual TEXT,
            semana_desde TEXT,
            semana_hasta TEXT,
            chofer_semanal TEXT,
            actualizado_en TEXT
        )
    """)
    con.execute("INSERT OR IGNORE INTO dashboard_turnos_choferes_cfg(id) VALUES (1)")
    con.commit()


def _ensure_dashboard_vehiculos_cfg(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_vehiculos_cfg(
            id INTEGER PRIMARY KEY CHECK (id = 1),
            responsable_tactico TEXT,
            actualizado_en TEXT
        )
    """)
    con.execute("""
        INSERT OR IGNORE INTO dashboard_vehiculos_cfg(id, responsable_tactico)
        VALUES (1, 'Ignacio Baroni')
    """)
    con.commit()


def _ensure_dashboard_turnos_choferes_ack_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_turnos_choferes_ack(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,                -- mensual / semanal
            periodo_ref TEXT NOT NULL,         -- YYYY-MM o YYYY-MM-DD|YYYY-MM-DD
            chofer TEXT NOT NULL,
            aceptado_en TEXT NOT NULL,
            aceptado_por TEXT,
            observaciones TEXT,
            UNIQUE(tipo, periodo_ref, chofer)
        )
    """)
    con.commit()


def _ensure_dashboard_rotacion_limpieza_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_rotacion_limpieza(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ref TEXT NOT NULL,           -- YYYY-MM
            sede TEXT NOT NULL,              -- S01 / S08 / S13 / S14
            turno TEXT NOT NULL,             -- Matutino / Vespertino
            grupo TEXT,                      -- GR1..GR4
            agente TEXT NOT NULL,
            actualizado_en TEXT
        )
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_dashboard_rotacion_limpieza
        ON dashboard_rotacion_limpieza(mes_ref, sede, turno)
    """)
    con.commit()


def _ensure_dashboard_novedades_obra_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_novedades_obra(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            texto TEXT NOT NULL,
            urgente INTEGER DEFAULT 0,
            tipo TEXT DEFAULT 'novedad',
            estado TEXT DEFAULT 'nuevo',
            responsable TEXT DEFAULT '',
            creado_en TEXT
        )
    """)
    cols = _table_cols(con, "dashboard_novedades_obra")
    if "urgente" not in cols:
        try:
            con.execute("ALTER TABLE dashboard_novedades_obra ADD COLUMN urgente INTEGER DEFAULT 0")
        except Exception:
            pass
    if "tipo" not in cols:
        try:
            con.execute("ALTER TABLE dashboard_novedades_obra ADD COLUMN tipo TEXT DEFAULT 'novedad'")
        except Exception:
            pass
    if "estado" not in cols:
        try:
            con.execute("ALTER TABLE dashboard_novedades_obra ADD COLUMN estado TEXT DEFAULT 'nuevo'")
        except Exception:
            pass
    if "responsable" not in cols:
        try:
            con.execute("ALTER TABLE dashboard_novedades_obra ADD COLUMN responsable TEXT DEFAULT ''")
        except Exception:
            pass
    con.commit()
