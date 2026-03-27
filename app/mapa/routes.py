import sqlite3
from flask import Blueprint
from . import bp

from datetime import date
import sqlite3
from datetime import date
import re
import unicodedata
from flask import render_template, request, jsonify
def register_mapa_routes(app, bp, get_db):
    def _strip_accents(text):
        if not text:
            return ""
        return "".join(
            ch for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )

    def normalize_institucion_categoria(text):
        s = (text or "").strip()
        if not s:
            return ""

        fold = _strip_accents(s).lower()

        replacements = [
            (r"\bcomisaria(s)?\b|\bcomis\.\b", "Comisaria"),
            (r"\bseccional(es)?\b|\bsecc\.\b", "Seccional"),
            (r"\bbrigada(s)?\b", "Brigada"),
            (r"\bsubcomisaria(s)?\b", "Subcomisaria"),
            (r"\bpolicia\b|\bpolicial\b", "Policia"),
        ]

        for pattern, label in replacements:
            if re.search(pattern, fold):
                return label

        # Fallback: conservar contenido pero sin espacios duplicados.
        return " ".join(s.split())

    def ensure_mapa_ssj_table(con):
        con.execute("""
        CREATE TABLE IF NOT EXISTS mapa_ssj_puntos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            direccion TEXT,
            lat REAL,
            lng REAL,
            fecha_alta TEXT NOT NULL,
            fecha_visita TEXT,
            contacto TEXT,
            referencia TEXT
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mapa_ssj_tipo_estado ON mapa_ssj_puntos(tipo, estado)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mapa_ssj_fecha_alta ON mapa_ssj_puntos(fecha_alta DESC, id DESC)")

    def ensure_cols(con, table, cols):
        cur = con.cursor()
        existing = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        for name, ctype in cols:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ctype}")
        con.commit()

    def normalize_payload(data):
        tipo = (data.get("tipo") or "otro").strip().lower()
        is_pericia = (tipo == "pericia")
        is_evacuacion = (tipo == "evacuacion")
        is_institucion = (tipo == "institucion")

        estado = "pendiente"
        if is_pericia:
            estado_in = (data.get("estado") or "pendiente").strip().lower()
            if estado_in in ("pendiente", "en_curso", "cerrado"):
                estado = estado_in

        return {
            "tipo": tipo,
            "estado": estado,
            "categoria": normalize_institucion_categoria(data.get("categoria")) if is_institucion else (data.get("categoria") or "").strip(),
            "responsable": (data.get("responsable") or "").strip() if is_evacuacion else "",
            "expediente": (data.get("expediente") or "").strip() if is_pericia else "",
            "asistido_nombre": (data.get("asistido_nombre") or "").strip() if is_pericia else "",
            "etapa": (data.get("etapa") or "").strip() if is_pericia else "",
            "etapa_total": (data.get("etapa_total") or "").strip() if is_pericia else "",
            "resultado": (data.get("resultado") or "").strip() if is_pericia else "",
            "resultado_detalle": (data.get("resultado_detalle") or "").strip() if is_pericia else "",
            "fecha_objetivo": (data.get("fecha_objetivo") or "").strip() if is_pericia else "",
        }
    # --- DDL BOOTSTRAP INJECTED ---

    ensure_mapa_ssj_table(get_db())
    # ------------------------------


    @bp.get("/mapa_ssj")
    def mapa_ssj():
        tipos_select = [
            "sede_mpd", "sede_mpa", "sede_pj",
            "proveedor", "institucion", "comisaria", "registro_civil", "servicio_penitenciario", "pericia", "otro"
        ]
        estados_select = ["pendiente", "en_curso", "cerrado"]
        return render_template(
            "mapa_ssj.html",
            title="Mapa SSJ",
            tipos_select=tipos_select,
            estados_select=estados_select
        )

    @bp.get("/api/mapa_ssj_puntos")
    def api_mapa_ssj_puntos():
        tipo = (request.args.get("tipo") or "").strip()
        estado = (request.args.get("estado") or "").strip()

        con = get_db()
        con.row_factory = sqlite3.Row
        # ensure_mapa_ssj_table(con)  # DDL-MOVED

        q = "SELECT * FROM mapa_ssj_puntos WHERE 1=1"
        params = []

        if tipo:
            if tipo == "sede_mpd":
                q += " AND tipo IN (?,?)"
                params.extend(["sede_mpd", "sede"])
            else:
                q += " AND tipo = ?"
                params.append(tipo)
        if estado:
            q += " AND estado = ?"
            params.append(estado)

        q += " ORDER BY fecha_alta DESC, id DESC"
        rows = con.execute(q, params).fetchall()
        con.close()

        out = []
        for r in rows:
            d = dict(r)
            if d.get("lat") is not None and d.get("lng") is not None:
                d["link_maps"] = f"https://www.google.com/maps?q={d['lat']},{d['lng']}"
            else:
                d["link_maps"] = ""
            out.append(d)

        return jsonify(out)

    @bp.post("/mapa_ssj/nuevo")
    def mapa_ssj_nuevo():
        data = request.get_json(force=True) or {}
        cleaned = normalize_payload(data)

        tipo = cleaned["tipo"]
        titulo = (data.get("titulo") or "").strip()
        if not titulo:
            return jsonify({"ok": False, "error": "Falta título"}), 400

        descripcion = (data.get("descripcion") or "").strip()
        direccion = (data.get("direccion") or "").strip()
        contacto = (data.get("contacto") or "").strip()
        referencia = (data.get("referencia") or "").strip()

        lat = data.get("lat")
        lng = data.get("lng")
        try:
            lat = float(lat) if lat not in (None, "", "null", "None") else None
            lng = float(lng) if lng not in (None, "", "null", "None") else None
        except Exception:
            lat, lng = None, None

        fecha_alta = (data.get("fecha_alta") or "").strip()
        if not fecha_alta:
            fecha_alta = date.today().strftime("%Y-%m-%d")

        con = get_db()
        # ensure_mapa_ssj_table(con)  # DDL-MOVED

        con.execute("""
            INSERT INTO mapa_ssj_puntos
            (tipo,titulo,descripcion,estado,direccion,lat,lng,fecha_alta,contacto,referencia,
             categoria,responsable,expediente,asistido_nombre,etapa,etapa_total,resultado,resultado_detalle,
             direccion_extra,barrio,localidad,fecha_objetivo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            tipo, titulo, descripcion, cleaned["estado"], direccion, lat, lng, fecha_alta,
            contacto, referencia,
            cleaned["categoria"],
            cleaned["responsable"],
            cleaned["expediente"],
            cleaned["asistido_nombre"],
            cleaned["etapa"],
            cleaned["etapa_total"],
            cleaned["resultado"],
            cleaned["resultado_detalle"],
            (data.get("direccion_extra") or "").strip(),
            (data.get("barrio") or "").strip(),
            (data.get("localidad") or "").strip(),
            cleaned["fecha_objetivo"],
        ))

        con.commit()
        con.close()
        return jsonify({"ok": True})

    @bp.post("/mapa_ssj/editar/<int:punto_id>")
    def mapa_ssj_editar(punto_id):
        data = request.get_json(force=True) or {}
        cleaned = normalize_payload(data)

        tipo = cleaned["tipo"]
        titulo = (data.get("titulo") or "").strip()
        if not titulo:
            return jsonify({"ok": False, "error": "Falta título"}), 400

        descripcion = (data.get("descripcion") or "").strip()
        direccion = (data.get("direccion") or "").strip()
        contacto = (data.get("contacto") or "").strip()
        referencia = (data.get("referencia") or "").strip()

        lat = data.get("lat")
        lng = data.get("lng")
        try:
            lat = float(lat) if lat not in (None, "", "null", "None") else None
            lng = float(lng) if lng not in (None, "", "null", "None") else None
        except Exception:
            lat, lng = None, None

        fecha_alta = (data.get("fecha_alta") or "").strip()
        if not fecha_alta:
            fecha_alta = date.today().strftime("%Y-%m-%d")

        con = get_db()
        # ensure_mapa_ssj_table(con)  # DDL-MOVED

        con.execute("""
            UPDATE mapa_ssj_puntos
            SET tipo=?, titulo=?, descripcion=?, estado=?, direccion=?, lat=?, lng=?,
                fecha_alta=?, contacto=?, referencia=?,
                categoria=?, responsable=?, expediente=?, asistido_nombre=?, etapa=?, etapa_total=?,
                resultado=?, resultado_detalle=?, direccion_extra=?, barrio=?, localidad=?, fecha_objetivo=?
            WHERE id=?
        """, (
            tipo, titulo, descripcion, cleaned["estado"],
            direccion, lat, lng, fecha_alta, contacto, referencia,
            cleaned["categoria"],
            cleaned["responsable"],
            cleaned["expediente"],
            cleaned["asistido_nombre"],
            cleaned["etapa"],
            cleaned["etapa_total"],
            cleaned["resultado"],
            cleaned["resultado_detalle"],
            (data.get("direccion_extra") or "").strip(),
            (data.get("barrio") or "").strip(),
            (data.get("localidad") or "").strip(),
            cleaned["fecha_objetivo"],
            punto_id
        ))
        con.commit()
        con.close()
        return jsonify({"ok": True})

    @bp.post("/mapa_ssj/estado/<int:punto_id>")
    def mapa_ssj_estado(punto_id):
        data = request.get_json(force=True) or {}
        estado = (data.get("estado") or "").strip().lower()
        fecha_visita = (data.get("fecha_visita") or "").strip()

        if estado not in ("pendiente", "en_curso", "cerrado"):
            return jsonify({"ok": False, "error": "Estado inválido"}), 400

        con = get_db()
        # ensure_mapa_ssj_table(con)  # DDL-MOVED

        if estado == "cerrado":
            if not fecha_visita:
                fecha_visita = date.today().strftime("%Y-%m-%d")
            con.execute("UPDATE mapa_ssj_puntos SET estado=?, fecha_visita=? WHERE id=?",
                        (estado, fecha_visita, punto_id))
        else:
            con.execute("UPDATE mapa_ssj_puntos SET estado=?, fecha_visita=NULL WHERE id=?",
                        (estado, punto_id))

        con.commit()
        con.close()
        return jsonify({"ok": True})

    @bp.post("/mapa_ssj/borrar/<int:punto_id>")
    def mapa_ssj_borrar(punto_id):
        con = get_db()
        # ensure_mapa_ssj_table(con)  # DDL-MOVED
        con.execute("DELETE FROM mapa_ssj_puntos WHERE id=?", (punto_id,))
        con.commit()
        con.close()
        return jsonify({"ok": True})
