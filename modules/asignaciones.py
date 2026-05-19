import csv
import io
from datetime import date, datetime, timedelta

from flask import flash, jsonify, make_response, redirect, render_template, request, session, url_for


def register_asignaciones(app, get_db):
    if getattr(app, "_asignaciones_registered", False):
        return
    app._asignaciones_registered = True

    CHOFERES_SEED = [
        ("Mauro Vea Murguia", 1),
        ("Emiliano P. de la Puente", 2),
        ("Gaston Villagra", 3),
        ("Jorge Corbacho", 4),
    ]
    DESTINOS_SEED = [
        ("Itinerancia", "Susques", "Pesado / jornada extendida", 4),
        ("Quebrada", "Tilcara", "Largo", 3),
        ("Quebrada", "Humahuaca", "Largo", 3),
        ("Norte", "La Quiaca", "Pesado / jornada extendida", 4),
        ("Norte", "Abra Pampa", "Pesado / jornada extendida", 4),
        ("Ramal", "Ledesma", "Largo", 3),
        ("Ramal", "San Pedro", "Medio", 2),
        ("Aledanos", "Perico", "Cercano", 1),
        ("Aledanos", "Palpala", "Cercano", 1),
        ("Aledanos", "Alto Comedero", "Cercano", 1),
        ("Especial", "Otro", "Medio", 2),
    ]
    CARGA_TO_PUNTAJE = {
        "cercano": 1,
        "medio": 2,
        "largo": 3,
        "pesado / jornada extendida": 4,
        "pesado": 4,
    }
    ESTADOS = [
        "Programado",
        "Asignado",
        "Realizado",
        "Cancelado",
        "Salta turno",
        "No afecta rotacion",
    ]
    ESTADOS_PLANILLA = ["Pendiente", "Asignado", "Realizado", "Cancelado"]
    ESTADOS_ROT_SIMPLE = ["Programado", "Realizado", "Cancelado"]
    PERIODOS_VALIDOS = [30, 60, 90, 365]
    ROTACION_SIMPLE_SEED = [
        ("Itinerancia Susques", "Programado", "2026-05-21", "Gaston Villagra", "Mauro Vea Murguia", "Jornada extendida"),
        ("Ledesma / San Pedro", "Programado", "", "Jorge Corbacho", "Emiliano P. de la Puente", ""),
        ("Perico", "Programado", "", "Emiliano P. de la Puente", "Mauro Vea Murguia", ""),
        ("La Quiaca", "Programado", "", "Mauro Vea Murguia", "Gaston Villagra", ""),
        ("Viaje largo general", "Programado", "", "Jorge Corbacho", "Mauro Vea Murguia", ""),
        ("Otro especial", "Programado", "", "Emiliano P. de la Puente", "Jorge Corbacho", ""),
    ]
    ROTACION_TIPOS = ["Itinerancia", "Ramal", "Norte", "Quebrada", "Especial"]
    CHOFER_COLOR_SEED = {
        "mauro vea murguia": "#7c3aed",      # violeta
        "mauro vea murguía": "#7c3aed",
        "gaston villagra": "#16a34a",        # verde
        "gastón villagra": "#16a34a",
        "jorge corbacho": "#2563eb",         # azul
        "emiliano p. de la puente": "#92400e",  # marron
    }
    DESTINOS_REFERENCIA_SEED = [
        ("Itinerancia", "Susques", "400 km aprox ida y vuelta", "7 hs aprox", "07:00", "21:00", "Pesado / jornada extendida", 1, "Viaje de jornada extendida."),
        ("Norte", "La Quiaca", "600 km aprox ida y vuelta", "8 hs aprox", "07:00", "23:00", "Pesado / jornada extendida", 1, "Programar con anticipacion."),
        ("Norte", "Abra Pampa", "500 km aprox ida y vuelta", "7 hs aprox", "07:00", "22:00", "Pesado / jornada extendida", 1, ""),
        ("Ramal", "Ledesma", "230 km aprox ida y vuelta", "3 hs aprox", "13:00", "18:00", "Largo", 0, "Puede salir luego de las 13:00."),
        ("Ramal", "San Pedro", "150 km aprox ida y vuelta", "2 hs aprox", "08:00", "12:00", "Medio", 0, ""),
        ("Quebrada", "Tilcara", "200 km aprox ida y vuelta", "4 hs aprox", "07:00", "17:00", "Largo", 0, ""),
        ("Quebrada", "Humahuaca", "260 km aprox ida y vuelta", "5 hs aprox", "07:00", "18:00", "Largo", 0, ""),
        ("Especial", "Otro", "", "", "", "", "Medio", 0, "Completar segun operativa real."),
    ]

    def _role() -> str:
        return (session.get("role") or "").strip().lower()

    def _username() -> str:
        return (session.get("username") or "").strip().lower()

    def _can_access() -> bool:
        role = _role()
        user = _username()
        if role in {"full", "admin", "int_vehiculos", "dashboard_vehiculos", "operativo_clave"}:
            return True
        return user in {"mcalderari", "admi", "ibaroni", "fsavio"}

    def _deny():
        try:
            flash("Acceso restringido a Intendencia.", "warning")
            return redirect(url_for("access_denied"))
        except Exception:
            return redirect(url_for("dashboard_exec"))

    def _norm(s):
        return (str(s or "").strip()).lower()

    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _today_iso():
        return date.today().isoformat()

    def _now_ts():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _parse_iso(d):
        try:
            return datetime.strptime(str(d or "").strip(), "%Y-%m-%d").date()
        except Exception:
            return None

    def _fmt_dmy(iso_date):
        d = _parse_iso(iso_date)
        if not d:
            return ""
        return d.strftime("%d/%m/%Y")

    def _period_or_default(v, default=60):
        p = _to_int(v, default)
        if p not in PERIODOS_VALIDOS:
            return default
        return p

    def _period_range(periodo, ref_iso=None):
        ref = _parse_iso(ref_iso) or date.today()
        since = ref - timedelta(days=max(1, int(periodo)) - 1)
        return since.isoformat(), ref.isoformat()

    def _estado_norm_for_calc(estado):
        e = _norm(estado)
        if e == "no afecta rotacion":
            return "noafecta"
        if e == "cancelado":
            return "cancelado"
        return "ok"

    def _puntaje_by_carga(tipo_carga):
        return CARGA_TO_PUNTAJE.get(_norm(tipo_carga), 0)

    def _ensure_schema(con):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS choferes_rotacion(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                activo INTEGER NOT NULL DEFAULT 1,
                orden_rotacion INTEGER NOT NULL DEFAULT 999,
                observaciones TEXT,
                creado_en TEXT DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS destinos_rotacion(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona TEXT NOT NULL,
                destino TEXT NOT NULL,
                tipo_carga TEXT NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 1,
                activo INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT,
                UNIQUE(zona, destino)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS asignaciones_rotacion(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                zona TEXT NOT NULL,
                destino TEXT NOT NULL,
                tipo_viaje TEXT,
                tipo_carga TEXT NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                chofer_id INTEGER NOT NULL,
                vehiculo TEXT,
                afecta_rotacion INTEGER NOT NULL DEFAULT 1,
                estado TEXT NOT NULL DEFAULT 'Programado',
                motivo TEXT,
                observaciones TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now')),
                actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS exclusiones_chofer(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chofer_id INTEGER NOT NULL,
                fecha_desde TEXT NOT NULL,
                fecha_hasta TEXT NOT NULL,
                motivo TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracion_rotacion(
                id INTEGER PRIMARY KEY CHECK (id = 1),
                periodo_default INTEGER NOT NULL DEFAULT 60,
                criterio_empate TEXT NOT NULL DEFAULT 'puntos|pesado_antiguo|menos_viajes|orden',
                observaciones TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS planilla_diaria(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                hora_salida TEXT,
                hora_regreso_estimada TEXT,
                chofer_id INTEGER,
                vehiculo TEXT,
                solicitante TEXT,
                destino TEXT,
                tipo_asignacion TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                observaciones TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now')),
                actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rotacion_simple_viajes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden INTEGER NOT NULL DEFAULT 999,
                viaje_destino TEXT NOT NULL UNIQUE,
                estado TEXT NOT NULL DEFAULT 'Programado',
                fecha TEXT,
                chofer_actual_id INTEGER,
                proximo_chofer_id INTEGER,
                observacion TEXT,
                actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rotacion_visual_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_viaje TEXT NOT NULL,
                posicion INTEGER NOT NULL,
                chofer_id INTEGER NOT NULL,
                fecha_programada TEXT,
                observaciones TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(tipo_viaje, posicion)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS destino_referencias(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona TEXT NOT NULL,
                destino TEXT NOT NULL,
                km_aprox TEXT,
                horas_aprox TEXT,
                salida_habitual TEXT,
                llegada_habitual TEXT,
                tipo_carga TEXT,
                jornada_extendida INTEGER NOT NULL DEFAULT 0,
                observaciones TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                UNIQUE(zona, destino)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_asig_fecha ON asignaciones_rotacion(fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_asig_chofer_fecha ON asignaciones_rotacion(chofer_id, fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_asig_zona_destino_fecha ON asignaciones_rotacion(zona, destino, fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_exc_chofer_activo ON exclusiones_chofer(chofer_id, activo, fecha_desde, fecha_hasta)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_planilla_fecha_hora ON planilla_diaria(fecha, hora_salida)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_planilla_chofer_fecha ON planilla_diaria(chofer_id, fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rot_simple_orden ON rotacion_simple_viajes(orden)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rv_tipo_pos ON rotacion_visual_items(tipo_viaje, posicion)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ref_zona_destino ON destino_referencias(zona, destino)")
        con.execute(
            """
            INSERT OR IGNORE INTO configuracion_rotacion(id, periodo_default, criterio_empate, observaciones)
            VALUES (1, 60, 'puntos|pesado_antiguo|menos_viajes|orden', '')
            """
        )
        for nombre, orden in CHOFERES_SEED:
            con.execute(
                """
                INSERT INTO choferes_rotacion(nombre, activo, orden_rotacion)
                SELECT ?, 1, ?
                WHERE NOT EXISTS(
                    SELECT 1 FROM choferes_rotacion WHERE LOWER(COALESCE(nombre,'')) = LOWER(?)
                )
                """,
                (nombre, orden, nombre),
            )
        for zona, destino, carga, puntaje in DESTINOS_SEED:
            con.execute(
                """
                INSERT INTO destinos_rotacion(zona, destino, tipo_carga, puntaje, activo)
                SELECT ?, ?, ?, ?, 1
                WHERE NOT EXISTS(
                    SELECT 1 FROM destinos_rotacion
                    WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
                      AND LOWER(COALESCE(destino,'')) = LOWER(?)
                )
                """,
                (zona, destino, carga, puntaje, zona, destino),
            )
        for zona, destino, km, horas, salida, llegada, carga, jornada, obs in DESTINOS_REFERENCIA_SEED:
            con.execute(
                """
                INSERT INTO destino_referencias(
                    zona, destino, km_aprox, horas_aprox, salida_habitual, llegada_habitual,
                    tipo_carga, jornada_extendida, observaciones, activo
                )
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, 1
                WHERE NOT EXISTS(
                    SELECT 1 FROM destino_referencias
                    WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
                      AND LOWER(COALESCE(destino,'')) = LOWER(?)
                )
                """,
                (zona, destino, km, horas, salida, llegada, carga, int(jornada), obs, zona, destino),
            )
        for i, (viaje, estado, fecha, chofer_actual, chofer_proximo, obs) in enumerate(ROTACION_SIMPLE_SEED, start=1):
            ca = con.execute(
                "SELECT id FROM choferes_rotacion WHERE LOWER(COALESCE(nombre,'')) = LOWER(?) LIMIT 1",
                (chofer_actual,),
            ).fetchone()
            cp = con.execute(
                "SELECT id FROM choferes_rotacion WHERE LOWER(COALESCE(nombre,'')) = LOWER(?) LIMIT 1",
                (chofer_proximo,),
            ).fetchone()
            con.execute(
                """
                INSERT INTO rotacion_simple_viajes(
                    orden, viaje_destino, estado, fecha, chofer_actual_id, proximo_chofer_id, observacion, actualizado_en
                )
                SELECT ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS(
                    SELECT 1 FROM rotacion_simple_viajes WHERE LOWER(COALESCE(viaje_destino,'')) = LOWER(?)
                )
                """,
                (
                    i,
                    viaje,
                    estado,
                    fecha,
                    int(ca["id"] if ca else 0) or None,
                    int(cp["id"] if cp else 0) or None,
                    obs,
                    _now_ts(),
                    viaje,
                ),
            )
        con.commit()

    def _fetch_config(con):
        row = con.execute(
            """
            SELECT
                COALESCE(periodo_default,60) AS periodo_default,
                COALESCE(criterio_empate,'') AS criterio_empate,
                COALESCE(observaciones,'') AS observaciones
            FROM configuracion_rotacion
            WHERE id=1
            """
        ).fetchone()
        if not row:
            return {"periodo_default": 60, "criterio_empate": "", "observaciones": ""}
        return {
            "periodo_default": _period_or_default(row["periodo_default"], 60),
            "criterio_empate": (row["criterio_empate"] or "").strip(),
            "observaciones": (row["observaciones"] or "").strip(),
        }

    def _list_choferes(con, include_inactive=False):
        where = "" if include_inactive else "WHERE COALESCE(activo,1)=1"
        return con.execute(
            f"""
            SELECT
                id,
                COALESCE(nombre,'') AS nombre,
                COALESCE(activo,1) AS activo,
                COALESCE(orden_rotacion,999) AS orden_rotacion,
                COALESCE(observaciones,'') AS observaciones
            FROM choferes_rotacion
            {where}
            ORDER BY COALESCE(orden_rotacion,999), LOWER(COALESCE(nombre,''))
            """
        ).fetchall()

    def _list_destinos(con, include_inactive=False):
        where = "" if include_inactive else "WHERE COALESCE(activo,1)=1"
        return con.execute(
            f"""
            SELECT
                id,
                COALESCE(zona,'') AS zona,
                COALESCE(destino,'') AS destino,
                COALESCE(tipo_carga,'') AS tipo_carga,
                COALESCE(puntaje,0) AS puntaje,
                COALESCE(activo,1) AS activo,
                COALESCE(observaciones,'') AS observaciones
            FROM destinos_rotacion
            {where}
            ORDER BY LOWER(COALESCE(zona,'')), LOWER(COALESCE(destino,''))
            """
        ).fetchall()

    def _destino_info(con, zona, destino):
        return con.execute(
            """
            SELECT
                COALESCE(tipo_carga,'') AS tipo_carga,
                COALESCE(puntaje,0) AS puntaje
            FROM destinos_rotacion
            WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
              AND LOWER(COALESCE(destino,'')) = LOWER(?)
            LIMIT 1
            """,
            ((zona or "").strip(), (destino or "").strip()),
        ).fetchone()

    def _is_chofer_excluded(con, chofer_id, ref_iso=None):
        ref = _parse_iso(ref_iso) or date.today()
        row = con.execute(
            """
            SELECT
                1
            FROM exclusiones_chofer
            WHERE chofer_id = ?
              AND COALESCE(activo,1)=1
              AND date(fecha_desde) <= date(?)
              AND date(fecha_hasta) >= date(?)
            LIMIT 1
            """,
            (int(chofer_id), ref.isoformat(), ref.isoformat()),
        ).fetchone()
        return bool(row)

    def calcular_puntaje_chofer(con, chofer_id, periodo, ref_iso=None):
        since_iso, until_iso = _period_range(periodo, ref_iso)
        row = con.execute(
            """
            SELECT
                COALESCE(SUM(COALESCE(puntaje,0)),0) AS puntos
            FROM asignaciones_rotacion
            WHERE chofer_id = ?
              AND date(fecha) BETWEEN date(?) AND date(?)
              AND COALESCE(afecta_rotacion,1)=1
              AND LOWER(COALESCE(estado,'')) NOT IN ('cancelado','no afecta rotacion')
            """,
            (int(chofer_id), since_iso, until_iso),
        ).fetchone()
        return int(row["puntos"] or 0) if row else 0

    def _chofer_metric(con, chofer_row, periodo, ref_iso=None):
        chofer_id = int(chofer_row["id"])
        since_iso, until_iso = _period_range(periodo, ref_iso)
        agg = con.execute(
            """
            SELECT
                COUNT(*) AS viajes,
                COALESCE(SUM(COALESCE(puntaje,0)),0) AS puntos,
                SUM(CASE WHEN LOWER(COALESCE(tipo_carga,''))='cercano' THEN 1 ELSE 0 END) AS cercanos,
                SUM(CASE WHEN LOWER(COALESCE(tipo_carga,''))='medio' THEN 1 ELSE 0 END) AS medios,
                SUM(CASE WHEN LOWER(COALESCE(tipo_carga,''))='largo' THEN 1 ELSE 0 END) AS largos,
                SUM(CASE WHEN LOWER(COALESCE(tipo_carga,'')) IN ('pesado','pesado / jornada extendida') THEN 1 ELSE 0 END) AS pesados
            FROM asignaciones_rotacion
            WHERE chofer_id = ?
              AND date(fecha) BETWEEN date(?) AND date(?)
              AND COALESCE(afecta_rotacion,1)=1
              AND LOWER(COALESCE(estado,'')) NOT IN ('cancelado','no afecta rotacion')
            """,
            (chofer_id, since_iso, until_iso),
        ).fetchone()
        last_any = con.execute(
            """
            SELECT
                COALESCE(fecha,'') AS fecha,
                COALESCE(destino,'') AS destino
            FROM asignaciones_rotacion
            WHERE chofer_id = ?
            ORDER BY date(fecha) DESC, id DESC
            LIMIT 1
            """,
            (chofer_id,),
        ).fetchone()
        last_heavy = con.execute(
            """
            SELECT
                COALESCE(fecha,'') AS fecha
            FROM asignaciones_rotacion
            WHERE chofer_id = ?
              AND COALESCE(afecta_rotacion,1)=1
              AND LOWER(COALESCE(estado,'')) NOT IN ('cancelado','no afecta rotacion')
              AND (
                COALESCE(puntaje,0) >= 4
                OR LOWER(COALESCE(tipo_carga,'')) IN ('pesado', 'pesado / jornada extendida')
              )
            ORDER BY date(fecha) DESC, id DESC
            LIMIT 1
            """,
            (chofer_id,),
        ).fetchone()
        excluded = _is_chofer_excluded(con, chofer_id, ref_iso)
        return {
            "chofer_id": chofer_id,
            "chofer": (chofer_row["nombre"] or "").strip(),
            "orden_rotacion": int(chofer_row["orden_rotacion"] or 999),
            "viajes": int((agg["viajes"] if agg else 0) or 0),
            "puntos": int((agg["puntos"] if agg else 0) or 0),
            "cercanos": int((agg["cercanos"] if agg else 0) or 0),
            "medios": int((agg["medios"] if agg else 0) or 0),
            "largos": int((agg["largos"] if agg else 0) or 0),
            "pesados": int((agg["pesados"] if agg else 0) or 0),
            "ultimo_viaje": (last_any["fecha"] or "") if last_any else "",
            "ultimo_destino": (last_any["destino"] or "") if last_any else "",
            "ultimo_pesado": (last_heavy["fecha"] or "") if last_heavy else "",
            "estado_disponibilidad": ("No disponible" if excluded else "Disponible"),
            "excluido": excluded,
        }

    def calcular_resumen_rotacion(con, periodo, ref_iso=None):
        rows = []
        for ch in _list_choferes(con, include_inactive=False):
            rows.append(_chofer_metric(con, ch, periodo, ref_iso))
        order = sugerir_proximo_chofer(con, "", "", periodo, ref_iso).get("orden_sugerido", [])
        by_id_rank = {int(r["chofer_id"]): i + 1 for i, r in enumerate(order)}
        for row in rows:
            row["proximo_orden_sugerido"] = by_id_rank.get(int(row["chofer_id"]), 999)
        rows.sort(key=lambda r: (r["proximo_orden_sugerido"], r["chofer"]))
        return rows

    def obtener_ultimo_viaje_por_zona(con, zona):
        return con.execute(
            """
            SELECT
                COALESCE(a.fecha,'') AS fecha,
                COALESCE(c.nombre,'') AS chofer,
                COALESCE(a.tipo_carga,'') AS tipo_carga,
                COALESCE(a.puntaje,0) AS puntaje,
                COALESCE(a.estado,'') AS estado,
                COALESCE(a.observaciones,'') AS observaciones
            FROM asignaciones_rotacion a
            LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
            WHERE LOWER(COALESCE(a.zona,'')) = LOWER(?)
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 1
            """,
            ((zona or "").strip(),),
        ).fetchone()

    def obtener_ultimo_viaje_por_destino(con, destino):
        return con.execute(
            """
            SELECT
                COALESCE(a.fecha,'') AS fecha,
                COALESCE(c.nombre,'') AS chofer,
                COALESCE(a.tipo_carga,'') AS tipo_carga,
                COALESCE(a.puntaje,0) AS puntaje,
                COALESCE(a.estado,'') AS estado,
                COALESCE(a.observaciones,'') AS observaciones
            FROM asignaciones_rotacion a
            LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
            WHERE LOWER(COALESCE(a.destino,'')) = LOWER(?)
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 1
            """,
            ((destino or "").strip(),),
        ).fetchone()

    def sugerir_proximo_chofer(con, destino, zona, periodo=60, ref_iso=None, carga_hint=None):
        choferes = _list_choferes(con, include_inactive=False)
        metrics = [_chofer_metric(con, ch, periodo, ref_iso) for ch in choferes]
        metrics = [m for m in metrics if not m["excluido"]]
        if not metrics:
            return {
                "sugerido_id": None,
                "sugerido": "",
                "orden_sugerido": [],
                "tipo_carga": carga_hint or "",
                "puntaje": _puntaje_by_carga(carga_hint),
            }

        info = _destino_info(con, zona, destino)
        tipo_carga = (carga_hint or (info["tipo_carga"] if info else "") or "").strip()
        puntaje = int((info["puntaje"] if info else 0) or 0)
        if not puntaje:
            puntaje = _puntaje_by_carga(tipo_carga)

        def sort_key(m):
            last_heavy = _parse_iso(m["ultimo_pesado"]) or date(1900, 1, 1)
            return (
                int(m["puntos"]),
                last_heavy,
                int(m["viajes"]),
                int(m["orden_rotacion"]),
                _norm(m["chofer"]),
            )

        ordered = sorted(metrics, key=sort_key)
        if _norm(tipo_carga) in {"pesado", "pesado / jornada extendida"} and len(ordered) > 1:
            last_heavy_dest = con.execute(
                """
                SELECT COALESCE(chofer_id,0) AS chofer_id
                FROM asignaciones_rotacion
                WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
                  AND LOWER(COALESCE(destino,'')) = LOWER(?)
                  AND COALESCE(afecta_rotacion,1)=1
                  AND (
                    COALESCE(puntaje,0) >= 4
                    OR LOWER(COALESCE(tipo_carga,'')) IN ('pesado', 'pesado / jornada extendida')
                  )
                ORDER BY date(fecha) DESC, id DESC
                LIMIT 1
                """,
                ((zona or "").strip(), (destino or "").strip()),
            ).fetchone()
            last_heavy_chofer_id = int((last_heavy_dest["chofer_id"] if last_heavy_dest else 0) or 0)
            if last_heavy_chofer_id and int(ordered[0]["chofer_id"]) == last_heavy_chofer_id:
                ordered = ordered[1:] + ordered[:1]

        top = ordered[0]
        return {
            "sugerido_id": int(top["chofer_id"]),
            "sugerido": top["chofer"],
            "orden_sugerido": ordered,
            "tipo_carga": tipo_carga,
            "puntaje": int(puntaje or 0),
        }

    def verificar_alertas_asignacion(con, chofer_id, destino, zona, tipo_carga, puntaje, periodo, observaciones):
        alerts = []
        if not (tipo_carga or "").strip():
            alerts.append("Falta cargar tipo de carga.")
        if int(chofer_id or 0) <= 0:
            alerts.append("Falta chofer asignado.")
            return alerts

        ch_id = int(chofer_id)
        tipo_norm = _norm(tipo_carga)
        if tipo_norm in {"pesado", "pesado / jornada extendida"}:
            last_heavy = con.execute(
                """
                SELECT COALESCE(chofer_id,0) AS chofer_id
                FROM asignaciones_rotacion
                WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
                  AND LOWER(COALESCE(destino,'')) = LOWER(?)
                  AND COALESCE(afecta_rotacion,1)=1
                  AND (
                    COALESCE(puntaje,0) >= 4
                    OR LOWER(COALESCE(tipo_carga,'')) IN ('pesado', 'pesado / jornada extendida')
                  )
                ORDER BY date(fecha) DESC, id DESC
                LIMIT 1
                """,
                ((zona or "").strip(), (destino or "").strip()),
            ).fetchone()
            if last_heavy and int(last_heavy["chofer_id"] or 0) == ch_id:
                alerts.append("Se esta repitiendo el mismo chofer del ultimo viaje pesado en esa ruta.")

        resumen = calcular_resumen_rotacion(con, periodo)
        if resumen:
            puntos_vals = [int(r["puntos"]) for r in resumen]
            avg = sum(puntos_vals) / float(len(puntos_vals) or 1)
            target = next((r for r in resumen if int(r["chofer_id"]) == ch_id), None)
            if target and int(target["puntos"]) > (avg + 3):
                alerts.append("El chofer asignado ya tiene carga alta respecto al promedio.")
            if target and (int(puntaje or 0) >= 4) and int(target["puntos"]) == max(puntos_vals) and not (observaciones or "").strip():
                alerts.append("Viaje pesado al chofer con mayor puntaje acumulado sin observacion justificativa.")

            for r in resumen:
                if not (r["ultimo_viaje"] or "").strip():
                    alerts.append(f"Chofer sin viajes recientes: {r['chofer']}.")
                    break

        return alerts

    def _build_indicators(con, periodo, ref_iso=None):
        since_iso, until_iso = _period_range(periodo, ref_iso)
        total_viajes = con.execute(
            """
            SELECT COUNT(*) AS n
            FROM asignaciones_rotacion
            WHERE date(fecha) BETWEEN date(?) AND date(?)
            """,
            (since_iso, until_iso),
        ).fetchone()
        pesados_mes = con.execute(
            """
            SELECT COUNT(*) AS n
            FROM asignaciones_rotacion
            WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', ?)
              AND (
                COALESCE(puntaje,0) >= 4
                OR LOWER(COALESCE(tipo_carga,'')) IN ('pesado', 'pesado / jornada extendida')
              )
              AND LOWER(COALESCE(estado,'')) NOT IN ('cancelado','no afecta rotacion')
            """,
            (until_iso,),
        ).fetchone()
        resumen = calcular_resumen_rotacion(con, periodo, ref_iso)
        mayor = resumen[0]["chofer"] if resumen else "-"
        menor = resumen[0]["chofer"] if resumen else "-"
        if resumen:
            ordered_points = sorted(resumen, key=lambda x: (-int(x["puntos"]), x["chofer"]))
            mayor = ordered_points[0]["chofer"]
            ordered_low = sorted(resumen, key=lambda x: (int(x["puntos"]), x["chofer"]))
            menor = ordered_low[0]["chofer"]

        sug_pesado = sugerir_proximo_chofer(con, "Susques", "Itinerancia", periodo, ref_iso, "Pesado / jornada extendida")
        ult_it = obtener_ultimo_viaje_por_zona(con, "Itinerancia")
        ult_ra = obtener_ultimo_viaje_por_zona(con, "Ramal")
        ult_no = obtener_ultimo_viaje_por_zona(con, "Norte")
        return {
            "total_viajes": int((total_viajes["n"] if total_viajes else 0) or 0),
            "viajes_pesados_mes": int((pesados_mes["n"] if pesados_mes else 0) or 0),
            "chofer_mayor_carga": mayor,
            "chofer_menor_carga": menor,
            "proximo_pesado": (sug_pesado.get("sugerido") or "-"),
            "ultima_itinerancia": (ult_it["fecha"] if ult_it else "-"),
            "ultimo_ramal": (ult_ra["fecha"] if ult_ra else "-"),
            "ultimo_norte": (ult_no["fecha"] if ult_no else "-"),
        }

    def _build_resumen_destinos(con, periodo, ref_iso=None):
        out = []
        for d in _list_destinos(con, include_inactive=False):
            zona = (d["zona"] or "").strip()
            destino = (d["destino"] or "").strip()
            last = con.execute(
                """
                SELECT
                    COALESCE(a.fecha,'') AS fecha,
                    COALESCE(c.nombre,'') AS chofer,
                    COALESCE(a.tipo_carga,'') AS tipo_carga,
                    COALESCE(a.puntaje,0) AS puntaje,
                    COALESCE(a.estado,'') AS estado,
                    COALESCE(a.observaciones,'') AS observaciones
                FROM asignaciones_rotacion a
                LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
                WHERE LOWER(COALESCE(a.zona,'')) = LOWER(?)
                  AND LOWER(COALESCE(a.destino,'')) = LOWER(?)
                ORDER BY date(a.fecha) DESC, a.id DESC
                LIMIT 1
                """,
                (zona, destino),
            ).fetchone()
            sug = sugerir_proximo_chofer(con, destino, zona, periodo, ref_iso, d["tipo_carga"])
            out.append(
                {
                    "zona": zona,
                    "destino": destino,
                    "ultima_fecha": (last["fecha"] if last else ""),
                    "ultimo_chofer": (last["chofer"] if last else ""),
                    "tipo_carga": (last["tipo_carga"] if last and last["tipo_carga"] else d["tipo_carga"]),
                    "puntaje": int((last["puntaje"] if last and last["puntaje"] else d["puntaje"]) or 0),
                    "proximo_sugerido": (sug.get("sugerido") or "-"),
                    "estado": (last["estado"] if last else "Programar"),
                    "observaciones": (last["observaciones"] if last else ""),
                }
            )
        out.sort(key=lambda r: (r["zona"].lower(), r["destino"].lower()))
        return out

    def _chofer_color_hex(nombre):
        return CHOFER_COLOR_SEED.get(_norm(nombre), "#64748b")

    def _rotacion_tipo_from_request():
        raw = (request.args.get("rv_tipo") or request.form.get("rv_tipo") or "").strip()
        for t in ROTACION_TIPOS:
            if _norm(raw) == _norm(t):
                return t
        return ROTACION_TIPOS[0]

    def _normalize_rotacion_visual(con, tipo_viaje):
        rows = con.execute(
            """
            SELECT id
            FROM rotacion_visual_items
            WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
            ORDER BY COALESCE(posicion,9999), id
            """,
            ((tipo_viaje or "").strip(),),
        ).fetchall()
        for i, r in enumerate(rows, start=1):
            con.execute("UPDATE rotacion_visual_items SET posicion=? WHERE id=?", (i, int(r["id"])))
        con.commit()

    def _ensure_rotacion_visual_base(con, tipo_viaje):
        tipo = (tipo_viaje or "").strip() or ROTACION_TIPOS[0]
        activos = _list_choferes(con, include_inactive=False)
        rows = con.execute(
            """
            SELECT id, chofer_id, posicion
            FROM rotacion_visual_items
            WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
            ORDER BY COALESCE(posicion,9999), id
            """,
            (tipo,),
        ).fetchall()
        existentes = {int(r["chofer_id"] or 0) for r in rows}
        next_pos = (max([int(r["posicion"] or 0) for r in rows]) + 1) if rows else 1
        for ch in activos:
            cid = int(ch["id"] or 0)
            if cid <= 0 or cid in existentes:
                continue
            con.execute(
                """
                INSERT INTO rotacion_visual_items(tipo_viaje, posicion, chofer_id, fecha_programada, observaciones, activo, actualizado_en)
                VALUES (?,?,?,?,?,1,?)
                """,
                (tipo, next_pos, cid, "", "", _now_ts()),
            )
            next_pos += 1
        con.commit()
        _normalize_rotacion_visual(con, tipo)

    def _list_rotacion_visual(con, tipo_viaje, ref_iso=None):
        tipo = (tipo_viaje or "").strip() or ROTACION_TIPOS[0]
        _ensure_rotacion_visual_base(con, tipo)
        rows = con.execute(
            """
            SELECT
                r.id,
                COALESCE(r.tipo_viaje,'') AS tipo_viaje,
                COALESCE(r.posicion,9999) AS posicion,
                COALESCE(r.chofer_id,0) AS chofer_id,
                COALESCE(c.nombre,'') AS chofer,
                COALESCE(r.fecha_programada,'') AS fecha_programada,
                COALESCE(r.observaciones,'') AS observaciones,
                COALESCE(r.activo,1) AS activo
            FROM rotacion_visual_items r
            LEFT JOIN choferes_rotacion c ON c.id = r.chofer_id
            WHERE LOWER(COALESCE(r.tipo_viaje,'')) = LOWER(?)
            ORDER BY COALESCE(r.posicion,9999), r.id
            """,
            (tipo,),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["excluido"] = _is_chofer_excluded(con, int(item["chofer_id"] or 0), ref_iso)
            item["color"] = _chofer_color_hex(item["chofer"])
            out.append(item)
        return out

    def _reorder_rotacion_visual(con, tipo_viaje, ordered_ids):
        tipo = (tipo_viaje or "").strip() or ROTACION_TIPOS[0]
        existing_ids = [
            int(r["id"])
            for r in con.execute(
                """
                SELECT id
                FROM rotacion_visual_items
                WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
                ORDER BY COALESCE(posicion,9999), id
                """,
                (tipo,),
            ).fetchall()
        ]
        if not existing_ids:
            return
        unique_given = []
        seen = set()
        for rid in ordered_ids or []:
            ir = _to_int(rid, 0)
            if ir > 0 and ir in existing_ids and ir not in seen:
                seen.add(ir)
                unique_given.append(ir)
        final_order = unique_given + [rid for rid in existing_ids if rid not in seen]
        for i, rid in enumerate(final_order, start=1):
            con.execute(
                """
                UPDATE rotacion_visual_items
                SET posicion=?, actualizado_en=?
                WHERE id=?
                """,
                (i, _now_ts(), int(rid)),
            )
        con.commit()

    def _move_rotacion_visual(con, row_id, tipo_viaje, direction):
        tipo = (tipo_viaje or "").strip() or ROTACION_TIPOS[0]
        row = con.execute(
            """
            SELECT id, posicion
            FROM rotacion_visual_items
            WHERE id=?
              AND LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
            LIMIT 1
            """,
            (int(row_id), tipo),
        ).fetchone()
        if not row:
            return False
        pos = int(row["posicion"] or 0)
        if direction == "up":
            target = con.execute(
                """
                SELECT id, posicion
                FROM rotacion_visual_items
                WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
                  AND COALESCE(posicion,9999) < ?
                ORDER BY COALESCE(posicion,9999) DESC, id DESC
                LIMIT 1
                """,
                (tipo, pos),
            ).fetchone()
        else:
            target = con.execute(
                """
                SELECT id, posicion
                FROM rotacion_visual_items
                WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
                  AND COALESCE(posicion,9999) > ?
                ORDER BY COALESCE(posicion,9999) ASC, id ASC
                LIMIT 1
                """,
                (tipo, pos),
            ).fetchone()
        if not target:
            return False
        con.execute("UPDATE rotacion_visual_items SET posicion=?, actualizado_en=? WHERE id=?", (int(target["posicion"]), _now_ts(), int(row["id"])))
        con.execute("UPDATE rotacion_visual_items SET posicion=?, actualizado_en=? WHERE id=?", (pos, _now_ts(), int(target["id"])))
        con.commit()
        _normalize_rotacion_visual(con, tipo)
        return True

    def _update_rotacion_visual_row(con, row_id, tipo_viaje, payload):
        tipo = (tipo_viaje or "").strip() or ROTACION_TIPOS[0]
        rid = int(row_id or 0)
        if rid <= 0:
            return False
        target_chofer_id = int(payload.get("chofer_id") or 0)
        if target_chofer_id <= 0:
            return False
        curr = con.execute(
            """
            SELECT COALESCE(chofer_id,0) AS chofer_id
            FROM rotacion_visual_items
            WHERE id=?
              AND LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
            LIMIT 1
            """,
            (rid, tipo),
        ).fetchone()
        if not curr:
            return False
        curr_chofer_id = int(curr["chofer_id"] or 0)
        other = con.execute(
            """
            SELECT id
            FROM rotacion_visual_items
            WHERE LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
              AND COALESCE(chofer_id,0) = ?
              AND id <> ?
            LIMIT 1
            """,
            (tipo, target_chofer_id, rid),
        ).fetchone()
        if other and curr_chofer_id > 0:
            con.execute(
                """
                UPDATE rotacion_visual_items
                SET chofer_id=?, actualizado_en=?
                WHERE id=?
                """,
                (curr_chofer_id, _now_ts(), int(other["id"])),
            )
        con.execute(
            """
            UPDATE rotacion_visual_items
            SET chofer_id=?,
                fecha_programada=?,
                observaciones=?,
                activo=?,
                actualizado_en=?
            WHERE id=?
              AND LOWER(COALESCE(tipo_viaje,'')) = LOWER(?)
            """,
            (
                target_chofer_id,
                (payload.get("fecha_programada") or "").strip(),
                (payload.get("observaciones") or "").strip(),
                int(payload.get("activo") or 0),
                _now_ts(),
                rid,
                tipo,
            ),
        )
        con.commit()
        return True

    def _list_destinos_por_zona(con, zona):
        z = (zona or "").strip()
        rows = con.execute(
            """
            SELECT
                COALESCE(destino,'') AS destino,
                COALESCE(tipo_carga,'') AS tipo_carga
            FROM destinos_rotacion
            WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
              AND COALESCE(activo,1)=1
            ORDER BY LOWER(COALESCE(destino,''))
            """,
            (z,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_destino_referencia(con, zona, destino):
        z = (zona or "").strip()
        d = (destino or "").strip()
        if not z or not d:
            return None
        row = con.execute(
            """
            SELECT
                COALESCE(zona,'') AS zona,
                COALESCE(destino,'') AS destino,
                COALESCE(km_aprox,'') AS km_aprox,
                COALESCE(horas_aprox,'') AS horas_aprox,
                COALESCE(salida_habitual,'') AS salida_habitual,
                COALESCE(llegada_habitual,'') AS llegada_habitual,
                COALESCE(tipo_carga,'') AS tipo_carga,
                COALESCE(jornada_extendida,0) AS jornada_extendida,
                COALESCE(observaciones,'') AS observaciones
            FROM destino_referencias
            WHERE LOWER(COALESCE(zona,'')) = LOWER(?)
              AND LOWER(COALESCE(destino,'')) = LOWER(?)
            LIMIT 1
            """,
            (z, d),
        ).fetchone()
        if row:
            return dict(row)
        info = _destino_info(con, z, d)
        return {
            "zona": z,
            "destino": d,
            "km_aprox": "",
            "horas_aprox": "",
            "salida_habitual": "",
            "llegada_habitual": "",
            "tipo_carga": (info["tipo_carga"] if info else ""),
            "jornada_extendida": 0,
            "observaciones": "",
        }

    def _save_destino_referencia(con, zona, destino, payload):
        z = (zona or "").strip()
        d = (destino or "").strip()
        if not z or not d:
            return False
        con.execute(
            """
            INSERT INTO destino_referencias(
                zona, destino, km_aprox, horas_aprox, salida_habitual, llegada_habitual,
                tipo_carga, jornada_extendida, observaciones, activo
            )
            VALUES (?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(zona, destino)
            DO UPDATE SET
                km_aprox=excluded.km_aprox,
                horas_aprox=excluded.horas_aprox,
                salida_habitual=excluded.salida_habitual,
                llegada_habitual=excluded.llegada_habitual,
                tipo_carga=excluded.tipo_carga,
                jornada_extendida=excluded.jornada_extendida,
                observaciones=excluded.observaciones,
                activo=1
            """,
            (
                z,
                d,
                (payload.get("km_aprox") or "").strip(),
                (payload.get("horas_aprox") or "").strip(),
                (payload.get("salida_habitual") or "").strip(),
                (payload.get("llegada_habitual") or "").strip(),
                (payload.get("tipo_carga") or "").strip(),
                1 if _norm(payload.get("jornada_extendida") or "") in {"1", "si", "true", "on"} else 0,
                (payload.get("observaciones") or "").strip(),
            ),
        )
        con.commit()
        return True

    def _ultimo_viaje_tipo(con, tipo_viaje):
        tipo = (tipo_viaje or "").strip()
        real = con.execute(
            """
            SELECT
                COALESCE(a.fecha,'') AS fecha,
                COALESCE(c.nombre,'') AS chofer
            FROM asignaciones_rotacion a
            LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
            WHERE LOWER(COALESCE(a.zona,'')) = LOWER(?)
              AND LOWER(COALESCE(a.estado,'')) = 'realizado'
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 1
            """,
            (tipo,),
        ).fetchone()
        if real:
            return {"fecha": real["fecha"], "chofer": real["chofer"]}
        any_row = con.execute(
            """
            SELECT
                COALESCE(a.fecha,'') AS fecha,
                COALESCE(c.nombre,'') AS chofer
            FROM asignaciones_rotacion a
            LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
            WHERE LOWER(COALESCE(a.zona,'')) = LOWER(?)
              AND LOWER(COALESCE(a.estado,'')) <> 'cancelado'
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 1
            """,
            (tipo,),
        ).fetchone()
        if any_row:
            return {"fecha": any_row["fecha"], "chofer": any_row["chofer"]}
        return {"fecha": "", "chofer": ""}

    def _proximo_rotacion_tipo(rows):
        for r in rows or []:
            if int(r.get("activo") or 0) != 1:
                continue
            if bool(r.get("excluido")):
                continue
            return r
        return None

    def _build_indicadores_rotacion_visual(con, ref_iso=None):
        out = {}
        for t in ROTACION_TIPOS:
            rows_t = _list_rotacion_visual(con, t, ref_iso)
            last = _ultimo_viaje_tipo(con, t)
            nxt = _proximo_rotacion_tipo(rows_t)
            out[t] = {
                "ultimo_chofer": (last.get("chofer") or "-"),
                "ultimo_fecha": (last.get("fecha") or "-"),
                "proximo_chofer": ((nxt.get("chofer") if nxt else "") or "-"),
            }
        return out

    def listar_historial(con, filtros):
        where = ["1=1"]
        params = []
        if filtros.get("desde"):
            where.append("date(a.fecha) >= date(?)")
            params.append(filtros["desde"])
        if filtros.get("hasta"):
            where.append("date(a.fecha) <= date(?)")
            params.append(filtros["hasta"])
        if filtros.get("chofer_id"):
            where.append("a.chofer_id = ?")
            params.append(int(filtros["chofer_id"]))
        if filtros.get("zona"):
            where.append("LOWER(COALESCE(a.zona,'')) = LOWER(?)")
            params.append(filtros["zona"])
        if filtros.get("destino"):
            where.append("LOWER(COALESCE(a.destino,'')) = LOWER(?)")
            params.append(filtros["destino"])
        if filtros.get("tipo_carga"):
            where.append("LOWER(COALESCE(a.tipo_carga,'')) = LOWER(?)")
            params.append(filtros["tipo_carga"])
        if filtros.get("estado"):
            where.append("LOWER(COALESCE(a.estado,'')) = LOWER(?)")
            params.append(filtros["estado"])

        return con.execute(
            f"""
            SELECT
                a.id,
                COALESCE(a.fecha,'') AS fecha,
                COALESCE(a.zona,'') AS zona,
                COALESCE(a.destino,'') AS destino,
                COALESCE(a.tipo_viaje,'') AS tipo_viaje,
                COALESCE(a.tipo_carga,'') AS tipo_carga,
                COALESCE(a.puntaje,0) AS puntaje,
                COALESCE(c.nombre,'') AS chofer,
                COALESCE(a.vehiculo,'') AS vehiculo,
                COALESCE(a.afecta_rotacion,1) AS afecta_rotacion,
                COALESCE(a.estado,'') AS estado,
                COALESCE(a.motivo,'') AS motivo,
                COALESCE(a.observaciones,'') AS observaciones
            FROM asignaciones_rotacion a
            LEFT JOIN choferes_rotacion c ON c.id = a.chofer_id
            WHERE {' AND '.join(where)}
            ORDER BY date(a.fecha) DESC, a.id DESC
            LIMIT 1200
            """,
            tuple(params),
        ).fetchall()

    def _parse_hhmm(raw):
        txt = str(raw or "").strip()
        if not txt:
            return None
        try:
            t = datetime.strptime(txt, "%H:%M")
            return t.hour * 60 + t.minute
        except Exception:
            return None

    def _planilla_payload_from_form():
        fecha = (request.form.get("fecha") or "").strip() or _today_iso()
        hora_salida = (request.form.get("hora_salida") or "").strip()
        hora_regreso = (request.form.get("hora_regreso_estimada") or "").strip()
        chofer_id = _to_int(request.form.get("chofer_id"), 0)
        vehiculo = (request.form.get("vehiculo") or "").strip()
        solicitante = (request.form.get("solicitante") or "").strip()
        destino = (request.form.get("destino") or "").strip()
        tipo_asignacion = (request.form.get("tipo_asignacion") or "").strip()
        estado = (request.form.get("estado") or "Pendiente").strip()
        observaciones = (request.form.get("observaciones") or "").strip()

        errores = []
        if not _parse_iso(fecha):
            errores.append("Fecha invalida.")
        if hora_salida and _parse_hhmm(hora_salida) is None:
            errores.append("Hora salida invalida (usar HH:MM).")
        if hora_regreso and _parse_hhmm(hora_regreso) is None:
            errores.append("Hora regreso invalida (usar HH:MM).")
        if estado not in ESTADOS_PLANILLA:
            estado = "Pendiente"

        payload = {
            "fecha": fecha,
            "hora_salida": hora_salida,
            "hora_regreso_estimada": hora_regreso,
            "chofer_id": (chofer_id if chofer_id > 0 else None),
            "vehiculo": vehiculo,
            "solicitante": solicitante,
            "destino": destino,
            "tipo_asignacion": tipo_asignacion,
            "estado": estado,
            "observaciones": observaciones,
        }
        return payload, errores

    def _save_planilla_diaria(con, payload, row_id=0):
        now = _now_ts()
        if int(row_id or 0) > 0:
            con.execute(
                """
                UPDATE planilla_diaria
                SET fecha=?,
                    hora_salida=?,
                    hora_regreso_estimada=?,
                    chofer_id=?,
                    vehiculo=?,
                    solicitante=?,
                    destino=?,
                    tipo_asignacion=?,
                    estado=?,
                    observaciones=?,
                    actualizado_en=?
                WHERE id=?
                """,
                (
                    payload["fecha"],
                    payload["hora_salida"],
                    payload["hora_regreso_estimada"],
                    payload["chofer_id"],
                    payload["vehiculo"],
                    payload["solicitante"],
                    payload["destino"],
                    payload["tipo_asignacion"],
                    payload["estado"],
                    payload["observaciones"],
                    now,
                    int(row_id),
                ),
            )
            con.commit()
            return int(row_id)
        cur = con.execute(
            """
            INSERT INTO planilla_diaria(
                fecha, hora_salida, hora_regreso_estimada, chofer_id, vehiculo,
                solicitante, destino, tipo_asignacion, estado, observaciones, creado_en, actualizado_en
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload["fecha"],
                payload["hora_salida"],
                payload["hora_regreso_estimada"],
                payload["chofer_id"],
                payload["vehiculo"],
                payload["solicitante"],
                payload["destino"],
                payload["tipo_asignacion"],
                payload["estado"],
                payload["observaciones"],
                now,
                now,
            ),
        )
        con.commit()
        return int(cur.lastrowid or 0)

    def _planilla_filters_from_request():
        return {
            "fecha": (request.args.get("pd_fecha") or "").strip(),
            "chofer_id": _to_int(request.args.get("pd_chofer_id"), 0),
            "vehiculo": (request.args.get("pd_vehiculo") or "").strip(),
            "estado": (request.args.get("pd_estado") or "").strip(),
            "sort": (request.args.get("pd_sort") or "hora").strip().lower(),
        }

    def _list_planilla_diaria(con, filtros):
        where = ["1=1"]
        params = []
        if filtros.get("fecha"):
            where.append("date(p.fecha) = date(?)")
            params.append(filtros["fecha"])
        if filtros.get("chofer_id"):
            where.append("p.chofer_id = ?")
            params.append(int(filtros["chofer_id"]))
        if filtros.get("vehiculo"):
            where.append("LOWER(COALESCE(p.vehiculo,'')) LIKE LOWER(?)")
            params.append(f"%{filtros['vehiculo']}%")
        if filtros.get("estado"):
            where.append("LOWER(COALESCE(p.estado,'')) = LOWER(?)")
            params.append(filtros["estado"])

        sort = filtros.get("sort") or "hora"
        if sort == "chofer":
            order = "LOWER(COALESCE(c.nombre,'')) ASC, COALESCE(p.hora_salida,'') ASC, p.id DESC"
        elif sort == "vehiculo":
            order = "LOWER(COALESCE(p.vehiculo,'')) ASC, COALESCE(p.hora_salida,'') ASC, p.id DESC"
        else:
            order = "date(p.fecha) DESC, COALESCE(p.hora_salida,'') ASC, p.id DESC"

        return con.execute(
            f"""
            SELECT
                p.id,
                COALESCE(p.fecha,'') AS fecha,
                COALESCE(p.hora_salida,'') AS hora_salida,
                COALESCE(p.hora_regreso_estimada,'') AS hora_regreso_estimada,
                COALESCE(p.chofer_id,0) AS chofer_id,
                COALESCE(c.nombre,'') AS chofer,
                COALESCE(p.vehiculo,'') AS vehiculo,
                COALESCE(p.solicitante,'') AS solicitante,
                COALESCE(p.destino,'') AS destino,
                COALESCE(p.tipo_asignacion,'') AS tipo_asignacion,
                COALESCE(p.estado,'Pendiente') AS estado,
                COALESCE(p.observaciones,'') AS observaciones
            FROM planilla_diaria p
            LEFT JOIN choferes_rotacion c ON c.id = p.chofer_id
            WHERE {' AND '.join(where)}
            ORDER BY {order}
            LIMIT 1500
            """,
            tuple(params),
        ).fetchall()

    def _build_planilla_alerts(rows):
        per_row = {}
        global_alerts = []

        def _add_row_alert(rid, txt):
            per_row.setdefault(int(rid), []).append(txt)
            global_alerts.append(f"ID {rid}: {txt}")

        rows_list = list(rows or [])
        for r in rows_list:
            rid = int(r["id"] or 0)
            if int(r["chofer_id"] or 0) <= 0:
                _add_row_alert(rid, "Falta chofer.")
            if not (r["vehiculo"] or "").strip():
                _add_row_alert(rid, "Falta vehiculo.")
            if _parse_hhmm(r["hora_salida"]) is None or _parse_hhmm(r["hora_regreso_estimada"]) is None:
                _add_row_alert(rid, "Falta horario completo (salida/regreso).")

        for i in range(len(rows_list)):
            a = rows_list[i]
            a_date = (a["fecha"] or "").strip()
            a_start = _parse_hhmm(a["hora_salida"])
            a_end = _parse_hhmm(a["hora_regreso_estimada"])
            if a_start is None or a_end is None:
                continue
            if a_end <= a_start:
                a_end = a_start + 1
            for j in range(i + 1, len(rows_list)):
                b = rows_list[j]
                if a_date != (b["fecha"] or "").strip():
                    continue
                b_start = _parse_hhmm(b["hora_salida"])
                b_end = _parse_hhmm(b["hora_regreso_estimada"])
                if b_start is None or b_end is None:
                    continue
                if b_end <= b_start:
                    b_end = b_start + 1
                overlap = (a_start < b_end) and (b_start < a_end)
                if not overlap:
                    continue

                a_chofer = int(a["chofer_id"] or 0)
                b_chofer = int(b["chofer_id"] or 0)
                if a_chofer > 0 and a_chofer == b_chofer:
                    _add_row_alert(int(a["id"]), "Chofer superpuesto en horario.")
                    _add_row_alert(int(b["id"]), "Chofer superpuesto en horario.")

                av = _norm(a["vehiculo"])
                bv = _norm(b["vehiculo"])
                if av and bv and av == bv:
                    _add_row_alert(int(a["id"]), "Vehiculo superpuesto en horario.")
                    _add_row_alert(int(b["id"]), "Vehiculo superpuesto en horario.")

        uniq_global = []
        seen = set()
        for g in global_alerts:
            if g in seen:
                continue
            seen.add(g)
            uniq_global.append(g)
        return per_row, uniq_global

    def _list_rotacion_simple(con):
        return con.execute(
            """
            SELECT
                r.id,
                COALESCE(r.orden,999) AS orden,
                COALESCE(r.viaje_destino,'') AS viaje_destino,
                COALESCE(r.estado,'Programado') AS estado,
                COALESCE(r.fecha,'') AS fecha,
                COALESCE(r.chofer_actual_id,0) AS chofer_actual_id,
                COALESCE(ca.nombre,'') AS chofer_actual,
                COALESCE(r.proximo_chofer_id,0) AS proximo_chofer_id,
                COALESCE(cp.nombre,'') AS proximo_chofer,
                COALESCE(r.observacion,'') AS observacion
            FROM rotacion_simple_viajes r
            LEFT JOIN choferes_rotacion ca ON ca.id = r.chofer_actual_id
            LEFT JOIN choferes_rotacion cp ON cp.id = r.proximo_chofer_id
            ORDER BY COALESCE(r.orden,999), r.id
            """
        ).fetchall()

    def _save_rotacion_simple_row(con, row_id, payload):
        rid = int(row_id or 0)
        if rid <= 0:
            return False
        estado = (payload.get("estado") or "Programado").strip()
        if estado not in ESTADOS_ROT_SIMPLE:
            estado = "Programado"
        fecha = (payload.get("fecha") or "").strip()
        if fecha and not _parse_iso(fecha):
            fecha = ""
        con.execute(
            """
            UPDATE rotacion_simple_viajes
            SET estado=?,
                fecha=?,
                chofer_actual_id=?,
                proximo_chofer_id=?,
                observacion=?,
                actualizado_en=?
            WHERE id=?
            """,
            (
                estado,
                fecha,
                (_to_int(payload.get("chofer_actual_id"), 0) or None),
                (_to_int(payload.get("proximo_chofer_id"), 0) or None),
                (payload.get("observacion") or "").strip(),
                _now_ts(),
                rid,
            ),
        )
        con.commit()
        return True

    def _rotacion_last_row_id(rows):
        top_id = 0
        top_date = None
        for r in rows or []:
            d = _parse_iso(r["fecha"])
            if not d:
                continue
            if (top_date is None) or (d > top_date):
                top_date = d
                top_id = int(r["id"] or 0)
        return top_id

    def _update_chofer_orden_simple(con, chofer_id, orden_rotacion, activo, observaciones):
        cid = int(chofer_id or 0)
        if cid <= 0:
            return False
        con.execute(
            """
            UPDATE choferes_rotacion
            SET orden_rotacion=?,
                activo=?,
                observaciones=?
            WHERE id=?
            """,
            (
                int(orden_rotacion or 999),
                int(activo or 0),
                (observaciones or "").strip(),
                cid,
            ),
        )
        con.commit()
        return True

    def _build_planilla_copy_text(rows, fecha_iso=None):
        fecha_txt = _fmt_dmy(fecha_iso) if fecha_iso else ""
        lines = [
            "ASIGNACIONES DEL DIA",
            f"Fecha: {fecha_txt or '-'}",
            "",
            "Hora | Chofer | Vehiculo | Destino | Solicitante | Observacion",
        ]
        for r in rows or []:
            h = f"{(r['hora_salida'] or '-')} - {(r['hora_regreso_estimada'] or '-')}"
            lines.append(
                f"{h} | {(r['chofer'] or '-')} | {(r['vehiculo'] or '-')} | {(r['destino'] or '-')} | {(r['solicitante'] or '-')} | {(r['observaciones'] or '-')}"
            )
        return "\n".join(lines)

    def _assignment_payload_from_form(con):
        fecha = (request.form.get("fecha") or "").strip() or _today_iso()
        zona = (request.form.get("zona") or "").strip()
        destino = (request.form.get("destino") or "").strip()
        tipo_viaje = (request.form.get("tipo_viaje") or "").strip()
        tipo_carga = (request.form.get("tipo_carga") or "").strip()
        chofer_id = _to_int(request.form.get("chofer_id"), 0)
        vehiculo = (request.form.get("vehiculo") or "").strip()
        estado = (request.form.get("estado") or "Programado").strip()
        motivo = (request.form.get("motivo") or "").strip()
        observaciones = (request.form.get("observaciones") or "").strip()
        afecta_rotacion = 1 if _norm(request.form.get("afecta_rotacion") or "1") in {"1", "si", "true", "on"} else 0
        puntaje_form = _to_int(request.form.get("puntaje"), 0)

        info = _destino_info(con, zona, destino)
        if not tipo_carga and info:
            tipo_carga = (info["tipo_carga"] or "").strip()
        puntaje_auto = int((info["puntaje"] if info else 0) or 0)
        if not puntaje_auto:
            puntaje_auto = _puntaje_by_carga(tipo_carga)
        puntaje = int(puntaje_form or puntaje_auto or 0)

        errores = []
        if not _parse_iso(fecha):
            errores.append("Fecha invalida.")
        if not zona:
            errores.append("Zona obligatoria.")
        if not destino:
            errores.append("Destino obligatorio.")
        if chofer_id <= 0:
            errores.append("Chofer obligatorio.")
        if not tipo_carga:
            errores.append("Tipo de carga obligatorio.")
        if estado == "Salta turno" and not motivo:
            errores.append("Motivo obligatorio para estado 'Salta turno'.")
        if estado == "No afecta rotacion":
            afecta_rotacion = 0

        payload = {
            "fecha": fecha,
            "zona": zona,
            "destino": destino,
            "tipo_viaje": tipo_viaje,
            "tipo_carga": tipo_carga,
            "puntaje": puntaje,
            "chofer_id": chofer_id,
            "vehiculo": vehiculo,
            "afecta_rotacion": afecta_rotacion,
            "estado": estado,
            "motivo": motivo,
            "observaciones": observaciones,
        }
        return payload, errores

    def registrar_asignacion(con, payload, asignacion_id=0):
        now = _now_ts()
        if int(asignacion_id or 0) > 0:
            con.execute(
                """
                UPDATE asignaciones_rotacion
                SET fecha=?,
                    zona=?,
                    destino=?,
                    tipo_viaje=?,
                    tipo_carga=?,
                    puntaje=?,
                    chofer_id=?,
                    vehiculo=?,
                    afecta_rotacion=?,
                    estado=?,
                    motivo=?,
                    observaciones=?,
                    actualizado_en=?
                WHERE id=?
                """,
                (
                    payload["fecha"],
                    payload["zona"],
                    payload["destino"],
                    payload["tipo_viaje"],
                    payload["tipo_carga"],
                    int(payload["puntaje"]),
                    int(payload["chofer_id"]),
                    payload["vehiculo"],
                    int(payload["afecta_rotacion"]),
                    payload["estado"],
                    payload["motivo"],
                    payload["observaciones"],
                    now,
                    int(asignacion_id),
                ),
            )
            con.commit()
            return int(asignacion_id)

        cur = con.execute(
            """
            INSERT INTO asignaciones_rotacion(
                fecha, zona, destino, tipo_viaje, tipo_carga, puntaje, chofer_id,
                vehiculo, afecta_rotacion, estado, motivo, observaciones, creado_en, actualizado_en
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload["fecha"],
                payload["zona"],
                payload["destino"],
                payload["tipo_viaje"],
                payload["tipo_carga"],
                int(payload["puntaje"]),
                int(payload["chofer_id"]),
                payload["vehiculo"],
                int(payload["afecta_rotacion"]),
                payload["estado"],
                payload["motivo"],
                payload["observaciones"],
                now,
                now,
            ),
        )
        con.commit()
        return int(cur.lastrowid or 0)

    def registrar_salto_turno(con, payload):
        payload = dict(payload or {})
        payload["estado"] = "Salta turno"
        payload["afecta_rotacion"] = 0
        return registrar_asignacion(con, payload, 0)

    def _render(view, con, extra=None):
        extra = extra or {}
        ref_iso = (request.args.get("fecha_ref") or "").strip() or _today_iso()
        choferes = _list_choferes(con, include_inactive=True)
        choferes_orden = sorted(choferes, key=lambda c: (int(c["orden_rotacion"] or 999), _norm(c["nombre"])))

        rot_simple_rows = _list_rotacion_simple(con)
        rot_last_row_id = _rotacion_last_row_id(rot_simple_rows)

        filtros_planilla = _planilla_filters_from_request()
        filtros_planilla["chofer_id"] = _to_int(filtros_planilla.get("chofer_id"), 0)
        filtros_planilla["vehiculo"] = ""
        filtros_planilla["estado"] = ""
        filtros_planilla["sort"] = "hora"
        if not filtros_planilla.get("fecha"):
            filtros_planilla["fecha"] = ref_iso
        planilla_rows = _list_planilla_diaria(con, filtros_planilla)
        planilla_copy_text = _build_planilla_copy_text(planilla_rows, filtros_planilla.get("fecha"))

        return render_template(
            "asignaciones_home.html",
            view=view,
            ref_iso=ref_iso,
            choferes=choferes,
            choferes_orden=choferes_orden,
            rot_simple_rows=rot_simple_rows,
            rot_last_row_id=rot_last_row_id,
            planilla_rows=planilla_rows,
            filtros_planilla=filtros_planilla,
            planilla_copy_text=planilla_copy_text,
            estados_rot_simple=ESTADOS_ROT_SIMPLE,
            estados_planilla=ESTADOS_PLANILLA,
            extra=extra,
            fmt_dmy=_fmt_dmy,
        )

    @app.route("/asignaciones", methods=["GET", "POST"], endpoint="asignaciones_home")
    def asignaciones_home():
        if not _can_access():
            return _deny()
        con = get_db()
        _ensure_schema(con)
        try:
            if request.method == "POST":
                action = _norm(request.form.get("action"))
                if action == "save_viaje":
                    row_id = _to_int(request.form.get("row_id"), 0)
                    payload = {
                        "estado": (request.form.get("estado") or "Programado").strip(),
                        "fecha": (request.form.get("fecha") or "").strip(),
                        "chofer_actual_id": _to_int(request.form.get("chofer_actual_id"), 0),
                        "proximo_chofer_id": _to_int(request.form.get("proximo_chofer_id"), 0),
                        "observacion": (request.form.get("observacion") or "").strip(),
                    }
                    if row_id <= 0:
                        flash("Fila de rotacion invalida.", "warning")
                    else:
                        _save_rotacion_simple_row(con, row_id, payload)
                        flash("Rotacion actualizada.", "success")
                elif action == "save_chofer_orden":
                    chofer_id = _to_int(request.form.get("chofer_id"), 0)
                    orden = _to_int(request.form.get("orden_rotacion"), 999)
                    activo = 1 if _norm(request.form.get("activo") or "") in {"1", "si", "true", "on"} else 0
                    obs = (request.form.get("observaciones") or "").strip()
                    if chofer_id <= 0:
                        flash("Chofer invalido.", "warning")
                    else:
                        _update_chofer_orden_simple(con, chofer_id, orden, activo, obs)
                        flash("Orden de chofer actualizado.", "success")
                return redirect(url_for("asignaciones_home"))
            return _render("rotacion", con, {})
        finally:
            con.close()

    @app.route("/asignaciones/nueva", methods=["GET", "POST"], endpoint="asignaciones_nueva")
    def asignaciones_nueva():
        if not _can_access():
            return _deny()
        flash("Vista oculta. Usa Rotacion o Planilla diaria.", "info")
        return redirect(url_for("asignaciones_home"))
        con = get_db()
        _ensure_schema(con)
        try:
            form_data = {
                "fecha": _today_iso(),
                "zona": "",
                "destino": "",
                "tipo_viaje": "",
                "tipo_carga": "",
                "puntaje": 0,
                "chofer_id": 0,
                "vehiculo": "",
                "afecta_rotacion": 1,
                "estado": "Programado",
                "motivo": "",
                "observaciones": "",
            }
            if request.method == "POST":
                payload, errores = _assignment_payload_from_form(con)
                form_data.update(payload)
                if errores:
                    for e in errores:
                        flash(e, "warning")
                else:
                    if payload["estado"] == "Salta turno":
                        aid = registrar_salto_turno(con, payload)
                    else:
                        aid = registrar_asignacion(con, payload, 0)
                    periodo = _period_or_default(request.args.get("periodo"), _fetch_config(con)["periodo_default"])
                    alerts = verificar_alertas_asignacion(
                        con,
                        payload["chofer_id"],
                        payload["destino"],
                        payload["zona"],
                        payload["tipo_carga"],
                        payload["puntaje"],
                        periodo,
                        payload["observaciones"],
                    )
                    for a in alerts:
                        flash(a, "warning")
                    flash(f"Asignacion registrada (ID {aid}).", "success")
                    return redirect(url_for("asignaciones_nueva"))

            return _render("nueva", con, {"form_data": form_data})
        finally:
            con.close()

    @app.route("/asignaciones/editar/<int:asig_id>", methods=["GET", "POST"], endpoint="asignaciones_editar")
    def asignaciones_editar(asig_id):
        if not _can_access():
            return _deny()
        con = get_db()
        _ensure_schema(con)
        try:
            row = con.execute(
                """
                SELECT
                    id, fecha, zona, destino, tipo_viaje, tipo_carga, puntaje, chofer_id,
                    vehiculo, afecta_rotacion, estado, motivo, observaciones
                FROM asignaciones_rotacion
                WHERE id=?
                LIMIT 1
                """,
                (int(asig_id),),
            ).fetchone()
            if not row:
                flash("Asignacion inexistente.", "warning")
                return redirect(url_for("asignaciones_historial"))

            form_data = {
                "id": int(row["id"]),
                "fecha": (row["fecha"] or "").strip(),
                "zona": (row["zona"] or "").strip(),
                "destino": (row["destino"] or "").strip(),
                "tipo_viaje": (row["tipo_viaje"] or "").strip(),
                "tipo_carga": (row["tipo_carga"] or "").strip(),
                "puntaje": int(row["puntaje"] or 0),
                "chofer_id": int(row["chofer_id"] or 0),
                "vehiculo": (row["vehiculo"] or "").strip(),
                "afecta_rotacion": int(row["afecta_rotacion"] or 0),
                "estado": (row["estado"] or "").strip(),
                "motivo": (row["motivo"] or "").strip(),
                "observaciones": (row["observaciones"] or "").strip(),
            }

            if request.method == "POST":
                payload, errores = _assignment_payload_from_form(con)
                form_data.update(payload)
                if errores:
                    for e in errores:
                        flash(e, "warning")
                else:
                    registrar_asignacion(con, payload, asig_id)
                    flash("Asignacion actualizada.", "success")
                    return redirect(url_for("asignaciones_historial"))

            return _render("nueva", con, {"form_data": form_data, "editing": True, "edit_id": asig_id})
        finally:
            con.close()

    @app.route("/asignaciones/eliminar/<int:asig_id>", methods=["POST"], endpoint="asignaciones_eliminar")
    def asignaciones_eliminar(asig_id):
        if not _can_access():
            return _deny()
        con = get_db()
        _ensure_schema(con)
        try:
            con.execute("DELETE FROM asignaciones_rotacion WHERE id=?", (int(asig_id),))
            con.commit()
            flash("Asignacion eliminada.", "success")
        finally:
            con.close()
        return redirect(url_for("asignaciones_historial"))

    @app.route("/asignaciones/historial", endpoint="asignaciones_historial")
    def asignaciones_historial():
        if not _can_access():
            return _deny()
        flash("Vista oculta. Usa Rotacion o Planilla diaria.", "info")
        return redirect(url_for("asignaciones_home"))
        con = get_db()
        _ensure_schema(con)
        try:
            filtros = {
                "desde": (request.args.get("desde") or "").strip(),
                "hasta": (request.args.get("hasta") or "").strip(),
                "chofer_id": _to_int(request.args.get("chofer_id"), 0),
                "zona": (request.args.get("zona") or "").strip(),
                "destino": (request.args.get("destino") or "").strip(),
                "tipo_carga": (request.args.get("tipo_carga") or "").strip(),
                "estado": (request.args.get("estado") or "").strip(),
            }
            rows = listar_historial(con, filtros)
            if _norm(request.args.get("export")) in {"1", "si", "true", "excel"}:
                sio = io.StringIO()
                wr = csv.writer(sio, delimiter=";")
                wr.writerow(
                    [
                        "Fecha",
                        "Zona",
                        "Destino",
                        "Chofer",
                        "Tipo viaje",
                        "Carga",
                        "Puntaje",
                        "Vehiculo",
                        "Afecta rotacion",
                        "Estado",
                        "Motivo",
                        "Observaciones",
                    ]
                )
                for r in rows:
                    wr.writerow(
                        [
                            r["fecha"],
                            r["zona"],
                            r["destino"],
                            r["chofer"],
                            r["tipo_viaje"],
                            r["tipo_carga"],
                            r["puntaje"],
                            r["vehiculo"],
                            ("Si" if int(r["afecta_rotacion"] or 0) == 1 else "No"),
                            r["estado"],
                            r["motivo"],
                            r["observaciones"],
                        ]
                    )
                resp = make_response(sio.getvalue())
                resp.headers["Content-Type"] = "text/csv; charset=utf-8"
                resp.headers["Content-Disposition"] = "attachment; filename=asignaciones_historial.csv"
                return resp

            return _render("historial", con, {})
        finally:
            con.close()

    @app.route("/asignaciones/planilla", methods=["GET", "POST"], endpoint="asignaciones_planilla")
    def asignaciones_planilla():
        if not _can_access():
            return _deny()
        con = get_db()
        _ensure_schema(con)
        try:
            form_data = {
                "fecha": _today_iso(),
                "hora_salida": "",
                "hora_regreso_estimada": "",
                "chofer_id": 0,
                "vehiculo": "",
                "solicitante": "",
                "destino": "",
                "tipo_asignacion": "",
                "estado": "Pendiente",
                "observaciones": "",
            }
            if request.method == "POST":
                payload, errores = _planilla_payload_from_form()
                form_data.update(payload)
                if errores:
                    for e in errores:
                        flash(e, "warning")
                else:
                    rid = _save_planilla_diaria(con, payload, 0)
                    flash(f"Asignacion diaria registrada (ID {rid}).", "success")
                    return redirect(
                        url_for(
                            "asignaciones_planilla",
                            pd_fecha=payload["fecha"],
                        )
                    )

            filtros = _planilla_filters_from_request()
            rows = _list_planilla_diaria(con, filtros)
            if _norm(request.args.get("export")) in {"1", "si", "true", "excel"}:
                sio = io.StringIO()
                wr = csv.writer(sio, delimiter=";")
                wr.writerow(
                    [
                        "Fecha",
                        "Hora salida",
                        "Hora regreso estimada",
                        "Chofer",
                        "Vehiculo",
                        "Solicitante",
                        "Destino",
                        "Tipo asignacion",
                        "Estado",
                        "Observaciones",
                    ]
                )
                for r in rows:
                    wr.writerow(
                        [
                            r["fecha"],
                            r["hora_salida"],
                            r["hora_regreso_estimada"],
                            r["chofer"],
                            r["vehiculo"],
                            r["solicitante"],
                            r["destino"],
                            r["tipo_asignacion"],
                            r["estado"],
                            r["observaciones"],
                        ]
                    )
                resp = make_response(sio.getvalue())
                resp.headers["Content-Type"] = "text/csv; charset=utf-8"
                resp.headers["Content-Disposition"] = "attachment; filename=asignaciones_planilla_diaria.csv"
                return resp

            return _render("planilla", con, {"planilla_form": form_data})
        finally:
            con.close()

    @app.route("/asignaciones/planilla/eliminar/<int:row_id>", methods=["POST"], endpoint="asignaciones_planilla_eliminar")
    def asignaciones_planilla_eliminar(row_id):
        if not _can_access():
            return _deny()
        con = get_db()
        _ensure_schema(con)
        try:
            con.execute("DELETE FROM planilla_diaria WHERE id=?", (int(row_id),))
            con.commit()
            flash("Fila eliminada de planilla diaria.", "success")
            return redirect(
                url_for(
                    "asignaciones_planilla",
                    pd_fecha=request.args.get("pd_fecha") or "",
                )
            )
        finally:
            con.close()

    @app.route("/asignaciones/rotacion-visual", methods=["GET", "POST"], endpoint="asignaciones_rotacion_visual")
    def asignaciones_rotacion_visual():
        if not _can_access():
            return _deny()
        return redirect(url_for("asignaciones_home"))
        con = get_db()
        _ensure_schema(con)
        try:
            rv_tipo = _rotacion_tipo_from_request()
            rv_destino = (request.args.get("rv_destino") or request.form.get("rv_destino") or "").strip()
            periodo_q = request.args.get("periodo") or request.form.get("periodo") or ""
            fecha_ref_q = request.args.get("fecha_ref") or request.form.get("fecha_ref") or ""

            if request.method == "POST":
                action = _norm(request.form.get("rv_action"))
                if action == "update_row":
                    row_id = _to_int(request.form.get("row_id"), 0)
                    payload = {
                        "chofer_id": _to_int(request.form.get("chofer_id"), 0),
                        "fecha_programada": (request.form.get("fecha_programada") or "").strip(),
                        "observaciones": (request.form.get("observaciones") or "").strip(),
                        "activo": (1 if _norm(request.form.get("activo") or "") in {"1", "si", "true", "on"} else 0),
                    }
                    if row_id <= 0 or payload["chofer_id"] <= 0:
                        flash("Fila o chofer invalido para actualizar la rueda.", "warning")
                    else:
                        _update_rotacion_visual_row(con, row_id, rv_tipo, payload)
                        flash("Rueda manual actualizada.", "success")
                elif action == "move_up":
                    row_id = _to_int(request.form.get("row_id"), 0)
                    if not _move_rotacion_visual(con, row_id, rv_tipo, "up"):
                        flash("No se pudo mover mas arriba.", "warning")
                elif action == "move_down":
                    row_id = _to_int(request.form.get("row_id"), 0)
                    if not _move_rotacion_visual(con, row_id, rv_tipo, "down"):
                        flash("No se pudo mover mas abajo.", "warning")
                elif action == "reorder":
                    ordered_raw = (request.form.get("ordered_ids") or "").strip()
                    ordered_ids = [x for x in ordered_raw.split(",") if x.strip()]
                    _reorder_rotacion_visual(con, rv_tipo, ordered_ids)
                    flash("Orden manual actualizado.", "success")
                elif action == "save_ref":
                    rv_destino = (request.form.get("rv_destino") or rv_destino or "").strip()
                    if not rv_destino:
                        flash("Selecciona destino para editar referencia.", "warning")
                    else:
                        payload = {
                            "km_aprox": request.form.get("km_aprox"),
                            "horas_aprox": request.form.get("horas_aprox"),
                            "salida_habitual": request.form.get("salida_habitual"),
                            "llegada_habitual": request.form.get("llegada_habitual"),
                            "tipo_carga": request.form.get("tipo_carga"),
                            "jornada_extendida": request.form.get("jornada_extendida"),
                            "observaciones": request.form.get("observaciones"),
                        }
                        _save_destino_referencia(con, rv_tipo, rv_destino, payload)
                        flash("Referencia de viaje actualizada.", "success")
                return redirect(
                    url_for(
                        "asignaciones_rotacion_visual",
                        periodo=periodo_q,
                        fecha_ref=fecha_ref_q,
                        rv_tipo=rv_tipo,
                        rv_destino=rv_destino,
                    )
                )

            return _render("rotacion_visual", con, {})
        finally:
            con.close()

    @app.route("/asignaciones/choferes", methods=["GET", "POST"], endpoint="asignaciones_choferes")
    def asignaciones_choferes():
        if not _can_access():
            return _deny()
        flash("Vista oculta. Usa Rotacion o Planilla diaria.", "info")
        return redirect(url_for("asignaciones_home"))
        con = get_db()
        _ensure_schema(con)
        try:
            if request.method == "POST":
                action = _norm(request.form.get("action"))
                if action == "add_chofer":
                    nombre = (request.form.get("nombre") or "").strip()
                    orden = _to_int(request.form.get("orden_rotacion"), 999)
                    obs = (request.form.get("observaciones") or "").strip()
                    if not nombre:
                        flash("Nombre de chofer obligatorio.", "warning")
                    else:
                        con.execute(
                            """
                            INSERT INTO choferes_rotacion(nombre, activo, orden_rotacion, observaciones)
                            SELECT ?, 1, ?, ?
                            WHERE NOT EXISTS(
                                SELECT 1 FROM choferes_rotacion WHERE LOWER(COALESCE(nombre,'')) = LOWER(?)
                            )
                            """,
                            (nombre, orden, obs, nombre),
                        )
                        con.commit()
                        flash("Chofer agregado.", "success")
                elif action == "update_chofer":
                    cid = _to_int(request.form.get("chofer_id"), 0)
                    orden = _to_int(request.form.get("orden_rotacion"), 999)
                    activo = 1 if _norm(request.form.get("activo") or "1") in {"1", "si", "true", "on"} else 0
                    obs = (request.form.get("observaciones") or "").strip()
                    if cid > 0:
                        con.execute(
                            """
                            UPDATE choferes_rotacion
                            SET orden_rotacion=?, activo=?, observaciones=?
                            WHERE id=?
                            """,
                            (orden, activo, obs, cid),
                        )
                        con.commit()
                        flash("Chofer actualizado.", "success")
                elif action == "add_exclusion":
                    cid = _to_int(request.form.get("chofer_id"), 0)
                    d1 = (request.form.get("fecha_desde") or "").strip()
                    d2 = (request.form.get("fecha_hasta") or "").strip()
                    mot = (request.form.get("motivo") or "").strip()
                    if cid <= 0 or not _parse_iso(d1) or not _parse_iso(d2) or not mot:
                        flash("Exclusion incompleta: chofer, fechas y motivo son obligatorios.", "warning")
                    else:
                        con.execute(
                            """
                            INSERT INTO exclusiones_chofer(chofer_id, fecha_desde, fecha_hasta, motivo, activo)
                            VALUES (?,?,?,?,1)
                            """,
                            (cid, d1, d2, mot),
                        )
                        con.commit()
                        flash("Exclusion temporal registrada.", "success")
                elif action == "close_exclusion":
                    ex_id = _to_int(request.form.get("exclusion_id"), 0)
                    if ex_id > 0:
                        con.execute("UPDATE exclusiones_chofer SET activo=0 WHERE id=?", (ex_id,))
                        con.commit()
                        flash("Exclusion desactivada.", "success")
                return redirect(url_for("asignaciones_choferes"))

            return _render("choferes", con, {})
        finally:
            con.close()

    @app.route("/asignaciones/configuracion", methods=["GET", "POST"], endpoint="asignaciones_configuracion")
    def asignaciones_configuracion():
        if not _can_access():
            return _deny()
        flash("Vista oculta. Usa Rotacion o Planilla diaria.", "info")
        return redirect(url_for("asignaciones_home"))
        con = get_db()
        _ensure_schema(con)
        try:
            if request.method == "POST":
                action = _norm(request.form.get("action"))
                if action == "save_config":
                    periodo = _period_or_default(request.form.get("periodo_default"), 60)
                    criterio = (request.form.get("criterio_empate") or "").strip()
                    obs = (request.form.get("observaciones") or "").strip()
                    con.execute(
                        """
                        UPDATE configuracion_rotacion
                        SET periodo_default=?, criterio_empate=?, observaciones=?
                        WHERE id=1
                        """,
                        (periodo, criterio, obs),
                    )
                    con.commit()
                    flash("Configuracion guardada.", "success")
                elif action == "add_destino":
                    zona = (request.form.get("zona") or "").strip()
                    destino = (request.form.get("destino") or "").strip()
                    carga = (request.form.get("tipo_carga") or "").strip()
                    puntaje = _to_int(request.form.get("puntaje"), 0)
                    if not puntaje:
                        puntaje = _puntaje_by_carga(carga)
                    if not (zona and destino and carga and puntaje):
                        flash("Completa zona, destino, tipo de carga y puntaje.", "warning")
                    else:
                        con.execute(
                            """
                            INSERT INTO destinos_rotacion(zona, destino, tipo_carga, puntaje, activo, observaciones)
                            VALUES (?,?,?,?,1,'')
                            ON CONFLICT(zona, destino)
                            DO UPDATE SET tipo_carga=excluded.tipo_carga, puntaje=excluded.puntaje
                            """,
                            (zona, destino, carga, puntaje),
                        )
                        con.commit()
                        flash("Destino guardado.", "success")
                elif action == "toggle_destino":
                    did = _to_int(request.form.get("destino_id"), 0)
                    activo = 1 if _norm(request.form.get("activo") or "1") in {"1", "si", "true", "on"} else 0
                    if did > 0:
                        con.execute("UPDATE destinos_rotacion SET activo=? WHERE id=?", (activo, did))
                        con.commit()
                        flash("Destino actualizado.", "success")
                elif action == "update_destino":
                    did = _to_int(request.form.get("destino_id"), 0)
                    zona = (request.form.get("zona") or "").strip()
                    destino = (request.form.get("destino") or "").strip()
                    carga = (request.form.get("tipo_carga") or "").strip()
                    puntaje = _to_int(request.form.get("puntaje"), 0)
                    obs = (request.form.get("observaciones") or "").strip()
                    if did > 0 and zona and destino:
                        con.execute(
                            """
                            UPDATE destinos_rotacion
                            SET zona=?, destino=?, tipo_carga=?, puntaje=?, observaciones=?
                            WHERE id=?
                            """,
                            (zona, destino, carga, puntaje, obs, did),
                        )
                        con.commit()
                        flash("Destino editado.", "success")
                return redirect(url_for("asignaciones_configuracion"))

            return _render("config", con, {})
        finally:
            con.close()

    @app.route("/asignaciones/sugerir", endpoint="asignaciones_sugerir")
    def asignaciones_sugerir():
        if not _can_access():
            return jsonify({"ok": False, "error": "No autorizado"}), 403
        con = get_db()
        _ensure_schema(con)
        try:
            zona = (request.args.get("zona") or "").strip()
            destino = (request.args.get("destino") or "").strip()
            tipo_carga = (request.args.get("tipo_carga") or "").strip()
            periodo = _period_or_default(request.args.get("periodo"), _fetch_config(con)["periodo_default"])
            ref_iso = (request.args.get("fecha_ref") or "").strip() or _today_iso()
            sug = sugerir_proximo_chofer(con, destino, zona, periodo, ref_iso, tipo_carga)
            return jsonify(
                {
                    "ok": True,
                    "sugerido_id": sug.get("sugerido_id"),
                    "sugerido": sug.get("sugerido", ""),
                    "tipo_carga": sug.get("tipo_carga", ""),
                    "puntaje": sug.get("puntaje", 0),
                    "orden": [
                        {
                            "chofer_id": int(r["chofer_id"]),
                            "chofer": r["chofer"],
                            "puntos": int(r["puntos"]),
                            "viajes": int(r["viajes"]),
                            "ultimo_pesado": r["ultimo_pesado"],
                            "estado": r["estado_disponibilidad"],
                        }
                        for r in sug.get("orden_sugerido", [])
                    ],
                }
            )
        finally:
            con.close()
