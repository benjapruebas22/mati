from datetime import date, datetime, timedelta
import sqlite3
from collections import defaultdict
import csv
import io
import os
import json
import uuid

from flask import render_template, request, redirect, url_for, flash, Response, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from modules.sede_navigation import build_operativa_nav_context


def register_sst(app, get_db, ensure_cols, ensure_sedes_mpd_cols, cal_colors, ensure_auth_tables, default_redirect_for_role=None):
    default_redirect_for_role_fn = default_redirect_for_role if callable(default_redirect_for_role) else None
    CAL_COLORS = cal_colors
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SST_DOCS_FOLDER = os.path.join(BASE_DIR, "uploads", "sst_documentacion")
    os.makedirs(SST_DOCS_FOLDER, exist_ok=True)
    ALLOWED_SST_DOC_EXT = {"pdf", "jpg", "jpeg", "png"}

    def allowed_sst_doc(filename: str) -> bool:
        if not filename or "." not in filename:
            return False
        ext = filename.rsplit(".", 1)[1].lower()
        return ext in ALLOWED_SST_DOC_EXT
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

    DOCUMENTOS_TIPOS = [
        "informe",
        "protocolo",
        "instruccion",
        "acta",
        "nota",
        "documento_general",
    ]
    DOCUMENTOS_ESTADOS = [
        "borrador",
        "emitido",
        "enviado",
        "cerrado",
        "archivado",
    ]
    DOCUMENTOS_DESTINOS = [
        "Defensora General",
        "Administrador General",
        "Archivo institucional",
        "Interno Intendencia",
    ]

    SGSST_PLAN_PHASE_META = {
        "marco": {
            "key": "marco",
            "short": "Etapa 1",
            "title": "Marco y organizacion",
            "tone": "slate",
            "description": "Lineamientos, alcance, roles y metodologia institucional.",
        },
        "diagnostico": {
            "key": "diagnostico",
            "short": "Etapa 2",
            "title": "Diagnostico",
            "tone": "blue",
            "description": "Situacion real por sede, modulos relevados y hallazgos abiertos.",
        },
        "implementacion": {
            "key": "implementacion",
            "short": "Etapa 3",
            "title": "Implementacion",
            "tone": "amber",
            "description": "Acciones, responsables, compras y regularizacion en curso.",
        },
        "operacion": {
            "key": "operacion",
            "short": "Etapa 4",
            "title": "Operacion y control",
            "tone": "green",
            "description": "Controles periodicos, vencimientos y verificacion sostenida.",
        },
    }
    SGSST_PLAN_HALLAZGO_STATES = [
        "Detectado",
        "En analisis",
        "Confirmado",
        "No aplica",
        "Resuelto",
        "Cerrado",
    ]
    SGSST_PLAN_ACTION_STATES = [
        "Pendiente",
        "En analisis",
        "En gestion",
        "Programada",
        "En ejecucion",
        "Bloqueada",
        "Implementada",
        "Verificada",
        "Cerrada",
        "Cancelada",
    ]
    SGSST_PLAN_PRIORITIES = ["Baja", "Media", "Alta", "Critica"]
    SGSST_PLAN_ROLE_SEED = [
        {"grupo": "Autoridad institucional", "rol": "Defensora General", "orden_visual": 10},
        {"grupo": "Autoridad institucional", "rol": "Defensor General Adjunto", "orden_visual": 20},
        {"grupo": "Autoridad institucional", "rol": "Administrador General", "orden_visual": 30},
        {"grupo": "Coordinacion operativa", "rol": "Encargado de Intendencia", "orden_visual": 40},
        {"grupo": "Coordinacion operativa", "rol": "Responsable SG-SST", "orden_visual": 50},
        {"grupo": "Coordinacion operativa", "rol": "Responsables administrativos", "orden_visual": 60},
        {"grupo": "Ejecucion", "rol": "Equipo de mantenimiento", "orden_visual": 70},
        {"grupo": "Ejecucion", "rol": "Personal de limpieza", "orden_visual": 80},
        {"grupo": "Ejecucion", "rol": "Choferes", "orden_visual": 90},
        {"grupo": "Ejecucion", "rol": "Prestadores externos", "orden_visual": 100},
        {"grupo": "Ejecucion", "rol": "Responsables de sede", "orden_visual": 110},
        {"grupo": "Apoyo y control", "rol": "ART", "orden_visual": 120},
        {"grupo": "Apoyo y control", "rol": "Medicina laboral", "orden_visual": 130},
        {"grupo": "Apoyo y control", "rol": "Compras", "orden_visual": 140},
        {"grupo": "Apoyo y control", "rol": "Contaduria", "orden_visual": 150},
        {"grupo": "Apoyo y control", "rol": "Sistemas", "orden_visual": 160},
        {"grupo": "Apoyo y control", "rol": "Recursos Humanos", "orden_visual": 170},
    ]
    SGSST_COMMAND_SCOPE_OPTIONS = [
        {"value": "AUTO", "label": "Segun modulo"},
        {"value": "COMPLETA", "label": "Completa"},
        {"value": "PENDIENTE", "label": "Pendiente"},
        {"value": "NO_APLICA", "label": "No aplica"},
        {"value": "FUERA_ALCANCE", "label": "Fuera de alcance temporal"},
    ]
    SGSST_COMMAND_SCOPE_LABELS = {
        "AUTO": "Segun modulo",
        "COMPLETA": "Completa",
        "PENDIENTE": "Pendiente",
        "NO_APLICA": "No aplica",
        "FUERA_ALCANCE": "Fuera de alcance temporal",
    }
    SGSST_COMMAND_PROJECT_SEED = [
        {
            "key": "carteleria",
            "label": "Carteleria",
            "icon": "🚪",
            "module_names": {"Carteleria"},
            "type_keys": {"carteleria"},
            "timeline_type": "carteleria",
            "keywords": ("carteleria",),
            "fallback_responsible": "Intendencia",
        },
        {
            "key": "luces",
            "label": "Luces de emergencia",
            "icon": "💡",
            "module_names": {"Luces de emergencia"},
            "type_keys": {"luces"},
            "timeline_type": "luces",
            "keywords": ("luces", "emergencia"),
            "fallback_responsible": "Intendencia",
        },
        {
            "key": "matafuegos",
            "label": "Matafuegos",
            "icon": "🧯",
            "module_names": {"Matafuegos"},
            "type_keys": {"matafuegos"},
            "timeline_type": "matafuegos",
            "keywords": ("matafuegos",),
            "fallback_responsible": "Intendencia",
        },
        {
            "key": "desinfeccion",
            "label": "Desinfeccion",
            "icon": "🧼",
            "module_names": {"Desinfeccion"},
            "type_keys": {"desinfeccion"},
            "timeline_type": "desinfeccion",
            "keywords": ("desinfeccion", "desinfecciones"),
            "fallback_responsible": "Intendencia",
        },
        {
            "key": "art",
            "label": "ART",
            "icon": "📋",
            "module_names": {"ART"},
            "type_keys": {"visita"},
            "timeline_type": "visita",
            "keywords": ("art", "visitas art", "visita art"),
            "fallback_responsible": "Responsable SG-SST",
        },
        {
            "key": "documentacion",
            "label": "Documentacion",
            "icon": "📄",
            "module_names": {"Documentacion"},
            "type_keys": {"documentacion"},
            "timeline_type": "documentacion",
            "keywords": ("documentacion", "rgrl", "351", "decreto 351"),
            "fallback_responsible": "Responsable SG-SST",
        },
        {
            "key": "evacuacion",
            "label": "Evacuacion",
            "icon": "🚨",
            "module_names": {"Evacuacion"},
            "type_keys": {"planos"},
            "timeline_type": "planos",
            "keywords": ("evacuacion", "plano", "planos"),
            "fallback_responsible": "Intendencia",
        },
    ]
    SST_MATRIX_PHASE_META = {
        "DIAGNOSTICO": {"label": "Diagnostico", "tone": "diagnostico", "order": 10},
        "PLANIFICACION": {"label": "Planificacion", "tone": "planificacion", "order": 20},
        "IMPLEMENTACION": {"label": "Implementacion", "tone": "implementacion", "order": 30},
        "OPERACION": {"label": "Operacion", "tone": "operacion", "order": 40},
        "NO_APLICA": {"label": "No aplica", "tone": "no-aplica", "order": 90},
    }
    SST_MATRIX_COMPONENTS = [
        {"key": "art", "label": "Visitas ART", "short": "ART", "project_key": "art", "history_component": "visitas_art"},
        {"key": "matafuegos", "label": "Matafuegos", "short": "Matafuegos", "project_key": "matafuegos", "history_component": "matafuegos"},
        {"key": "luces", "label": "Luces de emergencia", "short": "Luces", "project_key": "luces", "history_component": "luces"},
        {"key": "carteleria", "label": "Carteleria", "short": "Carteleria", "project_key": "carteleria", "history_component": "carteleria"},
        {"key": "evacuacion", "label": "Evacuacion", "short": "Evacuacion", "project_key": "evacuacion", "history_component": "evacuacion"},
        {"key": "desinfeccion", "label": "Desinfecciones", "short": "Desinfeccion", "project_key": "desinfeccion", "history_component": "desinfecciones"},
    ]

    def _sgsst_command_project_catalog():
        return [dict(item) for item in SGSST_COMMAND_PROJECT_SEED]

    def _sgsst_command_project_map():
        return {item["key"]: dict(item) for item in SGSST_COMMAND_PROJECT_SEED}

    def _sgsst_command_scope_label(value):
        key = str(value or "AUTO").strip().upper() or "AUTO"
        return SGSST_COMMAND_SCOPE_LABELS.get(key, SGSST_COMMAND_SCOPE_LABELS["AUTO"])

    def _sgsst_command_project_open_url(project_key, sede_code=""):
        sede_key = str(sede_code or "").strip().upper()
        if project_key == "carteleria":
            return url_for("sst_carteleria_home", sede=sede_key or None, open_sede=sede_key or None)
        if project_key == "luces":
            return url_for("sst_luces_home", sede=sede_key or None, open_sede=sede_key or None)
        if project_key == "matafuegos":
            return url_for("matafuegos_home", sede=sede_key or None, open_sede=sede_key or None)
        if project_key == "desinfeccion":
            return url_for("sst_desinfecciones_home", sede=sede_key or None, open_sede=sede_key or None)
        if project_key in {"art", "documentacion"}:
            return url_for("sst_visitas", sede=sede_key or None, open_sede=sede_key or None)
        if project_key == "evacuacion":
            if sede_key:
                return url_for("sede_ficha", codigo=sede_key, tab="evacuacion")
            return url_for("sst_calendario_operativo", tipo="planos")
        return url_for("sst_calendario_operativo")

    def ensure_sst_general_table(con):
        con.execute("""
        CREATE TABLE IF NOT EXISTS sst_general(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,          -- YYYY-MM-DD
            sede_codigo TEXT,             -- S01, S02, ...
            tipo TEXT NOT NULL,           -- prevencion / no_conformidad / informe
            categoria TEXT,
            area TEXT,
            titulo TEXT,
            detalle TEXT,
            estado TEXT,                  -- ABIERTO / CERRADO / EN_REVISION
            prioridad TEXT,
            responsable TEXT,
            accion_correctiva TEXT,
            evidencia_url TEXT,
            fecha_objetivo TEXT,
            fecha_cierre TEXT
        )
        """)
        ensure_cols(con, "sst_general", [
            ("categoria", "TEXT"),
            ("area", "TEXT"),
            ("prioridad", "TEXT"),
            ("responsable", "TEXT"),
            ("accion_correctiva", "TEXT"),
            ("evidencia_url", "TEXT"),
            ("fecha_objetivo", "TEXT"),
            ("fecha_cierre", "TEXT"),
            ("origen_tipo", "TEXT"),
            ("origen_id", "INTEGER"),
            ("origen_deposito_codigo", "TEXT"),
        ])
        con.commit()

    SST_VISITA_TIPOS = [
        "ART",
        "Interna",
        "Seguimiento",
        "Relevamiento inicial",
    ]
    SST_VISITA_ESTADOS = [
        "SIN_VISITA",
        "PROGRAMADA",
        "VISITADA",
        "OBSERVADA",
        "EN_SEGUIMIENTO",
        "CERRADA",
    ]
    SST_VISITA_ART_STATE_LABELS = {
        "SIN_VISITA": "Sin visita",
        "PROGRAMADA": "Programada",
        "VISITADA": "Visitada",
        "OBSERVADA": "Observada",
        "EN_SEGUIMIENTO": "En seguimiento",
        "CERRADA": "Cerrada",
    }
    SST_VISITA_ART_DOC_TYPE_LABELS = {
        "RGRL": "RGRL",
        "DEC_351_79": "Decreto 351/79",
    }
    SST_VISITA_ART_DOC_STATE_LABELS = {
        "SIN_DOCUMENTACION": "Sin documentacion",
        "FALTANTE": "Faltante",
        "CARGADO": "Cargado",
        "OBSERVADO": "Observado",
        "NO_APLICA": "No aplica",
    }
    SST_VISITA_ART_DOC_FILTER_LABELS = {
        "COMPLETA": "Completa",
        "INCOMPLETA": "Incompleta",
        "SIN_DOCUMENTACION": "Sin documentacion",
    }
    SST_VISITA_ART_OBSERVATION_LABELS = {
        "SIN_DATOS": "Sin datos",
        "SIN_OBSERVACIONES": "Sin observaciones",
        "OBSERVADA": "Observada",
    }
    SST_DOC_TIPOS = [
        "DEC_351_79",
        "RGRL",
        "RAR",
        "ACTA",
        "FOTO",
        "OTRO",
    ]
    SST_DOC_ESTADOS_REVISION = [
        "FALTANTE",
        "CARGADO",
        "OBSERVADO",
        "NO_APLICA",
    ]
    SST_CALENDAR_MONTHS = [
        (1, "Enero"),
        (2, "Febrero"),
        (3, "Marzo"),
        (4, "Abril"),
        (5, "Mayo"),
        (6, "Junio"),
        (7, "Julio"),
        (8, "Agosto"),
        (9, "Septiembre"),
        (10, "Octubre"),
        (11, "Noviembre"),
        (12, "Diciembre"),
    ]
    SST_CALENDAR_TYPE_META = {
        "desinfeccion": {"label": "Desinfeccion", "short": "DES", "icon": "\U0001F9F9", "action": "Abrir desinfecciones"},
        "matafuegos": {"label": "Matafuegos", "short": "MF", "icon": "🧯", "action": "Ver matafuegos"},
        "visita": {"label": "Visitas ART", "short": "VS", "icon": "👷", "action": "Abrir Visitas ART"},
        "documentacion": {"label": "Documentacion ART", "short": "DOC", "icon": "📄", "action": "Abrir documentacion"},
        "carteleria": {"label": "Carteleria", "short": "CAR", "icon": "🚪", "action": "Abrir sede"},
        "luces": {"label": "Luces de emergencia", "short": "LUC", "icon": "💡", "action": "Abrir sede"},
        "planos": {"label": "Plan de evacuacion", "short": "PE", "icon": "🚨", "action": "Abrir sede"},
        "seguimiento": {"label": "Seguimiento", "short": "SEG", "icon": "📌", "action": "Abrir seguimiento"},
        "hallazgo": {"label": "Hallazgo", "short": "HAL", "icon": "⚠", "action": "Abrir hallazgo"},
        "otro": {"label": "Otro control SG-SST", "short": "OT", "icon": "•", "action": "Abrir"},
    }
    SST_CALENDAR_STATE_META = {
        "cumplido": {"label": "Cumplido", "class": "ok", "rank": 10, "icon": "🟢"},
        "programado": {"label": "Programado", "class": "info", "rank": 20, "icon": "🔵"},
        "proximo": {"label": "Proximo", "class": "warn", "rank": 40, "icon": "🟡"},
        "pendiente": {"label": "Pendiente", "class": "pending", "rank": 45, "icon": "🟠"},
        "en_seguimiento": {"label": "En seguimiento", "class": "follow", "rank": 50, "icon": "🟣"},
        "vencido": {"label": "Vencido", "class": "danger", "rank": 60, "icon": "🔴"},
        "sin_datos": {"label": "Sin datos", "class": "muted", "rank": 15, "icon": "⚪"},
    }
    SST_CALENDAR_PHASE_META = {
        "diagnostico": {"key": "diagnostico", "short": "F1", "label": "Diagnostico", "title": "FASE 1 - DIAGNOSTICO"},
        "implementacion": {"key": "implementacion", "short": "F2", "label": "Implementacion", "title": "FASE 2 - IMPLEMENTACION"},
        "operacion": {"key": "operacion", "short": "F3", "label": "Operacion", "title": "FASE 3 - OPERACION"},
    }
    SST_CALENDAR_REQUIRED_DOCS = ("DEC_351_79", "RGRL")
    SST_CALENDAR_VISIBLE_TYPES = (
        "matafuegos",
        "desinfeccion",
        "luces",
        "carteleria",
        "visita",
        "documentacion",
        "planos",
        "hallazgo",
        "seguimiento",
    )
    SST_CALENDAR_MATAFUEGOS_SCHEDULE = {
        "S01": {"due_date": "2026-09-01", "lot_label": "Lote 1", "lot_month": "Septiembre"},
        "S03": {"due_date": "2026-09-01", "lot_label": "Lote 1", "lot_month": "Septiembre"},
        "S08": {"due_date": "2026-09-01", "lot_label": "Lote 1", "lot_month": "Septiembre"},
        "S10": {"due_date": "2026-09-01", "lot_label": "Lote 1", "lot_month": "Septiembre"},
        "S12": {"due_date": "2026-09-01", "lot_label": "Lote 1", "lot_month": "Septiembre"},
        "S04": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S05": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S06": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S07": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S11": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S14": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S15": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S16": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S18": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S20": {"due_date": "2027-05-01", "lot_label": "Lote 2", "lot_month": "Mayo"},
        "S13": {"due_date": "2026-12-01", "lot_label": "Lote 3", "lot_month": "Diciembre"},
    }
    SST_CARTELERIA_GROUP_LABELS = {
        "SEGURIDAD": "Seguridad",
        "PROTOCOLOS": "Protocolos",
        "IDENTIFICACION": "Identificacion",
    }
    SST_CARTELERIA_GROUP_ORDER = ["SEGURIDAD", "PROTOCOLOS", "IDENTIFICACION"]
    SST_CARTELERIA_TIPOS_SEED = [
        ("SEGURIDAD", "MATAFUEGOS", "Matafuegos", 10),
        ("SEGURIDAD", "SALIDA", "Salida", 20),
        ("SEGURIDAD", "SALIDA_IZQUIERDA", "Salida izquierda", 30),
        ("SEGURIDAD", "SALIDA_DERECHA", "Salida derecha", 40),
        ("SEGURIDAD", "CHOQUE_ELECTRICO", "Choque electrico", 50),
        ("SEGURIDAD", "ESCALERA_SUBIDA", "Escalera subida", 60),
        ("SEGURIDAD", "ESCALERA_BAJADA", "Escalera bajada", 70),
        ("SEGURIDAD", "LUZ_EMERGENCIA", "Luz de emergencia", 80),
        ("PROTOCOLOS", "PROHIBIDO_FUMAR", "Prohibido fumar", 110),
        ("PROTOCOLOS", "RESIDUOS_SECOS", "Residuos secos", 120),
        ("PROTOCOLOS", "RESIDUOS_HUMEDOS", "Residuos humedos", 130),
        ("PROTOCOLOS", "USO_RESPONSABLE_BANO", "Uso responsable del bano", 140),
        ("IDENTIFICACION", "CARTEL_IDENTIFICATORIO_SEDE", "Cartel identificatorio de la sede", 210),
        ("IDENTIFICACION", "PLANO_EVACUACION", "Plano de evacuacion", 220),
    ]
    SST_CARTELERIA_TIPO_LABELS = {codigo: nombre for _, codigo, nombre, _ in SST_CARTELERIA_TIPOS_SEED}
    SST_CARTELERIA_TIPO_GROUPS = {codigo: grupo for grupo, codigo, _, _ in SST_CARTELERIA_TIPOS_SEED}
    SST_CARTELERIA_TIPO_ORDER = {codigo: orden for _, codigo, _, orden in SST_CARTELERIA_TIPOS_SEED}
    SST_CARTELERIA_VISIBLE_CODES = [codigo for _, codigo, _, _ in SST_CARTELERIA_TIPOS_SEED]
    SST_CARTELERIA_APLICA_LABELS = {
        "SI": "Si",
        "NO": "No",
        "NO_RELEVADO": "No relevado",
    }
    SST_CARTELERIA_CANONICAL_TIPO_MAP = {
        "MATAFUEGOS": "MATAFUEGOS",
        "SALIDA": "SALIDA",
        "SALIDA_EMERGENCIA": "SALIDA",
        "SALIDA_IZQUIERDA": "SALIDA_IZQUIERDA",
        "SALIDA_DERECHA": "SALIDA_DERECHA",
        "RIESGO_ELECTRICO": "CHOQUE_ELECTRICO",
        "CHOQUE_ELECTRICO": "CHOQUE_ELECTRICO",
        "ESCALERA_SUBIDA": "ESCALERA_SUBIDA",
        "ESCALERA_BAJADA": "ESCALERA_BAJADA",
        "LUZ_EMERGENCIA": "LUZ_EMERGENCIA",
        "PROHIBIDO_FUMAR": "PROHIBIDO_FUMAR",
        "RESIDUOS_SECOS": "RESIDUOS_SECOS",
        "RESIDUOS_HUMEDOS": "RESIDUOS_HUMEDOS",
        "USO_RESPONSABLE_BANO": "USO_RESPONSABLE_BANO",
        "IDENTIFICACION_EXTERIOR": "CARTEL_IDENTIFICATORIO_SEDE",
        "PLANO_DIRECTORIO": "PLANO_EVACUACION",
        "PLANO_EVACUACION": "PLANO_EVACUACION",
        "CARTEL_IDENTIFICATORIO_SEDE": "CARTEL_IDENTIFICATORIO_SEDE",
    }
    SST_CARTELERIA_STATE_LABELS = {
        "NO_RELEVADO": "No relevado",
        "RELEVADO": "Relevado",
        "PENDIENTE_SOLICITUD": "Pendiente solicitud",
        "COMPRA_EN_PROCESO": "Compra en proceso",
        "MATERIAL_RECIBIDO": "Material recibido",
        "INSTALACION_PROGRAMADA": "Instalacion programada",
        "COMPLETO": "Completo",
    }
    SST_LUCES_STATE_LABELS = {
        "NO_APLICA": "No aplica",
        "SIN_RELEVAR": "Sin relevar",
        "RELEVADO": "Relevado",
        "PENDIENTE_DE_SOLICITUD": "Pendiente de solicitud",
        "EN_PROCESO_DE_COMPRA": "En proceso de compra",
        "MATERIAL_RECIBIDO": "Material recibido",
        "INSTALACION_PROGRAMADA": "Instalacion programada",
        "COMPLETO": "Completo",
        "MANTENIMIENTO": "Mantenimiento",
    }
    SST_CARTELERIA_PURCHASE_STATES = {"PENDIENTE_SOLICITUD", "COMPRA_EN_PROCESO"}
    SST_LUCES_PURCHASE_STATES = {"EN_PROCESO_DE_COMPRA"}
    SST_CARTELERIA_PENDING_STATES = {
        "NO_RELEVADO",
        "RELEVADO",
        "PENDIENTE_SOLICITUD",
        "COMPRA_EN_PROCESO",
        "MATERIAL_RECIBIDO",
        "INSTALACION_PROGRAMADA",
    }
    SST_LUCES_PENDING_STATES = {
        "SIN_RELEVAR",
        "PENDIENTE_DE_SOLICITUD",
        "EN_PROCESO_DE_COMPRA",
        "MATERIAL_RECIBIDO",
        "INSTALACION_PROGRAMADA",
        "MANTENIMIENTO",
    }
    SST_MANUAL_CARTELERIA_STATES = set(SST_CARTELERIA_STATE_LABELS.keys())
    SST_MANUAL_LUCES_STATES = set(SST_LUCES_STATE_LABELS.keys())
    SST_LUCES_FORM_STATE_LABELS = {key: value for key, value in SST_LUCES_STATE_LABELS.items()}
    SST_CARTELERIA_PLACEHOLDER_PISO = "SEDE"
    SST_CARTELERIA_PLACEHOLDER_DEPOSITO = "SEDE"
    SST_CARTELERIA_PLAN_PREFIX = "[[SGSST_CARTELERIA_PLANO_V1]]"
    SST_LUCES_PLACEHOLDER_PISO = "SEDE"
    SST_LUCES_PLACEHOLDER_DEPOSITO = "SEDE"
    SST_LUCES_PLAN_PREFIX = "[[SGSST_LUCES_PLANO_V1]]"
    SST_LUCES_INITIAL_LOAD = [
        {"sede_codigo": "S01", "aplica": 1, "cantidad_requerida": 8, "motivo_no_aplica": ""},
        {"sede_codigo": "S02", "aplica": 0, "cantidad_requerida": 0, "motivo_no_aplica": "Dentro del Poder Judicial"},
        {"sede_codigo": "S03", "aplica": 1, "cantidad_requerida": 2, "motivo_no_aplica": ""},
        {"sede_codigo": "S04", "aplica": 1, "cantidad_requerida": 1, "motivo_no_aplica": ""},
        {"sede_codigo": "S05", "aplica": 1, "cantidad_requerida": 2, "motivo_no_aplica": ""},
        {"sede_codigo": "S06", "aplica": 1, "cantidad_requerida": 4, "motivo_no_aplica": ""},
        {"sede_codigo": "S07", "aplica": 1, "cantidad_requerida": 1, "motivo_no_aplica": ""},
        {"sede_codigo": "S08", "aplica": 1, "cantidad_requerida": 4, "motivo_no_aplica": ""},
        {"sede_codigo": "S10", "aplica": 1, "cantidad_requerida": 2, "motivo_no_aplica": ""},
        {"sede_codigo": "S11", "aplica": 1, "cantidad_requerida": 8, "motivo_no_aplica": ""},
        {"sede_codigo": "S12", "aplica": 1, "cantidad_requerida": 4, "motivo_no_aplica": ""},
        {"sede_codigo": "S13", "aplica": 1, "cantidad_requerida": 4, "motivo_no_aplica": ""},
        {"sede_codigo": "S14", "aplica": 1, "cantidad_requerida": 3, "motivo_no_aplica": ""},
        {"sede_codigo": "S15", "aplica": 1, "cantidad_requerida": 1, "motivo_no_aplica": ""},
        {"sede_codigo": "S16", "aplica": 1, "cantidad_requerida": 2, "motivo_no_aplica": ""},
        {"sede_codigo": "S17", "aplica": 0, "cantidad_requerida": 0, "motivo_no_aplica": "Dentro del Poder Judicial"},
        {"sede_codigo": "S18", "aplica": 1, "cantidad_requerida": 2, "motivo_no_aplica": ""},
        {"sede_codigo": "S19", "aplica": 0, "cantidad_requerida": 0, "motivo_no_aplica": "Dentro del Poder Judicial"},
        {"sede_codigo": "S20", "aplica": 1, "cantidad_requerida": 5, "motivo_no_aplica": ""},
    ]

    def _sst_current_user():
        return (
            (session.get("full_name") or "").strip()
            or (session.get("username") or "").strip()
            or "sistema"
        )

    def _sst_now_ts():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _sst_clean_upper(value, fallback=""):
        return (str(value or fallback).strip().upper() or fallback).strip().upper()

    def _sst_int_nonneg(value):
        try:
            return max(int(value or 0), 0)
        except Exception:
            return 0

    def _sst_bool_flag(value):
        return 1 if str(value or "").strip().lower() in {"1", "true", "on", "si", "yes"} else 0

    def _sst_state_badge(state_code, state_labels):
        code = _sst_clean_upper(state_code)
        label = state_labels.get(code, code.replace("_", " ").title() if code else "-")
        if code in {
            "VERIFICADO", "VERIFICADA", "OPERATIVA", "RELEVADO_SIN_FALTANTES",
            "COMPLETO_OPERATIVO", "COMPLETO", "COMPLETA", "RELEVADO", "VISITADA", "CERRADA",
            "CARGADO", "SIN_OBSERVACIONES", "EJECUTADO",
        }:
            badge = "correcto"
        elif code in {
            "OBSERVADO", "OBSERVADA", "FUERA_DE_SERVICIO", "FALTA_EQUIPO", "FALTAN_EQUIPOS",
            "REQUIERE_REPARACION", "REQUIERE_REEMPLAZO", "FALTA_SOLICITAR",
            "REQUIERE_MANTENIMIENTO", "MANTENIMIENTO", "FALTANTE", "INCOMPLETA",
        }:
            badge = "atencion"
        elif code in {"NO_RELEVADO", "NO_APLICA", "SIN_RELEVAR", "SIN_VISITA", "SIN_DOCUMENTACION", "SIN_DATOS"}:
            badge = "sin-dato"
        else:
            badge = "pendiente"
        return {"code": code, "label": label, "class": badge}

    def ensure_sst_operativo_historial_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_operativo_historial(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                componente TEXT NOT NULL,
                origen_id INTEGER,
                sede_codigo TEXT,
                deposito_codigo TEXT,
                accion TEXT NOT NULL,
                detalle TEXT,
                usuario TEXT,
                fecha_evento TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_historial_componente_fecha ON sst_operativo_historial(componente, fecha_evento DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_historial_sede ON sst_operativo_historial(sede_codigo, deposito_codigo)")
        con.commit()

    def ensure_sst_carteleria_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_carteleria_tipos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo TEXT NOT NULL,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                orden INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                creado_en TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_carteleria_registros(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                piso TEXT DEFAULT 'SEDE',
                deposito_codigo TEXT NOT NULL DEFAULT 'SEDE',
                tipo_id INTEGER NOT NULL,
                cantidad_requerida INTEGER DEFAULT 0,
                cantidad_instalada INTEGER DEFAULT 0,
                estado TEXT,
                fecha_relevamiento TEXT,
                responsable_relevamiento TEXT,
                fecha_pedido TEXT,
                numero_pedido TEXT,
                fecha_disponibilidad TEXT,
                fecha_programada_colocacion TEXT,
                fecha_colocacion TEXT,
                fecha_verificacion TEXT,
                observaciones TEXT,
                seguimiento_id INTEGER,
                activo INTEGER DEFAULT 1,
                creado_por TEXT,
                actualizado_por TEXT,
                fecha_creacion TEXT DEFAULT (datetime('now')),
                fecha_actualizacion TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(tipo_id) REFERENCES sst_carteleria_tipos(id),
                FOREIGN KEY(seguimiento_id) REFERENCES sst_general(id)
            )
        """)
        ensure_cols(con, "sst_carteleria_registros", [
            ("piso", "TEXT"),
            ("aplica", "TEXT"),
            ("estado", "TEXT"),
            ("fecha_relevamiento", "TEXT"),
            ("responsable_relevamiento", "TEXT"),
            ("fecha_pedido", "TEXT"),
            ("numero_pedido", "TEXT"),
            ("fecha_disponibilidad", "TEXT"),
            ("fecha_programada_colocacion", "TEXT"),
            ("fecha_colocacion", "TEXT"),
            ("fecha_verificacion", "TEXT"),
            ("observaciones", "TEXT"),
            ("seguimiento_id", "INTEGER"),
            ("activo", "INTEGER DEFAULT 1"),
            ("creado_por", "TEXT"),
            ("actualizado_por", "TEXT"),
            ("fecha_creacion", "TEXT DEFAULT (datetime('now'))"),
            ("fecha_actualizacion", "TEXT DEFAULT (datetime('now'))"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_carteleria_sede_dep ON sst_carteleria_registros(sede_codigo, deposito_codigo, piso)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_carteleria_estado ON sst_carteleria_registros(estado, activo)")
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sst_carteleria_unique_active
            ON sst_carteleria_registros(sede_codigo, piso, deposito_codigo, tipo_id)
            WHERE activo = 1
        """)
        for grupo, codigo, nombre, orden in SST_CARTELERIA_TIPOS_SEED:
            con.execute("""
                INSERT INTO sst_carteleria_tipos(grupo, codigo, nombre, orden, activo)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(codigo) DO UPDATE SET
                    grupo = excluded.grupo,
                    nombre = excluded.nombre,
                    orden = excluded.orden
            """, (grupo, codigo, nombre, orden))
        con.commit()

    def ensure_sst_luces_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_luces_registros(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                piso TEXT DEFAULT 'SEDE',
                deposito_codigo TEXT NOT NULL DEFAULT 'SEDE',
                aplica INTEGER DEFAULT 1,
                motivo_no_aplica TEXT,
                cantidad_requerida INTEGER DEFAULT 0,
                cantidad_instalada INTEGER DEFAULT 0,
                cantidad_operativa INTEGER DEFAULT 0,
                cantidad_fuera_servicio INTEGER DEFAULT 0,
                marca TEXT,
                modelo TEXT,
                tipo_equipo TEXT,
                bateria TEXT,
                estado TEXT,
                fecha_relevamiento TEXT,
                fecha_ultima_prueba TEXT,
                resultado_ultima_prueba TEXT,
                fecha_proxima_prueba TEXT,
                requiere_bateria INTEGER DEFAULT 0,
                requiere_reemplazo INTEGER DEFAULT 0,
                fecha_solicitud_compra TEXT,
                fecha_pedido TEXT,
                referencia_pedido TEXT,
                numero_pedido TEXT,
                fecha_entrega TEXT,
                fecha_disponibilidad TEXT,
                fecha_programada_colocacion TEXT,
                fecha_intervencion_programada TEXT,
                fecha_programada_intervencion TEXT,
                fecha_colocacion TEXT,
                fecha_intervencion_realizada TEXT,
                fecha_intervencion TEXT,
                fecha_mantenimiento TEXT,
                fecha_verificacion TEXT,
                observaciones TEXT,
                seguimiento_id INTEGER,
                activo INTEGER DEFAULT 1,
                creado_por TEXT,
                actualizado_por TEXT,
                fecha_creacion TEXT DEFAULT (datetime('now')),
                fecha_actualizacion TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(seguimiento_id) REFERENCES sst_general(id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_luces_pruebas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registro_id INTEGER NOT NULL,
                fecha_prueba TEXT NOT NULL,
                resultado TEXT,
                fecha_proxima_prueba TEXT,
                observaciones TEXT,
                creado_por TEXT,
                creado_en TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(registro_id) REFERENCES sst_luces_registros(id)
            )
        """)
        ensure_cols(con, "sst_luces_registros", [
            ("piso", "TEXT"),
            ("aplica", "INTEGER DEFAULT 1"),
            ("motivo_no_aplica", "TEXT"),
            ("cantidad_operativa", "INTEGER DEFAULT 0"),
            ("cantidad_fuera_servicio", "INTEGER DEFAULT 0"),
            ("marca", "TEXT"),
            ("modelo", "TEXT"),
            ("tipo_equipo", "TEXT"),
            ("bateria", "TEXT"),
            ("estado", "TEXT"),
            ("fecha_relevamiento", "TEXT"),
            ("fecha_ultima_prueba", "TEXT"),
            ("resultado_ultima_prueba", "TEXT"),
            ("fecha_proxima_prueba", "TEXT"),
            ("requiere_bateria", "INTEGER DEFAULT 0"),
            ("requiere_reemplazo", "INTEGER DEFAULT 0"),
            ("fecha_solicitud_compra", "TEXT"),
            ("fecha_pedido", "TEXT"),
            ("referencia_pedido", "TEXT"),
            ("numero_pedido", "TEXT"),
            ("fecha_entrega", "TEXT"),
            ("fecha_disponibilidad", "TEXT"),
            ("fecha_programada_colocacion", "TEXT"),
            ("fecha_intervencion_programada", "TEXT"),
            ("fecha_programada_intervencion", "TEXT"),
            ("fecha_colocacion", "TEXT"),
            ("fecha_intervencion_realizada", "TEXT"),
            ("fecha_intervencion", "TEXT"),
            ("fecha_mantenimiento", "TEXT"),
            ("fecha_verificacion", "TEXT"),
            ("observaciones", "TEXT"),
            ("seguimiento_id", "INTEGER"),
            ("activo", "INTEGER DEFAULT 1"),
            ("creado_por", "TEXT"),
            ("actualizado_por", "TEXT"),
            ("fecha_creacion", "TEXT DEFAULT (datetime('now'))"),
            ("fecha_actualizacion", "TEXT DEFAULT (datetime('now'))"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_luces_sede_dep ON sst_luces_registros(sede_codigo, deposito_codigo, piso)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_luces_sede ON sst_luces_registros(sede_codigo, activo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_luces_estado ON sst_luces_registros(estado, activo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_luces_pruebas_registro ON sst_luces_pruebas(registro_id, fecha_prueba DESC)")
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sst_luces_unique_active
            ON sst_luces_registros(sede_codigo, piso, deposito_codigo)
            WHERE activo = 1
        """)
        con.commit()

    def _sst_historial_log(con, componente, accion, origen_id=None, sede_codigo="", deposito_codigo="", detalle=""):
        ensure_sst_operativo_historial_tables(con)
        con.execute("""
            INSERT INTO sst_operativo_historial(
                componente, origen_id, sede_codigo, deposito_codigo,
                accion, detalle, usuario, fecha_evento
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            (componente or "").strip().lower(),
            origen_id,
            (_sst_clean_upper(sede_codigo) or None),
            (_sst_clean_upper(deposito_codigo) or None),
            (accion or "").strip(),
            (detalle or "").strip(),
            _sst_current_user(),
            _sst_now_ts(),
        ))

    def ensure_sst_visitas_docs_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_visitas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                fecha TEXT NOT NULL,
                tipo_visita TEXT,
                responsable TEXT,
                estado TEXT,
                observaciones TEXT,
                creado_en TEXT DEFAULT (datetime('now'))
            )
        """)
        ensure_cols(con, "sst_visitas", [
            ("observacion_art", "TEXT"),
            ("accion_requerida", "TEXT"),
            ("accion_responsable", "TEXT"),
            ("fecha_programada", "TEXT"),
            ("ejecutado", "INTEGER DEFAULT 0"),
            ("fecha_ejecucion", "TEXT"),
            ("evidencia_url", "TEXT"),
            ("seguimiento_id", "INTEGER"),
            ("actualizado_por", "TEXT"),
            ("fecha_actualizacion", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_documentos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                visita_id INTEGER,
                tipo TEXT NOT NULL,
                fecha_documento TEXT,
                fecha_carga TEXT DEFAULT (date('now')),
                archivo TEXT,
                drive_url TEXT,
                estado_revision TEXT,
                notas TEXT,
                creado_en TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(visita_id) REFERENCES sst_visitas(id)
            )
        """)
        ensure_cols(con, "sst_documentos", [
            ("actualizado_por", "TEXT"),
            ("fecha_actualizacion", "TEXT"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_visitas_sede_fecha ON sst_visitas(sede_codigo, fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_documentos_sede_tipo ON sst_documentos(sede_codigo, tipo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sst_documentos_visita ON sst_documentos(visita_id)")
        con.commit()

    def ensure_sst_plan_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_objetivos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT,
                codigo TEXT,
                titulo TEXT NOT NULL,
                horizonte_meses INTEGER,
                descripcion TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                estado TEXT,
                prioridad TEXT,
                creado_en TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_objetivo_acciones(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                objetivo_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                fase TEXT,
                responsable_area TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                estado TEXT,
                indicador TEXT,
                clasificacion TEXT,
                justificacion TEXT,
                avance_pct INTEGER,
                evidencia_url TEXT,
                notas TEXT,
                orden INTEGER DEFAULT 0,
                creado_en TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(objetivo_id) REFERENCES sst_objetivos(id)
            )
        """)
        ensure_cols(con, "sst_objetivo_acciones", [
            ("fase", "TEXT"),
            ("indicador", "TEXT"),
            ("clasificacion", "TEXT"),
            ("justificacion", "TEXT"),
            ("avance_pct", "INTEGER"),
        ])
        con.commit()

    def ensure_sgsst_implementation_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_marco(
                id INTEGER PRIMARY KEY CHECK (id = 1),
                objetivo TEXT,
                alcance TEXT,
                metodologia TEXT,
                criterios TEXT,
                prioridades TEXT,
                estado_plan TEXT DEFAULT 'EN_ELABORACION',
                aprobado INTEGER DEFAULT 0,
                responsable_general TEXT,
                fecha_inicio TEXT,
                fecha_actualizacion TEXT,
                observaciones TEXT
            )
        """)
        ensure_cols(con, "sgsst_plan_marco", [
            ("objetivo", "TEXT"),
            ("alcance", "TEXT"),
            ("metodologia", "TEXT"),
            ("criterios", "TEXT"),
            ("prioridades", "TEXT"),
            ("estado_plan", "TEXT DEFAULT 'EN_ELABORACION'"),
            ("aprobado", "INTEGER DEFAULT 0"),
            ("responsable_general", "TEXT"),
            ("fecha_inicio", "TEXT"),
            ("fecha_actualizacion", "TEXT"),
            ("observaciones", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_hallazgos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                piso TEXT,
                dependencia TEXT,
                modulo_origen TEXT,
                registro_origen_id TEXT,
                categoria TEXT,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                fecha_deteccion TEXT,
                detectado_por TEXT,
                fuente TEXT,
                prioridad TEXT DEFAULT 'Media',
                estado TEXT DEFAULT 'Detectado',
                evidencia_inicial TEXT,
                observaciones TEXT,
                fecha_cierre TEXT,
                cerrado_por TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT
            )
        """)
        ensure_cols(con, "sgsst_plan_hallazgos", [
            ("piso", "TEXT"),
            ("dependencia", "TEXT"),
            ("modulo_origen", "TEXT"),
            ("registro_origen_id", "TEXT"),
            ("categoria", "TEXT"),
            ("descripcion", "TEXT"),
            ("fecha_deteccion", "TEXT"),
            ("detectado_por", "TEXT"),
            ("fuente", "TEXT"),
            ("prioridad", "TEXT DEFAULT 'Media'"),
            ("estado", "TEXT DEFAULT 'Detectado'"),
            ("evidencia_inicial", "TEXT"),
            ("observaciones", "TEXT"),
            ("fecha_cierre", "TEXT"),
            ("cerrado_por", "TEXT"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("updated_at", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_acciones(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hallazgo_id INTEGER,
                sede_codigo TEXT NOT NULL,
                modulo_origen TEXT,
                titulo TEXT NOT NULL,
                accion_requerida TEXT,
                responsable TEXT,
                area_responsable TEXT,
                prioridad TEXT DEFAULT 'Media',
                fecha_creacion TEXT,
                fecha_objetivo TEXT,
                estado TEXT DEFAULT 'Pendiente',
                avance_pct INTEGER,
                evidencia TEXT,
                costo_estimado REAL,
                compra_requerida INTEGER DEFAULT 0,
                intervencion_requerida INTEGER DEFAULT 0,
                observaciones TEXT,
                fecha_cierre TEXT,
                cerrado_por TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT,
                FOREIGN KEY(hallazgo_id) REFERENCES sgsst_plan_hallazgos(id)
            )
        """)
        ensure_cols(con, "sgsst_plan_acciones", [
            ("hallazgo_id", "INTEGER"),
            ("modulo_origen", "TEXT"),
            ("accion_requerida", "TEXT"),
            ("responsable", "TEXT"),
            ("area_responsable", "TEXT"),
            ("prioridad", "TEXT DEFAULT 'Media'"),
            ("fecha_creacion", "TEXT"),
            ("fecha_objetivo", "TEXT"),
            ("estado", "TEXT DEFAULT 'Pendiente'"),
            ("avance_pct", "INTEGER"),
            ("evidencia", "TEXT"),
            ("costo_estimado", "REAL"),
            ("compra_requerida", "INTEGER DEFAULT 0"),
            ("intervencion_requerida", "INTEGER DEFAULT 0"),
            ("observaciones", "TEXT"),
            ("fecha_cierre", "TEXT"),
            ("cerrado_por", "TEXT"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("updated_at", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_evidencias(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                accion_id INTEGER NOT NULL,
                tipo TEXT,
                descripcion TEXT,
                archivo_url TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                created_by TEXT,
                FOREIGN KEY(accion_id) REFERENCES sgsst_plan_acciones(id)
            )
        """)
        ensure_cols(con, "sgsst_plan_evidencias", [
            ("tipo", "TEXT"),
            ("descripcion", "TEXT"),
            ("archivo_url", "TEXT"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("created_by", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_document_links(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                bloque_codigo TEXT,
                documento_codigo TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        ensure_cols(con, "sgsst_plan_document_links", [
            ("entity_type", "TEXT"),
            ("entity_id", "INTEGER"),
            ("bloque_codigo", "TEXT"),
            ("documento_codigo", "TEXT"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_plan_roles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo TEXT NOT NULL,
                rol TEXT NOT NULL,
                referente TEXT,
                activo INTEGER DEFAULT 1,
                orden_visual INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT
            )
        """)
        ensure_cols(con, "sgsst_plan_roles", [
            ("grupo", "TEXT"),
            ("rol", "TEXT"),
            ("referente", "TEXT"),
            ("activo", "INTEGER DEFAULT 1"),
            ("orden_visual", "INTEGER DEFAULT 0"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("updated_at", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_command_projects(
                project_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                responsable TEXT,
                frecuencia TEXT,
                periodicidad TEXT,
                reglas TEXT,
                activo INTEGER DEFAULT 1,
                orden_visual INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT
            )
        """)
        ensure_cols(con, "sgsst_command_projects", [
            ("label", "TEXT"),
            ("responsable", "TEXT"),
            ("frecuencia", "TEXT"),
            ("periodicidad", "TEXT"),
            ("reglas", "TEXT"),
            ("activo", "INTEGER DEFAULT 1"),
            ("orden_visual", "INTEGER DEFAULT 0"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("updated_at", "TEXT"),
        ])
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_command_project_scope(
                project_key TEXT NOT NULL,
                sede_codigo TEXT NOT NULL,
                scope_state TEXT DEFAULT 'AUTO',
                note TEXT,
                updated_at TEXT,
                PRIMARY KEY(project_key, sede_codigo),
                FOREIGN KEY(project_key) REFERENCES sgsst_command_projects(project_key)
            )
        """)
        ensure_cols(con, "sgsst_command_project_scope", [
            ("project_key", "TEXT"),
            ("sede_codigo", "TEXT"),
            ("scope_state", "TEXT DEFAULT 'AUTO'"),
            ("note", "TEXT"),
            ("updated_at", "TEXT"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_plan_hallazgos_sede ON sgsst_plan_hallazgos(sede_codigo, estado)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_plan_acciones_sede ON sgsst_plan_acciones(sede_codigo, estado)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_plan_acciones_hallazgo ON sgsst_plan_acciones(hallazgo_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_plan_roles_grupo ON sgsst_plan_roles(grupo, activo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_command_scope_project ON sgsst_command_project_scope(project_key, scope_state)")

        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_plan_marco").fetchone()
        if int((row["n"] if row else 0) or 0) == 0:
            now = _sst_now_ts()
            con.execute("""
                INSERT INTO sgsst_plan_marco(
                    id, objetivo, alcance, metodologia, criterios, prioridades,
                    estado_plan, aprobado, responsable_general, fecha_inicio, fecha_actualizacion, observaciones
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "Implementar el SG-SST en forma progresiva, integrada al SGI y orientada a la operacion real de las sedes.",
                "Sedes, dependencias, modulos operativos SG-SST, biblioteca documental y seguimiento institucional del MPD.",
                "Diagnostico por sede, definicion de hallazgos, acciones verificables y control periodico sostenido.",
                "No duplicar modulos, usar datos existentes, crear trazabilidad minima y priorizar regularizacion real.",
                "Primero base documental y diagnostico; luego acciones, compras, colocacion, verificacion y control.",
                "EN_ELABORACION",
                0,
                "Intendencia / Responsable SG-SST",
                date.today().isoformat(),
                now,
                "Primera capa institucional creada sobre los modulos existentes del SGI.",
            ))

        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_plan_roles").fetchone()
        if int((row["n"] if row else 0) or 0) == 0:
            now = _sst_now_ts()
            for seed in SGSST_PLAN_ROLE_SEED:
                con.execute("""
                    INSERT INTO sgsst_plan_roles(
                        grupo, rol, referente, activo, orden_visual, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?)
                """, (
                    seed["grupo"],
                    seed["rol"],
                    "",
                    int(seed.get("orden_visual") or 0),
                    now,
                    now,
                ))
        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_command_projects").fetchone()
        if int((row["n"] if row else 0) or 0) == 0:
            now = _sst_now_ts()
            for idx, seed in enumerate(_sgsst_command_project_catalog(), start=1):
                con.execute("""
                    INSERT INTO sgsst_command_projects(
                        project_key, label, responsable, frecuencia, periodicidad, reglas,
                        activo, orden_visual, created_at, updated_at
                    ) VALUES (?, ?, ?, '', '', '', 1, ?, ?, ?)
                """, (
                    seed["key"],
                    seed["label"],
                    seed["fallback_responsible"],
                    idx * 10,
                    now,
                    now,
                ))
        con.commit()


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

    def ensure_documentos_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos(
                id_documento INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                tipo_documento TEXT NOT NULL DEFAULT 'documento_general',
                descripcion TEXT,
                fecha TEXT,
                autor TEXT,
                archivo_url TEXT,
                estado TEXT NOT NULL DEFAULT 'borrador',
                creado_en TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_sedes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                sede_codigo TEXT NOT NULL,
                UNIQUE(id_documento, sede_codigo)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_agentes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                id_agente INTEGER NOT NULL,
                UNIQUE(id_documento, id_agente)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_vehiculos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                patente TEXT NOT NULL,
                UNIQUE(id_documento, patente)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_sst(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                tipo_evento TEXT,
                id_evento INTEGER,
                UNIQUE(id_documento, tipo_evento, id_evento)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_tags(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                tag TEXT NOT NULL,
                UNIQUE(id_documento, tag)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS documentos_destino(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_documento INTEGER NOT NULL,
                destino TEXT NOT NULL,
                UNIQUE(id_documento, destino)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_documentos_tipo_estado ON documentos(tipo_documento, estado)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_documentos_fecha ON documentos(fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doc_sedes_sede ON documentos_sedes(sede_codigo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doc_agentes_agente ON documentos_agentes(id_agente)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doc_vehiculos_patente ON documentos_vehiculos(patente)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doc_tags_tag ON documentos_tags(tag)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doc_destino_dest ON documentos_destino(destino)")
        con.commit()

    # ============================================================
    # SG-SST - Bloque documental interno (sin Drive)
    # ============================================================

    SGSST_BLOQUES_VALIDOS = [
        "politica",
        "plan_accion",
        "roles",
        "protocolos",
        "instructivos",
        "riesgos",
    ]

    SGSST_DOCS_SEED = [
        {
            "codigo": "SGSST-POL-01",
            "bloque": "politica",
            "orden_visual": 1,
            "titulo": "Política de gestión de intendencia y seguridad y salud en el trabajo",
            "subtitulo": "Declaración de compromiso institucional",
            "descripcion_corta": "Marco general de compromiso, principios, alcance, responsabilidades y mejora continua del SGI + SG-SST.",
            "contenido": "\n".join([
                "POLÍTICA DE GESTIÓN DE INTENDENCIA Y SEGURIDAD Y SALUD EN EL TRABAJO (SGI + SG-SST)",
                "",
                "1) Declaración de compromiso",
                "La Administración General y el Área de Intendencia del MPD asumen el compromiso de proteger la integridad psicofísica del personal y de promover condiciones de trabajo seguras y saludables en todas sus sedes.",
                "",
                "2) Propósito",
                "Establecer el marco institucional para gestionar la prevención, la identificación y control de riesgos laborales, el cumplimiento normativo aplicable y la mejora continua del desempeño en Seguridad y Salud en el Trabajo (SG-SST), integrado al Sistema de Gestión de Intendencia (SGI).",
                "",
                "3) Alcance",
                "Aplica a las sedes del MPD y a las actividades habituales de Intendencia (mantenimiento, logística, traslados, limpieza, soporte operativo, relevamientos y controles asociados).",
                "",
                "4) Marco general",
                "El SG-SST se implementa como un componente integrado al SGI: se planifica, ejecuta, registra y hace seguimiento dentro de la operatoria habitual, sin generar estructuras paralelas ni operativos exclusivos.",
                "",
                "5) Principios de gestión",
                "- Prevención como criterio rector.",
                "- Cumplimiento de requisitos legales y otros requisitos aplicables.",
                "- Participación del personal y consulta permanente.",
                "- Registro, evidencia y trazabilidad en el sistema.",
                "- Priorización por criticidad y mejora progresiva por sede.",
                "- Revisión periódica y mejora continua.",
                "",
                "6) Objetivos generales",
                "- Identificar peligros y evaluar riesgos, con prioridad ergonómica.",
                "- Estandarizar controles (protocolos) e instructivos de carga y registro.",
                "- Reducir incidentes, no conformidades y condiciones inseguras.",
                "- Fortalecer la comunicación interna y la cultura preventiva.",
                "",
                "7) Responsabilidades",
                "- Alta Dirección / Administración General: definir lineamientos, asignar recursos y revisar el desempeño del sistema.",
                "- Intendencia: planificar, ejecutar y registrar acciones SG-SST dentro de las tareas habituales.",
                "- Responsables técnicos SG-SST: asesorar, relevar, proponer medidas y verificar evidencias/cierres.",
                "- Personal operativo y de apoyo: colaborar, cumplir procedimientos, utilizar EPP cuando aplique y reportar desvíos.",
                "",
                "8) Comunicación",
                "Se garantizará la comunicación interna de la política, los riesgos relevantes, los protocolos/instructivos vigentes y las medidas preventivas mediante canales institucionales y registros trazables en el sistema.",
                "",
                "9) Revisión y mejora continua",
                "La política y documentos asociados se revisarán periódicamente y ante cambios significativos (sedes, procesos, incidentes o normativa), actualizando objetivos, acciones y controles para asegurar la mejora continua del SGI + SG-SST.",
            ]),
        },
        {
            "codigo": "SGSST-PLA-01",
            "bloque": "plan_accion",
            "orden_visual": 2,
            "titulo": "Plan de acción e implementación",
            "subtitulo": "Implementación progresiva del SG-SST integrada al SGI",
            "descripcion_corta": "Plan operativo para implementar el SG-SST en las sedes del MPD.",
            "contenido": "\n".join([
                "PLAN DE ACCIÓN E IMPLEMENTACIÓN (SG-SST INTEGRADO AL SGI)",
                "",
                "1) Objetivo",
                "Implementar el SG-SST de manera progresiva e integrada al SGI, incorporando controles, registros y seguimiento dentro de las tareas habituales de Intendencia.",
                "",
                "2) Alcance",
                "Aplica a sedes del MPD y a procesos operativos (mantenimiento, logística, limpieza, traslados, relevamientos, control de condiciones y seguimiento de desvíos).",
                "",
                "3) Modalidad de implementación (integración al SGI)",
                "- No genera operativos exclusivos: se ejecuta en el marco de la operatoria habitual.",
                "- Acompaña recorridas y controles existentes de Intendencia, agregando criterios preventivos y trazabilidad.",
                "- Integra evidencias y resultados en el sistema (registro unificado).",
                "",
                "4) Relevamiento inicial",
                "- Diagnóstico por sede y proceso (condiciones generales, instalaciones, seguridad contra incendios, sanitarios, señalización, orden y limpieza).",
                "- Relevamiento ergonómico y condiciones del puesto de trabajo (prioridad).",
                "",
                "5) Detección de desvíos",
                "- Registro de hallazgos, incidentes y no conformidades.",
                "- Clasificación por criticidad y definición de responsables/plazos.",
                "",
                "6) Gestión de riesgos",
                "- Identificación de peligros y evaluación inicial.",
                "- Definición de controles preventivos/correctivos y criterios de verificación.",
                "",
                "7) Acciones preventivas",
                "- Controles periódicos según protocolos vigentes.",
                "- Entrega y control de EPP cuando corresponda.",
                "- Comunicación interna de medidas y criterios preventivos.",
                "",
                "8) Planificación operativa",
                "- Cronograma macro por sede (etapas) y planificación mensual/semanal según agenda real de Intendencia.",
                "- Priorización por criticidad y factibilidad operativa.",
                "",
                "9) Seguimiento",
                "- Registro de avances, evidencias, verificaciones y cierres.",
                "- Indicadores mínimos: controles realizados, desvíos abiertos/cerrados, incidentes, EPP entregado, hallazgos recurrentes.",
                "",
                "10) Mejora continua",
                "El plan se revisa y ajusta en función de resultados, incidentes, auditorías internas y cambios operativos, asegurando evolución sostenida del SG-SST dentro del SGI.",
            ]),
        },
        {
            "codigo": "SGSST-ROL-01",
            "bloque": "roles",
            "orden_visual": 3,
            "titulo": "Roles y responsabilidades",
            "subtitulo": "Participación del personal del área de Intendencia",
            "descripcion_corta": "Definición de roles operativos, técnicos y apoyo del sistema.",
            "contenido": "\n".join([
                "ROLES Y RESPONSABILIDADES (SGI + SG-SST)",
                "",
                "1) Alta Dirección / Administración General",
                "- Definir lineamientos institucionales del SGI + SG-SST.",
                "- Asegurar recursos para la implementación progresiva (tiempos, insumos, priorizaciones).",
                "- Revisar indicadores y resultados del sistema; impulsar mejora continua.",
                "",
                "2) Administración general (gestión y coordinación)",
                "- Alinear prioridades institucionales con la planificación operativa.",
                "- Facilitar coordinación interáreas cuando se requieran acciones correctivas.",
                "",
                "3) Responsables operativos (Intendencia / procesos)",
                "- Integrar acciones SG-SST al trabajo habitual (sin estructuras paralelas).",
                "- Ejecutar controles/relevamientos según protocolos vigentes.",
                "- Registrar evidencias y resultados en el sistema para trazabilidad.",
                "- Reportar desvíos, incidentes y condiciones inseguras.",
                "",
                "4) Responsables técnicos (SG-SST)",
                "- Asesorar técnicamente y proponer medidas preventivas/correctivas.",
                "- Realizar verificaciones y apoyar la evaluación de riesgos (prioridad ergonómica).",
                "- Verificar cierres y eficacia de acciones implementadas.",
                "",
                "5) Personal de apoyo",
                "- Colaborar en la coordinación de actividades por sede.",
                "- Apoyar carga de registros cuando corresponda y asegurar consistencia documental.",
                "",
                "6) Participación del equipo de Intendencia",
                "- Participar en relevamientos y controles operativos.",
                "- Sostener buenas prácticas (orden, limpieza, señalización, uso de EPP cuando aplique).",
                "",
                "7) Responsabilidades generales (registro, control, colaboración y reporte)",
                "- Registrar: fecha, sede, responsable, hallazgos, evidencia y acciones.",
                "- Controlar: condiciones básicas y cumplimiento de protocolos/instructivos.",
                "- Colaborar: con áreas involucradas para resolver desvíos.",
                "- Reportar: incidentes/no conformidades y oportunidades de mejora.",
            ]),
        },
        {
            "codigo": "SGSST-PRO-01",
            "bloque": "protocolos",
            "orden_visual": 4,
            "titulo": "Protocolos operativos",
            "subtitulo": "Procedimientos básicos del SG-SST",
            "descripcion_corta": "Protocolos operativos aplicables a relevamientos, controles, incidentes, EPP y no conformidades.",
            "contenido": "\n".join([
                "PROTOCOLOS OPERATIVOS (SG-SST INTEGRADO AL SGI)",
                "",
                "Este bloque consolida el conjunto de protocolos operativos específicos del SG-SST, integrados al Sistema de Gestión de Intendencia (SGI).",
                "",
                "Concepto",
                "Los protocolos estandarizan controles y tareas preventivas, definiendo criterios mínimos de registro y evidencia para asegurar consistencia entre sedes.",
                "",
                "Integración al SGI",
                "Las acciones del SG-SST se integran al Sistema de Gestión de Intendencia (SGI), realizándose en el marco de las tareas operativas habituales, sin generar estructuras paralelas ni operativos exclusivos.",
                "",
                "Qué incluye cada protocolo",
                "- Objetivo y alcance.",
                "- Procedimiento mínimo (pasos y criterios).",
                "- Registro asociado y evidencia requerida.",
                "- Frecuencia y responsable.",
                "",
                "Protocolos base (iniciales)",
                "- PROT-SST-01: Relevamiento de sedes.",
                "- PROT-SST-02: Control de matafuegos.",
                "- PROT-SST-03: Control de condiciones eléctricas básicas.",
                "- PROT-SST-04: Control de condiciones sanitarias.",
                "- PROT-SST-05: Entrega y control de EPP.",
                "- PROT-SST-06: Detección y registro de riesgos.",
                "- PROT-SST-07: Gestión de no conformidades.",
                "- PROT-SST-08: Incidentes.",
            ]),
        },
        {
            "codigo": "SGSST-INS-01",
            "bloque": "instructivos",
            "orden_visual": 5,
            "titulo": "Instructivos y documentación",
            "subtitulo": "Documentación de apoyo operativo",
            "descripcion_corta": "Instructivos simples para ejecución, registro y trazabilidad de acciones SG-SST.",
            "contenido": "\n".join([
                "INSTRUCTIVOS Y DOCUMENTACIÓN",
                "",
                "Concepto general",
                "Los instructivos son guías breves, operativas y claras para estandarizar la ejecución y la carga de registros vinculados al SG-SST dentro del SGI.",
                "",
                "Instructivos breves (uso operativo)",
                "- Indican qué cargar, cuándo, con qué criterio y qué evidencia registrar.",
                "- Reducen variabilidad entre sedes y roles, mejorando consistencia documental.",
                "",
                "Vinculación con registros",
                "Cada instructivo se asocia a registros del sistema (relevamientos, incidentes, EPP, no conformidades, acciones preventivas), asegurando que la información quede trazable y verificable.",
                "",
                "Trazabilidad en el sistema",
                "El sistema permite seguimiento de avances, control de cumplimiento y trazabilidad histórica por sede, fecha y responsable.",
            ]),
        },
        {
            "codigo": "SGSST-RIE-01",
            "bloque": "riesgos",
            "orden_visual": 6,
            "titulo": "Proceso de gestión de riesgos",
            "subtitulo": "Identificación, evaluación y seguimiento de riesgos",
            "descripcion_corta": "Proceso base para gestión de riesgos, con prioridad ergonómica y enfoque preventivo.",
            "contenido": "\n".join([
                "PROCESO DE GESTIÓN DE RIESGOS",
                "",
                "1) Concepto general de riesgo laboral",
                "El riesgo laboral combina probabilidad y severidad. Se gestiona identificando peligros, evaluando criticidad y aplicando controles preventivos/correctivos verificables.",
                "",
                "2) Prioridad ergonómica",
                "Se priorizan riesgos ergonómicos por su impacto y recurrencia (adecuación de puestos, posturas, movimientos repetitivos, carga física y pausas).",
                "",
                "3) Identificación de peligros",
                "- Relevamientos por sede y proceso.",
                "- Observación directa y consulta al personal.",
                "- Análisis de incidentes y no conformidades.",
                "",
                "4) Evaluación inicial",
                "- Valoración de criticidad (probabilidad/severidad) y definición de prioridades.",
                "- Identificación de controles existentes y brechas.",
                "",
                "5) Medidas preventivas y correctivas",
                "- Eliminación/sustitución cuando sea posible.",
                "- Controles de ingeniería y administrativos.",
                "- Señalización, orden y limpieza, mantenimiento preventivo.",
                "- EPP como última barrera cuando aplique.",
                "",
                "6) Seguimiento",
                "- Registro de acciones, responsables, plazos y evidencias.",
                "- Verificación de eficacia y cierre documentado.",
                "",
                "7) Mejora continua",
                "La gestión de riesgos se revisa periódicamente y ante cambios (obras, mudanzas, incidentes, normativa), actualizando criterios y priorizaciones.",
            ]),
        },
    ]

    SGSST_PROTOCOLOS_BASE = [
        {"codigo": "PROT-SST-01", "titulo": "Protocolo de relevamiento de sedes", "categoria": "Relevamientos", "orden": 1},
        {"codigo": "PROT-SST-02", "titulo": "Protocolo de control de matafuegos", "categoria": "Seguridad contra incendios", "orden": 2},
        {"codigo": "PROT-SST-03", "titulo": "Protocolo de control de condiciones eléctricas básicas", "categoria": "Instalaciones", "orden": 3},
        {"codigo": "PROT-SST-04", "titulo": "Protocolo de control de condiciones sanitarias", "categoria": "Condiciones generales", "orden": 4},
        {"codigo": "PROT-SST-05", "titulo": "Protocolo de entrega y control de EPP", "categoria": "EPP", "orden": 5},
        {"codigo": "PROT-SST-06", "titulo": "Protocolo de detección y registro de riesgos", "categoria": "Gestión de riesgos", "orden": 6},
        {"codigo": "PROT-SST-07", "titulo": "Protocolo de gestión de no conformidades", "categoria": "No conformidades", "orden": 7},
        {"codigo": "PROT-SST-08", "titulo": "Protocolo de incidentes", "categoria": "Incidentes", "orden": 8},
    ]

    SGSST_INSTRUCTIVOS_BASE = [
        {"codigo": "INS-SST-01", "titulo": "Instructivo de carga de relevamientos de sede", "categoria": "Relevamientos", "orden": 1},
        {"codigo": "INS-SST-02", "titulo": "Instructivo de registro de incidentes", "categoria": "Incidentes", "orden": 2},
        {"codigo": "INS-SST-03", "titulo": "Instructivo de carga de entrega de EPP", "categoria": "EPP", "orden": 3},
        {"codigo": "INS-SST-04", "titulo": "Instructivo de registro de no conformidades", "categoria": "No conformidades", "orden": 4},
        {"codigo": "INS-SST-05", "titulo": "Instructivo de seguimiento de acciones preventivas", "categoria": "Seguimiento", "orden": 5},
    ]

    _SGSST_INTEGRACION_SGI_FRASE = (
        "Las acciones del SG-SST se integran al Sistema de Gestión de Intendencia (SGI), "
        "realizándose en el marco de las tareas operativas habituales, sin generar estructuras paralelas "
        "ni operativos exclusivos."
    )

    def _sgsst_now_ts() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def ensure_sgsst_documentacion_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_documentos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                bloque TEXT NOT NULL,
                titulo TEXT NOT NULL,
                subtitulo TEXT,
                descripcion_corta TEXT,
                contenido TEXT,
                estado TEXT DEFAULT 'BORRADOR',
                orden_visual INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_actualizacion TEXT,
                responsable TEXT,
                observaciones TEXT
            )
        """)
        ensure_cols(con, "sgsst_documentos", [
            ("subtitulo", "TEXT"),
            ("descripcion_corta", "TEXT"),
            ("contenido", "TEXT"),
            ("estado", "TEXT DEFAULT 'BORRADOR'"),
            ("orden_visual", "INTEGER DEFAULT 0"),
            ("activo", "INTEGER DEFAULT 1"),
            ("fecha_actualizacion", "TEXT"),
            ("responsable", "TEXT"),
            ("observaciones", "TEXT"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_documentos_bloque ON sgsst_documentos(bloque)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_documentos_activo ON sgsst_documentos(activo)")

        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_protocolos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                titulo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descripcion_corta TEXT,
                objetivo TEXT,
                alcance TEXT,
                procedimiento TEXT,
                registro_asociado TEXT,
                frecuencia TEXT,
                responsable TEXT,
                estado TEXT DEFAULT 'BORRADOR',
                orden_visual INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_actualizacion TEXT,
                integrado_sgi INTEGER DEFAULT 1
            )
        """)
        ensure_cols(con, "sgsst_protocolos", [
            ("descripcion_corta", "TEXT"),
            ("objetivo", "TEXT"),
            ("alcance", "TEXT"),
            ("procedimiento", "TEXT"),
            ("registro_asociado", "TEXT"),
            ("frecuencia", "TEXT"),
            ("responsable", "TEXT"),
            ("estado", "TEXT DEFAULT 'BORRADOR'"),
            ("orden_visual", "INTEGER DEFAULT 0"),
            ("activo", "INTEGER DEFAULT 1"),
            ("fecha_actualizacion", "TEXT"),
            ("integrado_sgi", "INTEGER DEFAULT 1"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_protocolos_categoria ON sgsst_protocolos(categoria)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_protocolos_activo ON sgsst_protocolos(activo)")

        con.execute("""
            CREATE TABLE IF NOT EXISTS sgsst_instructivos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                titulo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descripcion_corta TEXT,
                contenido TEXT,
                uso_aplicable TEXT,
                responsable TEXT,
                estado TEXT DEFAULT 'BORRADOR',
                orden_visual INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_actualizacion TEXT
            )
        """)
        ensure_cols(con, "sgsst_instructivos", [
            ("descripcion_corta", "TEXT"),
            ("contenido", "TEXT"),
            ("uso_aplicable", "TEXT"),
            ("responsable", "TEXT"),
            ("estado", "TEXT DEFAULT 'BORRADOR'"),
            ("orden_visual", "INTEGER DEFAULT 0"),
            ("activo", "INTEGER DEFAULT 1"),
            ("fecha_actualizacion", "TEXT"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_instructivos_categoria ON sgsst_instructivos(categoria)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sgsst_instructivos_activo ON sgsst_instructivos(activo)")
        con.commit()

    def seed_sgsst_documentacion(con):
        ensure_sgsst_documentacion_tables(con)

        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_documentos").fetchone()
        n_docs = int((row["n"] if row else 0) or 0)
        if n_docs == 0:
            now = _sgsst_now_ts()
            for d in SGSST_DOCS_SEED:
                con.execute(
                    """
                    INSERT INTO sgsst_documentos (
                        codigo, bloque, titulo, subtitulo, descripcion_corta, contenido,
                        estado, orden_visual, activo, fecha_actualizacion, responsable, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        d["codigo"],
                        d["bloque"],
                        d["titulo"],
                        d.get("subtitulo"),
                        d.get("descripcion_corta"),
                        d.get("contenido"),
                        "BORRADOR",
                        int(d.get("orden_visual") or 0),
                        1,
                        now,
                        "",
                        "",
                    ),
                )
            con.commit()

        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_protocolos").fetchone()
        n_prot = int((row["n"] if row else 0) or 0)
        if n_prot == 0:
            now = _sgsst_now_ts()
            for p in SGSST_PROTOCOLOS_BASE:
                titulo = p["titulo"]
                objetivo = "\n".join([
                    f"Objetivo: estandarizar y registrar \"{titulo}\".",
                    _SGSST_INTEGRACION_SGI_FRASE,
                ])
                alcance = "Alcance: sedes del MPD y tareas habituales de Intendencia vinculadas al tema."
                procedimiento = "\n".join([
                    "Procedimiento mínimo:",
                    "1. Planificar (sede, fecha, responsable).",
                    "2. Ejecutar el control/relevamiento.",
                    "3. Registrar evidencias y hallazgos.",
                    "4. Definir acciones ante desvíos y hacer seguimiento.",
                    "5. Verificar cierre y documentar.",
                    "",
                    _SGSST_INTEGRACION_SGI_FRASE,
                ])
                registro_asociado = "Registro asociado: carga y evidencia en el sistema (checklist/relevamiento/incidente/no conformidad/acciones)."
                con.execute(
                    """
                    INSERT INTO sgsst_protocolos (
                        codigo, titulo, categoria, descripcion_corta, objetivo, alcance, procedimiento,
                        registro_asociado, frecuencia, responsable, estado, orden_visual, activo,
                        fecha_actualizacion, integrado_sgi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p["codigo"],
                        titulo,
                        p["categoria"],
                        f"Protocolo operativo: {p['categoria']}.",
                        objetivo,
                        alcance,
                        procedimiento,
                        registro_asociado,
                        "Según planificación operativa (mínimo mensual o por criticidad).",
                        "Intendencia / Responsable técnico SG-SST",
                        "BORRADOR",
                        int(p.get("orden") or 0),
                        1,
                        now,
                        1,
                    ),
                )
            con.commit()

        row = con.execute("SELECT COUNT(1) AS n FROM sgsst_instructivos").fetchone()
        n_ins = int((row["n"] if row else 0) or 0)
        if n_ins == 0:
            now = _sgsst_now_ts()
            for i in SGSST_INSTRUCTIVOS_BASE:
                contenido = "\n".join([
                    i["titulo"].upper(),
                    "",
                    "Objetivo: guiar la carga correcta, consistente y trazable de registros en el sistema.",
                    "",
                    "Pasos mínimos:",
                    "1. Ingresar al módulo correspondiente.",
                    "2. Completar campos obligatorios y validar datos.",
                    "3. Registrar evidencias cuando aplique.",
                    "4. Guardar y verificar el registro.",
                    "5. Actualizar estado y cerrar cuando corresponda.",
                ])
                uso_aplicable = "\n".join([
                    f"Uso aplicable: categoría \"{i['categoria']}\".",
                    _SGSST_INTEGRACION_SGI_FRASE,
                ])
                con.execute(
                    """
                    INSERT INTO sgsst_instructivos (
                        codigo, titulo, categoria, descripcion_corta, contenido, uso_aplicable,
                        responsable, estado, orden_visual, activo, fecha_actualizacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        i["codigo"],
                        i["titulo"],
                        i["categoria"],
                        f"Instructivo breve: {i['categoria']}.",
                        contenido,
                        uso_aplicable,
                        "Intendencia / Responsable operativo",
                        "BORRADOR",
                        int(i.get("orden") or 0),
                        1,
                        now,
                    ),
                )
            con.commit()

    def _sgsst_estado_bloque(contenido: str, activo: int) -> dict:
        txt = (contenido or "").strip()
        if int(activo or 0) != 1:
            return {"label": "Pendiente", "cls": "pending"}
        if not txt:
            return {"label": "Pendiente", "cls": "pending"}
        if len(txt) < 650:
            return {"label": "En desarrollo", "cls": "dev"}
        return {"label": "Completo", "cls": "complete"}

    def _sgsst_estado_por_base(con, table: str, codigos_base):
        codigos = [str(x or "").strip() for x in (codigos_base or []) if str(x or "").strip()]
        if not codigos:
            return {"label": "Pendiente", "cls": "pending", "detalle": "", "n_act": 0, "total": 0}
        placeholders = ",".join(["?"] * len(codigos))
        row = con.execute(
            f"""
            SELECT COUNT(1) AS n
            FROM {table}
            WHERE COALESCE(activo, 1) = 1
              AND codigo IN ({placeholders})
            """,
            codigos,
        ).fetchone()
        n_act = int((row["n"] if row else 0) or 0)
        total = len(codigos)
        detalle = f"{n_act}/{total}"
        if n_act <= 0:
            return {"label": "Pendiente", "cls": "pending", "detalle": detalle, "n_act": n_act, "total": total}
        if n_act < total:
            return {"label": "En desarrollo", "cls": "dev", "detalle": detalle, "n_act": n_act, "total": total}
        return {"label": "Completo", "cls": "complete", "detalle": detalle, "n_act": n_act, "total": total}

    def _split_doc_tags(raw):
        chunks = []
        seen = set()
        for item in str(raw or "").replace(";", ",").split(","):
            t = item.strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            chunks.append(t)
        return chunks

    def iso_date(s):
        """Acepta '2025-11-24' o '24/11/2025' y devuelve '2025-11-24'."""
        if not s:
            return None
        s = s.strip()
        if "-" in s:
            return s
        try:
            return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            return None
    
    def asegurar_tabla_limpieza():
        con = get_db()
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sedes_limpieza (
                cod_sede            TEXT PRIMARY KEY,
                agente_id           INTEGER,
                responsable         TEXT,
                turno               TEXT,
                frecuencia          TEXT,
                observaciones       TEXT,
                fecha_actualizacion TEXT
            )
        """)

        con.commit()
        con.close()


    # -------------------------
    # PLANOS POR SEDE (PDF / IMAGEN)
    # -------------------------

    def asegurar_tablas_planos():
        """
        Crea las tablas sedes_planos y sedes_infra si no existen.
        Usamos esta función SOLO para estos dos objetos.
        """
        con = get_db()
        cur = con.cursor()

        # Tabla de archivos de planos (PDF / imágenes) por sede
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sedes_planos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cod_sede    TEXT NOT NULL,
                tipo        TEXT NOT NULL,        -- analisis / depositos / evacuacion
                archivo     TEXT NOT NULL,        -- nombre del archivo guardado
                fecha_carga TEXT                 -- YYYY-MM-DD
            )
        """)

        # Resumen numérico de infraestructura (por ahora lo dejamos en cero)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sedes_infra (
                cod_sede             TEXT PRIMARY KEY,
                oficinas             INTEGER DEFAULT 0,
                salas_entrevistas    INTEGER DEFAULT 0,
                banios               INTEGER DEFAULT 0,
                espacios_comunes     INTEGER DEFAULT 0,
                depositos            INTEGER DEFAULT 0,
                personas             INTEGER DEFAULT 0,
                m2_totales           REAL    DEFAULT 0,
                m2_por_persona       REAL    DEFAULT 0,
                personas_por_oficina REAL    DEFAULT 0
            )
        """)

        con.commit()
        con.close()

    def asegurar_tabla_limpieza():
        """Crea la tabla sedes_limpieza si no existe."""
        con = get_db()
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sedes_limpieza (
                cod_sede           TEXT PRIMARY KEY,
                agente_id          INTEGER,
                responsable        TEXT,
                turno              TEXT,
                frecuencia         TEXT,
                observaciones      TEXT,
                protocolo_url      TEXT,
                fecha_actualizacion TEXT
            )
        """)

        con.commit()
        con.close()

    def obtener_aires_por_sede(codigo):
        con = get_db()
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, sede_codigo, ambiente_codigo, ambiente_desc,
                   marca, fecha_ultimo_service, fecha_limpieza,
                   fecha_carga_gas, estado, observaciones
            FROM aires_sede
            WHERE sede_codigo = ?
            ORDER BY ambiente_codigo
        """, (codigo,))
        return cur.fetchall()
    def asegurar_tabla_aires():
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS aires_mpd(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,   -- S01, S02, S03...
                ambiente    TEXT,            -- Ej: Mesa de entrada, Planta alta, Oficina 3
                marca       TEXT,
                gas         TEXT,            -- Ej: R410, R32, etc.
                modelo      TEXT,
                tipo        TEXT,            -- Split, ventana, central, etc.
                frigorias   INTEGER,
                estado      TEXT,            -- OK, pendiente service, no funciona, etc.
                fecha_instalacion      TEXT,
                fecha_ultima_limpieza  TEXT,
                fecha_ultimo_service   TEXT,
                frecuencia_meses       INTEGER,    -- cada cuántos meses limpiás
                observaciones          TEXT
            );
        """)
        cols = [r[1] for r in cur.execute("PRAGMA table_info(aires_mpd)").fetchall()]
        if "gas" not in cols:
            cur.execute("ALTER TABLE aires_mpd ADD COLUMN gas TEXT")
        if "fecha_ultimo_service" not in cols:
            cur.execute("ALTER TABLE aires_mpd ADD COLUMN fecha_ultimo_service TEXT")
        con.commit()


    def upsert_evento(con, fuente, ref, tipo, titulo, inicio, fin=None, descripcion=None, color=None):
        """Crea o actualiza evento. No duplica si ya existe por UNIQUE."""
        if not inicio:
            return
        inicio = iso_date(inicio)
        fin = iso_date(fin) if fin else None
        color = color or CAL_COLORS.get(tipo)

        con.execute("""
            INSERT INTO eventos(fuente, ref, tipo, titulo, inicio, fin, color, descripcion)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(fuente, ref, tipo, inicio) DO UPDATE SET
                titulo=excluded.titulo,
                fin=excluded.fin,
                color=excluded.color,
                descripcion=excluded.descripcion
        """, (fuente, ref, tipo, titulo, inicio, fin, color, descripcion))

    def delete_eventos_fuente(con, fuente, ref, tipos):
        """Borra eventos viejos de una fuente/tipo para evitar basura."""
        q = ",".join(["?"]*len(tipos))
        con.execute(f"DELETE FROM eventos WHERE fuente=? AND ref=? AND tipo IN ({q})",
                    (fuente, ref, *tipos))


    # =========================
    # INIT DB
    # =========================
    def init_db():
        con = get_db()
        cur = con.cursor()


        # ---------------------------
        # DEPOSITOS / AMBIENTES POR SEDE
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sedes_depositos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_sede TEXT NOT NULL,   -- S01, S02, ...
            codigo_local TEXT NOT NULL,  -- S01-P00-D01
            descripcion TEXT NOT NULL,   -- Pasillo, Cocina, etc.
            UNIQUE(codigo_local),
            FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
        )
        """)
        # SEED DEPOSITOS (solo si está vacía)
        cur.execute("SELECT COUNT(*) FROM sedes_depositos")
        if cur.fetchone()[0] == 0:
            depositos_seed = [
                # ==== S01 – Independencia 202 ====
                ("S01", "S01-P00-D01", "Pasillo"),
                ("S01", "S01-P00-D02", "Sec Def General"),
                ("S01", "S01-P00-D03", "Audiencia 1"),
                ("S01", "S01-P00-D04", "Peritos"),
                ("S01", "S01-P00-D05", "Cocina"),
                ("S01", "S01-P00-D06", "Baño 1"),
                ("S01", "S01-P00-D07", "Baño 2"),
                ("S01", "S01-P00-D08", "Patio"),
                ("S01", "S01-P00-D09", "Audiencia 3"),
                ("S01", "S01-P00-D10", "Salud Mental"),
                ("S01", "S01-P01-D11", "Laura del Valle"),
                ("S01", "S01-P01-D12", "Secretaría General"),
                ("S01", "S01-P01-D13", "Def 3"),
                ("S01", "S01-P01-D14", "Def 1"),
                ("S01", "S01-P01-D15", "Dra Fernández"),
                ("S01", "S01-P01-D16", "Baño 3"),
                ("S01", "S01-P01-D17", "Dr. Salinas"),
                ("S01", "S01-P01-D18", "Defensa General"),
                ("S01", "S01-P01-D19", "Baño 4"),
                ("S01", "S01-P01-D20", "Pasillo"),
                ("S01", "S01-P02-D21", "Sala Reunión"),
                ("S01", "S01-P02-D22", "Def de Menores"),
                ("S01", "S01-P02-D23", "Def 2"),
                ("S01", "S01-P02-D24", "Dra López"),
                ("S01", "S01-P02-D25", "Def 4"),
                ("S01", "S01-P02-D26", "Dra Quintar"),
                ("S01", "S01-P02-D27", "Depósito"),
                ("S01", "S01-P02-D28", "Baño 5"),
                ("S01", "S01-P02-D29", "Dra Garay"),
                ("S01", "S01-P02-D30", "Pasillo"),

                # ==== S02 – San Pedro (Penal / Civil / Menores) ====
                ("S02", "S02-P00-D01", "Equipo Canetti"),
                ("S02", "S02-P00-D02", "Baño"),
                ("S02", "S02-P00-D03", "Dr Canetti"),
                ("S02", "S02-P00-D04", "Dr Elgoyhen"),
                ("S02", "S02-P00-D05", "Baño"),
                ("S02", "S02-P00-D06", "Equipo Dr Elgoyhen"),
                ("S02", "S02-P00-D07", "Dra Cortez"),
                ("S02", "S02-P00-D08", "Sajama"),
                ("S02", "S02-P00-D09", "Baño"),
                ("S02", "S02-P00-D10", "Equipo Menores"),
                ("S02", "S02-P00-D11", "Dra Sajama"),
                ("S02", "S02-P00-D12", "Equipo Dra Sajama"),
                ("S02", "S02-P00-D13", "Lescano Patricia"),
                ("S02", "S02-P00-D14", "Mesa de Entrada"),
                ("S02", "S02-P00-D15", "Baño"),
                ("S02", "S02-P00-D16", "Cocina"),
                ("S02", "S02-P00-D17", "Baño"),
                ("S02", "S02-P00-D18", "Equipo Dra Yapura"),
                ("S02", "S02-P00-D19", "Dra Yapura"),
                ("S02", "S02-P00-D20", "Baño"),
                ("S02", "S02-P00-D21", "Equipo Defensor 1"),
                ("S02", "S02-P00-D22", "Defensor 1"),
                ("S02", "S02-P00-D23", "Cocina"),
                ("S02", "S02-P00-D24", "Baño"),
                ("S02", "S02-P00-D25", "Equipo Defensor 2"),
                ("S02", "S02-P00-D26", "Defensor 2"),
                ("S02", "S02-P00-D27", "Dr Vilca Gaitán"),
                ("S02", "S02-P00-D28", "Equipo Def 5"),
                ("S02", "S02-P00-D29", "Equipo Dra Soria"),
                ("S02", "S02-P00-D30", "Dra Soria"),
                ("S02", "S02-P00-D31", "Baño"),
                ("S02", "S02-P00-D32", "Baño"),
                ("S02", "S02-P00-D33", "Dr Rivas"),
                ("S02", "S02-P00-D34", "Equipo Dr Rivas"),
                ("S02", "S02-P00-D35", "Pasillo"),

                # ==== S03 – Perico Penal (ejemplo) ====
                ("S03", "S03-P01-D01", "Administrativos"),
                ("S03", "S03-P01-D02", "Defensor"),
                ("S03", "S03-P01-D03", "Baño 1"),
                ("S03", "S03-P01-D04", "Dr Elías"),
                ("S03", "S03-P01-D05", "Patio"),
                ("S03", "S03-P01-D06", "Cocina"),
                ("S03", "S03-P01-D07", "Sala Entrevista"),
                ("S03", "S03-P01-D08", "Dra Acuña"),
                ("S03", "S03-P01-D09", "Pasillo"),
                ("S03", "S03-P01-D10", "Baño 2"),

                # ...seguís copiando el resto tal como están en tu listado PDF
                # (S04, S05, ... S20) con el mismo formato.
            ]

            cur.executemany("""
                INSERT INTO sedes_depositos (codigo_sede, codigo_local, descripcion)
                VALUES (?,?,?)
            """, depositos_seed)

        # Backfill: ensure S02 has the full set even if table already had partial data.
        s02_seed = [
            ("S02", "S02-P00-D01", "Equipo Canetti"),
            ("S02", "S02-P00-D02", "Ba¤o"),
            ("S02", "S02-P00-D03", "Dr Canetti"),
            ("S02", "S02-P00-D04", "Dr Elgoyhen"),
            ("S02", "S02-P00-D05", "Ba¤o"),
            ("S02", "S02-P00-D06", "Equipo Dr Elgoyhen"),
            ("S02", "S02-P00-D07", "Dra Cortez"),
            ("S02", "S02-P00-D08", "Sajama"),
            ("S02", "S02-P00-D09", "Ba¤o"),
            ("S02", "S02-P00-D10", "Equipo Menores"),
            ("S02", "S02-P00-D11", "Dra Sajama"),
            ("S02", "S02-P00-D12", "Equipo Dra Sajama"),
            ("S02", "S02-P00-D13", "Lescano Patricia"),
            ("S02", "S02-P00-D14", "Mesa de Entrada"),
            ("S02", "S02-P00-D15", "Ba¤o"),
            ("S02", "S02-P00-D16", "Cocina"),
            ("S02", "S02-P00-D17", "Ba¤o"),
            ("S02", "S02-P00-D18", "Equipo Dra Yapura"),
            ("S02", "S02-P00-D19", "Dra Yapura"),
            ("S02", "S02-P00-D20", "Ba¤o"),
            ("S02", "S02-P00-D21", "Equipo Defensor 1"),
            ("S02", "S02-P00-D22", "Defensor 1"),
            ("S02", "S02-P00-D23", "Cocina"),
            ("S02", "S02-P00-D24", "Ba¤o"),
            ("S02", "S02-P00-D25", "Equipo Defensor 2"),
            ("S02", "S02-P00-D26", "Defensor 2"),
            ("S02", "S02-P00-D27", "Dr Vilca Gait n"),
            ("S02", "S02-P00-D28", "Equipo Def 5"),
            ("S02", "S02-P00-D29", "Equipo Dra Soria"),
            ("S02", "S02-P00-D30", "Dra Soria"),
            ("S02", "S02-P00-D31", "Ba¤o"),
            ("S02", "S02-P00-D32", "Ba¤o"),
            ("S02", "S02-P00-D33", "Dr Rivas"),
            ("S02", "S02-P00-D34", "Equipo Dr Rivas"),
            ("S02", "S02-P00-D35", "Pasillo"),
        ]
        existing_s02 = {
            r[0] for r in cur.execute(
                "SELECT codigo_local FROM sedes_depositos WHERE codigo_sede = 'S02'"
            ).fetchall()
        }
        missing_s02 = [row for row in s02_seed if row[1] not in existing_s02]
        if missing_s02:
            cur.executemany("""
                INSERT OR IGNORE INTO sedes_depositos (codigo_sede, codigo_local, descripcion)
                VALUES (?,?,?)
            """, missing_s02)

        s06_layout = [
            ("D01", "Mesa de Entrada"),
            ("D02", "Leiva, Carolina del Valle Y Salazar, Cecilia del Valle"),
            ("D03", "Baño 1"),
            ("D04", "Dra Rodas"),
            ("D05", "Dr Ferreyra"),
            ("D06", "Baño 2"),
            ("D07", "Pasillo"),
            ("D08", "Baño"),
            ("D09", "Dra Castro"),
            ("D10", "Patio Interno"),
            ("D11", "Baño"),
            ("D12", "Cocina"),
            ("D13", "Entrevistas"),
            ("D14", "Acceso"),
        ]
        existing_s06 = {
            str(r[0] or "").strip().upper()
            for r in cur.execute(
                "SELECT codigo_local FROM sedes_depositos WHERE codigo_sede = 'S06'"
            ).fetchall()
        }
        for codigo_local, descripcion in s06_layout:
            if codigo_local in existing_s06:
                cur.execute("""
                    UPDATE sedes_depositos
                    SET descripcion = ?
                    WHERE codigo_sede = 'S06' AND UPPER(TRIM(codigo_local)) = ?
                """, (descripcion, codigo_local))
            else:
                cur.execute("""
                    INSERT INTO sedes_depositos (codigo_sede, codigo_local, descripcion)
                    VALUES ('S06', ?, ?)
                """, (codigo_local, descripcion))

        s06_personal_moves = [
            ("Leiva, Carolina del Valle", "cleiva@mpdjujuy.gob.ar", "D02"),
            ("Salazar, Cecilia del Valle", "", "D02"),
            ("Rodas, Paola Giselle", "prodas@mpdpjujuy.gob.ar", "D04"),
            ("Ferreyra, Marcelo Adrián", "aferreyra@mpdpjujuy.gob.ar", "D05"),
            ("Castro Reyna, María Sofía", "mcastro@mpdjujuy.gob.ar", "D09"),
        ]
        for nombre_apellido, email_admin, codigo_local in s06_personal_moves:
            cur.execute("""
                UPDATE personal_sede
                SET codigo_local = ?, piso = COALESCE(NULLIF(TRIM(piso), ''), 'PB')
                WHERE codigo_sede = 'S06'
                  AND (
                    nombre_apellido = ?
                    OR (TRIM(COALESCE(email_admin, '')) <> '' AND LOWER(TRIM(email_admin)) = LOWER(TRIM(?)))
                  )
            """, (codigo_local, nombre_apellido, email_admin))


        # ---------------------------
        # MOVIMIENTOS DE MOBILIARIO
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_mobiliario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,              -- YYYY-MM-DD
            item TEXT NOT NULL,               -- Ej: Escritorio, Silla, PC
            cantidad REAL DEFAULT 1,

            sede_origen   TEXT,
            deposito_origen TEXT,
            sede_destino    TEXT,
            deposito_destino TEXT,

            observaciones TEXT
        )
        """)

        # ---------------------------
        # PLANOS DE SEDES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sede_planos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_sede TEXT NOT NULL,
            tipo TEXT NOT NULL,      -- 'distribucion','depositos','evacuacion'
            archivo TEXT NOT NULL,   -- nombre del archivo en /static/planos
            activo INTEGER DEFAULT 1,
            FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
        )
        """)

        # ---------------------------
        # INVENTARIO SIMPLE POR SEDE
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sede_inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_sede TEXT NOT NULL,
            item TEXT NOT NULL,
            categoria TEXT,
            ubicacion TEXT,
            cantidad REAL,
            observaciones TEXT,
            FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
        )
        """)

        # ---------------------------
        # CALENDARIO / EVENTOS
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS eventos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,          -- YYYY-MM-DD
            titulo TEXT NOT NULL,
            detalle TEXT,
            color TEXT DEFAULT '#3B82F6',
            fuente TEXT NOT NULL,         -- 'vehiculos','combustible','viajes','checklist'
            ref_id TEXT                  -- patente o id relacionado
        )
        """)

        # ---------------------------
        # AGENTES INTENDENCIA
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_intendencia(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente TEXT NOT NULL,
            rubro TEXT NOT NULL,
            dias_feria INTEGER DEFAULT 0,
            foto_url TEXT,
            activo INTEGER DEFAULT 1
        )
        """)
        # ---------------------------
        # LICENCIAS DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_licencias(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,              -- vacaciones, enfermedad, etc.
            fecha_desde TEXT NOT NULL,       -- YYYY-MM-DD
            fecha_hasta TEXT NOT NULL,
            observaciones TEXT,
            estado TEXT DEFAULT 'APROBADA',  -- APROBADA / PENDIENTE / RECHAZADA
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)
        # ---------------------------
        # COMPENSATORIOS DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_compensatorios_mov(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,            -- fecha de carga (YYYY-MM-DD)
            tipo TEXT NOT NULL,             -- INICIAL / FERIA / HORAS / TOMA
            dias REAL DEFAULT 0,
            horas REAL DEFAULT 0,
            periodo TEXT,                   -- Ej: Enero 2026
            desde TEXT,                     -- para TOMA
            hasta TEXT,                     -- para TOMA
            observaciones TEXT,
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)
        # ---------------------------
        # DOCUMENTACIÓN DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_documentacion(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,              -- carnet_conducir, dni, art, examen_medico, etc.
            fecha_vencimiento TEXT NOT NULL, -- YYYY-MM-DD
            observaciones TEXT,
            estado TEXT,                     -- VIGENTE, VENCIDO, EN TRÁMITE, etc.
            archivo TEXT,
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id),
            UNIQUE(agente_id, tipo)
        )
        """)
        # ASIGNACIONES DE AGENTES A SEDES
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            sede_codigo TEXT NOT NULL,
            fecha_desde TEXT NOT NULL,   -- YYYY-MM-DD
            fecha_hasta TEXT,            -- opcional
            observaciones TEXT,
            estado TEXT,                 -- ACTIVA / HISTORICA / BAJA
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)
        # ---------------------------
        # MAPA SAN SALVADOR (PROVEEDORES / TAREAS / PENDIENTES)
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS mapa_ssj_puntos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,              -- 'proveedor' / 'tarea' / 'pericia' / 'otro'
            titulo TEXT NOT NULL,            -- nombre corto (ej: "Ferretería X", "Medición gas", etc.)
            descripcion TEXT,                -- detalle libre
            estado TEXT NOT NULL DEFAULT 'pendiente',  -- 'pendiente' / 'ejecutado'
            direccion TEXT,
            lat REAL,
            lng REAL,
            fecha_alta TEXT NOT NULL,        -- YYYY-MM-DD
            fecha_visita TEXT,               -- YYYY-MM-DD (cuando se ejecuta o se revisa)
            contacto TEXT,                   -- opcional (tel/email)
            referencia TEXT                  -- opcional (nro pedido, orden, expediente, etc.)
        )
        """)



         # ---------------------------
        # EQUIPO INTERDISCIPLINARIO
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS equipo_interdisciplinario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            profesion TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            UNIQUE(nombre, profesion)
        )
        """)

        cur.execute("SELECT COUNT(*) FROM equipo_interdisciplinario")
        if cur.fetchone()[0] == 0:
            equipo_seed = [
                ("Natalia Marcos", "Asistente Social"),
                ("Rut Romero", "Asistente Social"),
                ("Agustina Frias", "Psicología"),
                ("Pamela Gareca", "Médica"),
                ("Jose Moreno", "Perito"),
            ]
            cur.executemany("""
                INSERT OR IGNORE INTO equipo_interdisciplinario(nombre, profesion)
                VALUES (?,?)
            """, equipo_seed)

        # ---------------------------
        # PRECIOS FIJOS COMBUSTIBLE
        # (los editás solo vos)
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS combustible_precios(
            tipo TEXT PRIMARY KEY,    -- 'nafta' / 'gasoil'
            precio_litro REAL NOT NULL
        )
        """)

        cur.execute("SELECT COUNT(*) FROM combustible_precios")
        if cur.fetchone()[0] == 0:
            cur.executemany("""
                INSERT INTO combustible_precios(tipo, precio_litro)
                VALUES (?,?)
            """, [("nafta", 0), ("gasoil", 0)])

        # ---------------------------
        # MOVIMIENTOS DE MOBILIARIO ENTRE SEDES / DEPÓSITOS
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_mobiliario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,          -- YYYY-MM-DD
            sede_origen TEXT NOT NULL,    -- código S01, S02...
            deposito_origen TEXT,         -- texto libre (Depósito 1, Oficina 2, etc.)
            sede_destino TEXT NOT NULL,   -- código S01, S02...
            deposito_destino TEXT,        -- texto libre
            item TEXT NOT NULL,           -- qué mueble / equipo se mueve
            cantidad REAL,                -- cuántas unidades
            observaciones TEXT
        )
        """)

        # ---------------------------
        # VEHICULOS
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculos(
            patente TEXT PRIMARY KEY,
            codigo_interno TEXT UNIQUE,   -- G-01 / N-01
            tipo TEXT NOT NULL,           -- G / N
            modelo TEXT,
            combustible TEXT NOT NULL,    -- gasoil/nafta
            base_ciudad TEXT DEFAULT 'San Salvador de Jujuy',
            color_tag TEXT DEFAULT '#5B5BEA',
            activo INTEGER DEFAULT 1
        )
        """)

        # Estado global (service/lavado/seguro/rtv)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculo_estado(
            patente TEXT PRIMARY KEY,
            ultimo_service TEXT,
            proximo_service TEXT,
            ultimo_lavado TEXT,
            proximo_lavado TEXT,
            seguro_inicio TEXT,
            seguro_vencimiento TEXT,
            rtv_inicio TEXT,
            rtv_vencimiento TEXT,
            FOREIGN KEY(patente) REFERENCES vehiculos(patente)
        )
        """)

        # Choferes autorizados (etapa 2)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculo_choferes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patente TEXT NOT NULL,
            chofer_id INTEGER NOT NULL,
            activo INTEGER DEFAULT 1,
            UNIQUE(patente, chofer_id),
            FOREIGN KEY(patente) REFERENCES vehiculos(patente),
            FOREIGN KEY(chofer_id) REFERENCES agentes_intendencia(id)
        )
        """)
        # ---------------------------
        # OBRAS / MANTENIMIENTO POR SEDE
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS obras_sede(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_sede TEXT NOT NULL,
            titulo TEXT NOT NULL,
            tipo TEXT,                     -- eléctrico, albañilería, pintura, etc.
            prioridad TEXT DEFAULT 'Media',-- Alta / Media / Baja
            estado TEXT DEFAULT 'PENDIENTE',   -- PENDIENTE / EN_CURSO / FINALIZADA
            fecha_solicitud TEXT NOT NULL,     -- YYYY-MM-DD
            fecha_inicio TEXT,
            fecha_fin_prevista TEXT,
            fecha_fin_real TEXT,
            descripcion TEXT,
            observaciones TEXT,
            FOREIGN KEY(codigo_sede) REFERENCES sedes_mpd(codigo)
        )
        """)

        # ---------------------------
        # DESTINOS
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS destinos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activo INTEGER DEFAULT 1
        )
        """)
        # ---------------------------
        # INCIDENTES / ACCIDENTES DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_incidentes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,          -- YYYY-MM-DD
            tipo TEXT NOT NULL,           -- incidente / accidente / casi_accidente, etc.
            lugar TEXT,
            descripcion TEXT,
            consecuencia TEXT,            -- sin lesion, con lesion leve, etc.
            acciones TEXT,                -- medidas tomadas
            estado TEXT,                  -- ABIERTO / CERRADO
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)

        # ---------------------------
        # SST (Prevencion / No conformidades / Informes)
        # ---------------------------
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

        # ---------------------------
        # DESEMPENO DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_desempeno(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,          -- YYYY-MM-DD
            tipo TEXT NOT NULL,           -- evaluacion, observacion, reconocimiento, etc.
            periodo TEXT,                 -- ej: 2025 - 1er semestre
            calificacion INTEGER,         -- 1 a 5 (opcional)
            observaciones TEXT,
            estado TEXT,                  -- ABIERTO / CERRADO / HISTORICO
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)

    # ---------------------------
        # VIAJES / CONTROL DIARIO
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS viajes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            patente TEXT NOT NULL,
            chofer_id INTEGER,
            agente_trasladado TEXT,
            equipo_id INTEGER,            -- para equipo interdisciplinario
            destino_id INTEGER,
            origen TEXT DEFAULT 'San Salvador de Jujuy',
            km_ini REAL DEFAULT 0,
            km_fin REAL DEFAULT 0,
            recorrido_km REAL DEFAULT 0,
            largo INTEGER DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY(patente) REFERENCES vehiculos(patente),
            FOREIGN KEY(chofer_id) REFERENCES agentes_intendencia(id),
            FOREIGN KEY(equipo_id) REFERENCES equipo_interdisciplinario(id),
            FOREIGN KEY(destino_id) REFERENCES destinos(id)
        )
        """)



        # ---------------------------
        # COMBUSTIBLE
        # columnas según tu planilla
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS combustible_cargas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            patente TEXT NOT NULL,
            chofer_id INTEGER,
            remito TEXT,
            km_actual REAL DEFAULT 0,
            litros REAL NOT NULL,
            precio_litro REAL NOT NULL,
            precio_total REAL NOT NULL,     -- cantidad en plata
            notas TEXT,
            FOREIGN KEY(patente) REFERENCES vehiculos(patente),
            FOREIGN KEY(chofer_id) REFERENCES agentes_intendencia(id)
        )
        """)

        # ---------------------------
        # CHECKLIST
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activo INTEGER DEFAULT 1
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_registros(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            patente TEXT NOT NULL,
            chofer_id INTEGER,
            tipo TEXT NOT NULL, -- salida / entrada
            observaciones TEXT,
            FOREIGN KEY(patente) REFERENCES vehiculos(patente),
            FOREIGN KEY(chofer_id) REFERENCES agentes_intendencia(id)
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_detalle(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registro_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            ok INTEGER DEFAULT 1,
            nota TEXT,
            FOREIGN KEY(registro_id) REFERENCES checklist_registros(id),
            FOREIGN KEY(item_id) REFERENCES checklist_items(id)
        )
        """)


        # ======================================================
        # SEEDS (solo si están vacías)
        # ======================================================

        # sedes
        cur.execute("SELECT COUNT(*) FROM sedes_mpd")
        if cur.fetchone()[0] == 0:
            sedes = [
                ("S01","Independencia 202","San Salvador de Jujuy","Independencia 202",-24.1872,-65.2960,"penal"),
                ("S02","San Pedro Civil - Penal Unificado","San Pedro de Jujuy","",-24.2319,-64.8667,"penal"),
                ("S03","Perico Penal","Perico","",-24.3833,-65.1167,"penal"),
                ("S04","Alto Comedero","San Salvador de Jujuy","",-24.2250,-65.2660,"juridico_social"),
                ("S05","Humahuaca Penal","Humahuaca","",-23.2050,-65.3490,"penal"),
                ("S06","Ledesma Penal y Menores Unificado","Libertador Gral. San Martín","",-23.8090,-64.7900,"penal"),
                ("S07","Palpalá Penal","Palpalá","",-24.2560,-65.2100,"penal"),
                ("S08","San Martín 137","San Salvador de Jujuy","San Martín 137",-24.1879,-65.2996,"administracion"),
                ("S10","El Carmen Civil - Penal Unificado","El Carmen","",-24.3860,-65.2790,"juridico_social"),
                ("S11","Gorriti 791","San Salvador de Jujuy","Gorriti 791",-24.1879,-65.2996,"juridico_social"),
                ("S12","Belgrano 284","San Salvador de Jujuy","Belgrano 284",-24.1879,-65.2996,"equipo_interdisciplinario"),
                ("S13","San Martín 271","San Salvador de Jujuy","San Martín 271",-24.1879,-65.2996,"menores_incapaces"),
            ]
            cur.executemany("""
                INSERT INTO sedes_mpd(codigo,nombre,ciudad,direccion,lat,lng,fuero)
                VALUES (?,?,?,?,?,?,?)
            """, sedes)

        # agentes intendencia
        cur.execute("SELECT COUNT(*) FROM agentes_intendencia")
        if cur.fetchone()[0] == 0:
            agentes = [
                ("Carlos Vidaurre","mantenimiento",0,None),
                ("Marcos Duran","mantenimiento",0,None),
                ("Nestor Guerrero","mantenimiento",0,None),
                ("Manuel Flores","mantenimiento",0,None),
                ("Francisco Savio","mantenimiento",0,None),
                ("Ignacio Baroni","choferes",0,None),
                ("Mauro Vea Murguia","choferes",0,None),
                ("Emiliano P. de la Puente","choferes",0,None),
                ("Nahuel Amado","choferes",0,None),
                ("Luis Cardozo","choferes",0,None),
                ("Beatriz Castillo","limpieza",0,None),
                ("Miriam Tejerina","limpieza",0,None),
                ("Yolanda Solis","limpieza",0,None),
                ("Mabel Alejo","limpieza",0,None),
                ("Miguel Saldano","limpieza",0,None),
                ("Flavia Gutierrez","limpieza",0,None),
                ("Micaela Aima","limpieza",0,None),
                ("Bustamante","limpieza",0,None),
            ]
            cur.executemany("""
                INSERT INTO agentes_intendencia(agente,rubro,dias_feria,foto_url)
                VALUES (?,?,?,?)
            """, agentes)

        # ---------------------------
        # EPP / HERRAMIENTAS DE AGENTES
        # ---------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agentes_epp(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,              -- casco, zapato, arnés, herramienta, etc.
            categoria TEXT,                  -- EPP / HERRAMIENTA
            fecha_entrega TEXT NOT NULL,     -- YYYY-MM-DD
            cantidad INTEGER DEFAULT 1,
            observaciones TEXT,
            estado TEXT,                     -- ENTREGADO / DEVUELTO / BAJA / PERDIDO
            FOREIGN KEY(agente_id) REFERENCES agentes_intendencia(id)
        )
        """)

        # equipo interdisciplinario
        cur.execute("SELECT COUNT(*) FROM equipo_interdisciplinario")
        if cur.fetchone()[0] == 0:
            equipo_seed = [
                ("Natalia Marcos", "Asistente Social"),
                ("Rut Romero", "Asistente Social"),
                ("Agustina Frias", "Psicología"),
                ("Pamela Gareca", "Médica"),
                ("Jose Moreno", "Perito"),
            ]
            cur.executemany("""
                INSERT OR IGNORE INTO equipo_interdisciplinario(nombre, profesion)
                VALUES (?,?)
            """, equipo_seed)

        # vehiculos
        cur.execute("SELECT COUNT(*) FROM vehiculos")
        if cur.fetchone()[0] == 0:
            vehiculos_seed = [
                ("AE856GD","G-01","G","Ford Ranger","gasoil","San Salvador de Jujuy","#5B5BEA"),
                ("AE856GE","G-02","G","Ford Ranger","gasoil","San Pedro de Jujuy","#65BFF4"),
                ("AF277OA","G-03","G","Ford Ranger","gasoil","San Salvador de Jujuy","#F64B94"),
                ("AG846FR","G-04","G","Renault","gasoil","San Pedro de Jujuy","#8B5CF6"),
                ("AB946VK","N-01","N","Ford Ranger","nafta","San Salvador de Jujuy","#3B82F6"),
            ]
            cur.executemany("""
                INSERT INTO vehiculos(patente,codigo_interno,tipo,modelo,combustible,base_ciudad,color_tag)
                VALUES (?,?,?,?,?,?,?)
            """, vehiculos_seed)

            for v in vehiculos_seed:
                cur.execute("INSERT INTO vehiculo_estado(patente) VALUES (?)", (v[0],))

        # destinos
        cur.execute("SELECT COUNT(*) FROM destinos")
        if cur.fetchone()[0] == 0:
            destinos_seed = [
                ("San Salvador",),("San Pedro",),("Perico",),("Palpalá",),
                ("Humahuaca",),("Tilcara",),("Abra Pampa",),("La Quiaca",),
                ("El Carmen",),("Ledesma",)
            ]
            cur.executemany("INSERT INTO destinos(nombre) VALUES (?)", destinos_seed)

        # checklist items
        cur.execute("SELECT COUNT(*) FROM checklist_items")
        if cur.fetchone()[0] == 0:
            items_seed = [
                ("Luces",),("Aceite",),("Agua",),("Rueda auxilio",),
                ("Botiquín",),("Extintor",),("Documentación",)
            ]
            cur.executemany("INSERT INTO checklist_items(nombre) VALUES (?)", items_seed)

        # precios combustible base
        cur.execute("SELECT COUNT(*) FROM combustible_precios")
        if cur.fetchone()[0] == 0:
            precios_seed = [
                ("nafta", 1200.0),
                ("gasoil", 1400.0)
            ]
            cur.executemany("""
                INSERT INTO combustible_precios(tipo, precio_litro)
                VALUES (?, ?)
            """, precios_seed)



    def add_evento(fecha, titulo, detalle="", color="#3B82F6", fuente="sistema", ref_id=None):
        if not fecha:
            return
        con = get_db()
        con.execute("""
            INSERT INTO eventos(fecha, titulo, detalle, color, fuente, ref_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fecha,
            titulo[:120],
            (detalle or "")[:500],
            color,
            fuente,
            str(ref_id) if ref_id is not None else None,
        ))
        con.commit()
        con.close()


    def add_evento_tipo(fecha, tipo, titulo, detalle="", fuente="agentes", ref_id=None):
        """
        Usa CAL_COLORS según el 'tipo' de evento.
        """
        if not fecha:
            return
        color = CAL_COLORS.get(tipo, "#3B82F6")
        add_evento(fecha, titulo, detalle, color=color, fuente=fuente, ref_id=ref_id)


    def rebuild_eventos_limpieza_sede():
        """
        Regenera los eventos de LIMPIEZA DE SEDES en la tabla eventos,
        a partir de la tabla sedes_limpieza.

        No toca los eventos de seguridad (matafuegos) ni otros tipos.
        """

        con = get_db()
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # 1) Borrar solo eventos de limpieza de sede
        cur.execute("DELETE FROM eventos WHERE fuente = 'limpieza_sede'")
        con.commit()

        # 2) Traer todas las asignaciones de limpieza
        cur.execute("""
            SELECT
                id,
                cod_sede,
                responsable,
                turno,
                frecuencia,
                observaciones,
                fecha_desde,
                fecha_hasta,
                fecha_actualizacion
            FROM sedes_limpieza
        """)
        filas = cur.fetchall()

        for fila in filas:
            cod_sede    = fila["cod_sede"]
            responsable = fila["responsable"] or "s/d"
            turno       = fila["turno"] or ""
            frecuencia  = fila["frecuencia"] or ""
            obs         = fila["observaciones"] or ""

            # Armamos un texto base
            partes = [f"Sede {cod_sede}", responsable]
            if turno:
                partes.append(turno)
            if frecuencia:
                partes.append(frecuencia)
            detalle_base = " · ".join(partes)

            if obs:
                detalle = f"{detalle_base} · {obs}"
            else:
                detalle = detalle_base

            # Fecha para el evento:
            #   prioridad: fecha_desde > fecha_actualizacion > hoy
            fecha_ini = fila["fecha_desde"] or fila["fecha_actualizacion"]
            if not fecha_ini:
                fecha_ini = date.today().isoformat()

            # ID de referencia para este registro de limpieza
            ref_id = f"LIMP-{fila['id']}"

            # Un evento por asignación (día de inicio)
            add_evento_tipo(
                fecha   = fecha_ini,
                tipo    = "limpieza_sede",
                titulo  = "Limpieza asignada",
                detalle = detalle,
                fuente  = "limpieza_sede",
                ref_id  = ref_id,
            )

        con.commit()
        con.close()

    def init_db():
        con = get_db()
        cur = con.cursor()

        # ... tus otras tablas ...

        cur.execute("""
        CREATE TABLE IF NOT EXISTS asistidos(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nombre TEXT NOT NULL,
          barrio TEXT,
          direccion TEXT,
          referencia TEXT,
          telefono TEXT,
          lat REAL,
          lng REAL,
          estado TEXT NOT NULL DEFAULT 'NO_REALIZADA',
          creado_en TEXT DEFAULT (date('now'))
        )
        """)

        # Backfill: S20 (Palpalá Civil)
        # PB: D01..D10
        # P1: D11..D17
        # Si faltan, los agregamos para que aparezcan en filtros/combos.
        try:
            cur.execute(
                "SELECT codigo_local FROM sedes_depositos WHERE codigo_sede = ?",
                ("S20",),
            )
            existing = {(r[0] or "").strip().upper() for r in cur.fetchall()}
            required = [
                ("D09", "deposito 9"),
                ("D10", "deposito 10"),
                ("D11", "piso 1 - deposito 11"),
                ("D12", "piso 1 - deposito 12"),
                ("D13", "piso 1 - deposito 13"),
                ("D14", "piso 1 - deposito 14"),
                ("D15", "piso 1 - deposito 15"),
                ("D16", "piso 1 - deposito 16"),
                ("D17", "piso 1 - deposito 17"),
            ]
            missing = [
                ("S20", codigo_local, descripcion)
                for codigo_local, descripcion in required
                if codigo_local.strip().upper() not in existing
            ]
            if missing:
                cur.executemany(
                    "INSERT OR IGNORE INTO sedes_depositos (codigo_sede, codigo_local, descripcion) VALUES (?,?,?)",
                    missing,
                )
        except sqlite3.OperationalError:
            pass

        ensure_sedes_mpd_cols(con)
        con.commit()
        con.close()



    init_db()

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

    def _guardias_pasivas_plan_2026():
        return [
            {"mes": "enero", "chofer": "Ignacio Baroni"},
            {"mes": "febrero", "chofer": "Mauro Vea Murguia"},
            {"mes": "marzo", "chofer": "Emiliano Perez de la Puente"},
            {"mes": "abril", "chofer": "Ignacio Baroni"},
            {"mes": "mayo", "chofer": "Mauro Vea Murguia"},
            {"mes": "junio", "chofer": "Jorge Corbacho"},
            {"mes": "julio", "chofer": "Francisco Savio / Manuel Flores"},
            {"mes": "agosto", "chofer": "Matias Calderari"},
            {"mes": "septiembre", "chofer": "Emiliano Perez de la Puente"},
            {"mes": "octubre", "chofer": "Ignacio Baroni"},
            {"mes": "noviembre", "chofer": "Mauro Vea Murguia"},
            {"mes": "diciembre", "chofer": "Jorge Corbacho"},
        ]

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

    def _append_unique_ci(items, value):
        v = (value or "").strip()
        if not v:
            return
        lk = v.lower()
        for x in items:
            if (x or "").strip().lower() == lk:
                return
        items.append(v)

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
            # Opciones generales para novedades que no corresponden a una sede puntual.
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

            # Sedes personalizadas agregadas desde el panel.
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

        # 1) Siempre: TODOS los eventos del calendario del dia.
        for ev in (data.get("calendario", {}) or {}).get("hoy", []) or []:
            _add(_ev_txt(ev), "Calendario")

        # 2) Proximos 7 dias: solo vencimientos/criticos para anticipacion.
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

    def _dashboard_operativo_data():
        con = get_db()
        today = date.today()
        today_iso = today.isoformat()
        week_start = (today - timedelta(days=6)).isoformat()
        month_start = (today - timedelta(days=29)).isoformat()

        data = {
            "vehiculos": {
                "donut": {
                    "enUso": 0,
                    "guardados": 0,
                    "pendientesCierre": 0,
                    "noDisponibles": 0,
                    "total": 0,
                },
                "finJornada": {
                    "pendientesCierre": 0,
                    "ok": True,
                },
                "topAsignacion": [],
                "ultimosViajesLargos": [],
                "manualMovimientos": [],
                "catalogos": {
                    "vehiculos": [],
                    "choferes": [],
                    "destinos": [],
                },
                "proceso": {
                    "responsableTactico": "Ignacio Baroni",
                },
            },
            "materiales": {
                "internosPendientes": 0,
                "enviadosCompra": 0,
                "entregasPendientesCierre": 0,
            },
            "obras": {
                "enEjecucionHoy": 0,
                "cerradasHoy": 0,
                "urgenciasExternas": 0,
                "novedadesHoy": [],
                "novedadesCount": 0,
            },
            "matafuegos": {
                "next": {"fecha": "", "sedes": []},
                "days_left": None,
                "count_45d": 0,
            },
            "desinfeccion": {
                "last": {"fecha": "", "sedes": [], "grupo": "", "label": ""},
                "next": {"fecha": "", "sedes": [], "grupo": "", "label": ""},
                "status": "",
            },
            "limpieza": {
                "pendientesRevision": 0,
            },
            "horarios": {
                "pendienteMail": 0,
                "enviadosHoy": 0,
                "turnosChoferesSinAsignarMes": 0,
            },
            "personal": {
                "distribucion": [],
                "totalAsignado": 0,
                "sedesSinPersonal": 0,
                "snapshot": "hoy",
            },
            "asignacionDia": {
                "licenciasDia": [],
                "compensatoriosActivos": [],
                "turnoMesChoferes": [],
                "turnoSemanaVespertino": [],
                "choferes": [],
                "turnosCfg": {
                    "mesMensual": "",
                    "choferMensual": "",
                    "semanaDesde": "",
                    "semanaHasta": "",
                    "choferSemanal": "",
                },
                "guardiasPasivas": {
                    "plan2026": _guardias_pasivas_plan_2026(),
                    "mensual": {
                        "estado": "pendiente",
                        "texto": "Pendiente de aceptacion",
                        "aceptadoEn": "",
                        "chofer": "",
                        "periodo": "",
                    },
                    "semanal": {
                        "estado": "pendiente",
                        "texto": "Pendiente de aceptacion",
                        "aceptadoEn": "",
                        "chofer": "",
                        "periodo": "",
                    }
                },
                "limpiezaTurnosSede": [],
                "gruposLimpieza": [],
                "rotacionActiva": {
                    "mes": "",
                    "proximaFecha": "",
                    "filas": [],
                    "refuerzoTexto": "El grupo asignado a San Martin 137 cubre Alto Comedero y Palpala cuando Intendencia lo disponga.",
                },
                "instructivoRotacion": [
                    "La rotacion es mensual y automatica.",
                    "Cada grupo rota por todas las sedes en ciclos de 4 meses.",
                    "Todos los agentes pasan por todas las sedes (criterio de equidad).",
                    "La sede San Martin 137, por su menor volumen operativo, actua como sede base de refuerzo territorial.",
                    "El grupo asignado a San Martin 137 cubre Alto Comedero y Palpala cuando Intendencia lo disponga.",
                    "Las licencias activan cobertura interna dentro del grupo.",
                    "El sistema prioriza equilibrio de carga laboral y justicia operativa.",
                ],
            },
            "fechaHoy": today_iso,
            "indicadores2026": {
                "kmPorVehiculo": [],
                "kmPorChofer": [],
                "totalKm": 0.0,
            },
            "calendario": {
                "fechaSel": today_iso,
                "diasConEventos": [],
                "diasMeta": {},
                "hoy": [],
                "proximos7": [],
                "resumen": {
                    "eventosHoy": 0,
                    "eventos7": 0,
                    "alertasCriticas": 0,
                },
            },
            "recordatorios": [],
            "licenciasHoy": 0,
            "sedeEstado": {
                "promedioPct": 0,
                "items": [],
                "variables": list(SEDE_ESTADO_VARS),
            },
        }

        veh_cols = _table_cols(con, "vehiculos")
        viajes_cols = _table_cols(con, "viajes")

        # =========================
        # VEHICULOS - DONUT + TOP 5
        # =========================
        if _table_exists(con, "vehiculos"):
            try:
                row_total = con.execute("SELECT COUNT(*) AS n FROM vehiculos").fetchone()
                total = int(_row_value(row_total, "n", 0) or 0)
            except Exception:
                total = 0

            no_disponibles = 0
            if "activo" in veh_cols:
                try:
                    row_nd = con.execute(
                        "SELECT COUNT(*) AS n FROM vehiculos WHERE COALESCE(activo, 1) = 0"
                    ).fetchone()
                    no_disponibles = int(_row_value(row_nd, "n", 0) or 0)
                except Exception:
                    no_disponibles = 0

            pendientes = 0
            en_uso = 0
            if _table_exists(con, "viajes") and {"patente", "fecha"}.issubset(viajes_cols):
                estado_expr = "UPPER(COALESCE(estado,''))" if "estado" in viajes_cols else "''"
                try:
                    rows_hoy = con.execute(f"""
                        SELECT
                            patente,
                            MAX(CASE WHEN {estado_expr} IN ('ABIERTO','EN CURSO','EN_CURSO','PENDIENTE CIERRE','PENDIENTE_CIERRE') THEN 1 ELSE 0 END) AS has_open,
                            MAX(CASE WHEN date(fecha) = date(?) THEN 1 ELSE 0 END) AS has_trip_today
                        FROM viajes
                        GROUP BY patente
                    """, (today_iso,)).fetchall()
                    for r in rows_hoy:
                        has_open = int(_row_value(r, "has_open", 0) or 0)
                        if has_open:
                            en_uso += 1
                except Exception:
                    pendientes = 0
                    en_uso = 0

            guardados = max(total - no_disponibles - pendientes - en_uso, 0)
            data["vehiculos"]["donut"] = {
                "enUso": int(en_uso),
                "guardados": int(guardados),
                "pendientesCierre": int(pendientes),
                "noDisponibles": int(no_disponibles),
                "total": int(total),
            }
            data["vehiculos"]["finJornada"] = {
                "pendientesCierre": int(pendientes),
                "ok": int(pendientes) == 0,
            }

            if "patente" in veh_cols:
                base_expr = "COALESCE(v.base_ciudad, '')" if "base_ciudad" in veh_cols else "''"
                lugar_expr = "COALESCE(v.lugar_reservado, '')" if "lugar_reservado" in veh_cols else "''"
                alias_expr = "COALESCE(v.codigo_interno, '')" if "codigo_interno" in veh_cols else "''"
                activo_expr = "COALESCE(v.activo, 1)" if "activo" in veh_cols else "1"

                select_sql = f"""
                    SELECT
                        v.patente AS patente,
                        {alias_expr} AS alias,
                        {base_expr} AS base_ciudad,
                        {lugar_expr} AS lugar_reservado,
                        {activo_expr} AS activo,
                        COALESCE(k7.km7, 0) AS km7,
                        COALESCE(k7.c7, 0) AS c7,
                        COALESCE(k30.km30, 0) AS km30,
                        COALESCE(k30.c30, 0) AS c30,
                        COALESCE(h.has_open, 0) AS has_open,
                        COALESCE(h.has_trip, 0) AS has_trip
                    FROM vehiculos v
                """
                params = []

                if _table_exists(con, "viajes") and {"patente", "fecha"}.issubset(viajes_cols):
                    km_calc = []
                    if "recorrido_km" in viajes_cols:
                        km_calc.append("recorrido_km")
                    if {"km_ini", "km_fin"}.issubset(viajes_cols):
                        km_calc.append("(km_fin - km_ini)")
                    km_expr = "COALESCE(" + ", ".join(km_calc) + ")" if km_calc else "NULL"
                    estado_expr = "UPPER(COALESCE(estado,''))" if "estado" in viajes_cols else "''"

                    select_sql += f"""
                        LEFT JOIN (
                            SELECT patente, COUNT(*) AS c7, SUM({km_expr}) AS km7
                            FROM viajes
                            WHERE date(fecha) >= date(?) AND date(fecha) <= date(?)
                            GROUP BY patente
                        ) k7 ON k7.patente = v.patente
                        LEFT JOIN (
                            SELECT patente, COUNT(*) AS c30, SUM({km_expr}) AS km30
                            FROM viajes
                            WHERE date(fecha) >= date(?) AND date(fecha) <= date(?)
                            GROUP BY patente
                        ) k30 ON k30.patente = v.patente
                        LEFT JOIN (
                            SELECT
                                patente,
                                MAX(CASE WHEN {estado_expr} IN ('ABIERTO','EN CURSO','EN_CURSO','PENDIENTE CIERRE','PENDIENTE_CIERRE') THEN 1 ELSE 0 END) AS has_open,
                                MAX(CASE WHEN date(fecha) = date(?) THEN 1 ELSE 0 END) AS has_trip
                            FROM viajes
                            GROUP BY patente
                        ) h ON h.patente = v.patente
                    """
                    params.extend([week_start, today_iso, month_start, today_iso, today_iso])
                else:
                    select_sql += """
                        LEFT JOIN (SELECT '' AS patente, 0 AS c7, 0 AS km7) k7 ON k7.patente = v.patente
                        LEFT JOIN (SELECT '' AS patente, 0 AS c30, 0 AS km30) k30 ON k30.patente = v.patente
                        LEFT JOIN (SELECT '' AS patente, 0 AS has_open, 0 AS has_trip) h ON h.patente = v.patente
                    """

                rows_top = con.execute(select_sql, params).fetchall()
                items = []
                for r in rows_top:
                    patente = (_row_value(r, "patente", "") or "").strip()
                    alias = (_row_value(r, "alias", "") or "").strip()
                    activo = int(_row_value(r, "activo", 1) or 1)
                    has_open = int(_row_value(r, "has_open", 0) or 0)
                    if activo == 0:
                        estado = "No disponible"
                    elif has_open:
                        estado = "En uso"
                    else:
                        estado = "Disponible"

                    if estado == "En uso":
                        ubicacion = "En calle"
                    else:
                        base_ciudad = (_row_value(r, "base_ciudad", "") or "").strip()
                        lugar = (_row_value(r, "lugar_reservado", "") or "").strip()
                        ubicacion = base_ciudad or lugar or "—"

                    c7 = int(_row_value(r, "c7", 0) or 0)
                    c30 = int(_row_value(r, "c30", 0) or 0)
                    km7 = _row_value(r, "km7", 0)
                    km30 = _row_value(r, "km30", 0)
                    km_semana = round(float(km7), 1) if c7 > 0 and km7 is not None else "—"
                    km_mes = round(float(km30), 1) if c30 > 0 and km30 is not None else "—"

                    items.append({
                        "patente": patente or "—",
                        "alias": alias or "—",
                        "ubicacion": ubicacion,
                        "kmSemana": km_semana,
                        "kmMes": km_mes,
                        "estado": estado,
                    })

                estado_order = {
                    "Disponible": 0,
                    "Pendiente cierre": 1,
                    "En uso": 2,
                    "No disponible": 3,
                }

                def _sort_key(item):
                    km = item["kmSemana"] if isinstance(item["kmSemana"], (int, float)) else 10**9
                    return (estado_order.get(item["estado"], 9), km, item["patente"])

                items.sort(key=_sort_key)
                data["vehiculos"]["topAsignacion"] = items[:5]

        if _table_exists(con, "viajes") and {"fecha", "patente"}.issubset(viajes_cols):
            km_expr = "COALESCE(vj.recorrido_km, (vj.km_fin - vj.km_ini), 0)"
            hora_salida_expr = "COALESCE(vj.hora_salida, '')" if "hora_salida" in viajes_cols else "''"
            hora_regreso_expr = "COALESCE(vj.hora_regreso_estimada, '')" if "hora_regreso_estimada" in viajes_cols else "''"
            conds = []
            if "largo" in viajes_cols:
                conds.append("COALESCE(vj.largo, 0) = 1")
            if "recorrido_km" in viajes_cols:
                conds.append("COALESCE(vj.recorrido_km, 0) >= 120")
            where_largos = "(" + " OR ".join(conds) + ")" if conds else "1=1"

            join_chofer = ""
            chofer_expr = "''"
            if _table_exists(con, "agentes_intendencia") and "chofer_id" in viajes_cols:
                join_chofer = "LEFT JOIN agentes_intendencia ai ON ai.id = vj.chofer_id"
                chofer_expr = "COALESCE(ai.agente, '')"

            join_destino = ""
            destino_expr = "''"
            if _table_exists(con, "destinos") and "destino_id" in viajes_cols:
                join_destino = "LEFT JOIN destinos d ON d.id = vj.destino_id"
                destino_expr = "COALESCE(d.nombre, '')"

            estado_expr = "UPPER(COALESCE(vj.estado, ''))" if "estado" in viajes_cols else "''"

            try:
                rows_mov = con.execute(f"""
                    SELECT
                        vj.id AS id,
                        vj.patente AS patente,
                        {chofer_expr} AS chofer,
                        {destino_expr} AS destino,
                        vj.fecha AS fecha,
                        {hora_salida_expr} AS hora_salida,
                        {hora_regreso_expr} AS hora_regreso_estimada,
                        {estado_expr} AS estado,
                        CASE WHEN {estado_expr} IN ('ABIERTO','EN CURSO','EN_CURSO','PENDIENTE CIERRE','PENDIENTE_CIERRE') THEN 1 ELSE 0 END AS is_open,
                        CASE WHEN date(vj.fecha)=date(?) THEN 1 ELSE 0 END AS is_today
                    FROM viajes vj
                    {join_chofer}
                    {join_destino}
                    WHERE ({estado_expr} IN ('ABIERTO','EN CURSO','EN_CURSO','PENDIENTE CIERRE','PENDIENTE_CIERRE') OR date(vj.fecha) = date(?))
                    ORDER BY is_open DESC, date(vj.fecha) DESC, vj.id DESC
                """, (today_iso, today_iso)).fetchall()

                seen_pat = set()
                mov = []
                for r in rows_mov:
                    pat = (_row_value(r, "patente", "") or "").strip()
                    if not pat or pat in seen_pat:
                        continue
                    seen_pat.add(pat)
                    mov.append({
                        "patente": pat,
                        "chofer": (_row_value(r, "chofer", "") or "").strip() or "-",
                        "destino": (_row_value(r, "destino", "") or "").strip() or "-",
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "horaSalida": (_row_value(r, "hora_salida", "") or "").strip(),
                        "horaRegresoEstimada": (_row_value(r, "hora_regreso_estimada", "") or "").strip(),
                        "estado": (_row_value(r, "estado", "") or "").strip(),
                    })
                data["vehiculos"]["movimientosHoy"] = mov
            except Exception:
                pass

            try:
                rows_viajes = con.execute(f"""
                    SELECT
                        vj.fecha AS fecha,
                        vj.patente AS patente,
                        {chofer_expr} AS chofer,
                        {destino_expr} AS destino,
                        {hora_salida_expr} AS hora_salida,
                        {hora_regreso_expr} AS hora_regreso_estimada,
                        {km_expr} AS km
                    FROM viajes vj
                    {join_chofer}
                    {join_destino}
                    WHERE date(vj.fecha) <= date(?)
                      AND date(vj.fecha) >= date(?)
                      AND {where_largos}
                    ORDER BY date(vj.fecha) DESC, COALESCE({km_expr}, 0) DESC, vj.id DESC
                    LIMIT 5
                """, (today_iso, month_start)).fetchall()

                data["vehiculos"]["ultimosViajesLargos"] = [{
                    "fecha": (_row_value(r, "fecha", "") or "").strip(),
                    "chofer": (_row_value(r, "chofer", "") or "").strip() or "-",
                    "destino": (_row_value(r, "destino", "") or "").strip() or "-",
                    "vehiculo": (_row_value(r, "patente", "") or "").strip() or "-",
                    "horaSalida": (_row_value(r, "hora_salida", "") or "").strip(),
                    "horaRegresoEstimada": (_row_value(r, "hora_regreso_estimada", "") or "").strip(),
                } for r in rows_viajes]
            except Exception:
                pass

        # =========================
        # MATERIALES - 3 CONTADORES
        # =========================
        tabla_pedidos = None
        # Prioridad: usar el flujo operativo del dashboard (calendario_pedidos)
        # para que los contadores Pedir/Pedido/Entregado reflejen el estado actual.
        if _table_exists(con, "calendario_pedidos"):
            tabla_pedidos = "calendario_pedidos"
        else:
            for t in ("pedidos_materiales", "materiales_pedidos"):
                if _table_exists(con, t):
                    tabla_pedidos = t
                    try:
                        n = int(_row_value(con.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone(), "n", 0) or 0)
                        if n > 0:
                            break
                    except Exception:
                        pass

        if tabla_pedidos:
            cols = _table_cols(con, tabla_pedidos)
            if "estado" in cols:
                try:
                    if tabla_pedidos == "calendario_pedidos":
                        # Flujo real: Generado -> En compras -> Recibido -> Cerrado
                        rows = con.execute(f"""
                            SELECT UPPER(COALESCE(estado, '')) AS estado, COUNT(*) AS n
                            FROM {tabla_pedidos}
                            GROUP BY UPPER(COALESCE(estado, ''))
                        """).fetchall()
                        for r in rows:
                            est = (_row_value(r, "estado", "") or "").strip()
                            n = int(_row_value(r, "n", 0) or 0)
                            if any(k in est for k in ("GENERADO", "PENDIENTE_INTENDENCIA", "PENDIENTE", "PEDIR", "NUEVO")):
                                data["materiales"]["internosPendientes"] += n
                            elif any(k in est for k in ("EN COMPRAS", "COMPRA", "AUTORIZADO", "PEDIDO")):
                                data["materiales"]["enviadosCompra"] += n

                        # Recibido hoy (no acumulado)
                        if "fecha_recibido" in cols:
                            row_r = con.execute(f"""
                                SELECT COUNT(*) AS n
                                FROM {tabla_pedidos}
                                WHERE UPPER(COALESCE(estado,'')) IN ('RECIBIDO')
                                  AND date(fecha_recibido) = date(?)
                            """, (today_iso,)).fetchone()
                        else:
                            row_r = con.execute(f"""
                                SELECT COUNT(*) AS n
                                FROM {tabla_pedidos}
                                WHERE UPPER(COALESCE(estado,'')) IN ('RECIBIDO')
                                  AND date(fecha) = date(?)
                            """, (today_iso,)).fetchone()
                        data["materiales"]["entregasPendientesCierre"] = int(_row_value(row_r, "n", 0) or 0)
                    else:
                        rows = con.execute(f"""
                            SELECT UPPER(COALESCE(estado, '')) AS estado, COUNT(*) AS n
                            FROM {tabla_pedidos}
                            GROUP BY UPPER(COALESCE(estado, ''))
                        """).fetchall()
                        for r in rows:
                            est = (_row_value(r, "estado", "") or "").strip()
                            n = int(_row_value(r, "n", 0) or 0)
                            if any(k in est for k in ("PEDIR", "PENDIENTE", "NUEVO", "BORRADOR", "CARGA")):
                                data["materiales"]["internosPendientes"] += n
                            elif any(k in est for k in ("PEDIDO", "COMPRA", "ENVIADO", "SOLICITADO")):
                                data["materiales"]["enviadosCompra"] += n
                            elif any(k in est for k in ("ENTREGADO", "ENTREGA", "CIERRE", "CERRAR")):
                                data["materiales"]["entregasPendientesCierre"] += n
                except Exception:
                    pass
            else:
                try:
                    if tabla_pedidos == "calendario_pedidos" and "prioridad" in cols:
                        rows = con.execute(f"""
                            SELECT UPPER(COALESCE(prioridad, 'MEDIA')) AS prioridad, COUNT(*) AS n
                            FROM {tabla_pedidos}
                            GROUP BY UPPER(COALESCE(prioridad, 'MEDIA'))
                        """).fetchall()
                        for r in rows:
                            pr = (_row_value(r, "prioridad", "") or "").strip()
                            n = int(_row_value(r, "n", 0) or 0)
                            if "ALTA" in pr:
                                data["materiales"]["internosPendientes"] += n
                            elif "BAJA" in pr:
                                data["materiales"]["entregasPendientesCierre"] += n
                            else:
                                data["materiales"]["enviadosCompra"] += n
                    else:
                        row_all = con.execute(f"SELECT COUNT(*) AS n FROM {tabla_pedidos}").fetchone()
                        data["materiales"]["internosPendientes"] = int(_row_value(row_all, "n", 0) or 0)
                except Exception:
                    pass

        # =========================
        # OBRAS DEL DIA
        # =========================
        if _table_exists(con, "obras_sede"):
            cols_obras = _table_cols(con, "obras_sede")
            estado_expr = "UPPER(COALESCE(estado, ''))" if "estado" in cols_obras else "''"
            f_ini = "fecha_inicio" if "fecha_inicio" in cols_obras else None
            f_fin = "fecha_fin_real" if "fecha_fin_real" in cols_obras else None
            prioridad_expr = "UPPER(COALESCE(prioridad, ''))" if "prioridad" in cols_obras else "''"
            ext_expr_parts = []
            for c in ("codigo_sede", "titulo", "descripcion", "observaciones", "tipo"):
                if c in cols_obras:
                    ext_expr_parts.append(f"COALESCE({c}, '')")
            ext_expr = " || ' ' || ".join(ext_expr_parts) if ext_expr_parts else "''"

            try:
                where_en_curso = f"{estado_expr} IN ('EN_CURSO','EN CURSO')"
                if f_ini:
                    where_en_curso += " AND (fecha_inicio IS NULL OR date(fecha_inicio) <= date(?))"
                if f_fin:
                    where_en_curso += " AND (fecha_fin_real IS NULL OR date(fecha_fin_real) >= date(?))"
                params = [today_iso] * (where_en_curso.count("?"))
                row = con.execute(f"SELECT COUNT(*) AS n FROM obras_sede WHERE {where_en_curso}", params).fetchone()
                data["obras"]["enEjecucionHoy"] = int(_row_value(row, "n", 0) or 0)
            except Exception:
                pass

            if f_fin:
                try:
                    row = con.execute(
                        "SELECT COUNT(*) AS n FROM obras_sede WHERE fecha_fin_real IS NOT NULL AND date(fecha_fin_real) = date(?)",
                        (today_iso,),
                    ).fetchone()
                    data["obras"]["cerradasHoy"] = int(_row_value(row, "n", 0) or 0)
                except Exception:
                    pass

            try:
                row = con.execute(f"""
                    SELECT COUNT(*) AS n
                    FROM obras_sede
                    WHERE {prioridad_expr} IN ('ALTA', 'URGENTE')
                      AND {estado_expr} NOT IN ('FINALIZADA','CERRADA','CERRADO')
                      AND LOWER({ext_expr}) NOT LIKE '%midefensa%'
                """).fetchone()
                data["obras"]["urgenciasExternas"] = int(_row_value(row, "n", 0) or 0)
            except Exception:
                pass

            # =========================
            # DESINFECCION (desde OBRAS)
            # =========================
            try:
                desinf_cols = [c for c in ("tipo", "titulo", "descripcion") if c in cols_obras]
                if f_fin and desinf_cols and "codigo_sede" in cols_obras:
                    where_parts = [f"LOWER(COALESCE({c}, '')) LIKE '%desinfecc%'" for c in desinf_cols]
                    where_desinf = "(" + " OR ".join(where_parts) + ")"

                    # Ultima realizada (fecha_fin_real)
                    last_date = ""
                    last_sedes = []
                    row_last = con.execute(
                        f"SELECT MAX(date({f_fin})) AS d FROM obras_sede WHERE {where_desinf} AND {f_fin} IS NOT NULL AND TRIM(COALESCE({f_fin},'')) <> ''"
                    ).fetchone()
                    last_date = (_row_value(row_last, "d", "") or "").strip()
                    if last_date:
                        rows_last = con.execute(f"""
                            SELECT DISTINCT UPPER(TRIM(COALESCE(codigo_sede,''))) AS sede
                            FROM obras_sede
                            WHERE {where_desinf}
                              AND {f_fin} IS NOT NULL
                              AND date({f_fin}) = date(?)
                              AND TRIM(COALESCE(codigo_sede,'')) <> ''
                            ORDER BY sede
                        """, (last_date,)).fetchall()
                        seen = set()
                        for rr in rows_last:
                            sede = (_row_value(rr, "sede", "") or "").strip().upper()
                            if sede and sede not in seen:
                                seen.add(sede)
                                last_sedes.append(sede)

                    # Proxima programada: fecha_inicio -> fecha_fin_prevista -> fecha_solicitud
                    date_candidates = []
                    if f_ini:
                        date_candidates.append(f"NULLIF(TRIM({f_ini}), '')")
                    if "fecha_fin_prevista" in cols_obras:
                        date_candidates.append("NULLIF(TRIM(fecha_fin_prevista), '')")
                    if "fecha_solicitud" in cols_obras:
                        date_candidates.append("NULLIF(TRIM(fecha_solicitud), '')")

                    next_date = ""
                    next_sedes = []
                    next_group = ""
                    next_label = ""
                    if date_candidates:
                        date_expr = "date(COALESCE(" + ",".join(date_candidates) + "))"
                        sub_rows = con.execute(f"""
                            SELECT *
                            FROM (
                                SELECT
                                    id,
                                    UPPER(TRIM(COALESCE(codigo_sede,''))) AS sede,
                                    COALESCE(titulo,'') AS titulo,
                                    COALESCE(tipo,'') AS tipo,
                                    COALESCE(descripcion,'') AS descripcion,
                                    {date_expr} AS fecha_prog,
                                    COALESCE({f_fin},'') AS fecha_fin_real_raw
                                FROM obras_sede
                                WHERE {where_desinf}
                                  AND (COALESCE({f_fin}, '') = '' OR TRIM(COALESCE({f_fin}, '')) = '')
                            ) t
                            WHERE fecha_prog IS NOT NULL AND TRIM(COALESCE(fecha_prog,'')) <> ''
                              AND date(fecha_prog) >= date(?)
                            ORDER BY date(fecha_prog) ASC, id ASC
                            LIMIT 120
                        """, (today_iso,)).fetchall()

                        if sub_rows:
                            next_date = (_row_value(sub_rows[0], "fecha_prog", "") or "").strip()
                            seen = set()
                            txts = []
                            for rr in sub_rows:
                                dprog = (_row_value(rr, "fecha_prog", "") or "").strip()
                                if dprog != next_date:
                                    break
                                sede = (_row_value(rr, "sede", "") or "").strip().upper()
                                if sede and sede not in seen:
                                    seen.add(sede)
                                    next_sedes.append(sede)
                                txts.append(" ".join([
                                    (_row_value(rr, "titulo", "") or "").strip(),
                                    (_row_value(rr, "tipo", "") or "").strip(),
                                    (_row_value(rr, "descripcion", "") or "").strip(),
                                ]).strip())

                            text_upper = " ".join([t for t in txts if t]).upper()
                            for i in (1, 2, 3):
                                if (f"GR{i}" in text_upper) or (f"GR {i}" in text_upper) or (f"GRUPO {i}" in text_upper):
                                    next_group = f"Grupo {i}"
                                    break

                            if "FERIA" in text_upper and "JUDICIAL" in text_upper:
                                if ("PRIMERA" in text_upper) or ("1RA" in text_upper) or ("1ª" in text_upper):
                                    next_label = "Primera semana de Feria Judicial"
                                elif ("SEGUNDA" in text_upper) or ("2DA" in text_upper) or ("2ª" in text_upper):
                                    next_label = "Segunda semana de Feria Judicial"
                                else:
                                    next_label = "Feria Judicial"
                        else:
                            # fallback: si no hay futura, tomar la mas antigua pendiente (vencida)
                            ov_rows = con.execute(f"""
                                SELECT *
                                FROM (
                                    SELECT
                                        id,
                                        UPPER(TRIM(COALESCE(codigo_sede,''))) AS sede,
                                        COALESCE(titulo,'') AS titulo,
                                        COALESCE(tipo,'') AS tipo,
                                        COALESCE(descripcion,'') AS descripcion,
                                        {date_expr} AS fecha_prog,
                                        COALESCE({f_fin},'') AS fecha_fin_real_raw
                                    FROM obras_sede
                                    WHERE {where_desinf}
                                      AND (COALESCE({f_fin}, '') = '' OR TRIM(COALESCE({f_fin}, '')) = '')
                                ) t
                                WHERE fecha_prog IS NOT NULL AND TRIM(COALESCE(fecha_prog,'')) <> ''
                                  AND date(fecha_prog) < date(?)
                                ORDER BY date(fecha_prog) ASC, id ASC
                                LIMIT 120
                            """, (today_iso,)).fetchall()

                            if ov_rows:
                                next_date = (_row_value(ov_rows[0], "fecha_prog", "") or "").strip()
                                seen = set()
                                txts = []
                                for rr in ov_rows:
                                    dprog = (_row_value(rr, "fecha_prog", "") or "").strip()
                                    if dprog != next_date:
                                        break
                                    sede = (_row_value(rr, "sede", "") or "").strip().upper()
                                    if sede and sede not in seen:
                                        seen.add(sede)
                                        next_sedes.append(sede)
                                    txts.append(" ".join([
                                        (_row_value(rr, "titulo", "") or "").strip(),
                                        (_row_value(rr, "tipo", "") or "").strip(),
                                        (_row_value(rr, "descripcion", "") or "").strip(),
                                    ]).strip())

                                text_upper = " ".join([t for t in txts if t]).upper()
                                for i in (1, 2, 3):
                                    if (f"GR{i}" in text_upper) or (f"GR {i}" in text_upper) or (f"GRUPO {i}" in text_upper):
                                        next_group = f"Grupo {i}"
                                        break

                                if "FERIA" in text_upper and "JUDICIAL" in text_upper:
                                    if ("PRIMERA" in text_upper) or ("1RA" in text_upper) or ("1ª" in text_upper):
                                        next_label = "Primera semana de Feria Judicial"
                                    elif ("SEGUNDA" in text_upper) or ("2DA" in text_upper) or ("2ª" in text_upper):
                                        next_label = "Segunda semana de Feria Judicial"
                                    else:
                                        next_label = "Feria Judicial"

                    status = ""
                    try:
                        if next_date:
                            nd = date.fromisoformat(next_date)
                            status = "Vencida" if nd < today else "Programada"
                        elif last_date:
                            status = "Finalizada"
                    except Exception:
                        status = "Programada" if next_date else ("Finalizada" if last_date else "")

                    data["desinfeccion"] = {
                        "last": {"fecha": last_date, "sedes": last_sedes, "grupo": "", "label": ""},
                        "next": {"fecha": next_date, "sedes": next_sedes, "grupo": next_group, "label": next_label},
                        "status": status,
                    }
            except Exception:
                pass

        # =========================
        # MATAFUEGOS (proximos vencimientos)
        # =========================
        if _table_exists(con, "matafuegos_sede"):
            try:
                cols_mata = _table_cols(con, "matafuegos_sede")
                if {"fecha_vencimiento", "cod_sede"}.issubset(set(cols_mata or [])):
                    where_activo = "COALESCE(activo,1)=1" if "activo" in cols_mata else "1=1"

                    row_next = con.execute(f"""
                        SELECT MIN(date(fecha_vencimiento)) AS d
                        FROM matafuegos_sede
                        WHERE {where_activo}
                          AND fecha_vencimiento IS NOT NULL
                          AND TRIM(COALESCE(fecha_vencimiento,'')) <> ''
                    """).fetchone()

                    next_date = (_row_value(row_next, "d", "") or "").strip()
                    next_sedes = []
                    days_left = None
                    if next_date:
                        try:
                            dnext = date.fromisoformat(next_date)
                            days_left = int((dnext - today).days)
                        except Exception:
                            days_left = None

                        rows_sedes = con.execute(f"""
                            SELECT DISTINCT UPPER(TRIM(COALESCE(cod_sede,''))) AS sede
                            FROM matafuegos_sede
                            WHERE {where_activo}
                              AND date(fecha_vencimiento) = date(?)
                              AND TRIM(COALESCE(cod_sede,'')) <> ''
                            ORDER BY sede
                        """, (next_date,)).fetchall()
                        seen = set()
                        for rr in rows_sedes:
                            sede = (_row_value(rr, "sede", "") or "").strip().upper()
                            if sede and sede not in seen:
                                seen.add(sede)
                                next_sedes.append(sede)

                    end_45 = (today + timedelta(days=45)).isoformat()
                    row_45 = con.execute(f"""
                        SELECT COUNT(*) AS n
                        FROM matafuegos_sede
                        WHERE {where_activo}
                          AND fecha_vencimiento IS NOT NULL
                          AND TRIM(COALESCE(fecha_vencimiento,'')) <> ''
                          AND date(fecha_vencimiento) >= date(?)
                          AND date(fecha_vencimiento) <= date(?)
                    """, (today_iso, end_45)).fetchone()
                    count_45 = int(_row_value(row_45, "n", 0) or 0)

                    data["matafuegos"] = {
                        "next": {"fecha": next_date, "sedes": next_sedes},
                        "days_left": days_left,
                        "count_45d": count_45,
                    }
            except Exception:
                pass

        # =========================
        # LIMPIEZA - PENDIENTES SUPERVISOR
        # =========================
        try:
            if _table_exists(con, "sedes_control_limpieza_cierres"):
                row = con.execute("""
                    SELECT COUNT(*) AS n
                    FROM sedes_control_limpieza_cierres
                    WHERE COALESCE(estado,'EN_CARGA') = 'CERRADO_POR_AGENTE'
                """).fetchone()
                data["limpieza"]["pendientesRevision"] = int(_row_value(row, "n", 0) or 0)
        except Exception:
            pass

        # =========================
        # HORARIOS ESPECIALES / MAILS
        # =========================
        if _table_exists(con, "eventos"):
            cols_eventos = _table_cols(con, "eventos")
            if {"fecha", "titulo"}.issubset(cols_eventos):
                try:
                    row = con.execute("""
                        SELECT COUNT(*) AS n
                        FROM eventos
                        WHERE date(fecha) <= date(?)
                          AND LOWER(COALESCE(titulo, '')) LIKE '%enviar mail autorizando horario especial%'
                    """, (today_iso,)).fetchone()
                    data["horarios"]["pendienteMail"] = int(_row_value(row, "n", 0) or 0)
                except Exception:
                    pass
                try:
                    row = con.execute("""
                        SELECT COUNT(*) AS n
                        FROM eventos
                        WHERE date(fecha) = date(?)
                          AND (
                                LOWER(COALESCE(titulo, '')) LIKE '%mail enviado%'
                             OR LOWER(COALESCE(detalle, '')) LIKE '%mail enviado%'
                          )
                    """, (today_iso,)).fetchone()
                    data["horarios"]["enviadosHoy"] = int(_row_value(row, "n", 0) or 0)
                except Exception:
                    pass

        if _table_exists(con, "viajes") and "fecha" in viajes_cols:
            chofer_cond = "(chofer_id IS NULL OR chofer_id = 0)" if "chofer_id" in viajes_cols else "1=0"
            try:
                row = con.execute(f"""
                    SELECT COUNT(*) AS n
                    FROM viajes
                    WHERE date(fecha) >= date(?,'start of month','+1 month')
                      AND date(fecha) <  date(?,'start of month','+2 month')
                      AND {chofer_cond}
                """, (today_iso, today_iso)).fetchone()
                data["horarios"]["turnosChoferesSinAsignarMes"] = int(_row_value(row, "n", 0) or 0)
            except Exception:
                pass

        if _table_exists(con, "agentes_licencias"):
            cols_lic = _table_cols(con, "agentes_licencias")
            if {"fecha_desde", "fecha_hasta"}.issubset(cols_lic):
                estado_expr = "UPPER(COALESCE(estado,''))" if "estado" in cols_lic else "''"
                try:
                    row = con.execute(f"""
                        SELECT COUNT(*) AS n
                        FROM agentes_licencias
                        WHERE date(fecha_desde) <= date(?)
                          AND date(fecha_hasta) >= date(?)
                          AND {estado_expr} NOT IN ('RECHAZADA','RECHAZADO')
                    """, (today_iso, today_iso)).fetchone()
                    data["licenciasHoy"] = int(_row_value(row, "n", 0) or 0)
                except Exception:
                    pass
                try:
                    rows_lic = con.execute(f"""
                        SELECT
                            COALESCE(ai.agente, '-') AS agente,
                            COALESCE(al.tipo, '') AS tipo,
                            COALESCE(al.fecha_desde, '') AS desde,
                            COALESCE(al.fecha_hasta, '') AS hasta
                        FROM agentes_licencias al
                        LEFT JOIN agentes_intendencia ai ON ai.id = al.agente_id
                        WHERE date(al.fecha_desde) <= date(?)
                          AND date(al.fecha_hasta) >= date(?)
                          AND {estado_expr} NOT IN ('RECHAZADA','RECHAZADO')
                        ORDER BY ai.agente
                        LIMIT 30
                    """, (today_iso, today_iso)).fetchall()
                    data["asignacionDia"]["licenciasDia"] = [{
                        "agente": (_row_value(r, "agente", "-") or "-").strip(),
                        "tipo": (_row_value(r, "tipo", "") or "").strip(),
                        "desde": (_row_value(r, "desde", "") or "").strip(),
                        "hasta": (_row_value(r, "hasta", "") or "").strip(),
                    } for r in rows_lic]
                except Exception:
                    pass

        if _table_exists(con, "agentes_compensatorios_mov"):
            try:
                rows_comp = con.execute("""
                    SELECT
                        COALESCE(ai.agente, '-') AS agente,
                        COALESCE(ac.desde, '') AS desde,
                        COALESCE(ac.hasta, '') AS hasta,
                        COALESCE(ac.tipo, '') AS tipo
                    FROM agentes_compensatorios_mov ac
                    LEFT JOIN agentes_intendencia ai ON ai.id = ac.agente_id
                    WHERE UPPER(COALESCE(ac.tipo,'')) = 'TOMA'
                      AND TRIM(COALESCE(ac.desde,'')) <> ''
                      AND TRIM(COALESCE(ac.hasta,'')) <> ''
                      AND date(ac.desde) <= date(?)
                      AND date(ac.hasta) >= date(?)
                    ORDER BY ai.agente
                    LIMIT 40
                """, (today_iso, today_iso)).fetchall()
                data["asignacionDia"]["compensatoriosActivos"] = [{
                    "agente": (_row_value(r, "agente", "-") or "-").strip(),
                    "desde": (_row_value(r, "desde", "") or "").strip(),
                    "hasta": (_row_value(r, "hasta", "") or "").strip(),
                    "tipo": (_row_value(r, "tipo", "") or "").strip(),
                } for r in rows_comp]
            except Exception:
                pass

        if _table_exists(con, "agentes_intendencia"):
            try:
                choferes_permitidos = (
                    "Emiliano P de la Puente",
                    "Emiliano Perez de la Puente",
                    "Ignacio Baroni",
                    "Mauro Vea Murguia",
                    "Luis Cardozo",
                )
                rows_ch = con.execute("""
                    SELECT COALESCE(agente,'') AS agente
                    FROM agentes_intendencia
                    WHERE COALESCE(activo,1)=1
                      AND LOWER(COALESCE(rubro,''))='choferes'
                      AND agente IN ({})
                    ORDER BY agente
                """.format(",".join(["?"] * len(choferes_permitidos))), choferes_permitidos).fetchall()
                choferes = [(_row_value(r, "agente", "") or "").strip() for r in rows_ch if (_row_value(r, "agente", "") or "").strip()]
                data["asignacionDia"]["choferes"] = choferes
                data["asignacionDia"]["turnoMesChoferes"] = [{"agente": x, "nota": "urgencias / findes / feriados"} for x in choferes]
                data["asignacionDia"]["turnoSemanaVespertino"] = [{"agente": x, "nota": "vespertino semanal"} for x in choferes]
            except Exception:
                pass

        # Rotacion activa: mes y proxima fecha (la asignacion se completa mas abajo cuando ya tenemos grupos/sedes)
        try:
            meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                     "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            data["asignacionDia"]["rotacionActiva"]["mes"] = f"{meses[today.month - 1]} {today.year}"
            nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            data["asignacionDia"]["rotacionActiva"]["proximaFecha"] = nxt.isoformat()
        except Exception:
            pass

        try:
            _ensure_dashboard_turnos_choferes_cfg(con)
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
            data["asignacionDia"]["turnosCfg"] = {
                "mesMensual": (_row_value(row_cfg, "mes_mensual", "") or "").strip(),
                "choferMensual": (_row_value(row_cfg, "chofer_mensual", "") or "").strip(),
                "semanaDesde": (_row_value(row_cfg, "semana_desde", "") or "").strip(),
                "semanaHasta": (_row_value(row_cfg, "semana_hasta", "") or "").strip(),
                "choferSemanal": (_row_value(row_cfg, "chofer_semanal", "") or "").strip(),
            }

            meses_l = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            guard = data["asignacionDia"].get("guardiasPasivas", {})
            plan = guard.get("plan2026", [])
            plan_by_mes = {str(x.get("mes", "")).strip().lower(): str(x.get("chofer", "")).strip() for x in plan if str(x.get("mes", "")).strip()}

            mes_cfg = str(data["asignacionDia"]["turnosCfg"].get("mesMensual", "") or "").strip().lower()
            if mes_cfg not in meses_l:
                mes_cfg = meses_l[today.month - 1]
            chofer_m = str(data["asignacionDia"]["turnosCfg"].get("choferMensual", "") or "").strip()
            if not chofer_m:
                chofer_m = plan_by_mes.get(mes_cfg, "")

            mm = (meses_l.index(mes_cfg) + 1) if mes_cfg in meses_l else today.month
            periodo_m = f"{today.year}-{mm:02d}"

            semanal_desde = str(data["asignacionDia"]["turnosCfg"].get("semanaDesde", "") or "").strip()
            semanal_hasta = str(data["asignacionDia"]["turnosCfg"].get("semanaHasta", "") or "").strip()
            chofer_s = str(data["asignacionDia"]["turnosCfg"].get("choferSemanal", "") or "").strip()
            periodo_s = (semanal_desde + "|" + semanal_hasta) if (semanal_desde and semanal_hasta) else ""

            _ensure_dashboard_turnos_choferes_ack_table(con)

            ack_m = None
            if chofer_m:
                ack_m = con.execute("""
                    SELECT COALESCE(aceptado_en,'') AS aceptado_en
                    FROM dashboard_turnos_choferes_ack
                    WHERE tipo='mensual' AND periodo_ref=? AND chofer=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (periodo_m, chofer_m)).fetchone()
            ack_s = None
            if chofer_s and periodo_s:
                ack_s = con.execute("""
                    SELECT COALESCE(aceptado_en,'') AS aceptado_en
                    FROM dashboard_turnos_choferes_ack
                    WHERE tipo='semanal' AND periodo_ref=? AND chofer=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (periodo_s, chofer_s)).fetchone()

            data["asignacionDia"]["guardiasPasivas"]["mensual"] = {
                "estado": "aceptada" if ack_m else "pendiente",
                "texto": ("Aceptada" if ack_m else "Pendiente de aceptacion"),
                "aceptadoEn": (_row_value(ack_m, "aceptado_en", "") if ack_m else "") or "",
                "chofer": chofer_m,
                "periodo": periodo_m,
                "mes": mes_cfg,
            }
            data["asignacionDia"]["guardiasPasivas"]["semanal"] = {
                "estado": "aceptada" if ack_s else "pendiente",
                "texto": ("Aceptada" if ack_s else "Pendiente de aceptacion"),
                "aceptadoEn": (_row_value(ack_s, "aceptado_en", "") if ack_s else "") or "",
                "chofer": chofer_s,
                "periodo": periodo_s,
                "desde": semanal_desde,
                "hasta": semanal_hasta,
            }
        except Exception:
            pass

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

        if _table_exists(con, "dashboard_sede_estado"):
            try:
                row_n = con.execute("SELECT COUNT(*) AS n FROM dashboard_sede_estado").fetchone()
                n = int(_row_value(row_n, "n", 0) or 0)
                if n == 0:
                    codigos = []
                    if _table_exists(con, "sedes_mpd"):
                        rows_s = con.execute("""
                            SELECT UPPER(COALESCE(codigo,'')) AS codigo
                            FROM sedes_mpd
                            WHERE TRIM(COALESCE(codigo,'')) <> ''
                            ORDER BY codigo
                            LIMIT 20
                        """).fetchall()
                        codigos = [(_row_value(r, "codigo", "") or "").strip() for r in rows_s]
                    if not codigos:
                        codigos = [f"S{str(i).zfill(2)}" for i in range(1, 21)]
                    for c in codigos:
                        if c:
                            con.execute("INSERT OR IGNORE INTO dashboard_sede_estado(sede_codigo) VALUES (?)", (c,))
                    con.commit()
            except Exception:
                pass

            try:
                rows_est = con.execute("""
                    SELECT
                        UPPER(COALESCE(sede_codigo,'')) AS sede_codigo,
                        COALESCE(relevamiento,0) AS relevamiento,
                        COALESCE(obra_terminada,0) AS obra_terminada,
                        COALESCE(matafuegos_recarga,0) AS matafuegos_recarga,
                        COALESCE(carteleria,0) AS carteleria,
                        COALESCE(luces_emergencia,0) AS luces_emergencia,
                        COALESCE(plano_evac,0) AS plano_evac,
                        COALESCE(orden_limpieza,0) AS orden_limpieza,
                        COALESCE(senalizacion,0) AS senalizacion,
                        COALESCE(accesibilidad,0) AS accesibilidad,
                        COALESCE(riesgo_electrico,0) AS riesgo_electrico
                    FROM dashboard_sede_estado
                    ORDER BY sede_codigo
                """).fetchall()
                items = []
                for r in rows_est:
                    vals = [int(_row_value(r, v, 0) or 0) for v in SEDE_ESTADO_VARS]
                    pts = sum(1 if v > 0 else 0 for v in vals)
                    pct = int(round((pts / 10.0) * 100))
                    items.append({
                        "sede": (_row_value(r, "sede_codigo", "") or "").strip() or "-",
                        "puntos": pts,
                        "pct": pct,
                    })
                data["sedeEstado"]["items"] = items
                if items:
                    data["sedeEstado"]["promedioPct"] = int(round(sum(x["pct"] for x in items) / len(items)))
            except Exception:
                pass

        if _table_exists(con, "sedes_limpieza"):
            rows_dist = []
            snapshot = "hoy"
            try:
                rows_dist = con.execute("""
                    SELECT UPPER(COALESCE(cod_sede, '')) AS sede, COUNT(*) AS n
                    FROM sedes_limpieza
                    WHERE (fecha_desde IS NULL OR date(fecha_desde) <= date(?))
                      AND (fecha_hasta IS NULL OR date(fecha_hasta) >= date(?))
                    GROUP BY UPPER(COALESCE(cod_sede, ''))
                    ORDER BY sede
                """, (today_iso, today_iso)).fetchall()
            except Exception:
                rows_dist = []

            if not rows_dist:
                snapshot = "ultimo corte"
                try:
                    row_ym = con.execute("""
                        SELECT MAX(substr(fecha_desde, 1, 7)) AS ym
                        FROM sedes_limpieza
                        WHERE fecha_desde IS NOT NULL AND TRIM(fecha_desde) <> ''
                    """).fetchone()
                    ym = (_row_value(row_ym, "ym", "") or "").strip()
                    if ym:
                        rows_dist = con.execute("""
                            SELECT UPPER(COALESCE(cod_sede, '')) AS sede, COUNT(*) AS n
                            FROM sedes_limpieza
                            WHERE substr(COALESCE(fecha_desde, ''), 1, 7) = ?
                            GROUP BY UPPER(COALESCE(cod_sede, ''))
                            ORDER BY sede
                        """, (ym,)).fetchall()
                except Exception:
                    rows_dist = []

            dist = []
            for r in rows_dist:
                sede = (_row_value(r, "sede", "") or "").strip()
                n = int(_row_value(r, "n", 0) or 0)
                if sede:
                    dist.append({"sede": sede, "cantidad": n})
            data["personal"]["distribucion"] = dist
            data["personal"]["totalAsignado"] = sum(int(x.get("cantidad", 0) or 0) for x in dist)
            data["personal"]["snapshot"] = snapshot

            try:
                rows_turn = con.execute("""
                    SELECT
                        UPPER(COALESCE(cod_sede,'')) AS sede,
                        COALESCE(turno,'') AS turno,
                        COALESCE(responsable,'') AS responsable
                    FROM sedes_limpieza
                    WHERE (fecha_desde IS NULL OR date(fecha_desde) <= date(?))
                      AND (fecha_hasta IS NULL OR date(fecha_hasta) >= date(?))
                    ORDER BY sede, responsable
                    LIMIT 80
                """, (today_iso, today_iso)).fetchall()
                data["asignacionDia"]["limpiezaTurnosSede"] = [{
                    "sede": (_row_value(r, "sede", "") or "").strip(),
                    "turno": (_row_value(r, "turno", "") or "").strip() or "s/d",
                    "responsable": (_row_value(r, "responsable", "") or "").strip() or "-",
                } for r in rows_turn if (_row_value(r, "sede", "") or "").strip()]
            except Exception:
                pass

            if _table_exists(con, "sedes_mpd"):
                try:
                    row_total_sedes = con.execute("SELECT COUNT(*) AS n FROM sedes_mpd").fetchone()
                    total_sedes = int(_row_value(row_total_sedes, "n", 0) or 0)
                    data["personal"]["sedesSinPersonal"] = max(total_sedes - len(dist), 0)
                except Exception:
                    pass

        if _table_exists(con, "agentes_intendencia"):
            try:
                rows_limp = con.execute("""
                    SELECT COALESCE(agente,'') AS agente
                    FROM agentes_intendencia
                    WHERE COALESCE(activo,1)=1
                      AND LOWER(COALESCE(rubro,''))='limpieza'
                    ORDER BY agente
                """).fetchall()
                noms = [(_row_value(r, "agente", "") or "").strip() for r in rows_limp if (_row_value(r, "agente", "") or "").strip()]
                grupos = [[], [], [], []]
                for i, nom in enumerate(noms):
                    grupos[i % 4].append(nom)
                data["asignacionDia"]["gruposLimpieza"] = [{
                    "grupo": f"GR{idx + 1}",
                    "agentes": grupos[idx],
                } for idx in range(4)]
            except Exception:
                pass

        # Rotacion mensual automatica S01 -> S08 -> S13 -> S14 (editable luego en UI)
        try:
            sedes_ciclo = ["S01", "S08", "S13", "S14"]
            grupos_cfg = data["asignacionDia"].get("gruposLimpieza", []) or []
            grupos_map = {}
            for g in grupos_cfg:
                gk = str(g.get("grupo", "")).strip().upper()
                if not gk:
                    continue
                arr = g.get("agentes") if isinstance(g.get("agentes"), list) else []
                grupos_map[gk] = [str(x or "").strip() for x in arr if str(x or "").strip()]

            grp_codes = [g for g in ["GR1", "GR2", "GR3", "GR4"] if g in grupos_map]
            if not grp_codes:
                grp_codes = ["GR1", "GR2", "GR3", "GR4"]

            month_offset = (int(today.month) - 1) % len(grp_codes)
            filas = []
            for idx_sede, sede in enumerate(sedes_ciclo):
                grp = grp_codes[(idx_sede - month_offset) % len(grp_codes)]
                ags = grupos_map.get(grp, [])
                filas.append({
                    "sede": sede,
                    "grupo": grp,
                    "matutino": (ags[0] if len(ags) > 0 else "-"),
                    "vespertino": (ags[1] if len(ags) > 1 else "-"),
                })
            # Aplica ediciones manuales guardadas para el mes actual.
            try:
                _ensure_dashboard_rotacion_limpieza_table(con)
                ym = today.strftime("%Y-%m")
                rows_ov = con.execute("""
                    SELECT
                        UPPER(COALESCE(sede,'')) AS sede,
                        LOWER(COALESCE(turno,'')) AS turno,
                        COALESCE(grupo,'') AS grupo,
                        COALESCE(agente,'') AS agente
                    FROM dashboard_rotacion_limpieza
                    WHERE mes_ref = ?
                """, (ym,)).fetchall()
                by_sede = {str(x.get("sede", "")).strip().upper(): x for x in filas}
                for r in rows_ov:
                    sede = (_row_value(r, "sede", "") or "").strip().upper()
                    turno = (_row_value(r, "turno", "") or "").strip().lower()
                    agente = (_row_value(r, "agente", "") or "").strip()
                    grupo = (_row_value(r, "grupo", "") or "").strip()
                    if not sede or sede not in by_sede:
                        continue
                    if grupo:
                        by_sede[sede]["grupo"] = grupo
                    if "vesp" in turno or "tarde" in turno:
                        by_sede[sede]["vespertino"] = agente or by_sede[sede].get("vespertino", "-")
                    else:
                        by_sede[sede]["matutino"] = agente or by_sede[sede].get("matutino", "-")
            except Exception:
                pass
            data["asignacionDia"]["rotacionActiva"]["filas"] = filas
        except Exception:
            pass

        if _table_exists(con, "viajes") and "fecha" in viajes_cols:
            km_expr = "0"
            if "recorrido_km" in viajes_cols and {"km_ini", "km_fin"}.issubset(viajes_cols):
                km_expr = "COALESCE(recorrido_km, (km_fin - km_ini), 0)"
            elif "recorrido_km" in viajes_cols:
                km_expr = "COALESCE(recorrido_km, 0)"
            elif {"km_ini", "km_fin"}.issubset(viajes_cols):
                km_expr = "COALESCE((km_fin - km_ini), 0)"

            try:
                rows = con.execute(f"""
                    SELECT patente, SUM({km_expr}) AS km
                    FROM viajes
                    WHERE strftime('%Y', fecha) = '2026'
                      AND TRIM(COALESCE(patente, '')) <> ''
                    GROUP BY patente
                    HAVING SUM({km_expr}) > 0
                    ORDER BY SUM({km_expr}) DESC, patente
                    LIMIT 8
                """).fetchall()
                data["indicadores2026"]["kmPorVehiculo"] = [{
                    "label": (_row_value(r, "patente", "") or "").strip() or "-",
                    "km": round(float(_row_value(r, "km", 0) or 0), 1),
                } for r in rows]
            except Exception:
                pass

            chofer_expr = "COALESCE(v.agente_trasladado, '')"
            join_sql = ""
            if "chofer_id" in viajes_cols and _table_exists(con, "agentes_intendencia"):
                chofer_expr = "COALESCE(ai.agente, '')"
                join_sql = "LEFT JOIN agentes_intendencia ai ON ai.id = v.chofer_id"

            try:
                rows = con.execute(f"""
                    SELECT {chofer_expr} AS chofer, SUM({km_expr}) AS km
                    FROM viajes v
                    {join_sql}
                    WHERE strftime('%Y', v.fecha) = '2026'
                      AND TRIM({chofer_expr}) <> ''
                    GROUP BY {chofer_expr}
                    HAVING SUM({km_expr}) > 0
                    ORDER BY SUM({km_expr}) DESC, {chofer_expr}
                    LIMIT 8
                """).fetchall()
                data["indicadores2026"]["kmPorChofer"] = [{
                    "label": (_row_value(r, "chofer", "") or "").strip() or "-",
                    "km": round(float(_row_value(r, "km", 0) or 0), 1),
                } for r in rows]
            except Exception:
                pass

            data["indicadores2026"]["totalKm"] = round(
                sum(float(x.get("km", 0) or 0) for x in data["indicadores2026"]["kmPorVehiculo"]), 1
            )

        if _table_exists(con, "eventos"):
            cols_ev = _table_cols(con, "eventos")
            if {"fecha", "titulo"}.issubset(cols_ev):
                try:
                    rows_mes = con.execute("""
                        SELECT fecha, COUNT(*) AS n
                        FROM eventos
                        WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', ?)
                        GROUP BY fecha
                        ORDER BY fecha
                    """, (today_iso,)).fetchall()
                    data["calendario"]["diasConEventos"] = [{
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "n": int(_row_value(r, "n", 0) or 0),
                    } for r in rows_mes]

                    rows_meta = con.execute("""
                        SELECT fecha, fuente, color, titulo, detalle, COUNT(*) AS n
                        FROM eventos
                        WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', ?)
                        GROUP BY fecha, fuente, color, titulo, detalle
                        ORDER BY fecha
                    """, (today_iso,)).fetchall()
                    meta = {}
                    for r in rows_meta:
                        f = (_row_value(r, "fecha", "") or "").strip()
                        if not f:
                            continue
                        if f not in meta:
                            meta[f] = {"colores": set(), "critica": False}
                        col = (_row_value(r, "color", "") or "").strip()
                        if col:
                            meta[f]["colores"].add(col)
                        src = (_row_value(r, "fuente", "") or "").lower()
                        txt = (
                            (_row_value(r, "titulo", "") or "") + " " +
                            (_row_value(r, "detalle", "") or "")
                        ).lower()
                        if any(k in txt for k in ("urgente", "venc", "crit", "pendiente")) or src in ("obras", "seguridad"):
                            meta[f]["critica"] = True
                    data["calendario"]["diasMeta"] = {
                        k: {
                            "colores": sorted(list(v["colores"]))[:3],
                            "critica": bool(v["critica"]),
                        } for k, v in meta.items()
                    }
                except Exception:
                    pass

                try:
                    rows_hoy = con.execute("""
                        SELECT fecha, titulo, detalle, fuente, color
                        FROM eventos
                        WHERE date(fecha) = date(?)
                        ORDER BY id DESC
                        LIMIT 8
                    """, (today_iso,)).fetchall()
                    data["calendario"]["hoy"] = [{
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "titulo": (_row_value(r, "titulo", "") or "").strip(),
                        "detalle": (_row_value(r, "detalle", "") or "").strip(),
                        "fuente": (_row_value(r, "fuente", "") or "").strip(),
                        "color": (_row_value(r, "color", "") or "").strip(),
                    } for r in rows_hoy]
                except Exception:
                    pass

                try:
                    rows_7 = con.execute("""
                        SELECT fecha, titulo, detalle, fuente, color
                        FROM eventos
                        WHERE date(fecha) >= date(?)
                          AND date(fecha) <= date(?,'+6 day')
                        ORDER BY date(fecha), id
                        LIMIT 20
                    """, (today_iso, today_iso)).fetchall()
                    data["calendario"]["proximos7"] = [{
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "titulo": (_row_value(r, "titulo", "") or "").strip(),
                        "detalle": (_row_value(r, "detalle", "") or "").strip(),
                        "fuente": (_row_value(r, "fuente", "") or "").strip(),
                        "color": (_row_value(r, "color", "") or "").strip(),
                    } for r in rows_7]
                except Exception:
                    pass

                data["calendario"]["resumen"]["eventosHoy"] = len(data["calendario"]["hoy"])
                data["calendario"]["resumen"]["eventos7"] = len(data["calendario"]["proximos7"])
                crit = 0
                for ev in data["calendario"]["proximos7"]:
                    txt = (ev.get("titulo", "") + " " + ev.get("detalle", "")).lower()
                    col = (ev.get("color", "") or "").lower()
                    if any(k in txt for k in ("urgente", "venc", "crit", "pendiente")) or any(
                        c in col for c in ("#dc2626", "#ef4444", "#b91c1c")
                    ):
                        crit += 1
                data["calendario"]["resumen"]["alertasCriticas"] = crit

        if _table_exists(con, "calendario_pedidos"):
            try:
                rows_mes_p = con.execute("""
                    SELECT fecha, COUNT(*) AS n
                    FROM calendario_pedidos
                    WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', ?)
                    GROUP BY fecha
                    ORDER BY fecha
                """, (today_iso,)).fetchall()
                by_fecha = {x["fecha"]: int(x["n"]) for x in data["calendario"]["diasConEventos"] if x.get("fecha")}
                for r in rows_mes_p:
                    f = (_row_value(r, "fecha", "") or "").strip()
                    by_fecha[f] = int(by_fecha.get(f, 0)) + int(_row_value(r, "n", 0) or 0)
                    if f:
                        if f not in data["calendario"]["diasMeta"]:
                            data["calendario"]["diasMeta"][f] = {"colores": [], "critica": False}
                        cols = set(data["calendario"]["diasMeta"][f].get("colores", []))
                        cols.add("#0ea5e9")
                        data["calendario"]["diasMeta"][f]["colores"] = sorted(list(cols))[:3]
                data["calendario"]["diasConEventos"] = [
                    {"fecha": f, "n": by_fecha[f]} for f in sorted(by_fecha.keys()) if f
                ]

                rows_hoy_p = con.execute("""
                    SELECT fecha, sede, solicitante, detalle, prioridad, estado
                    FROM calendario_pedidos
                    WHERE date(fecha) = date(?)
                    ORDER BY id DESC
                    LIMIT 8
                """, (today_iso,)).fetchall()
                for r in rows_hoy_p:
                    det = (_row_value(r, "detalle", "") or "").strip()
                    sede = (_row_value(r, "sede", "") or "").strip()
                    sol = (_row_value(r, "solicitante", "") or "").strip()
                    est = (_row_value(r, "estado", "") or "").strip()
                    titulo = "Pedido / novedad"
                    if sede:
                        titulo += f" ({sede})"
                    data["calendario"]["hoy"].append({
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "titulo": titulo,
                        "detalle": (det or sol or "").strip(),
                        "estado": est or "Pedir",
                        "fuente": "calendario_pedidos",
                        "color": "#0ea5e9",
                    })
                data["calendario"]["hoy"] = data["calendario"]["hoy"][:8]

                rows_7_p = con.execute("""
                    SELECT fecha, sede, solicitante, detalle, prioridad, estado
                    FROM calendario_pedidos
                    WHERE date(fecha) >= date(?)
                      AND date(fecha) <= date(?,'+6 day')
                    ORDER BY date(fecha), id
                    LIMIT 20
                """, (today_iso, today_iso)).fetchall()
                for r in rows_7_p:
                    det = (_row_value(r, "detalle", "") or "").strip()
                    sede = (_row_value(r, "sede", "") or "").strip()
                    sol = (_row_value(r, "solicitante", "") or "").strip()
                    est = (_row_value(r, "estado", "") or "").strip()
                    titulo = "Pedido / novedad"
                    if sede:
                        titulo += f" ({sede})"
                    data["calendario"]["proximos7"].append({
                        "fecha": (_row_value(r, "fecha", "") or "").strip(),
                        "titulo": titulo,
                        "detalle": (det or sol or "").strip(),
                        "estado": est or "Pedir",
                        "fuente": "calendario_pedidos",
                        "color": "#0ea5e9",
                    })
                data["calendario"]["proximos7"].sort(key=lambda x: (x.get("fecha", ""), x.get("titulo", "")))
                data["calendario"]["proximos7"] = data["calendario"]["proximos7"][:20]

                row_p_hoy = con.execute(
                    "SELECT COUNT(*) AS n FROM calendario_pedidos WHERE date(fecha) = date(?)",
                    (today_iso,),
                ).fetchone()
                pedidos_hoy = int(_row_value(row_p_hoy, "n", 0) or 0)
                data["calendario"]["resumen"]["eventosHoy"] = len(data["calendario"]["hoy"])
                data["calendario"]["resumen"]["eventos7"] = len(data["calendario"]["proximos7"])
                if pedidos_hoy > 0:
                    data["recordatorios"].append(f"{pedidos_hoy} recordatorio/s de materiales hoy")
            except Exception:
                pass

        if int(data["horarios"]["turnosChoferesSinAsignarMes"] or 0) > 0:
            data["recordatorios"].append(
                f"{int(data['horarios']['turnosChoferesSinAsignarMes'])} turnos de chofer sin asignar (proximo mes)"
            )
        if int(data["horarios"]["pendienteMail"] or 0) > 0:
            data["recordatorios"].append(
                f"{int(data['horarios']['pendienteMail'])} mails de horario especial pendientes"
            )
        if int(data["materiales"]["internosPendientes"] or 0) > 0:
            data["recordatorios"].append(
                f"{int(data['materiales']['internosPendientes'])} pedidos internos de materiales"
            )

        # Catalogos para carga manual de vehiculos en dashboard
        try:
            _ensure_dashboard_vehiculos_cfg(con)
            row_vcfg = con.execute("""
                SELECT COALESCE(responsable_tactico,'Ignacio Baroni') AS responsable_tactico
                FROM dashboard_vehiculos_cfg
                WHERE id=1
            """).fetchone()
            data["vehiculos"]["proceso"]["responsableTactico"] = (
                (_row_value(row_vcfg, "responsable_tactico", "Ignacio Baroni") or "Ignacio Baroni").strip()
            )

            if _table_exists(con, "vehiculos"):
                vrows = con.execute("""
                    SELECT
                        COALESCE(patente, '') AS patente,
                        COALESCE(codigo_interno, '') AS alias
                    FROM vehiculos
                    WHERE COALESCE(activo, 1) = 1
                    ORDER BY codigo_interno, patente
                """).fetchall()
                data["vehiculos"]["catalogos"]["vehiculos"] = [
                    {
                        "value": (_row_value(r, "patente", "") or "").strip(),
                        "label": ((_row_value(r, "alias", "") or "").strip() + " - " + (_row_value(r, "patente", "") or "").strip()).strip(" -"),
                    }
                    for r in vrows
                    if (_row_value(r, "patente", "") or "").strip()
                ]
            if _table_exists(con, "agentes_intendencia"):
                crows = con.execute("""
                    SELECT COALESCE(agente, '') AS agente
                    FROM agentes_intendencia
                    WHERE COALESCE(activo, 1) = 1
                      AND LOWER(COALESCE(rubro, '')) = 'choferes'
                    ORDER BY agente
                """).fetchall()
                data["vehiculos"]["catalogos"]["choferes"] = [
                    (_row_value(r, "agente", "") or "").strip()
                    for r in crows
                    if (_row_value(r, "agente", "") or "").strip()
                ]
            if _table_exists(con, "destinos"):
                drows = con.execute("""
                    SELECT COALESCE(nombre, '') AS nombre
                    FROM destinos
                    WHERE COALESCE(activo, 1) = 1
                    ORDER BY nombre
                """).fetchall()
                data["vehiculos"]["catalogos"]["destinos"] = [
                    (_row_value(r, "nombre", "") or "").strip()
                    for r in drows
                    if (_row_value(r, "nombre", "") or "").strip()
                ]
        except Exception:
            pass

        # =========================
        # VEHICULOS - CARGA MANUAL (dashboard)
        # =========================
        try:
            _ensure_dashboard_vehiculos_manual_table(con)
            rows_vm = con.execute("""
                SELECT
                    id,
                    COALESCE(fecha,'') AS fecha,
                    COALESCE(vehiculo,'') AS vehiculo,
                    COALESCE(chofer,'') AS chofer,
                    COALESCE(destino,'') AS destino,
                    COALESCE(hora_salida,'') AS hora_salida,
                    COALESCE(hora_regreso_estimada,'') AS hora_regreso_estimada,
                    COALESCE(estado,'En uso') AS estado,
                    COALESCE(combustible,'') AS combustible,
                    COALESCE(materiales,'') AS materiales,
                    COALESCE(agente_traslado,'') AS agente_traslado,
                    COALESCE(observaciones,'') AS observaciones
                FROM dashboard_vehiculos_manual
                WHERE date(fecha) = date(?)
                ORDER BY id DESC
                LIMIT 80
            """, (today_iso,)).fetchall()
            data["vehiculos"]["manualMovimientos"] = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "vehiculo": (_row_value(r, "vehiculo", "") or "").strip(),
                "chofer": (_row_value(r, "chofer", "") or "").strip(),
                "destino": (_row_value(r, "destino", "") or "").strip(),
                "horaSalida": (_row_value(r, "hora_salida", "") or "").strip(),
                "horaRegresoEstimada": (_row_value(r, "hora_regreso_estimada", "") or "").strip(),
                "estado": (_row_value(r, "estado", "En uso") or "En uso").strip(),
                "combustible": (_row_value(r, "combustible", "") or "").strip(),
                "materiales": (_row_value(r, "materiales", "") or "").strip(),
                "agenteTraslado": (_row_value(r, "agente_traslado", "") or "").strip(),
                "observaciones": (_row_value(r, "observaciones", "") or "").strip(),
            } for r in rows_vm]
        except Exception:
            pass

        # =========================
        # OBRAS - NOVEDADES DEL DIA
        # =========================
        try:
            _ensure_dashboard_novedades_obra_table(con)
            rows_nov = con.execute("""
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
                ORDER BY id DESC
                LIMIT 12
            """, (today_iso,)).fetchall()
            data["obras"]["novedadesHoy"] = [{
                "id": int(_row_value(r, "id", 0) or 0),
                "fecha": (_row_value(r, "fecha", "") or "").strip(),
                "texto": (_row_value(r, "texto", "") or "").strip(),
                "urgente": int(_row_value(r, "urgente", 0) or 0),
                "tipo": (_row_value(r, "tipo", "novedad") or "novedad").strip(),
                "estado": (_row_value(r, "estado", "nuevo") or "nuevo").strip(),
                "responsable": (_row_value(r, "responsable", "") or "").strip(),
            } for r in rows_nov if (_row_value(r, "texto", "") or "").strip()]
            data["obras"]["novedadesCount"] = len(data["obras"]["novedadesHoy"])
        except Exception:
            pass

        con.close()
        return data

    app.config["DASHBOARD_OPERATIVO_DATA_FN"] = _dashboard_operativo_data

    def _vehiculos_cards_from_base(base, con):
        vehiculos_cards = []
        veh_lookup = {}
        if _table_exists(con, "vehiculos"):
            rows = con.execute("""
                SELECT patente, tipo, combustible, base_ciudad, lugar_reservado, activo
                FROM vehiculos
            """).fetchall()
            for r in rows:
                pat = (_row_value(r, "patente", "") or "").strip()
                if not pat:
                    continue
                veh_lookup[pat] = {
                    "tipo": (_row_value(r, "tipo", "") or "").strip(),
                    "combustible": (_row_value(r, "combustible", "") or "").strip(),
                    "base": (_row_value(r, "base_ciudad", "") or "").strip(),
                    "lugar": (_row_value(r, "lugar_reservado", "") or "").strip(),
                    "activo": int(_row_value(r, "activo", 1) or 1),
                }

        base_items = ((base.get("vehiculos") or {}).get("topAsignacion") or [])
        if not base_items and veh_lookup:
            for pat, v in list(veh_lookup.items())[:6]:
                base_items.append({
                    "patente": pat,
                    "alias": "-",
                    "ubicacion": v.get("base") or v.get("lugar") or "-",
                    "kmSemana": "-",
                    "kmMes": "-",
                    "estado": "Disponible" if v.get("activo", 1) else "No disponible",
                })

        def _bar_pct(estado):
            if estado == "Disponible":
                return 80
            if estado == "En uso":
                return 60
            if estado == "Pendiente cierre":
                return 40
            if estado == "No disponible":
                return 15
            return 50

        for item in base_items[:8]:
            pat = (item.get("patente") or "").strip() or "-"
            v = veh_lookup.get(pat, {})
            km = item.get("kmSemana")
            if not isinstance(km, (int, float)):
                km = item.get("kmMes")
            km_txt = f"{km} km" if isinstance(km, (int, float)) else "-"
            estado = item.get("estado") or "Sin datos"
            vehiculos_cards.append({
                "patente": pat,
                "estado": estado,
                "combustible": v.get("combustible") or "-",
                "km": km_txt,
                "sede": item.get("ubicacion") or v.get("base") or v.get("lugar") or "-",
                "uso": v.get("tipo") or "-",
                "bar": _bar_pct(estado),
            })
        return vehiculos_cards

    def _obras_sedes_resumen(con):
        obras_sedes = []
        obras_total = 0
        obras_donut = ""
        sedes_lookup = {}
        if _table_exists(con, "sedes_mpd"):
            rows = con.execute("SELECT codigo, nombre, direccion FROM sedes_mpd").fetchall()
            for r in rows:
                cod = (_row_value(r, "codigo", "") or "").strip().upper()
                if not cod:
                    continue
                sedes_lookup[cod] = {
                    "nombre": (_row_value(r, "nombre", "") or "").strip(),
                    "direccion": (_row_value(r, "direccion", "") or "").strip(),
                }

        if _table_exists(con, "obras_sede"):
            cols_obras = _table_cols(con, "obras_sede")
            if "codigo_sede" in cols_obras:
                rows = con.execute("""
                    SELECT UPPER(TRIM(COALESCE(codigo_sede, ''))) AS sede, COUNT(*) AS n
                    FROM obras_sede
                    WHERE TRIM(COALESCE(codigo_sede, '')) <> ''
                    GROUP BY UPPER(TRIM(COALESCE(codigo_sede, '')))
                    ORDER BY n DESC, sede ASC
                """).fetchall()

                obras_total = sum(int(_row_value(r, "n", 0) or 0) for r in rows)
                palette = ["#8ac5ff", "#9fe8b8", "#f5d08a", "#f2b0c3", "#b9b6f5", "#9fd9e7", "#f3c89a", "#c6e6b0"]
                acc = 0.0
                donut_parts = []
                for idx, r in enumerate(rows[:8]):
                    n = int(_row_value(r, "n", 0) or 0)
                    if n <= 0 or obras_total <= 0:
                        continue
                    sede = (_row_value(r, "sede", "") or "").strip().upper()
                    meta = sedes_lookup.get(sede, {})
                    label = meta.get("direccion") or meta.get("nombre") or sede or "Sede"
                    pct = round((n / obras_total) * 100, 1)
                    color = palette[idx % len(palette)]
                    obras_sedes.append({
                        "codigo": sede,
                        "label": label,
                        "pct": pct,
                        "n": n,
                        "color": color,
                    })
                    start = acc
                    end = acc + pct
                    donut_parts.append(f"{color} {start}%, {color} {end}%")
                    acc = end

                if obras_total > 0 and acc < 100:
                    donut_parts.append(f"#e8eef7 {acc}%, #e8eef7 100%")
                obras_donut = "conic-gradient(" + ", ".join(donut_parts) + ")" if donut_parts else ""

        return obras_sedes, obras_total, obras_donut

    @app.route("/dashboard/sgi", endpoint="sgi_home")
    def sgi_home():
        def _to_int(v, default=0):
            try:
                return int(v if v is not None else default)
            except Exception:
                try:
                    return int(float(v))
                except Exception:
                    return int(default)

        today_iso = date.today().isoformat()
        sgi = {
            "vehiculos": {
                "total": 0,
                "estado": "Sin datos",
                "fuera_servicio": 0,
            },
            "obras": {
                "pendientes": 0,
                "en_curso": 0,
                "alta_prioridad": 0,
            },
            "sedes": {
                "total": 20,
                "con_alertas": 0,
            },
            "seguimiento": {
                "estado": "Activo",
                "novedades_hoy": 0,
            },
            "alertas": {
                "estado": "Monitoreo",
                "criticas": 0,
            },
            "alcance": {
                "sigla": "MPD",
                "texto": "Cobertura operativa institucional",
            },
        }

        base = {}
        try:
            base = _dashboard_operativo_data() or {}
        except Exception:
            base = {}

        donut = ((base.get("vehiculos") or {}).get("donut") or {})
        veh_total = _to_int(donut.get("total"), 0)
        veh_fuera = _to_int(donut.get("noDisponibles"), 0)
        if veh_total <= 0:
            veh_estado = "Sin datos"
        elif veh_fuera >= veh_total:
            veh_estado = "Fuera de servicio"
        elif veh_fuera > 0:
            veh_estado = "Atencion"
        else:
            veh_estado = "Normal"
        sgi["vehiculos"]["total"] = veh_total
        sgi["vehiculos"]["fuera_servicio"] = veh_fuera
        sgi["vehiculos"]["estado"] = veh_estado

        try:
            sgi["alertas"]["criticas"] = len(_dashboard_alertas_criticas(base) or [])
        except Exception:
            sgi["alertas"]["criticas"] = 0

        con = get_db()
        try:
            if _table_exists(con, "obras_sede"):
                cols_obras = _table_cols(con, "obras_sede")
                estado_expr = "UPPER(TRIM(COALESCE(estado,'')))" if "estado" in cols_obras else "''"
                prioridad_expr = "UPPER(TRIM(COALESCE(prioridad,'')))" if "prioridad" in cols_obras else "''"

                row_obras = con.execute(f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN {estado_expr} = 'PENDIENTE' THEN 1 ELSE 0 END), 0) AS pendientes,
                        COALESCE(SUM(CASE WHEN {estado_expr} IN ('EN_CURSO','EN CURSO') THEN 1 ELSE 0 END), 0) AS en_curso,
                        COALESCE(SUM(CASE WHEN {prioridad_expr} IN ('ALTA','URGENTE')
                            AND {estado_expr} NOT IN ('FINALIZADA','CERRADA','CERRADO') THEN 1 ELSE 0 END), 0) AS alta_prioridad
                    FROM obras_sede
                """).fetchone()

                sgi["obras"]["pendientes"] = _to_int(_row_value(row_obras, "pendientes", 0), 0)
                sgi["obras"]["en_curso"] = _to_int(_row_value(row_obras, "en_curso", 0), 0)
                sgi["obras"]["alta_prioridad"] = _to_int(_row_value(row_obras, "alta_prioridad", 0), 0)

                if "codigo_sede" in cols_obras:
                    row_sedes_alerta = con.execute(f"""
                        SELECT COUNT(DISTINCT UPPER(TRIM(COALESCE(codigo_sede,'')))) AS n
                        FROM obras_sede
                        WHERE {prioridad_expr} IN ('ALTA','URGENTE')
                          AND {estado_expr} NOT IN ('FINALIZADA','CERRADA','CERRADO')
                          AND TRIM(COALESCE(codigo_sede,'')) <> ''
                    """).fetchone()
                    sgi["sedes"]["con_alertas"] = _to_int(_row_value(row_sedes_alerta, "n", 0), 0)

            if _table_exists(con, "sedes_mpd"):
                row_sedes = con.execute("SELECT COUNT(*) AS n FROM sedes_mpd").fetchone()
                total_sedes = _to_int(_row_value(row_sedes, "n", 0), 0)
                if total_sedes > 0:
                    sgi["sedes"]["total"] = total_sedes

            _ensure_novedades_diarias_table(con)
            resumen_nvd = _novedades_resumen(con, today_iso)
            nvd_diarias = _to_int((resumen_nvd or {}).get("total"), 0)
            nvd_obras = _to_int(((base.get("obras") or {}).get("novedadesCount")), 0)
            sgi["seguimiento"]["novedades_hoy"] = nvd_diarias + nvd_obras
        except Exception:
            pass
        finally:
            try:
                con.close()
            except Exception:
                pass

        if _to_int(sgi["sedes"].get("con_alertas"), 0) <= 0 and _to_int(sgi["alertas"].get("criticas"), 0) > 0:
            sgi["sedes"]["con_alertas"] = min(
                _to_int(sgi["alertas"].get("criticas"), 0),
                max(_to_int(sgi["sedes"].get("total"), 20), 0),
            )

        # =========================
        # BLOQUE VEHICULOS OPERATIVOS + OBRAS POR SEDE
        # =========================
        vehiculos_cards = []
        obras_sedes = []
        obras_total = 0
        obras_donut = ""

        con = get_db()
        try:
            vehiculos_cards = _vehiculos_cards_from_base(base, con)
            obras_sedes, obras_total, obras_donut = _obras_sedes_resumen(con)
        except Exception:
            pass
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgi_home.html",
            sgi=sgi,
            vehiculos_cards=vehiculos_cards,
            obras_sedes=obras_sedes,
            obras_total=obras_total,
            obras_donut=obras_donut,
        )

    @app.route("/dashboard/alta-direccion", endpoint="dashboard_ejecutivo")
    def dashboard_ejecutivo():
        base = {}
        try:
            base = _dashboard_operativo_data() or {}
        except Exception:
            base = {}

        con = get_db()
        con.row_factory = sqlite3.Row
        try:
            # =========================
            # KPIs GENERALES
            # =========================
            sedes_activas = 0
            if _table_exists(con, "sedes_mpd"):
                cols_sedes = _table_cols(con, "sedes_mpd")
                if "activa" in cols_sedes:
                    row = con.execute("SELECT COUNT(*) AS n FROM sedes_mpd WHERE COALESCE(activa,1)=1").fetchone()
                else:
                    row = con.execute("SELECT COUNT(*) AS n FROM sedes_mpd").fetchone()
                sedes_activas = int(_row_value(row, "n", 0) or 0)

            obras_en_curso = 0
            pendientes_criticos = 0
            obras_total = 0
            obras_finalizadas = 0
            if _table_exists(con, "obras_sede"):
                cols_obras = _table_cols(con, "obras_sede")
                estado_expr = "UPPER(TRIM(COALESCE(estado,'')))" if "estado" in cols_obras else "''"
                prioridad_expr = "UPPER(TRIM(COALESCE(prioridad,'')))" if "prioridad" in cols_obras else "''"
                row = con.execute(f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN {estado_expr} IN ('EN_CURSO','EN CURSO') THEN 1 ELSE 0 END),0) AS en_curso,
                        COALESCE(SUM(CASE WHEN {estado_expr} IN ('FINALIZADA','CERRADA','CERRADO') THEN 1 ELSE 0 END),0) AS finalizadas,
                        COALESCE(COUNT(*),0) AS total,
                        COALESCE(SUM(CASE WHEN {prioridad_expr} IN ('ALTA','URGENTE')
                            AND {estado_expr} NOT IN ('FINALIZADA','CERRADA','CERRADO') THEN 1 ELSE 0 END),0) AS criticas
                    FROM obras_sede
                """).fetchone()
                obras_en_curso = int(_row_value(row, "en_curso", 0) or 0)
                pendientes_criticos = int(_row_value(row, "criticas", 0) or 0)
                obras_total = int(_row_value(row, "total", 0) or 0)
                obras_finalizadas = int(_row_value(row, "finalizadas", 0) or 0)

            donut = (base.get("vehiculos") or {}).get("donut") or {}
            veh_total = int(donut.get("total") or 0)
            veh_no_disp = int(donut.get("noDisponibles") or 0)
            veh_operativos = max(veh_total - veh_no_disp, 0)

            # =========================
            # SG-SST (progreso por sede)
            # =========================
            sedes_sst, items_sst = _dashboard_sede_estado_read(con)
            sst_avg = 0
            if items_sst:
                sst_avg = round(sum([i.get("pct", 0) for i in items_sst]) / len(items_sst), 1)
            if sst_avg >= 85:
                sst_estado = "Adecuado"
                sst_estado_cls = "ok"
            elif sst_avg >= 70:
                sst_estado = "En progreso"
                sst_estado_cls = "warn"
            elif items_sst:
                sst_estado = "Critico"
                sst_estado_cls = "bad"
            else:
                sst_estado = "Sin datos"
                sst_estado_cls = "na"

            sst_etapa = "-"
            if _table_exists(con, "sst_objetivo_acciones"):
                cols_acc = _table_cols(con, "sst_objetivo_acciones")
                if "fase" in cols_acc:
                    row = con.execute("""
                        SELECT UPPER(TRIM(COALESCE(fase,''))) AS fase, COUNT(*) AS n
                        FROM sst_objetivo_acciones
                        WHERE TRIM(COALESCE(fase,'')) <> ''
                        GROUP BY UPPER(TRIM(COALESCE(fase,'')))
                        ORDER BY n DESC
                        LIMIT 1
                    """).fetchone()
                    fase = (row["fase"] if row else "") or ""
                    if "PLANIFIC" in fase:
                        sst_etapa = "Planificacion"
                    elif "IMPLEMENT" in fase:
                        sst_etapa = "Implementacion"
                    elif "EVAL" in fase:
                        sst_etapa = "Evaluacion"

            # =========================
            # SEDES (cards ejecutivas)
            # =========================
            sedes_cards = []
            if _table_exists(con, "sedes_mpd"):
                rows_sedes = con.execute("""
                    SELECT codigo, nombre, ciudad, direccion, fuero
                    FROM sedes_mpd
                    WHERE TRIM(COALESCE(codigo,'')) <> ''
                    ORDER BY codigo
                """).fetchall()

                def _safe_int(v):
                    try:
                        return int(v or 0)
                    except Exception:
                        return 0

                for s in rows_sedes:
                    cod = (_row_value(s, "codigo", "") or "").strip().upper()
                    if not cod:
                        continue

                    infra = con.execute("""
                        SELECT oficinas, salas_entrevistas, banios, espacios_comunes, depositos, personas,
                               m2_totales, m2_por_persona, personas_por_oficina
                        FROM sedes_infraestructura
                        WHERE sede_codigo = ?
                    """, (cod,)).fetchone() if _table_exists(con, "sedes_infraestructura") else None

                    metricas_row = con.execute("""
                        SELECT sede_codigo, m2_totales, personas, oficinas, depositos, actualizado_en
                        FROM sedes_metricas
                        WHERE sede_codigo = ?
                    """, (cod,)).fetchone() if _table_exists(con, "sedes_metricas") else None
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
                        base_oc = float(oficinas_m) * 2.5
                        if base_oc:
                            ocupacion_pct = round((float(personas_m) / base_oc) * 100.0, 1)

                    depositos_kpi = 0
                    if depositos_m is not None:
                        depositos_kpi = depositos_m
                    else:
                        try:
                            depositos_kpi = con.execute(
                                "SELECT COUNT(*) AS c FROM sedes_depositos WHERE codigo_sede = ?",
                                (cod,)
                            ).fetchone()["c"]
                        except Exception:
                            depositos_kpi = _row_value(infra, "depositos", 0) if infra else 0

                    per_kpi = con.execute("""
                        SELECT COALESCE(COUNT(*),0) AS personas
                        FROM personal_sede
                        WHERE codigo_sede = ?
                          AND COALESCE(activo,1)=1
                    """, (cod,)).fetchone() if _table_exists(con, "personal_sede") else {"personas": 0}

                    puestos_trabajo = 0
                    if _table_exists(con, "luminarias_sede"):
                        try:
                            row_pt = con.execute("""
                                SELECT COALESCE(SUM(COALESCE(puestos_trabajo,0)),0) AS n
                                FROM luminarias_sede
                                WHERE codigo_sede = ?
                            """, (cod,)).fetchone()
                            puestos_trabajo = _safe_int(_row_value(row_pt, "n", 0))
                        except Exception:
                            puestos_trabajo = 0

                    seg_vencen = 0
                    if _table_exists(con, "matafuegos_sede"):
                        try:
                            row_v = con.execute("""
                                SELECT COALESCE(COUNT(*),0) AS vencen_pronto
                                FROM matafuegos_sede
                                WHERE cod_sede = ?
                                  AND COALESCE(activo,1)=1
                                  AND fecha_vencimiento IS NOT NULL
                                  AND date(fecha_vencimiento) <= date('now','+45 day')
                            """, (cod,)).fetchone()
                            seg_vencen = _safe_int(_row_value(row_v, "vencen_pronto", 0))
                        except Exception:
                            seg_vencen = 0

                    infra_oficinas = _safe_int(_row_value(infra, "oficinas", 0) if infra else 0)
                    infra_entrev = _safe_int(_row_value(infra, "salas_entrevistas", 0) if infra else 0)
                    infra_banios = _safe_int(_row_value(infra, "banios", 0) if infra else 0)
                    infra_comunes = _safe_int(_row_value(infra, "espacios_comunes", 0) if infra else 0)
                    infra_depositos = _safe_int(_row_value(infra, "depositos", 0) if infra else 0)

                    m2pp_base = m2_por_persona if m2_por_persona is not None else None
                    amb_oficinas = (oficinas_m if oficinas_m is not None else infra_oficinas) or 0
                    amb_depositos = (depositos_m if depositos_m is not None else infra_depositos) or 0
                    amb_utiles = amb_oficinas + infra_entrev + infra_banios + infra_comunes
                    amb_total = amb_utiles + amb_depositos
                    factor_deposito = (amb_depositos / amb_total) if amb_total > 0 else 0
                    factor_potencial = (1 + (factor_deposito * 0.7))
                    m2pp = round((m2pp_base * factor_potencial), 2) if m2pp_base is not None else None

                    ppo = personas_por_oficina if personas_por_oficina is not None else None
                    venc45 = seg_vencen

                    if m2pp is None:
                        m2_class = "na"
                        m2_score = None
                    elif m2pp < 8:
                        m2_class = "bad"
                        m2_score = 35
                    elif m2pp <= 12:
                        m2_class = "ok"
                        m2_score = 100
                    elif m2pp <= 20:
                        m2_class = "warn"
                        m2_score = 70
                    else:
                        m2_class = "info"
                        m2_score = 60

                    if m2pp_base is not None and m2pp is not None and m2pp_base < 8 and m2pp >= 8 and amb_depositos > 0:
                        m2_class = "warn"
                        m2_score = 75

                    if ppo is None:
                        ppo_class = "na"
                        ppo_score = None
                    elif ppo <= 2:
                        ppo_class = "ok"
                        ppo_score = 100
                    elif ppo <= 3:
                        ppo_class = "warn"
                        ppo_score = 70
                    else:
                        ppo_class = "bad"
                        ppo_score = 35

                    if venc45 is None:
                        seg_class = "na"
                        seg_score = None
                    elif int(venc45) == 0:
                        seg_class = "ok"
                        seg_score = 100
                    elif int(venc45) <= 2:
                        seg_class = "warn"
                        seg_score = 70
                    else:
                        seg_class = "bad"
                        seg_score = 35

                    idx_sum = 0
                    idx_n = 0
                    for sc in (m2_score, ppo_score, seg_score):
                        if sc is not None:
                            idx_sum += sc
                            idx_n += 1
                    idx_general = int(round((idx_sum / idx_n), 0)) if idx_n > 0 else None
                    if idx_general is None:
                        idx_class = "na"
                    elif idx_general >= 85:
                        idx_class = "ok"
                    elif idx_general >= 70:
                        idx_class = "warn"
                    else:
                        idx_class = "bad"

                    sedes_cards.append({
                        "codigo": cod,
                        "nombre": _row_value(s, "nombre", "") or "",
                        "ciudad": _row_value(s, "ciudad", "") or "",
                        "direccion": _row_value(s, "direccion", "") or "",
                        "fuero": _row_value(s, "fuero", "") or "",
                        "personal": _safe_int(_row_value(per_kpi, "personas", 0)),
                        "puestos": puestos_trabajo,
                        "depositos": depositos_kpi or 0,
                        "ocupacion_pct": ocupacion_pct,
                        "m2pp": m2pp,
                        "ppo": ppo,
                        "idx_general": idx_general,
                        "idx_class": idx_class,
                    })

                severity_order = {"bad": 0, "warn": 1, "ok": 2, "na": 3}
                sedes_cards.sort(key=lambda x: (severity_order.get(x["idx_class"], 9), x["codigo"]))

            # =========================
            # OBRAS / INTERVENCIONES
            # =========================
            top_obras = []
            if _table_exists(con, "obras_sede"):
                cols_obras = _table_cols(con, "obras_sede")
                has_fecha = "fecha_solicitud" in cols_obras
                rows_o = con.execute(f"""
                    SELECT codigo_sede, titulo, tipo, prioridad, estado, {'fecha_solicitud' if has_fecha else 'NULL'} AS fecha_solicitud
                    FROM obras_sede
                    WHERE TRIM(COALESCE(titulo,'')) <> ''
                    ORDER BY
                        CASE WHEN UPPER(COALESCE(prioridad,'')) IN ('ALTA','URGENTE') THEN 0
                             WHEN UPPER(COALESCE(prioridad,'')) = 'MEDIA' THEN 1
                             ELSE 2 END,
                        CASE WHEN UPPER(COALESCE(estado,'')) IN ('EN_CURSO','EN CURSO') THEN 0
                             WHEN UPPER(COALESCE(estado,'')) = 'PENDIENTE' THEN 1
                             ELSE 2 END,
                        COALESCE(fecha_solicitud, '') DESC
                    LIMIT 5
                """).fetchall()
                for r in rows_o:
                    top_obras.append({
                        "sede": (_row_value(r, "codigo_sede", "") or "").strip(),
                        "titulo": (_row_value(r, "titulo", "") or "").strip(),
                        "tipo": (_row_value(r, "tipo", "") or "").strip(),
                        "prioridad": (_row_value(r, "prioridad", "") or "").strip(),
                        "estado": (_row_value(r, "estado", "") or "").strip(),
                    })

            obras_avance_pct = round((obras_finalizadas * 100.0 / obras_total), 1) if obras_total else 0
            obras_sedes, obras_total_sedes, obras_donut = _obras_sedes_resumen(con)

            # =========================
            # VEHICULOS
            # =========================
            vehiculos_cards = _vehiculos_cards_from_base(base, con)
            total_km = ((base.get("indicadores2026") or {}).get("totalKm")) or 0
            uso_general = {
                "en_uso": int(donut.get("enUso") or 0),
                "guardados": int(donut.get("guardados") or 0),
                "pendientes": int(donut.get("pendientesCierre") or 0),
                "no_disp": int(donut.get("noDisponibles") or 0),
                "total": veh_total,
            }

            # =========================
            # SG-SST LISTA (TOP)
            # =========================
            sst_top = sorted(items_sst, key=lambda x: x.get("pct", 0), reverse=True)[:6]

        finally:
            con.close()

        return render_template(
            "dashboard_ejecutivo.html",
            sedes_activas=sedes_activas,
            obras_en_curso=obras_en_curso,
            pendientes_criticos=pendientes_criticos,
            vehiculos_operativos=veh_operativos,
            sst_avance=sst_avg,
            sst_estado=sst_estado,
            sst_estado_cls=sst_estado_cls,
            sst_etapa=sst_etapa,
            sedes_cards=sedes_cards[:6],
            sedes_total=len(sedes_cards),
            obras_avance_pct=obras_avance_pct,
            obras_total=obras_total,
            obras_sedes=obras_sedes,
            obras_donut=obras_donut,
            top_obras=top_obras,
            vehiculos_cards=vehiculos_cards,
            total_km=total_km,
            uso_general=uso_general,
            sst_top=sst_top,
        )


    @app.route("/dashboard/sgi/documentacion", endpoint="sgi_documentacion")
    def sgi_documentacion():
        return render_template("sgi_documentacion.html")

    @app.route("/dashboard/sgi/documentacion/informes", methods=["GET", "POST"], endpoint="sgi_documentacion_informes")
    def sgi_documentacion_informes():
        con = get_db()
        con.row_factory = sqlite3.Row
        ensure_documentos_tables(con)

        def _sync_documento_relaciones(cur, doc_id, limpiar_previas=False):
            if limpiar_previas:
                cur.execute("DELETE FROM documentos_sedes WHERE id_documento = ?", (doc_id,))
                cur.execute("DELETE FROM documentos_agentes WHERE id_documento = ?", (doc_id,))
                cur.execute("DELETE FROM documentos_vehiculos WHERE id_documento = ?", (doc_id,))
                cur.execute("DELETE FROM documentos_sst WHERE id_documento = ?", (doc_id,))
                cur.execute("DELETE FROM documentos_tags WHERE id_documento = ?", (doc_id,))
                cur.execute("DELETE FROM documentos_destino WHERE id_documento = ?", (doc_id,))

            for sede_codigo in sorted(set([x.strip().upper() for x in request.form.getlist("sedes_codigos") if str(x).strip()])):
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_sedes(id_documento, sede_codigo) VALUES (?, ?)",
                    (doc_id, sede_codigo),
                )

            agentes_ids = []
            for raw in request.form.getlist("agentes_ids"):
                try:
                    aid = int(str(raw).strip())
                    if aid > 0:
                        agentes_ids.append(aid)
                except Exception:
                    pass
            for aid in sorted(set(agentes_ids)):
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_agentes(id_documento, id_agente) VALUES (?, ?)",
                    (doc_id, aid),
                )

            for patente in sorted(set([x.strip().upper() for x in request.form.getlist("vehiculos_patentes") if str(x).strip()])):
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_vehiculos(id_documento, patente) VALUES (?, ?)",
                    (doc_id, patente),
                )

            sst_tipo_evento = (request.form.get("sst_tipo_evento") or "").strip()
            sst_id_evento = (request.form.get("sst_id_evento") or "").strip()
            sst_evento_id = None
            try:
                if sst_id_evento:
                    sst_evento_id = int(sst_id_evento)
            except Exception:
                sst_evento_id = None
            if sst_tipo_evento or sst_evento_id is not None:
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_sst(id_documento, tipo_evento, id_evento) VALUES (?, ?, ?)",
                    (doc_id, sst_tipo_evento or None, sst_evento_id),
                )

            for tag in _split_doc_tags(request.form.get("tags") or ""):
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_tags(id_documento, tag) VALUES (?, ?)",
                    (doc_id, tag),
                )

            destinos = []
            for d in request.form.getlist("destinos"):
                d2 = str(d or "").strip()
                if d2 in DOCUMENTOS_DESTINOS:
                    destinos.append(d2)
            for d in sorted(set(destinos)):
                cur.execute(
                    "INSERT OR IGNORE INTO documentos_destino(id_documento, destino) VALUES (?, ?)",
                    (doc_id, d),
                )

        if request.method == "POST":
            action = (request.form.get("_action") or "create").strip().lower()
            if action not in ("create", "edit", "delete"):
                action = "create"

            if action == "delete":
                try:
                    doc_id = int((request.form.get("id_documento") or "").strip())
                except Exception:
                    doc_id = 0

                if doc_id <= 0:
                    flash("Documento invalido para borrar.", "error")
                else:
                    cur = con.cursor()
                    cur.execute("DELETE FROM documentos_sedes WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos_agentes WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos_vehiculos WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos_sst WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos_tags WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos_destino WHERE id_documento = ?", (doc_id,))
                    cur.execute("DELETE FROM documentos WHERE id_documento = ?", (doc_id,))
                    if cur.rowcount:
                        con.commit()
                        flash("Documento borrado correctamente.", "success")
                    else:
                        flash("No se encontro el documento para borrar.", "warning")
                con.close()
                return redirect(url_for("sgi_documentacion_informes"))

            titulo = (request.form.get("titulo") or "").strip()
            tipo_documento = (request.form.get("tipo_documento") or "documento_general").strip().lower()
            descripcion = (request.form.get("descripcion") or "").strip()
            fecha = (request.form.get("fecha") or "").strip()
            autor = (request.form.get("autor") or "").strip()
            archivo_url = (request.form.get("archivo_url") or "").strip()
            estado = (request.form.get("estado") or "borrador").strip().lower()

            if tipo_documento not in DOCUMENTOS_TIPOS:
                tipo_documento = "documento_general"
            if estado not in DOCUMENTOS_ESTADOS:
                estado = "borrador"

            if not titulo:
                flash("El titulo del documento es obligatorio.", "error")
            else:
                cur = con.cursor()
                if action == "edit":
                    try:
                        doc_id = int((request.form.get("id_documento") or "").strip())
                    except Exception:
                        doc_id = 0
                    if doc_id <= 0:
                        flash("Documento invalido para editar.", "error")
                    else:
                        cur.execute(
                            """
                            UPDATE documentos
                            SET titulo = ?,
                                tipo_documento = ?,
                                descripcion = ?,
                                fecha = ?,
                                autor = ?,
                                archivo_url = ?,
                                estado = ?
                            WHERE id_documento = ?
                            """,
                            (
                                titulo,
                                tipo_documento,
                                descripcion or None,
                                fecha or None,
                                autor or None,
                                archivo_url or None,
                                estado,
                                doc_id,
                            ),
                        )
                        existe = con.execute(
                            "SELECT 1 FROM documentos WHERE id_documento = ?",
                            (doc_id,),
                        ).fetchone()
                        if existe:
                            _sync_documento_relaciones(cur, doc_id, limpiar_previas=True)
                            con.commit()
                            flash("Documento actualizado correctamente.", "success")
                            con.close()
                            return redirect(url_for("sgi_documentacion_informes"))
                        else:
                            flash("No se encontro el documento para editar.", "warning")
                else:
                    cur.execute(
                        """
                        INSERT INTO documentos(titulo, tipo_documento, descripcion, fecha, autor, archivo_url, estado)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            titulo,
                            tipo_documento,
                            descripcion or None,
                            fecha or None,
                            autor or None,
                            archivo_url or None,
                            estado,
                        ),
                    )
                    doc_id = cur.lastrowid
                    _sync_documento_relaciones(cur, doc_id)

                    con.commit()
                    flash("Documento guardado y vinculado correctamente.", "success")
                    con.close()
                    return redirect(url_for("sgi_documentacion_informes"))

        q_texto = (request.args.get("q") or "").strip()
        q_tipo = (request.args.get("tipo") or "").strip().lower()
        q_estado = (request.args.get("estado") or "").strip().lower()
        q_sede = (request.args.get("sede") or "").strip().upper()
        q_agente = (request.args.get("agente") or "").strip()
        q_vehiculo = (request.args.get("vehiculo") or "").strip().upper()
        q_destino = (request.args.get("destino") or "").strip()
        q_tag = (request.args.get("tag") or "").strip()
        q_edit = (request.args.get("edit") or "").strip()

        sedes = con.execute("SELECT codigo, nombre FROM sedes_mpd ORDER BY codigo").fetchall()
        agentes = con.execute("SELECT id, agente FROM agentes_intendencia WHERE COALESCE(activo,1)=1 ORDER BY agente").fetchall()
        vehiculos = con.execute("SELECT patente, modelo, tipo FROM vehiculos WHERE COALESCE(activo,1)=1 ORDER BY patente").fetchall()
        sst_eventos = con.execute(
            """
            SELECT id, fecha, tipo, COALESCE(titulo, '') AS titulo
            FROM sst_general
            ORDER BY COALESCE(fecha, '') DESC, id DESC
            LIMIT 150
            """
        ).fetchall()
        tags_disponibles = con.execute("SELECT DISTINCT tag FROM documentos_tags WHERE TRIM(tag) <> '' ORDER BY tag").fetchall()

        doc_editar = None
        if q_edit:
            try:
                edit_id = int(q_edit)
            except Exception:
                edit_id = 0
            if edit_id > 0:
                doc_editar = con.execute(
                    """
                    SELECT
                        d.id_documento,
                        d.titulo,
                        d.tipo_documento,
                        d.descripcion,
                        d.fecha,
                        d.autor,
                        d.archivo_url,
                        d.estado,
                        COALESCE((SELECT GROUP_CONCAT(ds.sede_codigo, ',') FROM documentos_sedes ds WHERE ds.id_documento = d.id_documento), '') AS sedes_ids_csv,
                        COALESCE((SELECT GROUP_CONCAT(da.id_agente, ',') FROM documentos_agentes da WHERE da.id_documento = d.id_documento), '') AS agentes_ids_csv,
                        COALESCE((SELECT GROUP_CONCAT(dv.patente, ',') FROM documentos_vehiculos dv WHERE dv.id_documento = d.id_documento), '') AS vehiculos_patentes_csv,
                        COALESCE((SELECT GROUP_CONCAT(dd.destino, '||') FROM documentos_destino dd WHERE dd.id_documento = d.id_documento), '') AS destinos_csv,
                        COALESCE((SELECT GROUP_CONCAT(dt.tag, ', ') FROM documentos_tags dt WHERE dt.id_documento = d.id_documento), '') AS tags_txt,
                        COALESCE((SELECT dx.tipo_evento FROM documentos_sst dx WHERE dx.id_documento = d.id_documento ORDER BY dx.id DESC LIMIT 1), '') AS sst_tipo_evento,
                        COALESCE((SELECT dx.id_evento FROM documentos_sst dx WHERE dx.id_documento = d.id_documento ORDER BY dx.id DESC LIMIT 1), '') AS sst_id_evento
                    FROM documentos d
                    WHERE d.id_documento = ?
                    """,
                    (edit_id,),
                ).fetchone()

        where = []
        params = []

        if q_texto:
            like = f"%{q_texto}%"
            where.append("(d.titulo LIKE ? OR d.descripcion LIKE ? OR d.autor LIKE ?)")
            params.extend([like, like, like])

        if q_tipo in DOCUMENTOS_TIPOS:
            where.append("d.tipo_documento = ?")
            params.append(q_tipo)

        if q_estado in DOCUMENTOS_ESTADOS:
            where.append("d.estado = ?")
            params.append(q_estado)

        if q_sede:
            where.append("EXISTS (SELECT 1 FROM documentos_sedes ds WHERE ds.id_documento = d.id_documento AND ds.sede_codigo = ?)")
            params.append(q_sede)

        if q_agente:
            try:
                q_agente_id = int(q_agente)
                where.append("EXISTS (SELECT 1 FROM documentos_agentes da WHERE da.id_documento = d.id_documento AND da.id_agente = ?)")
                params.append(q_agente_id)
            except Exception:
                pass

        if q_vehiculo:
            where.append("EXISTS (SELECT 1 FROM documentos_vehiculos dv WHERE dv.id_documento = d.id_documento AND dv.patente = ?)")
            params.append(q_vehiculo)

        if q_destino:
            where.append("EXISTS (SELECT 1 FROM documentos_destino dd WHERE dd.id_documento = d.id_documento AND dd.destino = ?)")
            params.append(q_destino)

        if q_tag:
            where.append("EXISTS (SELECT 1 FROM documentos_tags dt WHERE dt.id_documento = d.id_documento AND dt.tag LIKE ?)")
            params.append(f"%{q_tag}%")

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)

        docs = con.execute(
            f"""
            SELECT
                d.id_documento,
                d.titulo,
                d.tipo_documento,
                d.descripcion,
                d.fecha,
                d.autor,
                d.archivo_url,
                d.estado,
                d.creado_en,
                COALESCE((SELECT GROUP_CONCAT(ds.sede_codigo, ', ') FROM documentos_sedes ds WHERE ds.id_documento = d.id_documento), '') AS sedes_txt,
                COALESCE((SELECT GROUP_CONCAT(ai.agente, ', ') FROM documentos_agentes da JOIN agentes_intendencia ai ON ai.id = da.id_agente WHERE da.id_documento = d.id_documento), '') AS agentes_txt,
                COALESCE((SELECT GROUP_CONCAT(dv.patente, ', ') FROM documentos_vehiculos dv WHERE dv.id_documento = d.id_documento), '') AS vehiculos_txt,
                COALESCE((SELECT GROUP_CONCAT(dd.destino, ', ') FROM documentos_destino dd WHERE dd.id_documento = d.id_documento), '') AS destinos_txt,
                COALESCE((SELECT GROUP_CONCAT(dt.tag, ', ') FROM documentos_tags dt WHERE dt.id_documento = d.id_documento), '') AS tags_txt,
                COALESCE((
                    SELECT GROUP_CONCAT(
                        COALESCE(dx.tipo_evento, '') || CASE WHEN dx.id_evento IS NOT NULL THEN ' #' || dx.id_evento ELSE '' END,
                        ', '
                    )
                    FROM documentos_sst dx
                    WHERE dx.id_documento = d.id_documento
                ), '') AS sst_txt
            FROM documentos d
            {where_sql}
            ORDER BY COALESCE(d.fecha, d.creado_en) DESC, d.id_documento DESC
            LIMIT 500
            """,
            params,
        ).fetchall()

        con.close()

        return render_template(
            "sgi_documentacion_informes.html",
            docs=docs,
            sedes=sedes,
            agentes=agentes,
            vehiculos=vehiculos,
            sst_eventos=sst_eventos,
            tipos_documento=DOCUMENTOS_TIPOS,
            estados_documento=DOCUMENTOS_ESTADOS,
            destinos_documento=DOCUMENTOS_DESTINOS,
            tags_disponibles=tags_disponibles,
            doc_editar=doc_editar,
            q_texto=q_texto,
            q_tipo=q_tipo,
            q_estado=q_estado,
            q_sede=q_sede,
            q_agente=q_agente,
            q_vehiculo=q_vehiculo,
            q_destino=q_destino,
            q_tag=q_tag,
        )

    # ============================================================
    # SG-SST - Bloque documental interno (rutas)
    # ============================================================

    def _sgsst_norm_bloque(bloque: str):
        b = (bloque or "").strip().lower()
        return b if b in SGSST_BLOQUES_VALIDOS else None

    def _sgsst_doc_por_bloque(con, bloque: str):
        return con.execute(
            """
            SELECT *
            FROM sgsst_documentos
            WHERE bloque = ?
            ORDER BY orden_visual, id
            LIMIT 1
            """,
            (bloque,),
        ).fetchone()

    def _sgsst_build_bloques_home(con):
        placeholders = ",".join(["?"] * len(SGSST_BLOQUES_VALIDOS))
        rows = con.execute(
            f"""
            SELECT *
            FROM sgsst_documentos
            WHERE bloque IN ({placeholders})
            ORDER BY orden_visual, id
            """,
            SGSST_BLOQUES_VALIDOS,
        ).fetchall()
        by_bloque = {}
        for r in rows:
            b = (r["bloque"] or "").strip().lower()
            if b and b not in by_bloque:
                by_bloque[b] = dict(r)

        base_prot_codigos = [x["codigo"] for x in SGSST_PROTOCOLOS_BASE]
        base_ins_codigos = [x["codigo"] for x in SGSST_INSTRUCTIVOS_BASE]
        estado_prot = _sgsst_estado_por_base(con, "sgsst_protocolos", base_prot_codigos)
        estado_ins = _sgsst_estado_por_base(con, "sgsst_instructivos", base_ins_codigos)

        bloques = []
        seed_by_bloque = {d["bloque"]: d for d in SGSST_DOCS_SEED}
        for b in SGSST_BLOQUES_VALIDOS:
            doc = by_bloque.get(b) or dict(seed_by_bloque.get(b) or {"bloque": b})
            if b == "protocolos":
                auto = estado_prot
            elif b == "instructivos":
                auto = estado_ins
            else:
                auto = _sgsst_estado_bloque(doc.get("contenido"), doc.get("activo", 0))
            bloques.append({"bloque": b, "doc": doc, "auto": auto})
        return bloques, estado_prot, estado_ins

    @app.route("/sgsst/documentacion", endpoint="sgsst_documentacion_home")
    def sgsst_documentacion_home():
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            bloques, estado_prot, estado_ins = _sgsst_build_bloques_home(con)

            bloques_activos = 0
            pendientes_bloques = 0
            for b in bloques:
                doc = b.get("doc") or {}
                auto = b.get("auto") or {}
                if int(doc.get("activo", 0) or 0) == 1:
                    bloques_activos += 1
                if (b.get("bloque") in ("politica", "plan_accion", "roles", "riesgos")) and auto.get("label") != "Completo":
                    pendientes_bloques += 1

            row = con.execute("SELECT COUNT(1) AS n FROM sgsst_protocolos WHERE COALESCE(activo, 1) = 1").fetchone()
            protocolos_activos = int((row["n"] if row else 0) or 0)
            row = con.execute("SELECT COUNT(1) AS n FROM sgsst_instructivos WHERE COALESCE(activo, 1) = 1").fetchone()
            instructivos_activos = int((row["n"] if row else 0) or 0)

            prot_act = int((estado_prot.get("n_act") or 0) or 0)
            prot_tot = int((estado_prot.get("total") or 0) or 0)
            ins_act = int((estado_ins.get("n_act") or 0) or 0)
            ins_tot = int((estado_ins.get("total") or 0) or 0)
            pendientes_total = pendientes_bloques + max(0, prot_tot - prot_act) + max(0, ins_tot - ins_act)
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_documentacion_home.html",
            bloques=bloques,
            kpi_bloques_activos=bloques_activos,
            kpi_protocolos_activos=protocolos_activos,
            kpi_instructivos_activos=instructivos_activos,
            kpi_pendientes=pendientes_total,
            estado_protocolos=estado_prot,
            estado_instructivos=estado_ins,
        )

    @app.route("/sgsst/documentacion/<bloque>", endpoint="sgsst_documento_detalle")
    def sgsst_documento_detalle(bloque):
        b = _sgsst_norm_bloque(bloque)
        if not b:
            return "Bloque no válido.", 404

        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = _sgsst_doc_por_bloque(con, b)
            if not row:
                return "Documento no encontrado.", 404
            doc = dict(row)

            if b == "protocolos":
                auto = _sgsst_estado_por_base(con, "sgsst_protocolos", [x["codigo"] for x in SGSST_PROTOCOLOS_BASE])
            elif b == "instructivos":
                auto = _sgsst_estado_por_base(con, "sgsst_instructivos", [x["codigo"] for x in SGSST_INSTRUCTIVOS_BASE])
            else:
                auto = _sgsst_estado_bloque(doc.get("contenido"), doc.get("activo", 0))
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_documento_detalle.html",
            doc=doc,
            bloque=b,
            auto_estado=auto,
        )

    @app.route("/sgsst/documentacion/<bloque>/editar", methods=["GET", "POST"], endpoint="sgsst_documento_editar")
    def sgsst_documento_editar(bloque):
        b = _sgsst_norm_bloque(bloque)
        if not b:
            return "Bloque no válido.", 404

        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = _sgsst_doc_por_bloque(con, b)
            if not row:
                return "Documento no encontrado.", 404
            doc = dict(row)

            if request.method == "POST":
                now = _sgsst_now_ts()
                quick = (request.form.get("quick") or "").strip()
                if quick == "1":
                    responsable = (request.form.get("responsable") or "").strip()
                    con.execute(
                        "UPDATE sgsst_documentos SET responsable = ?, fecha_actualizacion = ? WHERE id = ?",
                        (responsable, now, int(doc["id"])),
                    )
                    con.commit()
                    return_to = (request.form.get("return_to") or "").strip().lower()
                    if return_to == "sst":
                        return redirect(url_for("sst_general"))
                    return redirect(url_for("sgsst_documento_detalle", bloque=b))

                titulo = (request.form.get("titulo") or "").strip()
                subtitulo = (request.form.get("subtitulo") or "").strip()
                descripcion_corta = (request.form.get("descripcion_corta") or "").strip()
                contenido = (request.form.get("contenido") or "").strip()
                estado = (request.form.get("estado") or "BORRADOR").strip().upper()
                responsable = (request.form.get("responsable") or "").strip()
                observaciones = (request.form.get("observaciones") or "").strip()

                activo = 1 if (request.form.get("activo") or "").strip() in ("1", "on", "true", "si") else 0
                try:
                    orden_visual = int((request.form.get("orden_visual") or doc.get("orden_visual") or 0) or 0)
                except Exception:
                    orden_visual = int(doc.get("orden_visual") or 0)

                if not titulo:
                    titulo = doc.get("titulo") or ""

                con.execute(
                    """
                    UPDATE sgsst_documentos
                    SET titulo = ?,
                        subtitulo = ?,
                        descripcion_corta = ?,
                        contenido = ?,
                        estado = ?,
                        orden_visual = ?,
                        activo = ?,
                        fecha_actualizacion = ?,
                        responsable = ?,
                        observaciones = ?
                    WHERE id = ?
                    """,
                    (
                        titulo,
                        subtitulo or None,
                        descripcion_corta or None,
                        contenido or None,
                        estado,
                        orden_visual,
                        activo,
                        now,
                        responsable or None,
                        observaciones or None,
                        int(doc["id"]),
                    ),
                )
                con.commit()
                return redirect(url_for("sgsst_documento_detalle", bloque=b))
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_documento_form.html",
            doc=doc,
            bloque=b,
            estados=["BORRADOR", "EN_DESARROLLO", "COMPLETO", "ARCHIVADO"],
        )

    # -------------------------
    # Protocolos (CRUD)
    # -------------------------

    @app.route("/sgsst/protocolos", endpoint="sgsst_protocolos")
    def sgsst_protocolos():
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            protocolos = con.execute(
                """
                SELECT *
                FROM sgsst_protocolos
                ORDER BY COALESCE(categoria, ''), orden_visual, COALESCE(titulo, '')
                """
            ).fetchall()
            protocolos = [dict(r) for r in (protocolos or [])]
        finally:
            try:
                con.close()
            except Exception:
                pass
        return render_template("sgsst_protocolos.html", protocolos=protocolos)

    @app.route("/sgsst/protocolos/<int:id>", endpoint="sgsst_protocolo_detalle")
    def sgsst_protocolo_detalle(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = con.execute("SELECT * FROM sgsst_protocolos WHERE id = ?", (int(id),)).fetchone()
            if not row:
                return "Protocolo no encontrado.", 404
            protocolo = dict(row)
        finally:
            try:
                con.close()
            except Exception:
                pass
        return render_template("sgsst_protocolo_detalle.html", protocolo=protocolo)

    @app.route("/sgsst/protocolos/nuevo", methods=["GET", "POST"], endpoint="sgsst_protocolo_nuevo")
    def sgsst_protocolo_nuevo():
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            if request.method == "POST":
                now = _sgsst_now_ts()
                codigo = (request.form.get("codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                categoria = (request.form.get("categoria") or "").strip()
                descripcion_corta = (request.form.get("descripcion_corta") or "").strip()
                objetivo = (request.form.get("objetivo") or "").strip()
                alcance = (request.form.get("alcance") or "").strip()
                procedimiento = (request.form.get("procedimiento") or "").strip()
                registro_asociado = (request.form.get("registro_asociado") or "").strip()
                frecuencia = (request.form.get("frecuencia") or "").strip()
                responsable = (request.form.get("responsable") or "").strip()
                estado = (request.form.get("estado") or "BORRADOR").strip().upper()
                activo = 1 if (request.form.get("activo") or "").strip() in ("1", "on", "true", "si") else 0
                integrado_sgi = 1 if (request.form.get("integrado_sgi") or "").strip() in ("1", "on", "true", "si") else 0
                try:
                    orden_visual = int((request.form.get("orden_visual") or 0) or 0)
                except Exception:
                    orden_visual = 0

                if not codigo or not titulo or not categoria:
                    flash("Código, título y categoría son obligatorios.", "error")
                else:
                    try:
                        con.execute(
                            """
                            INSERT INTO sgsst_protocolos (
                                codigo, titulo, categoria, descripcion_corta, objetivo, alcance, procedimiento,
                                registro_asociado, frecuencia, responsable, estado, orden_visual, activo,
                                fecha_actualizacion, integrado_sgi
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                codigo, titulo, categoria,
                                descripcion_corta or None,
                                objetivo or None,
                                alcance or None,
                                procedimiento or None,
                                registro_asociado or None,
                                frecuencia or None,
                                responsable or None,
                                estado,
                                orden_visual,
                                activo,
                                now,
                                integrado_sgi,
                            ),
                        )
                        con.commit()
                        new_id = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                        return redirect(url_for("sgsst_protocolo_detalle", id=int(new_id)))
                    except sqlite3.IntegrityError:
                        flash("Ya existe un protocolo con ese código.", "error")
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_protocolo_form.html",
            protocolo={},
            is_new=True,
            estados=["BORRADOR", "EN_DESARROLLO", "COMPLETO", "ARCHIVADO"],
        )

    @app.route("/sgsst/protocolos/<int:id>/editar", methods=["GET", "POST"], endpoint="sgsst_protocolo_editar")
    def sgsst_protocolo_editar(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = con.execute("SELECT * FROM sgsst_protocolos WHERE id = ?", (int(id),)).fetchone()
            if not row:
                return "Protocolo no encontrado.", 404
            protocolo = dict(row)

            if request.method == "POST":
                now = _sgsst_now_ts()
                codigo = (request.form.get("codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                categoria = (request.form.get("categoria") or "").strip()
                descripcion_corta = (request.form.get("descripcion_corta") or "").strip()
                objetivo = (request.form.get("objetivo") or "").strip()
                alcance = (request.form.get("alcance") or "").strip()
                procedimiento = (request.form.get("procedimiento") or "").strip()
                registro_asociado = (request.form.get("registro_asociado") or "").strip()
                frecuencia = (request.form.get("frecuencia") or "").strip()
                responsable = (request.form.get("responsable") or "").strip()
                estado = (request.form.get("estado") or "BORRADOR").strip().upper()
                activo = 1 if (request.form.get("activo") or "").strip() in ("1", "on", "true", "si") else 0
                integrado_sgi = 1 if (request.form.get("integrado_sgi") or "").strip() in ("1", "on", "true", "si") else 0
                try:
                    orden_visual = int((request.form.get("orden_visual") or 0) or 0)
                except Exception:
                    orden_visual = int(protocolo.get("orden_visual") or 0)

                if not codigo or not titulo or not categoria:
                    flash("Código, título y categoría son obligatorios.", "error")
                else:
                    try:
                        con.execute(
                            """
                            UPDATE sgsst_protocolos
                            SET codigo = ?,
                                titulo = ?,
                                categoria = ?,
                                descripcion_corta = ?,
                                objetivo = ?,
                                alcance = ?,
                                procedimiento = ?,
                                registro_asociado = ?,
                                frecuencia = ?,
                                responsable = ?,
                                estado = ?,
                                orden_visual = ?,
                                activo = ?,
                                fecha_actualizacion = ?,
                                integrado_sgi = ?
                            WHERE id = ?
                            """,
                            (
                                codigo, titulo, categoria,
                                descripcion_corta or None,
                                objetivo or None,
                                alcance or None,
                                procedimiento or None,
                                registro_asociado or None,
                                frecuencia or None,
                                responsable or None,
                                estado,
                                orden_visual,
                                activo,
                                now,
                                integrado_sgi,
                                int(id),
                            ),
                        )
                        con.commit()
                        return redirect(url_for("sgsst_protocolo_detalle", id=int(id)))
                    except sqlite3.IntegrityError:
                        flash("Ya existe un protocolo con ese código.", "error")
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_protocolo_form.html",
            protocolo=protocolo,
            is_new=False,
            estados=["BORRADOR", "EN_DESARROLLO", "COMPLETO", "ARCHIVADO"],
        )

    @app.route("/sgsst/protocolos/<int:id>/eliminar", methods=["POST"], endpoint="sgsst_protocolo_eliminar")
    def sgsst_protocolo_eliminar(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            now = _sgsst_now_ts()
            con.execute(
                "UPDATE sgsst_protocolos SET activo = 0, fecha_actualizacion = ? WHERE id = ?",
                (now, int(id)),
            )
            con.commit()
        finally:
            try:
                con.close()
            except Exception:
                pass
        return redirect(url_for("sgsst_protocolos"))

    # -------------------------
    # Instructivos (CRUD)
    # -------------------------

    @app.route("/sgsst/instructivos", endpoint="sgsst_instructivos")
    def sgsst_instructivos():
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            instructivos = con.execute(
                """
                SELECT *
                FROM sgsst_instructivos
                ORDER BY COALESCE(categoria, ''), orden_visual, COALESCE(titulo, '')
                """
            ).fetchall()
            instructivos = [dict(r) for r in (instructivos or [])]
        finally:
            try:
                con.close()
            except Exception:
                pass
        return render_template("sgsst_instructivos.html", instructivos=instructivos)

    @app.route("/sgsst/instructivos/<int:id>", endpoint="sgsst_instructivo_detalle")
    def sgsst_instructivo_detalle(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = con.execute("SELECT * FROM sgsst_instructivos WHERE id = ?", (int(id),)).fetchone()
            if not row:
                return "Instructivo no encontrado.", 404
            instructivo = dict(row)
        finally:
            try:
                con.close()
            except Exception:
                pass
        return render_template("sgsst_instructivo_detalle.html", instructivo=instructivo)

    @app.route("/sgsst/instructivos/nuevo", methods=["GET", "POST"], endpoint="sgsst_instructivo_nuevo")
    def sgsst_instructivo_nuevo():
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            if request.method == "POST":
                now = _sgsst_now_ts()
                codigo = (request.form.get("codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                categoria = (request.form.get("categoria") or "").strip()
                descripcion_corta = (request.form.get("descripcion_corta") or "").strip()
                contenido = (request.form.get("contenido") or "").strip()
                uso_aplicable = (request.form.get("uso_aplicable") or "").strip()
                responsable = (request.form.get("responsable") or "").strip()
                estado = (request.form.get("estado") or "BORRADOR").strip().upper()
                activo = 1 if (request.form.get("activo") or "").strip() in ("1", "on", "true", "si") else 0
                try:
                    orden_visual = int((request.form.get("orden_visual") or 0) or 0)
                except Exception:
                    orden_visual = 0

                if not codigo or not titulo or not categoria:
                    flash("Código, título y categoría son obligatorios.", "error")
                else:
                    try:
                        con.execute(
                            """
                            INSERT INTO sgsst_instructivos (
                                codigo, titulo, categoria, descripcion_corta, contenido, uso_aplicable,
                                responsable, estado, orden_visual, activo, fecha_actualizacion
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                codigo, titulo, categoria,
                                descripcion_corta or None,
                                contenido or None,
                                uso_aplicable or None,
                                responsable or None,
                                estado,
                                orden_visual,
                                activo,
                                now,
                            ),
                        )
                        con.commit()
                        new_id = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                        return redirect(url_for("sgsst_instructivo_detalle", id=int(new_id)))
                    except sqlite3.IntegrityError:
                        flash("Ya existe un instructivo con ese código.", "error")
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_instructivo_form.html",
            instructivo={},
            is_new=True,
            estados=["BORRADOR", "EN_DESARROLLO", "COMPLETO", "ARCHIVADO"],
        )

    @app.route("/sgsst/instructivos/<int:id>/editar", methods=["GET", "POST"], endpoint="sgsst_instructivo_editar")
    def sgsst_instructivo_editar(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            row = con.execute("SELECT * FROM sgsst_instructivos WHERE id = ?", (int(id),)).fetchone()
            if not row:
                return "Instructivo no encontrado.", 404
            instructivo = dict(row)

            if request.method == "POST":
                now = _sgsst_now_ts()
                codigo = (request.form.get("codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                categoria = (request.form.get("categoria") or "").strip()
                descripcion_corta = (request.form.get("descripcion_corta") or "").strip()
                contenido = (request.form.get("contenido") or "").strip()
                uso_aplicable = (request.form.get("uso_aplicable") or "").strip()
                responsable = (request.form.get("responsable") or "").strip()
                estado = (request.form.get("estado") or "BORRADOR").strip().upper()
                activo = 1 if (request.form.get("activo") or "").strip() in ("1", "on", "true", "si") else 0
                try:
                    orden_visual = int((request.form.get("orden_visual") or 0) or 0)
                except Exception:
                    orden_visual = int(instructivo.get("orden_visual") or 0)

                if not codigo or not titulo or not categoria:
                    flash("Código, título y categoría son obligatorios.", "error")
                else:
                    try:
                        con.execute(
                            """
                            UPDATE sgsst_instructivos
                            SET codigo = ?,
                                titulo = ?,
                                categoria = ?,
                                descripcion_corta = ?,
                                contenido = ?,
                                uso_aplicable = ?,
                                responsable = ?,
                                estado = ?,
                                orden_visual = ?,
                                activo = ?,
                                fecha_actualizacion = ?
                            WHERE id = ?
                            """,
                            (
                                codigo, titulo, categoria,
                                descripcion_corta or None,
                                contenido or None,
                                uso_aplicable or None,
                                responsable or None,
                                estado,
                                orden_visual,
                                activo,
                                now,
                                int(id),
                            ),
                        )
                        con.commit()
                        return redirect(url_for("sgsst_instructivo_detalle", id=int(id)))
                    except sqlite3.IntegrityError:
                        flash("Ya existe un instructivo con ese código.", "error")
        finally:
            try:
                con.close()
            except Exception:
                pass

        return render_template(
            "sgsst_instructivo_form.html",
            instructivo=instructivo,
            is_new=False,
            estados=["BORRADOR", "EN_DESARROLLO", "COMPLETO", "ARCHIVADO"],
        )

    @app.route("/sgsst/instructivos/<int:id>/eliminar", methods=["POST"], endpoint="sgsst_instructivo_eliminar")
    def sgsst_instructivo_eliminar(id):
        con = get_db()
        try:
            seed_sgsst_documentacion(con)
            now = _sgsst_now_ts()
            con.execute(
                "UPDATE sgsst_instructivos SET activo = 0, fecha_actualizacion = ? WHERE id = ?",
                (now, int(id)),
            )
            con.commit()
        finally:
            try:
                con.close()
            except Exception:
                pass
        return redirect(url_for("sgsst_instructivos"))

    @app.route("/dashboard/materiales-historial", endpoint="dashboard_materiales_historial")
    def dashboard_materiales_historial():
        return render_template("dashboard_materiales_historial.html")

    @app.route("/dashboard/novedades-historial", endpoint="dashboard_novedades_historial")
    def dashboard_novedades_historial():
        return render_template("dashboard_novedades_historial.html")

    @app.route("/dashboard/sede-estado-manual", endpoint="dashboard_sede_estado_manual")
    def dashboard_sede_estado_manual():
        return render_template("dashboard_sede_estado_manual.html")

    @app.route("/checklist/interior", methods=["GET", "POST"])
    def checklist_interior():
        con = get_db()
        cur = con.cursor()

        # Asegurar que la tabla exista (si no existe, la crea)
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
        con.commit()

        if request.method == "POST":
            data = request.form

            fecha    = data.get("fecha") or date.today().isoformat()
            chofer   = data.get("chofer") or ""
            vehiculo = data.get("vehiculo") or ""

            tilcara_hora    = data.get("tilcara_hora") or ""
            humapenal_hora  = data.get("humapenal_hora") or ""
            humacivil_hora  = data.get("humacivil_hora") or ""
            abrapampa_hora  = data.get("abrapampa_hora") or ""
            laquiaca_hora   = data.get("laquiaca_hora") or ""

            doc_ok          = 1 if data.get("doc_ok") == "on" else 0
            vehiculo_ok     = 1 if data.get("vehiculo_ok") == "on" else 0
            materiales_ok   = 1 if data.get("materiales_ok") == "on" else 0
            herramientas_ok = 1 if data.get("herramientas_ok") == "on" else 0
            insumos_ok      = 1 if data.get("insumos_ok") == "on" else 0
            expediente_ok   = 1 if data.get("expediente_ok") == "on" else 0

            tareas_previstas  = data.get("tareas_previstas") or ""
            tareas_realizadas = data.get("tareas_realizadas") or ""
            observaciones     = data.get("observaciones") or ""

            hora_regreso_s08   = data.get("hora_regreso_s08") or ""
            check_reg_vehiculo = 1 if data.get("check_reg_vehiculo_ok") == "on" else 0

            cur.execute("""
                INSERT INTO checklist_visitas_interior(
                  fecha, chofer, vehiculo,
                  tilcara_hora, humapenal_hora, humacivil_hora,
                  abrapampa_hora, laquiaca_hora,
                  doc_ok, vehiculo_ok, materiales_ok, herramientas_ok,
                  insumos_ok, expediente_ok,
                  tareas_previstas, tareas_realizadas, observaciones,
                  hora_regreso_s08, check_reg_vehiculo_ok
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fecha, chofer, vehiculo,
                tilcara_hora, humapenal_hora, humacivil_hora,
                abrapampa_hora, laquiaca_hora,
                doc_ok, vehiculo_ok, materiales_ok, herramientas_ok,
                insumos_ok, expediente_ok,
                tareas_previstas, tareas_realizadas, observaciones,
                hora_regreso_s08, check_reg_vehiculo
            ))
            con.commit()
            con.close()

            flash("Checklist de visita al interior guardado.", "success")
            return redirect(url_for("checklist_interior"))

        # GET: mostrar formulario + historial
        registros = cur.execute("""
            SELECT *
            FROM checklist_visitas_interior
            ORDER BY fecha DESC, id DESC
        """).fetchall()
        con.close()

        registros = [dict(r) for r in registros]

        return render_template(
            "checklist_interior.html",
            hoy=date.today().isoformat(),
            registros=registros,
        )


    # --- AIRE ACONDICIONADO POR SEDE -----------------------------------------
    from flask import render_template, request, redirect, url_for, abort

    def _ensure_aires_mpd_schema(con):
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS aires_mpd(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sede_codigo TEXT NOT NULL,
                codigo_local TEXT,
                ambiente    TEXT,
                marca       TEXT,
                gas         TEXT,
                modelo      TEXT,
                tipo        TEXT,
                frigorias   INTEGER,
                estado      TEXT,
                fecha_instalacion      TEXT,
                fecha_ultima_limpieza  TEXT,
                fecha_ultimo_service   TEXT,
                frecuencia_meses       INTEGER,
                observaciones          TEXT
            );
        """)
        cols = [r[1] for r in cur.execute("PRAGMA table_info(aires_mpd)").fetchall()]
        if "codigo_local" not in cols:
            cur.execute("ALTER TABLE aires_mpd ADD COLUMN codigo_local TEXT")
        if "gas" not in cols:
            cur.execute("ALTER TABLE aires_mpd ADD COLUMN gas TEXT")
        if "fecha_ultimo_service" not in cols:
            cur.execute("ALTER TABLE aires_mpd ADD COLUMN fecha_ultimo_service TEXT")
        con.commit()

    def obtener_sede(codigo):
        con = get_db()
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        _ensure_aires_mpd_schema(con)
        cur.execute("SELECT * FROM sedes_mpd WHERE codigo = ?", (codigo,))
        sede = cur.fetchone()
        if not sede:
            abort(404)
        return con, cur, sede

    def _norm_local_code(raw):
        txt = str(raw or "").upper().strip()
        if not txt:
            return ""
        if "-" in txt:
            txt = txt.split("-")[-1].strip()
        if txt.startswith("D") and txt[1:].isdigit():
            return f"D{int(txt[1:]):02d}"
        if txt.isdigit():
            return f"D{int(txt):02d}"
        return ""

    def _locales_sede(cur, codigo):
        rows = cur.execute("""
            SELECT COALESCE(codigo_local,'') AS codigo_local, COALESCE(descripcion,'') AS descripcion
            FROM sedes_depositos
            WHERE codigo_sede = ?
            ORDER BY codigo_local
        """, (codigo,)).fetchall()
        out = []
        seen = set()
        for r in rows:
            c = _norm_local_code(r["codigo_local"])
            if not c or c in seen:
                continue
            seen.add(c)
            out.append({
                "codigo_local": c,
                "descripcion": (r["descripcion"] or "").strip(),
            })
        out.sort(key=lambda x: x["codigo_local"])
        return out


    @app.route("/sedes/<codigo>/aires")
    def sede_aires(codigo):
        con, cur, sede = obtener_sede(codigo)
        locales_opts = _locales_sede(cur, codigo)
        locales_desc = {x["codigo_local"]: x["descripcion"] for x in locales_opts}

        sedes_nav = cur.execute("""
            SELECT codigo
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        cur.execute("""
            SELECT id, sede_codigo, COALESCE(codigo_local,'') AS codigo_local, ambiente, marca, gas, modelo, tipo,
                   frigorias, estado, fecha_instalacion,
                   fecha_ultima_limpieza, fecha_ultimo_service, frecuencia_meses, observaciones
            FROM aires_mpd
            WHERE sede_codigo = ?
            ORDER BY ambiente
        """, (codigo,))
        aires_raw = cur.fetchall()
        aires = []
        for a in aires_raw:
            item = dict(a)
            dep = _norm_local_code(item.get("codigo_local"))
            if dep:
                item["codigo_local"] = dep
                dsc = (locales_desc.get(dep) or "").strip()
                item["deposito_label"] = f"{dep} · {dsc}" if dsc else dep
            else:
                item["codigo_local"] = ""
                item["deposito_label"] = "-"
            aires.append(item)

        # Estadísticas simples
        def _estado_norm(v):
            return str(v or "").strip().lower()

        def _equipo_computable(item):
            if _estado_norm(item.get("estado")) in (
                "no va a ir", "no va ir", "sin aire", "n/a", "no aplica"
            ):
                return False
            sede_code = str((item.get("sede_codigo") or "")).strip().upper()
            local_code = _norm_local_code(item.get("codigo_local"))
            if sede_code == "S01" and local_code in ("D22", "D23", "D24"):
                return False
            # Regla operativa: equipos "central" se muestran en listado,
            # pero no se cuentan como unidad independiente de split.
            obs = _estado_norm(item.get("observaciones"))
            return "central" not in obs

        aires_computables = [a for a in aires if _equipo_computable(a)]
        total = len(aires_computables)
        sin_limpieza = sum(
            1 for a in aires_computables
            if not (a["fecha_ultima_limpieza"] or "").strip()
        )
        fuera_servicio = sum(
            1 for a in aires_computables
            if _estado_norm(a.get("estado")) in (
                "fuera de servicio", "no funciona", "baja"
            )
        )
        operativos = sum(
            1 for a in aires_computables
            if _estado_norm(a.get("estado")) in ("operativo", "ok", "en servicio")
        )

        stats = {
            "total": total,
            "sin_limpieza": sin_limpieza,
            "fuera_servicio": fuera_servicio,
            "operativos": operativos,
            "total_registros": len(aires),
        }

        return render_template(
            "sede_aires.html",
            sede=sede,
            sedes_nav=sedes_nav,
            aires=aires,
            stats=stats,
            locales_opts=locales_opts,
        )


    @app.route("/sedes/<codigo>/aires/nuevo", methods=["GET", "POST"])
    def aire_nuevo(codigo):
        con, cur, sede = obtener_sede(codigo)
        locales_opts = _locales_sede(cur, codigo)
        return_piso = (request.values.get("return_piso") or "PB").strip().upper() or "PB"
        return_local = _norm_local_code(request.values.get("return_local", ""))

        if request.method == "POST":
            codigo_local = _norm_local_code(request.form.get("codigo_local", ""))
            ambiente = request.form.get("ambiente", "").strip()
            marca = request.form.get("marca", "").strip()
            gas = request.form.get("gas", "").strip()
            modelo = request.form.get("modelo", "").strip()
            tipo = request.form.get("tipo", "").strip()
            frigorias = request.form.get("frigorias", "").strip()
            estado = request.form.get("estado", "").strip()
            fecha_instalacion = request.form.get("fecha_instalacion") or None
            fecha_ultima_limpieza = request.form.get("fecha_ultima_limpieza") or None
            fecha_ultimo_service = request.form.get("fecha_ultimo_service") or None
            frecuencia_meses = request.form.get("frecuencia_meses") or None
            observaciones = request.form.get("observaciones", "").strip()

            cur.execute("""
                INSERT INTO aires_mpd (
                    sede_codigo, codigo_local, ambiente, marca, gas, modelo, tipo, frigorias,
                    estado, fecha_instalacion, fecha_ultima_limpieza,
                    fecha_ultimo_service, frecuencia_meses, observaciones
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                codigo, (codigo_local or None), ambiente, marca, gas, modelo, tipo, frigorias,
                estado, fecha_instalacion, fecha_ultima_limpieza,
                fecha_ultimo_service, frecuencia_meses, observaciones
            ))
            con.commit()
            new_id = cur.lastrowid
            return redirect(url_for(
                "sede_ficha",
                codigo=codigo,
                piso=return_piso,
                local=(codigo_local or return_local or None),
                tab="aires",
                view="operativo",
                aid=new_id,
            ))

            # si algo falla, vuelve a mostrar el formulario

        return render_template(
            "aire_form.html",
            sede=sede,
            aire=None,
            locales_opts=locales_opts,
            return_piso=return_piso,
            return_local=return_local,
        )


    @app.route("/sedes/<codigo>/aires/<int:aid>/editar", methods=["GET", "POST"])
    def aire_editar(codigo, aid):
        con, cur, sede = obtener_sede(codigo)
        locales_opts = _locales_sede(cur, codigo)
        return_piso = (request.values.get("return_piso") or "PB").strip().upper() or "PB"
        return_local = _norm_local_code(request.values.get("return_local", ""))

        cur.execute("""
            SELECT *
            FROM aires_mpd
            WHERE id = ? AND sede_codigo = ?
        """, (aid, codigo))
        aire = cur.fetchone()
        if not aire:
            abort(404)

        if request.method == "POST":
            codigo_local = _norm_local_code(request.form.get("codigo_local", ""))
            ambiente = request.form.get("ambiente", "").strip()
            marca = request.form.get("marca", "").strip()
            gas = request.form.get("gas", "").strip()
            modelo = request.form.get("modelo", "").strip()
            tipo = request.form.get("tipo", "").strip()
            frigorias = request.form.get("frigorias", "").strip()
            estado = request.form.get("estado", "").strip()
            fecha_instalacion = request.form.get("fecha_instalacion") or None
            fecha_ultima_limpieza = request.form.get("fecha_ultima_limpieza") or None
            fecha_ultimo_service = request.form.get("fecha_ultimo_service") or None
            frecuencia_meses = request.form.get("frecuencia_meses") or None
            observaciones = request.form.get("observaciones", "").strip()

            cur.execute("""
                UPDATE aires_mpd
                   SET codigo_local = ?,
                       ambiente = ?,
                       marca = ?,
                       gas = ?,
                       modelo = ?,
                       tipo = ?,
                       frigorias = ?,
                       estado = ?,
                       fecha_instalacion = ?,
                       fecha_ultima_limpieza = ?,
                       fecha_ultimo_service = ?,
                       frecuencia_meses = ?,
                       observaciones = ?
                 WHERE id = ? AND sede_codigo = ?
            """, (
                (codigo_local or None), ambiente, marca, gas, modelo, tipo, frigorias, estado,
                fecha_instalacion, fecha_ultima_limpieza,
                fecha_ultimo_service, frecuencia_meses, observaciones,
                aid, codigo
            ))
            con.commit()
            return redirect(url_for(
                "sede_ficha",
                codigo=codigo,
                piso=return_piso,
                local=(codigo_local or return_local or None),
                tab="aires",
                view="operativo",
                aid=aid,
            ))

        return render_template(
            "aire_form.html",
            sede=sede,
            aire=aire,
            locales_opts=locales_opts,
            return_piso=return_piso,
            return_local=return_local,
        )


    @app.route("/sedes/<codigo>/aires/<int:aid>/borrar", methods=["POST"])
    def aire_borrar(codigo, aid):
        return_piso = (request.values.get("return_piso") or "PB").strip().upper() or "PB"
        return_local = _norm_local_code(request.values.get("return_local", ""))
        con = get_db()
        cur = con.cursor()
        row = cur.execute("""
            SELECT COALESCE(codigo_local,'') AS codigo_local
            FROM aires_mpd
            WHERE id = ? AND sede_codigo = ?
        """, (aid, codigo)).fetchone()
        cur.execute("""
            DELETE FROM aires_mpd
            WHERE id = ? AND sede_codigo = ?
        """, (aid, codigo))
        con.commit()
        return redirect(url_for(
            "sede_ficha",
            codigo=codigo,
            piso=return_piso,
            local=(_norm_local_code(row["codigo_local"]) if row and row["codigo_local"] else (return_local or None)),
            tab="aires",
            view="operativo",
        ))

    def rebuild_eventos_sst():
        # Placeholder para mantener compatibilidad si se llama desde SST.
        return None

    def _sst_operational_home_context():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)
        ensure_sst_plan_tables(con)

        hoy = date.today().isoformat()
        limite_visitas = (date.today() + timedelta(days=30)).isoformat()
        limite_vencimientos = (date.today() + timedelta(days=45)).isoformat()

        visitas = con.execute("""
            SELECT v.id, v.sede_codigo, v.fecha, v.tipo_visita, v.estado,
                   COALESCE(s.nombre, '') AS sede_nombre
            FROM sst_visitas v
            LEFT JOIN sedes_mpd s ON s.codigo = v.sede_codigo
            WHERE (date(v.fecha) BETWEEN date(?) AND date(?))
               OR UPPER(COALESCE(v.estado, '')) IN ('PEND_ANALISIS', 'REQUIERE_CORRECCION')
            ORDER BY CASE WHEN date(v.fecha) < date(?) THEN 0 ELSE 1 END,
                     date(v.fecha), v.id DESC
            LIMIT 8
        """, (hoy, limite_visitas, hoy)).fetchall()

        matafuegos = con.execute("""
            SELECT m.id, UPPER(COALESCE(m.sede, '')) AS sede_codigo,
                   COALESCE(s.nombre, '') AS sede_nombre,
                   m.fecha_vencimiento, m.tipo, m.numero_serie
            FROM matafuegos m
            LEFT JOIN sedes_mpd s ON UPPER(s.codigo) = UPPER(m.sede)
            WHERE COALESCE(m.activo, 1) = 1
              AND m.fecha_vencimiento IS NOT NULL
              AND date(m.fecha_vencimiento) <= date(?)
            ORDER BY date(m.fecha_vencimiento), m.id
            LIMIT 8
        """, (limite_vencimientos,)).fetchall()

        seguimientos = con.execute("""
            SELECT g.id, g.sede_codigo, COALESCE(s.nombre, '') AS sede_nombre,
                   g.titulo, g.accion_correctiva, g.responsable, g.prioridad,
                   g.fecha_objetivo, g.estado
            FROM sst_general g
            LEFT JOIN sedes_mpd s ON s.codigo = g.sede_codigo
            WHERE UPPER(COALESCE(g.estado, 'ABIERTO')) <> 'CERRADO'
              AND (
                UPPER(COALESCE(g.prioridad, '')) IN ('ALTA', 'CRITICA', 'CRÍTICA')
                OR (g.fecha_objetivo IS NOT NULL AND date(g.fecha_objetivo) < date(?))
              )
            ORDER BY CASE WHEN g.fecha_objetivo IS NOT NULL AND date(g.fecha_objetivo) < date(?) THEN 0 ELSE 1 END,
                     date(g.fecha_objetivo), g.id DESC
            LIMIT 8
        """, (hoy, hoy)).fetchall()

        sedes_rows = con.execute("""
            SELECT s.codigo, s.nombre,
                   (SELECT MAX(v.fecha) FROM sst_visitas v WHERE v.sede_codigo = s.codigo) AS ultima_visita,
                   (SELECT COUNT(*) FROM sst_general g
                    WHERE g.sede_codigo = s.codigo
                      AND g.tipo = 'no_conformidad'
                      AND UPPER(COALESCE(g.estado, 'ABIERTO')) <> 'CERRADO') AS hallazgos,
                   (SELECT COUNT(DISTINCT d.tipo) FROM sst_documentos d
                    WHERE d.sede_codigo = s.codigo
                      AND UPPER(d.tipo) IN ('DEC_351_79', 'RGRL')
                      AND (TRIM(COALESCE(d.archivo, '')) <> '' OR TRIM(COALESCE(d.drive_url, '')) <> '')) AS docs_art
            FROM sedes_mpd s
            ORDER BY s.codigo
        """).fetchall()
        sedes_atencion = []
        for sede in sedes_rows:
            motivos = []
            if not sede["ultima_visita"]:
                motivos.append("Sin visita")
            if int(sede["docs_art"] or 0) < 2:
                motivos.append("Documentación ART incompleta")
            if int(sede["hallazgos"] or 0) > 0:
                motivos.append(f"{int(sede['hallazgos'])} hallazgo(s) abierto(s)")
            if motivos:
                sedes_atencion.append({
                    "codigo": sede["codigo"],
                    "nombre": sede["nombre"],
                    "motivos": motivos,
                })
            if len(sedes_atencion) >= 8:
                break

        recordatorios = []
        try:
            recordatorios = con.execute("""
                SELECT id, fecha, titulo, detalle, fuente, ref_id
                FROM eventos
                WHERE date(fecha) BETWEEN date(?) AND date(?, '+30 day')
                  AND (
                    LOWER(COALESCE(fuente, '')) LIKE '%sst%'
                    OR LOWER(COALESCE(fuente, '')) LIKE '%matafuego%'
                    OR LOWER(COALESCE(titulo, '')) LIKE '%visita%'
                    OR LOWER(COALESCE(titulo, '')) LIKE '%venc%'
                  )
                ORDER BY date(fecha), id
                LIMIT 8
            """, (hoy, hoy)).fetchall()
        except sqlite3.OperationalError:
            recordatorios = []

        con.close()
        return {
            "hoy": hoy,
            "visitas_atencion": visitas,
            "matafuegos_atencion": matafuegos,
            "seguimientos_atencion": seguimientos,
            "sedes_atencion": sedes_atencion,
            "recordatorios": recordatorios,
        }

    @app.route("/sst/inicio", methods=["GET"], endpoint="sst_inicio_operativo")
    def sst_inicio_operativo():
        return render_template("sst_operativo.html", **_sst_operational_home_context())

    @app.route("/sst/matriz-general", methods=["GET"], endpoint="sst_matriz_general")
    def sst_matriz_general():
        return render_template("sst_matriz_general.html", **build_sgsst_matriz_general_context())

    @app.route("/sst/implementacion", methods=["GET"], endpoint="sst_implementacion_tablero")
    def sst_implementacion_tablero():
        args = request.args.to_dict(flat=True)
        args["vista"] = "implementacion"
        if not str(args.get("fase") or "").strip():
            args["fase"] = "implementacion"
        return redirect(url_for("sst_calendario_operativo", **args))

    @app.route("/sst/calendario-operativo", methods=["GET"], endpoint="sst_calendario_operativo")
    def sst_calendario_operativo():
        con = get_db()
        view_mode = (request.args.get("vista") or "").strip().lower()
        if view_mode not in {"implementacion"}:
            view_mode = "general"
        selected_year_raw = (request.args.get("year") or "").strip()
        selected_month_raw = (request.args.get("month") or "").strip()
        selected_year = date.today().year
        if selected_year_raw.isdigit():
            try:
                selected_year = max(2024, min(2035, int(selected_year_raw)))
            except Exception:
                selected_year = date.today().year
        selected_month = 0
        if selected_month_raw.isdigit():
            try:
                selected_month = max(0, min(12, int(selected_month_raw)))
            except Exception:
                selected_month = 0
        phase_filter = (request.args.get("fase") or "").strip().lower()
        if phase_filter not in {"diagnostico", "implementacion", "operacion"}:
            phase_filter = ""
        quick_filter = (request.args.get("quick") or "").strip().lower()
        if quick_filter not in {"pendientes", "vencidos", "finalizados"}:
            quick_filter = ""
        filters = {
            "month": selected_month,
            "region": (request.args.get("region") or "").strip(),
            "sede": (request.args.get("sede") or "").strip().upper(),
            "tipo": (request.args.get("tipo") or "").strip().lower(),
            "estado": (request.args.get("estado") or "").strip().lower(),
            "responsable": (request.args.get("responsable") or "").strip(),
            "fase": phase_filter,
            "quick": quick_filter,
        }
        context_raw = _sst_calendar_collect_events(con, selected_year)
        con.close()
        plan_context = build_sgsst_plan_implementation_context(view_mode="general", selected_sede=filters["sede"])

        def _calendar_page_url(**overrides):
            params = {
                "vista": (view_mode if view_mode != "general" else ""),
                "year": selected_year,
                "month": selected_month,
                "region": filters["region"],
                "sede": filters["sede"],
                "tipo": filters["tipo"],
                "estado": filters["estado"],
                "responsable": filters["responsable"],
                "fase": filters["fase"],
                "quick": filters["quick"],
            }
            params.update(overrides)
            clean = {}
            for key, value in params.items():
                if value in ("", None):
                    continue
                if key == "month":
                    try:
                        if int(value) <= 0:
                            continue
                    except Exception:
                        continue
                clean[key] = value
            return url_for("sst_calendario_operativo", **clean)

        for item in (plan_context.get("suggestions") or []):
            sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
            if sede_codigo:
                item["context_url"] = _calendar_page_url(sede=sede_codigo) + "#sstCalendarContext"

        all_events = list(context_raw["events"]) + _sst_calendar_build_plan_events(plan_context, selected_year, context_raw["today"])
        sedes_dashboard = list(plan_context.get("sedes_dashboard") or [])
        if filters["sede"]:
            sedes_scope = [item for item in sedes_dashboard if item["codigo"] == filters["sede"]]
        else:
            sedes_scope = list(sedes_dashboard)
        hallazgos_scope = [
            item for item in (plan_context.get("hallazgos") or [])
            if not filters["sede"] or str(item.get("sede_codigo") or "").strip().upper() == filters["sede"]
        ]
        actions_scope = [
            item for item in (plan_context.get("acciones") or [])
            if not filters["sede"] or str(item.get("sede_codigo") or "").strip().upper() == filters["sede"]
        ]
        suggestions_scope = [
            item for item in (plan_context.get("suggestions") or [])
            if not filters["sede"] or str(item.get("sede_codigo") or "").strip().upper() == filters["sede"]
        ]
        event_scope = [
            item for item in all_events
            if not filters["sede"] or str(item.get("sede_codigo") or "").strip().upper() == filters["sede"]
        ]

        def _project_text_match(value, keywords):
            text = str(value or "").strip().lower()
            return any(keyword in text for keyword in keywords)

        project_catalog = _sgsst_command_project_catalog()
        project_meta_by_key = dict(plan_context.get("command_project_meta") or {})
        project_scope_by_key = dict(plan_context.get("command_project_scope") or {})
        project_tree_rows = []
        total_scope_sedes = len(sedes_scope)
        for project in project_catalog:
            project_meta = project_meta_by_key.get(project["key"], {}) or {}
            if int(project_meta.get("activo", 1) or 1) != 1:
                continue
            scope_summary = _sgsst_command_scope_summary(
                project["key"],
                sedes_scope,
                project_scope_by_key.get(project["key"], {}),
            )
            module_rows = scope_summary["module_rows"]
            completed_sedes = scope_summary["completed_sedes"]
            pending_sedes = scope_summary["pending_sedes"]
            missing_sedes = scope_summary["missing_sedes"]
            no_aplica_sedes = scope_summary["no_aplica_sedes"]
            out_scope_sedes = scope_summary["out_scope_sedes"]
            applicable_total = scope_summary["applicable_total"]
            applicable_codes = set(scope_summary["applicable_codes"])
            excluded_codes = set(no_aplica_sedes) | set(out_scope_sedes)
            if not module_rows:
                continue
            planning_pct = _sgsst_plan_percent(len(completed_sedes), applicable_total) if applicable_total else 0
            project_actions = []
            project_hallazgos = []
            project_suggestions = []
            project_events = []
            for item in actions_scope:
                sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
                if sede_codigo and sede_codigo in excluded_codes:
                    continue
                if applicable_codes and sede_codigo and sede_codigo not in applicable_codes:
                    continue
                ref_text = " ".join([
                    str(item.get("modulo_origen") or ""),
                    str(item.get("titulo") or ""),
                    str(item.get("accion_requerida") or ""),
                ])
                if _project_text_match(ref_text, project["keywords"]):
                    project_actions.append(item)
            for item in hallazgos_scope:
                sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
                if sede_codigo and sede_codigo in excluded_codes:
                    continue
                if applicable_codes and sede_codigo and sede_codigo not in applicable_codes:
                    continue
                ref_text = " ".join([
                    str(item.get("modulo_origen") or ""),
                    str(item.get("titulo") or ""),
                    str(item.get("descripcion") or ""),
                    str(item.get("categoria") or ""),
                ])
                if _project_text_match(ref_text, project["keywords"]):
                    project_hallazgos.append(item)
            for item in suggestions_scope:
                sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
                if sede_codigo and sede_codigo in excluded_codes:
                    continue
                if applicable_codes and sede_codigo and sede_codigo not in applicable_codes:
                    continue
                if _project_text_match(item.get("module"), project["keywords"]):
                    project_suggestions.append(item)
            for item in event_scope:
                sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
                if sede_codigo and sede_codigo in excluded_codes:
                    continue
                if applicable_codes and sede_codigo and sede_codigo not in applicable_codes:
                    continue
                if str(item.get("type_key") or "").strip().lower() in project["type_keys"]:
                    project_events.append(item)
            project_events.sort(key=lambda item: (item.get("fecha_evento") or "9999-12-31", item.get("title") or ""))
            open_actions = [item for item in project_actions if not _sgsst_plan_is_action_closed(item.get("state_label"))]
            overdue_actions = [item for item in open_actions if item.get("overdue")]
            planning_events = [item for item in project_events if str(item.get("phase_key") or "").strip().lower() == "diagnostico"]
            operation_events = [item for item in project_events if str(item.get("phase_key") or "").strip().lower() == "operacion"]
            completed_controls = [item for item in operation_events if str(item.get("state_key") or "").strip().lower() == "cumplido"]
            open_controls = [item for item in operation_events if str(item.get("state_key") or "").strip().lower() != "cumplido"]
            overdue_controls = [item for item in open_controls if str(item.get("state_key") or "").strip().lower() == "vencido"]
            next_control = next(
                (
                    item for item in open_controls
                    if str(item.get("fecha_evento") or "").strip()
                ),
                None,
            )
            last_control = completed_controls[-1] if completed_controls else None
            planning_open = applicable_total > 0 and planning_pct < 100
            implementation_open = applicable_total > 0 and (not planning_open) and bool(open_actions or project_suggestions)
            active_stage = "plan" if planning_open else ("implementation" if implementation_open else "operation")
            planning_state = "active" if active_stage == "plan" else ("done" if applicable_total > 0 and planning_pct == 100 else "ready")
            implementation_state = "active" if active_stage == "implementation" else ("done" if active_stage == "operation" else "locked")
            operation_state = "active" if active_stage == "operation" else "locked"
            planning_summary = (f"{planning_pct}% relevado" if applicable_total else "Sin alcance")
            planning_caption = (
                f"{len(completed_sedes)} completas, {len(pending_sedes)} pendientes, {len(missing_sedes)} sin registrar"
                if applicable_total else
                "Sin sedes en alcance"
            )
            planning_scope_note = " - ".join(filter(None, [
                f"{len(no_aplica_sedes)} no aplica" if no_aplica_sedes else "",
                f"{len(out_scope_sedes)} fuera de alcance" if out_scope_sedes else "",
            ]))
            if applicable_total == 0:
                stage_label = "Sin alcance"
                health_label = "No aplica" if no_aplica_sedes else "Fuera de alcance"
                health_class = "muted"
                next_step = "Definir alcance"
                implementation_status = "Sin alcance"
                implementation_note = "No hay sedes activas en este proyecto."
                operation_status = "Sin alcance"
                operation_summary = "Se activa cuando exista una sede aplicable."
                active_stage = "plan"
                planning_state = "active"
                implementation_state = "locked"
                operation_state = "locked"
            elif planning_pct < 100:
                stage_label = "Planificacion"
                health_label = "Sin iniciar" if planning_pct == 0 else "En desarrollo"
                health_class = "muted" if planning_pct == 0 else "warn"
                if missing_sedes:
                    next_step = f"Cargar {missing_sedes[0]}"
                elif pending_sedes:
                    next_step = f"Relevar {pending_sedes[0]}"
                else:
                    next_step = "Cerrar relevamiento"
                implementation_status = "Espera diagnostico"
                implementation_note = "Se habilita al cerrar Planificacion"
                operation_status = "Sin iniciar"
                operation_summary = "Disponible al finalizar la implementacion."
            elif open_actions or project_suggestions:
                stage_label = "Implementacion"
                health_label = "Detenido" if (overdue_actions or overdue_controls) else "En desarrollo"
                health_class = "risk" if (overdue_actions or overdue_controls) else "warn"
                next_step = (
                    str((overdue_actions[0] if overdue_actions else open_actions[0]).get("titulo") or "").strip()
                    if open_actions else
                    (f"Revisar {project_suggestions[0]['sede_codigo']}" if project_suggestions else "Continuar implementacion")
                )
                implementation_status = "En curso"
                implementation_note = (
                    f"{len(open_actions)} accion(es) abierta(s)"
                    if open_actions else
                    f"{len(project_suggestions)} sugerencia(s) pendiente(s)"
                )
                operation_status = "Sin iniciar"
                operation_summary = "Disponible al finalizar la implementacion."
            else:
                stage_label = "Operacion"
                health_label = "Operativo" if not overdue_controls else "Detenido"
                health_class = "ok" if not overdue_controls else "risk"
                if next_control and next_control.get("fecha_evento"):
                    next_step = f"Control {_sst_calendar_short_date(next_control.get('fecha_evento'))}"
                else:
                    next_step = "Seguimiento normal"
                implementation_status = "Finalizada"
                implementation_note = "Sin acciones abiertas."
                operation_status = "Operativa" if not overdue_controls else "Con alertas"
                operation_summary = (
                    f"{len(open_controls)} control(es) activo(s)"
                    if open_controls else
                    "Sin alertas operativas"
                )
            project_tree_rows.append({
                "key": project["key"],
                "label": project["label"],
                "icon": project["icon"],
                "responsable": _sgsst_command_project_responsable(
                    project_actions,
                    project_events,
                    str(project_meta.get("responsable") or "").strip() or project["fallback_responsible"],
                ),
                "progress_text": f"{len(completed_sedes)}/{applicable_total} ({planning_pct}%)" if applicable_total else "0/0",
                "planning_pct": planning_pct,
                "stage_label": stage_label,
                "health_label": health_label,
                "health_class": health_class,
                "next_step": next_step,
                "hallazgos_count": len(project_hallazgos),
                "actions_count": len(open_actions),
                "open_url": (module_rows[0]["url"] if filters["sede"] and module_rows else _sgsst_command_project_open_url(project["key"], filters["sede"])),
                "actions_url": url_for("sst_plan_implementacion", vista="acciones", sede=(filters["sede"] or None), prefill_modulo=project["label"]),
                "timeline_url": _calendar_page_url(tipo=project["timeline_type"], fase="", quick=""),
                "config_url": url_for(
                    "sst_project_config",
                    project_key=project["key"],
                    year=selected_year,
                    month=(selected_month or None),
                    sede=(filters["sede"] or None),
                    tipo=(filters["tipo"] or None),
                    estado=(filters["estado"] or None),
                    region=(filters["region"] or None),
                    responsable=(filters["responsable"] or None),
                    fase=(filters["fase"] or None),
                    quick=(filters["quick"] or None),
                ),
                "should_open": (filters["tipo"] in project["type_keys"]),
                "active_stage": active_stage,
                "stage_track": [
                    {"key": "plan", "label": "Planificacion", "state": ("current" if active_stage == "plan" else "done")},
                    {"key": "implementation", "label": "Implementacion", "state": ("current" if active_stage == "implementation" else ("done" if active_stage == "operation" else "todo"))},
                    {"key": "operation", "label": "Operacion", "state": ("current" if active_stage == "operation" else "todo")},
                ],
                "planning": {
                    "card_state": planning_state,
                    "applicable_total": applicable_total,
                    "no_aplica_count": len(no_aplica_sedes),
                    "out_scope_count": len(out_scope_sedes),
                    "completed_count": len(completed_sedes),
                    "pending_count": len(pending_sedes),
                    "missing_count": len(missing_sedes),
                    "completed_preview": completed_sedes[:8],
                    "pending_preview": pending_sedes[:8],
                    "missing_preview": missing_sedes[:8],
                    "no_aplica_preview": no_aplica_sedes[:8],
                    "out_scope_preview": out_scope_sedes[:8],
                    "record_count": len(planning_events),
                    "summary": planning_summary,
                    "caption": planning_caption,
                    "scope_note": planning_scope_note,
                    "detail_available": bool(completed_sedes or pending_sedes or missing_sedes or no_aplica_sedes or out_scope_sedes),
                },
                "implementation": {
                    "card_state": implementation_state,
                    "status": implementation_status,
                    "note": implementation_note,
                    "actions_open": len(open_actions),
                    "actions_overdue": len(overdue_actions),
                    "suggestions_count": len(project_suggestions),
                    "show_items": implementation_open,
                    "next_items": [
                        {
                            "title": str(item.get("titulo") or item.get("accion_requerida") or "Accion SG-SST").strip(),
                            "meta": str(item.get("fecha_objetivo_label") or item.get("state_label") or "").strip(),
                            "url": item.get("detail_url") or url_for("sst_plan_implementacion", vista="acciones"),
                        }
                        for item in open_actions[:3]
                    ],
                    "suggestions": [
                        {
                            "title": f"{item.get('sede_codigo') or ''} - {item.get('reason') or ''}".strip(" -"),
                            "url": item.get("action_url") or item.get("origin_url") or item.get("context_url") or _sgsst_command_project_open_url(project["key"], filters["sede"]),
                        }
                        for item in project_suggestions[:3]
                    ],
                },
                "operation": {
                    "card_state": operation_state,
                    "enabled": active_stage == "operation",
                    "status": operation_status,
                    "last_control": _sst_calendar_short_date(last_control.get("fecha_evento")) if last_control else "-",
                    "next_control": _sst_calendar_short_date(next_control.get("fecha_evento")) if next_control else "-",
                    "overdue_controls": len(overdue_controls),
                    "open_controls": len(open_controls),
                    "summary": operation_summary,
                },
            })
        project_tree_rows.sort(key=lambda item: (
            0 if item["health_class"] == "risk" else (1 if item["health_class"] == "warn" else (2 if item["health_class"] == "ok" else 3)),
            item["label"],
        ))
        filtered_events = _sst_calendar_filter_events(all_events, filters)
        visible_events = _sst_calendar_visible_events(filtered_events)
        focus_month = selected_month or (context_raw["today"].month if selected_year == context_raw["today"].year else 1)
        matrix_rows, matrix_payload = _sst_calendar_build_matrix(context_raw["sedes"], visible_events)
        summary = _sst_calendar_summary(visible_events, focus_month)
        mobile_rows = _sst_calendar_mobile_rows(context_raw["sedes"], matrix_payload, focus_month)

        region_options = sorted({
            (sede.get("region") or "").strip()
            for sede in context_raw["sedes"]
            if (sede.get("region") or "").strip()
        })
        responsable_options = sorted({
            (event.get("responsible") or "").strip()
            for event in all_events
            if (event.get("responsible") or "").strip()
        })
        type_options = [
            {"value": "matafuegos", "label": "Matafuegos", "short": "MF", "icon": "\U0001F9EF"},
            {"value": "desinfeccion", "label": "Desinfeccion", "short": "DES", "icon": "\U0001F9F9"},
            {"value": "luces", "label": "Luces de emergencia", "short": "LUC", "icon": "\U0001F6A8"},
            {"value": "carteleria", "label": "Carteleria", "short": "CAR", "icon": "\U0001F6AA"},
            {"value": "visita", "label": "Visitas ART", "short": "VIS", "icon": "\U0001F477"},
            {"value": "documentacion", "label": "Documentacion", "short": "DOC", "icon": "\U0001F4C4"},
            {"value": "planos", "label": "Evacuacion", "short": "PE", "icon": "\U0001F6A8"},
            {"value": "hallazgo", "label": "Hallazgos", "short": "HAL", "icon": "\u26A0"},
            {"value": "seguimiento", "label": "Acciones", "short": "SEG", "icon": "\U0001F4CC"},
        ]
        state_options = [
            {"value": key, "label": meta["label"], "class": meta["class"], "icon": meta.get("icon", "")}
            for key, meta in SST_CALENDAR_STATE_META.items()
        ]
        source_counts = []
        type_counts_map = {}
        type_total_counts_map = {}
        for type_item in type_options:
            type_total_counts_map[type_item["value"]] = sum(
                int(event.get("units", 1) or 1)
                for event in all_events
                if event["type_key"] == type_item["value"]
            )
        for type_item in type_options:
            count_value = sum(int(event.get("units", 1) or 1) for event in visible_events if event["type_key"] == type_item["value"])
            type_counts_map[type_item["value"]] = count_value
            if count_value <= 0:
                continue
            source_counts.append({
                "label": type_item["label"],
                "short": _sst_calendar_type_meta(type_item["value"])["short"],
                "icon": _sst_calendar_type_meta(type_item["value"]).get("icon", ""),
                "count": count_value,
            })
        matafuegos_overview = list(context_raw.get("matafuegos_overview") or [])
        matafuegos_visible = any(event["type_key"] == "matafuegos" for event in visible_events)
        selected_month_for_next = selected_month or 1
        matafuegos_next = next(
            (
                item for item in matafuegos_overview
                if (int(item["year"]), int(item["month"])) >= (int(selected_year), int(selected_month_for_next))
            ),
            matafuegos_overview[0] if matafuegos_overview else None,
        )
        matrix_payload["__meta__"] = {
            "today_month": int(context_raw["today"].month),
            "today_year": int(context_raw["today"].year),
            "selected_year": int(selected_year),
            "focus_month": int(focus_month),
            "focus_month_label": _sst_calendar_month_name(focus_month),
            "type_counts": type_counts_map,
            "type_total_counts": type_total_counts_map,
        }

        selected_sede = next(
            (sede for sede in context_raw["sedes"] if sede["codigo"] == filters["sede"]),
            None,
        )
        selected_sede_row = plan_context.get("selected_sede_row")
        selected_sede_events = []
        if selected_sede_row:
            for event in visible_events:
                if str(event.get("sede_codigo") or "").strip().upper() != selected_sede_row["codigo"]:
                    continue
                if event.get("is_suggestion"):
                    continue
                selected_sede_events.append({
                    "title": event.get("title") or event.get("type_label") or "Evento SG-SST",
                    "detail": event.get("detail") or "",
                    "date_label": _sst_calendar_short_date(event.get("fecha_evento")),
                    "sort_date": event.get("fecha_evento") or "",
                    "phase_title": event.get("phase_title") or "",
                    "type_icon": event.get("type_icon") or "",
                    "state_label": event.get("state_label") or "",
                    "state_class": event.get("state_class") or "muted",
                    "responsible": event.get("responsible") or "",
                    "url_detail": event.get("url_detail") or "",
                })
            selected_sede_events.sort(key=lambda item: (item["sort_date"] or "9999-12-31", item["title"]))
        selected_sede_suggestions = []
        if selected_sede_row:
            selected_sede_suggestions = [
                item
                for item in (plan_context.get("suggestions") or [])
                if str(item.get("sede_codigo") or "").strip().upper() == selected_sede_row["codigo"]
            ]
        selected_sede_phase_cards = []
        if selected_sede_row:
            selected_sede_phase_cards = [
                {
                    "tone": "tone-blue",
                    "kicker": "Fase 1",
                    "title": "Diagnostico",
                    "lines": [
                        selected_sede_row.get("diagnostico_text") or "Sin relevamiento consolidado",
                        f"Hallazgos abiertos: {selected_sede_row.get('hallazgos_abiertos', 0)}",
                    ],
                },
                {
                    "tone": "tone-warn",
                    "kicker": "Fase 2",
                    "title": "Implementacion",
                    "lines": [
                        selected_sede_row.get("implementacion_text") or "Sin acciones cargadas",
                        f"Acciones abiertas: {selected_sede_row.get('acciones_abiertas', 0)}",
                    ],
                },
                {
                    "tone": "tone-ok",
                    "kicker": "Fase 3",
                    "title": "Operacion y control",
                    "lines": [
                        selected_sede_row.get("operacion_text") or "Sin controles activos",
                        ("Proximo control: con alertas" if int(selected_sede_row.get("periodic_overdue") or 0) > 0 else "Proximo control: en fecha"),
                    ],
                },
            ]

        for row in matrix_rows:
            row["sede_context_url"] = _calendar_page_url(sede=row["sede"]["codigo"]) + "#sstCalendarContext"
        for row in mobile_rows:
            row["sede_context_url"] = _calendar_page_url(sede=row["sede_codigo"]) + "#sstCalendarContext"

        quick_phase_filters = [
            {"label": "Todas", "active": not filters["fase"], "url": _calendar_page_url(fase="")},
            {"label": "\U0001F4CB Diagnostico", "active": filters["fase"] == "diagnostico", "url": _calendar_page_url(fase="diagnostico")},
            {"label": "\U0001F527 Implementacion", "active": filters["fase"] == "implementacion", "url": _calendar_page_url(fase="implementacion")},
            {"label": "\U0001F501 Operacion", "active": filters["fase"] == "operacion", "url": _calendar_page_url(fase="operacion")},
        ]
        quick_state_filters = [
            {"label": "\u26A0\uFE0F Pendientes", "active": filters["quick"] == "pendientes", "url": _calendar_page_url(quick="pendientes")},
            {"label": "\U0001F534 Vencidos", "active": filters["quick"] == "vencidos", "url": _calendar_page_url(quick="vencidos")},
            {"label": "\u2705 Finalizados", "active": filters["quick"] == "finalizados", "url": _calendar_page_url(quick="finalizados")},
        ]

        return render_template(
            "sst_calendario_operativo.html",
            sst_section="implementacion" if view_mode == "implementacion" else "inicio",
            operativa_nav=build_operativa_nav_context(
                context_raw["sedes"],
                filters["sede"] or (selected_sede["codigo"] if selected_sede else (context_raw["sedes"][0]["codigo"] if context_raw["sedes"] else "")),
                "sst_calendario",
                filters={
                    "vista": (view_mode if view_mode != "general" else ""),
                    "year": selected_year,
                    "month": selected_month,
                    "region": filters["region"],
                    "tipo": filters["tipo"],
                    "estado": filters["estado"],
                    "responsable": filters["responsable"],
                    "fase": filters["fase"],
                    "quick": filters["quick"],
                },
            ),
            selected_year=selected_year,
            selected_month=selected_month,
            focus_month=focus_month,
            focus_month_label=_sst_calendar_month_name(focus_month),
            filters=filters,
            summary=summary,
            matrix_rows=matrix_rows,
            matrix_payload=matrix_payload,
            mobile_rows=mobile_rows,
            quick_phase_filters=quick_phase_filters,
            quick_state_filters=quick_state_filters,
            project_tree_rows=project_tree_rows,
            project_scope_total=total_scope_sedes,
            source_counts=source_counts,
            matafuegos_overview=matafuegos_overview,
            matafuegos_visible=matafuegos_visible,
            matafuegos_next=matafuegos_next,
            sedes=context_raw["sedes"],
            selected_sede=selected_sede,
            selected_sede_row=selected_sede_row,
            selected_sede_events=selected_sede_events[:10],
            selected_sede_suggestions=selected_sede_suggestions[:6],
            selected_sede_phase_cards=selected_sede_phase_cards,
            plan_actions_url=url_for("sst_plan_implementacion", vista="acciones", sede=(filters["sede"] or None)),
            library_url=url_for("sgsst_documentacion_home"),
            seguimiento_url=url_for("sst_plan"),
            region_options=region_options,
            responsable_options=responsable_options,
            type_options=type_options,
            state_options=state_options,
            year_options=context_raw["event_years"],
            month_options=[{"value": number, "label": label} for number, label in SST_CALENDAR_MONTHS],
            total_filtered_events=len(visible_events),
            today_iso=context_raw["today"].isoformat(),
            today_year=context_raw["today"].year,
            today_month=context_raw["today"].month,
            view_mode=view_mode,
        )

    def _sst_fetch_sedes_base(con):
        return con.execute("""
            SELECT
                UPPER(COALESCE(codigo, '')) AS codigo,
                COALESCE(nombre, '') AS nombre,
                COALESCE(fuero, '') AS fuero,
                COALESCE(ciudad, '') AS ciudad,
                COALESCE(direccion, '') AS direccion
            FROM sedes_mpd
            WHERE TRIM(COALESCE(codigo, '')) <> ''
            ORDER BY codigo
        """).fetchall()

    def _sst_fetch_depositos_map(con):
        rows = con.execute("""
            SELECT
                UPPER(COALESCE(codigo_sede, '')) AS sede_codigo,
                UPPER(COALESCE(codigo_local, '')) AS deposito_codigo,
                COALESCE(descripcion, '') AS descripcion
            FROM sedes_depositos
            ORDER BY codigo_sede, codigo_local
        """).fetchall()
        depositos_map = {}
        depositos_by_sede = defaultdict(list)
        for row in rows:
            sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            deposito_codigo = (_row_value(row, "deposito_codigo", "") or "").strip().upper()
            descripcion = (_row_value(row, "descripcion", "") or "").strip()
            if not sede_codigo or not deposito_codigo:
                continue
            depositos_map[(sede_codigo, deposito_codigo)] = descripcion
            depositos_by_sede[sede_codigo].append({
                "codigo": deposito_codigo,
                "descripcion": descripcion,
                "label": f"{deposito_codigo} - {descripcion}" if descripcion else deposito_codigo,
            })
        for sede_codigo in list(depositos_by_sede.keys()):
            depositos_by_sede[sede_codigo].sort(key=lambda item: item["codigo"])
        return depositos_map, depositos_by_sede

    def _sst_deposito_label(sede_codigo, deposito_codigo, depositos_map):
        dep = (_sst_clean_upper(deposito_codigo) or "").strip()
        if not dep:
            return "-"
        descripcion = (depositos_map.get((_sst_clean_upper(sede_codigo), dep)) or "").strip()
        return f"{dep} - {descripcion}" if descripcion else dep

    def _sst_dates_for_month(record, fields):
        values = []
        for field in fields:
            parsed = _sst_calendar_parse_date(record.get(field, ""))
            if parsed:
                values.append(parsed)
        return values

    def _sst_carteleria_canonical_tipo_code(value):
        raw_code = (_sst_clean_upper(value) or "").strip().upper()
        if not raw_code:
            return ""
        canonical = SST_CARTELERIA_CANONICAL_TIPO_MAP.get(raw_code, raw_code)
        return canonical if canonical in SST_CARTELERIA_TIPO_LABELS else ""

    def _sst_carteleria_normalize_aplica(value, fallback=""):
        raw_value = (_sst_clean_upper(value) or "").strip().upper()
        legacy_map = {
            "SI": "SI",
            "S": "SI",
            "1": "SI",
            "TRUE": "SI",
            "YES": "SI",
            "APLICA": "SI",
            "REQUERIDO": "SI",
            "INSTALADO": "SI",
            "NO": "NO",
            "0": "NO",
            "FALSE": "NO",
            "NO_APLICA": "NO",
            "NO APLICA": "NO",
            "NO_RELEVADO": "NO_RELEVADO",
            "SIN_RELEVAR": "NO_RELEVADO",
        }
        normalized = legacy_map.get(raw_value, raw_value)
        if normalized in SST_CARTELERIA_APLICA_LABELS:
            return normalized
        return fallback if fallback in SST_CARTELERIA_APLICA_LABELS else "NO_RELEVADO"

    def _sst_carteleria_normalize_manual_state(value):
        raw_state = (_sst_clean_upper(value) or "").strip().upper()
        legacy_map = {
            "NO_RELEVADO": "NO_RELEVADO",
            "RELEVADO": "RELEVADO",
            "RELEVADO_SIN_FALTANTES": "RELEVADO",
            "RELEVADO_CON_FALTANTES": "PENDIENTE_SOLICITUD",
            "SOLICITAR_A_COMPRAS": "PENDIENTE_SOLICITUD",
            "PENDIENTE_DE_SOLICITUD": "PENDIENTE_SOLICITUD",
            "PENDIENTE_SOLICITUD": "PENDIENTE_SOLICITUD",
            "PEDIDO_REALIZADO": "COMPRA_EN_PROCESO",
            "EN_PROCESO_DE_COMPRA": "COMPRA_EN_PROCESO",
            "COMPRA_EN_PROCESO": "COMPRA_EN_PROCESO",
            "DISPONIBLE": "MATERIAL_RECIBIDO",
            "MATERIAL_RECIBIDO": "MATERIAL_RECIBIDO",
            "PROGRAMADO": "INSTALACION_PROGRAMADA",
            "INSTALACION_PROGRAMADA": "INSTALACION_PROGRAMADA",
            "EJECUTADO": "COMPLETO",
            "VERIFICADO": "COMPLETO",
            "COMPLETO": "COMPLETO",
            "OBSERVADO": "RELEVADO",
        }
        normalized = legacy_map.get(raw_state, raw_state)
        return normalized if normalized in SST_CARTELERIA_STATE_LABELS else ""

    def _sst_carteleria_has_relevamiento(record):
        if _sst_carteleria_normalize_aplica(record.get("aplica")) != "NO_RELEVADO":
            return True
        for field in (
            "fecha_solicitud",
            "fecha_pedido",
            "fecha_entrega",
            "fecha_disponibilidad",
            "fecha_instalacion",
            "fecha_programada_colocacion",
            "fecha_colocacion",
            "observaciones",
        ):
            if str(record.get(field) or "").strip():
                return True
        if _sst_carteleria_normalize_manual_state(record.get("estado")):
            return True
        return any(_sst_int_nonneg(record.get(field)) for field in ("cantidad_requerida", "cantidad_instalada"))

    def _sst_carteleria_state_code(record):
        tipos_sin_relevar = _sst_int_nonneg(record.get("tipos_sin_relevar"))
        tipos_relevados = _sst_int_nonneg(record.get("tipos_relevados"))
        if tipos_sin_relevar > 0:
            return "NO_RELEVADO"
        raw_state = _sst_carteleria_normalize_manual_state(record.get("estado"))
        requerida = _sst_int_nonneg(record.get("cantidad_requerida") or record.get("requeridos"))
        instalada = _sst_int_nonneg(record.get("cantidad_instalada") or record.get("instalados"))
        faltante = max(requerida - instalada, 0)
        fecha_solicitud = str(record.get("fecha_solicitud") or record.get("fecha_pedido") or "").strip()
        fecha_entrega = str(record.get("fecha_entrega") or record.get("fecha_disponibilidad") or "").strip()
        fecha_instalacion = (
            str(record.get("fecha_instalacion") or "").strip()
            or str(record.get("fecha_colocacion") or "").strip()
            or str(record.get("fecha_programada_colocacion") or "").strip()
        )
        if not _sst_carteleria_has_relevamiento(record) and tipos_relevados <= 0:
            return "NO_RELEVADO"
        if fecha_instalacion and faltante > 0:
            return "INSTALACION_PROGRAMADA"
        if fecha_entrega and faltante > 0:
            return "MATERIAL_RECIBIDO"
        if fecha_solicitud and faltante > 0:
            return "COMPRA_EN_PROCESO"
        if requerida > 0 and instalada >= requerida:
            return "COMPLETO"
        if requerida > 0 and faltante > 0:
            return "PENDIENTE_SOLICITUD"
        if raw_state in {"COMPRA_EN_PROCESO", "MATERIAL_RECIBIDO", "INSTALACION_PROGRAMADA"} and faltante > 0:
            return raw_state
        if tipos_relevados > 0:
            return "COMPLETO" if faltante == 0 else "RELEVADO"
        return "RELEVADO"

    def _sst_carteleria_action_text(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_carteleria_state_code(record))
        faltantes = _sst_int_nonneg(record.get("cantidad_faltante") or record.get("faltantes"))
        if state_code == "NO_RELEVADO":
            return "Completar relevamiento."
        if state_code == "RELEVADO":
            return "Sin acciones pendientes." if faltantes <= 0 else f"Solicitar compra de {faltantes} cartel{'es' if faltantes != 1 else ''}."
        if state_code == "PENDIENTE_SOLICITUD":
            return f"Solicitar compra de {faltantes} cartel{'es' if faltantes != 1 else ''}."
        if state_code == "COMPRA_EN_PROCESO":
            return "Esperar entrega."
        if state_code == "MATERIAL_RECIBIDO":
            return "Programar colocacion."
        if state_code == "INSTALACION_PROGRAMADA":
            return "Ejecutar colocacion."
        if state_code == "COMPLETO":
            return "Sin acciones pendientes."
        return "Abrir"

    def _sst_carteleria_followup_text(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_carteleria_state_code(record))
        faltantes = max(_sst_int_nonneg(record.get("cantidad_faltante") or record.get("faltantes")), 1)
        if state_code == "NO_RELEVADO":
            return "Completar relevamiento de carteleria por sede."
        if state_code in {"RELEVADO", "PENDIENTE_SOLICITUD"}:
            return f"Solicitar compra e implementar {faltantes} cart{'eles' if faltantes != 1 else 'el'} pendientes."
        if state_code == "COMPRA_EN_PROCESO":
            return "Hacer seguimiento de la compra de carteleria."
        if state_code == "MATERIAL_RECIBIDO":
            return "Programar colocacion de la carteleria recibida."
        if state_code == "INSTALACION_PROGRAMADA":
            return "Ejecutar la colocacion programada de carteleria."
        if state_code == "COMPLETO":
            return "Sin acciones pendientes sobre carteleria."
        return "Gestionar carteleria de la sede."

    def _sst_carteleria_has_pending_action(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_carteleria_state_code(record))
        return state_code in SST_CARTELERIA_PENDING_STATES

    def _sst_carteleria_record_sort_key(item):
        return (
            str(item.get("ultima_actualizacion") or ""),
            str(item.get("fecha_actualizacion") or ""),
            str(item.get("fecha_creacion") or ""),
            int(item.get("id") or 0),
        )

    def _sst_carteleria_type_detail(records):
        ordered_records = sorted(list(records or []), key=_sst_carteleria_record_sort_key, reverse=True)
        primary_record = ordered_records[0] if ordered_records else None
        aplica_state = "NO_RELEVADO"
        if primary_record:
            fallback_aplica = "SI" if any(
                _sst_int_nonneg(item.get("cantidad_requerida")) > 0 or _sst_int_nonneg(item.get("cantidad_instalada")) > 0
                for item in ordered_records
            ) else "NO"
            aplica_state = _sst_carteleria_normalize_aplica(primary_record.get("aplica"), fallback_aplica)
        requerida = 0
        instalada = 0
        if aplica_state == "SI":
            if primary_record and primary_record.get("piso") == SST_CARTELERIA_PLACEHOLDER_PISO and primary_record.get("deposito_codigo") == SST_CARTELERIA_PLACEHOLDER_DEPOSITO:
                requerida = _sst_int_nonneg(primary_record.get("cantidad_requerida"))
                instalada = _sst_int_nonneg(primary_record.get("cantidad_instalada"))
            else:
                requerida = sum(_sst_int_nonneg(item.get("cantidad_requerida")) for item in ordered_records)
                instalada = sum(_sst_int_nonneg(item.get("cantidad_instalada")) for item in ordered_records)
        faltante = max(requerida - instalada, 0) if aplica_state == "SI" else 0
        return {
            "primary_record": primary_record,
            "aplica": aplica_state,
            "aplica_label": SST_CARTELERIA_APLICA_LABELS.get(aplica_state, "No relevado"),
            "cantidad_requerida": requerida,
            "cantidad_instalada": instalada,
            "cantidad_faltante": faltante,
            "record_count": len(ordered_records),
            "records": ordered_records,
        }

    def _sst_luces_normalize_manual_state(value):
        raw_state = _sst_clean_upper(value)
        legacy_map = {
            "NO_APLICA": "NO_APLICA",
            "NO_RELEVADO": "SIN_RELEVAR",
            "OPERATIVA": "COMPLETO",
            "COMPLETO_OPERATIVO": "COMPLETO",
            "PARCIALMENTE_OPERATIVA": "MANTENIMIENTO",
            "FUERA_DE_SERVICIO": "MANTENIMIENTO",
            "FALTA_EQUIPO": "PENDIENTE_DE_SOLICITUD",
            "FALTAN_EQUIPOS": "PENDIENTE_DE_SOLICITUD",
            "SOLICITAR_A_COMPRAS": "PENDIENTE_DE_SOLICITUD",
            "FALTA_SOLICITAR": "PENDIENTE_DE_SOLICITUD",
            "PEDIDO_REALIZADO": "EN_PROCESO_DE_COMPRA",
            "SOLICITADO_A_COMPRAS": "EN_PROCESO_DE_COMPRA",
            "DISPONIBLE": "MATERIAL_RECIBIDO",
            "ENTREGADO": "MATERIAL_RECIBIDO",
            "PENDIENTE_DE_COLOCACION": "MATERIAL_RECIBIDO",
            "INTERVENCION_PROGRAMADA": "INSTALACION_PROGRAMADA",
            "COLOCACION_PROGRAMADA": "INSTALACION_PROGRAMADA",
            "INTERVENCION_REALIZADA": "COMPLETO",
            "INSTALADO": "COMPLETO",
            "VERIFICACION_PENDIENTE": "COMPLETO",
            "VERIFICADO": "COMPLETO",
            "VERIFICADA": "COMPLETO",
            "REQUIERE_REPARACION": "MANTENIMIENTO",
            "REQUIERE_BATERIA": "MANTENIMIENTO",
            "REQUIERE_REEMPLAZO": "MANTENIMIENTO",
            "REQUIERE_MANTENIMIENTO": "MANTENIMIENTO",
            "OBSERVADO": "RELEVADO",
            "OBSERVADA": "RELEVADO",
        }
        normalized = legacy_map.get(raw_state, raw_state)
        return normalized if normalized in SST_LUCES_STATE_LABELS else ""

    def _sst_luces_has_relevamiento(record):
        if record.get("plan_markers"):
            return True
        for field in (
            "fecha_solicitud_compra",
            "fecha_entrega",
            "fecha_programada_colocacion",
            "fecha_colocacion",
            "observaciones",
            "motivo_no_aplica",
        ):
            if str(record.get(field) or "").strip():
                return True
        return any(_sst_int_nonneg(record.get(field)) for field in ("cantidad_requerida", "cantidad_instalada"))

    def _sst_luces_state_code(record):
        if not _sst_luces_has_relevamiento(record):
            return "SIN_RELEVAR"
        if not _sst_bool_flag(record.get("aplica", 1)):
            return "NO_APLICA"
        raw_state = _sst_luces_normalize_manual_state(record.get("estado"))
        if raw_state in SST_MANUAL_LUCES_STATES:
            return raw_state
        requerida = _sst_int_nonneg(record.get("cantidad_requerida"))
        instalada = _sst_int_nonneg(record.get("cantidad_instalada"))
        faltante = max(requerida - instalada, 0)
        fecha_solicitud = str(record.get("fecha_solicitud_compra") or "").strip()
        fecha_entrega = str(record.get("fecha_entrega") or "").strip()
        fecha_instalacion = (
            str(record.get("fecha_colocacion") or "").strip()
            or str(record.get("fecha_programada_colocacion") or "").strip()
        )
        fecha_mantenimiento = str(record.get("fecha_mantenimiento") or "").strip()
        if fecha_mantenimiento:
            return "MANTENIMIENTO"
        if requerida > 0 and instalada >= requerida:
            return "COMPLETO"
        if fecha_entrega:
            if fecha_instalacion:
                return "INSTALACION_PROGRAMADA"
            return "MATERIAL_RECIBIDO"
        if fecha_solicitud:
            return "EN_PROCESO_DE_COMPRA"
        if requerida > instalada:
            return "PENDIENTE_DE_SOLICITUD"
        return "RELEVADO"

    def _sst_luces_action_text(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_luces_state_code(record))
        faltantes = _sst_int_nonneg(record.get("cantidad_faltante") or record.get("faltantes"))
        if state_code == "NO_APLICA":
            return "Sin acciones pendientes."
        if state_code == "SIN_RELEVAR":
            return "Relevar sede."
        if state_code == "RELEVADO":
            if not _sst_bool_flag(record.get("aplica", 1)):
                return "Sin acciones pendientes."
            return "Solicitar compra." if faltantes > 0 else "Sin acciones pendientes."
        if state_code == "PENDIENTE_DE_SOLICITUD":
            return "Solicitar compra."
        if state_code == "EN_PROCESO_DE_COMPRA":
            return "Esperar entrega."
        if state_code == "MATERIAL_RECIBIDO":
            return "Programar instalacion."
        if state_code == "INSTALACION_PROGRAMADA":
            return "Instalar equipos."
        if state_code == "COMPLETO":
            return "Sin acciones pendientes."
        if state_code == "MANTENIMIENTO":
            return "Coordinar mantenimiento."
        return "Abrir"

    def _sst_luces_followup_text(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_luces_state_code(record))
        faltantes = max(_sst_int_nonneg(record.get("cantidad_faltante") or record.get("faltantes")), 1)
        if state_code == "NO_APLICA":
            return "Sin acciones pendientes sobre luces de emergencia."
        if state_code == "SIN_RELEVAR":
            return "Realizar relevamiento de luces de emergencia."
        if state_code in {"RELEVADO", "PENDIENTE_DE_SOLICITUD"}:
            return f"Solicitar compra e implementar {faltantes} luz{'es' if faltantes != 1 else ''} de emergencia."
        if state_code == "EN_PROCESO_DE_COMPRA":
            return "Hacer seguimiento de la compra de luces de emergencia."
        if state_code == "MATERIAL_RECIBIDO":
            return "Programar instalacion de luces de emergencia recibidas."
        if state_code == "INSTALACION_PROGRAMADA":
            return "Ejecutar la instalacion programada de luces de emergencia."
        if state_code == "MANTENIMIENTO":
            return "Coordinar mantenimiento de luces de emergencia."
        if state_code == "COMPLETO":
            return "Sin acciones pendientes sobre luces de emergencia."
        return "Gestionar luces de emergencia de la sede."

    def _sst_luces_has_pending_action(record):
        state_code = _sst_clean_upper(record.get("state_code") or _sst_luces_state_code(record))
        return state_code in SST_LUCES_PENDING_STATES

    def _sst_luces_canonical_plan_state(value):
        raw_state = _sst_clean_upper(value).replace("-", "_").replace(" ", "_")
        state_map = {
            "PREVISTA": "prevista",
            "INSTALADA": "instalada",
            "OPERATIVA": "instalada",
            "FUERA_SERVICIO": "fuera_servicio",
            "FUERA_DE_SERVICIO": "fuera_servicio",
            "MANTENIMIENTO": "fuera_servicio",
            "NO_APLICA": "no_aplica",
        }
        return state_map.get(raw_state, "")

    def _sst_luces_unpack_observaciones(raw_value):
        raw_text = str(raw_value or "").strip()
        if not raw_text:
            return "", []
        if not raw_text.startswith(SST_LUCES_PLAN_PREFIX):
            return raw_text, []
        try:
            payload = json.loads(raw_text[len(SST_LUCES_PLAN_PREFIX):].strip() or "{}")
        except Exception:
            return raw_text, []
        note = str((payload or {}).get("note") or "").strip()
        markers = []
        for item in ((payload or {}).get("markers") or []):
            if not isinstance(item, dict):
                continue
            state_code = _sst_luces_canonical_plan_state(item.get("state"))
            if not state_code:
                continue
            try:
                x_val = float(item.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(item.get("y", 0.5))
            except Exception:
                y_val = 0.5
            markers.append({
                "state": state_code,
                "label": str(item.get("label") or "").strip(),
                "local": (_sst_clean_upper(item.get("local")) or "").strip().upper(),
                "x": max(0.03, min(0.97, x_val)),
                "y": max(0.03, min(0.97, y_val)),
            })
        return note, markers

    def _sst_luces_pack_observaciones(markers=None, note=""):
        safe_markers = []
        for item in (markers or []):
            if not isinstance(item, dict):
                continue
            state_code = _sst_luces_canonical_plan_state(item.get("state"))
            if not state_code:
                continue
            try:
                x_val = float(item.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(item.get("y", 0.5))
            except Exception:
                y_val = 0.5
            safe_markers.append({
                "state": state_code,
                "label": str(item.get("label") or "").strip(),
                "local": (_sst_clean_upper(item.get("local")) or "").strip().upper(),
                "x": max(0.03, min(0.97, x_val)),
                "y": max(0.03, min(0.97, y_val)),
            })
        payload = {
            "note": str(note or "").strip(),
            "markers": safe_markers,
        }
        return SST_LUCES_PLAN_PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    def _sst_carteleria_unpack_observaciones(raw_value):
        raw_text = str(raw_value or "").strip()
        if not raw_text:
            return "", []
        if not raw_text.startswith(SST_CARTELERIA_PLAN_PREFIX):
            return raw_text, []
        try:
            payload = json.loads(raw_text[len(SST_CARTELERIA_PLAN_PREFIX):].strip() or "{}")
        except Exception:
            return raw_text, []
        note = str((payload or {}).get("note") or "").strip()
        markers = []
        for item in ((payload or {}).get("markers") or []):
            if not isinstance(item, dict):
                continue
            tipo_code = _sst_carteleria_canonical_tipo_code(item.get("type"))
            if not tipo_code:
                continue
            try:
                x_val = float(item.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(item.get("y", 0.5))
            except Exception:
                y_val = 0.5
            x_val = max(0.03, min(0.97, x_val))
            y_val = max(0.03, min(0.97, y_val))
            markers.append({
                "type": tipo_code,
                "label": str(item.get("label") or "").strip(),
                "local": (_sst_clean_upper(item.get("local")) or "").strip().upper(),
                "x": x_val,
                "y": y_val,
            })
        return note, markers

    def _sst_carteleria_pack_observaciones(markers=None, note=""):
        safe_markers = []
        for item in (markers or []):
            if not isinstance(item, dict):
                continue
            tipo_code = _sst_carteleria_canonical_tipo_code(item.get("type"))
            if not tipo_code:
                continue
            try:
                x_val = float(item.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(item.get("y", 0.5))
            except Exception:
                y_val = 0.5
            safe_markers.append({
                "type": tipo_code,
                "label": str(item.get("label") or "").strip(),
                "local": (_sst_clean_upper(item.get("local")) or "").strip().upper(),
                "x": max(0.03, min(0.97, x_val)),
                "y": max(0.03, min(0.97, y_val)),
            })
        payload = {
            "note": str(note or "").strip(),
            "markers": safe_markers,
        }
        return SST_CARTELERIA_PLAN_PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    def _sst_fetch_carteleria_records(con):
        ensure_sst_carteleria_tables(con)
        depositos_map, _ = _sst_fetch_depositos_map(con)
        rows = con.execute("""
            SELECT
                r.*,
                t.grupo AS grupo,
                t.codigo AS tipo_codigo,
                t.nombre AS tipo_nombre,
                COALESCE(s.nombre, '') AS sede_nombre,
                COALESCE(s.ciudad, '') AS sede_ciudad,
                COALESCE(s.direccion, '') AS sede_direccion
            FROM sst_carteleria_registros r
            JOIN sst_carteleria_tipos t ON t.id = r.tipo_id
            LEFT JOIN sedes_mpd s ON s.codigo = r.sede_codigo
            WHERE COALESCE(r.activo, 1) = 1
            ORDER BY UPPER(COALESCE(r.sede_codigo, '')), COALESCE(r.piso, 'PB'), UPPER(COALESCE(r.deposito_codigo, '')), t.orden, r.id
        """).fetchall()
        out = []
        for row in rows:
            item = {key: row[key] for key in row.keys()}
            item["id"] = int(_row_value(row, "id", 0) or 0)
            item["sede_codigo"] = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            item["piso"] = (_row_value(row, "piso", SST_CARTELERIA_PLACEHOLDER_PISO) or SST_CARTELERIA_PLACEHOLDER_PISO).strip().upper()
            item["deposito_codigo"] = (_row_value(row, "deposito_codigo", SST_CARTELERIA_PLACEHOLDER_DEPOSITO) or SST_CARTELERIA_PLACEHOLDER_DEPOSITO).strip().upper()
            inferred_aplica = "SI" if _sst_int_nonneg(_row_value(row, "cantidad_requerida", 0)) or _sst_int_nonneg(_row_value(row, "cantidad_instalada", 0)) else "NO"
            item["aplica"] = _sst_carteleria_normalize_aplica(_row_value(row, "aplica", ""), inferred_aplica)
            item["cantidad_requerida"] = _sst_int_nonneg(_row_value(row, "cantidad_requerida", 0))
            item["cantidad_instalada"] = _sst_int_nonneg(_row_value(row, "cantidad_instalada", 0))
            if item["aplica"] != "SI":
                item["cantidad_requerida"] = 0
                item["cantidad_instalada"] = 0
            item["cantidad_faltante"] = max(item["cantidad_requerida"] - item["cantidad_instalada"], 0) if item["aplica"] == "SI" else 0
            item["tipo_codigo"] = (_row_value(row, "tipo_codigo", "") or "").strip().upper()
            item["canonical_tipo_codigo"] = _sst_carteleria_canonical_tipo_code(item["tipo_codigo"])
            if item["canonical_tipo_codigo"]:
                item["grupo_label"] = SST_CARTELERIA_GROUP_LABELS.get(
                    SST_CARTELERIA_TIPO_GROUPS.get(item["canonical_tipo_codigo"], ""),
                    (_row_value(row, "grupo", "") or "").strip().title(),
                )
                item["tipo_nombre"] = SST_CARTELERIA_TIPO_LABELS.get(item["canonical_tipo_codigo"], (_row_value(row, "tipo_nombre", "") or "").strip())
            else:
                item["grupo_label"] = SST_CARTELERIA_GROUP_LABELS.get((_row_value(row, "grupo", "") or "").strip().upper(), (_row_value(row, "grupo", "") or "").strip().title())
                item["tipo_nombre"] = (_row_value(row, "tipo_nombre", "") or "").strip()
            item["deposito_label"] = _sst_deposito_label(item["sede_codigo"], item["deposito_codigo"], depositos_map)
            item["fecha_solicitud"] = (_row_value(row, "fecha_pedido", "") or "").strip()
            item["fecha_entrega"] = (_row_value(row, "fecha_disponibilidad", "") or "").strip()
            item["fecha_instalacion"] = (
                (_row_value(row, "fecha_colocacion", "") or "").strip()
                or (_row_value(row, "fecha_programada_colocacion", "") or "").strip()
            )
            item["estado"] = _sst_carteleria_normalize_manual_state(_row_value(row, "estado", "")) or (_row_value(row, "estado", "") or "").strip().upper()
            obs_note, plan_markers = _sst_carteleria_unpack_observaciones(_row_value(row, "observaciones", ""))
            item["observaciones_raw"] = (_row_value(row, "observaciones", "") or "").strip()
            item["observaciones"] = obs_note
            item["plan_markers"] = plan_markers
            item["aplica_label"] = SST_CARTELERIA_APLICA_LABELS.get(item["aplica"], "No relevado")
            item["state_code"] = _sst_carteleria_state_code(item)
            item["state_meta"] = _sst_state_badge(item["state_code"], SST_CARTELERIA_STATE_LABELS)
            item["action_label"] = _sst_carteleria_action_text(item)
            item["ultima_actualizacion"] = max([
                str(item.get("fecha_actualizacion") or "").strip(),
                str(item.get("fecha_colocacion") or "").strip(),
                str(item.get("fecha_programada_colocacion") or "").strip(),
                str(item.get("fecha_entrega") or "").strip(),
                str(item.get("fecha_solicitud") or "").strip(),
                str(item.get("fecha_relevamiento") or "").strip(),
                str(item.get("fecha_creacion") or "").strip(),
            ])
            out.append(item)
        return out

    def _sst_carteleria_primary_record(records):
        if not records:
            return None
        return sorted(list(records), key=_sst_carteleria_record_sort_key, reverse=True)[0]

    def _sst_carteleria_checklist_groups(items):
        groups = []
        for group_code in SST_CARTELERIA_GROUP_ORDER:
            members = [item for item in items if item["group_code"] == group_code]
            if members:
                groups.append({
                    "code": group_code,
                    "label": SST_CARTELERIA_GROUP_LABELS.get(group_code, group_code.title()),
                    "items": members,
                })
        return groups

    def _sst_carteleria_aggregate_by_sede(records):
        grouped = defaultdict(list)
        for item in records:
            sede_codigo = (_sst_clean_upper(item.get("sede_codigo")) or "").strip().upper()
            if not sede_codigo:
                continue
            grouped[sede_codigo].append(item)
        out = {}
        for sede_codigo, sede_records in grouped.items():
            by_tipo = defaultdict(list)
            for item in sede_records:
                canonical_code = item.get("canonical_tipo_codigo") or ""
                if not canonical_code:
                    continue
                by_tipo[canonical_code].append(item)
            checklist_items = []
            authoritative_records = []
            requeridos = 0
            instalados = 0
            faltantes = 0
            tipos_relevados = 0
            tipos_sin_relevar = 0
            for canonical_code in SST_CARTELERIA_VISIBLE_CODES:
                tipo_records = sorted(by_tipo.get(canonical_code, []), key=_sst_carteleria_record_sort_key, reverse=True)
                placeholder_records = [
                    item for item in tipo_records
                    if item.get("piso") == SST_CARTELERIA_PLACEHOLDER_PISO and item.get("deposito_codigo") == SST_CARTELERIA_PLACEHOLDER_DEPOSITO
                ]
                plan_records = [
                    item for item in tipo_records
                    if not (
                        item.get("piso") == SST_CARTELERIA_PLACEHOLDER_PISO
                        and item.get("deposito_codigo") == SST_CARTELERIA_PLACEHOLDER_DEPOSITO
                    )
                ]
                effective_records = plan_records or placeholder_records or tipo_records
                detail = _sst_carteleria_type_detail(effective_records)
                primary_record = detail["primary_record"]
                if primary_record:
                    authoritative_records.append(primary_record)
                if detail["aplica"] == "NO_RELEVADO":
                    tipos_sin_relevar += 1
                else:
                    tipos_relevados += 1
                requeridos += detail["cantidad_requerida"]
                instalados += detail["cantidad_instalada"]
                faltantes += detail["cantidad_faltante"]
                checklist_items.append({
                    "code": canonical_code,
                    "label": SST_CARTELERIA_TIPO_LABELS[canonical_code],
                    "group_code": SST_CARTELERIA_TIPO_GROUPS[canonical_code],
                    "group_label": SST_CARTELERIA_GROUP_LABELS.get(SST_CARTELERIA_TIPO_GROUPS[canonical_code], ""),
                    "order": SST_CARTELERIA_TIPO_ORDER[canonical_code],
                    "aplica": detail["aplica"],
                    "aplica_label": detail["aplica_label"],
                    "cantidad_requerida": detail["cantidad_requerida"],
                    "cantidad_instalada": detail["cantidad_instalada"],
                    "cantidad_faltante": detail["cantidad_faltante"],
                    "record_id": int(primary_record.get("id") or 0) if primary_record else 0,
                    "has_data": bool(primary_record),
                })
            primary_record = _sst_carteleria_primary_record(authoritative_records)
            summary = dict(primary_record or {})
            summary.update({
                "id": int(primary_record.get("id") or 0) if primary_record else 0,
                "primary_record_id": int(primary_record.get("id") or 0) if primary_record else 0,
                "record_count": len(authoritative_records),
                "record_ids": [int(item.get("id") or 0) for item in authoritative_records if int(item.get("id") or 0) > 0],
                "sede_codigo": sede_codigo,
                "tipos_relevados": tipos_relevados,
                "tipos_sin_relevar": tipos_sin_relevar,
                "cantidad_requerida": requeridos,
                "cantidad_instalada": instalados,
                "cantidad_faltante": faltantes,
                "faltantes": faltantes,
                "fecha_solicitud": max((str(item.get("fecha_solicitud") or "").strip() for item in authoritative_records if str(item.get("fecha_solicitud") or "").strip()), default=""),
                "fecha_entrega": max((str(item.get("fecha_entrega") or "").strip() for item in authoritative_records if str(item.get("fecha_entrega") or "").strip()), default=""),
                "fecha_instalacion": max((str(item.get("fecha_instalacion") or "").strip() for item in authoritative_records if str(item.get("fecha_instalacion") or "").strip()), default=""),
                "observaciones": next((str(item.get("observaciones") or "").strip() for item in authoritative_records if str(item.get("observaciones") or "").strip()), ""),
                "seguimiento_id": next((int(item.get("seguimiento_id") or 0) for item in authoritative_records if int(item.get("seguimiento_id") or 0) > 0), 0),
                "estado": next((_sst_carteleria_normalize_manual_state(item.get("estado")) for item in authoritative_records if _sst_carteleria_normalize_manual_state(item.get("estado"))), ""),
                "ultima_actualizacion": max((str(item.get("ultima_actualizacion") or "").strip() for item in authoritative_records if str(item.get("ultima_actualizacion") or "").strip()), default=""),
                "checklist_items": checklist_items,
                "checklist_groups": _sst_carteleria_checklist_groups(checklist_items),
            })
            if summary["cantidad_requerida"]:
                summary["porcentaje_cumplimiento"] = int(round((summary["cantidad_instalada"] / summary["cantidad_requerida"]) * 100))
            else:
                summary["porcentaje_cumplimiento"] = 100 if summary["tipos_sin_relevar"] == 0 else 0
            summary["state_code"] = _sst_carteleria_state_code(summary)
            summary["state_meta"] = _sst_state_badge(summary["state_code"], SST_CARTELERIA_STATE_LABELS)
            summary["action_label"] = _sst_carteleria_action_text(summary)
            summary["action_button_label"] = "Abrir"
            out[sede_codigo] = summary
        return out

    def _sst_carteleria_empty_summary(sede):
        sede_codigo = (_row_value(sede, "codigo", "") or "").strip().upper()
        checklist_items = [{
            "code": code,
            "label": SST_CARTELERIA_TIPO_LABELS[code],
            "group_code": SST_CARTELERIA_TIPO_GROUPS[code],
            "group_label": SST_CARTELERIA_GROUP_LABELS.get(SST_CARTELERIA_TIPO_GROUPS[code], ""),
            "order": SST_CARTELERIA_TIPO_ORDER[code],
            "aplica": "NO_RELEVADO",
            "aplica_label": SST_CARTELERIA_APLICA_LABELS["NO_RELEVADO"],
            "cantidad_requerida": 0,
            "cantidad_instalada": 0,
            "cantidad_faltante": 0,
            "record_id": 0,
            "has_data": False,
        } for code in SST_CARTELERIA_VISIBLE_CODES]
        summary = {
            "id": 0,
            "primary_record_id": 0,
            "record_count": 0,
            "record_ids": [],
            "sede_codigo": sede_codigo,
            "sede_nombre": (_row_value(sede, "nombre", "") or "").strip(),
            "tipos_relevados": 0,
            "tipos_sin_relevar": len(SST_CARTELERIA_VISIBLE_CODES),
            "cantidad_requerida": 0,
            "cantidad_instalada": 0,
            "cantidad_faltante": 0,
            "faltantes": 0,
            "porcentaje_cumplimiento": 0,
            "fecha_solicitud": "",
            "fecha_entrega": "",
            "fecha_instalacion": "",
            "observaciones": "",
            "seguimiento_id": 0,
            "estado": "",
            "ultima_actualizacion": "",
            "checklist_items": checklist_items,
            "checklist_groups": _sst_carteleria_checklist_groups(checklist_items),
        }
        summary["state_code"] = _sst_carteleria_state_code(summary)
        summary["state_meta"] = _sst_state_badge(summary["state_code"], SST_CARTELERIA_STATE_LABELS)
        summary["action_label"] = _sst_carteleria_action_text(summary)
        summary["action_button_label"] = "Abrir"
        return summary

    def _sst_fetch_luces_records(con):
        ensure_sst_luces_tables(con)
        latest_tests = {}
        test_counts = defaultdict(int)
        if _table_exists(con, "sst_luces_pruebas"):
            for row in con.execute("""
                SELECT p.*
                FROM sst_luces_pruebas p
                ORDER BY COALESCE(p.fecha_prueba, '') DESC, p.id DESC
            """).fetchall():
                registro_id = int(_row_value(row, "registro_id", 0) or 0)
                if registro_id <= 0:
                    continue
                test_counts[registro_id] += 1
                if registro_id not in latest_tests:
                    latest_tests[registro_id] = row
        rows = con.execute("""
            SELECT
                r.*,
                COALESCE(s.nombre, '') AS sede_nombre,
                COALESCE(s.ciudad, '') AS sede_ciudad,
                COALESCE(s.direccion, '') AS sede_direccion
            FROM sst_luces_registros r
            LEFT JOIN sedes_mpd s ON s.codigo = r.sede_codigo
            WHERE COALESCE(r.activo, 1) = 1
            ORDER BY UPPER(COALESCE(r.sede_codigo, '')), COALESCE(r.piso, 'PB'), UPPER(COALESCE(r.deposito_codigo, '')), r.id
        """).fetchall()
        out = []
        for row in rows:
            item = {key: row[key] for key in row.keys()}
            item["id"] = int(_row_value(row, "id", 0) or 0)
            item["sede_codigo"] = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            item["piso"] = (_row_value(row, "piso", "PB") or "PB").strip().upper()
            item["deposito_codigo"] = (_row_value(row, "deposito_codigo", "") or "").strip().upper()
            item["aplica"] = 0 if str(_row_value(row, "aplica", 1) or "").strip().lower() in {"0", "false", "no"} else 1
            item["motivo_no_aplica"] = (_row_value(row, "motivo_no_aplica", "") or "").strip()
            for field in ("cantidad_requerida", "cantidad_instalada", "cantidad_operativa", "cantidad_fuera_servicio"):
                item[field] = _sst_int_nonneg(_row_value(row, field, 0))
            item["cantidad_operativa"] = min(item["cantidad_operativa"], item["cantidad_instalada"])
            item["fecha_solicitud_compra"] = (
                (_row_value(row, "fecha_solicitud_compra", "") or "").strip()
                or (_row_value(row, "fecha_pedido", "") or "").strip()
            )
            item["referencia_pedido"] = (
                (_row_value(row, "referencia_pedido", "") or "").strip()
                or (_row_value(row, "numero_pedido", "") or "").strip()
            )
            item["fecha_entrega"] = (
                (_row_value(row, "fecha_entrega", "") or "").strip()
                or (_row_value(row, "fecha_disponibilidad", "") or "").strip()
            )
            item["fecha_programada_colocacion"] = (
                (_row_value(row, "fecha_programada_colocacion", "") or "").strip()
                or (_row_value(row, "fecha_intervencion_programada", "") or "").strip()
                or (_row_value(row, "fecha_programada_intervencion", "") or "").strip()
            )
            item["fecha_colocacion"] = (
                (_row_value(row, "fecha_colocacion", "") or "").strip()
                or (_row_value(row, "fecha_intervencion_realizada", "") or "").strip()
                or (_row_value(row, "fecha_intervencion", "") or "").strip()
            )
            item["fecha_mantenimiento"] = (_row_value(row, "fecha_mantenimiento", "") or "").strip()
            item["fecha_intervencion_programada"] = (
                (_row_value(row, "fecha_intervencion_programada", "") or "").strip()
                or (_row_value(row, "fecha_programada_intervencion", "") or "").strip()
            )
            item["fecha_intervencion_realizada"] = (
                (_row_value(row, "fecha_intervencion_realizada", "") or "").strip()
                or (_row_value(row, "fecha_intervencion", "") or "").strip()
            )
            latest_test = latest_tests.get(item["id"])
            if latest_test:
                item["fecha_ultima_prueba"] = (_row_value(latest_test, "fecha_prueba", item.get("fecha_ultima_prueba")) or "").strip()
                item["resultado_ultima_prueba"] = (_row_value(latest_test, "resultado", item.get("resultado_ultima_prueba")) or "").strip()
                if not (item.get("fecha_proxima_prueba") or "").strip():
                    item["fecha_proxima_prueba"] = (_row_value(latest_test, "fecha_proxima_prueba", "") or "").strip()
            item["pruebas_total"] = int(test_counts.get(item["id"], 0) or 0)
            if not item["aplica"]:
                item["cantidad_requerida"] = 0
                item["cantidad_instalada"] = 0
                item["cantidad_operativa"] = 0
                item["fecha_solicitud_compra"] = ""
                item["referencia_pedido"] = ""
                item["fecha_entrega"] = ""
                item["fecha_programada_colocacion"] = ""
                item["fecha_colocacion"] = ""
                item["fecha_mantenimiento"] = ""
            item["cantidad_fuera_servicio"] = max(item["cantidad_instalada"] - item["cantidad_operativa"], 0)
            item["cantidad_faltante"] = max(item["cantidad_requerida"] - item["cantidad_instalada"], 0)
            item["faltantes"] = item["cantidad_faltante"]
            item["fecha_instalacion"] = item["fecha_colocacion"] or item["fecha_programada_colocacion"]
            item["estado"] = _sst_luces_normalize_manual_state(_row_value(row, "estado", "")) or (_row_value(row, "estado", "") or "").strip().upper()
            obs_note, plan_markers = _sst_luces_unpack_observaciones(_row_value(row, "observaciones", ""))
            item["observaciones_raw"] = (_row_value(row, "observaciones", "") or "").strip()
            item["observaciones"] = obs_note
            item["plan_markers"] = plan_markers
            item["state_code"] = _sst_luces_state_code(item)
            item["state_meta"] = _sst_state_badge(item["state_code"], SST_LUCES_STATE_LABELS)
            item["action_label"] = _sst_luces_action_text(item)
            item["action_button_label"] = "Abrir"
            item["ultima_actualizacion"] = max([
                str(item.get("fecha_actualizacion") or "").strip(),
                str(item.get("fecha_mantenimiento") or "").strip(),
                str(item.get("fecha_colocacion") or "").strip(),
                str(item.get("fecha_programada_colocacion") or "").strip(),
                str(item.get("fecha_entrega") or "").strip(),
                str(item.get("fecha_solicitud_compra") or "").strip(),
                str(item.get("fecha_creacion") or "").strip(),
            ])
            out.append(item)
        return out

    def _sst_luces_primary_record(records):
        if not records:
            return None
        return sorted(
            list(records),
            key=lambda item: (
                str(item.get("ultima_actualizacion") or ""),
                str(item.get("fecha_actualizacion") or ""),
                str(item.get("fecha_creacion") or ""),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )[0]

    def _sst_luces_aggregate_by_sede(records):
        grouped = defaultdict(list)
        for item in records:
            sede_codigo = (_sst_clean_upper(item.get("sede_codigo")) or "").strip().upper()
            if not sede_codigo:
                continue
            grouped[sede_codigo].append(item)
        out = {}
        for sede_codigo, sede_records in grouped.items():
            ordered_records = sorted(
                sede_records,
                key=lambda item: (
                    str(item.get("ultima_actualizacion") or ""),
                    str(item.get("fecha_actualizacion") or ""),
                    str(item.get("fecha_creacion") or ""),
                    int(item.get("id") or 0),
                ),
                reverse=True,
            )
            placeholder_records = [
                item for item in ordered_records
                if item.get("piso") == SST_LUCES_PLACEHOLDER_PISO and item.get("deposito_codigo") == SST_LUCES_PLACEHOLDER_DEPOSITO
            ]
            plan_records = [
                item for item in ordered_records
                if not (
                    item.get("piso") == SST_LUCES_PLACEHOLDER_PISO
                    and item.get("deposito_codigo") == SST_LUCES_PLACEHOLDER_DEPOSITO
                )
            ]
            effective_records = plan_records or placeholder_records or ordered_records
            primary = effective_records[0]
            manual_state = next(
                (_sst_luces_normalize_manual_state(item.get("estado")) for item in effective_records if _sst_luces_normalize_manual_state(item.get("estado")) in SST_MANUAL_LUCES_STATES),
                "",
            )
            applies = 1 if any(_sst_bool_flag(item.get("aplica", 1)) for item in effective_records) else 0
            summary = dict(primary)
            summary.update({
                "id": int(primary.get("id") or 0),
                "primary_record_id": int(primary.get("id") or 0),
                "record_count": len(effective_records),
                "record_ids": [int(item.get("id") or 0) for item in effective_records],
                "aplica": applies,
                "motivo_no_aplica": next((str(item.get("motivo_no_aplica") or "").strip() for item in effective_records if str(item.get("motivo_no_aplica") or "").strip()), ""),
                "cantidad_requerida": (sum(_sst_int_nonneg(item.get("cantidad_requerida")) for item in effective_records) if applies else 0),
                "cantidad_instalada": (sum(_sst_int_nonneg(item.get("cantidad_instalada")) for item in effective_records) if applies else 0),
                "cantidad_operativa": (sum(_sst_int_nonneg(item.get("cantidad_operativa")) for item in effective_records) if applies else 0),
                "fecha_solicitud_compra": max((str(item.get("fecha_solicitud_compra") or "").strip() for item in effective_records if str(item.get("fecha_solicitud_compra") or "").strip()), default=""),
                "referencia_pedido": next((str(item.get("referencia_pedido") or "").strip() for item in effective_records if str(item.get("referencia_pedido") or "").strip()), ""),
                "fecha_entrega": max((str(item.get("fecha_entrega") or "").strip() for item in effective_records if str(item.get("fecha_entrega") or "").strip()), default=""),
                "fecha_programada_colocacion": max((str(item.get("fecha_programada_colocacion") or "").strip() for item in effective_records if str(item.get("fecha_programada_colocacion") or "").strip()), default=""),
                "fecha_colocacion": max((str(item.get("fecha_colocacion") or "").strip() for item in effective_records if str(item.get("fecha_colocacion") or "").strip()), default=""),
                "fecha_mantenimiento": max((str(item.get("fecha_mantenimiento") or "").strip() for item in effective_records if str(item.get("fecha_mantenimiento") or "").strip()), default=""),
                "seguimiento_id": next((int(item.get("seguimiento_id") or 0) for item in effective_records if int(item.get("seguimiento_id") or 0) > 0), 0),
                "observaciones": next((str(item.get("observaciones") or "").strip() for item in effective_records if str(item.get("observaciones") or "").strip()), ""),
                "estado": manual_state,
                "pruebas_total": sum(int(item.get("pruebas_total") or 0) for item in effective_records),
                "ultima_actualizacion": max((str(item.get("ultima_actualizacion") or "").strip() for item in effective_records if str(item.get("ultima_actualizacion") or "").strip()), default=""),
            })
            if not applies:
                summary["cantidad_requerida"] = 0
                summary["cantidad_instalada"] = 0
                summary["cantidad_operativa"] = 0
            summary["cantidad_fuera_servicio"] = max(summary["cantidad_instalada"] - summary["cantidad_operativa"], 0)
            summary["cantidad_faltante"] = max(summary["cantidad_requerida"] - summary["cantidad_instalada"], 0)
            summary["faltantes"] = summary["cantidad_faltante"]
            summary["fecha_instalacion"] = summary["fecha_colocacion"] or summary["fecha_programada_colocacion"]
            summary["state_code"] = _sst_luces_state_code(summary)
            summary["state_meta"] = _sst_state_badge(summary["state_code"], SST_LUCES_STATE_LABELS)
            summary["action_label"] = _sst_luces_action_text(summary)
            summary["action_button_label"] = "Abrir"
            out[sede_codigo] = summary
        return out

    def _sst_luces_empty_summary(sede, seed_item=None):
        sede_codigo = (_row_value(sede, "codigo", "") or "").strip().upper()
        aplica = 1 if not seed_item else int(seed_item.get("aplica", 1) or 0)
        cantidad_requerida = _sst_int_nonneg(seed_item.get("cantidad_requerida") if seed_item else 0) if aplica else 0
        summary = {
            "id": 0,
            "primary_record_id": 0,
            "record_count": 0,
            "record_ids": [],
            "sede_codigo": sede_codigo,
            "sede_nombre": (_row_value(sede, "nombre", "") or "").strip(),
            "aplica": aplica,
            "motivo_no_aplica": ((seed_item.get("motivo_no_aplica") or "").strip() if seed_item and not aplica else ""),
            "cantidad_requerida": cantidad_requerida,
            "cantidad_instalada": 0,
            "cantidad_operativa": 0,
            "cantidad_fuera_servicio": 0,
            "cantidad_faltante": cantidad_requerida,
            "faltantes": cantidad_requerida,
            "fecha_solicitud_compra": "",
            "referencia_pedido": "",
            "fecha_entrega": "",
            "fecha_programada_colocacion": "",
            "fecha_colocacion": "",
            "fecha_mantenimiento": "",
            "fecha_instalacion": "",
            "observaciones": "",
            "seguimiento_id": 0,
            "estado": "",
            "pruebas_total": 0,
            "ultima_actualizacion": "",
        }
        summary["state_code"] = _sst_luces_state_code(summary)
        summary["state_meta"] = _sst_state_badge(summary["state_code"], SST_LUCES_STATE_LABELS)
        summary["action_label"] = _sst_luces_action_text(summary)
        summary["action_button_label"] = "Abrir"
        return summary

    def _sst_fetch_historial_rows(con, componente, sede_codigo=""):
        ensure_sst_operativo_historial_tables(con)
        where = ["LOWER(COALESCE(componente, '')) = ?"]
        params = [(componente or "").strip().lower()]
        if sede_codigo:
            where.append("UPPER(COALESCE(sede_codigo, '')) = ?")
            params.append((_sst_clean_upper(sede_codigo) or "").strip().upper())
        rows = con.execute(f"""
            SELECT *
            FROM sst_operativo_historial
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(fecha_evento, '') DESC, id DESC
            LIMIT 24
        """, params).fetchall()
        return [{
            "id": int(_row_value(row, "id", 0) or 0),
            "sede_codigo": (_row_value(row, "sede_codigo", "") or "").strip().upper(),
            "deposito_codigo": (_row_value(row, "deposito_codigo", "") or "").strip().upper(),
            "accion": (_row_value(row, "accion", "") or "").strip(),
            "detalle": (_row_value(row, "detalle", "") or "").strip(),
            "usuario": (_row_value(row, "usuario", "") or "").strip(),
            "fecha_evento": (_row_value(row, "fecha_evento", "") or "").strip(),
        } for row in rows]

    def _sst_carteleria_context(con):
        ensure_sst_general_table(con)
        ensure_sst_carteleria_tables(con)
        sedes = list(_sst_fetch_sedes_base(con))
        all_records = _sst_fetch_carteleria_records(con)
        summary_map = _sst_carteleria_aggregate_by_sede(all_records)
        f_sede = (_sst_clean_upper(request.args.get("sede")) or "").strip().upper()
        f_estado = (_sst_clean_upper(request.args.get("estado")) or "").strip().upper()
        f_q = (request.args.get("q") or "").strip().lower()
        f_month = _sst_int_nonneg(request.args.get("month"))
        f_open_sede = (_sst_clean_upper(request.args.get("open_sede")) or "").strip().upper()
        f_registro = _sst_int_nonneg(request.args.get("registro") or request.args.get("edit"))
        selected_filter_sede = next((item for item in sedes if item["codigo"] == f_sede), None)
        visible_sedes = [selected_filter_sede] if selected_filter_sede else list(sedes)
        base_rows = []
        for sede in visible_sedes:
            if not sede:
                continue
            sede_codigo = (_row_value(sede, "codigo", "") or "").strip().upper()
            sede_fuero_class, sede_fuero_color = _sst_sede_fuero_style(sede_codigo, _row_value(sede, "fuero", ""))
            row = dict(summary_map.get(sede_codigo) or _sst_carteleria_empty_summary(sede))
            row["sede_codigo"] = sede_codigo
            row["sede_nombre"] = (_row_value(sede, "nombre", "") or "").strip()
            row["sede_fuero_class"] = sede_fuero_class
            row["sede_fuero_color"] = sede_fuero_color
            row["url"] = url_for(
                "sst_carteleria_home",
                sede=f_sede or None,
                estado=f_estado or None,
                q=f_q or None,
                month=(f_month or None),
                open_sede=sede_codigo,
                registro=(int(row.get("primary_record_id") or 0) or None),
            )
            base_rows.append(row)
        filtered_rows = []
        for row in base_rows:
            if f_estado and row["state_code"] != f_estado:
                continue
            if f_month:
                month_dates = _sst_dates_for_month(
                    row,
                    ["fecha_solicitud", "fecha_entrega", "fecha_instalacion", "ultima_actualizacion"],
                )
                if not any(d.month == f_month for d in month_dates):
                    continue
            if f_q:
                haystack = " ".join([
                    row["sede_codigo"],
                    str(row.get("sede_nombre") or ""),
                    str(row.get("state_meta", {}).get("label", "") or ""),
                    str(row.get("action_label") or ""),
                    str(row.get("observaciones") or ""),
                ]).lower()
                if f_q not in haystack:
                    continue
            filtered_rows.append(row)
        state_by_sede = sorted(filtered_rows, key=lambda item: item["sede_codigo"])
        selected_record = next((item for item in all_records if int(item["id"]) == f_registro), None)
        detail_sede = f_open_sede or (selected_record.get("sede_codigo") if selected_record else "")
        selected_summary = next((item for item in base_rows if item["sede_codigo"] == detail_sede), None)
        history_rows = [
            item
            for item in _sst_fetch_historial_rows(con, "carteleria", detail_sede or f_sede)
            if item.get("accion") in {"alta", "actualizacion", "cambio_estado", "seguimiento"}
        ]
        prefill_sede = (_sst_clean_upper(request.args.get("prefill_sede") or detail_sede or f_sede) or "").strip().upper()
        show_form = bool(request.method == "POST" or request.args.get("mostrar_form"))
        default_item_rows = {
            code: {
                "aplica": "NO_RELEVADO",
                "cantidad_requerida": 0,
                "cantidad_instalada": 0,
                "cantidad_faltante": 0,
            }
            for code in SST_CARTELERIA_VISIBLE_CODES
        }
        if selected_summary:
            for checklist_item in selected_summary.get("checklist_items", []):
                default_item_rows[checklist_item["code"]] = {
                    "aplica": checklist_item.get("aplica", "NO_RELEVADO"),
                    "cantidad_requerida": _sst_int_nonneg(checklist_item.get("cantidad_requerida")),
                    "cantidad_instalada": _sst_int_nonneg(checklist_item.get("cantidad_instalada")),
                    "cantidad_faltante": _sst_int_nonneg(checklist_item.get("cantidad_faltante")),
                }
        form_defaults = {
            "edit_id": int(selected_summary["primary_record_id"]) if selected_summary else 0,
            "sede_codigo": (selected_summary["sede_codigo"] if selected_summary else prefill_sede),
            "fecha_solicitud": ((selected_summary.get("fecha_solicitud") or "") if selected_summary else ""),
            "fecha_entrega": ((selected_summary.get("fecha_entrega") or "") if selected_summary else ""),
            "fecha_instalacion": ((selected_summary.get("fecha_instalacion") or "") if selected_summary else ""),
            "observaciones": ((selected_summary.get("observaciones") or "") if selected_summary else ""),
            "item_rows": default_item_rows,
        }
        if request.method == "POST" and (request.form.get("action") or "save").strip().lower() == "save":
            posted_item_rows = {}
            for code in SST_CARTELERIA_VISIBLE_CODES:
                aplica = _sst_carteleria_normalize_aplica(request.form.get(f"item_aplica_{code}"), "NO_RELEVADO")
                cantidad_requerida = _sst_int_nonneg(request.form.get(f"item_requerida_{code}"))
                cantidad_instalada = _sst_int_nonneg(request.form.get(f"item_instalada_{code}"))
                if aplica != "SI":
                    cantidad_requerida = 0
                    cantidad_instalada = 0
                posted_item_rows[code] = {
                    "aplica": aplica,
                    "cantidad_requerida": cantidad_requerida,
                    "cantidad_instalada": cantidad_instalada,
                    "cantidad_faltante": max(cantidad_requerida - cantidad_instalada, 0) if aplica == "SI" else 0,
                }
            form_defaults.update({
                "edit_id": _sst_int_nonneg(request.form.get("edit_id")),
                "sede_codigo": (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper(),
                "fecha_solicitud": (request.form.get("fecha_solicitud") or "").strip(),
                "fecha_entrega": (request.form.get("fecha_entrega") or "").strip(),
                "fecha_instalacion": (request.form.get("fecha_instalacion") or "").strip(),
                "observaciones": (request.form.get("observaciones") or "").strip(),
                "item_rows": posted_item_rows,
            })
        form_requeridos = sum(
            int(item["cantidad_requerida"] or 0)
            for item in form_defaults["item_rows"].values()
            if item.get("aplica") == "SI"
        )
        form_instalados = sum(
            int(item["cantidad_instalada"] or 0)
            for item in form_defaults["item_rows"].values()
            if item.get("aplica") == "SI"
        )
        form_faltantes = sum(
            int(item["cantidad_faltante"] or 0)
            for item in form_defaults["item_rows"].values()
            if item.get("aplica") == "SI"
        )
        form_tipos_relevados = sum(1 for item in form_defaults["item_rows"].values() if item.get("aplica") != "NO_RELEVADO")
        form_tipos_sin_relevar = sum(1 for item in form_defaults["item_rows"].values() if item.get("aplica") == "NO_RELEVADO")
        form_porcentaje = int(round((form_instalados / form_requeridos) * 100)) if form_requeridos else (100 if form_tipos_sin_relevar == 0 else 0)
        checklist_catalog = [{
            "code": code,
            "label": SST_CARTELERIA_TIPO_LABELS[code],
            "group_code": SST_CARTELERIA_TIPO_GROUPS[code],
            "group_label": SST_CARTELERIA_GROUP_LABELS.get(SST_CARTELERIA_TIPO_GROUPS[code], ""),
            "order": SST_CARTELERIA_TIPO_ORDER[code],
        } for code in SST_CARTELERIA_VISIBLE_CODES]
        checklist_groups = _sst_carteleria_checklist_groups([
            dict(
                item,
                aplica=form_defaults["item_rows"].get(item["code"], {}).get("aplica", "NO_RELEVADO"),
                aplica_label=SST_CARTELERIA_APLICA_LABELS.get(form_defaults["item_rows"].get(item["code"], {}).get("aplica", "NO_RELEVADO"), "No relevado"),
                cantidad_requerida=_sst_int_nonneg(form_defaults["item_rows"].get(item["code"], {}).get("cantidad_requerida")),
                cantidad_instalada=_sst_int_nonneg(form_defaults["item_rows"].get(item["code"], {}).get("cantidad_instalada")),
                cantidad_faltante=_sst_int_nonneg(form_defaults["item_rows"].get(item["code"], {}).get("cantidad_faltante")),
                record_id=0,
                has_data=False,
            )
            for item in checklist_catalog
        ])
        close_modal_url = url_for(
            "sst_carteleria_home",
            sede=f_sede or None,
            estado=f_estado or None,
            q=f_q or None,
            month=(f_month or None),
        )
        if selected_summary:
            def _carteleria_form_url(prefill_estado_value=""):
                return url_for(
                    "sst_carteleria_home",
                    sede=f_sede or None,
                    estado=f_estado or None,
                    q=f_q or None,
                    month=(f_month or None),
                    open_sede=selected_summary["sede_codigo"],
                    registro=(int(selected_summary.get("primary_record_id") or 0) or None),
                    prefill_sede=selected_summary["sede_codigo"],
                    prefill_estado=(prefill_estado_value or None),
                    mostrar_form=1,
                )
            selected_summary["modal_close_url"] = close_modal_url
            selected_summary["modal_edit_url"] = _carteleria_form_url(selected_summary.get("state_code") or "")
            selected_summary["modal_delivery_url"] = _carteleria_form_url("MATERIAL_RECIBIDO")
            selected_summary["modal_followup_enabled"] = (
                _sst_carteleria_has_pending_action(selected_summary)
                and int(selected_summary.get("seguimiento_id") or 0) <= 0
                and int(selected_summary.get("primary_record_id") or 0) > 0
            )
            selected_summary["show_register_delivery"] = selected_summary["state_code"] in {"RELEVADO", "PENDIENTE_SOLICITUD", "COMPRA_EN_PROCESO"}
        return {
            "sst_section": "carteleria",
            "sedes": sedes,
            "operativa_nav": build_operativa_nav_context(
                sedes,
                detail_sede or f_open_sede or f_sede or (state_by_sede[0]["sede_codigo"] if state_by_sede else ""),
                "sst_carteleria",
                filters={
                    "estado": f_estado,
                    "month": f_month,
                    "q": f_q,
                },
            ),
            "selected_sede": next((item for item in sedes if item["codigo"] == (detail_sede or f_sede)), None),
            "records": all_records,
            "state_by_sede": state_by_sede,
            "history_rows": history_rows,
            "estado_options": [{"code": key, "label": value} for key, value in SST_CARTELERIA_STATE_LABELS.items()],
            "month_options": [{"value": number, "label": label} for number, label in SST_CALENDAR_MONTHS],
            "checklist_groups": checklist_groups,
            "item_aplica_options": [
                {"code": "SI", "label": "Si"},
                {"code": "NO", "label": "No"},
                {"code": "NO_RELEVADO", "label": "No relevado"},
            ],
            "f_sede": f_sede,
            "f_estado": f_estado,
            "f_q": f_q,
            "f_month": f_month,
            "f_open_sede": f_open_sede,
            "f_registro": f_registro,
            "show_form": show_form,
            "form_defaults": form_defaults,
            "form_requeridos": form_requeridos,
            "form_instalados": form_instalados,
            "form_faltantes": form_faltantes,
            "form_tipos_relevados": form_tipos_relevados,
            "form_tipos_sin_relevar": form_tipos_sin_relevar,
            "form_porcentaje": form_porcentaje,
            "selected_record": selected_record,
            "selected_summary": selected_summary,
            "kpi_requeridos": sum(item["cantidad_requerida"] for item in state_by_sede),
            "kpi_instalados": sum(item["cantidad_instalada"] for item in state_by_sede),
            "kpi_faltantes": sum(item["cantidad_faltante"] for item in state_by_sede),
            "kpi_sedes_pendientes": sum(1 for item in state_by_sede if item["state_code"] in SST_CARTELERIA_PENDING_STATES),
            "kpi_compras_en_proceso": sum(1 for item in state_by_sede if item["state_code"] == "COMPRA_EN_PROCESO"),
            "kpi_colocaciones_programadas": sum(1 for item in state_by_sede if item["state_code"] == "INSTALACION_PROGRAMADA"),
            "fmt_fecha": _sst_fmt_fecha,
        }

    def _sst_luces_context(con):
        ensure_sst_general_table(con)
        ensure_sst_luces_tables(con)
        sedes = list(_sst_fetch_sedes_base(con))
        all_records = _sst_fetch_luces_records(con)
        summary_map = _sst_luces_aggregate_by_sede(all_records)
        seed_map = {item["sede_codigo"]: item for item in SST_LUCES_INITIAL_LOAD}
        f_sede = (_sst_clean_upper(request.args.get("sede")) or "").strip().upper()
        f_estado = (_sst_clean_upper(request.args.get("estado")) or "").strip().upper()
        f_q = (request.args.get("q") or "").strip().lower()
        f_month = _sst_int_nonneg(request.args.get("month"))
        f_open_sede = (_sst_clean_upper(request.args.get("open_sede")) or "").strip().upper()
        f_registro = _sst_int_nonneg(request.args.get("registro") or request.args.get("edit"))
        selected_filter_sede = next((item for item in sedes if item["codigo"] == f_sede), None)
        visible_sedes = [selected_filter_sede] if selected_filter_sede else list(sedes)
        base_rows = []
        for sede in visible_sedes:
            if not sede:
                continue
            sede_codigo = (_row_value(sede, "codigo", "") or "").strip().upper()
            sede_fuero_class, sede_fuero_color = _sst_sede_fuero_style(sede_codigo, _row_value(sede, "fuero", ""))
            row = dict(summary_map.get(sede_codigo) or _sst_luces_empty_summary(sede))
            row["sede_codigo"] = sede_codigo
            row["sede_nombre"] = (_row_value(sede, "nombre", "") or "").strip()
            row["sede_fuero_class"] = sede_fuero_class
            row["sede_fuero_color"] = sede_fuero_color
            row["aplica_label"] = ("Si" if _sst_bool_flag(row.get("aplica", 1)) else "No")
            row["record_exists"] = bool(int(row.get("primary_record_id") or 0))
            row["legacy_multiple"] = int(row.get("record_count") or 0) > 1
            row["fecha_actualizacion"] = row.get("ultima_actualizacion") or ""
            row["url"] = url_for(
                "sst_luces_home",
                sede=f_sede or None,
                estado=f_estado or None,
                q=f_q or None,
                month=(f_month or None),
                open_sede=sede_codigo,
                registro=(int(row.get("primary_record_id") or 0) or None),
            )
            base_rows.append(row)
        filtered_rows = []
        for row in base_rows:
            if f_estado and row["state_code"] != f_estado:
                continue
            if f_month:
                month_dates = _sst_dates_for_month(
                    row,
                    [
                        "fecha_solicitud_compra",
                        "fecha_entrega",
                        "fecha_programada_colocacion",
                        "fecha_colocacion",
                        "fecha_actualizacion",
                    ],
                )
                if not any(d.month == f_month for d in month_dates):
                    continue
            if f_q:
                haystack = " ".join([
                    row["sede_codigo"],
                    str(row.get("sede_nombre") or ""),
                    str(row.get("state_meta", {}).get("label", "") or ""),
                    str(row.get("action_label") or ""),
                    str(row.get("motivo_no_aplica") or ""),
                    str(row.get("observaciones") or ""),
                ]).lower()
                if f_q not in haystack:
                    continue
            filtered_rows.append(row)
        state_by_sede = sorted(filtered_rows, key=lambda item: item["sede_codigo"])
        selected_record = next((item for item in all_records if int(item["id"]) == f_registro), None)
        detail_sede = f_open_sede or (selected_record.get("sede_codigo") if selected_record else "")
        selected_summary = next((item for item in base_rows if item["sede_codigo"] == detail_sede), None)
        if not selected_record and selected_summary and int(selected_summary.get("primary_record_id") or 0) > 0:
            selected_record = next((item for item in all_records if int(item["id"]) == int(selected_summary["primary_record_id"])), None)
        history_rows = [
            item
            for item in _sst_fetch_historial_rows(con, "luces", detail_sede or f_sede)
            if item.get("accion") in {"alta", "cambio_estado"}
        ]
        prefill_sede = (_sst_clean_upper(request.args.get("prefill_sede") or f_sede) or "").strip().upper()
        prefill_seed = seed_map.get(prefill_sede, {})
        prefill_fecha_instalacion = (
            request.args.get("prefill_fecha_instalacion")
            or (selected_record.get("fecha_instalacion") if selected_record else "")
            or (selected_record.get("fecha_colocacion") if selected_record else "")
            or (selected_record.get("fecha_programada_colocacion") if selected_record else "")
            or ""
        ).strip()
        prefill_estado = _sst_luces_normalize_manual_state(request.args.get("prefill_estado") or (selected_record.get("estado") if selected_record else ""))
        show_form = bool(request.method == "POST" or request.args.get("mostrar_form"))
        form_defaults = {
            "edit_id": int(selected_record["id"]) if selected_record else 0,
            "sede_codigo": (selected_record["sede_codigo"] if selected_record else prefill_sede),
            "aplica": (int(selected_record.get("aplica", 1)) if selected_record else int(prefill_seed.get("aplica", 1) or 0)),
            "motivo_no_aplica": ((selected_record.get("motivo_no_aplica") or "") if selected_record else prefill_seed.get("motivo_no_aplica", "")),
            "cantidad_requerida": int(selected_record["cantidad_requerida"]) if selected_record else int(prefill_seed.get("cantidad_requerida", 0) or 0),
            "cantidad_instalada": int(selected_record["cantidad_instalada"]) if selected_record else 0,
            "cantidad_faltante": int(selected_record["cantidad_faltante"]) if selected_record else max(int(prefill_seed.get("cantidad_requerida", 0) or 0), 0),
            "estado": ((selected_record.get("estado") or "") if selected_record else prefill_estado),
            "fecha_solicitud_compra": ((selected_record.get("fecha_solicitud_compra") or "") if selected_record else ""),
            "fecha_entrega": ((selected_record.get("fecha_entrega") or "") if selected_record else ""),
            "fecha_instalacion": (prefill_fecha_instalacion if not selected_record else (selected_record.get("fecha_instalacion") or selected_record.get("fecha_colocacion") or selected_record.get("fecha_programada_colocacion") or "")),
            "observaciones": ((selected_record.get("observaciones") or "") if selected_record else ""),
        }
        if request.method == "POST" and (request.form.get("action") or "save").strip().lower() == "save":
            posted_aplica = _sst_bool_flag(request.form.get("aplica"))
            posted_requerida = _sst_int_nonneg(request.form.get("cantidad_requerida"))
            posted_instalada = _sst_int_nonneg(request.form.get("cantidad_instalada"))
            if not posted_aplica:
                posted_requerida = 0
                posted_instalada = 0
            form_defaults.update({
                "edit_id": _sst_int_nonneg(request.form.get("edit_id")),
                "sede_codigo": (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper(),
                "aplica": posted_aplica,
                "motivo_no_aplica": (request.form.get("motivo_no_aplica") or "").strip(),
                "cantidad_requerida": posted_requerida,
                "cantidad_instalada": posted_instalada,
                "cantidad_faltante": max(posted_requerida - posted_instalada, 0),
                "estado": _sst_luces_normalize_manual_state(request.form.get("estado")),
                "fecha_solicitud_compra": (request.form.get("fecha_solicitud_compra") or "").strip(),
                "fecha_entrega": (request.form.get("fecha_entrega") or "").strip(),
                "fecha_instalacion": (request.form.get("fecha_instalacion") or "").strip(),
                "observaciones": (request.form.get("observaciones") or "").strip(),
            })
        selected_context_sede = next((item for item in sedes if item["codigo"] == (detail_sede or f_sede)), None)
        close_modal_url = url_for(
            "sst_luces_home",
            sede=f_sede or None,
            estado=f_estado or None,
            q=f_q or None,
            month=(f_month or None),
        )
        if selected_summary:
            def _luces_form_url(prefill_estado_value=""):
                return url_for(
                    "sst_luces_home",
                    sede=f_sede or None,
                    estado=f_estado or None,
                    q=f_q or None,
                    month=(f_month or None),
                    open_sede=selected_summary["sede_codigo"],
                    registro=(int(selected_summary.get("primary_record_id") or 0) or None),
                    prefill_sede=selected_summary["sede_codigo"],
                    prefill_estado=(prefill_estado_value or None),
                    mostrar_form=1,
                )

            selected_summary = dict(selected_summary)
            selected_summary["modal_edit_url"] = _luces_form_url(selected_summary.get("estado") or "")
            selected_summary["modal_delivery_url"] = _luces_form_url("MATERIAL_RECIBIDO")
            selected_summary["show_register_delivery"] = bool(
                selected_summary.get("aplica")
                and selected_summary["state_code"] in {"PENDIENTE_DE_SOLICITUD", "EN_PROCESO_DE_COMPRA"}
            )
            selected_summary["modal_followup_enabled"] = bool(
                selected_summary.get("record_exists")
                and not selected_summary.get("seguimiento_id")
                and _sst_luces_has_pending_action(selected_summary)
            )
            selected_summary["modal_close_url"] = close_modal_url
        return {
            "sst_section": "luces",
            "sedes": sedes,
            "operativa_nav": build_operativa_nav_context(
                sedes,
                detail_sede or f_open_sede or f_sede or (state_by_sede[0]["sede_codigo"] if state_by_sede else ""),
                "sst_luces",
                filters={
                    "estado": f_estado,
                    "month": f_month,
                    "q": f_q,
                },
            ),
            "selected_sede": selected_context_sede,
            "selected_summary": selected_summary,
            "records": filtered_rows,
            "state_by_sede": state_by_sede,
            "history_rows": history_rows,
            "estado_options": [{"code": key, "label": value} for key, value in SST_LUCES_STATE_LABELS.items()],
            "estado_form_options": [{"code": key, "label": value} for key, value in SST_LUCES_FORM_STATE_LABELS.items()],
            "month_options": [{"value": number, "label": label} for number, label in SST_CALENDAR_MONTHS],
            "f_sede": f_sede,
            "f_estado": f_estado,
            "f_q": f_q,
            "f_month": f_month,
            "f_registro": f_registro,
            "f_open_sede": f_open_sede,
            "show_form": show_form,
            "form_defaults": form_defaults,
            "selected_record": selected_record,
            "kpi_requeridas": sum(item["cantidad_requerida"] for item in filtered_rows),
            "kpi_instaladas": sum(item["cantidad_instalada"] for item in filtered_rows),
            "kpi_faltantes": sum(item["cantidad_faltante"] for item in filtered_rows),
            "kpi_sedes_pendientes": sum(1 for item in filtered_rows if _sst_luces_has_pending_action(item)),
            "kpi_compras_en_proceso": sum(1 for item in filtered_rows if item["state_code"] in SST_LUCES_PURCHASE_STATES),
            "kpi_colocaciones_programadas": sum(1 for item in filtered_rows if item["state_code"] == "INSTALACION_PROGRAMADA"),
            "close_modal_url": close_modal_url,
            "fmt_fecha": _sst_fmt_fecha,
        }

    @app.route("/sst/luces", methods=["GET", "POST"], endpoint="sst_luces_home")
    def sst_luces_home():
        con = get_db()
        ensure_sst_general_table(con)
        ensure_sst_luces_tables(con)
        ensure_sst_operativo_historial_tables(con)
        if request.method == "POST":
            action = (request.form.get("action") or "save").strip().lower()
            user_name = _sst_current_user()
            if action == "seed":
                existing_map = _sst_luces_aggregate_by_sede(_sst_fetch_luces_records(con))
                inserted = 0
                skipped = 0
                now_ts = _sst_now_ts()
                for item in SST_LUCES_INITIAL_LOAD:
                    sede_codigo = (_sst_clean_upper(item.get("sede_codigo")) or "").strip().upper()
                    if not sede_codigo:
                        continue
                    if sede_codigo in existing_map:
                        skipped += 1
                        continue
                    aplica = 1 if int(item.get("aplica", 1) or 0) == 1 else 0
                    cantidad_requerida = int(item.get("cantidad_requerida", 0) or 0) if aplica else 0
                    motivo_no_aplica = (item.get("motivo_no_aplica") or "").strip() if not aplica else ""
                    con.execute("""
                        INSERT INTO sst_luces_registros(
                            sede_codigo, piso, deposito_codigo, aplica, motivo_no_aplica,
                            cantidad_requerida, cantidad_instalada, cantidad_operativa, cantidad_fuera_servicio,
                            creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?)
                    """, (
                        sede_codigo,
                        SST_LUCES_PLACEHOLDER_PISO,
                        SST_LUCES_PLACEHOLDER_DEPOSITO,
                        aplica,
                        motivo_no_aplica or None,
                        cantidad_requerida,
                        user_name,
                        user_name,
                        now_ts,
                        now_ts,
                    ))
                    registro_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                    _sst_historial_log(con, "luces", "carga_inicial", registro_id, sede_codigo, "", "Carga inicial sugerida aplicada.")
                    inserted += 1
                con.commit()
                con.close()
                if inserted and skipped:
                    flash(f"Se cargaron {inserted} sedes base y se omitieron {skipped} porque ya tienen relevamiento.", "success")
                elif inserted:
                    flash(f"Se cargaron {inserted} sedes base para luces de emergencia.", "success")
                else:
                    flash("No se aplico la carga inicial porque las sedes sugeridas ya tienen datos.", "warning")
                return redirect(url_for("sst_luces_home"))
            elif action == "save":
                edit_id = _sst_int_nonneg(request.form.get("edit_id"))
                sede_codigo = (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper()
                aplica = _sst_bool_flag(request.form.get("aplica"))
                motivo_no_aplica = (request.form.get("motivo_no_aplica") or "").strip()
                cantidad_requerida = _sst_int_nonneg(request.form.get("cantidad_requerida"))
                cantidad_instalada = _sst_int_nonneg(request.form.get("cantidad_instalada"))
                estado = _sst_luces_normalize_manual_state(request.form.get("estado"))
                if estado and estado not in SST_MANUAL_LUCES_STATES:
                    estado = ""
                if not sede_codigo:
                    flash("Selecciona una sede para guardar el relevamiento.", "warning")
                elif not aplica and not motivo_no_aplica:
                    flash("Indica el motivo cuando la sede no aplica.", "warning")
                elif aplica and cantidad_requerida > 0 and cantidad_instalada > cantidad_requerida:
                    flash("La cantidad instalada no deberia superar la requerida sin confirmacion.", "warning")
                else:
                    previous_summary = _sst_luces_aggregate_by_sede(
                        [item for item in _sst_fetch_luces_records(con) if item["sede_codigo"] == sede_codigo]
                    ).get(sede_codigo)
                    existing_rows = con.execute("""
                        SELECT id
                        FROM sst_luces_registros
                        WHERE COALESCE(activo, 1) = 1
                          AND UPPER(COALESCE(sede_codigo, '')) = ?
                          AND (? = 0 OR id <> ?)
                        ORDER BY COALESCE(fecha_actualizacion, fecha_creacion, '') DESC, id DESC
                    """, (sede_codigo, edit_id, edit_id)).fetchall()
                    if not edit_id and existing_rows:
                        edit_id = int(_row_value(existing_rows[0], "id", 0) or 0)
                    if len(existing_rows) > 1:
                        flash("Se detectaron registros legacy multiples para la sede. Se actualizara el mas reciente y la vista seguira consolidando por sede.", "warning")
                    fecha_solicitud_compra = (request.form.get("fecha_solicitud_compra") or "").strip()
                    fecha_entrega = (request.form.get("fecha_entrega") or "").strip()
                    fecha_instalacion = (request.form.get("fecha_instalacion") or "").strip()
                    referencia_pedido = str((previous_summary or {}).get("referencia_pedido") or "").strip()
                    fecha_programada_colocacion = fecha_instalacion
                    fecha_colocacion = (
                        fecha_instalacion
                        if (estado == "COMPLETO" or cantidad_instalada >= cantidad_requerida)
                        else ""
                    )
                    fecha_mantenimiento = str((previous_summary or {}).get("fecha_mantenimiento") or "").strip()
                    observaciones = (request.form.get("observaciones") or "").strip()
                    if not aplica:
                        cantidad_requerida = 0
                        cantidad_instalada = 0
                        motivo_no_aplica = motivo_no_aplica.strip()
                        estado = "NO_APLICA"
                        fecha_solicitud_compra = ""
                        referencia_pedido = ""
                        fecha_entrega = ""
                        fecha_programada_colocacion = ""
                        fecha_colocacion = ""
                    cantidad_operativa = cantidad_instalada if aplica else 0
                    cantidad_fuera_servicio = 0
                    if edit_id:
                        con.execute("""
                            UPDATE sst_luces_registros
                            SET sede_codigo = ?,
                                aplica = ?, motivo_no_aplica = ?,
                                cantidad_requerida = ?, cantidad_instalada = ?,
                                cantidad_operativa = ?, cantidad_fuera_servicio = ?,
                                estado = ?,
                                fecha_solicitud_compra = ?, fecha_pedido = ?,
                                referencia_pedido = ?, numero_pedido = ?,
                                fecha_entrega = ?, fecha_disponibilidad = ?,
                                fecha_programada_colocacion = ?, fecha_intervencion_programada = ?, fecha_programada_intervencion = ?,
                                fecha_colocacion = ?, fecha_intervencion_realizada = ?, fecha_intervencion = ?,
                                fecha_mantenimiento = ?, observaciones = ?,
                                actualizado_por = ?, fecha_actualizacion = ?
                            WHERE id = ?
                        """, (
                            sede_codigo,
                            aplica,
                            (motivo_no_aplica or None),
                            cantidad_requerida,
                            cantidad_instalada,
                            cantidad_operativa,
                            cantidad_fuera_servicio,
                            estado or None,
                            fecha_solicitud_compra or None,
                            fecha_solicitud_compra or None,
                            referencia_pedido or None,
                            referencia_pedido or None,
                            fecha_entrega or None,
                            fecha_entrega or None,
                            fecha_programada_colocacion or None,
                            fecha_programada_colocacion or None,
                            fecha_programada_colocacion or None,
                            fecha_colocacion or None,
                            fecha_colocacion or None,
                            fecha_colocacion or None,
                            fecha_mantenimiento or None,
                            observaciones or None,
                            user_name,
                            _sst_now_ts(),
                            edit_id,
                        ))
                        registro_id = edit_id
                    else:
                        con.execute("""
                            INSERT INTO sst_luces_registros(
                                sede_codigo, piso, deposito_codigo, aplica, motivo_no_aplica,
                                cantidad_requerida, cantidad_instalada, cantidad_operativa, cantidad_fuera_servicio,
                                estado,
                                fecha_solicitud_compra, fecha_pedido,
                                referencia_pedido, numero_pedido,
                                fecha_entrega, fecha_disponibilidad,
                                fecha_programada_colocacion, fecha_intervencion_programada, fecha_programada_intervencion,
                                fecha_colocacion, fecha_intervencion_realizada, fecha_intervencion,
                                fecha_mantenimiento, observaciones,
                                creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sede_codigo,
                            SST_LUCES_PLACEHOLDER_PISO,
                            SST_LUCES_PLACEHOLDER_DEPOSITO,
                            aplica,
                            (motivo_no_aplica or None),
                            cantidad_requerida,
                            cantidad_instalada,
                            cantidad_operativa,
                            cantidad_fuera_servicio,
                            estado or None,
                            fecha_solicitud_compra or None,
                            fecha_solicitud_compra or None,
                            referencia_pedido or None,
                            referencia_pedido or None,
                            fecha_entrega or None,
                            fecha_entrega or None,
                            fecha_programada_colocacion or None,
                            fecha_programada_colocacion or None,
                            fecha_programada_colocacion or None,
                            fecha_colocacion or None,
                            fecha_colocacion or None,
                            fecha_colocacion or None,
                            fecha_mantenimiento or None,
                            observaciones or None,
                            user_name,
                            user_name,
                            _sst_now_ts(),
                            _sst_now_ts(),
                        ))
                        registro_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                    updated_summary = _sst_luces_aggregate_by_sede(
                        [item for item in _sst_fetch_luces_records(con) if item["sede_codigo"] == sede_codigo]
                    ).get(sede_codigo)
                    if edit_id and previous_summary:
                        _sst_historial_log(con, "luces", "actualizacion", registro_id, sede_codigo, "", "Actualizacion de gestion consolidada por sede.")
                    else:
                        _sst_historial_log(con, "luces", "alta", registro_id, sede_codigo, "", "Alta de gestion consolidada por sede.")
                    if updated_summary:
                        previous_label = previous_summary["state_meta"]["label"] if previous_summary else "Sin estado"
                        current_label = updated_summary["state_meta"]["label"]
                        if not previous_summary or previous_summary["state_code"] != updated_summary["state_code"]:
                            detail = f"{previous_label} -> {current_label}"
                            if observaciones:
                                detail += f" | {observaciones}"
                            _sst_historial_log(con, "luces", "cambio_estado", registro_id, sede_codigo, "", detail)
                    flash("Registro de luces guardado.", "success")
                    con.commit()
                    con.close()
                    return redirect(url_for("sst_luces_home", sede=sede_codigo, open_sede=sede_codigo, registro=registro_id))
            elif action == "delete":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                row = con.execute("SELECT sede_codigo FROM sst_luces_registros WHERE id = ?", (record_id,)).fetchone()
                if row:
                    sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                    con.execute("UPDATE sst_luces_registros SET activo = 0, actualizado_por = ?, fecha_actualizacion = ? WHERE id = ?", (user_name, _sst_now_ts(), record_id))
                    _sst_historial_log(con, "luces", "baja_logica", record_id, sede_codigo, "", "Baja logica del relevamiento de luces.")
                    con.commit()
                    con.close()
                    flash("Registro de luces dado de baja.", "success")
                    return redirect(url_for("sst_luces_home", sede=sede_codigo))
            elif action == "test":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                row = con.execute("SELECT sede_codigo FROM sst_luces_registros WHERE id = ?", (record_id,)).fetchone()
                fecha_prueba = (request.form.get("fecha_prueba") or "").strip()
                if row and fecha_prueba:
                    sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                    resultado = (request.form.get("resultado_prueba") or "").strip()
                    proxima = (request.form.get("fecha_proxima_prueba_test") or "").strip()
                    observaciones = (request.form.get("observaciones_prueba") or "").strip()
                    con.execute("INSERT INTO sst_luces_pruebas(registro_id, fecha_prueba, resultado, fecha_proxima_prueba, observaciones, creado_por) VALUES (?, ?, ?, ?, ?, ?)", (record_id, fecha_prueba, resultado or None, proxima or None, observaciones or None, user_name))
                    con.execute("UPDATE sst_luces_registros SET fecha_ultima_prueba = ?, resultado_ultima_prueba = ?, fecha_proxima_prueba = COALESCE(?, fecha_proxima_prueba), actualizado_por = ?, fecha_actualizacion = ? WHERE id = ?", (fecha_prueba, resultado or None, proxima or None, user_name, _sst_now_ts(), record_id))
                    _sst_historial_log(con, "luces", "prueba", record_id, sede_codigo, "", f"Prueba registrada: {resultado or 'sin resultado'}.")
                    con.commit()
                    con.close()
                    flash("Prueba de luces registrada.", "success")
                    return redirect(url_for("sst_luces_home", sede=sede_codigo, open_sede=sede_codigo, registro=record_id))
            elif action == "followup":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                raw_record = next((item for item in _sst_fetch_luces_records(con) if int(item["id"]) == record_id), None)
                record = None
                if raw_record:
                    record = _sst_luces_aggregate_by_sede([item for item in _sst_fetch_luces_records(con) if item["sede_codigo"] == raw_record["sede_codigo"]]).get(raw_record["sede_codigo"])
                if record:
                    if not _sst_luces_has_pending_action(record):
                        con.close()
                        flash("La sede no tiene acciones pendientes para seguimiento.", "warning")
                        return redirect(url_for("sst_luces_home", sede=record["sede_codigo"], open_sede=record["sede_codigo"], registro=record_id))
                    if int(record.get("seguimiento_id") or 0) > 0:
                        con.close()
                        flash("La sede ya tiene un seguimiento vinculado para luces.", "warning")
                        return redirect(url_for("sst_luces_home", sede=record["sede_codigo"], open_sede=record["sede_codigo"], registro=record_id))
                    accion_correctiva = _sst_luces_followup_text(record)
                    detalle = (
                        f"Estado: {record['state_meta']['label']} | "
                        f"Requeridas: {record['cantidad_requerida']} | "
                        f"Instaladas: {record['cantidad_instalada']} | "
                        f"Faltantes: {record['cantidad_faltante']} | "
                        f"Proxima accion: {record['action_label']}"
                    )
                    if str(record.get("observaciones") or "").strip():
                        detalle += f" | Observaciones: {record['observaciones']}"
                    con.execute("""
                        INSERT INTO sst_general(
                            fecha, sede_codigo, tipo, categoria, area, titulo, detalle,
                            estado, prioridad, responsable, accion_correctiva, fecha_objetivo,
                            origen_tipo, origen_id, origen_deposito_codigo
                        )
                        VALUES (?, ?, 'no_conformidad', 'Luces de emergencia', 'SG-SST', ?, ?, 'ABIERTO', 'Media', ?, ?, ?, 'luces', ?, ?)
                    """, (
                        date.today().isoformat(),
                        record["sede_codigo"],
                        f"Luces de emergencia {record['sede_codigo']}",
                        detalle,
                        user_name,
                        accion_correctiva,
                        record.get("fecha_programada_colocacion")
                        or record.get("fecha_colocacion")
                        or record.get("fecha_entrega")
                        or record.get("fecha_solicitud_compra")
                        or date.today().isoformat(),
                        int(record.get("primary_record_id") or record_id),
                        None,
                    ))
                    seguimiento_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                    con.execute("""
                        UPDATE sst_luces_registros
                        SET seguimiento_id = ?, actualizado_por = ?, fecha_actualizacion = ?
                        WHERE COALESCE(activo, 1) = 1 AND UPPER(COALESCE(sede_codigo, '')) = ?
                    """, (seguimiento_id, user_name, _sst_now_ts(), record["sede_codigo"]))
                    _sst_historial_log(con, "luces", "seguimiento", int(record.get("primary_record_id") or record_id), record["sede_codigo"], "", f"Seguimiento #{seguimiento_id} creado.")
                    con.commit()
                    con.close()
                    flash("Seguimiento creado desde luces.", "success")
                    return redirect(url_for("sst_luces_home", sede=record["sede_codigo"], open_sede=record["sede_codigo"], registro=record_id))
            con.commit()
        context = _sst_luces_context(con)
        con.close()
        return render_template("sst_luces_home.html", **context)

    @app.route("/sst/luces/plano/<sede_codigo>/<piso>", methods=["GET", "POST"], endpoint="sst_luces_plano_api")
    def sst_luces_plano_api(sede_codigo, piso):
        con = get_db()
        ensure_sst_luces_tables(con)
        ensure_sst_operativo_historial_tables(con)
        sede_codigo = (_sst_clean_upper(sede_codigo) or "").strip().upper()
        piso = (_sst_clean_upper(piso) or "PB").strip().upper()
        if piso == "1P":
            piso = "P1"
        elif piso == "2P":
            piso = "P2"

        if not sede_codigo:
            con.close()
            return jsonify({"ok": False, "message": "Sede invalida."}), 400

        if request.method == "GET":
            markers = []
            for record in _sst_fetch_luces_records(con):
                if record.get("sede_codigo") != sede_codigo or record.get("piso") != piso:
                    continue
                if not record.get("plan_markers"):
                    continue
                for marker in (record.get("plan_markers") or []):
                    try:
                        x_val = float(marker.get("x", 0.5))
                    except Exception:
                        x_val = 0.5
                    try:
                        y_val = float(marker.get("y", 0.5))
                    except Exception:
                        y_val = 0.5
                    markers.append({
                        "id": f"le-{uuid.uuid4().hex[:8]}",
                        "state": _sst_luces_canonical_plan_state(marker.get("state")),
                        "label": str(marker.get("label") or "").strip(),
                        "local": (_sst_clean_upper(marker.get("local")) or "").strip().upper(),
                        "x": max(0.03, min(0.97, x_val)),
                        "y": max(0.03, min(0.97, y_val)),
                    })
            con.close()
            return jsonify({"ok": True, "markers": markers})

        payload = request.get_json(silent=True) or {}
        raw_markers = payload.get("markers")
        if not isinstance(raw_markers, list):
            con.close()
            return jsonify({"ok": False, "message": "No se recibieron marcadores validos."}), 400

        user_name = _sst_current_user()
        normalized_markers = []
        for idx, marker in enumerate(raw_markers, start=1):
            if not isinstance(marker, dict):
                continue
            state_code = _sst_luces_canonical_plan_state(marker.get("state"))
            if not state_code:
                continue
            try:
                x_val = float(marker.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(marker.get("y", 0.5))
            except Exception:
                y_val = 0.5
            normalized_markers.append({
                "state": state_code,
                "label": str(marker.get("label") or "").strip() or f"LE {idx:02d}",
                "local": (_sst_clean_upper(marker.get("local")) or "").strip().upper(),
                "x": max(0.03, min(0.97, x_val)),
                "y": max(0.03, min(0.97, y_val)),
            })

        now_ts = _sst_now_ts()
        con.execute("""
            UPDATE sst_luces_registros
            SET activo = 0, actualizado_por = ?, fecha_actualizacion = ?
            WHERE COALESCE(activo, 1) = 1
              AND UPPER(COALESCE(sede_codigo, '')) = ?
              AND UPPER(COALESCE(piso, 'PB')) = ?
              AND NOT (
                UPPER(COALESCE(piso, 'SEDE')) = ?
                AND UPPER(COALESCE(deposito_codigo, 'SEDE')) = ?
              )
        """, (user_name, now_ts, sede_codigo, piso, SST_LUCES_PLACEHOLDER_PISO, SST_LUCES_PLACEHOLDER_DEPOSITO))

        con.execute("""
            UPDATE sst_luces_registros
            SET activo = 0, actualizado_por = ?, fecha_actualizacion = ?
            WHERE COALESCE(activo, 1) = 1
              AND UPPER(COALESCE(sede_codigo, '')) = ?
              AND UPPER(COALESCE(piso, 'SEDE')) = ?
              AND UPPER(COALESCE(deposito_codigo, 'SEDE')) = ?
        """, (user_name, now_ts, sede_codigo, SST_LUCES_PLACEHOLDER_PISO, SST_LUCES_PLACEHOLDER_DEPOSITO))

        registro_id = 0
        if normalized_markers:
            required_count = sum(1 for marker in normalized_markers if marker["state"] != "no_aplica")
            installed_count = sum(1 for marker in normalized_markers if marker["state"] in {"instalada", "fuera_servicio"})
            operative_count = sum(1 for marker in normalized_markers if marker["state"] == "instalada")
            out_of_service_count = sum(1 for marker in normalized_markers if marker["state"] == "fuera_servicio")
            applies = 1 if required_count > 0 else 0
            estado = "MANTENIMIENTO" if out_of_service_count > 0 else None
            motivo_no_aplica = "Marcado como no aplica en el plano." if not applies else None
            observaciones = _sst_luces_pack_observaciones(normalized_markers)
            con.execute("""
                INSERT INTO sst_luces_registros(
                    sede_codigo, piso, deposito_codigo, aplica, motivo_no_aplica,
                    cantidad_requerida, cantidad_instalada, cantidad_operativa, cantidad_fuera_servicio,
                    estado, fecha_relevamiento, fecha_mantenimiento, observaciones,
                    creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sede_codigo,
                piso,
                SST_LUCES_PLACEHOLDER_DEPOSITO,
                applies,
                motivo_no_aplica,
                required_count if applies else 0,
                installed_count if applies else 0,
                operative_count if applies else 0,
                out_of_service_count if applies else 0,
                estado,
                date.today().isoformat(),
                date.today().isoformat() if out_of_service_count > 0 else None,
                observaciones,
                user_name,
                user_name,
                now_ts,
                now_ts,
            ))
            registro_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

        _sst_historial_log(
            con,
            "luces",
            "actualizacion",
            registro_id,
            sede_codigo,
            piso,
            f"Plano de luces actualizado desde sede ({piso}). Marcadores: {len(normalized_markers)}.",
        )
        con.commit()
        con.close()
        return jsonify({"ok": True, "message": "Luces guardadas.", "markers": normalized_markers})

    @app.route("/sst/carteleria", methods=["GET", "POST"], endpoint="sst_carteleria_home")
    def sst_carteleria_home():
        asegurar_tablas_planos()
        con = get_db()
        ensure_sst_general_table(con)
        ensure_sst_carteleria_tables(con)
        ensure_sst_operativo_historial_tables(con)
        if request.method == "POST":
            action = (request.form.get("action") or "save").strip().lower()
            user_name = _sst_current_user()
            if action == "save":
                sede_codigo = (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper()
                fecha_solicitud = (request.form.get("fecha_solicitud") or "").strip()
                fecha_entrega = (request.form.get("fecha_entrega") or "").strip()
                fecha_instalacion = (request.form.get("fecha_instalacion") or "").strip()
                observaciones = (request.form.get("observaciones") or "").strip()
                item_rows = {}
                validation_errors = []
                for code in SST_CARTELERIA_VISIBLE_CODES:
                    aplica = _sst_carteleria_normalize_aplica(request.form.get(f"item_aplica_{code}"), "NO_RELEVADO")
                    cantidad_requerida = _sst_int_nonneg(request.form.get(f"item_requerida_{code}"))
                    cantidad_instalada = _sst_int_nonneg(request.form.get(f"item_instalada_{code}"))
                    if aplica != "SI":
                        cantidad_requerida = 0
                        cantidad_instalada = 0
                    if aplica == "SI" and cantidad_instalada > cantidad_requerida:
                        validation_errors.append(
                            f"{SST_CARTELERIA_TIPO_LABELS.get(code, code.title())}: instalada no puede superar requerida."
                        )
                    item_rows[code] = {
                        "aplica": aplica,
                        "cantidad_requerida": cantidad_requerida,
                        "cantidad_instalada": cantidad_instalada,
                    }
                if not sede_codigo:
                    flash("Selecciona una sede.", "warning")
                elif validation_errors:
                    for message in validation_errors[:3]:
                        flash(message, "warning")
                else:
                    type_rows = con.execute("""
                        SELECT id, codigo
                        FROM sst_carteleria_tipos
                        WHERE COALESCE(activo, 1) = 1
                    """).fetchall()
                    type_id_by_code = {
                        (_row_value(row, "codigo", "") or "").strip().upper(): int(_row_value(row, "id", 0) or 0)
                        for row in type_rows
                    }
                    previous_summary = _sst_carteleria_aggregate_by_sede(
                        [item for item in _sst_fetch_carteleria_records(con) if item["sede_codigo"] == sede_codigo]
                    ).get(sede_codigo)
                    existing_rows = con.execute("""
                        SELECT r.id, t.codigo
                        FROM sst_carteleria_registros r
                        JOIN sst_carteleria_tipos t ON t.id = r.tipo_id
                        WHERE COALESCE(r.activo, 1) = 1
                          AND UPPER(COALESCE(r.sede_codigo, '')) = ?
                          AND UPPER(COALESCE(r.piso, 'SEDE')) = ?
                          AND UPPER(COALESCE(r.deposito_codigo, 'SEDE')) = ?
                    """, (sede_codigo, SST_CARTELERIA_PLACEHOLDER_PISO, SST_CARTELERIA_PLACEHOLDER_DEPOSITO)).fetchall()
                    existing_by_code = {
                        (_row_value(row, "codigo", "") or "").strip().upper(): int(_row_value(row, "id", 0) or 0)
                        for row in existing_rows
                    }
                    requeridos = sum(item["cantidad_requerida"] for item in item_rows.values() if item["aplica"] == "SI")
                    instalados = sum(item["cantidad_instalada"] for item in item_rows.values() if item["aplica"] == "SI")
                    auto_complete = requeridos > 0 and instalados >= requeridos
                    fecha_programada = fecha_instalacion if fecha_instalacion and not auto_complete else None
                    fecha_colocacion = fecha_instalacion if fecha_instalacion and auto_complete else None
                    registro_id = 0
                    for code in SST_CARTELERIA_VISIBLE_CODES:
                        tipo_id = type_id_by_code.get(code)
                        if not tipo_id:
                            continue
                        row_data = item_rows.get(code, {})
                        aplica = row_data.get("aplica", "NO_RELEVADO")
                        cantidad_requerida = _sst_int_nonneg(row_data.get("cantidad_requerida"))
                        cantidad_instalada = _sst_int_nonneg(row_data.get("cantidad_instalada"))
                        existing_id = int(existing_by_code.get(code) or 0)
                        payload = (
                            sede_codigo,
                            SST_CARTELERIA_PLACEHOLDER_PISO,
                            SST_CARTELERIA_PLACEHOLDER_DEPOSITO,
                            tipo_id,
                            aplica or None,
                            cantidad_requerida,
                            cantidad_instalada,
                            None,
                            (date.today().isoformat() if aplica != "NO_RELEVADO" else None),
                            user_name,
                            fecha_solicitud or None,
                            None,
                            fecha_entrega or None,
                            fecha_programada,
                            fecha_colocacion,
                            None,
                            observaciones or None,
                        )
                        if existing_id:
                            con.execute("""
                                UPDATE sst_carteleria_registros
                                SET sede_codigo = ?, piso = ?, deposito_codigo = ?, tipo_id = ?, aplica = ?,
                                    cantidad_requerida = ?, cantidad_instalada = ?, estado = ?,
                                    fecha_relevamiento = ?, responsable_relevamiento = ?,
                                    fecha_pedido = ?, numero_pedido = ?, fecha_disponibilidad = ?,
                                    fecha_programada_colocacion = ?, fecha_colocacion = ?,
                                    fecha_verificacion = ?, observaciones = ?,
                                    actualizado_por = ?, fecha_actualizacion = ?
                                WHERE id = ?
                            """, payload + (user_name, _sst_now_ts(), existing_id))
                            registro_id = registro_id or existing_id
                        else:
                            con.execute("""
                                INSERT INTO sst_carteleria_registros(
                                    sede_codigo, piso, deposito_codigo, tipo_id, aplica, cantidad_requerida, cantidad_instalada, estado,
                                    fecha_relevamiento, responsable_relevamiento, fecha_pedido, numero_pedido, fecha_disponibilidad,
                                    fecha_programada_colocacion, fecha_colocacion, fecha_verificacion, observaciones,
                                    creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, payload + (user_name, user_name, _sst_now_ts(), _sst_now_ts()))
                            registro_id = registro_id or int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                    updated_summary = _sst_carteleria_aggregate_by_sede(
                        [item for item in _sst_fetch_carteleria_records(con) if item["sede_codigo"] == sede_codigo]
                    ).get(sede_codigo)
                    if previous_summary:
                        _sst_historial_log(con, "carteleria", "actualizacion", registro_id, sede_codigo, "", "Actualizacion de gestion consolidada por sede.")
                    else:
                        _sst_historial_log(con, "carteleria", "alta", registro_id, sede_codigo, "", "Alta de gestion consolidada por sede.")
                    if updated_summary:
                        previous_label = previous_summary["state_meta"]["label"] if previous_summary else "Sin estado"
                        current_label = updated_summary["state_meta"]["label"]
                        if not previous_summary or previous_summary["state_code"] != updated_summary["state_code"]:
                            detalle = f"{previous_label} -> {current_label}"
                            if observaciones:
                                detalle += f" | {observaciones}"
                            _sst_historial_log(con, "carteleria", "cambio_estado", registro_id, sede_codigo, "", detalle)
                    flash("Registro de carteleria guardado.", "success")
                    con.commit()
                    con.close()
                    return redirect(url_for("sst_carteleria_home", sede=sede_codigo, open_sede=sede_codigo, registro=registro_id))
            elif action == "delete":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                row = con.execute("SELECT sede_codigo, piso, deposito_codigo FROM sst_carteleria_registros WHERE id = ?", (record_id,)).fetchone()
                if row:
                    sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                    piso = (_row_value(row, "piso", "PB") or "PB").strip().upper()
                    deposito_codigo = (_row_value(row, "deposito_codigo", "") or "").strip().upper()
                    con.execute("UPDATE sst_carteleria_registros SET activo = 0, actualizado_por = ?, fecha_actualizacion = ? WHERE id = ?", (user_name, _sst_now_ts(), record_id))
                    _sst_historial_log(con, "carteleria", "baja_logica", record_id, sede_codigo, deposito_codigo, "Baja logica del relevamiento de carteleria.")
                    con.commit()
                    con.close()
                    flash("Registro de carteleria dado de baja.", "success")
                    return redirect(url_for("sst_carteleria_home", sede=sede_codigo))
            elif action == "followup":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                raw_record = next((item for item in _sst_fetch_carteleria_records(con) if int(item["id"]) == record_id), None)
                record = None
                if raw_record:
                    record = _sst_carteleria_aggregate_by_sede(
                        [item for item in _sst_fetch_carteleria_records(con) if item["sede_codigo"] == raw_record["sede_codigo"]]
                    ).get(raw_record["sede_codigo"])
                if record:
                    if not _sst_carteleria_has_pending_action(record):
                        con.close()
                        flash("La sede no tiene acciones pendientes para seguimiento.", "warning")
                        return redirect(url_for("sst_carteleria_home", sede=record["sede_codigo"], open_sede=record["sede_codigo"], registro=record_id))
                    if int(record.get("seguimiento_id") or 0) > 0:
                        con.close()
                        flash("La sede ya tiene un seguimiento vinculado para carteleria.", "warning")
                        return redirect(url_for("sst_carteleria_home", sede=record["sede_codigo"], open_sede=record["sede_codigo"], registro=record_id))
                    accion_correctiva = _sst_carteleria_followup_text(record)
                    detalle = (
                        f"Estado: {record['state_meta']['label']} | "
                        f"Requeridos: {record['cantidad_requerida']} | "
                        f"Instalados: {record['cantidad_instalada']} | "
                        f"Faltantes: {record['cantidad_faltante']} | "
                        f"Proxima accion: {record['action_label']}"
                    )
                    if str(record.get("observaciones") or "").strip():
                        detalle += f" | Observaciones: {record['observaciones']}"
                    con.execute("""
                        INSERT INTO sst_general(
                            fecha, sede_codigo, tipo, categoria, area, titulo, detalle,
                            estado, prioridad, responsable, accion_correctiva, fecha_objetivo,
                            origen_tipo, origen_id, origen_deposito_codigo
                        )
                        VALUES (?, ?, 'no_conformidad', 'Carteleria', 'SG-SST', ?, ?, 'ABIERTO', 'Media', ?, ?, ?, 'carteleria', ?, ?)
                    """, (
                        date.today().isoformat(),
                        record["sede_codigo"],
                        f"Carteleria {record['sede_codigo']}",
                        detalle,
                        user_name,
                        accion_correctiva,
                        record.get("fecha_instalacion") or record.get("fecha_entrega") or record.get("fecha_solicitud") or date.today().isoformat(),
                        int(record.get("primary_record_id") or record_id),
                        None,
                    ))
                    seguimiento_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                    con.execute("""
                        UPDATE sst_carteleria_registros
                        SET seguimiento_id = ?, actualizado_por = ?, fecha_actualizacion = ?
                        WHERE COALESCE(activo, 1) = 1 AND UPPER(COALESCE(sede_codigo, '')) = ?
                    """, (seguimiento_id, user_name, _sst_now_ts(), record["sede_codigo"]))
                    _sst_historial_log(con, "carteleria", "seguimiento", int(record.get("primary_record_id") or record_id), record["sede_codigo"], "", f"Seguimiento #{seguimiento_id} creado.")
                    con.commit()
                    con.close()
                    flash("Seguimiento creado desde carteleria.", "success")
                    return redirect(url_for(
                        "sst_general",
                        modo="gestion",
                        sede=record["sede_codigo"],
                        tipo="no_conformidad",
                        q=f"Carteleria {record['sede_codigo']}",
                    ))
            con.commit()
        context = _sst_carteleria_context(con)
        con.close()
        return render_template("sst_carteleria_home.html", **context)

    @app.route("/sst/carteleria/plano/<sede_codigo>/<piso>", methods=["GET", "POST"], endpoint="sst_carteleria_plano_api")
    def sst_carteleria_plano_api(sede_codigo, piso):
        con = get_db()
        ensure_sst_carteleria_tables(con)
        ensure_sst_operativo_historial_tables(con)
        sede_codigo = (_sst_clean_upper(sede_codigo) or "").strip().upper()
        piso = (_sst_clean_upper(piso) or "PB").strip().upper()
        if piso == "1P":
            piso = "P1"
        elif piso == "2P":
            piso = "P2"

        if not sede_codigo:
            con.close()
            return jsonify({"ok": False, "message": "Sede invalida."}), 400

        if request.method == "GET":
            markers = []
            for record in _sst_fetch_carteleria_records(con):
                if record.get("sede_codigo") != sede_codigo or record.get("piso") != piso:
                    continue
                if not record.get("plan_markers"):
                    continue
                default_local = "" if record.get("deposito_codigo") == SST_CARTELERIA_PLACEHOLDER_DEPOSITO else (record.get("deposito_codigo") or "")
                default_type = record.get("canonical_tipo_codigo") or record.get("tipo_codigo") or ""
                for marker in (record.get("plan_markers") or []):
                    try:
                        x_val = float(marker.get("x", 0.5))
                    except Exception:
                        x_val = 0.5
                    try:
                        y_val = float(marker.get("y", 0.5))
                    except Exception:
                        y_val = 0.5
                    markers.append({
                        "id": f"ct-{uuid.uuid4().hex[:8]}",
                        "type": _sst_carteleria_canonical_tipo_code(marker.get("type") or default_type),
                        "label": str(marker.get("label") or "").strip(),
                        "local": (_sst_clean_upper(marker.get("local") or default_local) or "").strip().upper(),
                        "x": max(0.03, min(0.97, x_val)),
                        "y": max(0.03, min(0.97, y_val)),
                    })
            con.close()
            return jsonify({"ok": True, "markers": markers})

        payload = request.get_json(silent=True) or {}
        raw_markers = payload.get("markers")
        if not isinstance(raw_markers, list):
            con.close()
            return jsonify({"ok": False, "message": "No se recibieron marcadores validos."}), 400

        user_name = _sst_current_user()
        type_rows = con.execute("""
            SELECT id, codigo
            FROM sst_carteleria_tipos
            WHERE COALESCE(activo, 1) = 1
        """).fetchall()
        type_id_by_code = {
            (_row_value(row, "codigo", "") or "").strip().upper(): int(_row_value(row, "id", 0) or 0)
            for row in type_rows
        }

        grouped = defaultdict(list)
        payload_type_codes = set()
        for idx, marker in enumerate(raw_markers, start=1):
            if not isinstance(marker, dict):
                continue
            type_code = _sst_carteleria_canonical_tipo_code(marker.get("type"))
            if not type_code or int(type_id_by_code.get(type_code) or 0) <= 0:
                continue
            try:
                x_val = float(marker.get("x", 0.5))
            except Exception:
                x_val = 0.5
            try:
                y_val = float(marker.get("y", 0.5))
            except Exception:
                y_val = 0.5
            local_label = (_sst_clean_upper(marker.get("local")) or "").strip().upper()
            storage_local = local_label or SST_CARTELERIA_PLACEHOLDER_DEPOSITO
            label = str(marker.get("label") or "").strip() or f"{type_code} {idx:02d}"
            grouped[(storage_local, type_code)].append({
                "type": type_code,
                "label": label,
                "local": local_label,
                "x": max(0.03, min(0.97, x_val)),
                "y": max(0.03, min(0.97, y_val)),
            })
            payload_type_codes.add(type_code)

        now_ts = _sst_now_ts()
        con.execute("""
            UPDATE sst_carteleria_registros
            SET activo = 0, actualizado_por = ?, fecha_actualizacion = ?
            WHERE COALESCE(activo, 1) = 1
              AND UPPER(COALESCE(sede_codigo, '')) = ?
              AND UPPER(COALESCE(piso, 'PB')) = ?
              AND NOT (
                UPPER(COALESCE(piso, 'SEDE')) = ?
                AND UPPER(COALESCE(deposito_codigo, 'SEDE')) = ?
              )
        """, (user_name, now_ts, sede_codigo, piso, SST_CARTELERIA_PLACEHOLDER_PISO, SST_CARTELERIA_PLACEHOLDER_DEPOSITO))

        if payload_type_codes:
            placeholders = con.execute(f"""
                SELECT r.id
                FROM sst_carteleria_registros r
                JOIN sst_carteleria_tipos t ON t.id = r.tipo_id
                WHERE COALESCE(r.activo, 1) = 1
                  AND UPPER(COALESCE(r.sede_codigo, '')) = ?
                  AND UPPER(COALESCE(r.piso, 'SEDE')) = ?
                  AND UPPER(COALESCE(r.deposito_codigo, 'SEDE')) = ?
                  AND UPPER(COALESCE(t.codigo, '')) IN ({",".join(["?"] * len(payload_type_codes))})
            """, (sede_codigo, SST_CARTELERIA_PLACEHOLDER_PISO, SST_CARTELERIA_PLACEHOLDER_DEPOSITO, *sorted(payload_type_codes))).fetchall()
            placeholder_ids = [int(_row_value(row, "id", 0) or 0) for row in placeholders if int(_row_value(row, "id", 0) or 0) > 0]
            if placeholder_ids:
                con.execute(f"""
                    UPDATE sst_carteleria_registros
                    SET activo = 0, actualizado_por = ?, fecha_actualizacion = ?
                    WHERE id IN ({",".join(["?"] * len(placeholder_ids))})
                """, (user_name, now_ts, *placeholder_ids))

        registro_id = 0
        saved_markers = []
        for (storage_local, type_code), markers_for_row in grouped.items():
            tipo_id = int(type_id_by_code.get(type_code) or 0)
            if not tipo_id:
                continue
            count = len(markers_for_row)
            observaciones = _sst_carteleria_pack_observaciones(markers_for_row)
            con.execute("""
                INSERT INTO sst_carteleria_registros(
                    sede_codigo, piso, deposito_codigo, tipo_id, aplica, cantidad_requerida, cantidad_instalada, estado,
                    fecha_relevamiento, responsable_relevamiento, fecha_pedido, numero_pedido, fecha_disponibilidad,
                    fecha_programada_colocacion, fecha_colocacion, fecha_verificacion, observaciones,
                    creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sede_codigo,
                piso,
                storage_local,
                tipo_id,
                "SI",
                count,
                count,
                None,
                date.today().isoformat(),
                user_name,
                None,
                None,
                None,
                None,
                date.today().isoformat(),
                None,
                observaciones,
                user_name,
                user_name,
                now_ts,
                now_ts,
            ))
            registro_id = registro_id or int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
            saved_markers.extend(markers_for_row)

        _sst_historial_log(
            con,
            "carteleria",
            "actualizacion",
            registro_id,
            sede_codigo,
            piso,
            f"Plano de carteleria actualizado desde sede ({piso}). Marcadores: {len(saved_markers)}.",
        )
        con.commit()
        con.close()
        return jsonify({"ok": True, "message": "Carteleria guardada.", "markers": saved_markers})

    @app.route("/sst", methods=["GET", "POST"], endpoint="sst_general")
    def sst_general():
        if request.method == "GET" and (request.args.get("modo") or "").strip().lower() != "gestion":
            return redirect(url_for("sst_calendario_operativo"))
        con = get_db()
        ensure_sst_general_table(con)
        q_agente_id = (request.args.get("agente_id") or "").strip()
        q_sede = (request.args.get("sede") or "").strip()
        q_tipo = (request.args.get("tipo") or "").strip()
        q_estado = (request.args.get("estado") or "").strip()
        q_categoria = (request.args.get("categoria") or "").strip()
        q_prioridad = (request.args.get("prioridad") or "").strip()
        q_buscar = (request.args.get("q") or "").strip()

        sedes = con.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        agentes_sst = con.execute("""
            SELECT id, agente, rubro
            FROM agentes_intendencia
            WHERE COALESCE(activo, 1) = 1
            ORDER BY agente
        """).fetchall()

        agente_sst_sel = None
        entregas_epp_sst = []
        incidentes_sst = []

        sst_total_personal = 0
        sst_relevados_personal = 0
        sst_pct_alcance = "0%"
        sst_pct_riesgo = "0%"
        sst_pct_documental = "0%"

        def _fmt_pct(v):
            try:
                vv = float(v or 0)
            except Exception:
                vv = 0.0
            if vv <= 0:
                return "0%"
            if vv >= 100:
                return "100%"
            return f"{vv:.1f}%"

        try:
            sync_sst_ergonomia_from_personal(con)
            ergo_tot_row = con.execute("SELECT COUNT(*) AS total FROM sst_ergonomia").fetchone()
            ergo_rel_row = con.execute(
                """
                SELECT COUNT(*) AS total
                FROM sst_ergonomia
                WHERE COALESCE(edad, 0) > 0
                  AND (
                    COALESCE(puntuacion_salud, 0) > 0
                    OR (
                      TRIM(COALESCE(descripcion_salud, '')) <> ''
                      AND TRIM(COALESCE(descripcion_salud, '')) <> '-'
                    )
                  )
                """
            ).fetchone()
            sst_total_personal = int((ergo_tot_row["total"] if ergo_tot_row else 0) or 0)
            sst_relevados_personal = int((ergo_rel_row["total"] if ergo_rel_row else 0) or 0)
        except Exception:
            sst_total_personal = 0
            sst_relevados_personal = 0

        if sst_total_personal > 0:
            sst_pct_alcance = "100%"
            sst_pct_riesgo = _fmt_pct((sst_relevados_personal * 100.0) / sst_total_personal)

        if q_agente_id.isdigit():
            agente_sst_sel = con.execute("""
                SELECT id, agente, rubro, dias_feria
                FROM agentes_intendencia
                WHERE id = ?
            """, (int(q_agente_id),)).fetchone()

            if agente_sst_sel:
                entregas_epp_sst = con.execute("""
                    SELECT id, tipo, fecha_entrega, cantidad, estado
                    FROM agentes_epp
                    WHERE agente_id = ?
                    ORDER BY fecha_entrega DESC, id DESC
                    LIMIT 20
                """, (agente_sst_sel["id"],)).fetchall()

                incidentes_sst = con.execute("""
                    SELECT id, fecha, tipo, estado
                    FROM agentes_incidentes
                    WHERE agente_id = ?
                    ORDER BY fecha DESC, id DESC
                    LIMIT 20
                """, (agente_sst_sel["id"],)).fetchall()

        if request.method == "POST":
            fecha = (request.form.get("fecha") or "").strip()
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            tipo = (request.form.get("tipo") or "").strip()
            categoria = (request.form.get("categoria") or "").strip()
            area = (request.form.get("area") or "").strip()
            titulo = (request.form.get("titulo") or "").strip()
            detalle = (request.form.get("detalle") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            prioridad = (request.form.get("prioridad") or "").strip()
            responsable = (request.form.get("responsable") or "").strip()
            accion_correctiva = (request.form.get("accion_correctiva") or "").strip()
            evidencia_url = (request.form.get("evidencia_url") or "").strip()
            fecha_objetivo = (request.form.get("fecha_objetivo") or "").strip()
            fecha_cierre = (request.form.get("fecha_cierre") or "").strip()

            if not fecha or not tipo:
                flash("Fecha y tipo son obligatorios.", "error")
                return redirect(url_for("sst_general"))

            if sede_codigo == "":
                sede_codigo = None

            con.execute("""
                INSERT INTO sst_general (
                    fecha, sede_codigo, tipo,
                    categoria, area,
                    titulo, detalle,
                    estado, prioridad, responsable,
                    accion_correctiva, evidencia_url,
                    fecha_objetivo, fecha_cierre
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fecha,
                sede_codigo,
                tipo,
                categoria or None,
                area or None,
                titulo or None,
                detalle or None,
                estado or None,
                prioridad or None,
                responsable or None,
                accion_correctiva or None,
                evidencia_url or None,
                fecha_objetivo or None,
                fecha_cierre or None,
            ))
            con.commit()
            con.close()
            rebuild_eventos_sst()
            flash("Registro SST guardado.", "success")
            return redirect(url_for("sst_general"))

        where = []
        params = []
        if q_sede:
            where.append("s.sede_codigo = ?")
            params.append(q_sede)
        if q_tipo:
            where.append("s.tipo = ?")
            params.append(q_tipo)
        if q_estado:
            where.append("s.estado = ?")
            params.append(q_estado)
        if q_categoria:
            where.append("s.categoria = ?")
            params.append(q_categoria)
        if q_prioridad:
            where.append("s.prioridad = ?")
            params.append(q_prioridad)
        if q_buscar:
            like = f"%{q_buscar}%"
            where.append("""
                (
                  COALESCE(s.titulo,'') LIKE ?
                  OR COALESCE(s.detalle,'') LIKE ?
                  OR COALESCE(s.responsable,'') LIKE ?
                  OR COALESCE(s.accion_correctiva,'') LIKE ?
                )
            """)
            params.extend([like, like, like, like])

        sql = """
            SELECT
                s.id, s.fecha, s.sede_codigo, s.tipo,
                s.categoria, s.area,
                s.titulo, s.detalle,
                s.estado, s.prioridad, s.responsable,
                s.accion_correctiva, s.evidencia_url,
                s.fecha_objetivo, s.fecha_cierre,
                sm.nombre AS sede_nombre
            FROM sst_general s
            LEFT JOIN sedes_mpd sm ON sm.codigo = s.sede_codigo
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY s.fecha DESC, s.id DESC"

        sst_registros = con.execute(sql, params).fetchall()

        sst_ops_pendientes = 0
        for r in sst_registros:
            try:
                t = (r["tipo"] or "").strip().lower()
                e = (r["estado"] or "").strip().upper()
            except Exception:
                t, e = "", ""
            if t == "no_conformidad" and e != "CERRADO":
                sst_ops_pendientes += 1

        # SG-SST documental interno (6 tarjetas)
        sgsst_cards = {}
        try:
            seed_sgsst_documentacion(con)
            placeholders = ",".join(["?"] * len(SGSST_BLOQUES_VALIDOS))
            rows_docs = con.execute(
                f"""
                SELECT bloque, contenido, activo, responsable
                FROM sgsst_documentos
                WHERE bloque IN ({placeholders})
                ORDER BY orden_visual, id
                """,
                SGSST_BLOQUES_VALIDOS,
            ).fetchall()
            by_bloque = {}
            for rr in rows_docs or []:
                bb = (rr["bloque"] or "").strip().lower()
                if bb and bb not in by_bloque:
                    by_bloque[bb] = rr

            estado_prot = _sgsst_estado_por_base(con, "sgsst_protocolos", [x["codigo"] for x in SGSST_PROTOCOLOS_BASE])
            estado_ins = _sgsst_estado_por_base(con, "sgsst_instructivos", [x["codigo"] for x in SGSST_INSTRUCTIVOS_BASE])

            for bb in SGSST_BLOQUES_VALIDOS:
                rr = by_bloque.get(bb)
                responsable_card = ""
                contenido_card = ""
                activo_card = 0
                if rr:
                    responsable_card = (rr["responsable"] or "").strip()
                    contenido_card = rr["contenido"]
                    activo_card = rr["activo"]

                if bb == "protocolos":
                    auto = estado_prot
                elif bb == "instructivos":
                    auto = estado_ins
                else:
                    auto = _sgsst_estado_bloque(contenido_card, activo_card)

                sgsst_cards[bb] = {
                    "responsable": responsable_card,
                    "estado_label": auto.get("label") or "Pendiente",
                    "estado_cls": auto.get("cls") or "pending",
                    "estado_detalle": auto.get("detalle") or "",
                }
        except Exception:
            sgsst_cards = {}

        con.close()

        return render_template(
            "sst_general.html",
            sedes=sedes,
            sst_registros=sst_registros,
            agentes_sst=agentes_sst,
            agente_sst_sel=agente_sst_sel,
            entregas_epp_sst=entregas_epp_sst,
            incidentes_sst=incidentes_sst,
            q_agente_id=q_agente_id,
            q_sede=q_sede,
            q_tipo=q_tipo,
            q_estado=q_estado,
            q_categoria=q_categoria,
            q_prioridad=q_prioridad,
            sst_total_personal=sst_total_personal,
            sst_relevados_personal=sst_relevados_personal,
            sst_pct_alcance=sst_pct_alcance,
            sst_pct_riesgo=sst_pct_riesgo,
            sst_pct_documental=sst_pct_documental,
            sst_ops_pendientes=sst_ops_pendientes,
            q_buscar=q_buscar,
            sgsst_cards=sgsst_cards,
        )

    @app.route("/sst/<int:sst_id>/eliminar", methods=["POST"], endpoint="sst_general_eliminar")
    def sst_general_eliminar(sst_id):
        con = get_db()
        ensure_sst_general_table(con)
        con.execute("DELETE FROM sst_general WHERE id = ?", (sst_id,))
        con.commit()
        con.close()
        flash("Registro SST eliminado.", "success")
        return redirect(url_for("sst_general"))

    @app.route("/sst/<int:sst_id>/editar", methods=["GET", "POST"], endpoint="sst_general_editar")
    def sst_general_editar(sst_id):
        con = get_db()
        ensure_sst_general_table(con)

        sedes = con.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        registro = con.execute("""
            SELECT *
            FROM sst_general
            WHERE id = ?
        """, (sst_id,)).fetchone()

        if not registro:
            con.close()
            flash("Registro SST no encontrado.", "warning")
            return redirect(url_for("sst_general"))

        if request.method == "POST":
            fecha = (request.form.get("fecha") or "").strip()
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            tipo = (request.form.get("tipo") or "").strip()
            categoria = (request.form.get("categoria") or "").strip()
            area = (request.form.get("area") or "").strip()
            titulo = (request.form.get("titulo") or "").strip()
            detalle = (request.form.get("detalle") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            prioridad = (request.form.get("prioridad") or "").strip()
            responsable = (request.form.get("responsable") or "").strip()
            accion_correctiva = (request.form.get("accion_correctiva") or "").strip()
            evidencia_url = (request.form.get("evidencia_url") or "").strip()
            fecha_objetivo = (request.form.get("fecha_objetivo") or "").strip()
            fecha_cierre = (request.form.get("fecha_cierre") or "").strip()

            if not fecha or not tipo:
                con.close()
                flash("Fecha y tipo son obligatorios.", "error")
                return redirect(url_for("sst_general_editar", sst_id=sst_id))

            if sede_codigo == "":
                sede_codigo = None

            con.execute("""
                UPDATE sst_general
                SET fecha = ?,
                    sede_codigo = ?,
                    tipo = ?,
                    categoria = ?,
                    area = ?,
                    titulo = ?,
                    detalle = ?,
                    estado = ?,
                    prioridad = ?,
                    responsable = ?,
                    accion_correctiva = ?,
                    evidencia_url = ?,
                    fecha_objetivo = ?,
                    fecha_cierre = ?
                WHERE id = ?
            """, (
                fecha,
                sede_codigo,
                tipo,
                categoria,
                area,
                titulo,
                detalle,
                estado,
                prioridad,
                responsable,
                accion_correctiva,
                evidencia_url,
                fecha_objetivo,
                fecha_cierre,
                sst_id,
            ))
            con.commit()
            con.close()
            rebuild_eventos_sst()
            flash("Registro SST actualizado.", "success")
            return redirect(url_for("sst_general"))

        con.close()
        return render_template(
            "sst_general_editar.html",
            sedes=sedes,
            r=registro
        )

    def _seed_sst_control_objetivos(con):
        rows = con.execute("SELECT COUNT(1) AS n FROM sst_control_objetivos").fetchone()
        if rows and rows["n"] > 0:
            return
        defaults = [
            "Carteleria",
            "Ubicacion de matafuegos",
            "Luces de emergencia",
        ]
        for nombre in defaults:
            con.execute("INSERT INTO sst_control_objetivos (nombre) VALUES (?)", (nombre,))
        con.commit()

    def _sst_parse_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None

    def _sst_month_ticks(range_start, range_end):
        if not range_start or not range_end:
            return []
        total_days = (range_end - range_start).days + 1
        if total_days <= 0:
            return []
        ticks = []
        cur = date(range_start.year, range_start.month, 1)
        months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        while cur <= range_end:
            left = (cur - range_start).days / total_days * 100
            label = f"{months[cur.month - 1]} {cur.year}"
            ticks.append({"label": label, "left": round(left, 2)})
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return ticks

    def _sst_bar(range_start, range_end, start_date, end_date):
        if not range_start or not range_end or not start_date or not end_date:
            return None, None
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        total_days = (range_end - range_start).days + 1
        if total_days <= 0:
            return None, None
        start_off = max(0, (start_date - range_start).days)
        end_off = min((end_date - range_start).days, total_days - 1)
        left = start_off / total_days * 100
        width = (end_off - start_off + 1) / total_days * 100
        return round(left, 2), round(width, 2)

    def _sst_plan_redirect_next():
        return_to = (request.args.get("next") or request.form.get("next") or "").strip().lower()
        if return_to == "cargar":
            return redirect(url_for("sst_plan_cargar"))
        return redirect(url_for("sst_plan"))

    ERGO_DESC_OPTIONS = [
        "Puesto completo de oficina",
        "Silla",
        "Escritorio",
        "Teclado y raton",
        "Monitor",
        "Computadora portatil",
        "Objetos de uso frecuente",
        "Telefono",
        "Pausas activas y movilidad",
    ]
    ERGO_SILLA_OPTIONS = [
        "Silla ergonomica",
        "Silla fija",
        "Silla giratoria",
    ]
    ERGO_ESCRITORIO_OPTIONS = [
        "Escritorio de PC solo",
        "Mesa de PC",
        "Escritorio profesional en L",
        "Escritorio doble (L con dos superficies)",
    ]
    ERGO_SOPORTE_OPTIONS = [
        "Con soporte de monitor",
        "Sin soporte de monitor",
    ]
    ERGO_ALTURA_MONITOR_OPTIONS = [
        "Altura correcta (a nivel de ojos)",
        "Monitor bajo",
        "Monitor alto",
    ]
    ERGO_ESPACIO_PIERNAS_OPTIONS = [
        "Espacio adecuado",
        "Espacio reducido",
        "Espacio insuficiente",
    ]
    ERGO_AJUSTE_ALTURA_OPTIONS = [
        "No requiere ajuste",
        "Subir monitor o escritorio",
        "Bajar monitor o escritorio",
    ]
    ERGO_NOTEBOOK_OPTIONS = [
        "No",
        "Si, con base o soporte",
        "Si, sin base o soporte",
    ]
    ERGO_INTERVENCION_OPTIONS = [
        "Ninguna",
        "Ajuste monitor",
        "Cambio silla",
        "Reubicacion",
        "Capacitacion",
        "Control administrativo",
    ]
    ERGO_SALUD_OPTIONS = [
        {"label": "Sin molestias", "score": 0},
        {"label": "Molestias leves", "score": 1},
        {"label": "Molestias frecuentes", "score": 3},
        {"label": "Restriccion medica", "score": 4},
    ]
    ERGO_SGI_FLOW_STATES = [
        "Programado",
        "Relevado",
        "Riesgo evaluado",
        "Recomendacion emitida",
        "Implementado",
        "Verificado",
        "Cerrado",
    ]
    ERGO_ACCION_OPTIONS = [
        "Urgente",
        "Programado",
        "No requiere atencion",
        "Cerrado",
    ]

    def _safe_int(value, default=0):
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def _safe_float(value, default=0.0):
        try:
            return float(str(value).strip().replace(',', '.'))
        except Exception:
            return default

    def _calc_age_from_birthdate(value):
        if not value:
            return None
        s = str(value).strip()
        born = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                born = datetime.strptime(s, fmt).date()
                break
            except Exception:
                continue
        if not born:
            return None
        today = date.today()
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if years < 0 or years > 120:
            return None
        return years

    def _ergo_age_score(age_value):
        age = _safe_int(age_value, 0)
        if age <= 0:
            return 0
        if age >= 60:
            return 3
        if age >= 50:
            return 2
        if age >= 40:
            return 1
        return 0

    def _ergo_build_audit_alerts(payload):
        alerts = []
        if not (payload.get("fecha_relevamiento") or "").strip():
            alerts.append("Falta fecha de relevamiento.")
        if not (payload.get("evaluador") or "").strip():
            alerts.append("Falta evaluador.")
        if _safe_int(payload.get("horas_pc"), 0) <= 0:
            alerts.append("Horas diarias en PC no informadas.")
        if (payload.get("uso_notebook") or "").strip() == "Si, sin base o soporte":
            alerts.append("Uso de notebook sin base o soporte.")
        if (payload.get("accion_tomar") or "").strip().lower() == "urgente" and not (payload.get("responsable") or "").strip():
            alerts.append("Accion urgente sin responsable asignado.")
        if (payload.get("altura_monitor") or "").strip() in ("Monitor bajo", "Monitor alto") and (payload.get("ajuste_altura") or "").strip() == "No requiere ajuste":
            alerts.append("Incoherencia: monitor fuera de altura y ajuste en 'No requiere ajuste'.")
        return alerts

    def _ergo_next_flow_state(payload):
        verificado = _safe_int(payload.get("verificado"), 0) == 1
        fecha_verificacion = (payload.get("fecha_verificacion") or "").strip()
        fecha_implementacion = (payload.get("fecha_implementacion") or "").strip()
        observaciones = (payload.get("observaciones") or "").strip()
        fecha_relevamiento = (payload.get("fecha_relevamiento") or "").strip()
        intervencion_realizada = (payload.get("intervencion_realizada") or "").strip().lower()

        if verificado and fecha_verificacion:
            if (payload.get("accion_tomar") or "").strip().lower() == "no requiere atencion":
                return "Cerrado"
            return "Verificado"
        if (payload.get("accion_tomar") or "").strip().lower() == "cerrado":
            return "Cerrado"
        if fecha_implementacion:
            return "Implementado"
        if intervencion_realizada and intervencion_realizada != "ninguna":
            return "Recomendacion emitida"
        if observaciones:
            return "Recomendacion emitida"
        if fecha_relevamiento:
            return "Riesgo evaluado"
        return "Programado"

    def _ergo_action_class(action):
        a = (action or '').strip().lower()
        if a == 'urgente':
            return 'urgente'
        if a == 'programado':
            return 'programado'
        if a == 'no requiere atencion':
            return 'ok'
        if a == 'cerrado':
            return 'ok'
        return 'otro'

    def _ergo_action_label(action):
        a = (action or '').strip().lower()
        if a == 'no requiere atencion':
            return 'Condicion adecuada'
        return action or '-'

    def _ergo_risk_flags(payload):
        flags = []
        edad = _safe_int(payload.get("edad"), 0)
        if edad >= 70:
            flags.append("Edad mayor o igual a 70")
        elif edad >= 60:
            flags.append("Edad mayor a 60")
        if _safe_int(payload.get("horas_pc"), 0) > 6:
            flags.append("Exposicion mayor a 6 horas en PC")
        if _safe_int(payload.get("puntuacion_puesto"), 0) >= 4:
            flags.append("Puntaje de puesto alto")
        if (payload.get("accion_tomar") or "").strip().lower() == "urgente":
            flags.append("Caso marcado como urgente")
        return flags

    def _ergo_total_score(punt_edad, punt_puesto, punt_salud):
        return _safe_int(punt_edad, 0) + _safe_int(punt_puesto, 0) + _safe_int(punt_salud, 0)

    def _ergo_semaforo(total_score):
        if total_score >= 7:
            return "alto"
        if total_score >= 4:
            return "medio"
        return "bajo"

    def _ergo_motivos_riesgo(payload):
        motivos = []
        if (payload.get("altura_monitor") or "").strip() in ("Monitor bajo", "Monitor alto"):
            motivos.append("Altura monitor")
        if (payload.get("espacio_piernas") or "").strip() in ("Espacio reducido", "Espacio insuficiente"):
            motivos.append("Espacio reducido")
        if (payload.get("tipo_silla") or "").strip() in ("Silla fija",):
            motivos.append("Silla inadecuada")
        if _safe_int(payload.get("edad"), 0) >= 60:
            motivos.append("Edad")
        if (payload.get("uso_notebook") or "").strip() == "Si, sin base o soporte":
            motivos.append("Notebook sin base")
        return motivos

    def _ergo_recommended_pyramid_level(payload):
        intervencion = (payload.get("intervencion_realizada") or "").strip().lower()
        if "administr" in intervencion or "capacit" in intervencion:
            return 4
        if any(k in intervencion for k in ("ajuste", "silla", "reubic")):
            return 3
        return 0

    def _ergo_ui_state_and_step(estado_flujo):
        estado = (estado_flujo or "").strip().lower()
        if estado in ("programado", "relevado"):
            return ("Pendiente relevamiento", 1)
        if estado == "riesgo evaluado":
            return ("Evaluado", 2)
        if estado == "recomendacion emitida":
            return ("En implementacion", 3)
        if estado == "implementado":
            return ("Implementado", 3)
        if estado == "verificado":
            return ("Verificado", 3)
        if estado == "cerrado":
            return ("Cerrado", 3)
        return ("Pendiente relevamiento", 1)

    def _ergo_days_since(fecha_iso):
        try:
            d = datetime.strptime((fecha_iso or "").strip(), "%Y-%m-%d").date()
            return max(0, (date.today() - d).days)
        except Exception:
            return None

    def _clamp(x, a, b):
        return max(a, min(b, x))

    def _pro_expo_0_100(horas_pc):
        h = _safe_int(horas_pc, 0)
        if h <= 3:
            return 25
        if h <= 5:
            return 50
        if h <= 7:
            return 75
        return 100

    def _pro_edad_pts(edad):
        e = _safe_int(edad, 0)
        if e < 40:
            return 10
        if e < 50:
            return 25
        if e < 60:
            return 45
        if e < 70:
            return 70
        return 90

    def _pro_salud_pts(puntaje_salud):
        # Escala interna actual aprox 0..4 -> 0..100
        return _clamp(_safe_int(puntaje_salud, 0) * 25, 0, 100)

    def _pro_nivel_por_score(score):
        if score is None:
            return "PENDIENTE"
        if score >= 70:
            return "URGENTE"
        if score >= 50:
            return "RIESGO"
        if score >= 25:
            return "PROGRAMADO"
        return "CONDICION_ADECUADA"

    def _pro_subir_un_nivel(n):
        if n == "CONDICION_ADECUADA":
            return "PROGRAMADO"
        if n == "PROGRAMADO":
            return "RIESGO"
        if n == "RIESGO":
            return "URGENTE"
        return n

    def _pro_score_parallel(payload):
        # Derivamos sistema/mobiliario desde lo que ya existe hoy, sin exigir nueva UI.
        puntaje_puesto = _safe_int(payload.get("puntaje_puesto"), 0)
        puntaje_sistema = _safe_int(payload.get("puntaje_sistema"), 0)
        puntaje_mobiliario = _safe_int(payload.get("puntaje_mobiliario"), 0)
        puntaje_salud = _safe_int(payload.get("puntaje_salud"), 0)
        horas_pc = _safe_int(payload.get("horas_pc"), 0)
        edad = _safe_int(payload.get("edad"), 0)
        usa_notebook = 1 if (payload.get("usa_notebook") or "").strip() == "Si, sin base o soporte" else 0
        dolor_reportado = 1 if _safe_int(payload.get("dolor_reportado"), 0) == 1 else 0
        restriccion_medica = 1 if _safe_int(payload.get("restriccion_medica"), 0) == 1 else 0

        faltan_clave = (puntaje_puesto <= 0 and puntaje_sistema <= 0 and puntaje_mobiliario <= 0)
        if faltan_clave:
            return {
                "condicion_0_100": None,
                "expo_0_100": None,
                "vulner_0_100": None,
                "score_final": None,
                "condicion_riesgo": "PENDIENTE",
                "motivos": ["Faltan datos para calculo"],
            }

        condicion_0_100 = _clamp((puntaje_puesto * 12) + (puntaje_sistema * 8) + (puntaje_mobiliario * 5), 0, 100)
        expo_0_100 = _pro_expo_0_100(horas_pc)
        edad_pts = _pro_edad_pts(edad)
        salud_pts = _pro_salud_pts(puntaje_salud)
        banderas = 0
        if dolor_reportado:
            banderas += 40
        if restriccion_medica:
            banderas += 60
        if usa_notebook and horas_pc >= 4:
            banderas += 15
        vulner_0_100 = _clamp((0.45 * edad_pts) + (0.55 * salud_pts) + banderas, 0, 100)

        score_final = round((0.55 * condicion_0_100) + (0.25 * expo_0_100) + (0.20 * vulner_0_100), 2)
        nivel = _pro_nivel_por_score(score_final)
        if vulner_0_100 >= 70:
            nivel = _pro_subir_un_nivel(nivel)
        if restriccion_medica:
            nivel = "URGENTE"
        elif dolor_reportado and nivel == "PROGRAMADO":
            nivel = "RIESGO"

        motivos = _ergo_motivos_riesgo({
            "altura_monitor": payload.get("altura_monitor"),
            "espacio_piernas": payload.get("espacio_piernas"),
            "tipo_silla": payload.get("tipo_silla"),
            "edad": edad,
            "uso_notebook": payload.get("usa_notebook"),
        })
        if horas_pc >= 6:
            motivos.append("Exposicion alta (horas PC)")
        if puntaje_salud >= 3:
            motivos.append("Factor salud")

        return {
            "condicion_0_100": round(condicion_0_100, 2),
            "expo_0_100": round(expo_0_100, 2),
            "vulner_0_100": round(vulner_0_100, 2),
            "score_final": score_final,
            "condicion_riesgo": nivel,
            "motivos": motivos[:6],
        }

    def _salud_score_from_desc(desc):
        d = (desc or "").strip().lower()
        for op in ERGO_SALUD_OPTIONS:
            if d == op["label"].strip().lower():
                return int(op["score"])
        return 0

    def _accion_from_pro_bucket(bucket):
        b = (bucket or "").strip().upper()
        if b == "CONDICION_ADECUADA":
            return "No requiere atencion"
        if b == "PROGRAMADO":
            return "Programado"
        if b in ("RIESGO", "URGENTE"):
            return "Urgente"
        return "Programado"

    def ensure_sst_ergonomia_table(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_ergonomia(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personal_id INTEGER NOT NULL UNIQUE,
                codigo_sede TEXT NOT NULL,
                nombre_apellido TEXT NOT NULL,
                edad INTEGER DEFAULT 0,
                correo TEXT,
                descripcion_puesto TEXT DEFAULT 'Puesto completo de oficina',
                tipo_silla TEXT DEFAULT 'Silla fija',
                tipo_escritorio TEXT DEFAULT 'Escritorio de PC solo',
                soporte_monitor TEXT DEFAULT 'Sin soporte de monitor',
                oficina TEXT,
                puntuacion_puesto INTEGER DEFAULT 0,
                descripcion_salud TEXT,
                puntuacion_salud INTEGER DEFAULT 0,
                promedio REAL DEFAULT 0,
                accion_tomar TEXT DEFAULT 'Programado',
                observaciones TEXT,
                actualizado_en TEXT DEFAULT (datetime('now'))
            )
        """)
        ensure_cols(con, "sst_ergonomia", [
            ("altura_monitor", "TEXT"),
            ("espacio_piernas", "TEXT"),
            ("ajuste_altura", "TEXT"),
            ("horas_pc", "INTEGER"),
            ("uso_notebook", "TEXT"),
            ("fecha_relevamiento", "TEXT"),
            ("evaluador", "TEXT"),
            ("fecha_nacimiento", "TEXT"),
            ("puntuacion_edad", "INTEGER"),
            ("estado_flujo", "TEXT"),
            ("fecha_implementacion", "TEXT"),
            ("responsable", "TEXT"),
            ("evidencia_url", "TEXT"),
            ("fecha_verificacion", "TEXT"),
            ("verificado", "INTEGER"),
            ("audit_alertas", "TEXT"),
            ("intervencion_realizada", "TEXT"),
            ("fecha_cierre", "TEXT"),
            ("fecha_recordatorio", "TEXT"),
            ("pro_condicion_0_100", "REAL"),
            ("pro_expo_0_100", "REAL"),
            ("pro_vulner_0_100", "REAL"),
            ("pro_score_final", "REAL"),
            ("pro_condicion_riesgo", "TEXT"),
            ("pro_motivos", "TEXT"),
            ("salud_evaluador", "TEXT"),
            ("salud_fecha", "TEXT"),
        ])
        con.commit()

    def ensure_sst_ergonomia_historial_table(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_ergonomia_historial(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personal_id INTEGER NOT NULL,
                fecha_evento TEXT DEFAULT (datetime('now')),
                usuario_cambio TEXT,
                accion_tomar TEXT,
                puntuacion_puesto INTEGER,
                promedio REAL,
                evaluador TEXT,
                fecha_relevamiento TEXT,
                observaciones TEXT,
                cambios_json TEXT,
                snapshot_json TEXT
            )
        """)
        ensure_cols(con, "sst_ergonomia_historial", [
            ("usuario_cambio", "TEXT"),
            ("cambios_json", "TEXT"),
        ])
        con.commit()

    def sync_sst_ergonomia_from_personal(con):
        ensure_sst_ergonomia_table(con)
        ensure_sst_ergonomia_historial_table(con)
        personal_rows = con.execute("""
            SELECT
                MIN(id) AS id,
                codigo_sede,
                nombre_apellido,
                COALESCE(email_admin, '') AS correo
            FROM personal_sede
            WHERE COALESCE(activo, 1) = 1
            GROUP BY
                codigo_sede,
                nombre_apellido,
                COALESCE(email_admin, '')
            ORDER BY codigo_sede, nombre_apellido
        """).fetchall()

        active_ids = []
        for p in personal_rows:
            pid = p['id']
            active_ids.append(pid)
            con.execute("""
                INSERT OR IGNORE INTO sst_ergonomia (
                    personal_id, codigo_sede, nombre_apellido, correo
                ) VALUES (?, ?, ?, ?)
            """, (pid, p['codigo_sede'], p['nombre_apellido'], p['correo']))
            con.execute("""
                UPDATE sst_ergonomia
                SET codigo_sede = ?,
                    nombre_apellido = ?,
                    correo = CASE
                        WHEN correo IS NULL OR TRIM(correo) = '' THEN ?
                        ELSE correo
                    END
                WHERE personal_id = ?
            """, (p['codigo_sede'], p['nombre_apellido'], p['correo'], pid))

        if active_ids:
            placeholders = ','.join(['?'] * len(active_ids))
            con.execute(f"DELETE FROM sst_ergonomia WHERE personal_id NOT IN ({placeholders})", active_ids)
        else:
            con.execute('DELETE FROM sst_ergonomia')
        con.commit()

    def build_ergonomia_context(con, sedes):
        sync_sst_ergonomia_from_personal(con)
        ergo_sede = (request.args.get('ergo_sede') or '').strip().upper()
        ergo_personal_id = _safe_int(request.args.get('ergo_personal_id'), 0)

        where = ''
        params = []
        if ergo_sede:
            where = 'WHERE codigo_sede = ?'
            params = [ergo_sede]

        rows = con.execute(f"""
            SELECT *
            FROM sst_ergonomia
            {where}
            ORDER BY codigo_sede, nombre_apellido
        """, params).fetchall()

        data_rows = []
        seen_people = set()
        counts = {'urgente': 0, 'programado': 0, 'ok': 0, 'otro': 0}
        prom_vals = []
        for r in rows:
            d = dict(r)
            dedup_key = (
                (d.get('codigo_sede') or '').strip().upper(),
                (d.get('nombre_apellido') or '').strip().upper(),
                (d.get('correo') or '').strip().lower(),
            )
            if dedup_key in seen_people:
                continue
            seen_people.add(dedup_key)
            d['accion_class'] = _ergo_action_class(d.get('accion_tomar'))
            d['accion_label'] = _ergo_action_label(d.get('accion_tomar'))
            edad_calc = _calc_age_from_birthdate(d.get('fecha_nacimiento'))
            if edad_calc is not None:
                d['edad'] = edad_calc
            d['nombre'] = d.get('nombre_apellido') or '-'
            d['punt_edad'] = _safe_int(d.get('puntuacion_edad'), _ergo_age_score(d.get('edad')))
            d['desc_puesto'] = d.get('descripcion_puesto') or '-'
            d['punt_puesto'] = d.get('puntuacion_puesto') or 0
            d['desc_salud'] = d.get('descripcion_salud') or '-'
            d['punt_salud'] = d.get('puntuacion_salud') or 0
            d['accion'] = d.get('accion_tomar') or '-'
            if not (d.get('estado_flujo') or '').strip():
                d['estado_flujo'] = _ergo_next_flow_state(d)
            d['total_score'] = _ergo_total_score(d.get('punt_edad'), d.get('punt_puesto'), d.get('punt_salud'))
            d['semaforo'] = _ergo_semaforo(d['total_score'])
            d['dias_desde_eval'] = _ergo_days_since(d.get('fecha_relevamiento'))
            d['motivos_riesgo'] = _ergo_motivos_riesgo(d)
            d['caso_prioritario'] = (len(d['motivos_riesgo']) >= 2) or (d['semaforo'] == 'alto')
            d['risk_flags'] = _ergo_risk_flags({
                "edad": d.get("edad"),
                "horas_pc": d.get("horas_pc"),
                "puntuacion_puesto": d.get("puntuacion_puesto"),
                "accion_tomar": d.get("accion_tomar"),
            })
            d['promedio_pendiente'] = not (
                _safe_int(d.get('edad'), 0) > 0 and (
                    _safe_int(d.get('puntuacion_salud'), 0) > 0 or (d.get('descripcion_salud') or '').strip()
                )
            )
            if d['promedio_pendiente']:
                d['promedio'] = None
            counts[d['accion_class']] += 1
            try:
                if d.get('promedio') is not None and str(d.get('promedio')).strip() != '':
                    prom_vals.append(float(d.get('promedio')))
            except Exception:
                pass
            data_rows.append(d)

        ergo_selected = None
        if data_rows:
            if ergo_personal_id:
                for item in data_rows:
                    if int(item.get('personal_id') or 0) == ergo_personal_id:
                        ergo_selected = item
                        break
            if ergo_selected is None:
                ergo_selected = data_rows[0]
                ergo_personal_id = int(ergo_selected.get('personal_id') or 0)
            ergo_selected['risk_flags'] = _ergo_risk_flags({
                "edad": ergo_selected.get("edad"),
                "horas_pc": ergo_selected.get("horas_pc"),
                "puntuacion_puesto": ergo_selected.get("puntuacion_puesto"),
                "accion_tomar": ergo_selected.get("accion_tomar"),
            })

        promedio_general = round(sum(prom_vals) / len(prom_vals), 2) if prom_vals else 0
        return {
            'ergo_sede': ergo_sede,
            'ergonomia_rows': data_rows,
            'ergonomia_total': len(data_rows),
            'ergonomia_urgente': counts['urgente'],
            'ergonomia_programado': counts['programado'],
            'ergonomia_sin_atencion': counts['ok'],
            'ergonomia_otros': counts['otro'],
            'ergonomia_promedio_general': promedio_general,
            'ergonomia_loaded': len(data_rows) > 0,
            'ergonomia_error': '',
            'ergo_desc_options': ERGO_DESC_OPTIONS,
            'ergo_silla_options': ERGO_SILLA_OPTIONS,
            'ergo_escritorio_options': ERGO_ESCRITORIO_OPTIONS,
            'ergo_soporte_options': ERGO_SOPORTE_OPTIONS,
            'ergo_altura_monitor_options': ERGO_ALTURA_MONITOR_OPTIONS,
            'ergo_espacio_piernas_options': ERGO_ESPACIO_PIERNAS_OPTIONS,
            'ergo_ajuste_altura_options': ERGO_AJUSTE_ALTURA_OPTIONS,
            'ergo_notebook_options': ERGO_NOTEBOOK_OPTIONS,
            'ergo_intervencion_options': ERGO_INTERVENCION_OPTIONS,
            'ergo_salud_options': ERGO_SALUD_OPTIONS,
            'ergo_accion_options': ERGO_ACCION_OPTIONS,
            'ergo_personal_id': ergo_personal_id,
            'ergo_selected': ergo_selected,
            'ergo_manual_url': (
                url_for('sst_ergonomia_manual')
                if 'sst_ergonomia_manual' in app.view_functions
                else None
            ),
            'ergo_gestion_url': (
                url_for('sst_ergonomia_gestion_riesgo')
                if 'sst_ergonomia_gestion_riesgo' in app.view_functions
                else None
            ),
            'ergo_sedes': [{'codigo': s['codigo'], 'nombre': s['nombre']} for s in sedes],
        }

    def ensure_sst_control_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_control_objetivos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                consolidado_ok INTEGER DEFAULT 0,
                decision_ok INTEGER DEFAULT 0,
                impl_compra_necesaria TEXT,
                impl_pedido TEXT,
                impl_recibido TEXT,
                impl_ejecucion TEXT,
                impl_colocacion TEXT,
                impl_pedido_fecha TEXT,
                impl_recibido_fecha TEXT,
                impl_ejecucion_fecha TEXT,
                impl_colocacion_fecha TEXT,
                eval_verificado TEXT,
                eval_observaciones TEXT,
                eval_cerrado TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sst_control_relevamientos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                objetivo_id INTEGER NOT NULL,
                sede_codigo TEXT NOT NULL,
                ok INTEGER DEFAULT 0,
                actualizado_en TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(objetivo_id) REFERENCES sst_control_objetivos(id)
            )
        """)
        con.commit()

    def build_sst_plan_context(show_carga=False, edit_obj=None, edit_acc=None, sst_view="all"):
        con = get_db()
        ensure_sst_plan_tables(con)
        ensure_sst_control_tables(con)
        _seed_sst_control_objetivos(con)

        try:
            sedes = con.execute("""
                SELECT codigo, nombre, fuero
                FROM sedes_mpd
                ORDER BY codigo
            """).fetchall()
        except Exception:
            sedes = con.execute("""
                SELECT codigo, nombre
                FROM sedes_mpd
                ORDER BY codigo
            """).fetchall()
        sedes_fueros = {}
        for s in sedes:
            try:
                sedes_fueros[s["codigo"]] = s["fuero"]
            except Exception:
                sedes_fueros[s["codigo"]] = ""
        sedes_control = []
        for s in sedes:
            try:
                sedes_control.append({"codigo": s["codigo"], "fuero": s.get("fuero", "")})
            except Exception:
                sedes_control.append({"codigo": s["codigo"], "fuero": ""})

        objetivos_rows = con.execute("""
            SELECT *
            FROM sst_objetivos
            ORDER BY id DESC
        """).fetchall()

        acciones_rows = con.execute("""
            SELECT *
            FROM sst_objetivo_acciones
            ORDER BY objetivo_id ASC, orden ASC, id ASC
        """).fetchall()

        acciones_by_obj = defaultdict(list)
        for a in acciones_rows:
            acciones_by_obj[a["objetivo_id"]].append(dict(a))

        objetivos = []
        total_cumplidos = 0
        total_en_curso = 0
        total_riesgo = 0

        for o in objetivos_rows:
            obj = dict(o)
            acciones = acciones_by_obj.get(o["id"], [])
            completed = 0
            total_avance = 0
            with_avance = 0
            for a in acciones:
                estado = (a.get("estado") or "").upper()
                avance = a.get("avance_pct")
                if avance is None:
                    avance = 100 if estado == "COMPLETADO" else 0
                try:
                    avance_val = int(avance)
                except Exception:
                    avance_val = 0
                a["avance_pct"] = avance_val
                if estado == "COMPLETADO" or avance_val >= 100:
                    completed += 1
                total_avance += avance_val
                with_avance += 1

            total_actions = len(acciones)
            progress_pct = int(round(total_avance / with_avance)) if with_avance else 0

            dates_start = []
            dates_end = []
            for a in acciones:
                d1 = _sst_parse_date(a.get("fecha_inicio"))
                d2 = _sst_parse_date(a.get("fecha_fin"))
                if d1:
                    dates_start.append(d1)
                if d2:
                    dates_end.append(d2)

            rango_start = min(dates_start) if dates_start else _sst_parse_date(o["fecha_inicio"])
            rango_end = max(dates_end) if dates_end else _sst_parse_date(o["fecha_fin"])
            if rango_start and rango_end and rango_end < rango_start:
                rango_start, rango_end = rango_end, rango_start
            month_ticks = _sst_month_ticks(rango_start, rango_end)

            for a in acciones:
                d1 = _sst_parse_date(a.get("fecha_inicio"))
                d2 = _sst_parse_date(a.get("fecha_fin"))
                if d1 and d2:
                    left, width = _sst_bar(rango_start, rango_end, d1, d2)
                    a["bar_left"] = left
                    a["bar_width"] = width
                else:
                    a["bar_left"] = None
                    a["bar_width"] = None

            obj["acciones"] = acciones
            obj["total_actions"] = total_actions
            obj["completed_actions"] = completed
            obj["progress_pct"] = max(0, min(progress_pct, 100))
            obj["range_start"] = rango_start
            obj["range_end"] = rango_end
            obj["month_ticks"] = month_ticks

            estado = (obj.get("estado") or "").upper()
            if estado == "CUMPLIDO":
                total_cumplidos += 1
            elif estado == "EN_RIESGO":
                total_riesgo += 1
            else:
                total_en_curso += 1

            objetivos.append(obj)

        control_rows = con.execute("""
            SELECT *
            FROM sst_control_objetivos
            ORDER BY id ASC
        """).fetchall()

        control_objetivos = []
        for o in control_rows:
            done = con.execute("""
                SELECT sede_codigo
                FROM sst_control_relevamientos
                WHERE objetivo_id = ? AND ok = 1
            """, (o["id"],)).fetchall()
            done_sedes = [r["sede_codigo"] for r in done]
            all_sedes = [s["codigo"] for s in sedes]
            missing_sedes = [c for c in all_sedes if c not in done_sedes]
            total_count = len(all_sedes)
            done_count = len(done_sedes)
            pct = int(round((done_count / total_count) * 100)) if total_count else 0
            if pct >= 80:
                pct_class = "ok"
            elif pct >= 40:
                pct_class = "warn"
            else:
                pct_class = "risk"

            consolidado_ok = bool(o["consolidado_ok"])
            decision_ok = bool(o["decision_ok"])

            min_sedes_impl = min(3, total_count) if total_count else 0
            threshold_unlocked = (done_count >= min_sedes_impl) if min_sedes_impl else False
            decision_ok_effective = decision_ok or consolidado_ok or threshold_unlocked
            auto_decision = decision_ok_effective and not decision_ok

            def _is_done_state(v):
                vv = str(v or "").strip().upper()
                return vv in ("?", "N/A", "NA", "OK")

            def _pct_class(v):
                if v >= 80:
                    return "ok"
                if v >= 40:
                    return "warn"
                return "risk"

            compra_nec = str(o["impl_compra_necesaria"] or "").strip().upper()
            impl_steps = ["impl_ejecucion", "impl_colocacion"] if compra_nec in ("NO", "N/A") else [
                "impl_pedido", "impl_recibido", "impl_ejecucion", "impl_colocacion"
            ]
            impl_done = sum(1 for key in impl_steps if _is_done_state(o[key]))
            impl_progress_pct = int(round((impl_done / len(impl_steps)) * 100)) if impl_steps else 0
            impl_progress_class = _pct_class(impl_progress_pct)

            eval_steps = ["eval_verificado", "eval_observaciones", "eval_cerrado"]
            eval_done = sum(1 for key in eval_steps if _is_done_state(o[key]))
            eval_progress_pct = int(round((eval_done / len(eval_steps)) * 100)) if eval_steps else 0
            eval_progress_class = _pct_class(eval_progress_pct)

            eval_ok_effective = decision_ok_effective and impl_progress_pct >= 100

            def _short_date(val):
                if not val:
                    return ""
                try:
                    return datetime.strptime(val, "%Y-%m-%d").strftime("%d/%m")
                except Exception:
                    return val

            control_objetivos.append({
                "id": o["id"],
                "nombre": o["nombre"],
                "done_count": done_count,
                "total_count": total_count,
                "done_sedes": done_sedes,
                "missing_sedes": missing_sedes,
                "pct": pct,
                "pct_class": pct_class,
                "consolidado_ok": consolidado_ok,
                "decision_ok": decision_ok,
                "decision_ok_effective": decision_ok_effective,
                "auto_decision": auto_decision,
                "min_sedes_impl": min_sedes_impl,
                "impl_progress_pct": impl_progress_pct,
                "impl_progress_class": impl_progress_class,
                "eval_progress_pct": eval_progress_pct,
                "eval_progress_class": eval_progress_class,
                "impl_compra_necesaria": o["impl_compra_necesaria"],
                "impl_pedido": o["impl_pedido"],
                "impl_recibido": o["impl_recibido"],
                "impl_ejecucion": o["impl_ejecucion"],
                "impl_colocacion": o["impl_colocacion"],
                "impl_pedido_fecha": o["impl_pedido_fecha"],
                "impl_recibido_fecha": o["impl_recibido_fecha"],
                "impl_ejecucion_fecha": o["impl_ejecucion_fecha"],
                "impl_colocacion_fecha": o["impl_colocacion_fecha"],
                "impl_pedido_fecha_short": _short_date(o["impl_pedido_fecha"]),
                "impl_recibido_fecha_short": _short_date(o["impl_recibido_fecha"]),
                "impl_ejecucion_fecha_short": _short_date(o["impl_ejecucion_fecha"]),
                "impl_colocacion_fecha_short": _short_date(o["impl_colocacion_fecha"]),
                "eval_verificado": o["eval_verificado"],
                "eval_observaciones": o["eval_observaciones"],
                "eval_cerrado": o["eval_cerrado"],
                "eval_ok_effective": eval_ok_effective,
            })

        ergonomia = build_ergonomia_context(con, sedes)
        con.close()

        return {
            "sedes": sedes,
            "sedes_fueros": sedes_fueros,
            "sedes_control": sedes_control,
            "objetivos": objetivos,
            "control_objetivos": control_objetivos,
            "total_obj": len(objetivos),
            "total_cumplidos": total_cumplidos,
            "total_en_curso": total_en_curso,
            "total_riesgo": total_riesgo,
            "ergonomia_rows": ergonomia.get("ergonomia_rows", []),
            "ergonomia_total": ergonomia.get("ergonomia_total", 0),
            "ergonomia_urgente": ergonomia.get("ergonomia_urgente", 0),
            "ergonomia_programado": ergonomia.get("ergonomia_programado", 0),
            "ergonomia_sin_atencion": ergonomia.get("ergonomia_sin_atencion", 0),
            "ergonomia_otros": ergonomia.get("ergonomia_otros", 0),
            "ergonomia_promedio_general": ergonomia.get("ergonomia_promedio_general", 0),
            "ergonomia_loaded": ergonomia.get("ergonomia_loaded", False),
            "ergonomia_error": ergonomia.get("ergonomia_error", ""),
            "ergo_desc_options": ergonomia.get("ergo_desc_options", ERGO_DESC_OPTIONS),
            "ergo_silla_options": ergonomia.get("ergo_silla_options", ERGO_SILLA_OPTIONS),
            "ergo_escritorio_options": ergonomia.get("ergo_escritorio_options", ERGO_ESCRITORIO_OPTIONS),
            "ergo_soporte_options": ergonomia.get("ergo_soporte_options", ERGO_SOPORTE_OPTIONS),
            "ergo_altura_monitor_options": ergonomia.get("ergo_altura_monitor_options", ERGO_ALTURA_MONITOR_OPTIONS),
            "ergo_espacio_piernas_options": ergonomia.get("ergo_espacio_piernas_options", ERGO_ESPACIO_PIERNAS_OPTIONS),
            "ergo_ajuste_altura_options": ergonomia.get("ergo_ajuste_altura_options", ERGO_AJUSTE_ALTURA_OPTIONS),
            "ergo_notebook_options": ergonomia.get("ergo_notebook_options", ERGO_NOTEBOOK_OPTIONS),
            "ergo_intervencion_options": ergonomia.get("ergo_intervencion_options", ERGO_INTERVENCION_OPTIONS),
            "ergo_salud_options": ergonomia.get("ergo_salud_options", ERGO_SALUD_OPTIONS),
            "ergo_accion_options": ergonomia.get("ergo_accion_options", ERGO_ACCION_OPTIONS),
            "ergo_manual_url": ergonomia.get("ergo_manual_url"),
            "ergo_gestion_url": ergonomia.get("ergo_gestion_url"),
            "ergo_sedes": ergonomia.get("ergo_sedes", []),
            "ergo_sede": ergonomia.get("ergo_sede", ""),
            "ergo_personal_id": ergonomia.get("ergo_personal_id", 0),
            "ergo_selected": ergonomia.get("ergo_selected"),
            "sst_view": sst_view,
            "show_carga": show_carga,
            "edit_obj": edit_obj,
            "edit_acc": edit_acc,
        }

    def _sgsst_plan_parse_date(value):
        txt = str(value or "").strip()
        if not txt:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(txt[:19], fmt).date()
            except Exception:
                continue
        try:
            return datetime.fromisoformat(txt.replace("Z", "")[:19]).date()
        except Exception:
            return None

    def _sgsst_plan_short_date(value):
        parsed = value if isinstance(value, date) else _sgsst_plan_parse_date(value)
        return parsed.strftime("%d/%m/%Y") if parsed else "-"

    def _sgsst_plan_percent(done, total):
        return int(round((done / total) * 100)) if total else 0

    def _sgsst_plan_progress_class(pct):
        if pct >= 80:
            return "ok"
        if pct >= 45:
            return "warn"
        return "risk"

    def _sgsst_plan_priority_label(value):
        txt = str(value or "").strip().lower()
        mapping = {
            "baja": "Baja",
            "media": "Media",
            "alta": "Alta",
            "critica": "Critica",
            "crítica": "Critica",
        }
        return mapping.get(txt, (str(value or "").strip().title() or "Media"))

    def _sgsst_plan_priority_rank(value):
        label = _sgsst_plan_priority_label(value)
        if label == "Critica":
            return 0
        if label == "Alta":
            return 1
        if label == "Media":
            return 2
        return 3

    def _sgsst_plan_hallazgo_state_label(value):
        txt = str(value or "").strip().lower()
        mapping = {
            "detectado": "Detectado",
            "en analisis": "En analisis",
            "confirmado": "Confirmado",
            "no aplica": "No aplica",
            "resuelto": "Resuelto",
            "cerrado": "Cerrado",
            "abierto": "Confirmado",
        }
        return mapping.get(txt, (str(value or "").strip().title() or "Detectado"))

    def _sgsst_plan_action_state_label(value):
        txt = str(value or "").strip().lower()
        mapping = {
            "pendiente": "Pendiente",
            "en analisis": "En analisis",
            "en curso": "En gestion",
            "en gestión": "En gestion",
            "en gestion": "En gestion",
            "programada": "Programada",
            "programado": "Programada",
            "en ejecucion": "En ejecucion",
            "en ejecución": "En ejecucion",
            "bloqueada": "Bloqueada",
            "implementada": "Implementada",
            "verificada": "Verificada",
            "cerrada": "Cerrada",
            "cerrado": "Cerrada",
            "cancelada": "Cancelada",
            "completado": "Cerrada",
        }
        return mapping.get(txt, (str(value or "").strip().title() or "Pendiente"))

    def _sgsst_plan_action_state_tone(value):
        state = _sgsst_plan_action_state_label(value)
        if state in {"Verificada", "Cerrada", "Implementada"}:
            return "ok"
        if state in {"Bloqueada"}:
            return "risk"
        if state in {"Pendiente", "En analisis", "En gestion", "Programada", "En ejecucion"}:
            return "warn"
        return "muted"

    def _sgsst_plan_hallazgo_state_tone(value):
        state = _sgsst_plan_hallazgo_state_label(value)
        if state in {"Resuelto", "Cerrado", "No aplica"}:
            return "ok"
        if state in {"Confirmado", "Detectado"}:
            return "risk"
        if state == "En analisis":
            return "warn"
        return "muted"

    def _sgsst_plan_is_action_closed(value):
        return _sgsst_plan_action_state_label(value) in {"Implementada", "Verificada", "Cerrada", "Cancelada"}

    def _sgsst_plan_is_hallazgo_closed(value):
        return _sgsst_plan_hallazgo_state_label(value) in {"Resuelto", "Cerrado", "No aplica"}

    def _sgsst_plan_status_summary_label(pct, overdue=0, active=0):
        if overdue > 0:
            return "Con alertas"
        if active > 0 and pct >= 80:
            return "Controlado"
        if active > 0:
            return "En despliegue"
        if pct > 0:
            return "Iniciado"
        return "Sin iniciar"

    def _sgsst_command_module_complete(project_key, module_row):
        state_label = str(module_row.get("state_label") or "").strip().lower()
        result_text = str(module_row.get("result") or "").strip().lower()
        if project_key == "art":
            return "sin visita" not in result_text and state_label not in {"pendiente", "sin datos", "sin registrar"}
        if project_key == "documentacion":
            return state_label in {"completa", "cargada", "cargado"}
        if project_key == "evacuacion":
            return state_label in {"cargado", "completa", "completo"}
        if project_key in {"carteleria", "luces"}:
            return state_label not in {"sin relevar", "sin datos"} and "sin base operativa" not in result_text
        if project_key == "matafuegos":
            return "sin equipos activos" not in result_text and state_label != "sin datos"
        if project_key == "desinfeccion":
            return "sin intervencion" not in result_text and state_label != "sin datos"
        return False

    def _sgsst_command_module_missing(project_key, module_row):
        state_label = str(module_row.get("state_label") or "").strip().lower()
        result_text = str(module_row.get("result") or "").strip().lower()
        if project_key == "art":
            return "sin visita" in result_text or state_label in {"pendiente", "sin datos", "sin registrar"}
        if project_key == "documentacion":
            return state_label in {"sin registrar", "sin datos"}
        if project_key == "evacuacion":
            return state_label in {"sin relevar", "sin registrar", "sin datos"}
        if project_key in {"carteleria", "luces"}:
            return state_label in {"sin relevar", "sin datos"} or "sin base operativa" in result_text
        if project_key == "matafuegos":
            return "sin equipos activos" in result_text or state_label == "sin datos"
        if project_key == "desinfeccion":
            return "sin intervencion" in result_text or state_label == "sin datos"
        return False

    def _sgsst_command_project_responsable(project_actions, project_events, fallback):
        buckets = {}
        for action in project_actions:
            for candidate in (
                action.get("responsable"),
                action.get("area_responsable"),
            ):
                txt = str(candidate or "").strip()
                if not txt:
                    continue
                buckets[txt] = buckets.get(txt, 0) + 1
        for event in project_events:
            txt = str(event.get("responsible") or "").strip()
            if not txt:
                continue
            buckets[txt] = buckets.get(txt, 0) + 1
        if not buckets:
            return fallback
        return sorted(buckets.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _sgsst_command_load_settings(con):
        ensure_sgsst_implementation_tables(con)
        project_meta = {}
        scope_map = defaultdict(dict)
        for row in con.execute("""
            SELECT
                project_key,
                COALESCE(label, '') AS label,
                COALESCE(responsable, '') AS responsable,
                COALESCE(frecuencia, '') AS frecuencia,
                COALESCE(periodicidad, '') AS periodicidad,
                COALESCE(reglas, '') AS reglas,
                COALESCE(activo, 1) AS activo,
                COALESCE(orden_visual, 0) AS orden_visual
            FROM sgsst_command_projects
            ORDER BY orden_visual, label
        """).fetchall():
            key = str(row["project_key"] or "").strip()
            if not key:
                continue
            project_meta[key] = dict(row)
        for row in con.execute("""
            SELECT
                project_key,
                UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                UPPER(COALESCE(scope_state, 'AUTO')) AS scope_state,
                COALESCE(note, '') AS note
            FROM sgsst_command_project_scope
        """).fetchall():
            project_key = str(row["project_key"] or "").strip()
            sede_codigo = str(row["sede_codigo"] or "").strip().upper()
            if not project_key or not sede_codigo:
                continue
            scope_map[project_key][sede_codigo] = {
                "scope_state": str(row["scope_state"] or "AUTO").strip().upper() or "AUTO",
                "note": str(row["note"] or "").strip(),
            }
        return project_meta, scope_map

    def _sgsst_command_scope_summary(project_key, sedes_scope, scope_state_map):
        project = _sgsst_command_project_map().get(project_key)
        completed_sedes = []
        pending_sedes = []
        missing_sedes = []
        no_aplica_sedes = []
        out_scope_sedes = []
        module_rows = []
        applicable_codes = set()
        if not project:
            return {
                "module_rows": [],
                "completed_sedes": completed_sedes,
                "pending_sedes": pending_sedes,
                "missing_sedes": missing_sedes,
                "no_aplica_sedes": no_aplica_sedes,
                "out_scope_sedes": out_scope_sedes,
                "applicable_total": 0,
                "all_total": 0,
                "applicable_codes": applicable_codes,
            }
        for sede_row in sedes_scope:
            match = next((row for row in (sede_row.get("module_rows") or []) if row.get("module") in project["module_names"]), None)
            if not match:
                continue
            sede_codigo = str(sede_row.get("codigo") or "").strip().upper()
            module_rows.append({
                "sede_codigo": sede_codigo,
                "sede_nombre": sede_row.get("nombre") or sede_codigo,
                "state_label": match.get("state_label") or "",
                "state_tone": match.get("state_tone") or "muted",
                "result": match.get("result") or "",
                "pending": match.get("pending") or "",
                "next_action": match.get("next_action") or "",
                "url": match.get("url") or _sgsst_command_project_open_url(project_key, sede_codigo),
            })
            scope_state = str((scope_state_map.get(sede_codigo) or {}).get("scope_state") or "AUTO").strip().upper() or "AUTO"
            if scope_state == "NO_APLICA":
                no_aplica_sedes.append(sede_codigo)
                continue
            if scope_state == "FUERA_ALCANCE":
                out_scope_sedes.append(sede_codigo)
                continue
            applicable_codes.add(sede_codigo)
            if scope_state == "COMPLETA":
                completed_sedes.append(sede_codigo)
                continue
            if scope_state == "PENDIENTE":
                pending_sedes.append(sede_codigo)
                continue
            if _sgsst_command_module_complete(project_key, match):
                completed_sedes.append(sede_codigo)
            elif _sgsst_command_module_missing(project_key, match):
                missing_sedes.append(sede_codigo)
            else:
                pending_sedes.append(sede_codigo)
        applicable_total = max(len(module_rows) - len(no_aplica_sedes) - len(out_scope_sedes), 0)
        return {
            "module_rows": module_rows,
            "completed_sedes": completed_sedes,
            "pending_sedes": pending_sedes,
            "missing_sedes": missing_sedes,
            "no_aplica_sedes": no_aplica_sedes,
            "out_scope_sedes": out_scope_sedes,
            "applicable_total": applicable_total,
            "all_total": len(module_rows),
            "applicable_codes": applicable_codes,
        }

    def build_sgsst_plan_implementation_context(view_mode="general", selected_sede="", open_form=""):
        con = get_db()
        ensure_sst_general_table(con)
        ensure_sst_plan_tables(con)
        ensure_sgsst_implementation_tables(con)
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_desinfecciones_tables(con)
        ensure_sst_carteleria_tables(con)
        ensure_sst_luces_tables(con)
        seed_sgsst_documentacion(con)

        today_ref = date.today()
        current_year = today_ref.year
        view_mode = (view_mode or "general").strip().lower()
        if view_mode not in {"general", "fases", "sedes", "acciones", "responsables", "cronograma"}:
            view_mode = "general"

        sedes_rows = con.execute("""
            SELECT
                UPPER(COALESCE(codigo, '')) AS codigo,
                COALESCE(nombre, '') AS nombre,
                COALESCE(ciudad, '') AS ciudad,
                COALESCE(direccion, '') AS direccion,
                COALESCE(fuero, '') AS fuero,
                COALESCE(activa, 1) AS activa
            FROM sedes_mpd
            WHERE TRIM(COALESCE(codigo, '')) <> ''
            ORDER BY codigo
        """).fetchall()
        sedes = []
        sedes_map = {}
        for row in sedes_rows:
            item = {key: row[key] for key in row.keys()}
            if int(item.get("activa", 1) or 1) != 1:
                continue
            sedes.append(item)
            sedes_map[item["codigo"]] = item

        marco_row = con.execute("SELECT * FROM sgsst_plan_marco WHERE id = 1").fetchone()
        marco = dict(marco_row) if marco_row else {}
        bloques, estado_prot, estado_ins = _sgsst_build_bloques_home(con)
        roles_rows = con.execute("""
            SELECT *
            FROM sgsst_plan_roles
            WHERE COALESCE(activo, 1) = 1
            ORDER BY grupo, orden_visual, rol
        """).fetchall()
        roles = [dict(r) for r in roles_rows]

        manual_hallazgos_rows = con.execute("""
            SELECT
                h.*,
                COALESCE(s.nombre, '') AS sede_nombre
            FROM sgsst_plan_hallazgos h
            LEFT JOIN sedes_mpd s ON s.codigo = h.sede_codigo
            ORDER BY
                CASE LOWER(COALESCE(h.estado, 'detectado'))
                    WHEN 'confirmado' THEN 0
                    WHEN 'detectado' THEN 1
                    WHEN 'en analisis' THEN 2
                    ELSE 3
                END,
                date(COALESCE(h.fecha_deteccion, substr(h.created_at, 1, 10))) DESC,
                h.id DESC
        """).fetchall()
        manual_hallazgos = []
        for row in manual_hallazgos_rows:
            item = dict(row)
            item["source_kind"] = "manual"
            item["source_label"] = "Hallazgo manual"
            item["state_label"] = _sgsst_plan_hallazgo_state_label(item.get("estado"))
            item["state_tone"] = _sgsst_plan_hallazgo_state_tone(item.get("estado"))
            item["priority_label"] = _sgsst_plan_priority_label(item.get("prioridad"))
            item["is_closed"] = _sgsst_plan_is_hallazgo_closed(item.get("estado"))
            item["fecha_deteccion_label"] = _sgsst_plan_short_date(item.get("fecha_deteccion") or item.get("created_at"))
            manual_hallazgos.append(item)

        legacy_rows = con.execute("""
            SELECT
                g.*,
                COALESCE(s.nombre, '') AS sede_nombre
            FROM sst_general g
            LEFT JOIN sedes_mpd s ON s.codigo = g.sede_codigo
            WHERE LOWER(COALESCE(g.tipo, '')) = 'no_conformidad'
            ORDER BY date(COALESCE(g.fecha_objetivo, g.fecha)) ASC, g.id DESC
        """).fetchall()
        hallazgos = list(manual_hallazgos)
        acciones = []
        for row in legacy_rows:
            base = dict(row)
            hallazgo_state = "Cerrado" if str(base.get("estado") or "").strip().upper() == "CERRADO" else "Confirmado"
            hallazgos.append({
                "id": f"legacy-{base['id']}",
                "sede_codigo": (base.get("sede_codigo") or "").strip().upper(),
                "sede_nombre": base.get("sede_nombre") or "",
                "modulo_origen": "Seguimiento operativo",
                "categoria": base.get("categoria") or "SG-SST",
                "titulo": base.get("titulo") or "Hallazgo operativo",
                "descripcion": base.get("detalle") or "",
                "fecha_deteccion": base.get("fecha") or "",
                "fecha_deteccion_label": _sgsst_plan_short_date(base.get("fecha")),
                "fuente": base.get("origen_tipo") or "relevamiento interno",
                "priority_label": _sgsst_plan_priority_label(base.get("prioridad")),
                "state_label": hallazgo_state,
                "state_tone": _sgsst_plan_hallazgo_state_tone(hallazgo_state),
                "is_closed": _sgsst_plan_is_hallazgo_closed(hallazgo_state),
                "source_kind": "legacy",
                "source_label": "Seguimiento existente",
                "detail_url": url_for("sst_general", modo="gestion", sede=base.get("sede_codigo") or None, tipo="no_conformidad"),
            })
            action_state = "Cerrada" if str(base.get("estado") or "").strip().upper() == "CERRADO" else ("En gestion" if (base.get("responsable") or "").strip() else "Pendiente")
            due_date = base.get("fecha_objetivo") or ""
            due_parsed = _sgsst_plan_parse_date(due_date)
            overdue = bool(due_parsed and due_parsed < today_ref and not _sgsst_plan_is_action_closed(action_state))
            acciones.append({
                "id": f"legacy-{base['id']}",
                "source_kind": "legacy",
                "source_label": "Seguimiento operativo",
                "hallazgo_ref": f"legacy-{base['id']}",
                "hallazgo_title": base.get("titulo") or "Hallazgo operativo",
                "sede_codigo": (base.get("sede_codigo") or "").strip().upper(),
                "sede_nombre": base.get("sede_nombre") or "",
                "modulo_origen": "Seguimiento operativo",
                "titulo": base.get("titulo") or "Accion operativa",
                "accion_requerida": (base.get("accion_correctiva") or base.get("titulo") or "").strip(),
                "responsable": (base.get("responsable") or "").strip(),
                "area_responsable": (base.get("area") or "").strip(),
                "priority_label": _sgsst_plan_priority_label(base.get("prioridad")),
                "priority_rank": _sgsst_plan_priority_rank(base.get("prioridad")),
                "fecha_creacion": base.get("fecha") or "",
                "fecha_creacion_label": _sgsst_plan_short_date(base.get("fecha")),
                "fecha_objetivo": due_date,
                "fecha_objetivo_label": _sgsst_plan_short_date(due_date) if due_date else "-",
                "state_label": _sgsst_plan_action_state_label(action_state),
                "state_tone": _sgsst_plan_action_state_tone(action_state),
                "avance_pct": 100 if _sgsst_plan_is_action_closed(action_state) else 35,
                "overdue": overdue,
                "detail_url": url_for("sst_general", modo="gestion", sede=base.get("sede_codigo") or None, tipo="no_conformidad"),
                "phase_key": "implementacion",
                "evidencia": base.get("evidencia_url") or "",
                "observaciones": base.get("detalle") or "",
            })

        manual_actions_rows = con.execute("""
            SELECT
                a.*,
                COALESCE(h.titulo, '') AS hallazgo_titulo,
                COALESCE(s.nombre, '') AS sede_nombre
            FROM sgsst_plan_acciones a
            LEFT JOIN sgsst_plan_hallazgos h ON h.id = a.hallazgo_id
            LEFT JOIN sedes_mpd s ON s.codigo = a.sede_codigo
            ORDER BY
                CASE LOWER(COALESCE(a.estado, 'pendiente'))
                    WHEN 'bloqueada' THEN 0
                    WHEN 'pendiente' THEN 1
                    WHEN 'en gestion' THEN 2
                    WHEN 'programada' THEN 3
                    WHEN 'en ejecucion' THEN 4
                    ELSE 5
                END,
                CASE LOWER(COALESCE(a.prioridad, 'media'))
                    WHEN 'critica' THEN 0
                    WHEN 'crítica' THEN 0
                    WHEN 'alta' THEN 1
                    WHEN 'media' THEN 2
                    ELSE 3
                END,
                date(COALESCE(a.fecha_objetivo, a.fecha_creacion, substr(a.created_at, 1, 10))) ASC,
                a.id DESC
        """).fetchall()
        manual_actions = []
        for row in manual_actions_rows:
            item = dict(row)
            state_label = _sgsst_plan_action_state_label(item.get("estado"))
            due_date = item.get("fecha_objetivo") or ""
            due_parsed = _sgsst_plan_parse_date(due_date)
            overdue = bool(due_parsed and due_parsed < today_ref and not _sgsst_plan_is_action_closed(state_label))
            pct = int(item.get("avance_pct") or (100 if _sgsst_plan_is_action_closed(state_label) else 0))
            manual_actions.append({
                "id": f"manual-{item['id']}",
                "raw_id": int(item["id"] or 0),
                "source_kind": "manual",
                "source_label": "Plan SG-SST",
                "hallazgo_ref": (f"manual-{int(item['hallazgo_id'])}" if int(item.get("hallazgo_id") or 0) > 0 else ""),
                "hallazgo_title": item.get("hallazgo_titulo") or "",
                "sede_codigo": (item.get("sede_codigo") or "").strip().upper(),
                "sede_nombre": item.get("sede_nombre") or "",
                "modulo_origen": (item.get("modulo_origen") or "Plan de implementacion").strip(),
                "titulo": item.get("titulo") or "Accion del plan",
                "accion_requerida": (item.get("accion_requerida") or "").strip(),
                "responsable": (item.get("responsable") or "").strip(),
                "area_responsable": (item.get("area_responsable") or "").strip(),
                "priority_label": _sgsst_plan_priority_label(item.get("prioridad")),
                "priority_rank": _sgsst_plan_priority_rank(item.get("prioridad")),
                "fecha_creacion": item.get("fecha_creacion") or "",
                "fecha_creacion_label": _sgsst_plan_short_date(item.get("fecha_creacion") or item.get("created_at")),
                "fecha_objetivo": due_date,
                "fecha_objetivo_label": _sgsst_plan_short_date(due_date) if due_date else "-",
                "state_label": state_label,
                "state_tone": _sgsst_plan_action_state_tone(state_label),
                "avance_pct": max(0, min(100, pct)),
                "overdue": overdue,
                "detail_url": url_for("sst_plan_implementacion", vista="acciones", sede=(item.get("sede_codigo") or None)),
                "phase_key": "implementacion",
                "evidencia": item.get("evidencia") or "",
                "observaciones": item.get("observaciones") or "",
                "compra_requerida": int(item.get("compra_requerida") or 0),
                "intervencion_requerida": int(item.get("intervencion_requerida") or 0),
            })
        acciones.extend(manual_actions)

        objetivo_actions_rows = con.execute("""
            SELECT
                a.*,
                COALESCE(o.sede_codigo, '') AS sede_codigo,
                COALESCE(o.titulo, '') AS objetivo_titulo,
                COALESCE(s.nombre, '') AS sede_nombre
            FROM sst_objetivo_acciones a
            LEFT JOIN sst_objetivos o ON o.id = a.objetivo_id
            LEFT JOIN sedes_mpd s ON s.codigo = o.sede_codigo
            ORDER BY a.id DESC
        """).fetchall()
        for row in objetivo_actions_rows:
            item = dict(row)
            state_label = _sgsst_plan_action_state_label(item.get("estado"))
            due_date = item.get("fecha_fin") or ""
            due_parsed = _sgsst_plan_parse_date(due_date)
            overdue = bool(due_parsed and due_parsed < today_ref and not _sgsst_plan_is_action_closed(state_label))
            pct = int(item.get("avance_pct") or (100 if _sgsst_plan_is_action_closed(state_label) else 0))
            acciones.append({
                "id": f"objetivo-{item['id']}",
                "source_kind": "objetivo",
                "source_label": "Objetivo SST",
                "hallazgo_ref": "",
                "hallazgo_title": item.get("objetivo_titulo") or "",
                "sede_codigo": (item.get("sede_codigo") or "").strip().upper(),
                "sede_nombre": item.get("sede_nombre") or "",
                "modulo_origen": (item.get("fase") or "Implementacion").strip(),
                "titulo": item.get("objetivo_titulo") or item.get("nombre") or "Objetivo SST",
                "accion_requerida": (item.get("nombre") or item.get("notas") or "").strip(),
                "responsable": (item.get("responsable_area") or "").strip(),
                "area_responsable": (item.get("responsable_area") or "").strip(),
                "priority_label": _sgsst_plan_priority_label("Media"),
                "priority_rank": _sgsst_plan_priority_rank("Media"),
                "fecha_creacion": item.get("fecha_inicio") or "",
                "fecha_creacion_label": _sgsst_plan_short_date(item.get("fecha_inicio") or item.get("created_at")),
                "fecha_objetivo": due_date,
                "fecha_objetivo_label": _sgsst_plan_short_date(due_date) if due_date else "-",
                "state_label": state_label,
                "state_tone": _sgsst_plan_action_state_tone(state_label),
                "avance_pct": max(0, min(100, pct)),
                "overdue": overdue,
                "detail_url": url_for("sst_plan", vista="gestion"),
                "phase_key": "implementacion",
                "evidencia": item.get("evidencia_url") or "",
                "observaciones": item.get("notas") or "",
                "compra_requerida": 0,
                "intervencion_requerida": 0,
            })

        acciones.sort(key=lambda item: (
            1 if _sgsst_plan_is_action_closed(item.get("state_label")) else 0,
            0 if item.get("overdue") else 1,
            item.get("priority_rank", 3),
            item.get("fecha_objetivo") or "9999-12-31",
            item.get("sede_codigo") or "ZZZ",
        ))

        calendar_raw = _sst_calendar_collect_events(con, current_year)
        control_events = [
            event for event in calendar_raw.get("events", [])
            if event.get("type_key") in {"matafuegos", "desinfeccion", "luces", "carteleria", "visita"}
        ]
        control_events.sort(key=lambda event: (event.get("fecha_evento") or "", event.get("sede_codigo") or ""))

        cart_summary = {}
        if _table_exists(con, "sst_carteleria_registros") and con.execute("SELECT COUNT(*) AS n FROM sst_carteleria_registros WHERE COALESCE(activo, 1) = 1").fetchone()["n"]:
            cart_summary = _sst_carteleria_aggregate_by_sede(_sst_fetch_carteleria_records(con))
        luces_summary = {}
        if _table_exists(con, "sst_luces_registros") and con.execute("SELECT COUNT(*) AS n FROM sst_luces_registros WHERE COALESCE(activo, 1) = 1").fetchone()["n"]:
            luces_summary = _sst_luces_aggregate_by_sede(_sst_fetch_luces_records(con))
        desinf_records = _sst_desinf_fetch_records(con)

        visitas_by_sede = defaultdict(list)
        for row in con.execute("""
            SELECT
                UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                COALESCE(fecha, '') AS fecha,
                COALESCE(tipo_visita, '') AS tipo_visita,
                COALESCE(estado, '') AS estado,
                COALESCE(accion_requerida, '') AS accion_requerida,
                COALESCE(fecha_programada, '') AS fecha_programada
            FROM sst_visitas
            ORDER BY date(fecha) DESC, id DESC
        """).fetchall():
            sede_codigo = (row["sede_codigo"] or "").strip().upper()
            if sede_codigo:
                visitas_by_sede[sede_codigo].append(dict(row))

        docs_by_sede = defaultdict(list)
        docs_count_by_sede = defaultdict(int)
        docs_status_by_sede = defaultdict(dict)
        for row in con.execute("""
            SELECT
                UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                COALESCE(tipo, '') AS tipo,
                COALESCE(estado_revision, '') AS estado_revision,
                COALESCE(fecha_carga, '') AS fecha_carga,
                COALESCE(fecha_actualizacion, '') AS fecha_actualizacion
            FROM sst_documentos
            ORDER BY date(COALESCE(fecha_actualizacion, fecha_carga)) DESC, id DESC
        """).fetchall():
            sede_codigo = (row["sede_codigo"] or "").strip().upper()
            if sede_codigo:
                docs_by_sede[sede_codigo].append(dict(row))
                docs_count_by_sede[sede_codigo] += 1
                tipo = str(row["tipo"] or "").strip().upper()
                if tipo and tipo not in docs_status_by_sede[sede_codigo]:
                    docs_status_by_sede[sede_codigo][tipo] = str(row["estado_revision"] or "").strip().upper()

        evac_by_sede = defaultdict(lambda: {"count": 0, "fecha": ""})
        if _table_exists(con, "sedes_planos"):
            for row in con.execute("""
                SELECT
                    UPPER(COALESCE(cod_sede, '')) AS sede_codigo,
                    COALESCE(fecha_carga, '') AS fecha_carga
                FROM sedes_planos
                WHERE LOWER(COALESCE(tipo, '')) = 'evacuacion'
            """).fetchall():
                sede_codigo = (row["sede_codigo"] or "").strip().upper()
                if not sede_codigo:
                    continue
                evac_by_sede[sede_codigo]["count"] += 1
                fecha_carga = str(row["fecha_carga"] or "").strip()
                if fecha_carga and fecha_carga > str(evac_by_sede[sede_codigo]["fecha"] or ""):
                    evac_by_sede[sede_codigo]["fecha"] = fecha_carga

        matafuegos_rows = con.execute("""
            SELECT
                UPPER(COALESCE(sede, cod_sede, '')) AS sede_codigo,
                COALESCE(fecha_vencimiento, '') AS fecha_vencimiento,
                COALESCE(activo, 1) AS activo
            FROM matafuegos
            WHERE COALESCE(activo, 1) = 1
        """).fetchall() if _table_exists(con, "matafuegos") else []
        mata_by_sede = defaultdict(lambda: {"total": 0, "vencidos": 0, "proximos": 0, "fecha_proxima": ""})
        for row in matafuegos_rows:
            sede_codigo = (row["sede_codigo"] or "").strip().upper()
            if not sede_codigo:
                continue
            due = _sgsst_plan_parse_date(row["fecha_vencimiento"])
            mata_by_sede[sede_codigo]["total"] += 1
            if due:
                if due < today_ref:
                    mata_by_sede[sede_codigo]["vencidos"] += 1
                elif due <= (today_ref + timedelta(days=45)):
                    mata_by_sede[sede_codigo]["proximos"] += 1
                current_next = _sgsst_plan_parse_date(mata_by_sede[sede_codigo]["fecha_proxima"])
                if current_next is None or due < current_next:
                    mata_by_sede[sede_codigo]["fecha_proxima"] = due.isoformat()

        desinf_by_sede = defaultdict(lambda: {"total": 0, "realizadas": 0, "pendientes": 0, "vencidas": 0, "ultima": "", "proxima": ""})
        for record in desinf_records:
            sede_codigo = (record.get("sede_codigo") or "").strip().upper()
            if not sede_codigo:
                continue
            desinf_by_sede[sede_codigo]["total"] += 1
            if record.get("fecha_realizada"):
                desinf_by_sede[sede_codigo]["realizadas"] += 1
                if not desinf_by_sede[sede_codigo]["ultima"] or str(record.get("fecha_realizada")) > desinf_by_sede[sede_codigo]["ultima"]:
                    desinf_by_sede[sede_codigo]["ultima"] = record.get("fecha_realizada")
            else:
                desinf_by_sede[sede_codigo]["pendientes"] += 1
                due = _sgsst_plan_parse_date(record.get("fecha_programada"))
                if due and due < today_ref:
                    desinf_by_sede[sede_codigo]["vencidas"] += 1
                if record.get("fecha_programada"):
                    current_next = _sgsst_plan_parse_date(desinf_by_sede[sede_codigo]["proxima"])
                    candidate = _sgsst_plan_parse_date(record.get("fecha_programada"))
                    if candidate and (current_next is None or candidate < current_next):
                        desinf_by_sede[sede_codigo]["proxima"] = record.get("fecha_programada")

        hallazgos_by_sede = defaultdict(list)
        for item in hallazgos:
            sede_codigo = (item.get("sede_codigo") or "").strip().upper()
            if sede_codigo:
                hallazgos_by_sede[sede_codigo].append(item)

        actions_by_sede = defaultdict(list)
        for item in acciones:
            sede_codigo = (item.get("sede_codigo") or "").strip().upper()
            if sede_codigo:
                actions_by_sede[sede_codigo].append(item)

        controls_by_sede = defaultdict(list)
        for event in control_events:
            sede_codigo = (event.get("sede_codigo") or "").strip().upper()
            if sede_codigo:
                controls_by_sede[sede_codigo].append(event)

        library_phase_map = {
            "politica": "marco",
            "plan_accion": "marco",
            "roles": "marco",
            "protocolos": "operacion",
            "instructivos": "operacion",
            "riesgos": "diagnostico",
        }
        library_cards = []
        for block in bloques:
            doc = block.get("doc") or {}
            auto = block.get("auto") or {}
            block_key = (block.get("bloque") or "").strip().lower()
            library_cards.append({
                "key": block_key,
                "title": doc.get("titulo") or block_key.replace("_", " ").title(),
                "subtitle": doc.get("subtitulo") or doc.get("descripcion_corta") or "",
                "status_label": auto.get("label") or "En armado",
                "status_tone": ("ok" if (auto.get("label") or "").strip().lower() == "completo" else "warn"),
                "phase_key": library_phase_map.get(block_key, "marco"),
                "detail_url": url_for("sgsst_documento_detalle", bloque=block_key),
            })

        command_project_meta, command_project_scope = _sgsst_command_load_settings(con)

        sedes_dashboard = []
        diagnostic_pct_values = []
        suggestions = []
        total_periodic_overdue = 0
        total_periodic_active = 0
        for sede in sedes:
            codigo = sede["codigo"]
            visits = visitas_by_sede.get(codigo, [])
            docs = docs_by_sede.get(codigo, [])
            docs_status = docs_status_by_sede.get(codigo, {})
            evac = evac_by_sede.get(codigo, {"count": 0, "fecha": ""})
            cart = cart_summary.get(codigo)
            luces = luces_summary.get(codigo)
            mata = mata_by_sede.get(codigo, {"total": 0, "vencidos": 0, "proximos": 0, "fecha_proxima": ""})
            desinf = desinf_by_sede.get(codigo, {"total": 0, "realizadas": 0, "pendientes": 0, "vencidas": 0, "ultima": "", "proxima": ""})
            hall_list = hallazgos_by_sede.get(codigo, [])
            act_list = actions_by_sede.get(codigo, [])
            control_list = controls_by_sede.get(codigo, [])

            hall_open = sum(1 for item in hall_list if not item.get("is_closed"))
            hall_closed = sum(1 for item in hall_list if item.get("is_closed"))
            act_open = sum(1 for item in act_list if not _sgsst_plan_is_action_closed(item.get("state_label")))
            act_closed = sum(1 for item in act_list if _sgsst_plan_is_action_closed(item.get("state_label")))
            act_overdue = sum(1 for item in act_list if item.get("overdue"))
            act_impl = sum(1 for item in act_list if item.get("state_label") in {"Implementada", "Verificada", "Cerrada"})
            periodic_total = len(control_list)
            periodic_overdue = sum(1 for item in control_list if item.get("state_key") == "vencido")
            periodic_active = sum(1 for item in control_list if item.get("active"))
            total_periodic_overdue += periodic_overdue
            total_periodic_active += periodic_active

            coverage_sources = 0
            if visits:
                coverage_sources += 1
            if docs:
                coverage_sources += 1
            if mata["total"] > 0:
                coverage_sources += 1
            if cart and int(cart.get("record_count") or 0) > 0:
                coverage_sources += 1
            if luces and int(luces.get("record_count") or 0) > 0:
                coverage_sources += 1
            if desinf["total"] > 0:
                coverage_sources += 1

            diagnostic_pct = _sgsst_plan_percent(coverage_sources, 6)
            diagnostic_pct_values.append(diagnostic_pct)
            diagnostic_started = coverage_sources > 0 or hall_open > 0
            diagnostic_complete = coverage_sources >= 4 and (len(visits) > 0 or len(docs) > 0 or hall_open > 0)
            impl_pct = _sgsst_plan_percent(act_impl, len(act_list))
            oper_pct = _sgsst_plan_percent(max(periodic_total - periodic_overdue, 0), periodic_total) if periodic_total else 0

            if act_overdue or periodic_overdue or any(item.get("priority_label") == "Critica" and not item.get("is_closed") for item in hall_list):
                estado_general = "Critico"
                estado_tone = "risk"
            elif hall_open or act_open:
                estado_general = "En despliegue"
                estado_tone = "warn"
            elif diagnostic_started:
                estado_general = "Con base operativa"
                estado_tone = "ok"
            else:
                estado_general = "Sin iniciar"
                estado_tone = "muted"

            docs_ok = sum(1 for doc_type in SST_CALENDAR_REQUIRED_DOCS if docs_status.get(doc_type) in {"CARGADO", "NO_APLICA"})
            docs_missing = max(len(SST_CALENDAR_REQUIRED_DOCS) - docs_ok, 0)
            if docs_missing == 0 and docs:
                docs_state_label = "Completa"
                docs_state_tone = "ok"
            elif docs:
                docs_state_label = "Pendiente"
                docs_state_tone = "warn"
            else:
                docs_state_label = "Sin registrar"
                docs_state_tone = "muted"

            module_rows = []
            module_rows.append({
                "module": "ART",
                "state_label": ("Visitada" if visits else "Pendiente"),
                "state_tone": ("ok" if visits else "muted"),
                "result": (f"{len(visits)} visita(s)" if visits else "Sin visita registrada"),
                "pending": (f"{sum(1 for d in docs if str(d.get('estado_revision') or '').strip().upper() == 'FALTANTE')} documento(s) pendiente(s)" if docs else "Sin documentacion asociada"),
                "next_action": ("Cargar documentacion ART" if visits and any(str(d.get("estado_revision") or "").strip().upper() == "FALTANTE" for d in docs) else ("Registrar primera visita" if not visits else "Mantener seguimiento")),
                "url": url_for("sst_visitas", sede=codigo, open_sede=codigo),
            })
            module_rows.append({
                "module": "Documentacion",
                "state_label": docs_state_label,
                "state_tone": docs_state_tone,
                "result": f"{docs_ok}/{len(SST_CALENDAR_REQUIRED_DOCS)} documento(s) obligatorio(s)",
                "pending": (f"{docs_missing} faltante(s)" if docs_missing else "Sin faltantes"),
                "next_action": ("Abrir documentacion" if docs else "Cargar documentacion"),
                "url": url_for("sst_visitas", sede=codigo, open_sede=codigo),
            })
            module_rows.append({
                "module": "Evacuacion",
                "state_label": ("Cargado" if evac["count"] > 0 else "Sin relevar"),
                "state_tone": ("ok" if evac["count"] > 0 else "muted"),
                "result": ("Plano cargado" if evac["count"] > 0 else "Sin plano cargado"),
                "pending": ("Verificar responsables y punto de encuentro" if evac["count"] > 0 else "Cargar plano de evacuacion"),
                "next_action": "Abrir evacuacion",
                "url": url_for("sede_ficha", codigo=codigo, tab="evacuacion"),
            })
            if cart:
                module_rows.append({
                    "module": "Carteleria",
                    "state_label": cart.get("state_meta", {}).get("label", "Con datos"),
                    "state_tone": ("ok" if int(cart.get("faltantes") or 0) == 0 else "warn"),
                    "result": f"{int(cart.get('cantidad_instalada') or 0)} / {int(cart.get('cantidad_requerida') or 0)} instaladas",
                    "pending": f"{int(cart.get('faltantes') or 0)} faltante(s)",
                    "next_action": cart.get("action_label") or "Abrir carteleria",
                    "url": url_for("sst_carteleria_home", sede=codigo, open_sede=codigo),
                })
            else:
                module_rows.append({
                    "module": "Carteleria",
                    "state_label": "Sin relevar",
                    "state_tone": "muted",
                    "result": "Sin base operativa cargada",
                    "pending": "Iniciar relevamiento",
                    "next_action": "Cargar carteleria",
                    "url": url_for("sst_carteleria_home", sede=codigo, open_sede=codigo),
                })
            if luces:
                module_rows.append({
                    "module": "Luces de emergencia",
                    "state_label": luces.get("state_meta", {}).get("label", "Con datos"),
                    "state_tone": ("ok" if int(luces.get("faltantes") or 0) == 0 and int(luces.get("cantidad_fuera_servicio") or 0) == 0 else "warn"),
                    "result": f"{int(luces.get('cantidad_operativa') or 0)} operativas / {int(luces.get('cantidad_requerida') or 0)} requeridas",
                    "pending": f"{int(luces.get('faltantes') or 0)} faltante(s) · {int(luces.get('cantidad_fuera_servicio') or 0)} fuera de servicio",
                    "next_action": luces.get("action_label") or "Abrir luces",
                    "url": url_for("sst_luces_home", sede=codigo, open_sede=codigo),
                })
            else:
                module_rows.append({
                    "module": "Luces de emergencia",
                    "state_label": "Sin relevar",
                    "state_tone": "muted",
                    "result": "Sin base operativa cargada",
                    "pending": "Iniciar relevamiento",
                    "next_action": "Cargar luces",
                    "url": url_for("sst_luces_home", sede=codigo, open_sede=codigo),
                })
            module_rows.append({
                "module": "Matafuegos",
                "state_label": ("Con alertas" if mata["vencidos"] > 0 else ("Vigente" if mata["total"] > 0 else "Sin datos")),
                "state_tone": ("risk" if mata["vencidos"] > 0 else ("ok" if mata["total"] > 0 else "muted")),
                "result": (f"{mata['total']} equipo(s) activos" if mata["total"] > 0 else "Sin equipos activos registrados"),
                "pending": (f"{mata['vencidos']} vencido(s) · {mata['proximos']} proximo(s)" if mata["total"] > 0 else "Controlar carga inicial"),
                "next_action": ("Regularizar vencimientos" if mata["vencidos"] > 0 else "Controlar proximos vencimientos"),
                "url": url_for("matafuegos_home", sede=codigo, open_sede=codigo),
            })
            module_rows.append({
                "module": "Desinfeccion",
                "state_label": ("Con alertas" if desinf["vencidas"] > 0 else ("Activa" if desinf["total"] > 0 else "Sin datos")),
                "state_tone": ("risk" if desinf["vencidas"] > 0 else ("ok" if desinf["total"] > 0 else "muted")),
                "result": (f"Ultima: {_sgsst_plan_short_date(desinf['ultima'])}" if desinf["ultima"] else "Sin intervencion realizada"),
                "pending": (f"{desinf['pendientes']} pendiente(s)" if desinf["total"] > 0 else "Registrar primera programacion"),
                "next_action": ("Programar proxima intervencion" if desinf["total"] > 0 else "Cargar desinfeccion"),
                "url": url_for("sst_desinfecciones_home", sede=codigo, open_sede=codigo),
            })

            if not visits:
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "ART",
                    "reason": "Sin visita registrada en la sede.",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="ART", prefill_titulo=f"Programar visita ART en {codigo}"),
                    "origin_url": url_for("sst_visitas", sede=codigo, open_sede=codigo),
                    "action_label": "Crear accion",
                })
            if docs_missing > 0:
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "Documentacion",
                    "reason": f"Faltan {docs_missing} documento(s) obligatorio(s).",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="Documentacion", prefill_titulo=f"Completar documentacion ART en {codigo}"),
                    "origin_url": url_for("sst_visitas", sede=codigo, open_sede=codigo),
                    "action_label": "Crear accion",
                })
            if evac["count"] == 0:
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "Evacuacion",
                    "reason": "No hay plano de evacuacion cargado.",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="Evacuacion", prefill_titulo=f"Cargar evacuacion en {codigo}"),
                    "origin_url": url_for("sede_ficha", codigo=codigo, tab="evacuacion"),
                    "action_label": "Crear accion",
                })
            if cart and int(cart.get("faltantes") or 0) > 0:
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "Carteleria",
                    "reason": f"Faltan {int(cart.get('faltantes') or 0)} cartel(es) por regularizar.",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="Carteleria", prefill_titulo=f"Completar carteleria en {codigo}"),
                    "origin_url": url_for("sst_carteleria_home", sede=codigo, open_sede=codigo),
                    "action_label": "Crear accion",
                })
            if luces and (int(luces.get("faltantes") or 0) > 0 or int(luces.get("cantidad_fuera_servicio") or 0) > 0):
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "Luces",
                    "reason": f"{int(luces.get('faltantes') or 0)} faltante(s) y {int(luces.get('cantidad_fuera_servicio') or 0)} fuera de servicio.",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="Luces de emergencia", prefill_titulo=f"Regularizar luces en {codigo}"),
                    "origin_url": url_for("sst_luces_home", sede=codigo, open_sede=codigo),
                    "action_label": "Crear accion",
                })
            if mata["vencidos"] > 0:
                suggestions.append({
                    "sede_codigo": codigo,
                    "sede_nombre": sede.get("nombre") or codigo,
                    "module": "Matafuegos",
                    "reason": f"{mata['vencidos']} matafuego(s) vencido(s).",
                    "action_url": url_for("sst_plan_implementacion", vista="acciones", form="accion", prefill_sede=codigo, prefill_modulo="Matafuegos", prefill_titulo=f"Regularizar matafuegos vencidos en {codigo}"),
                    "origin_url": url_for("matafuegos_home", sede=codigo, open_sede=codigo),
                    "action_label": "Crear accion",
                })

            sedes_dashboard.append({
                "codigo": codigo,
                "nombre": sede.get("nombre") or codigo,
                "ciudad": sede.get("ciudad") or "",
                "direccion": sede.get("direccion") or "",
                "fuero": sede.get("fuero") or "",
                "diagnostico_pct": diagnostic_pct,
                "diagnostico_text": f"{coverage_sources}/6 fuentes activas",
                "diagnostico_state": ("Completo" if diagnostic_complete else ("Iniciado" if diagnostic_started else "Sin iniciar")),
                "diagnostico_complete": diagnostic_complete,
                "hallazgos_abiertos": hall_open,
                "hallazgos_totales": len(hall_list),
                "hallazgos_cerrados": hall_closed,
                "acciones_abiertas": act_open,
                "acciones_totales": len(act_list),
                "acciones_cerradas": act_closed,
                "acciones_vencidas": act_overdue,
                "implementacion_pct": impl_pct,
                "implementacion_text": (f"{act_impl}/{len(act_list)} implementadas" if act_list else "Sin acciones cargadas"),
                "operacion_pct": oper_pct,
                "operacion_text": (f"{periodic_total - periodic_overdue}/{periodic_total} controles en fecha" if periodic_total else "Sin control periodico activo"),
                "periodic_total": periodic_total,
                "periodic_overdue": periodic_overdue,
                "estado_general": estado_general,
                "estado_tone": estado_tone,
                "module_rows": module_rows,
                "actions_preview": act_list[:5],
                "hallazgos_preview": hall_list[:5],
                "detail_url": url_for("sst_plan_implementacion", vista="sedes", sede=codigo),
            })

        selected_sede = (selected_sede or "").strip().upper()
        selected_sede_row = next((item for item in sedes_dashboard if item["codigo"] == selected_sede), None)
        if selected_sede_row is None and view_mode == "sedes" and sedes_dashboard:
            selected_sede_row = sedes_dashboard[0]

        hallazgos_abiertos = sum(1 for item in hallazgos if not item.get("is_closed"))
        hallazgos_cerrados = sum(1 for item in hallazgos if item.get("is_closed"))
        acciones_abiertas = sum(1 for item in acciones if not _sgsst_plan_is_action_closed(item.get("state_label")))
        acciones_cerradas = sum(1 for item in acciones if _sgsst_plan_is_action_closed(item.get("state_label")))
        acciones_vencidas = sum(1 for item in acciones if item.get("overdue"))
        acciones_verificadas = sum(1 for item in acciones if item.get("state_label") in {"Verificada", "Cerrada"})

        marco_checks = [
            {"label": "Objetivo definido", "done": bool((marco.get("objetivo") or "").strip())},
            {"label": "Alcance definido", "done": bool((marco.get("alcance") or "").strip())},
            {"label": "Roles definidos", "done": len(roles) > 0},
            {"label": "Metodologia definida", "done": bool((marco.get("metodologia") or "").strip())},
            {"label": "Plan documental vinculado", "done": any(card["key"] == "plan_accion" for card in library_cards)},
            {"label": "Protocolos / instructivos activos", "done": int((estado_prot.get("n_act") or 0) or 0) > 0 and int((estado_ins.get("n_act") or 0) or 0) > 0},
        ]
        marco_pct = _sgsst_plan_percent(sum(1 for item in marco_checks if item["done"]), len(marco_checks))
        diagnostico_iniciado = sum(1 for item in sedes_dashboard if item["diagnostico_pct"] > 0)
        diagnostico_completo = sum(1 for item in sedes_dashboard if item["diagnostico_complete"])
        diagnostico_pct = int(round(sum(diagnostic_pct_values) / len(diagnostic_pct_values))) if diagnostic_pct_values else 0
        implementacion_pct = _sgsst_plan_percent(acciones_verificadas, len(acciones))
        operacion_pct = _sgsst_plan_percent(max(total_periodic_active - total_periodic_overdue, 0), total_periodic_active) if total_periodic_active else 0
        overall_pct = int(round((marco_pct + diagnostico_pct + implementacion_pct + operacion_pct) / 4))
        overall_state = _sgsst_plan_status_summary_label(overall_pct, overdue=(acciones_vencidas + total_periodic_overdue), active=(hallazgos_abiertos + acciones_abiertas))
        overall_tone = ("risk" if (acciones_vencidas + total_periodic_overdue) > 0 else ("warn" if hallazgos_abiertos or acciones_abiertas else "ok"))

        phase_cards = [
            {
                "key": "marco",
                "short": SGSST_PLAN_PHASE_META["marco"]["short"],
                "title": SGSST_PLAN_PHASE_META["marco"]["title"],
                "description": SGSST_PLAN_PHASE_META["marco"]["description"],
                "pct": marco_pct,
                "class": _sgsst_plan_progress_class(marco_pct),
                "stats": [
                    {"label": "Checklist institucional", "value": f"{sum(1 for item in marco_checks if item['done'])}/{len(marco_checks)}"},
                    {"label": "Documentos vinculados", "value": str(len(library_cards))},
                    {"label": "Roles activos", "value": str(len(roles))},
                ],
                "items": marco_checks,
            },
            {
                "key": "diagnostico",
                "short": SGSST_PLAN_PHASE_META["diagnostico"]["short"],
                "title": SGSST_PLAN_PHASE_META["diagnostico"]["title"],
                "description": SGSST_PLAN_PHASE_META["diagnostico"]["description"],
                "pct": diagnostico_pct,
                "class": _sgsst_plan_progress_class(diagnostico_pct),
                "stats": [
                    {"label": "Sedes iniciadas", "value": f"{diagnostico_iniciado}/{len(sedes_dashboard)}"},
                    {"label": "Sedes con base consolidada", "value": f"{diagnostico_completo}/{len(sedes_dashboard)}"},
                    {"label": "Hallazgos abiertos", "value": str(hallazgos_abiertos)},
                ],
                "items": [
                    {"label": "Sedes sin iniciar", "done": diagnostico_iniciado < len(sedes_dashboard), "value": str(max(len(sedes_dashboard) - diagnostico_iniciado, 0))},
                    {"label": "Sedes en relevamiento", "done": diagnostico_iniciado > 0, "value": str(max(diagnostico_iniciado - diagnostico_completo, 0))},
                    {"label": "Sedes con diagnostico consolidado", "done": diagnostico_completo > 0, "value": str(diagnostico_completo)},
                ],
            },
            {
                "key": "implementacion",
                "short": SGSST_PLAN_PHASE_META["implementacion"]["short"],
                "title": SGSST_PLAN_PHASE_META["implementacion"]["title"],
                "description": SGSST_PLAN_PHASE_META["implementacion"]["description"],
                "pct": implementacion_pct,
                "class": _sgsst_plan_progress_class(implementacion_pct),
                "stats": [
                    {"label": "Acciones abiertas", "value": str(acciones_abiertas)},
                    {"label": "Acciones vencidas", "value": str(acciones_vencidas)},
                    {"label": "Acciones cerradas", "value": str(acciones_cerradas)},
                ],
                "items": [
                    {"label": "En gestion", "done": any(item.get("state_label") == "En gestion" for item in acciones), "value": str(sum(1 for item in acciones if item.get("state_label") == "En gestion"))},
                    {"label": "Programadas", "done": any(item.get("state_label") == "Programada" for item in acciones), "value": str(sum(1 for item in acciones if item.get("state_label") == "Programada"))},
                    {"label": "Implementadas / verificadas", "done": acciones_verificadas > 0, "value": str(acciones_verificadas)},
                ],
            },
            {
                "key": "operacion",
                "short": SGSST_PLAN_PHASE_META["operacion"]["short"],
                "title": SGSST_PLAN_PHASE_META["operacion"]["title"],
                "description": SGSST_PLAN_PHASE_META["operacion"]["description"],
                "pct": operacion_pct,
                "class": _sgsst_plan_progress_class(operacion_pct),
                "stats": [
                    {"label": "Controles activos", "value": str(total_periodic_active)},
                    {"label": "Controles vencidos", "value": str(total_periodic_overdue)},
                    {"label": "Proximos 45 dias", "value": str(sum(1 for item in control_events if item.get('state_key') in {'proximo', 'programado'}))},
                ],
                "items": [
                    {"label": "Vigentes", "done": total_periodic_active > total_periodic_overdue, "value": str(max(total_periodic_active - total_periodic_overdue, 0))},
                    {"label": "Vencidos", "done": total_periodic_overdue > 0, "value": str(total_periodic_overdue)},
                    {"label": "Seguimientos abiertos", "done": hallazgos_abiertos > 0 or acciones_abiertas > 0, "value": str(hallazgos_abiertos + acciones_abiertas)},
                ],
            },
        ]

        cronograma_items = []
        for item in acciones:
            due = _sgsst_plan_parse_date(item.get("fecha_objetivo"))
            if due:
                cronograma_items.append({
                    "source": "accion",
                    "title": item.get("titulo") or item.get("accion_requerida") or "Accion SG-SST",
                    "detail": item.get("accion_requerida") or item.get("hallazgo_title") or "",
                    "sede_codigo": item.get("sede_codigo") or "",
                    "responsable": item.get("responsable") or item.get("area_responsable") or "Sin responsable",
                    "date": due.isoformat(),
                    "date_label": _sgsst_plan_short_date(due),
                    "state_label": item.get("state_label") or "",
                    "state_tone": ("risk" if item.get("overdue") else item.get("state_tone")),
                    "phase_key": "implementacion",
                    "url": item.get("detail_url") or url_for("sst_plan_implementacion", vista="acciones"),
                })
        for event in control_events:
            cronograma_items.append({
                "source": "control",
                "title": event.get("title") or event.get("type_label") or "Control SG-SST",
                "detail": event.get("detail") or "",
                "sede_codigo": event.get("sede_codigo") or "",
                "responsable": event.get("responsible") or "Seguimiento SG-SST",
                "date": event.get("fecha_evento") or "",
                "date_label": _sgsst_plan_short_date(event.get("fecha_evento")),
                "state_label": event.get("state_label") or "",
                "state_tone": ("risk" if event.get("state_key") == "vencido" else ("warn" if event.get("active") else "ok")),
                "phase_key": event.get("phase_key") or "operacion",
                "url": event.get("url_detail") or url_for("sst_plan_implementacion", vista="cronograma"),
            })
        cronograma_items.sort(key=lambda item: (item.get("date") or "9999-12-31", item.get("sede_codigo") or "ZZZ", item.get("title") or ""))
        cronograma_items = cronograma_items[:20]

        responsables_count = defaultdict(lambda: {"open": 0, "overdue": 0, "closed": 0, "critical": 0, "next_due": "", "items": []})
        for action in acciones:
            key = (action.get("responsable") or action.get("area_responsable") or "Sin responsable").strip()
            bucket = responsables_count[key]
            bucket["items"].append(action)
            if _sgsst_plan_is_action_closed(action.get("state_label")):
                bucket["closed"] += 1
            else:
                bucket["open"] += 1
            if action.get("overdue"):
                bucket["overdue"] += 1
            if action.get("priority_label") == "Critica":
                bucket["critical"] += 1
            due = action.get("fecha_objetivo") or ""
            if due and (not bucket["next_due"] or due < bucket["next_due"]):
                bucket["next_due"] = due
        responsables_rows = []
        for responsable, stats in responsables_count.items():
            responsables_rows.append({
                "responsable": responsable,
                "open": stats["open"],
                "overdue": stats["overdue"],
                "closed": stats["closed"],
                "critical": stats["critical"],
                "next_due": stats["next_due"],
                "next_due_label": _sgsst_plan_short_date(stats["next_due"]) if stats["next_due"] else "-",
                "tone": ("risk" if stats["overdue"] or stats["critical"] else ("warn" if stats["open"] else "ok")),
            })
        responsables_rows.sort(key=lambda item: (-item["overdue"], -item["critical"], -item["open"], item["responsable"]))

        roles_grouped = defaultdict(list)
        for role in roles:
            roles_grouped[role.get("grupo") or "Sin grupo"].append(role)
        role_groups = [{"grupo": grupo, "roles": sorted(items, key=lambda role: (int(role.get("orden_visual") or 0), role.get("rol") or ""))} for grupo, items in roles_grouped.items()]

        last_update_candidates = [
            marco.get("fecha_actualizacion"),
            marco.get("fecha_inicio"),
        ]
        for item in hallazgos[:25]:
            last_update_candidates.extend([item.get("updated_at"), item.get("created_at"), item.get("fecha_deteccion")])
        for item in acciones[:25]:
            last_update_candidates.extend([item.get("fecha_creacion"), item.get("fecha_objetivo")])
        for block in bloques:
            doc = block.get("doc") or {}
            last_update_candidates.append(doc.get("fecha_actualizacion"))
        last_update = None
        for candidate in last_update_candidates:
            parsed = _sgsst_plan_parse_date(candidate)
            if parsed and (last_update is None or parsed > last_update):
                last_update = parsed

        prefill = {
            "sede_codigo": ((request.args.get("prefill_sede") or selected_sede or "").strip().upper()),
            "modulo_origen": (request.args.get("prefill_modulo") or "").strip(),
            "titulo": (request.args.get("prefill_titulo") or "").strip(),
        }

        con.close()
        return {
            "sst_section": "plan",
            "view_mode": view_mode,
            "hero": {
                "title": "Plan de Implementacion SG-SST",
                "subtitle": "Implementacion progresiva del SG-SST integrada al SGI y conectada con la operacion diaria de las sedes.",
                "last_updated": _sgsst_plan_short_date(last_update) if last_update else _sgsst_plan_short_date(today_ref),
                "sedes_total": len(sedes_dashboard),
                "overall_pct": overall_pct,
                "overall_class": _sgsst_plan_progress_class(overall_pct),
                "overall_state": overall_state,
                "overall_tone": overall_tone,
            },
            "summary_cards": [
                {"label": "Sedes incluidas", "value": len(sedes_dashboard), "tone": "muted"},
                {"label": "Diagnostico iniciado", "value": diagnostico_iniciado, "tone": "blue"},
                {"label": "Diagnostico consolidado", "value": diagnostico_completo, "tone": "ok"},
                {"label": "Hallazgos abiertos", "value": hallazgos_abiertos, "tone": "risk"},
                {"label": "Acciones abiertas", "value": acciones_abiertas, "tone": "warn"},
                {"label": "Acciones vencidas", "value": acciones_vencidas, "tone": "risk"},
                {"label": "Acciones cerradas", "value": acciones_cerradas, "tone": "ok"},
                {"label": "Controles periodicos activos", "value": total_periodic_active, "tone": "blue"},
                {"label": "Documentacion pendiente", "value": sum(1 for docs in docs_by_sede.values() for doc in docs if str(doc.get('estado_revision') or '').strip().upper() == 'FALTANTE'), "tone": "warn"},
            ],
            "phase_cards": phase_cards,
            "library_cards": library_cards,
            "library_url": url_for("sgsst_documentacion_home"),
            "seguimiento_url": url_for("sst_plan"),
            "sedes_dashboard": sedes_dashboard,
            "selected_sede_row": selected_sede_row,
            "hallazgos": hallazgos,
            "hallazgos_abiertos": hallazgos_abiertos,
            "hallazgos_cerrados": hallazgos_cerrados,
            "acciones": acciones,
            "acciones_abiertas": acciones_abiertas,
            "acciones_cerradas": acciones_cerradas,
            "acciones_vencidas": acciones_vencidas,
            "cronograma_items": cronograma_items,
            "responsables_rows": responsables_rows[:12],
            "role_groups": role_groups,
            "roles_total": len(roles),
            "suggestions": suggestions[:8],
            "marco": marco,
            "open_form": open_form,
            "prefill": prefill,
            "sedes": sedes,
            "command_project_meta": command_project_meta,
            "command_project_scope": command_project_scope,
            "command_scope_options": list(SGSST_COMMAND_SCOPE_OPTIONS),
            "manual_hallazgos": manual_hallazgos,
            "hallazgo_states": SGSST_PLAN_HALLAZGO_STATES,
            "action_states": SGSST_PLAN_ACTION_STATES,
            "priority_options": SGSST_PLAN_PRIORITIES,
            "module_options": [
                "ART",
                "Documentacion",
                "Evacuacion",
                "Carteleria",
                "Luces de emergencia",
                "Matafuegos",
                "Desinfecciones",
                "Biblioteca documental",
                "General",
            ],
            "fuente_options": [
                "relevamiento interno",
                "visita ART",
                "RGRL",
                "inspeccion",
                "carteleria",
                "luces",
                "matafuegos",
                "desinfecciones",
                "otro",
            ],
            "today_iso": today_ref.isoformat(),
        }

    def _sst_matrix_component_map():
        return {item["key"]: dict(item) for item in SST_MATRIX_COMPONENTS}

    def _sst_matrix_phase_meta(phase_code):
        key = str(phase_code or "DIAGNOSTICO").strip().upper() or "DIAGNOSTICO"
        meta = dict(SST_MATRIX_PHASE_META.get(key) or SST_MATRIX_PHASE_META["DIAGNOSTICO"])
        meta["code"] = key
        return meta

    def _sst_matrix_normalize_component(value):
        key = str(value or "").strip().lower()
        aliases = {
            "art": "art",
            "visitas": "art",
            "visitas_art": "art",
            "matafuegos": "matafuegos",
            "luces": "luces",
            "luces_emergencia": "luces",
            "carteleria": "carteleria",
            "evacuacion": "evacuacion",
            "desinfeccion": "desinfeccion",
            "desinfecciones": "desinfeccion",
        }
        return aliases.get(key, "")

    def _sst_matrix_progress(value):
        try:
            return max(0, min(int(round(float(value or 0))), 100))
        except Exception:
            return 0

    def _sst_matrix_detail_url(current_args, sede_codigo, component_key):
        args = dict(current_args or {})
        args["detalle_sede"] = (_sst_clean_upper(sede_codigo) or "").strip().upper()
        args["detalle_componente"] = _sst_matrix_normalize_component(component_key)
        clean = {}
        for key, value in args.items():
            if value in ("", None, False):
                continue
            clean[key] = value
        return url_for("sst_matriz_general", **clean)

    def _sst_matrix_make_cell(
        component_key,
        sede_codigo,
        *,
        phase_code,
        step_label,
        progress_pct,
        pending_count=0,
        next_step="",
        summary_text="",
        open_url="",
        alert_tone="muted",
        is_no_data=False,
        is_no_aplica=False,
        extra=None,
    ):
        component = _sst_matrix_component_map().get(component_key) or {"key": component_key, "label": component_key.title(), "short": component_key.title()}
        phase_meta = _sst_matrix_phase_meta("NO_APLICA" if is_no_aplica else phase_code)
        progress = _sst_matrix_progress(progress_pct)
        pending = max(_sst_int_nonneg(pending_count), 0)
        step = (str(step_label or "").strip() or phase_meta["label"])
        summary = (str(summary_text or "").strip() or step)
        next_action = str(next_step or "").strip()
        has_pending = bool(
            pending
            or alert_tone in {"warn", "risk"}
            or phase_meta["code"] in {"DIAGNOSTICO", "PLANIFICACION", "IMPLEMENTACION"}
        ) and not is_no_aplica
        return {
            "component_key": component_key,
            "component_label": component.get("label") or component_key.title(),
            "component_short": component.get("short") or component_key.title(),
            "history_component": component.get("history_component") or component_key,
            "sede_codigo": (_sst_clean_upper(sede_codigo) or "").strip().upper(),
            "phase_code": phase_meta["code"],
            "phase_meta": phase_meta,
            "step_label": step,
            "summary_text": summary,
            "progress_pct": progress,
            "pending_count": pending,
            "pending_label": (f"{pending} pendiente(s)" if pending else "Sin pendientes"),
            "next_step": next_action,
            "open_url": open_url,
            "detail_url": "",
            "alert_tone": alert_tone,
            "is_no_data": bool(is_no_data),
            "is_no_aplica": bool(is_no_aplica),
            "has_pending": has_pending,
            "extra": dict(extra or {}),
        }

    def _sst_matrix_apply_scope_override(cell, scope_entry):
        base = dict(cell or {})
        if not base:
            return base
        scope_state = str((scope_entry or {}).get("scope_state") or "AUTO").strip().upper() or "AUTO"
        scope_note = str((scope_entry or {}).get("note") or "").strip()
        if scope_state == "NO_APLICA":
            overridden = _sst_matrix_make_cell(
                base.get("component_key") or "",
                base.get("sede_codigo") or "",
                phase_code="NO_APLICA",
                step_label="No aplica",
                progress_pct=0,
                pending_count=0,
                next_step="Sin accion requerida",
                summary_text=(scope_note or "Excluido por configuracion del proyecto"),
                open_url=base.get("open_url") or "",
                alert_tone="muted",
                is_no_aplica=True,
                extra=base.get("extra") or {},
            )
            overridden["extra"]["scope_state"] = scope_state
            overridden["extra"]["scope_note"] = scope_note
            overridden["extra"]["scope_override"] = True
            return overridden
        if scope_state == "FUERA_ALCANCE":
            overridden = _sst_matrix_make_cell(
                base.get("component_key") or "",
                base.get("sede_codigo") or "",
                phase_code="NO_APLICA",
                step_label="Fuera de alcance",
                progress_pct=0,
                pending_count=0,
                next_step="Sin accion requerida",
                summary_text=(scope_note or "Excluido temporalmente del alcance"),
                open_url=base.get("open_url") or "",
                alert_tone="muted",
                is_no_aplica=True,
                extra=base.get("extra") or {},
            )
            overridden["extra"]["scope_state"] = scope_state
            overridden["extra"]["scope_note"] = scope_note
            overridden["extra"]["scope_override"] = True
            return overridden
        if scope_note:
            extra = dict(base.get("extra") or {})
            extra["scope_note"] = scope_note
            base["extra"] = extra
        return base

    def _sst_matrix_collect_matafuegos_state(con, today_ref):
        summary = defaultdict(lambda: {
            "total": 0,
            "vencidos": 0,
            "proximos": 0,
            "fuera_servicio": 0,
            "incompletos": 0,
            "sin_ubicacion": 0,
            "sin_vencimiento": 0,
            "ultimo_vencimiento": "",
        })
        if not _table_exists(con, "matafuegos"):
            return summary
        rows = con.execute("""
            SELECT
                UPPER(COALESCE(sede, cod_sede, '')) AS sede_codigo,
                COALESCE(ubicacion, '') AS ubicacion,
                COALESCE(fecha_vencimiento, '') AS fecha_vencimiento,
                COALESCE(numero_serie, '') AS numero_serie,
                COALESCE(nro_extintor, '') AS nro_extintor,
                COALESCE(estado, '') AS estado
            FROM matafuegos
            WHERE COALESCE(activo, 1) = 1
        """).fetchall()
        upcoming_limit = today_ref + timedelta(days=45)
        for row in rows:
            sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            if not sede_codigo:
                continue
            bucket = summary[sede_codigo]
            bucket["total"] += 1
            ubicacion = str(_row_value(row, "ubicacion", "") or "").strip()
            fecha_vencimiento = str(_row_value(row, "fecha_vencimiento", "") or "").strip()
            estado = str(_row_value(row, "estado", "") or "").strip().lower()
            identificador = str(_row_value(row, "numero_serie", "") or "").strip() or str(_row_value(row, "nro_extintor", "") or "").strip()
            incomplete = False
            if not ubicacion:
                bucket["sin_ubicacion"] += 1
                incomplete = True
            if not fecha_vencimiento:
                bucket["sin_vencimiento"] += 1
                incomplete = True
            if not identificador:
                incomplete = True
            if incomplete:
                bucket["incompletos"] += 1
            due = _sst_calendar_parse_date(fecha_vencimiento)
            if due:
                if not bucket["ultimo_vencimiento"] or fecha_vencimiento > bucket["ultimo_vencimiento"]:
                    bucket["ultimo_vencimiento"] = fecha_vencimiento
                if due < today_ref:
                    bucket["vencidos"] += 1
                elif due <= upcoming_limit:
                    bucket["proximos"] += 1
            if "fuera" in estado:
                bucket["fuera_servicio"] += 1
        return summary

    def _sst_matrix_collect_evacuacion_state(con):
        summary = defaultdict(lambda: {
            "plan_count": 0,
            "routes_count": 0,
            "salidas_count": 0,
            "responsables_count": 0,
            "has_point": False,
            "markers_total": 0,
            "floors_count": 0,
            "last_plan_date": "",
        })
        if _table_exists(con, "sedes_planos"):
            for row in con.execute("""
                SELECT
                    UPPER(COALESCE(cod_sede, '')) AS sede_codigo,
                    COALESCE(fecha_carga, '') AS fecha_carga
                FROM sedes_planos
                WHERE LOWER(COALESCE(tipo, '')) = 'evacuacion'
            """).fetchall():
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                if not sede_codigo:
                    continue
                bucket = summary[sede_codigo]
                bucket["plan_count"] += 1
                fecha_carga = str(_row_value(row, "fecha_carga", "") or "").strip()
                if fecha_carga and fecha_carga > bucket["last_plan_date"]:
                    bucket["last_plan_date"] = fecha_carga
        if _table_exists(con, "evacuacion_responsables"):
            for row in con.execute("""
                SELECT
                    UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                    COALESCE(responsable, '') AS responsable
                FROM evacuacion_responsables
            """).fetchall():
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                responsable = str(_row_value(row, "responsable", "") or "").strip()
                if sede_codigo and responsable:
                    summary[sede_codigo]["responsables_count"] += 1
        sedes_cols = _table_cols(con, "sedes_mpd")
        if "url_punto_encuentro" in sedes_cols:
            for row in con.execute("""
                SELECT
                    UPPER(COALESCE(codigo, '')) AS sede_codigo,
                    COALESCE(url_punto_encuentro, '') AS url_punto_encuentro
                FROM sedes_mpd
            """).fetchall():
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                if not sede_codigo:
                    continue
                summary[sede_codigo]["has_point"] = bool(str(_row_value(row, "url_punto_encuentro", "") or "").strip())
        evacuacion_dir = os.path.join(BASE_DIR, "uploads", "evacuacion_planos")
        route_types = {"ruta_arriba", "ruta_derecha", "ruta_abajo", "ruta_izquierda"}
        if os.path.isdir(evacuacion_dir):
            for sede_codigo in os.listdir(evacuacion_dir):
                sede_path = os.path.join(evacuacion_dir, sede_codigo)
                if not os.path.isdir(sede_path):
                    continue
                sede_key = str(sede_codigo or "").strip().upper()
                if not sede_key:
                    continue
                for filename in os.listdir(sede_path):
                    if not filename.lower().endswith(".json"):
                        continue
                    path = os.path.join(sede_path, filename)
                    try:
                        with open(path, "r", encoding="utf-8") as fh:
                            payload = json.load(fh)
                    except Exception:
                        continue
                    markers = payload.get("markers") if isinstance(payload, dict) else []
                    if not isinstance(markers, list):
                        continue
                    bucket = summary[sede_key]
                    bucket["floors_count"] += 1
                    for marker in markers:
                        if not isinstance(marker, dict):
                            continue
                        marker_type = str(marker.get("type") or "").strip()
                        if not marker_type:
                            continue
                        bucket["markers_total"] += 1
                        if marker_type in route_types:
                            bucket["routes_count"] += 1
                        elif marker_type == "salida":
                            bucket["salidas_count"] += 1
        return summary

    def _sst_matrix_build_art_cell(sede_info, record, docs_by_type, today_ref):
        summary = _sst_visitas_art_build_summary(sede_info, record, docs_by_type, today_ref)
        docs_missing = sum(1 for item in (summary["rgrl"], summary["dec_351_79"]) if item.get("code") != "CARGADO")
        overdue_action = False
        action_date = _sst_calendar_parse_date(summary.get("fecha_programada"))
        if action_date and action_date < today_ref and not summary.get("ejecutado"):
            overdue_action = True
        if not summary.get("primary_record_id"):
            phase_code = "DIAGNOSTICO"
            step_label = "Sin visita"
            progress = 0
            pending = 1
            next_step = "Registrar primera visita"
            alert_tone = "muted"
            no_data = True
        elif summary.get("state_code") == "PROGRAMADA":
            phase_code = "PLANIFICACION"
            step_label = "Visita programada"
            progress = 35
            pending = 1
            next_step = "Realizar visita"
            alert_tone = "warn"
            no_data = False
        elif summary.get("observation_code") == "OBSERVADA" and not summary.get("accion_requerida"):
            phase_code = "DIAGNOSTICO"
            step_label = "Brecha detectada"
            progress = 45
            pending = 1
            next_step = "Definir accion"
            alert_tone = "warn"
            no_data = False
        elif summary.get("accion_requerida") and not summary.get("ejecutado"):
            phase_code = "PLANIFICACION"
            step_label = "Accion definida" if (summary.get("accion_responsable") or summary.get("fecha_programada")) else "Accion pendiente de definir"
            progress = 60 if (summary.get("accion_responsable") or summary.get("fecha_programada")) else 52
            pending = 1
            next_step = "Ejecutar accion" if step_label == "Accion definida" else "Definir responsable y fecha"
            alert_tone = "risk" if overdue_action else "warn"
            no_data = False
        elif summary.get("accion_requerida") and summary.get("ejecutado") and summary.get("state_code") != "CERRADA":
            phase_code = "IMPLEMENTACION"
            step_label = "Pendiente de verificacion"
            progress = 82
            pending = 1
            next_step = "Verificar cierre"
            alert_tone = "warn"
            no_data = False
        elif docs_missing > 0:
            phase_code = "DIAGNOSTICO"
            step_label = "Documentacion incompleta"
            progress = 50
            pending = docs_missing
            next_step = "Cargar documentacion"
            alert_tone = "warn"
            no_data = False
        else:
            phase_code = "OPERACION"
            step_label = "Documentacion vigente"
            progress = 100
            pending = 0
            next_step = "Mantener proxima visita"
            alert_tone = "ok"
            no_data = False
        summary_text = f"{summary['state_meta']['label']} · Docs {2 - docs_missing}/2"
        return _sst_matrix_make_cell(
            "art",
            sede_info.get("codigo"),
            phase_code=phase_code,
            step_label=step_label,
            progress_pct=progress,
            pending_count=pending,
            next_step=next_step,
            summary_text=summary_text,
            open_url=_sgsst_command_project_open_url("art", sede_info.get("codigo")),
            alert_tone=alert_tone,
            is_no_data=no_data,
            extra={
                "ultima_visita": summary.get("ultima_visita") or "",
                "docs_missing": docs_missing,
                "state_label": summary["state_meta"]["label"],
            },
        )

    def _sst_matrix_build_matafuegos_cell(sede_codigo, raw_summary):
        summary = dict(raw_summary or {})
        total = _sst_int_nonneg(summary.get("total"))
        vencidos = _sst_int_nonneg(summary.get("vencidos"))
        proximos = _sst_int_nonneg(summary.get("proximos"))
        fuera_servicio = _sst_int_nonneg(summary.get("fuera_servicio"))
        incompletos = _sst_int_nonneg(summary.get("incompletos"))
        if total <= 0:
            return _sst_matrix_make_cell(
                "matafuegos",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Sin inventario",
                progress_pct=0,
                pending_count=1,
                next_step="Cargar inventario base",
                summary_text="Sin equipos activos registrados",
                open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
                alert_tone="muted",
                is_no_data=True,
            )
        if incompletos > 0:
            progress = _sst_matrix_progress(((total - incompletos) / max(total, 1)) * 60)
            return _sst_matrix_make_cell(
                "matafuegos",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Inventario incompleto",
                progress_pct=progress,
                pending_count=incompletos,
                next_step="Completar ubicacion y vencimiento",
                summary_text=f"{total} equipo(s) · {incompletos} con datos faltantes",
                open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
                alert_tone="warn",
            )
        if fuera_servicio > 0:
            return _sst_matrix_make_cell(
                "matafuegos",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Fuera de servicio",
                progress_pct=35,
                pending_count=fuera_servicio,
                next_step="Regularizar equipos inactivos",
                summary_text=f"{total} equipo(s) activos",
                open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
                alert_tone="risk",
            )
        if vencidos > 0:
            return _sst_matrix_make_cell(
                "matafuegos",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Vencido",
                progress_pct=45,
                pending_count=vencidos,
                next_step="Gestionar recarga urgente",
                summary_text=f"{vencidos} vencido(s) · {proximos} proximo(s)",
                open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
                alert_tone="risk",
            )
        if proximos > 0:
            return _sst_matrix_make_cell(
                "matafuegos",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Proximo vencimiento",
                progress_pct=82,
                pending_count=proximos,
                next_step="Programar recarga",
                summary_text=f"{total} equipo(s) · {proximos} proximos",
                open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
                alert_tone="warn",
            )
        return _sst_matrix_make_cell(
            "matafuegos",
            sede_codigo,
            phase_code="OPERACION",
            step_label="Al dia",
            progress_pct=100,
            pending_count=0,
            next_step="Mantener control vigente",
            summary_text=f"{total} equipo(s) activos",
            open_url=_sgsst_command_project_open_url("matafuegos", sede_codigo),
            alert_tone="ok",
        )

    def _sst_matrix_build_luces_cell(sede_info, summary):
        row = dict(summary or _sst_luces_empty_summary(sede_info))
        sede_codigo = (_row_value(sede_info, "codigo", "") or "").strip().upper()
        state_code = str(row.get("state_code") or "").strip().upper()
        faltantes = _sst_int_nonneg(row.get("cantidad_faltante"))
        fuera_servicio = _sst_int_nonneg(row.get("cantidad_fuera_servicio"))
        pending_total = faltantes + fuera_servicio
        if not _sst_bool_flag(row.get("aplica", 1)):
            return _sst_matrix_make_cell(
                "luces",
                sede_codigo,
                phase_code="NO_APLICA",
                step_label="No aplica",
                progress_pct=0,
                pending_count=0,
                next_step="Sin accion requerida",
                summary_text=(str(row.get("motivo_no_aplica") or "").strip() or "Sin aplicacion operativa"),
                open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                alert_tone="muted",
                is_no_aplica=True,
            )
        if int(row.get("record_count") or 0) <= 0 or state_code == "SIN_RELEVAR":
            return _sst_matrix_make_cell(
                "luces",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Sin relevar",
                progress_pct=0,
                pending_count=max(_sst_int_nonneg(row.get("cantidad_requerida")), 1),
                next_step="Registrar relevamiento",
                summary_text="Sin base operativa cargada",
                open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                alert_tone="muted",
                is_no_data=True,
            )
        if state_code == "RELEVADO":
            if pending_total > 0:
                return _sst_matrix_make_cell(
                    "luces",
                    sede_codigo,
                    phase_code="PLANIFICACION",
                    step_label="Accion pendiente de definir",
                    progress_pct=55,
                    pending_count=pending_total,
                    next_step="Definir compra o reparacion",
                    summary_text=f"{row.get('cantidad_instalada', 0)} instaladas / {row.get('cantidad_requerida', 0)} requeridas",
                    open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                    alert_tone="warn",
                )
            return _sst_matrix_make_cell(
                "luces",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Operativas",
                progress_pct=100,
                pending_count=0,
                next_step="Mantener pruebas periodicas",
                summary_text=f"{row.get('cantidad_operativa', 0)} operativas",
                open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                alert_tone="ok",
            )
        implementation_map = {
            "PENDIENTE_DE_SOLICITUD": ("IMPLEMENTACION", "Pendiente de solicitud", 66, "Enviar solicitud"),
            "EN_PROCESO_DE_COMPRA": ("IMPLEMENTACION", "Esperando compra", 72, "Confirmar provision"),
            "MATERIAL_RECIBIDO": ("IMPLEMENTACION", "Material recibido", 82, "Programar instalacion"),
            "INSTALACION_PROGRAMADA": ("IMPLEMENTACION", "Pendiente de instalacion", 90, "Verificar colocacion"),
        }
        if state_code in implementation_map:
            phase_code, step_label, progress, next_step = implementation_map[state_code]
            return _sst_matrix_make_cell(
                "luces",
                sede_codigo,
                phase_code=phase_code,
                step_label=step_label,
                progress_pct=progress,
                pending_count=max(pending_total, 1),
                next_step=next_step,
                summary_text=f"{row.get('cantidad_operativa', 0)} operativas / {row.get('cantidad_requerida', 0)} requeridas",
                open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                alert_tone="warn",
            )
        if state_code == "MANTENIMIENTO" or fuera_servicio > 0:
            return _sst_matrix_make_cell(
                "luces",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Pendiente de reparacion" if fuera_servicio > 0 else "Control programado",
                progress_pct=78,
                pending_count=max(fuera_servicio, 1 if state_code == "MANTENIMIENTO" else 0),
                next_step="Registrar mantenimiento",
                summary_text=f"{row.get('cantidad_operativa', 0)} operativas · {fuera_servicio} fuera de servicio",
                open_url=_sgsst_command_project_open_url("luces", sede_codigo),
                alert_tone="warn" if fuera_servicio <= 0 else "risk",
            )
        return _sst_matrix_make_cell(
            "luces",
            sede_codigo,
            phase_code="OPERACION",
            step_label="Operativas",
            progress_pct=100 if pending_total <= 0 else 84,
            pending_count=pending_total,
            next_step="Mantener control vigente",
            summary_text=f"{row.get('cantidad_operativa', 0)} operativas / {row.get('cantidad_requerida', 0)} requeridas",
            open_url=_sgsst_command_project_open_url("luces", sede_codigo),
            alert_tone="ok" if pending_total <= 0 else "warn",
        )

    def _sst_matrix_build_carteleria_cell(sede_info, summary):
        row = dict(summary or _sst_carteleria_empty_summary(sede_info))
        sede_codigo = (_row_value(sede_info, "codigo", "") or "").strip().upper()
        state_code = str(row.get("state_code") or "").strip().upper()
        faltantes = _sst_int_nonneg(row.get("faltantes"))
        applies_count = sum(1 for item in (row.get("checklist_items") or []) if str(item.get("aplica") or "").strip().upper() == "SI")
        if applies_count <= 0 and int(row.get("record_count") or 0) > 0 and int(row.get("tipos_sin_relevar") or 0) == 0:
            return _sst_matrix_make_cell(
                "carteleria",
                sede_codigo,
                phase_code="NO_APLICA",
                step_label="No aplica",
                progress_pct=0,
                pending_count=0,
                next_step="Sin accion requerida",
                summary_text="Sin carteleria requerida para la sede",
                open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
                alert_tone="muted",
                is_no_aplica=True,
            )
        if int(row.get("record_count") or 0) <= 0 or state_code == "NO_RELEVADO":
            return _sst_matrix_make_cell(
                "carteleria",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Sin relevar",
                progress_pct=0,
                pending_count=max(int(row.get("tipos_sin_relevar") or 0), 1),
                next_step="Iniciar relevamiento",
                summary_text="Sin base operativa cargada",
                open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
                alert_tone="muted",
                is_no_data=True,
            )
        if state_code == "RELEVADO":
            if faltantes > 0:
                return _sst_matrix_make_cell(
                    "carteleria",
                    sede_codigo,
                    phase_code="PLANIFICACION",
                    step_label="Accion pendiente de definir",
                    progress_pct=56,
                    pending_count=faltantes,
                    next_step="Definir adquisicion",
                    summary_text=f"{row.get('cantidad_instalada', 0)} instaladas / {row.get('cantidad_requerida', 0)} requeridas",
                    open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
                    alert_tone="warn",
                )
            return _sst_matrix_make_cell(
                "carteleria",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Correcta",
                progress_pct=100,
                pending_count=0,
                next_step="Mantener control visual",
                summary_text=f"{row.get('cantidad_instalada', 0)} instaladas",
                open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
                alert_tone="ok",
            )
        implementation_map = {
            "PENDIENTE_SOLICITUD": ("IMPLEMENTACION", "Pendiente de solicitud", 66, "Enviar solicitud"),
            "COMPRA_EN_PROCESO": ("IMPLEMENTACION", "Esperando compra", 74, "Confirmar provision"),
            "MATERIAL_RECIBIDO": ("IMPLEMENTACION", "Material recibido", 84, "Programar colocacion"),
            "INSTALACION_PROGRAMADA": ("IMPLEMENTACION", "Pendiente de colocacion", 90, "Verificar instalacion"),
        }
        if state_code in implementation_map:
            phase_code, step_label, progress, next_step = implementation_map[state_code]
            return _sst_matrix_make_cell(
                "carteleria",
                sede_codigo,
                phase_code=phase_code,
                step_label=step_label,
                progress_pct=progress,
                pending_count=max(faltantes, 1),
                next_step=next_step,
                summary_text=f"{row.get('cantidad_instalada', 0)} instaladas / {row.get('cantidad_requerida', 0)} requeridas",
                open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
                alert_tone="warn",
            )
        return _sst_matrix_make_cell(
            "carteleria",
            sede_codigo,
            phase_code="OPERACION",
            step_label="Correcta" if faltantes <= 0 else "Pendiente de reposicion",
            progress_pct=100 if faltantes <= 0 else 82,
            pending_count=faltantes,
            next_step="Mantener control visual",
            summary_text=f"{row.get('cantidad_instalada', 0)} instaladas / {row.get('cantidad_requerida', 0)} requeridas",
            open_url=_sgsst_command_project_open_url("carteleria", sede_codigo),
            alert_tone="ok" if faltantes <= 0 else "warn",
        )

    def _sst_matrix_build_evacuacion_cell(sede_codigo, raw_summary):
        summary = dict(raw_summary or {})
        checks = [
            ("plano", int(summary.get("plan_count") or 0) > 0, "Cargar plano"),
            ("rutas", int(summary.get("routes_count") or 0) > 0, "Completar rutas"),
            ("salidas", int(summary.get("salidas_count") or 0) > 0, "Registrar salidas"),
            ("responsables", int(summary.get("responsables_count") or 0) > 0, "Definir responsables"),
            ("punto", bool(summary.get("has_point")), "Definir punto de encuentro"),
        ]
        completed = sum(1 for _, ok, _ in checks if ok)
        pending_labels = [label for _, ok, label in checks if not ok]
        progress = _sst_matrix_progress((completed / len(checks)) * 100)
        if completed == 0:
            return _sst_matrix_make_cell(
                "evacuacion",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Sin relevar",
                progress_pct=0,
                pending_count=len(checks),
                next_step="Cargar plano de evacuacion",
                summary_text="Sin plano ni configuracion asociada",
                open_url=_sgsst_command_project_open_url("evacuacion", sede_codigo),
                alert_tone="muted",
                is_no_data=True,
            )
        if not checks[0][1]:
            return _sst_matrix_make_cell(
                "evacuacion",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Sin plano cargado",
                progress_pct=progress,
                pending_count=len(pending_labels),
                next_step="Cargar plano base",
                summary_text=f"{completed}/{len(checks)} requisito(s) resuelto(s)",
                open_url=_sgsst_command_project_open_url("evacuacion", sede_codigo),
                alert_tone="risk",
            )
        if not checks[1][1] or not checks[2][1]:
            return _sst_matrix_make_cell(
                "evacuacion",
                sede_codigo,
                phase_code="DIAGNOSTICO",
                step_label="Relevamiento incompleto",
                progress_pct=progress,
                pending_count=len(pending_labels),
                next_step=(pending_labels[0] if pending_labels else "Completar relevamiento"),
                summary_text=f"{int(summary.get('routes_count') or 0)} ruta(s) · {int(summary.get('salidas_count') or 0)} salida(s)",
                open_url=_sgsst_command_project_open_url("evacuacion", sede_codigo),
                alert_tone="warn",
            )
        if not checks[3][1] or not checks[4][1]:
            step_label = "Completar definiciones"
            if not checks[3][1] and checks[4][1]:
                step_label = "Definir responsables"
            elif checks[3][1] and not checks[4][1]:
                step_label = "Definir punto de encuentro"
            return _sst_matrix_make_cell(
                "evacuacion",
                sede_codigo,
                phase_code="IMPLEMENTACION",
                step_label=step_label,
                progress_pct=progress,
                pending_count=len(pending_labels),
                next_step=(pending_labels[0] if pending_labels else "Preparar simulacro"),
                summary_text=f"{int(summary.get('markers_total') or 0)} marcador(es) en plano",
                open_url=_sgsst_command_project_open_url("evacuacion", sede_codigo),
                alert_tone="warn",
            )
        return _sst_matrix_make_cell(
            "evacuacion",
            sede_codigo,
            phase_code="OPERACION",
            step_label="Plan vigente",
            progress_pct=100,
            pending_count=0,
            next_step="Mantener revision periodica",
            summary_text=f"{int(summary.get('routes_count') or 0)} ruta(s) · {int(summary.get('responsables_count') or 0)} responsable(s)",
            open_url=_sgsst_command_project_open_url("evacuacion", sede_codigo),
            alert_tone="ok",
        )

    def _sst_matrix_build_desinfeccion_cell(sede_info, summary):
        row = dict(summary or _sst_desinf_empty_summary(sede_info))
        sede_codigo = (_row_value(sede_info, "codigo", "") or "").strip().upper()
        state_code = str(row.get("state_code") or "").strip().upper()
        if int(row.get("record_count") or 0) <= 0 or state_code == "SIN_REGISTRO":
            return _sst_matrix_make_cell(
                "desinfeccion",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Sin antecedentes",
                progress_pct=0,
                pending_count=1,
                next_step="Registrar primera programacion",
                summary_text="Sin intervencion registrada",
                open_url=_sgsst_command_project_open_url("desinfeccion", sede_codigo),
                alert_tone="muted",
                is_no_data=True,
            )
        if state_code == "VENCIDA":
            return _sst_matrix_make_cell(
                "desinfeccion",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Vencida",
                progress_pct=35,
                pending_count=1,
                next_step="Reprogramar intervencion",
                summary_text=f"Ultima {row.get('ultima_desinfeccion') or '-'}",
                open_url=_sgsst_command_project_open_url("desinfeccion", sede_codigo),
                alert_tone="risk",
            )
        if state_code == "PROGRAMADA":
            return _sst_matrix_make_cell(
                "desinfeccion",
                sede_codigo,
                phase_code="OPERACION",
                step_label="Programada",
                progress_pct=72,
                pending_count=1,
                next_step="Coordinar ejecucion",
                summary_text=f"Proxima {row.get('proxima_prevista') or '-'}",
                open_url=_sgsst_command_project_open_url("desinfeccion", sede_codigo),
                alert_tone="warn",
            )
        if state_code in {"OBSERVADA", "CANCELADA", "PENDIENTE_DE_PROGRAMACION"}:
            step_label = {
                "OBSERVADA": "Pendiente de correccion",
                "CANCELADA": "Reprogramar",
                "PENDIENTE_DE_PROGRAMACION": "Pendiente de programacion",
            }.get(state_code, "Pendiente")
            return _sst_matrix_make_cell(
                "desinfeccion",
                sede_codigo,
                phase_code="OPERACION",
                step_label=step_label,
                progress_pct=48,
                pending_count=1,
                next_step=_sst_desinf_next_action(state_code),
                summary_text=f"Ultima {row.get('ultima_desinfeccion') or '-'}",
                open_url=_sgsst_command_project_open_url("desinfeccion", sede_codigo),
                alert_tone="warn",
            )
        return _sst_matrix_make_cell(
            "desinfeccion",
            sede_codigo,
            phase_code="OPERACION",
            step_label="Al dia",
            progress_pct=100,
            pending_count=0,
            next_step="Mantener cronograma",
            summary_text=f"Ultima {row.get('ultima_desinfeccion') or '-'}",
            open_url=_sgsst_command_project_open_url("desinfeccion", sede_codigo),
            alert_tone="ok",
        )

    def _sst_matrix_cell_matches(cell, phase_filter="", step_filter="", pending_only=False, no_data_only=False):
        if phase_filter and str(cell.get("phase_code") or "").strip().upper() != str(phase_filter or "").strip().upper():
            return False
        if step_filter and str(cell.get("step_label") or "").strip() != str(step_filter or "").strip():
            return False
        if pending_only and not bool(cell.get("has_pending")):
            return False
        if no_data_only and not bool(cell.get("is_no_data")):
            return False
        return True

    def build_sgsst_matriz_general_context():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)
        ensure_sst_carteleria_tables(con)
        ensure_sst_luces_tables(con)
        ensure_sst_desinfecciones_tables(con)
        ensure_sst_operativo_historial_tables(con)
        ensure_sgsst_implementation_tables(con)
        _, command_project_scope = _sgsst_command_load_settings(con)

        today_ref = date.today()
        sedes_cols = _table_cols(con, "sedes_mpd")
        region_expr = "''"
        if "region" in sedes_cols:
            region_expr = "COALESCE(region, '')"
        elif "ciudad" in sedes_cols:
            region_expr = "COALESCE(ciudad, '')"
        elif "fuero" in sedes_cols:
            region_expr = "COALESCE(fuero, '')"
        sedes = []
        for row in con.execute(f"""
            SELECT
                UPPER(COALESCE(codigo, '')) AS codigo,
                COALESCE(nombre, '') AS nombre,
                {region_expr} AS region,
                COALESCE(fuero, '') AS fuero
            FROM sedes_mpd
            WHERE TRIM(COALESCE(codigo, '')) <> ''
              AND COALESCE(activa, 1) = 1
            ORDER BY codigo
        """).fetchall():
            sede_codigo = (_row_value(row, "codigo", "") or "").strip().upper()
            if not sede_codigo:
                continue
            fuero_raw = (_row_value(row, "fuero", "") or "").strip()
            fuero_class, fuero_color = _sst_sede_fuero_style(sede_codigo, fuero_raw)
            sedes.append({
                "codigo": sede_codigo,
                "nombre": (_row_value(row, "nombre", "") or "").strip(),
                "region": (_row_value(row, "region", "") or "").strip(),
                "fuero": fuero_raw,
                "fuero_class": fuero_class,
                "fuero_color": fuero_color,
            })

        latest_visit_by_sede = {}
        for row in con.execute("""
            SELECT
                id,
                UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                COALESCE(fecha, '') AS fecha,
                COALESCE(tipo_visita, '') AS tipo_visita,
                COALESCE(responsable, '') AS responsable,
                COALESCE(estado, '') AS estado,
                COALESCE(observaciones, '') AS observaciones,
                COALESCE(observacion_art, '') AS observacion_art,
                COALESCE(accion_requerida, '') AS accion_requerida,
                COALESCE(accion_responsable, '') AS accion_responsable,
                COALESCE(fecha_programada, '') AS fecha_programada,
                COALESCE(ejecutado, 0) AS ejecutado,
                COALESCE(fecha_ejecucion, '') AS fecha_ejecucion,
                COALESCE(evidencia_url, '') AS evidencia_url,
                COALESCE(seguimiento_id, 0) AS seguimiento_id
            FROM sst_visitas
            ORDER BY UPPER(COALESCE(sede_codigo, '')), date(COALESCE(fecha, '')) DESC, id DESC
        """).fetchall():
            sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            if sede_codigo and sede_codigo not in latest_visit_by_sede:
                latest_visit_by_sede[sede_codigo] = dict(row)

        docs_by_sede = defaultdict(dict)
        for row in con.execute("""
            SELECT
                id,
                UPPER(COALESCE(sede_codigo, '')) AS sede_codigo,
                UPPER(COALESCE(tipo, '')) AS tipo,
                COALESCE(fecha_documento, '') AS fecha_documento,
                COALESCE(fecha_carga, '') AS fecha_carga,
                COALESCE(archivo, '') AS archivo,
                COALESCE(drive_url, '') AS drive_url,
                COALESCE(estado_revision, '') AS estado_revision,
                COALESCE(notas, '') AS notas
            FROM sst_documentos
            WHERE UPPER(COALESCE(tipo, '')) IN ('RGRL', 'DEC_351_79')
            ORDER BY UPPER(COALESCE(sede_codigo, '')), UPPER(COALESCE(tipo, '')), COALESCE(fecha_documento, fecha_carga, '') DESC, id DESC
        """).fetchall():
            sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
            doc_type = (_row_value(row, "tipo", "") or "").strip().upper()
            if sede_codigo and doc_type and doc_type not in docs_by_sede[sede_codigo]:
                docs_by_sede[sede_codigo][doc_type] = dict(row)

        cart_summary = _sst_carteleria_aggregate_by_sede(_sst_fetch_carteleria_records(con))
        luces_summary = _sst_luces_aggregate_by_sede(_sst_fetch_luces_records(con))
        desinf_summary = _sst_desinf_aggregate_by_sede(_sst_desinf_fetch_records(con))
        mata_summary = _sst_matrix_collect_matafuegos_state(con, today_ref)
        evac_summary = _sst_matrix_collect_evacuacion_state(con)

        current_args = request.args.to_dict(flat=True)
        component_filter = _sst_matrix_normalize_component(request.args.get("componente"))
        phase_filter = str(request.args.get("fase") or "").strip().upper()
        if phase_filter and phase_filter not in SST_MATRIX_PHASE_META:
            phase_filter = ""
        sede_filter = (_sst_clean_upper(request.args.get("sede")) or "").strip().upper()
        region_filter = str(request.args.get("region") or "").strip()
        step_filter = str(request.args.get("paso") or "").strip()
        pending_only = _sst_bool_flag(request.args.get("con_pendientes"))
        no_data_only = _sst_bool_flag(request.args.get("sin_datos"))
        detail_sede = (_sst_clean_upper(request.args.get("detalle_sede")) or "").strip().upper()
        detail_component = _sst_matrix_normalize_component(request.args.get("detalle_componente"))

        visible_components = [item for item in SST_MATRIX_COMPONENTS if not component_filter or item["key"] == component_filter]
        visible_component_keys = [item["key"] for item in visible_components]

        step_values = set()
        rows = []
        for sede in sedes:
            sede_codigo = sede["codigo"]
            cells_by_key = {}
            cells_by_key["art"] = _sst_matrix_build_art_cell(sede, latest_visit_by_sede.get(sede_codigo), docs_by_sede.get(sede_codigo, {}), today_ref)
            cells_by_key["matafuegos"] = _sst_matrix_build_matafuegos_cell(sede_codigo, mata_summary.get(sede_codigo))
            cells_by_key["luces"] = _sst_matrix_build_luces_cell(sede, luces_summary.get(sede_codigo))
            cells_by_key["carteleria"] = _sst_matrix_build_carteleria_cell(sede, cart_summary.get(sede_codigo))
            cells_by_key["evacuacion"] = _sst_matrix_build_evacuacion_cell(sede_codigo, evac_summary.get(sede_codigo))
            cells_by_key["desinfeccion"] = _sst_matrix_build_desinfeccion_cell(sede, desinf_summary.get(sede_codigo))
            for component_key, cell in list(cells_by_key.items()):
                project_key = str((_sst_matrix_component_map().get(component_key) or {}).get("project_key") or component_key).strip().lower()
                scope_entry = dict(command_project_scope.get(project_key, {}) or {}).get(sede_codigo)
                cell = _sst_matrix_apply_scope_override(cell, scope_entry)
                cells_by_key[component_key] = cell
                cell["detail_url"] = _sst_matrix_detail_url(current_args, sede_codigo, component_key)
                step_values.add(cell["step_label"])
            candidate_cells = [cells_by_key[key] for key in visible_component_keys if key in cells_by_key]
            if sede_filter and sede_codigo != sede_filter:
                continue
            if region_filter and sede["region"] != region_filter:
                continue
            if not any(_sst_matrix_cell_matches(cell, phase_filter, step_filter, pending_only, no_data_only) for cell in candidate_cells):
                continue
            row = dict(sede)
            row["cells_by_key"] = cells_by_key
            row["cells"] = candidate_cells
            row["pending_cells"] = sum(1 for cell in candidate_cells if cell["has_pending"])
            rows.append(row)

        selected_cell = None
        if detail_sede and detail_component:
            for row in rows:
                if row["codigo"] != detail_sede:
                    continue
                selected_cell = dict(row["cells_by_key"].get(detail_component) or {})
                if selected_cell:
                    history_rows = _sst_fetch_historial_rows(con, selected_cell.get("history_component"), detail_sede)
                    selected_cell["history_rows"] = history_rows
                    selected_cell["sede_nombre"] = row["nombre"]
                    selected_cell["region"] = row["region"]
                    selected_cell["fuero"] = row["fuero"]
                break

        summary_counts = defaultdict(int)
        pending_cells_total = 0
        no_data_cells_total = 0
        for row in rows:
            for cell in row["cells"]:
                summary_counts[cell["phase_code"]] += 1
                if cell["has_pending"]:
                    pending_cells_total += 1
                if cell["is_no_data"]:
                    no_data_cells_total += 1

        region_options = sorted({item["region"] for item in sedes if item["region"]})
        step_options = sorted(step_values)
        con.close()
        return {
            "sst_section": "matriz",
            "matrix_rows": rows,
            "visible_components": visible_components,
            "component_options": list(SST_MATRIX_COMPONENTS),
            "phase_options": [
                {"code": key, "label": value["label"]}
                for key, value in sorted(SST_MATRIX_PHASE_META.items(), key=lambda item: item[1]["order"])
            ],
            "step_options": step_options,
            "region_options": region_options,
            "filters": {
                "sede": sede_filter,
                "componente": component_filter,
                "fase": phase_filter,
                "paso": step_filter,
                "region": region_filter,
                "con_pendientes": pending_only,
                "sin_datos": no_data_only,
            },
            "selected_cell": selected_cell,
            "clear_url": url_for("sst_matriz_general"),
            "summary_cards": [
                {"label": "Sedes visibles", "value": len(rows), "tone": "muted"},
                {"label": "Diagnostico", "value": summary_counts.get("DIAGNOSTICO", 0), "tone": "diagnostico"},
                {"label": "Planificacion", "value": summary_counts.get("PLANIFICACION", 0), "tone": "planificacion"},
                {"label": "Implementacion", "value": summary_counts.get("IMPLEMENTACION", 0), "tone": "implementacion"},
                {"label": "Operacion", "value": summary_counts.get("OPERACION", 0), "tone": "operacion"},
                {"label": "Con pendientes", "value": pending_cells_total, "tone": "warn"},
                {"label": "Sin datos", "value": no_data_cells_total, "tone": "muted"},
            ],
        }

    @app.route("/sst/plan-implementacion", methods=["GET", "POST"], endpoint="sst_plan_implementacion")
    def sst_plan_implementacion():
        selected_sede = (request.values.get("sede") or request.values.get("prefill_sede") or "").strip().upper()
        view_mode = (request.values.get("vista") or "general").strip().lower()
        open_form = (request.values.get("form") or "").strip().lower()

        if request.method == "POST":
            con = get_db()
            ensure_sst_general_table(con)
            ensure_sst_plan_tables(con)
            ensure_sgsst_implementation_tables(con)
            ensure_sst_visitas_docs_tables(con)
            seed_sgsst_documentacion(con)
            intent = (request.form.get("intent") or "").strip().lower()
            user_name = _sst_current_user()
            now = _sst_now_ts()
            valid_sedes = {
                str(_row_value(row, "codigo", "") or "").strip().upper()
                for row in con.execute("SELECT codigo FROM sedes_mpd").fetchall()
            }

            if intent == "hallazgo":
                sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                if not sede_codigo or sede_codigo not in valid_sedes:
                    flash("Selecciona una sede valida para el hallazgo.", "warning")
                    con.close()
                    return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=selected_sede or None, form="hallazgo"))
                if not titulo:
                    flash("El hallazgo necesita un titulo.", "warning")
                    con.close()
                    return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo, form="hallazgo"))

                con.execute("""
                    INSERT INTO sgsst_plan_hallazgos(
                        sede_codigo, piso, dependencia, modulo_origen, registro_origen_id,
                        categoria, titulo, descripcion, fecha_deteccion, detectado_por, fuente,
                        prioridad, estado, evidencia_inicial, observaciones, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sede_codigo,
                    (request.form.get("piso") or "").strip(),
                    (request.form.get("dependencia") or "").strip(),
                    (request.form.get("modulo_origen") or "").strip(),
                    (request.form.get("registro_origen_id") or "").strip(),
                    (request.form.get("categoria") or "").strip(),
                    titulo,
                    (request.form.get("descripcion") or "").strip(),
                    (request.form.get("fecha_deteccion") or date.today().isoformat()),
                    (request.form.get("detectado_por") or user_name).strip(),
                    (request.form.get("fuente") or "relevamiento interno").strip(),
                    _sgsst_plan_priority_label(request.form.get("prioridad") or "Media"),
                    _sgsst_plan_hallazgo_state_label(request.form.get("estado") or "Detectado"),
                    (request.form.get("evidencia_inicial") or "").strip(),
                    (request.form.get("observaciones") or "").strip(),
                    now,
                    now,
                ))
                con.commit()
                con.close()
                flash("Hallazgo SG-SST creado.", "success")
                return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo, form="hallazgo"))

            if intent == "accion":
                sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
                titulo = (request.form.get("titulo") or "").strip()
                if not sede_codigo or sede_codigo not in valid_sedes:
                    flash("Selecciona una sede valida para la accion.", "warning")
                    con.close()
                    return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=selected_sede or None, form="accion"))
                if not titulo:
                    flash("La accion necesita un titulo.", "warning")
                    con.close()
                    return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo, form="accion"))

                hallazgo_id = 0
                try:
                    hallazgo_id = int(request.form.get("hallazgo_id") or 0)
                except Exception:
                    hallazgo_id = 0
                if hallazgo_id > 0:
                    row = con.execute("SELECT id FROM sgsst_plan_hallazgos WHERE id = ?", (hallazgo_id,)).fetchone()
                    if not row:
                        hallazgo_id = 0

                fecha_creacion = (request.form.get("fecha_creacion") or date.today().isoformat()).strip()
                fecha_objetivo = (request.form.get("fecha_objetivo") or "").strip()
                if fecha_objetivo:
                    fecha_creacion_dt = _sgsst_plan_parse_date(fecha_creacion)
                    fecha_objetivo_dt = _sgsst_plan_parse_date(fecha_objetivo)
                    if fecha_creacion_dt and fecha_objetivo_dt and fecha_objetivo_dt < fecha_creacion_dt:
                        flash("La fecha objetivo no puede ser anterior a la fecha de creacion.", "warning")
                        con.close()
                        return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo, form="accion"))

                con.execute("""
                    INSERT INTO sgsst_plan_acciones(
                        hallazgo_id, sede_codigo, modulo_origen, titulo, accion_requerida,
                        responsable, area_responsable, prioridad, fecha_creacion, fecha_objetivo,
                        estado, avance_pct, evidencia, costo_estimado, compra_requerida,
                        intervencion_requerida, observaciones, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    (hallazgo_id or None),
                    sede_codigo,
                    (request.form.get("modulo_origen") or "").strip(),
                    titulo,
                    (request.form.get("accion_requerida") or "").strip(),
                    (request.form.get("responsable") or "").strip(),
                    (request.form.get("area_responsable") or "").strip(),
                    _sgsst_plan_priority_label(request.form.get("prioridad") or "Media"),
                    fecha_creacion,
                    fecha_objetivo or None,
                    _sgsst_plan_action_state_label(request.form.get("estado") or "Pendiente"),
                    int(request.form.get("avance_pct") or 0),
                    (request.form.get("evidencia") or "").strip(),
                    (float(request.form.get("costo_estimado") or 0) if str(request.form.get("costo_estimado") or "").strip() else None),
                    _sst_bool_flag(request.form.get("compra_requerida")),
                    _sst_bool_flag(request.form.get("intervencion_requerida")),
                    (request.form.get("observaciones") or "").strip(),
                    now,
                    now,
                ))
                con.commit()
                con.close()
                flash("Accion del plan creada.", "success")
                return redirect(url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo, form="accion"))

            con.close()

        context = build_sgsst_plan_implementation_context(view_mode=view_mode, selected_sede=selected_sede, open_form=open_form)
        return render_template("sst_plan_implementacion.html", **context)

    @app.route("/sst/proyectos/<project_key>/configuracion", methods=["GET", "POST"], endpoint="sst_project_config")
    def sst_project_config(project_key):
        project_key = (project_key or "").strip().lower()
        project = _sgsst_command_project_map().get(project_key)
        if not project:
            flash("Proyecto SG-SST inexistente.", "warning")
            return redirect(url_for("sst_calendario_operativo"))

        return_args = {
            "year": (request.values.get("year") or "").strip(),
            "month": (request.values.get("month") or "").strip(),
            "sede": (request.values.get("sede") or "").strip().upper(),
            "tipo": (request.values.get("tipo") or "").strip().lower(),
            "estado": (request.values.get("estado") or "").strip().lower(),
            "region": (request.values.get("region") or "").strip(),
            "responsable": (request.values.get("responsable") or "").strip(),
            "fase": (request.values.get("fase") or "").strip().lower(),
            "quick": (request.values.get("quick") or "").strip().lower(),
        }
        return_clean = {key: value for key, value in return_args.items() if value not in {"", None}}
        return_url = url_for("sst_calendario_operativo", **return_clean) if return_clean else url_for("sst_calendario_operativo")

        if request.method == "POST":
            con = get_db()
            ensure_sgsst_implementation_tables(con)
            now = _sst_now_ts()
            valid_sedes = {
                str(row["codigo"] or "").strip().upper()
                for row in con.execute("SELECT codigo FROM sedes_mpd WHERE TRIM(COALESCE(codigo, '')) <> ''").fetchall()
            }
            existing = con.execute("SELECT project_key FROM sgsst_command_projects WHERE project_key = ?", (project_key,)).fetchone()
            if existing:
                con.execute("""
                    UPDATE sgsst_command_projects
                    SET label = ?,
                        responsable = ?,
                        frecuencia = ?,
                        periodicidad = ?,
                        reglas = ?,
                        activo = 1,
                        updated_at = ?
                    WHERE project_key = ?
                """, (
                    project["label"],
                    (request.form.get("responsable") or "").strip() or project["fallback_responsible"],
                    (request.form.get("frecuencia") or "").strip(),
                    (request.form.get("periodicidad") or "").strip(),
                    (request.form.get("reglas") or "").strip(),
                    now,
                    project_key,
                ))
            else:
                con.execute("""
                    INSERT INTO sgsst_command_projects(
                        project_key, label, responsable, frecuencia, periodicidad, reglas,
                        activo, orden_visual, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """, (
                    project_key,
                    project["label"],
                    (request.form.get("responsable") or "").strip() or project["fallback_responsible"],
                    (request.form.get("frecuencia") or "").strip(),
                    (request.form.get("periodicidad") or "").strip(),
                    (request.form.get("reglas") or "").strip(),
                    now,
                    now,
                ))

            valid_states = {item["value"] for item in SGSST_COMMAND_SCOPE_OPTIONS}
            for sede_codigo in sorted(valid_sedes):
                scope_state = str(request.form.get(f"scope_state__{sede_codigo}") or "AUTO").strip().upper() or "AUTO"
                if scope_state not in valid_states:
                    scope_state = "AUTO"
                note = (request.form.get(f"scope_note__{sede_codigo}") or "").strip()
                if scope_state == "AUTO" and not note:
                    con.execute("""
                        DELETE FROM sgsst_command_project_scope
                        WHERE project_key = ? AND sede_codigo = ?
                    """, (project_key, sede_codigo))
                    continue
                con.execute("""
                    INSERT INTO sgsst_command_project_scope(project_key, sede_codigo, scope_state, note, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_key, sede_codigo) DO UPDATE SET
                        scope_state = excluded.scope_state,
                        note = excluded.note,
                        updated_at = excluded.updated_at
                """, (
                    project_key,
                    sede_codigo,
                    scope_state,
                    note,
                    now,
                ))
            con.commit()
            flash("Configuracion del proyecto actualizada.", "success")
            return redirect(url_for("sst_project_config", project_key=project_key, **return_clean))

        context = build_sgsst_plan_implementation_context(view_mode="general")
        project_meta = dict(context.get("command_project_meta") or {}).get(project_key, {}) or {}
        scope_map = dict(context.get("command_project_scope") or {}).get(project_key, {}) or {}
        scope_summary = _sgsst_command_scope_summary(project_key, list(context.get("sedes_dashboard") or []), scope_map)
        module_index = {row["sede_codigo"]: row for row in scope_summary["module_rows"]}
        scope_rows = []
        for sede_row in context.get("sedes_dashboard") or []:
            sede_codigo = str(sede_row.get("codigo") or "").strip().upper()
            module_row = module_index.get(sede_codigo)
            if not module_row:
                continue
            saved_scope = scope_map.get(sede_codigo, {})
            saved_state = str(saved_scope.get("scope_state") or "AUTO").strip().upper() or "AUTO"
            if saved_state == "AUTO":
                if _sgsst_command_module_complete(project_key, module_row):
                    effective_label = "Completa"
                elif _sgsst_command_module_missing(project_key, module_row):
                    effective_label = "Sin registrar"
                else:
                    effective_label = "Pendiente"
            else:
                effective_label = _sgsst_command_scope_label(saved_state)
            scope_rows.append({
                "codigo": sede_codigo,
                "nombre": sede_row.get("nombre") or sede_codigo,
                "scope_state": saved_state,
                "scope_note": str(saved_scope.get("note") or "").strip(),
                "effective_label": effective_label,
                "module_result": module_row.get("result") or "",
                "module_pending": module_row.get("pending") or "",
                "module_url": module_row.get("url") or _sgsst_command_project_open_url(project_key, sede_codigo),
            })

        return render_template(
            "sst_project_config.html",
            project=project,
            project_meta=project_meta,
            scope_rows=scope_rows,
            scope_summary=scope_summary,
            scope_options=list(SGSST_COMMAND_SCOPE_OPTIONS),
            scope_label_map=dict(SGSST_COMMAND_SCOPE_LABELS),
            return_url=return_url,
            return_args=return_clean,
            sst_section="calendario",
        )

    def _sst_seguimiento_context():
        con = get_db()
        ensure_sst_general_table(con)
        estado = (request.args.get("estado") or "pendientes").strip().lower()
        sede = (request.args.get("sede") or "").strip().upper()
        q = (request.args.get("q") or "").strip()
        hoy = date.today().isoformat()

        where = ["g.tipo = 'no_conformidad'"]
        params = []
        if estado == "pendientes":
            where.append("UPPER(COALESCE(g.estado, 'ABIERTO')) <> 'CERRADO'")
        elif estado == "alta":
            where.append("UPPER(COALESCE(g.estado, 'ABIERTO')) <> 'CERRADO'")
            where.append("UPPER(COALESCE(g.prioridad, '')) IN ('ALTA', 'CRITICA', 'CRÍTICA')")
        elif estado == "vencidos":
            where.append("UPPER(COALESCE(g.estado, 'ABIERTO')) <> 'CERRADO'")
            where.append("g.fecha_objetivo IS NOT NULL AND date(g.fecha_objetivo) < date(?)")
            params.append(hoy)
        elif estado == "cerrados":
            where.append("UPPER(COALESCE(g.estado, '')) = 'CERRADO'")
        if sede:
            where.append("UPPER(COALESCE(g.sede_codigo, '')) = ?")
            params.append(sede)
        if q:
            where.append("(COALESCE(g.titulo, '') LIKE ? OR COALESCE(g.detalle, '') LIKE ? OR COALESCE(g.accion_correctiva, '') LIKE ? OR COALESCE(g.responsable, '') LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])

        rows = con.execute(f"""
            SELECT g.*, COALESCE(s.nombre, '') AS sede_nombre
            FROM sst_general g
            LEFT JOIN sedes_mpd s ON s.codigo = g.sede_codigo
            WHERE {' AND '.join(where)}
            ORDER BY CASE UPPER(COALESCE(g.prioridad, ''))
                       WHEN 'CRITICA' THEN 0 WHEN 'CRÍTICA' THEN 0 WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
                     CASE WHEN g.fecha_objetivo IS NULL THEN 1 ELSE 0 END,
                     date(g.fecha_objetivo), g.id DESC
        """, params).fetchall()
        sedes = con.execute("SELECT codigo, nombre FROM sedes_mpd ORDER BY codigo").fetchall()
        con.close()
        return {"seguimientos": rows, "sedes": sedes, "f_estado": estado, "f_sede": sede, "f_q": q, "hoy": hoy}

    @app.route("/sst/plan", methods=["GET", "POST"], endpoint="sst_plan")
    def sst_plan():
        con = get_db()
        ensure_sst_plan_tables(con)
        con.close()

        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            codigo = (request.form.get("codigo") or "").strip()
            titulo = (request.form.get("titulo") or "").strip()
            horizonte_meses = (request.form.get("horizonte_meses") or "").strip()
            descripcion = (request.form.get("descripcion") or "").strip()
            fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
            fecha_fin = (request.form.get("fecha_fin") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            prioridad = (request.form.get("prioridad") or "").strip()

            if sede_codigo == "":
                sede_codigo = None

            if not titulo:
                flash("El titulo es obligatorio.", "error")
                return redirect(url_for("sst_plan_cargar"))

            try:
                horizonte_val = int(horizonte_meses) if horizonte_meses else None
            except Exception:
                horizonte_val = None

            con = get_db()
            con.execute("""
                INSERT INTO sst_objetivos
                    (sede_codigo, codigo, titulo, horizonte_meses, descripcion,
                     fecha_inicio, fecha_fin, estado, prioridad)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sede_codigo,
                codigo,
                titulo,
                horizonte_val,
                descripcion,
                fecha_inicio,
                fecha_fin,
                estado,
                prioridad,
            ))
            con.commit()
            con.close()
            flash("Objetivo creado.", "success")
            return redirect(url_for("sst_plan_cargar"))

        vista = (request.args.get("vista") or "operativa").strip().lower()
        if vista not in {"gestion", "all", "gantt", "ergonomia"}:
            return render_template("sst_seguimiento.html", **_sst_seguimiento_context())
        context = build_sst_plan_context(show_carga=False, sst_view=("all" if vista == "gestion" else vista))
        return render_template("sst_plan.html", **context)

    @app.route("/sst/plan/cargar", methods=["GET"], endpoint="sst_plan_cargar")
    def sst_plan_cargar():
        context = build_sst_plan_context(show_carga=True, sst_view=(request.args.get("vista") or "all"))
        return render_template("sst_plan.html", **context)

    @app.route("/sst/plan/<int:oid>/editar", methods=["GET", "POST"], endpoint="sst_plan_editar")
    def sst_plan_editar(oid):
        con = get_db()
        ensure_sst_plan_tables(con)
        obj = con.execute("SELECT * FROM sst_objetivos WHERE id = ?", (oid,)).fetchone()
        con.close()
        if not obj:
            flash("Objetivo no encontrado.", "warning")
            return _sst_plan_redirect_next()

        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            codigo = (request.form.get("codigo") or "").strip()
            titulo = (request.form.get("titulo") or "").strip()
            horizonte_meses = (request.form.get("horizonte_meses") or "").strip()
            descripcion = (request.form.get("descripcion") or "").strip()
            fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
            fecha_fin = (request.form.get("fecha_fin") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            prioridad = (request.form.get("prioridad") or "").strip()

            if sede_codigo == "":
                sede_codigo = None

            if not titulo:
                flash("El titulo es obligatorio.", "error")
                return redirect(url_for("sst_plan_editar", oid=oid, next=request.args.get("next")))

            try:
                horizonte_val = int(horizonte_meses) if horizonte_meses else None
            except Exception:
                horizonte_val = None

            con = get_db()
            con.execute("""
                UPDATE sst_objetivos
                SET sede_codigo = ?,
                    codigo = ?,
                    titulo = ?,
                    horizonte_meses = ?,
                    descripcion = ?,
                    fecha_inicio = ?,
                    fecha_fin = ?,
                    estado = ?,
                    prioridad = ?
                WHERE id = ?
            """, (
                sede_codigo,
                codigo,
                titulo,
                horizonte_val,
                descripcion,
                fecha_inicio,
                fecha_fin,
                estado,
                prioridad,
                oid,
            ))
            con.commit()
            con.close()
            flash("Objetivo actualizado.", "success")
            return _sst_plan_redirect_next()

        context = build_sst_plan_context(show_carga=True, edit_obj=dict(obj), sst_view=(request.args.get("vista") or "all"))
        return render_template("sst_plan.html", **context)

    @app.route("/sst/plan/<int:oid>/eliminar", methods=["POST"], endpoint="sst_plan_eliminar")
    def sst_plan_eliminar(oid):
        con = get_db()
        con.execute("DELETE FROM sst_objetivo_acciones WHERE objetivo_id = ?", (oid,))
        con.execute("DELETE FROM sst_objetivos WHERE id = ?", (oid,))
        con.commit()
        con.close()
        flash("Objetivo eliminado.", "success")
        return _sst_plan_redirect_next()

    @app.route("/sst/plan/accion/<int:oid>/agregar", methods=["POST"], endpoint="sst_plan_accion_agregar")
    def sst_plan_accion_agregar(oid):
        nombre = (request.form.get("nombre") or "").strip()
        fase = (request.form.get("fase") or "").strip()
        responsable_area = (request.form.get("responsable_area") or "").strip()
        estado = (request.form.get("estado") or "").strip()
        fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
        fecha_fin = (request.form.get("fecha_fin") or "").strip()

        if not nombre:
            flash("Completa el nombre de la accion.", "warning")
            return _sst_plan_redirect_next()

        con = get_db()
        con.execute("""
            INSERT INTO sst_objetivo_acciones
                (objetivo_id, nombre, fase, responsable_area, fecha_inicio, fecha_fin, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (oid, nombre, fase, responsable_area, fecha_inicio, fecha_fin, estado))
        con.commit()
        con.close()
        flash("Accion agregada.", "success")
        return _sst_plan_redirect_next()

    @app.route("/sst/plan/accion/<int:aid>/editar", methods=["GET", "POST"], endpoint="sst_plan_accion_editar")
    def sst_plan_accion_editar(aid):
        con = get_db()
        accion = con.execute("""
            SELECT a.*, o.titulo AS objetivo_titulo
            FROM sst_objetivo_acciones a
            LEFT JOIN sst_objetivos o ON o.id = a.objetivo_id
            WHERE a.id = ?
        """, (aid,)).fetchone()
        con.close()
        if not accion:
            flash("Accion no encontrada.", "warning")
            return _sst_plan_redirect_next()

        if request.method == "POST":
            nombre = (request.form.get("nombre") or "").strip()
            fase = (request.form.get("fase") or "").strip()
            responsable_area = (request.form.get("responsable_area") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            fecha_inicio = (request.form.get("fecha_inicio") or "").strip()
            fecha_fin = (request.form.get("fecha_fin") or "").strip()
            avance_pct = (request.form.get("avance_pct") or "").strip()
            indicador = (request.form.get("indicador") or "").strip()
            clasificacion = (request.form.get("clasificacion") or "").strip()
            justificacion = (request.form.get("justificacion") or "").strip()
            evidencia_url = (request.form.get("evidencia_url") or "").strip()
            notas = (request.form.get("notas") or "").strip()

            if not nombre:
                flash("Completa el nombre de la accion.", "warning")
                return redirect(url_for("sst_plan_accion_editar", aid=aid, next=request.args.get("next")))

            try:
                avance_val = int(avance_pct) if avance_pct != "" else None
            except Exception:
                avance_val = None

            con = get_db()
            con.execute("""
                UPDATE sst_objetivo_acciones
                SET nombre = ?,
                    fase = ?,
                    responsable_area = ?,
                    estado = ?,
                    fecha_inicio = ?,
                    fecha_fin = ?,
                    avance_pct = ?,
                    indicador = ?,
                    clasificacion = ?,
                    justificacion = ?,
                    evidencia_url = ?,
                    notas = ?
                WHERE id = ?
            """, (
                nombre,
                fase,
                responsable_area,
                estado,
                fecha_inicio,
                fecha_fin,
                avance_val,
                indicador,
                clasificacion,
                justificacion,
                evidencia_url,
                notas,
                aid,
            ))
            con.commit()
            con.close()
            flash("Accion actualizada.", "success")
            return _sst_plan_redirect_next()

        context = build_sst_plan_context(show_carga=True, edit_acc=dict(accion), sst_view=(request.args.get("vista") or "all"))
        return render_template("sst_plan.html", **context)

    @app.route("/sst/cuadro-unico", methods=["GET"], endpoint="sst_cuadro_unico")
    def sst_cuadro_unico():
        context = build_sst_plan_context(show_carga=False, sst_view="cuadro")
        return render_template("sst_plan.html", **context)

    def _sst_fmt_fecha(s):
        if not s:
            return "—"
        try:
            if "-" in s and len(s) >= 10:
                return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
        except Exception:
            pass
        return s

    def _sst_visitas_art_normalize_state(value):
        raw_state = (_sst_clean_upper(value) or "").strip().upper()
        legacy_map = {
            "SIN_OBS": "VISITADA",
            "CON_OBS": "OBSERVADA",
            "REQUIERE_CORRECCION": "EN_SEGUIMIENTO",
            "PEND_ANALISIS": "OBSERVADA",
        }
        normalized = legacy_map.get(raw_state, raw_state)
        return normalized if normalized in SST_VISITA_ART_STATE_LABELS else ""

    def _sst_visitas_art_normalize_doc_state(value, has_support=False):
        raw_state = (_sst_clean_upper(value) or "").strip().upper()
        legacy_map = {
            "PENDIENTE": "OBSERVADO",
            "REVISADO": "CARGADO",
            "APROBADO": "CARGADO",
            "OK": "CARGADO",
        }
        normalized = legacy_map.get(raw_state, raw_state)
        if normalized in SST_VISITA_ART_DOC_STATE_LABELS:
            return normalized
        return "CARGADO" if has_support else "SIN_DOCUMENTACION"

    def _sst_visitas_art_doc_summary(doc_row):
        if not doc_row:
            return {
                "id": 0,
                "code": "SIN_DOCUMENTACION",
                "meta": _sst_state_badge("SIN_DOCUMENTACION", SST_VISITA_ART_DOC_STATE_LABELS),
                "fecha_documento": "",
                "fecha_carga": "",
                "observacion": "",
                "drive_url": "",
                "archivo": "",
                "support_url": "",
                "support_label": "",
                "has_support": False,
            }
        drive_url = str(_row_value(doc_row, "drive_url", "") or "").strip()
        archivo = str(_row_value(doc_row, "archivo", "") or "").strip()
        has_support = bool(drive_url or archivo)
        state_code = _sst_visitas_art_normalize_doc_state(_row_value(doc_row, "estado_revision", ""), has_support)
        if state_code == "SIN_DOCUMENTACION" and has_support:
            state_code = "CARGADO"
        support_url = drive_url or (url_for("sst_doc_archivo", filename=archivo) if archivo else "")
        support_label = "Drive" if drive_url else ("Archivo" if archivo else "")
        return {
            "id": int(_row_value(doc_row, "id", 0) or 0),
            "code": state_code,
            "meta": _sst_state_badge(state_code, SST_VISITA_ART_DOC_STATE_LABELS),
            "fecha_documento": str(_row_value(doc_row, "fecha_documento", "") or "").strip(),
            "fecha_carga": str(_row_value(doc_row, "fecha_carga", "") or "").strip(),
            "observacion": str(_row_value(doc_row, "notas", "") or "").strip(),
            "drive_url": drive_url,
            "archivo": archivo,
            "support_url": support_url,
            "support_label": support_label,
            "has_support": has_support,
        }

    def _sst_visitas_art_doc_overall_code(rgrl_summary, dec_summary):
        codes = [rgrl_summary.get("code"), dec_summary.get("code")]
        if all(code == "SIN_DOCUMENTACION" for code in codes):
            return "SIN_DOCUMENTACION"
        if any(code in {"SIN_DOCUMENTACION", "FALTANTE", "OBSERVADO"} for code in codes):
            return "INCOMPLETA"
        return "COMPLETA"

    def _sst_visitas_art_observation_code(record):
        if not record or not str(_row_value(record, "fecha", "") or "").strip():
            return "SIN_DATOS"
        if str(_row_value(record, "observacion_art", "") or "").strip() or str(_row_value(record, "accion_requerida", "") or "").strip():
            return "OBSERVADA"
        return "SIN_OBSERVACIONES"

    def _sst_visitas_art_state_code(record, today_ref=None):
        today_ref = today_ref or date.today()
        if not record or not str(_row_value(record, "fecha", "") or "").strip():
            return "SIN_VISITA"
        visit_date = _sst_calendar_parse_date(_row_value(record, "fecha", ""))
        manual_state = _sst_visitas_art_normalize_state(_row_value(record, "estado", ""))
        has_observation = bool(
            str(_row_value(record, "observacion_art", "") or "").strip()
            or str(_row_value(record, "accion_requerida", "") or "").strip()
        )
        has_action = bool(
            str(_row_value(record, "accion_requerida", "") or "").strip()
            or str(_row_value(record, "accion_responsable", "") or "").strip()
            or str(_row_value(record, "fecha_programada", "") or "").strip()
            or int(_row_value(record, "seguimiento_id", 0) or 0) > 0
        )
        action_executed = bool(
            _sst_bool_flag(_row_value(record, "ejecutado", 0))
            or str(_row_value(record, "fecha_ejecucion", "") or "").strip()
            or str(_row_value(record, "evidencia_url", "") or "").strip()
        )
        if manual_state == "SIN_VISITA":
            return "SIN_VISITA"
        if visit_date and visit_date > today_ref:
            return "PROGRAMADA"
        if manual_state and manual_state != "PROGRAMADA":
            return manual_state
        if has_action and not action_executed:
            return "EN_SEGUIMIENTO"
        if has_observation:
            return "CERRADA" if action_executed else "OBSERVADA"
        return "VISITADA"

    def _sst_visitas_art_next_action(summary):
        state_code = str(summary.get("state_code") or "").strip().upper()
        doc_overall_code = str(summary.get("doc_overall_code") or "").strip().upper()
        observation_code = str(summary.get("observation_code") or "").strip().upper()
        action_required = str(summary.get("accion_requerida") or "").strip()
        executed = bool(summary.get("ejecutado"))
        has_evidence = bool(str(summary.get("evidencia_url") or "").strip() or str(summary.get("fecha_ejecucion") or "").strip())
        if state_code == "SIN_VISITA":
            return "Programar visita."
        if state_code == "PROGRAMADA":
            return "Realizar visita."
        if observation_code == "OBSERVADA" and not action_required:
            return "Definir accion requerida."
        if action_required and not executed:
            return "Ejecutar accion."
        if action_required and executed and not has_evidence and state_code != "CERRADA":
            return "Registrar evidencia o cerrar."
        if doc_overall_code != "COMPLETA":
            return "Cargar documentacion."
        if action_required and executed and state_code != "CERRADA":
            return "Registrar evidencia o cerrar."
        return "Sin acciones pendientes."

    def _sst_visitas_art_followup_text(summary):
        state_code = str(summary.get("state_code") or "").strip().upper()
        doc_overall_code = str(summary.get("doc_overall_code") or "").strip().upper()
        action_required = str(summary.get("accion_requerida") or "").strip()
        if state_code == "SIN_VISITA":
            return "Programar visita ART de la sede."
        if state_code == "PROGRAMADA":
            return "Realizar la visita ART programada."
        if action_required:
            return f"Ejecutar accion ART: {action_required}"
        if doc_overall_code != "COMPLETA":
            return "Completar documentacion ART obligatoria de la sede."
        return "Dar seguimiento a la gestion operativa de Visitas ART."

    def _sst_visitas_art_anchor_year(summary):
        for raw_value in (
            summary.get("ultima_visita"),
            summary.get("fecha_programada"),
            summary.get("fecha_ejecucion"),
        ):
            parsed = _sst_calendar_parse_date(raw_value)
            if parsed:
                return int(parsed.year)
        return 0

    def _sst_sede_estado_label(estado_code):
        normalized = _sst_visitas_art_normalize_state(estado_code)
        if normalized:
            return SST_VISITA_ART_STATE_LABELS.get(normalized, normalized.replace("_", " ").title())
        e = (estado_code or "").strip().upper()
        if e == "SIN_OBS":
            return "Sin obs."
        if e == "CON_OBS":
            return "Con obs."
        if e == "REQUIERE_CORRECCION":
            return "Requiere correccion"
        if e == "PEND_ANALISIS":
            return "Pend. analisis"
        return estado_code or "—"

    def _sst_calc_semaforo(has_visita, docs_ok, docs_pend, pend_hallazgos):
        if not has_visita:
            return ("danger", "Sin visita")
        if not docs_ok:
            return ("pending", "Docs pendientes")
        if docs_pend:
            return ("pending", "En revision")
        if (pend_hallazgos or 0) > 0:
            return ("pending", "En seguimiento")
        return ("complete", "Al dia")

    def _sst_fuero_style(fuero_raw):
        fu = str(fuero_raw or "").strip().lower()
        if not fu:
            return ("otro", "#64748b")
        if "administr" in fu or "violencia" in fu:
            return ("administracion", "#f58a5e")
        if "menor" in fu or "incap" in fu:
            return ("menores_incapaces", "#65BFF4")
        if "jurid" in fu or "social" in fu or "civil" in fu:
            return ("juridico_social", "#F14B94")
        if "penal" in fu:
            return ("penal", "#6666cc")
        if "equipo" in fu or "interdiscip" in fu:
            return ("equipo_interdisciplinario", "#4D4D4D")
        return ("otro", "#64748b")

    def _sst_sede_fuero_style(sede_codigo, fuero_raw):
        code = (_sst_clean_upper(sede_codigo) or "").strip().upper()
        code_overrides = {
            "S08": ("administracion", "#f58a5e"),
            "S11": ("juridico_social", "#F14B94"),
            "S12": ("administracion", "#f58a5e"),
            "S13": ("menores_incapaces", "#65BFF4"),
            "S14": ("juridico_social", "#F14B94"),
            "S15": ("juridico_social", "#F14B94"),
            "S16": ("juridico_social", "#F14B94"),
            "S17": ("juridico_social", "#F14B94"),
            "S18": ("juridico_social", "#F14B94"),
            "S19": ("juridico_social", "#F14B94"),
            "S20": ("juridico_social", "#F14B94"),
        }
        if code in code_overrides:
            return code_overrides[code]
        return _sst_fuero_style(fuero_raw)

    def _sst_calendar_parse_date(value):
        raw = str(value or "").strip()
        if not raw:
            return None
        raw = raw[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            return None

    def _sst_calendar_month_name(month_number):
        for number, label in SST_CALENDAR_MONTHS:
            if number == month_number:
                return label
        return "-"

    def _sst_calendar_state_meta(state_key):
        return SST_CALENDAR_STATE_META.get(state_key, SST_CALENDAR_STATE_META["pendiente"])

    def _sst_calendar_type_meta(type_key):
        return SST_CALENDAR_TYPE_META.get(type_key, SST_CALENDAR_TYPE_META["otro"])

    def _sst_calendar_phase_meta(phase_key):
        return SST_CALENDAR_PHASE_META.get(phase_key)

    # The lifecycle phase is a visual derivation of the module state; it is never stored manually.
    def _sst_calendar_phase_for_event(event):
        phase_hint = str(event.get("phase_hint") or "").strip().lower()
        if phase_hint in SST_CALENDAR_PHASE_META:
            return _sst_calendar_phase_meta(phase_hint)
        type_key = str(event.get("type_key") or "").strip().lower()
        source_type = str(event.get("source_type") or "").strip().lower()
        module_state_code = _sst_clean_upper(event.get("module_state_code") or event.get("state_code"))

        if type_key in {"visita", "documentacion", "hallazgo", "planos"}:
            return _sst_calendar_phase_meta("diagnostico")
        if type_key == "seguimiento":
            return _sst_calendar_phase_meta("implementacion")
        if type_key in {"matafuegos", "desinfeccion"}:
            return _sst_calendar_phase_meta("operacion")
        if source_type == "sst_control" and type_key in {"carteleria", "luces"}:
            return _sst_calendar_phase_meta("diagnostico")
        if type_key == "carteleria":
            if module_state_code in {"NO_RELEVADO", "RELEVADO"}:
                return _sst_calendar_phase_meta("diagnostico")
            if module_state_code in {"PENDIENTE_SOLICITUD", "COMPRA_EN_PROCESO", "MATERIAL_RECIBIDO", "INSTALACION_PROGRAMADA"}:
                return _sst_calendar_phase_meta("implementacion")
            if module_state_code == "COMPLETO":
                return _sst_calendar_phase_meta("operacion")
        if type_key == "luces":
            if module_state_code in {"SIN_RELEVAR", "RELEVADO"}:
                return _sst_calendar_phase_meta("diagnostico")
            if module_state_code in {"PENDIENTE_DE_SOLICITUD", "EN_PROCESO_DE_COMPRA", "MATERIAL_RECIBIDO", "INSTALACION_PROGRAMADA"}:
                return _sst_calendar_phase_meta("implementacion")
            if module_state_code in {"COMPLETO", "MANTENIMIENTO"}:
                return _sst_calendar_phase_meta("operacion")
        return None

    def _sst_calendar_phase_rank(phase_key):
        phase = str(phase_key or "").strip().lower()
        if phase == "diagnostico":
            return 10
        if phase == "implementacion":
            return 20
        if phase == "operacion":
            return 30
        return 90

    def _sst_calendar_due_state(target_date, today_ref, alert_days=45):
        if not target_date:
            return "sin_datos"
        if target_date < today_ref:
            return "vencido"
        if target_date <= (today_ref + timedelta(days=alert_days)):
            return "proximo"
        return "programado"

    def _sst_calendar_control_type(nombre_objetivo):
        txt = str(nombre_objetivo or "").strip().lower()
        if not txt:
            return ""
        if "cartel" in txt or "senal" in txt or "señal" in txt:
            return "carteleria"
        if "luz" in txt or "emerg" in txt:
            return "luces"
        if "plano" in txt or "evacu" in txt:
            return "planos"
        return ""

    def _sst_calendar_visible_events(events):
        return [event for event in events if event.get("type_key") in SST_CALENDAR_VISIBLE_TYPES]

    def _sst_calendar_matafuegos_schedule(sede_codigo, raw_due_date=""):
        sede_key = str(sede_codigo or "").strip().upper()
        config = SST_CALENDAR_MATAFUEGOS_SCHEDULE.get(sede_key)
        if not config:
            return {
                "event_date": _sst_calendar_parse_date(raw_due_date),
                "lot_label": "",
                "lot_month": "",
            }
        return {
            "event_date": _sst_calendar_parse_date(config.get("due_date", "")),
            "lot_label": str(config.get("lot_label", "") or "").strip(),
            "lot_month": str(config.get("lot_month", "") or "").strip(),
        }

    def _sst_calendar_build_event(
        source_id,
        source_type,
        sede_codigo,
        sede_nombre,
        region_label,
        event_date,
        type_key,
        title,
        detail,
        state_key,
        responsible="",
        url_detail="",
        action_label="",
        active=True,
        units=1,
        records=None,
        extra=None,
    ):
        state_meta = _sst_calendar_state_meta(state_key)
        type_meta = _sst_calendar_type_meta(type_key)
        event = {
            "source_id": source_id,
            "source_type": source_type,
            "sede_codigo": (sede_codigo or "").strip().upper(),
            "sede_nombre": (sede_nombre or "").strip(),
            "region": (region_label or "").strip(),
            "fecha_evento": event_date.isoformat(),
            "year": event_date.year,
            "month": event_date.month,
            "day": event_date.day,
            "type_key": type_key,
            "type_label": type_meta["label"],
            "type_short": type_meta["short"],
            "type_icon": type_meta.get("icon", ""),
            "type_badge": f"{type_meta.get('icon', '')} {type_meta['short']}".strip(),
            "title": (title or "").strip() or type_meta["label"],
            "detail": (detail or "").strip(),
            "state_key": state_key,
            "state_label": state_meta["label"],
            "state_class": state_meta["class"],
            "state_icon": state_meta.get("icon", ""),
            "state_rank": int(state_meta["rank"]),
            "responsible": (responsible or "").strip(),
            "url_detail": url_detail,
            "action_label": action_label or type_meta["action"],
            "active": bool(active),
            "units": max(1, int(units or 1)),
            "records": list(records or []),
        }
        if isinstance(extra, dict):
            event.update(extra)
        phase_meta = _sst_calendar_phase_for_event(event)
        event["phase_key"] = phase_meta["key"] if phase_meta else ""
        event["phase_short"] = phase_meta["short"] if phase_meta else ""
        event["phase_label"] = phase_meta["label"] if phase_meta else ""
        event["phase_title"] = phase_meta["title"] if phase_meta else ""
        return event

    def _sst_calendar_open_state(anchor_date, today_ref, alert_days=30):
        if not anchor_date:
            return "pendiente"
        if anchor_date < today_ref:
            return "vencido"
        if anchor_date <= (today_ref + timedelta(days=alert_days)):
            return "proximo"
        return "programado"

    def _sst_calendar_short_date(value):
        parsed = value if isinstance(value, date) else _sst_calendar_parse_date(value)
        if not parsed:
            return ""
        return parsed.strftime("%d/%m/%Y")

    def _sst_calendar_plan_module_type_key(module_name):
        module_txt = str(module_name or "").strip().lower()
        if not module_txt:
            return "seguimiento"
        if "luz" in module_txt:
            return "luces"
        if "cartel" in module_txt or "senal" in module_txt or "señal" in module_txt:
            return "carteleria"
        if "mataf" in module_txt:
            return "matafuegos"
        if "desinf" in module_txt:
            return "desinfeccion"
        if "visit" in module_txt or " art" in f" {module_txt} ":
            return "visita"
        if "doc" in module_txt:
            return "documentacion"
        if "evac" in module_txt or "plano" in module_txt:
            return "planos"
        return "seguimiento"

    def _sst_calendar_plan_action_state_key(state_label, due_date, today_ref):
        state = str(state_label or "").strip().lower()
        if state in {"cerrada", "cerrado", "verificada", "verificado", "implementada", "implementado", "completada", "completado"}:
            return "cumplido"
        if due_date and due_date < today_ref and state not in {"cancelada", "cancelado", "no aplica"}:
            return "vencido"
        if state in {"programada", "programado"}:
            return _sst_calendar_open_state(due_date, today_ref, alert_days=30)
        if state in {"en ejecucion", "en ejecución", "en gestion", "en gestión", "en analisis", "en análisis", "bloqueada", "bloqueado"}:
            return "en_seguimiento"
        if state in {"cancelada", "cancelado"}:
            return "cumplido"
        return _sst_calendar_open_state(due_date, today_ref, alert_days=30)

    def _sst_calendar_plan_hallazgo_state_key(state_label):
        state = str(state_label or "").strip().lower()
        if state in {"resuelto", "cerrado", "cerrada", "no aplica"}:
            return "cumplido"
        if state in {"confirmado", "en analisis", "en análisis"}:
            return "en_seguimiento"
        return "pendiente"

    def _sst_calendar_force_phase(event, phase_key):
        phase_meta = _sst_calendar_phase_meta(phase_key)
        event["phase_hint"] = str(phase_key or "").strip().lower()
        event["phase_key"] = phase_meta["key"] if phase_meta else ""
        event["phase_short"] = phase_meta["short"] if phase_meta else ""
        event["phase_label"] = phase_meta["label"] if phase_meta else ""
        event["phase_title"] = phase_meta["title"] if phase_meta else ""
        return event

    def _sst_calendar_pick_event_date(anchor_date, created_date, selected_year, today_ref, keep_current_open=False):
        year_start = date(selected_year, 1, 1)
        if anchor_date and anchor_date.year == selected_year:
            return anchor_date
        if created_date and created_date.year == selected_year:
            return created_date
        if keep_current_open and selected_year == today_ref.year:
            if anchor_date and anchor_date < year_start:
                return today_ref
            if created_date and created_date < year_start:
                return today_ref
        if not anchor_date and not created_date and selected_year == today_ref.year:
            return today_ref
        return None

    def _sst_calendar_build_plan_events(plan_context, selected_year, today_ref):
        events = []

        for item in (plan_context.get("hallazgos") or []):
            if str(item.get("source_kind") or "").strip().lower() != "manual":
                continue
            sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
            if not sede_codigo:
                continue
            detected_date = _sst_calendar_parse_date(item.get("fecha_deteccion"))
            created_date = _sst_calendar_parse_date(item.get("created_at"))
            event_date = _sst_calendar_pick_event_date(
                detected_date,
                created_date,
                selected_year,
                today_ref,
                keep_current_open=not bool(item.get("is_closed")),
            )
            if not event_date:
                continue
            detail_parts = [
                str(item.get("descripcion") or "").strip(),
                str(item.get("categoria") or "").strip(),
                str(item.get("fuente") or "").strip(),
            ]
            event = _sst_calendar_build_event(
                source_id=str(item.get("id") or ""),
                source_type="sgsst_plan_hallazgo",
                sede_codigo=sede_codigo,
                sede_nombre=str(item.get("sede_nombre") or "").strip(),
                region_label="",
                event_date=event_date,
                type_key="hallazgo",
                title=str(item.get("titulo") or "").strip() or "Hallazgo SG-SST",
                detail=" · ".join(part for part in detail_parts if part) or "Hallazgo detectado en la sede.",
                state_key=_sst_calendar_plan_hallazgo_state_key(item.get("state_label")),
                responsible=str(item.get("detectado_por") or "").strip(),
                url_detail=item.get("detail_url") or url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo),
                action_label="Abrir hallazgo",
                active=not bool(item.get("is_closed")),
                extra={
                    "phase_hint": "diagnostico",
                    "module_origin": str(item.get("modulo_origen") or "").strip(),
                },
            )
            events.append(_sst_calendar_force_phase(event, "diagnostico"))

        for item in (plan_context.get("acciones") or []):
            if str(item.get("source_kind") or "").strip().lower() not in {"manual", "objetivo"}:
                continue
            sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
            if not sede_codigo:
                continue
            due_date = _sst_calendar_parse_date(item.get("fecha_objetivo"))
            created_date = _sst_calendar_parse_date(item.get("fecha_creacion"))
            state_label = item.get("state_label") or ""
            is_closed = _sgsst_plan_is_action_closed(state_label)
            event_date = _sst_calendar_pick_event_date(
                due_date,
                created_date,
                selected_year,
                today_ref,
                keep_current_open=not is_closed,
            )
            if not event_date:
                continue
            module_origin = str(item.get("modulo_origen") or "").strip()
            detail_parts = [
                str(item.get("accion_requerida") or "").strip(),
                str(item.get("hallazgo_title") or "").strip(),
                f"Prioridad: {str(item.get('priority_label') or '').strip()}" if str(item.get("priority_label") or "").strip() else "",
            ]
            event = _sst_calendar_build_event(
                source_id=str(item.get("id") or ""),
                source_type="sgsst_plan_accion",
                sede_codigo=sede_codigo,
                sede_nombre=str(item.get("sede_nombre") or "").strip(),
                region_label="",
                event_date=event_date,
                type_key=_sst_calendar_plan_module_type_key(module_origin),
                title=str(item.get("titulo") or "").strip() or "Accion SG-SST",
                detail=" · ".join(part for part in detail_parts if part) or "Accion del plan SG-SST.",
                state_key=_sst_calendar_plan_action_state_key(state_label, due_date or created_date or event_date, today_ref),
                responsible=str(item.get("responsable") or item.get("area_responsable") or "").strip(),
                url_detail=item.get("detail_url") or url_for("sst_plan_implementacion", vista="acciones", sede=sede_codigo),
                action_label="Abrir accion",
                active=not is_closed,
                extra={
                    "phase_hint": "implementacion",
                    "module_origin": module_origin,
                    "action_state_label": state_label,
                },
            )
            events.append(_sst_calendar_force_phase(event, "implementacion"))

        if selected_year == today_ref.year:
            for item in (plan_context.get("suggestions") or []):
                sede_codigo = str(item.get("sede_codigo") or "").strip().upper()
                if not sede_codigo:
                    continue
                type_key = _sst_calendar_plan_module_type_key(item.get("module"))
                phase_key = "diagnostico" if type_key in {"visita", "documentacion", "planos", "hallazgo"} else "implementacion"
                event = _sst_calendar_build_event(
                    source_id=f"suggestion-{sede_codigo}-{str(item.get('module') or '').strip().lower()}",
                    source_type="sgsst_plan_suggestion",
                    sede_codigo=sede_codigo,
                    sede_nombre=str(item.get("sede_nombre") or "").strip(),
                    region_label="",
                    event_date=today_ref,
                    type_key=type_key,
                    title=f"Sugerencia: {str(item.get('module') or '').strip() or 'Trabajo detectado'}",
                    detail=str(item.get("reason") or "").strip() or "Trabajo detectado por el sistema.",
                    state_key="pendiente",
                    responsible="Sistema SG-SST",
                    url_detail=item.get("context_url") or item.get("origin_url") or item.get("action_url") or "",
                    action_label="Revisar sugerencia",
                    active=True,
                    extra={
                        "phase_hint": phase_key,
                        "is_suggestion": True,
                        "suggestion_label": "Sugerencia",
                        "module_origin": str(item.get("module") or "").strip(),
                    },
                )
                events.append(_sst_calendar_force_phase(event, phase_key))

        return events

    def _sst_calendar_count_text(count_value, singular, plural):
        count = max(0, int(count_value or 0))
        return f"{count} {singular if count == 1 else plural}"

    def _sst_calendar_carteleria_state_key(state_code, anchor_date, today_ref):
        state = _sst_clean_upper(state_code)
        if state == "NO_RELEVADO":
            return "sin_datos"
        if state in {"RELEVADO", "PENDIENTE_SOLICITUD"}:
            return "pendiente"
        if state == "COMPRA_EN_PROCESO":
            return "en_seguimiento"
        if state == "MATERIAL_RECIBIDO":
            return "pendiente"
        if state == "INSTALACION_PROGRAMADA":
            if anchor_date and anchor_date < today_ref:
                return "vencido"
            return "programado"
        if state == "COMPLETO":
            return "cumplido"
        return "pendiente"

    def _sst_calendar_luces_state_key(state_code, anchor_date, today_ref):
        state = _sst_clean_upper(state_code)
        if state == "SIN_RELEVAR":
            return "sin_datos"
        if state in {"RELEVADO", "PENDIENTE_DE_SOLICITUD"}:
            return "pendiente"
        if state == "EN_PROCESO_DE_COMPRA":
            return "en_seguimiento"
        if state == "MATERIAL_RECIBIDO":
            return "pendiente"
        if state == "INSTALACION_PROGRAMADA":
            if anchor_date and anchor_date < today_ref:
                return "vencido"
            return "programado"
        if state == "MANTENIMIENTO":
            return "vencido"
        if state == "COMPLETO":
            return "cumplido"
        return "pendiente"

    def _sst_carteleria_calendar_entry(record, today_ref):
        state_code = _sst_clean_upper(record.get("state_code"))
        requerida = int(record.get("cantidad_requerida") or 0)
        faltante = int(record.get("cantidad_faltante") or 0)
        anchor_sources = {
            "NO_RELEVADO": (
                record.get("fecha_relevamiento"),
                record.get("fecha_actualizacion"),
            ),
            "RELEVADO": (
                record.get("fecha_relevamiento"),
                record.get("fecha_actualizacion"),
            ),
            "PENDIENTE_SOLICITUD": (
                record.get("fecha_relevamiento"),
                record.get("fecha_solicitud"),
                record.get("fecha_pedido"),
                record.get("fecha_actualizacion"),
            ),
            "COMPRA_EN_PROCESO": (
                record.get("fecha_solicitud"),
                record.get("fecha_pedido"),
                record.get("fecha_actualizacion"),
            ),
            "MATERIAL_RECIBIDO": (
                record.get("fecha_entrega"),
                record.get("fecha_disponibilidad"),
                record.get("fecha_actualizacion"),
            ),
            "INSTALACION_PROGRAMADA": (
                record.get("fecha_instalacion"),
                record.get("fecha_programada_colocacion"),
                record.get("fecha_colocacion"),
                record.get("fecha_actualizacion"),
            ),
            "COMPLETO": (
                record.get("fecha_colocacion"),
                record.get("fecha_instalacion"),
                record.get("fecha_programada_colocacion"),
                record.get("fecha_entrega"),
                record.get("fecha_actualizacion"),
            ),
        }
        anchor = next(
            (
                _sst_calendar_parse_date(value)
                for value in anchor_sources.get(state_code, ())
                if _sst_calendar_parse_date(value)
            ),
            None,
        ) or today_ref
        if state_code == "NO_RELEVADO":
            title = "Relevamiento pendiente"
            detail = ""
        elif state_code == "RELEVADO":
            title = "Relevada"
            detail = (f"{faltante} faltantes" if faltante > 0 else "")
        elif state_code == "PENDIENTE_SOLICITUD":
            title = "Pendiente de solicitud"
            detail = _sst_calendar_count_text(max(faltante, requerida), "cartel", "carteles")
        elif state_code == "COMPRA_EN_PROCESO":
            title = "En proceso de compra"
            detail = _sst_calendar_count_text(max(faltante, requerida), "cartel", "carteles")
        elif state_code == "MATERIAL_RECIBIDO":
            title = "Material recibido"
            detail = _sst_calendar_count_text(max(faltante, requerida), "cartel", "carteles")
        elif state_code == "INSTALACION_PROGRAMADA":
            title = "Colocacion programada"
            detail = _sst_calendar_short_date(anchor) or _sst_calendar_count_text(max(faltante, requerida), "cartel", "carteles")
        else:
            title = "Completa"
            detail = _sst_calendar_short_date(anchor)
        return {
            "event_date": anchor,
            "state_key": _sst_calendar_carteleria_state_key(state_code, anchor, today_ref),
            "title": title,
            "detail": detail,
            "units": (max(faltante, 1) if state_code != "COMPLETO" else 1),
        }

    def _sst_luces_calendar_entries(record, today_ref):
        state_code = _sst_clean_upper(record.get("state_code"))
        if state_code == "NO_APLICA":
            return []
        requerida = int(record.get("cantidad_requerida") or 0)
        faltante = int(record.get("cantidad_faltante") or 0)
        fuera_servicio = int(record.get("cantidad_fuera_servicio") or 0)
        anchor_sources = {
            "SIN_RELEVAR": (
                record.get("fecha_actualizacion"),
                record.get("fecha_creacion"),
            ),
            "RELEVADO": (
                record.get("fecha_actualizacion"),
                record.get("fecha_creacion"),
            ),
            "PENDIENTE_DE_SOLICITUD": (
                record.get("fecha_actualizacion"),
                record.get("fecha_creacion"),
            ),
            "EN_PROCESO_DE_COMPRA": (
                record.get("fecha_solicitud_compra"),
                record.get("fecha_actualizacion"),
            ),
            "MATERIAL_RECIBIDO": (
                record.get("fecha_entrega"),
                record.get("fecha_actualizacion"),
            ),
            "INSTALACION_PROGRAMADA": (
                record.get("fecha_colocacion"),
                record.get("fecha_programada_colocacion"),
                record.get("fecha_actualizacion"),
            ),
            "COMPLETO": (
                record.get("fecha_colocacion"),
                record.get("fecha_programada_colocacion"),
                record.get("fecha_actualizacion"),
            ),
            "MANTENIMIENTO": (
                record.get("fecha_mantenimiento"),
                record.get("fecha_actualizacion"),
            ),
        }
        anchor = next(
            (
                _sst_calendar_parse_date(value)
                for value in anchor_sources.get(state_code, ())
                if _sst_calendar_parse_date(value)
            ),
            None,
        ) or today_ref
        if state_code == "SIN_RELEVAR":
            title = "Sin relevar"
            detail = ""
            units = 1
        elif state_code in {"RELEVADO", "PENDIENTE_DE_SOLICITUD"}:
            title = "Pendiente de solicitud"
            detail = _sst_calendar_count_text(max(faltante, requerida), "equipo", "equipos")
            units = max(faltante, 1)
        elif state_code == "EN_PROCESO_DE_COMPRA":
            title = "En proceso de compra"
            detail = _sst_calendar_count_text(max(faltante, requerida), "equipo", "equipos")
            units = max(faltante, 1)
        elif state_code == "MATERIAL_RECIBIDO":
            title = "Material recibido"
            detail = _sst_calendar_count_text(max(faltante, requerida), "equipo", "equipos")
            units = max(faltante, 1)
        elif state_code == "INSTALACION_PROGRAMADA":
            title = "Colocacion programada"
            detail = _sst_calendar_short_date(anchor) or _sst_calendar_count_text(max(faltante, requerida), "equipo", "equipos")
            units = max(faltante, 1)
        elif state_code == "MANTENIMIENTO":
            title = "Requiere mantenimiento"
            detail = _sst_calendar_count_text(max(fuera_servicio, 1), "equipo", "equipos")
            units = max(fuera_servicio, 1)
        else:
            title = "Completo"
            detail = _sst_calendar_short_date(anchor)
            units = 1
        return [{
            "event_date": anchor,
            "state_key": _sst_calendar_luces_state_key(state_code, anchor, today_ref),
            "title": title,
            "detail": detail,
            "units": units,
        }]

    def _sst_calendar_collect_events(con, selected_year):
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)
        ensure_sst_plan_tables(con)
        ensure_sst_control_tables(con)

        today_ref = date.today()
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        event_years = {today_ref.year - 1, today_ref.year, today_ref.year + 1, selected_year}

        sedes_cols = _table_cols(con, "sedes_mpd")
        region_expr = "''"
        if "region" in sedes_cols:
            region_expr = "COALESCE(region, '')"
        elif "ciudad" in sedes_cols:
            region_expr = "COALESCE(ciudad, '')"
        elif "fuero" in sedes_cols:
            region_expr = "COALESCE(fuero, '')"
        fuero_expr = "COALESCE(fuero, '')" if "fuero" in sedes_cols else "''"
        nombre_expr = "COALESCE(nombre, '')" if "nombre" in sedes_cols else "COALESCE(codigo, '')"

        sedes_rows = con.execute(f"""
            SELECT
                UPPER(COALESCE(codigo, '')) AS codigo,
                {nombre_expr} AS nombre,
                {region_expr} AS region,
                {fuero_expr} AS fuero
            FROM sedes_mpd
            WHERE TRIM(COALESCE(codigo, '')) <> ''
            ORDER BY codigo
        """).fetchall()
        sedes = []
        sedes_map = {}
        for row in sedes_rows:
            fuero_raw = (_row_value(row, "fuero", "") or "").strip()
            fuero_class, fuero_color = _sst_sede_fuero_style(
                (_row_value(row, "codigo", "") or "").strip().upper(),
                fuero_raw,
            )
            sede_item = {
                "codigo": (_row_value(row, "codigo", "") or "").strip().upper(),
                "nombre": (_row_value(row, "nombre", "") or "").strip(),
                "region": (_row_value(row, "region", "") or "").strip(),
                "fuero": fuero_raw,
                "fuero_class": fuero_class,
                "fuero_color": fuero_color,
            }
            if not sede_item["codigo"]:
                continue
            sedes.append(sede_item)
            sedes_map[sede_item["codigo"]] = sede_item

        events = []
        matafuegos_overview_map = {}
        has_carteleria_operativa = _table_exists(con, "sst_carteleria_registros") and bool(con.execute("SELECT COUNT(*) FROM sst_carteleria_registros WHERE COALESCE(activo, 1) = 1").fetchone()[0])
        has_luces_operativa = _table_exists(con, "sst_luces_registros") and bool(con.execute("SELECT COUNT(*) FROM sst_luces_registros WHERE COALESCE(activo, 1) = 1").fetchone()[0])

        if _table_exists(con, "matafuegos"):
            mata_cols = _table_cols(con, "matafuegos")
            sede_expr = "UPPER(COALESCE(sede, ''))"
            if "cod_sede" in mata_cols and "sede" in mata_cols:
                sede_expr = "UPPER(COALESCE(sede, cod_sede, ''))"
            elif "cod_sede" in mata_cols:
                sede_expr = "UPPER(COALESCE(cod_sede, ''))"
            activo_expr = "COALESCE(activo, 1)" if "activo" in mata_cols else "1"
            tipo_expr = "COALESCE(tipo, '')" if "tipo" in mata_cols else "''"
            serie_expr = "COALESCE(numero_serie, '')" if "numero_serie" in mata_cols else "''"
            ubic_expr = "COALESCE(ubicacion, '')" if "ubicacion" in mata_cols else "''"
            venc_expr = "COALESCE(fecha_vencimiento, '')" if "fecha_vencimiento" in mata_cols else "''"
            recarga_expr = "COALESCE(fecha_recarga, '')" if "fecha_recarga" in mata_cols else "''"
            nro_ext_expr = "COALESCE(nro_extintor, '')" if "nro_extintor" in mata_cols else "''"
            lote_expr = "COALESCE(lote_vencimiento, '')" if "lote_vencimiento" in mata_cols else "''"
            raw_rows = con.execute(f"""
                SELECT
                    id,
                    {sede_expr} AS sede_codigo,
                    {tipo_expr} AS tipo,
                    {serie_expr} AS numero_serie,
                    {ubic_expr} AS ubicacion,
                    {venc_expr} AS fecha_vencimiento,
                    {recarga_expr} AS fecha_recarga,
                    {nro_ext_expr} AS nro_extintor,
                    {lote_expr} AS lote_vencimiento,
                    {activo_expr} AS activo
                FROM matafuegos
                WHERE {activo_expr} = 1
            """).fetchall()
            grouped_mata = {}
            for row in raw_rows:
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                schedule_info = _sst_calendar_matafuegos_schedule(
                    sede_codigo,
                    _row_value(row, "fecha_vencimiento", ""),
                )
                event_date = schedule_info["event_date"]
                if not event_date:
                    continue
                event_years.add(event_date.year)
                overview_key = (event_date.year, event_date.month)
                overview_item = matafuegos_overview_map.setdefault(overview_key, {
                    "year": event_date.year,
                    "month": event_date.month,
                    "count": 0,
                    "sedes": set(),
                    "first_date": event_date,
                    "last_date": event_date,
                })
                overview_item["count"] += 1
                if sede_codigo:
                    overview_item["sedes"].add(sede_codigo)
                if event_date < overview_item["first_date"]:
                    overview_item["first_date"] = event_date
                if event_date > overview_item["last_date"]:
                    overview_item["last_date"] = event_date
                if not sede_codigo or event_date.year != selected_year:
                    continue
                group_key = (sede_codigo, event_date.year, event_date.month)
                if group_key not in grouped_mata:
                    grouped_mata[group_key] = []
                grouped_mata[group_key].append((row, schedule_info))
            for (sede_codigo, event_year, event_month), rows_group in grouped_mata.items():
                fechas_grupo = []
                for item, schedule_info in rows_group:
                    event_date = schedule_info["event_date"] or _sst_calendar_parse_date(_row_value(item, "fecha_vencimiento", ""))
                    if event_date:
                        fechas_grupo.append(event_date)
                if not fechas_grupo:
                    continue
                event_date = min(fechas_grupo)
                sede_info = sedes_map.get(sede_codigo, {})
                if any(f < today_ref for f in fechas_grupo):
                    estado = "vencido"
                elif any(f <= (today_ref + timedelta(days=45)) for f in fechas_grupo):
                    estado = "proximo"
                else:
                    estado = "programado"
                count_items = len(rows_group)
                fechas_count = defaultdict(int)
                lotes = []
                recargas = []
                for item, schedule_info in rows_group:
                    fecha_item = schedule_info["event_date"] or _sst_calendar_parse_date(_row_value(item, "fecha_vencimiento", ""))
                    if fecha_item:
                        fechas_count[fecha_item] += 1
                    fecha_recarga = _sst_calendar_parse_date(_row_value(item, "fecha_recarga", ""))
                    if fecha_recarga:
                        recargas.append(fecha_recarga)
                    lote_label = schedule_info.get("lot_label", "") or (_row_value(item, "lote_vencimiento", "") or "").strip()
                    lote_month = schedule_info.get("lot_month", "")
                    lote = lote_label
                    if lote_label and lote_month:
                        lote = f"{lote_label} ({lote_month})"
                    if lote and lote.lower() != "otro" and lote not in lotes:
                        lotes.append(lote)
                lote_preview = lotes[0] if lotes else ""
                lote_titulo = lote_preview.split("(", 1)[0].strip()
                lote_mes = ""
                if "(" in lote_preview and ")" in lote_preview:
                    lote_mes = lote_preview.split("(", 1)[1].split(")", 1)[0].strip().lower()
                if estado == "vencido":
                    title = "Vencidos"
                    detail = _sst_calendar_count_text(count_items, "equipo", "equipos")
                elif lote_titulo and lote_mes:
                    title = f"{lote_titulo} vence en {lote_mes}"
                    detail = _sst_calendar_count_text(count_items, "equipo", "equipos")
                elif estado == "proximo":
                    title = "Proximo vencimiento"
                    detail = _sst_calendar_count_text(count_items, "equipo", "equipos")
                else:
                    title = "Vencimiento programado"
                    detail = _sst_calendar_count_text(count_items, "equipo", "equipos")
                ultima_recarga = max(recargas).isoformat() if recargas else ""
                records = []
                rows_sorted = sorted(
                    rows_group,
                    key=lambda item: (
                        ((item[1].get("event_date").isoformat() if item[1].get("event_date") else "") or (_row_value(item[0], "fecha_vencimiento", "") or "")),
                        _row_value(item[0], "ubicacion", "") or "",
                        _row_value(item[0], "nro_extintor", "") or "",
                        _row_value(item[0], "numero_serie", "") or "",
                    ),
                )
                for item, schedule_info in rows_sorted:
                    fecha_item = schedule_info["event_date"] or _sst_calendar_parse_date(_row_value(item, "fecha_vencimiento", ""))
                    ubicacion = (_row_value(item, "ubicacion", "") or "").strip()
                    numero_serie = (_row_value(item, "numero_serie", "") or "").strip()
                    nro_extintor = (_row_value(item, "nro_extintor", "") or "").strip()
                    tipo = (_row_value(item, "tipo", "") or "").strip()
                    lote = schedule_info.get("lot_label", "") or (_row_value(item, "lote_vencimiento", "") or "").strip()
                    lote_month = schedule_info.get("lot_month", "")
                    record_label_parts = []
                    if nro_extintor:
                        record_label_parts.append(f"Ext. {nro_extintor}")
                    if numero_serie:
                        record_label_parts.append(f"Serie {numero_serie}")
                    if ubicacion:
                        record_label_parts.append(ubicacion)
                    record_detail_parts = []
                    if tipo:
                        record_detail_parts.append(tipo)
                    if lote and lote.lower() != "otro":
                        record_detail_parts.append(f"{lote}{(' - ' + lote_month) if lote_month else ''}")
                    if fecha_item:
                        record_detail_parts.append(fecha_item.strftime("%d/%m/%Y"))
                    records.append({
                        "label": " - ".join(record_label_parts) if record_label_parts else "Matafuego",
                        "detail": " - ".join(record_detail_parts),
                    })
                events.append(_sst_calendar_build_event(
                    source_id=",".join(str(_row_value(item[0], "id", "")) for item in rows_group),
                    source_type="matafuegos",
                    sede_codigo=sede_codigo,
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=event_date,
                    type_key="matafuegos",
                    title=title,
                    detail=detail,
                    state_key=estado,
                    responsible="",
                    url_detail=url_for(
                        "matafuegos_home",
                        sede=sede_codigo,
                        lote_vencimiento=(lote_titulo or None),
                        vencimiento=("vencidos" if estado == "vencido" else ("proximos" if estado == "proximo" else "todos")),
                    ),
                    action_label="Ver matafuegos",
                    active=(estado != "cumplido"),
                    units=count_items,
                    records=records,
                    extra={"last_service_date": ultima_recarga},
                ))

        matafuegos_overview = []
        for overview_key in sorted(matafuegos_overview_map.keys()):
            overview_item = matafuegos_overview_map[overview_key]
            matafuegos_overview.append({
                "year": int(overview_item["year"]),
                "month": int(overview_item["month"]),
                "month_label": _sst_calendar_month_name(int(overview_item["month"])),
                "count": int(overview_item["count"]),
                "sedes_count": len(overview_item["sedes"]),
                "first_date": overview_item["first_date"].isoformat(),
                "last_date": overview_item["last_date"].isoformat(),
            })

        if _table_exists(con, "sst_visitas"):
            docs_by_visit = defaultdict(list)
            if _table_exists(con, "sst_documentos"):
                docs_by_visit_rows = con.execute("""
                    SELECT
                        visita_id,
                        COALESCE(archivo, '') AS archivo,
                        COALESCE(drive_url, '') AS drive_url
                    FROM sst_documentos
                    WHERE visita_id IS NOT NULL
                """).fetchall()
                for doc_row in docs_by_visit_rows:
                    visit_id = _row_value(doc_row, "visita_id", None)
                    if visit_id is None:
                        continue
                    docs_by_visit[int(visit_id)].append(doc_row)
            visitas_rows = con.execute("""
                SELECT
                    v.id,
                    UPPER(COALESCE(v.sede_codigo, '')) AS sede_codigo,
                    COALESCE(v.fecha, '') AS fecha,
                    COALESCE(v.tipo_visita, '') AS tipo_visita,
                    COALESCE(v.responsable, '') AS responsable,
                    COALESCE(v.estado, '') AS estado,
                    COALESCE(v.observaciones, '') AS observaciones,
                    COALESCE(v.observacion_art, '') AS observacion_art,
                    COALESCE(v.accion_requerida, '') AS accion_requerida,
                    COALESCE(v.accion_responsable, '') AS accion_responsable,
                    COALESCE(v.fecha_programada, '') AS fecha_programada,
                    COALESCE(v.ejecutado, 0) AS ejecutado,
                    COALESCE(v.fecha_ejecucion, '') AS fecha_ejecucion,
                    COALESCE(v.evidencia_url, '') AS evidencia_url
                FROM sst_visitas v
                ORDER BY date(v.fecha), v.id
            """).fetchall()
            for row in visitas_rows:
                event_date = _sst_calendar_parse_date(_row_value(row, "fecha", ""))
                if not event_date or event_date.year != selected_year:
                    continue
                event_years.add(event_date.year)
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                if not sede_codigo:
                    continue
                sede_info = sedes_map.get(sede_codigo, {})
                visit_id = int(_row_value(row, "id", 0) or 0)
                visit_docs = docs_by_visit.get(visit_id, [])
                art_loaded = any(
                    (_row_value(item, "archivo", "") or "").strip() or (_row_value(item, "drive_url", "") or "").strip()
                    for item in visit_docs
                )
                observaciones = (_row_value(row, "observacion_art", "") or "").strip() or (_row_value(row, "observaciones", "") or "").strip()
                accion_requerida = (_row_value(row, "accion_requerida", "") or "").strip()
                accion_responsable = (_row_value(row, "accion_responsable", "") or "").strip()
                ejecutado = bool(
                    _sst_bool_flag(_row_value(row, "ejecutado", 0))
                    or (_row_value(row, "fecha_ejecucion", "") or "").strip()
                    or (_row_value(row, "evidencia_url", "") or "").strip()
                )
                visit_state = _sst_visitas_art_state_code(row, today_ref)
                detail = _sst_calendar_short_date(event_date)
                if visit_state == "PROGRAMADA":
                    estado = "programado"
                    title = "Programada"
                elif observaciones or accion_requerida:
                    if ejecutado:
                        estado = "cumplido"
                        title = "Realizada"
                        detail = "Observacion resuelta"
                    elif accion_requerida:
                        estado = "en_seguimiento"
                        title = "Observada"
                        detail = "1 accion pendiente"
                    else:
                        estado = "pendiente"
                        title = "Observada"
                        detail = "Definir accion requerida"
                else:
                    estado = "cumplido"
                    title = "Realizada"
                    detail = "Sin observaciones"
                events.append(_sst_calendar_build_event(
                    source_id=str(_row_value(row, "id", "")),
                    source_type="sst_visitas",
                    sede_codigo=sede_codigo,
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=event_date,
                    type_key="visita",
                    title=title,
                    detail=detail,
                    state_key=estado,
                    responsible=((_row_value(row, "responsable", "") or "").strip() or accion_responsable),
                    url_detail=url_for("sst_visitas", sede=sede_codigo, open_sede=sede_codigo),
                    action_label="Abrir Visitas ART",
                    active=(estado != "cumplido"),
                    extra={
                        "visit_type": (_row_value(row, "tipo_visita", "") or "").strip(),
                        "observaciones": observaciones,
                        "art_loaded": art_loaded,
                        "visit_documents_count": len(visit_docs),
                        "type_icon": "\U0001F477",
                        "type_label": "Visitas",
                        "type_short": "VIS",
                    },
                ))
                action_date = _sst_calendar_parse_date(_row_value(row, "fecha_programada", ""))
                if action_date and action_date.year == selected_year and (observaciones or accion_requerida) and not ejecutado:
                    event_years.add(action_date.year)
                    events.append(_sst_calendar_build_event(
                        source_id=f"visita-accion-{_row_value(row, 'id', '')}",
                        source_type="sst_visitas",
                        sede_codigo=sede_codigo,
                        sede_nombre=sede_info.get("nombre", ""),
                        region_label=sede_info.get("region", ""),
                        event_date=action_date,
                        type_key="visita",
                        title="Observada",
                        detail=("Accion vencida" if action_date < today_ref else "1 accion pendiente"),
                        state_key=("vencido" if action_date < today_ref else "pendiente"),
                        responsible=(accion_responsable or (_row_value(row, "responsable", "") or "").strip()),
                        url_detail=url_for("sst_visitas", sede=sede_codigo, open_sede=sede_codigo),
                        action_label="Abrir Visitas ART",
                        active=True,
                        extra={
                            "visit_type": (_row_value(row, "tipo_visita", "") or "").strip(),
                            "observaciones": observaciones,
                            "action_required": accion_requerida,
                            "type_icon": "\U0001F477",
                            "type_label": "Visitas ART",
                            "type_short": "VIS",
                        },
                    ))

        for record in _sst_desinf_fetch_records(con):
            sede_codigo = (record.get("sede_codigo") or "").strip().upper()
            if not sede_codigo:
                continue
            sede_info = sedes_map.get(sede_codigo, {})
            fecha_realizada = _sst_calendar_parse_date(record.get("fecha_realizada"))
            fecha_programada = _sst_calendar_parse_date(record.get("fecha_programada"))
            if fecha_realizada and fecha_realizada.year == selected_year:
                event_years.add(fecha_realizada.year)
                events.append(_sst_calendar_build_event(
                    source_id=f"desinf-real-{record.get('source')}-{record.get('source_id')}",
                    source_type=record.get("source") or "desinfecciones_sede",
                    sede_codigo=sede_codigo,
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=fecha_realizada,
                    type_key="desinfeccion",
                    title="Realizada",
                    detail=_sst_calendar_short_date(fecha_realizada),
                    state_key="cumplido",
                    responsible=record.get("responsable") or "",
                    url_detail=url_for("sst_desinfecciones_home", sede=sede_codigo, open_sede=sede_codigo),
                    action_label="Abrir desinfecciones",
                    active=False,
                    extra={
                        "type_icon": "\U0001F9F9",
                        "type_label": "Desinfeccion",
                        "type_short": "DES",
                        "modality": record.get("modalidad_label") or "",
                    },
                ))
            if fecha_programada and not fecha_realizada and fecha_programada.year == selected_year:
                event_years.add(fecha_programada.year)
                overdue = fecha_programada < today_ref
                events.append(_sst_calendar_build_event(
                    source_id=f"desinf-plan-{record.get('source')}-{record.get('source_id')}",
                    source_type=record.get("source") or "desinfecciones_sede",
                    sede_codigo=sede_codigo,
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=fecha_programada,
                    type_key="desinfeccion",
                    title=("Vencida" if overdue else "Programada"),
                    detail=_sst_calendar_short_date(fecha_programada),
                    state_key=("vencido" if overdue else "programado"),
                    responsible=record.get("responsable") or "",
                    url_detail=url_for("sst_desinfecciones_home", sede=sede_codigo, open_sede=sede_codigo),
                    action_label="Abrir desinfecciones",
                    active=True,
                    extra={
                        "type_icon": "\U0001F9F9",
                        "type_label": "Desinfeccion",
                        "type_short": "DES",
                        "modality": record.get("modalidad_label") or "",
                    },
                ))

        if has_carteleria_operativa:
            for record in _sst_carteleria_aggregate_by_sede(_sst_fetch_carteleria_records(con)).values():
                event_meta = _sst_carteleria_calendar_entry(record, today_ref)
                if not event_meta or event_meta["event_date"].year != selected_year:
                    continue
                sede_info = sedes_map.get(record["sede_codigo"], {})
                event_years.add(event_meta["event_date"].year)
                events.append(_sst_calendar_build_event(
                    source_id=str(record["id"]),
                    source_type="sst_carteleria_registros",
                    sede_codigo=record["sede_codigo"],
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=event_meta["event_date"],
                    type_key="carteleria",
                    title=event_meta["title"],
                    detail=event_meta["detail"],
                    state_key=event_meta["state_key"],
                    responsible=(record.get("responsable_relevamiento") or "").strip(),
                    url_detail=url_for(
                        "sst_carteleria_home",
                        sede=record["sede_codigo"],
                        month=event_meta["event_date"].month,
                        estado=record["state_code"],
                        open_sede=record["sede_codigo"],
                        registro=record["primary_record_id"],
                    ),
                    action_label="Abrir carteleria",
                    active=(event_meta["state_key"] != "cumplido"),
                    units=max(1, int(event_meta.get("units") or 1)),
                    extra={"module_state_code": record["state_code"]},
                ))

        if has_luces_operativa:
            for record in _sst_luces_aggregate_by_sede(_sst_fetch_luces_records(con)).values():
                sede_info = sedes_map.get(record["sede_codigo"], {})
                for event_meta in _sst_luces_calendar_entries(record, today_ref):
                    if event_meta["event_date"].year != selected_year:
                        continue
                    event_years.add(event_meta["event_date"].year)
                    events.append(_sst_calendar_build_event(
                        source_id=str(record["id"]),
                        source_type="sst_luces_registros",
                        sede_codigo=record["sede_codigo"],
                        sede_nombre=sede_info.get("nombre", ""),
                        region_label=sede_info.get("region", ""),
                        event_date=event_meta["event_date"],
                        type_key="luces",
                        title=event_meta["title"],
                        detail=event_meta["detail"],
                        state_key=event_meta["state_key"],
                        responsible="",
                        url_detail=url_for(
                            "sst_luces_home",
                            sede=record["sede_codigo"],
                            estado=record["state_code"],
                            month=event_meta["event_date"].month,
                            open_sede=record["sede_codigo"],
                            registro=record["id"],
                        ),
                        action_label="Abrir luces",
                        active=(event_meta["state_key"] != "cumplido"),
                        units=max(1, int(event_meta.get("units") or 1)),
                        extra={"module_state_code": record["state_code"]},
                    ))

        if _table_exists(con, "sst_general"):
            general_rows = con.execute("""
                SELECT
                    g.id,
                    UPPER(COALESCE(g.sede_codigo, '')) AS sede_codigo,
                    COALESCE(g.fecha, '') AS fecha,
                    COALESCE(g.tipo, '') AS tipo,
                    COALESCE(g.titulo, '') AS titulo,
                    COALESCE(g.detalle, '') AS detalle,
                    COALESCE(g.estado, '') AS estado,
                    COALESCE(g.prioridad, '') AS prioridad,
                    COALESCE(g.responsable, '') AS responsable,
                    COALESCE(g.accion_correctiva, '') AS accion_correctiva,
                    COALESCE(g.fecha_objetivo, '') AS fecha_objetivo,
                    COALESCE(g.fecha_cierre, '') AS fecha_cierre
                FROM sst_general g
                ORDER BY g.id DESC
            """).fetchall()
            for row in general_rows:
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                if not sede_codigo:
                    continue
                sede_info = sedes_map.get(sede_codigo, {})
                estado_raw = (_row_value(row, "estado", "") or "").strip().upper()
                fecha_base = _sst_calendar_parse_date(_row_value(row, "fecha", ""))
                fecha_obj = _sst_calendar_parse_date(_row_value(row, "fecha_objetivo", ""))
                fecha_cierre = _sst_calendar_parse_date(_row_value(row, "fecha_cierre", ""))
                if estado_raw == "CERRADO":
                    event_date = fecha_cierre or fecha_obj or fecha_base
                    if not event_date or event_date.year != selected_year:
                        continue
                    estado = "cumplido"
                else:
                    if fecha_obj:
                        if fecha_obj.year == selected_year:
                            event_date = fecha_obj
                        elif selected_year == today_ref.year and fecha_obj < year_start:
                            event_date = today_ref
                        else:
                            continue
                        if fecha_obj < today_ref:
                            estado = "vencido"
                        elif fecha_obj <= (today_ref + timedelta(days=30)):
                            estado = "proximo"
                        else:
                            estado = "en_seguimiento"
                    else:
                        if selected_year == today_ref.year:
                            event_date = today_ref
                            estado = "en_seguimiento"
                        elif fecha_base and fecha_base.year == selected_year:
                            event_date = fecha_base
                            estado = "en_seguimiento"
                        else:
                            continue
                event_years.add(event_date.year)
                tipo_raw = (_row_value(row, "tipo", "") or "").strip().lower()
                type_key = "hallazgo" if tipo_raw == "no_conformidad" else "seguimiento"
                title = (_row_value(row, "titulo", "") or "").strip()
                if not title:
                    title = "Hallazgo abierto" if type_key == "hallazgo" else "Seguimiento operativo"
                detail_parts = []
                if (_row_value(row, "detalle", "") or "").strip():
                    detail_parts.append((_row_value(row, "detalle", "") or "").strip())
                if (_row_value(row, "accion_correctiva", "") or "").strip():
                    detail_parts.append(f"Accion: {(_row_value(row, 'accion_correctiva', '') or '').strip()}")
                if (_row_value(row, "prioridad", "") or "").strip():
                    detail_parts.append(f"Prioridad: {(_row_value(row, 'prioridad', '') or '').strip()}")
                events.append(_sst_calendar_build_event(
                    source_id=str(_row_value(row, "id", "")),
                    source_type="sst_general",
                    sede_codigo=sede_codigo,
                    sede_nombre=sede_info.get("nombre", ""),
                    region_label=sede_info.get("region", ""),
                    event_date=event_date,
                    type_key=type_key,
                    title=title,
                    detail=" · ".join(detail_parts) if detail_parts else "Accion operativa SG-SST.",
                    state_key=estado,
                    responsible=(_row_value(row, "responsable", "") or "").strip(),
                    url_detail=url_for(
                        "sst_general",
                        modo="gestion",
                        sede=sede_codigo,
                        tipo=(tipo_raw if tipo_raw else None),
                    ),
                    action_label=("Abrir hallazgos" if type_key == "hallazgo" else "Abrir seguimiento"),
                    active=(estado != "cumplido"),
                ))

        if _table_exists(con, "sst_control_objetivos") and _table_exists(con, "sst_control_relevamientos") and selected_year == today_ref.year:
            control_rows = con.execute("""
                SELECT
                    o.id AS objetivo_id,
                    LOWER(COALESCE(o.nombre, '')) AS nombre,
                    UPPER(COALESCE(r.sede_codigo, '')) AS sede_codigo,
                    r.ok,
                    COALESCE(r.actualizado_en, '') AS actualizado_en
                FROM sst_control_objetivos o
                LEFT JOIN sst_control_relevamientos r ON r.objetivo_id = o.id
                ORDER BY o.id, r.sede_codigo
            """).fetchall()
            control_map = defaultdict(dict)
            control_available = set()
            for row in control_rows:
                control_type = _sst_calendar_control_type(_row_value(row, "nombre", ""))
                if not control_type:
                    continue
                if control_type == "planos":
                    control_type = "carteleria"
                control_available.add(control_type)
                sede_codigo = (_row_value(row, "sede_codigo", "") or "").strip().upper()
                if not sede_codigo:
                    continue
                control_item = control_map[control_type].setdefault(sede_codigo, {"oks": [], "actualizados": []})
                ok_value = _row_value(row, "ok", None)
                control_item["oks"].append(None if ok_value is None else int(ok_value or 0))
                actualizado = (_row_value(row, "actualizado_en", "") or "").strip()
                if actualizado:
                    control_item["actualizados"].append(actualizado)
            for sede_item in sedes:
                sede_codigo = sede_item["codigo"]
                for control_type in ("carteleria", "luces"):
                    if control_type == "carteleria" and has_carteleria_operativa:
                        continue
                    if control_type == "luces" and has_luces_operativa:
                        continue
                    if control_type not in control_available:
                        continue
                    control_row = control_map.get(control_type, {}).get(sede_codigo)
                    if not control_row or not control_row.get("oks") or all(ok is None for ok in control_row["oks"]):
                        events.append(_sst_calendar_build_event(
                            source_id=f"{control_type}-missing-{sede_codigo}",
                            source_type="sst_control",
                            sede_codigo=sede_codigo,
                            sede_nombre=sede_item["nombre"],
                            region_label=sede_item["region"],
                            event_date=today_ref,
                            type_key=control_type,
                            title=("Relevamiento pendiente" if control_type == "carteleria" else "Sin relevar"),
                            detail="",
                            state_key="sin_datos",
                            responsible="",
                            url_detail=(
                                url_for("sst_carteleria_home", sede=sede_codigo)
                                if control_type == "carteleria"
                                else url_for("sst_luces_home", sede=sede_codigo)
                            ),
                            action_label=(
                                "Abrir carteleria"
                                if control_type == "carteleria"
                                else "Abrir luces"
                            ),
                            active=True,
                            extra={
                                "module_state_code": ("NO_RELEVADO" if control_type == "carteleria" else "SIN_RELEVAR"),
                                "type_icon": ("\U0001F6AA" if control_type == "carteleria" else "\U0001F6A8"),
                                "type_label": ("Carteleria" if control_type == "carteleria" else "Luces de emergencia"),
                            },
                        ))
                        continue
                    oks = [ok for ok in control_row.get("oks", []) if ok is not None]
                    if oks and all(int(ok or 0) == 1 for ok in oks):
                        continue
                    actualizados = sorted(control_row.get("actualizados", []))
                    anchor = _sst_calendar_parse_date(actualizados[-1]) if actualizados else today_ref
                    anchor = anchor or today_ref
                    events.append(_sst_calendar_build_event(
                        source_id=f"{control_type}-{sede_codigo}",
                        source_type="sst_control",
                        sede_codigo=sede_codigo,
                        sede_nombre=sede_item["nombre"],
                        region_label=sede_item["region"],
                        event_date=anchor,
                        type_key=control_type,
                        title=("Relevada" if control_type == "carteleria" else "Relevado"),
                        detail="Pendiente de gestion.",
                        state_key="pendiente",
                        responsible="",
                        url_detail=(
                            url_for("sst_carteleria_home", sede=sede_codigo)
                            if control_type == "carteleria"
                            else url_for("sst_luces_home", sede=sede_codigo)
                        ),
                        action_label=(
                            "Abrir carteleria"
                            if control_type == "carteleria"
                            else "Abrir luces"
                        ),
                        active=True,
                        extra={
                            "module_state_code": "RELEVADO",
                            "type_icon": ("\U0001F6AA" if control_type == "carteleria" else "\U0001F6A8"),
                            "type_label": ("Carteleria" if control_type == "carteleria" else "Luces de emergencia"),
                        },
                    ))

        return {
            "events": sorted(
                events,
                key=lambda item: (
                    item["sede_codigo"],
                    item["month"],
                    item["day"],
                    -int(item["state_rank"]),
                    item["type_label"],
                    item["title"],
                ),
            ),
            "sedes": sedes,
            "event_years": sorted(event_years),
            "matafuegos_overview": matafuegos_overview,
            "today": today_ref,
        }

    def _sst_calendar_filter_events(events, filters):
        filtered = []
        region_filter = str(filters.get("region") or "").strip().lower()
        sede_filter = str(filters.get("sede") or "").strip().upper()
        type_filter = str(filters.get("tipo") or "").strip().lower()
        state_filter = str(filters.get("estado") or "").strip().lower()
        responsable_filter = str(filters.get("responsable") or "").strip().lower()
        phase_filter = str(filters.get("fase") or "").strip().lower()
        quick_filter = str(filters.get("quick") or "").strip().lower()
        month_filter = int(filters.get("month") or 0)
        for event in events:
            if month_filter and int(event["month"]) != month_filter:
                continue
            if region_filter and region_filter != str(event.get("region", "") or "").strip().lower():
                continue
            if sede_filter and sede_filter != str(event.get("sede_codigo", "") or "").strip().upper():
                continue
            if type_filter and type_filter != str(event.get("type_key", "") or "").strip().lower():
                continue
            if state_filter and state_filter != str(event.get("state_key", "") or "").strip().lower():
                continue
            if responsable_filter and responsable_filter != str(event.get("responsible", "") or "").strip().lower():
                continue
            if phase_filter and phase_filter != str(event.get("phase_key", "") or "").strip().lower():
                continue
            state_key = str(event.get("state_key", "") or "").strip().lower()
            if quick_filter == "pendientes" and state_key not in {"pendiente", "proximo", "vencido", "en_seguimiento", "sin_datos"}:
                continue
            if quick_filter == "vencidos" and state_key != "vencido":
                continue
            if quick_filter == "finalizados" and state_key != "cumplido":
                continue
            filtered.append(event)
        return filtered

    def _sst_calendar_group_tooltip_lines(group):
        lines = []
        title = str(group.get("title") or "").strip()
        detail = str(group.get("detail") or "").strip()
        if title:
            lines.append(title)
        if detail and detail.lower() != title.lower():
            lines.append(detail)
        return lines[:2]

    def _sst_calendar_build_matrix(sedes, events):
        cells = defaultdict(list)
        for event in events:
            cells[(event["sede_codigo"], int(event["month"]))].append(event)

        payload = {}
        rows = []
        for sede in sedes:
            month_cells = []
            for month_number, month_label in SST_CALENDAR_MONTHS:
                cell_events = sorted(
                    cells.get((sede["codigo"], month_number), []),
                    key=lambda item: (
                        0 if item["type_key"] == "matafuegos" else 1,
                        _sst_calendar_phase_rank(item.get("phase_key")),
                        1 if item.get("is_suggestion") else 0,
                        -int(item["state_rank"]),
                        item["day"],
                        item["type_label"],
                        item["title"],
                    ),
                )
                type_groups = {}
                for event in cell_events:
                    group_key = "::".join([
                        str(event.get("type_key") or "").strip().lower(),
                        str(event.get("phase_key") or "sin_fase").strip().lower(),
                        ("suggestion" if event.get("is_suggestion") else "normal"),
                    ])
                    group = type_groups.setdefault(group_key, {
                        "type_key": group_key,
                        "base_type_key": event["type_key"],
                        "type_label": event["type_label"],
                        "type_short": event["type_short"],
                        "type_icon": event.get("type_icon", ""),
                        "type_badge": event.get("type_badge", event["type_short"]),
                        "state_rank": -1,
                        "state_key": event["state_key"],
                        "state_class": event["state_class"],
                        "state_label": event["state_label"],
                        "state_icon": event.get("state_icon", ""),
                        "count": 0,
                        "events_count": 0,
                        "url_detail": event.get("url_detail", ""),
                        "action_label": event.get("action_label", "Abrir"),
                        "title": event.get("title", ""),
                        "detail": event.get("detail", ""),
                        "fecha_evento": event.get("fecha_evento", ""),
                        "phase_key": event.get("phase_key", ""),
                        "phase_short": event.get("phase_short", ""),
                        "phase_label": event.get("phase_label", ""),
                        "phase_title": event.get("phase_title", ""),
                        "phase_rank": _sst_calendar_phase_rank(event.get("phase_key")),
                        "sede_codigo": sede["codigo"],
                        "sede_nombre": sede["nombre"],
                        "month": month_number,
                        "month_label": month_label,
                        "is_suggestion": bool(event.get("is_suggestion")),
                        "suggestion_label": event.get("suggestion_label", ""),
                        "events": [],
                    })
                    group["count"] += int(event.get("units", 1) or 1)
                    group["events_count"] += 1
                    group["events"].append(event)
                    if not group.get("phase_key") and event.get("phase_key"):
                        group["phase_key"] = event.get("phase_key", "")
                        group["phase_short"] = event.get("phase_short", "")
                        group["phase_label"] = event.get("phase_label", "")
                        group["phase_title"] = event.get("phase_title", "")
                    if int(event["state_rank"]) > int(group["state_rank"]):
                        group["state_rank"] = int(event["state_rank"])
                        group["state_key"] = event["state_key"]
                        group["state_class"] = event["state_class"]
                        group["state_label"] = event["state_label"]
                        group["state_icon"] = event.get("state_icon", "")
                        group["url_detail"] = event.get("url_detail", "")
                        group["action_label"] = event.get("action_label", "Abrir")
                        group["title"] = event.get("title", "")
                        group["detail"] = event.get("detail", "")
                        group["fecha_evento"] = event.get("fecha_evento", "")
                        group["phase_key"] = event.get("phase_key", "")
                        group["phase_short"] = event.get("phase_short", "")
                        group["phase_label"] = event.get("phase_label", "")
                        group["phase_title"] = event.get("phase_title", "")
                indicators = sorted(
                    type_groups.values(),
                    key=lambda item: (
                        0 if item["base_type_key"] == "matafuegos" else 1,
                        int(item.get("phase_rank") or 90),
                        1 if item.get("is_suggestion") else 0,
                        -int(item["state_rank"]),
                        -int(item["count"]),
                        item["type_label"],
                    ),
                )
                for indicator in indicators:
                    indicator["badge_count"] = (
                        int(indicator["count"])
                        if (indicator["events_count"] > 1 or indicator["base_type_key"] == "matafuegos") and int(indicator["count"]) > 1
                        else 0
                    )
                    indicator["tooltip_lines"] = _sst_calendar_group_tooltip_lines(indicator)
                    phase_prefix = f"{indicator['phase_title']}. " if indicator.get("phase_title") else ""
                    indicator["aria_label"] = (
                        f"{phase_prefix}{indicator['type_label']} en {indicator['sede_codigo']}, "
                        f"{indicator['month_label']}, {indicator['title'] or indicator['state_label']}"
                    )
                cell_key = f"{sede['codigo']}|{month_number:02d}"
                payload[cell_key] = {
                    "title": f"{month_label} - {sede['codigo']} - {sede['nombre']}",
                    "month_label": month_label,
                    "sede_codigo": sede["codigo"],
                    "sede_nombre": sede["nombre"],
                    "events": cell_events,
                    "groups": indicators,
                }
                month_cells.append({
                    "key": cell_key,
                    "month": month_number,
                    "label": month_label,
                    "count": len(cell_events),
                    "has_events": bool(cell_events),
                    "groups": indicators,
                })
            rows.append({
                "sede": sede,
                "cells": month_cells,
            })
        return rows, payload

    def _sst_calendar_mobile_rows(sedes, payload, focus_month):
        mobile_rows = []
        for sede in sedes:
            cell_key = f"{sede['codigo']}|{focus_month:02d}"
            info = payload.get(cell_key) or {}
            if not info.get("events"):
                continue
            mobile_rows.append({
                "cell_key": cell_key,
                "sede_codigo": sede["codigo"],
                "sede_nombre": sede["nombre"],
                "sede_fuero_class": sede.get("fuero_class", ""),
                "sede_fuero_color": sede.get("fuero_color", ""),
                "groups": info.get("groups", []),
                "count": len(info.get("events", [])),
            })
        return mobile_rows

    def _sst_calendar_summary(events, focus_month):
        month_events = [event for event in events if int(event["month"]) == int(focus_month)]
        open_states = {"pendiente", "proximo", "vencido", "en_seguimiento", "sin_datos"}
        return {
            "acciones_mes": len(month_events),
            "vencimientos_proximos": sum(1 for event in events if event["state_key"] == "proximo"),
            "acciones_vencidas": sum(1 for event in events if event["state_key"] == "vencido"),
            "sedes_pendientes": len({event["sede_codigo"] for event in events if event["state_key"] in open_states}),
            "seguimientos_abiertos": sum(
                1 for event in events
                if event["type_key"] in {"seguimiento", "hallazgo"} and event["state_key"] != "cumplido"
            ),
        }

    def _sst_visitas_art_build_summary(sede_info, record, docs_by_type, today_ref):
        sede_codigo = str(sede_info.get("codigo") or "").strip().upper()
        rgrl_summary = _sst_visitas_art_doc_summary((docs_by_type or {}).get("RGRL"))
        dec_summary = _sst_visitas_art_doc_summary((docs_by_type or {}).get("DEC_351_79"))
        state_code = _sst_visitas_art_state_code(record, today_ref)
        observation_code = _sst_visitas_art_observation_code(record)
        ejecutado = bool(
            record and (
                _sst_bool_flag(_row_value(record, "ejecutado", 0))
                or str(_row_value(record, "fecha_ejecucion", "") or "").strip()
                or str(_row_value(record, "evidencia_url", "") or "").strip()
            )
        )
        summary = {
            "primary_record_id": int(_row_value(record, "id", 0) or 0) if record else 0,
            "record_raw": dict(record) if record else {},
            "sede_codigo": sede_codigo,
            "sede_nombre": str(sede_info.get("nombre") or "").strip(),
            "ultima_visita": str(_row_value(record, "fecha", "") or "").strip() if record else "",
            "responsable": str(_row_value(record, "responsable", "") or "").strip() if record else "",
            "tipo_visita": str(_row_value(record, "tipo_visita", "") or "").strip() if record else "",
            "state_code": state_code,
            "state_meta": _sst_state_badge(state_code, SST_VISITA_ART_STATE_LABELS),
            "rgrl": rgrl_summary,
            "dec_351_79": dec_summary,
            "doc_overall_code": _sst_visitas_art_doc_overall_code(rgrl_summary, dec_summary),
            "observation_code": observation_code,
            "observation_meta": _sst_state_badge(observation_code, SST_VISITA_ART_OBSERVATION_LABELS),
            "observacion_art": str(_row_value(record, "observacion_art", "") or "").strip() if record else "",
            "accion_requerida": str(_row_value(record, "accion_requerida", "") or "").strip() if record else "",
            "accion_responsable": str(_row_value(record, "accion_responsable", "") or "").strip() if record else "",
            "fecha_programada": str(_row_value(record, "fecha_programada", "") or "").strip() if record else "",
            "ejecutado": ejecutado,
            "ejecutado_label": (
                "Si" if ejecutado else (
                    "No" if (
                        record and (
                            str(_row_value(record, "accion_requerida", "") or "").strip()
                            or str(_row_value(record, "observacion_art", "") or "").strip()
                        )
                    ) else "-"
                )
            ),
            "fecha_ejecucion": str(_row_value(record, "fecha_ejecucion", "") or "").strip() if record else "",
            "evidencia_url": str(_row_value(record, "evidencia_url", "") or "").strip() if record else "",
            "seguimiento_id": int(_row_value(record, "seguimiento_id", 0) or 0) if record else 0,
            "observaciones": str(_row_value(record, "observaciones", "") or "").strip() if record else "",
        }
        summary["sede_fuero_class"], summary["sede_fuero_color"] = _sst_sede_fuero_style(
            sede_codigo,
            sede_info.get("fuero"),
        )
        summary["doc_overall_meta"] = _sst_state_badge(summary["doc_overall_code"], SST_VISITA_ART_DOC_FILTER_LABELS)
        summary["next_action"] = _sst_visitas_art_next_action(summary)
        summary["anchor_year"] = _sst_visitas_art_anchor_year(summary)
        summary["visited_flag"] = bool(
            summary["ultima_visita"]
            and (_sst_calendar_parse_date(summary["ultima_visita"]) or today_ref) <= today_ref
        )
        return summary

    def _sst_visitas_art_upsert_doc(con, sede_codigo, visit_id, doc_type, payload, user_name):
        existing = con.execute("""
            SELECT id, fecha_documento, archivo, drive_url, estado_revision, notas
            FROM sst_documentos
            WHERE UPPER(COALESCE(sede_codigo, '')) = ?
              AND UPPER(COALESCE(tipo, '')) = ?
            ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
            LIMIT 1
        """, (sede_codigo, doc_type)).fetchone()
        existing = dict(existing) if existing else None

        fecha_documento = str(payload.get("fecha_documento") or "").strip()
        drive_url = str(payload.get("drive_url") or "").strip()
        notas = str(payload.get("notas") or "").strip()
        requested_state = str(payload.get("estado") or "").strip().upper()
        archivo_name = str((existing or {}).get("archivo") or "").strip()

        file = payload.get("file")
        if file and getattr(file, "filename", ""):
            if not allowed_sst_doc(file.filename):
                raise ValueError("Archivo no permitido. Use PDF/JPG/PNG.")
            safe = secure_filename(file.filename)
            archivo_name = f"{sede_codigo}_{doc_type}_{uuid.uuid4().hex}_{safe}"
            file.save(os.path.join(SST_DOCS_FOLDER, archivo_name))

        has_any_value = bool(
            fecha_documento or drive_url or notas or archivo_name or requested_state
        )
        if not has_any_value and not existing:
            return None

        final_state = _sst_visitas_art_normalize_doc_state(
            requested_state or ((existing or {}).get("estado_revision") or ""),
            bool(drive_url or archivo_name),
        )
        if not requested_state:
            if drive_url or archivo_name:
                final_state = "CARGADO"
            elif notas:
                final_state = "OBSERVADO"
            elif existing:
                final_state = _sst_visitas_art_normalize_doc_state(
                    (existing or {}).get("estado_revision") or "",
                    bool((existing or {}).get("drive_url") or (existing or {}).get("archivo")),
                )
            else:
                final_state = "SIN_DOCUMENTACION"
        if final_state == "CARGADO" and not (drive_url or archivo_name):
            final_state = "FALTANTE"

        payload_values = (
            sede_codigo,
            visit_id,
            doc_type,
            fecha_documento or None,
            archivo_name or None,
            drive_url or None,
            final_state,
            notas or None,
            user_name,
            _sst_now_ts(),
        )
        if existing:
            con.execute("""
                UPDATE sst_documentos
                SET visita_id = ?,
                    fecha_documento = ?,
                    archivo = ?,
                    drive_url = ?,
                    estado_revision = ?,
                    notas = ?,
                    actualizado_por = ?,
                    fecha_actualizacion = ?
                WHERE id = ?
            """, (
                visit_id,
                fecha_documento or None,
                archivo_name or None,
                drive_url or None,
                final_state,
                notas or None,
                user_name,
                _sst_now_ts(),
                int(existing["id"]),
            ))
            return {"id": int(existing["id"]), "state_code": final_state, "action": "documentacion_actualizada"}
        con.execute("""
            INSERT INTO sst_documentos(
                sede_codigo, visita_id, tipo, fecha_documento, archivo, drive_url,
                estado_revision, notas, actualizado_por, fecha_actualizacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, payload_values)
        return {
            "id": int(con.execute("SELECT last_insert_rowid()").fetchone()[0]),
            "state_code": final_state,
            "action": "documentacion_cargada",
        }

    def _sst_visitas_art_context(con):
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_operativo_historial_tables(con)

        today_ref = date.today()
        f_sede = (request.args.get("sede") or "").strip().upper()
        f_estado_visita = (request.args.get("estado_visita") or "").strip().upper()
        f_estado_doc = (request.args.get("estado_doc") or "").strip().upper()
        f_obs_art = (request.args.get("observaciones_art") or "").strip().upper()
        f_responsable = (request.args.get("responsable") or "").strip()
        f_q = (request.args.get("q") or "").strip().lower()
        f_open_sede = (request.args.get("open_sede") or "").strip().upper()
        f_year_raw = (request.args.get("year") or "").strip()
        f_year = int(f_year_raw) if f_year_raw.isdigit() else 0
        show_form = str(request.args.get("mostrar_form") or "").strip().lower() in {"1", "true", "si", "yes"}
        selected_record_id = int(request.args.get("registro") or 0) if str(request.args.get("registro") or "").isdigit() else 0
        prefill_sede = (request.args.get("prefill_sede") or f_open_sede or f_sede).strip().upper()

        sedes = [{
            "codigo": row["codigo"],
            "nombre": row["nombre"],
            "fuero": row["fuero"],
        } for row in _sst_fetch_sedes_base(con)]
        sedes_map = {item["codigo"]: item for item in sedes}

        visit_rows = con.execute("""
            SELECT
                id, sede_codigo, fecha, tipo_visita, responsable, estado, observaciones,
                observacion_art, accion_requerida, accion_responsable, fecha_programada,
                ejecutado, fecha_ejecucion, evidencia_url, seguimiento_id
            FROM sst_visitas
            ORDER BY date(fecha) DESC, id DESC
        """).fetchall()
        latest_by_sede = {}
        visits_by_id = {}
        responsable_options = set()
        year_options = {today_ref.year}
        for row in visit_rows:
            row_dict = dict(row)
            visits_by_id[int(row_dict["id"])] = row_dict
            sede_codigo = str(row_dict.get("sede_codigo") or "").strip().upper()
            if sede_codigo and sede_codigo not in latest_by_sede:
                latest_by_sede[sede_codigo] = row_dict
            for person_key in ("responsable", "accion_responsable"):
                person_value = str(row_dict.get(person_key) or "").strip()
                if person_value:
                    responsable_options.add(person_value)
            for date_key in ("fecha", "fecha_programada", "fecha_ejecucion"):
                parsed = _sst_calendar_parse_date(row_dict.get(date_key))
                if parsed:
                    year_options.add(parsed.year)

        docs_rows = con.execute("""
            SELECT
                id, sede_codigo, visita_id, tipo, fecha_documento, fecha_carga,
                archivo, drive_url, estado_revision, notas
            FROM sst_documentos
            WHERE UPPER(COALESCE(tipo, '')) IN ('RGRL', 'DEC_351_79')
            ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
        """).fetchall()
        docs_latest = defaultdict(dict)
        for row in docs_rows:
            row_dict = dict(row)
            sede_codigo = str(row_dict.get("sede_codigo") or "").strip().upper()
            doc_type = str(row_dict.get("tipo") or "").strip().upper()
            if sede_codigo and doc_type and doc_type not in docs_latest[sede_codigo]:
                docs_latest[sede_codigo][doc_type] = row_dict

        all_rows = []
        summary_by_sede = {}
        for sede_info in sedes:
            summary = _sst_visitas_art_build_summary(
                sede_info,
                latest_by_sede.get(sede_info["codigo"]),
                docs_latest.get(sede_info["codigo"], {}),
                today_ref,
            )
            summary_by_sede[summary["sede_codigo"]] = summary
            all_rows.append(summary)

        close_modal_url = url_for(
            "sst_visitas",
            sede=f_sede or None,
            estado_visita=f_estado_visita or None,
            estado_doc=f_estado_doc or None,
            observaciones_art=f_obs_art or None,
            responsable=f_responsable or None,
            year=(f_year or None),
            q=f_q or None,
        )
        for summary in all_rows:
            summary["url"] = url_for(
                "sst_visitas",
                sede=f_sede or None,
                estado_visita=f_estado_visita or None,
                estado_doc=f_estado_doc or None,
                observaciones_art=f_obs_art or None,
                responsable=f_responsable or None,
                year=(f_year or None),
                q=f_q or None,
                open_sede=summary["sede_codigo"],
            )
            summary["action_button_label"] = "Abrir"
            summary["modal_close_url"] = close_modal_url
            summary["modal_edit_url"] = url_for(
                "sst_visitas",
                sede=f_sede or None,
                estado_visita=f_estado_visita or None,
                estado_doc=f_estado_doc or None,
                observaciones_art=f_obs_art or None,
                responsable=f_responsable or None,
                year=(f_year or None),
                q=f_q or None,
                open_sede=summary["sede_codigo"],
                registro=(summary["primary_record_id"] or None),
                prefill_sede=summary["sede_codigo"],
                mostrar_form=1,
            )
            summary["show_cargar_documentacion"] = summary["doc_overall_code"] != "COMPLETA"
            summary["show_registrar_observacion"] = bool(summary["ultima_visita"]) and summary["observation_code"] != "OBSERVADA"
            summary["show_programar_accion"] = summary["observation_code"] == "OBSERVADA" and not summary["accion_requerida"]
            summary["show_marcar_ejecutado"] = bool(summary["accion_requerida"]) and not summary["ejecutado"]
            summary["show_followup"] = bool(
                summary["primary_record_id"]
                and summary["next_action"] != "Sin acciones pendientes."
                and not summary["seguimiento_id"]
            )

        filtered_rows = []
        kpi_visitadas = 0
        kpi_sin_visitar = 0
        kpi_docs_completa = 0
        kpi_docs_incompleta = 0
        kpi_observadas = 0
        kpi_acciones_pendientes = 0
        for summary in all_rows:
            responsible_values = {
                str(summary.get("responsable") or "").strip().lower(),
                str(summary.get("accion_responsable") or "").strip().lower(),
            }
            haystack = " ".join([
                summary["sede_codigo"],
                summary["sede_nombre"],
                summary["state_meta"]["label"],
                summary["doc_overall_meta"]["label"],
                summary["observation_meta"]["label"],
                summary.get("responsable") or "",
                summary.get("accion_responsable") or "",
                summary.get("observacion_art") or "",
                summary.get("accion_requerida") or "",
                summary.get("next_action") or "",
            ]).lower()
            if f_sede and summary["sede_codigo"] != f_sede:
                continue
            if f_estado_visita and summary["state_code"] != f_estado_visita:
                continue
            if f_estado_doc and summary["doc_overall_code"] != f_estado_doc:
                continue
            if f_obs_art and summary["observation_code"] != f_obs_art:
                continue
            if f_responsable and f_responsable.strip().lower() not in responsible_values:
                continue
            if f_year and summary["anchor_year"] and summary["anchor_year"] != f_year:
                continue
            if f_year and not summary["anchor_year"]:
                continue
            if f_q and f_q not in haystack:
                continue
            filtered_rows.append(summary)
            if summary["visited_flag"]:
                kpi_visitadas += 1
            else:
                kpi_sin_visitar += 1
            if summary["doc_overall_code"] == "COMPLETA":
                kpi_docs_completa += 1
            else:
                kpi_docs_incompleta += 1
            if summary["observation_code"] == "OBSERVADA":
                kpi_observadas += 1
            if summary["next_action"] != "Sin acciones pendientes.":
                kpi_acciones_pendientes += 1

        detail_sede = f_open_sede or prefill_sede
        selected_summary = summary_by_sede.get(detail_sede)
        selected_record = visits_by_id.get(selected_record_id)
        if not selected_record and selected_summary and selected_summary["primary_record_id"]:
            selected_record = dict(selected_summary.get("record_raw") or {})

        history_sede = f_open_sede or f_sede
        history_sql = """
            SELECT id, componente, origen_id, sede_codigo, deposito_codigo, accion, detalle, usuario, fecha_evento
            FROM sst_operativo_historial
            WHERE componente = 'visitas_art'
        """
        history_params = []
        if history_sede:
            history_sql += " AND UPPER(COALESCE(sede_codigo, '')) = ?"
            history_params.append(history_sede)
        history_sql += " ORDER BY fecha_evento DESC, id DESC LIMIT 50"
        history_rows = [dict(row) for row in con.execute(history_sql, tuple(history_params)).fetchall()]

        selected_docs = selected_summary or {}
        form_defaults = {
            "edit_id": int((selected_record or {}).get("id") or 0),
            "sede_codigo": str((selected_record or {}).get("sede_codigo") or prefill_sede or "").strip().upper(),
            "fecha": str((selected_record or {}).get("fecha") or "").strip(),
            "responsable": str((selected_record or {}).get("responsable") or "").strip(),
            "tipo_visita": str((selected_record or {}).get("tipo_visita") or "ART").strip(),
            "estado": _sst_visitas_art_normalize_state((selected_record or {}).get("estado") or ""),
            "observacion_art": str((selected_record or {}).get("observacion_art") or "").strip(),
            "accion_requerida": str((selected_record or {}).get("accion_requerida") or "").strip(),
            "accion_responsable": str((selected_record or {}).get("accion_responsable") or "").strip(),
            "fecha_programada": str((selected_record or {}).get("fecha_programada") or "").strip(),
            "ejecutado": "1" if _sst_bool_flag((selected_record or {}).get("ejecutado")) else "0",
            "fecha_ejecucion": str((selected_record or {}).get("fecha_ejecucion") or "").strip(),
            "evidencia_url": str((selected_record or {}).get("evidencia_url") or "").strip(),
            "observaciones": str((selected_record or {}).get("observaciones") or "").strip(),
            "rgrl_estado": ((selected_docs.get("rgrl") or {}).get("code") or "SIN_DOCUMENTACION"),
            "rgrl_fecha_documento": ((selected_docs.get("rgrl") or {}).get("fecha_documento") or ""),
            "rgrl_drive_url": ((selected_docs.get("rgrl") or {}).get("drive_url") or ""),
            "rgrl_observacion": ((selected_docs.get("rgrl") or {}).get("observacion") or ""),
            "rgrl_support_url": ((selected_docs.get("rgrl") or {}).get("support_url") or ""),
            "rgrl_support_label": ((selected_docs.get("rgrl") or {}).get("support_label") or ""),
            "dec_351_estado": ((selected_docs.get("dec_351_79") or {}).get("code") or "SIN_DOCUMENTACION"),
            "dec_351_fecha_documento": ((selected_docs.get("dec_351_79") or {}).get("fecha_documento") or ""),
            "dec_351_drive_url": ((selected_docs.get("dec_351_79") or {}).get("drive_url") or ""),
            "dec_351_observacion": ((selected_docs.get("dec_351_79") or {}).get("observacion") or ""),
            "dec_351_support_url": ((selected_docs.get("dec_351_79") or {}).get("support_url") or ""),
            "dec_351_support_label": ((selected_docs.get("dec_351_79") or {}).get("support_label") or ""),
        }

        return {
            "sst_section": "visitas",
            "sedes": sedes,
            "state_by_sede": filtered_rows,
            "selected_summary": selected_summary,
            "show_form": show_form,
            "form_defaults": form_defaults,
            "history_rows": history_rows,
            "estado_visita_options": [{"code": key, "label": value} for key, value in SST_VISITA_ART_STATE_LABELS.items()],
            "estado_doc_options": [{"code": key, "label": value} for key, value in SST_VISITA_ART_DOC_FILTER_LABELS.items()],
            "observacion_art_options": [{"code": key, "label": value} for key, value in SST_VISITA_ART_OBSERVATION_LABELS.items()],
            "doc_estado_form_options": [{"code": key, "label": value} for key, value in SST_VISITA_ART_DOC_STATE_LABELS.items()],
            "year_options": sorted(year_options, reverse=True),
            "responsable_options": sorted(responsable_options),
            "f_sede": f_sede,
            "f_estado_visita": f_estado_visita,
            "f_estado_doc": f_estado_doc,
            "f_obs_art": f_obs_art,
            "f_responsable": f_responsable,
            "f_year": f_year,
            "f_q": f_q,
            "f_open_sede": f_open_sede,
            "kpi_visitadas": kpi_visitadas,
            "kpi_sin_visitar": kpi_sin_visitar,
            "kpi_docs_completa": kpi_docs_completa,
            "kpi_docs_incompleta": kpi_docs_incompleta,
            "kpi_observadas": kpi_observadas,
            "kpi_acciones_pendientes": kpi_acciones_pendientes,
            "fmt_fecha": _sst_fmt_fecha,
        }

    @app.route("/sst/visitas", methods=["GET", "POST"], endpoint="sst_visitas")
    def sst_visitas():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)
        if request.method == "POST":
            action = (request.form.get("action") or "save").strip().lower()
            user_name = _sst_current_user()

            if action == "followup":
                record_id = int(request.form.get("record_id") or 0) if str(request.form.get("record_id") or "").isdigit() else 0
                record = con.execute("""
                    SELECT
                        id, sede_codigo, fecha, tipo_visita, responsable, estado, observaciones,
                        observacion_art, accion_requerida, accion_responsable, fecha_programada,
                        ejecutado, fecha_ejecucion, evidencia_url, seguimiento_id
                    FROM sst_visitas
                    WHERE id = ?
                """, (record_id,)).fetchone()
                if not record:
                    con.close()
                    flash("No se encontro la visita ART para crear seguimiento.", "warning")
                    return redirect(url_for("sst_visitas"))
                record_dict = dict(record)
                sede_row = con.execute(
                    "SELECT codigo, nombre FROM sedes_mpd WHERE UPPER(COALESCE(codigo, '')) = ?",
                    ((record_dict.get("sede_codigo") or "").strip().upper(),),
                ).fetchone()
                sede_info = {
                    "codigo": (record_dict.get("sede_codigo") or "").strip().upper(),
                    "nombre": (sede_row["nombre"] if sede_row else "") or "",
                }
                docs_latest = {}
                for doc_row in con.execute("""
                    SELECT id, sede_codigo, visita_id, tipo, fecha_documento, fecha_carga, archivo, drive_url, estado_revision, notas
                    FROM sst_documentos
                    WHERE UPPER(COALESCE(sede_codigo, '')) = ?
                      AND UPPER(COALESCE(tipo, '')) IN ('RGRL', 'DEC_351_79')
                    ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
                """, (sede_info["codigo"],)).fetchall():
                    doc_type = str(doc_row["tipo"] or "").strip().upper()
                    if doc_type and doc_type not in docs_latest:
                        docs_latest[doc_type] = dict(doc_row)
                summary = _sst_visitas_art_build_summary(sede_info, record_dict, docs_latest, date.today())
                if not summary["primary_record_id"]:
                    con.close()
                    flash("La sede no tiene una visita ART cargada para seguimiento.", "warning")
                    return redirect(url_for("sst_visitas", sede=sede_info["codigo"], open_sede=sede_info["codigo"]))
                if summary["next_action"] == "Sin acciones pendientes.":
                    con.close()
                    flash("La sede no tiene acciones pendientes para seguimiento.", "warning")
                    return redirect(url_for("sst_visitas", sede=sede_info["codigo"], open_sede=sede_info["codigo"]))
                if summary["seguimiento_id"]:
                    con.close()
                    flash("La sede ya tiene un seguimiento vinculado para Visitas ART.", "warning")
                    return redirect(url_for("sst_visitas", sede=sede_info["codigo"], open_sede=sede_info["codigo"]))
                detalle = (
                    f"Estado visita: {summary['state_meta']['label']} | "
                    f"RGRL: {summary['rgrl']['meta']['label']} | "
                    f"Decreto 351/79: {summary['dec_351_79']['meta']['label']} | "
                    f"Observacion ART: {summary['observation_meta']['label']} | "
                    f"Proxima accion: {summary['next_action']}"
                )
                if summary["accion_requerida"]:
                    detalle += f" | Accion requerida: {summary['accion_requerida']}"
                if summary["observacion_art"]:
                    detalle += f" | Observacion: {summary['observacion_art']}"
                con.execute("""
                    INSERT INTO sst_general(
                        fecha, sede_codigo, tipo, categoria, area, titulo, detalle,
                        estado, prioridad, responsable, accion_correctiva, fecha_objetivo,
                        origen_tipo, origen_id, origen_deposito_codigo
                    )
                    VALUES (?, ?, 'no_conformidad', 'Visitas ART', 'SG-SST', ?, ?, 'ABIERTO', 'Media', ?, ?, ?, 'visitas_art', ?, ?)
                """, (
                    date.today().isoformat(),
                    sede_info["codigo"],
                    f"Visitas ART {sede_info['codigo']}",
                    detalle,
                    user_name,
                    _sst_visitas_art_followup_text(summary),
                    summary["fecha_programada"] or summary["ultima_visita"] or date.today().isoformat(),
                    summary["primary_record_id"],
                    None,
                ))
                seguimiento_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                con.execute("""
                    UPDATE sst_visitas
                    SET seguimiento_id = ?, actualizado_por = ?, fecha_actualizacion = ?
                    WHERE id = ?
                """, (seguimiento_id, user_name, _sst_now_ts(), summary["primary_record_id"]))
                _sst_historial_log(
                    con,
                    "visitas_art",
                    "seguimiento",
                    summary["primary_record_id"],
                    sede_info["codigo"],
                    "",
                    f"Seguimiento #{seguimiento_id} creado.",
                )
                con.commit()
                con.close()
                flash("Seguimiento creado desde Visitas ART.", "success")
                return redirect(url_for(
                    "sst_general",
                    modo="gestion",
                    sede=sede_info["codigo"],
                    tipo="no_conformidad",
                    q=f"Visitas ART {sede_info['codigo']}",
                ))

            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            edit_id = int(request.form.get("edit_id") or 0) if str(request.form.get("edit_id") or "").isdigit() else 0
            fecha = (request.form.get("fecha") or "").strip()
            responsable = (request.form.get("responsable") or "").strip()
            tipo_visita = (request.form.get("tipo_visita") or "").strip() or "ART"
            estado = (request.form.get("estado") or "").strip().upper()
            observacion_art = (request.form.get("observacion_art") or "").strip()
            accion_requerida = (request.form.get("accion_requerida") or "").strip()
            accion_responsable = (request.form.get("accion_responsable") or "").strip()
            fecha_programada = (request.form.get("fecha_programada") or "").strip()
            ejecutado = _sst_bool_flag(request.form.get("ejecutado"))
            fecha_ejecucion = (request.form.get("fecha_ejecucion") or "").strip()
            evidencia_url = (request.form.get("evidencia_url") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()

            rgrl_payload = {
                "estado": (request.form.get("rgrl_estado") or "").strip().upper(),
                "fecha_documento": (request.form.get("rgrl_fecha_documento") or "").strip(),
                "drive_url": (request.form.get("rgrl_drive_url") or "").strip(),
                "notas": (request.form.get("rgrl_observacion") or "").strip(),
                "file": request.files.get("rgrl_archivo"),
            }
            dec_payload = {
                "estado": (request.form.get("dec_351_estado") or "").strip().upper(),
                "fecha_documento": (request.form.get("dec_351_fecha_documento") or "").strip(),
                "drive_url": (request.form.get("dec_351_drive_url") or "").strip(),
                "notas": (request.form.get("dec_351_observacion") or "").strip(),
                "file": request.files.get("dec_351_archivo"),
            }
            has_doc_payload = any([
                rgrl_payload["estado"], rgrl_payload["fecha_documento"], rgrl_payload["drive_url"], rgrl_payload["notas"],
                bool(rgrl_payload["file"] and getattr(rgrl_payload["file"], "filename", "")),
                dec_payload["estado"], dec_payload["fecha_documento"], dec_payload["drive_url"], dec_payload["notas"],
                bool(dec_payload["file"] and getattr(dec_payload["file"], "filename", "")),
            ])
            has_visit_payload = any([
                fecha, responsable, tipo_visita, estado, observacion_art, accion_requerida,
                accion_responsable, fecha_programada, fecha_ejecucion, evidencia_url, observaciones, ejecutado,
            ])

            if not sede_codigo:
                con.close()
                flash("La sede es obligatoria.", "error")
                return redirect(url_for("sst_visitas", mostrar_form=1, prefill_sede=request.args.get("prefill_sede") or None))
            if has_visit_payload and not fecha:
                con.close()
                flash("La fecha de visita es obligatoria para guardar la visita ART.", "error")
                return redirect(url_for("sst_visitas", sede=sede_codigo, open_sede=sede_codigo, mostrar_form=1, prefill_sede=sede_codigo, registro=(edit_id or None)))
            if not has_visit_payload and not has_doc_payload and not edit_id:
                con.close()
                flash("No hay datos para guardar en Visitas ART.", "warning")
                return redirect(url_for("sst_visitas", sede=sede_codigo, open_sede=sede_codigo, mostrar_form=1, prefill_sede=sede_codigo))

            existing_record = None
            if edit_id:
                existing_row = con.execute("""
                    SELECT
                        id, sede_codigo, fecha, tipo_visita, responsable, estado, observaciones,
                        observacion_art, accion_requerida, accion_responsable, fecha_programada,
                        ejecutado, fecha_ejecucion, evidencia_url, seguimiento_id
                    FROM sst_visitas
                    WHERE id = ?
                """, (edit_id,)).fetchone()
                existing_record = dict(existing_row) if existing_row else None

            previous_state = _sst_visitas_art_state_code(existing_record, date.today()) if existing_record else ""
            previous_observation = str((existing_record or {}).get("observacion_art") or "").strip()
            previous_action = str((existing_record or {}).get("accion_requerida") or "").strip()
            previous_executed = bool(
                existing_record and (
                    _sst_bool_flag((existing_record or {}).get("ejecutado"))
                    or str((existing_record or {}).get("fecha_ejecucion") or "").strip()
                    or str((existing_record or {}).get("evidencia_url") or "").strip()
                )
            )

            record_id = edit_id
            if has_visit_payload:
                payload = (
                    sede_codigo,
                    fecha,
                    tipo_visita or "ART",
                    responsable or None,
                    estado or None,
                    observaciones or None,
                    observacion_art or None,
                    accion_requerida or None,
                    accion_responsable or None,
                    fecha_programada or None,
                    ejecutado,
                    fecha_ejecucion or None,
                    evidencia_url or None,
                    user_name,
                    _sst_now_ts(),
                )
                if existing_record:
                    con.execute("""
                        UPDATE sst_visitas
                        SET sede_codigo = ?, fecha = ?, tipo_visita = ?, responsable = ?, estado = ?,
                            observaciones = ?, observacion_art = ?, accion_requerida = ?, accion_responsable = ?,
                            fecha_programada = ?, ejecutado = ?, fecha_ejecucion = ?, evidencia_url = ?,
                            actualizado_por = ?, fecha_actualizacion = ?
                        WHERE id = ?
                    """, payload + (edit_id,))
                else:
                    con.execute("""
                        INSERT INTO sst_visitas(
                            sede_codigo, fecha, tipo_visita, responsable, estado, observaciones,
                            observacion_art, accion_requerida, accion_responsable, fecha_programada,
                            ejecutado, fecha_ejecucion, evidencia_url, actualizado_por, fecha_actualizacion
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, payload)
                    record_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

            try:
                doc_results = []
                for doc_type, doc_payload in (("RGRL", rgrl_payload), ("DEC_351_79", dec_payload)):
                    doc_result = _sst_visitas_art_upsert_doc(con, sede_codigo, (record_id or None), doc_type, doc_payload, user_name)
                    if doc_result:
                        doc_results.append((doc_type, doc_result))
            except ValueError as exc:
                con.close()
                flash(str(exc), "error")
                return redirect(url_for("sst_visitas", sede=sede_codigo, open_sede=sede_codigo, mostrar_form=1, prefill_sede=sede_codigo, registro=(record_id or None)))

            sede_row = con.execute(
                "SELECT codigo, nombre FROM sedes_mpd WHERE UPPER(COALESCE(codigo, '')) = ?",
                (sede_codigo,),
            ).fetchone()
            sede_info = {"codigo": sede_codigo, "nombre": (sede_row["nombre"] if sede_row else "") or ""}
            record_after = None
            if record_id:
                row = con.execute("""
                    SELECT
                        id, sede_codigo, fecha, tipo_visita, responsable, estado, observaciones,
                        observacion_art, accion_requerida, accion_responsable, fecha_programada,
                        ejecutado, fecha_ejecucion, evidencia_url, seguimiento_id
                    FROM sst_visitas
                    WHERE id = ?
                """, (record_id,)).fetchone()
                record_after = dict(row) if row else None
            docs_after = {}
            for row in con.execute("""
                SELECT id, sede_codigo, visita_id, tipo, fecha_documento, fecha_carga, archivo, drive_url, estado_revision, notas
                FROM sst_documentos
                WHERE UPPER(COALESCE(sede_codigo, '')) = ?
                  AND UPPER(COALESCE(tipo, '')) IN ('RGRL', 'DEC_351_79')
                ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
            """, (sede_codigo,)).fetchall():
                doc_type = str(row["tipo"] or "").strip().upper()
                if doc_type and doc_type not in docs_after:
                    docs_after[doc_type] = dict(row)
            summary_after = _sst_visitas_art_build_summary(sede_info, record_after, docs_after, date.today())

            if has_visit_payload:
                _sst_historial_log(
                    con,
                    "visitas_art",
                    "actualizacion" if existing_record else "alta",
                    record_id,
                    sede_codigo,
                    "",
                    "Actualizacion de visita ART por sede." if existing_record else "Alta de visita ART por sede.",
                )
            if previous_state and previous_state != summary_after["state_code"]:
                _sst_historial_log(
                    con,
                    "visitas_art",
                    "cambio_estado",
                    record_id or None,
                    sede_codigo,
                    "",
                    f"{SST_VISITA_ART_STATE_LABELS.get(previous_state, previous_state)} -> {summary_after['state_meta']['label']}",
                )
            if summary_after["observacion_art"] and summary_after["observacion_art"] != previous_observation:
                _sst_historial_log(
                    con,
                    "visitas_art",
                    "observacion_registrada",
                    record_id or None,
                    sede_codigo,
                    "",
                    summary_after["observacion_art"],
                )
            if summary_after["accion_requerida"] and summary_after["accion_requerida"] != previous_action:
                detail = summary_after["accion_requerida"]
                if summary_after["fecha_programada"]:
                    detail += f" | Fecha programada: {summary_after['fecha_programada']}"
                _sst_historial_log(con, "visitas_art", "accion_programada", record_id or None, sede_codigo, "", detail)
            if summary_after["ejecutado"] and not previous_executed:
                _sst_historial_log(
                    con,
                    "visitas_art",
                    "accion_ejecutada",
                    record_id or None,
                    sede_codigo,
                    "",
                    summary_after["fecha_ejecucion"] or "Accion marcada como ejecutada.",
                )
            if summary_after["state_code"] == "CERRADA" and previous_state != "CERRADA":
                _sst_historial_log(con, "visitas_art", "cierre", record_id or None, sede_codigo, "", "Observacion ART cerrada.")
            for doc_type, doc_result in doc_results:
                _sst_historial_log(
                    con,
                    "visitas_art",
                    doc_result["action"],
                    record_id or doc_result["id"],
                    sede_codigo,
                    "",
                    f"{SST_VISITA_ART_DOC_TYPE_LABELS.get(doc_type, doc_type)}: {SST_VISITA_ART_DOC_STATE_LABELS.get(doc_result['state_code'], doc_result['state_code'])}",
                )

            con.commit()
            con.close()
            flash("Registro de Visitas ART guardado.", "success")
            return redirect(url_for(
                "sst_visitas",
                sede=sede_codigo,
                open_sede=sede_codigo,
                prefill_sede=sede_codigo,
                mostrar_form=1,
                registro=(record_id or None),
            ))

        context = _sst_visitas_art_context(con)
        con.close()
        return render_template("sst_visitas.html", **context)

    @app.route("/sst/visitas/cargar", methods=["GET", "POST"], endpoint="sst_visita_cargar")
    def sst_visita_cargar():
        sede_codigo = (request.values.get("sede") or request.values.get("sede_codigo") or "").strip().upper()
        return redirect(url_for(
            "sst_visitas",
            sede=sede_codigo or None,
            open_sede=sede_codigo or None,
            prefill_sede=sede_codigo or None,
            mostrar_form=1,
        ))

    @app.route("/sst/docs/subir", methods=["GET", "POST"], endpoint="sst_doc_subir")
    def sst_doc_subir():
        sede_codigo = (request.values.get("sede") or request.values.get("sede_codigo") or "").strip().upper()
        return redirect(url_for(
            "sst_visitas",
            sede=sede_codigo or None,
            open_sede=sede_codigo or None,
            prefill_sede=sede_codigo or None,
            mostrar_form=1,
        ))

    @app.route("/sst/docs/archivo/<path:filename>", methods=["GET"], endpoint="sst_doc_archivo")
    def sst_doc_archivo(filename):
        return send_from_directory(SST_DOCS_FOLDER, filename, as_attachment=False)

    SST_DESINFECCION_STATE_LABELS = {
        "SIN_REGISTRO": "Sin registro",
        "PENDIENTE_DE_PROGRAMACION": "Pendiente de programacion",
        "PROGRAMADA": "Programada",
        "REALIZADA": "Realizada",
        "VENCIDA": "Vencida",
        "OBSERVADA": "Observada",
        "CANCELADA": "Cancelada",
    }
    SST_DESINFECCION_MODALIDAD_LABELS = {
        "TERCERO_CONTRATADO": "Tercero contratado",
        "PERSONAL_INTENDENCIA": "Personal de Intendencia",
    }
    SST_DESINFECCION_PENDING_STATES = {
        "SIN_REGISTRO",
        "PENDIENTE_DE_PROGRAMACION",
        "PROGRAMADA",
        "VENCIDA",
        "OBSERVADA",
        "CANCELADA",
    }

    def ensure_sst_desinfecciones_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS desinfecciones_sede(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cod_sede TEXT NOT NULL,
                fecha TEXT,
                empresa TEXT,
                observaciones TEXT
            )
        """)
        ensure_cols(con, "desinfecciones_sede", [
            ("fecha_programada", "TEXT"),
            ("fecha_realizada", "TEXT"),
            ("modalidad", "TEXT"),
            ("responsable", "TEXT"),
            ("producto_detalle", "TEXT"),
            ("estado", "TEXT"),
            ("seguimiento_id", "INTEGER"),
            ("activo", "INTEGER DEFAULT 1"),
            ("creado_por", "TEXT"),
            ("actualizado_por", "TEXT"),
            ("fecha_creacion", "TEXT"),
            ("fecha_actualizacion", "TEXT"),
        ])
        con.execute("CREATE INDEX IF NOT EXISTS idx_desinf_sede_fecha ON desinfecciones_sede(cod_sede, fecha)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_desinf_sede_estado ON desinfecciones_sede(cod_sede, estado)")
        con.commit()

    def _sst_desinf_normalize_modalidad(value, responsable=""):
        raw = _sst_clean_upper(value)
        merged = " ".join([raw, _sst_clean_upper(responsable)]).strip()
        if any(token in merged for token in ("INTENDENCIA", "INTERNO", "PERSONAL")):
            return "PERSONAL_INTENDENCIA"
        if raw in SST_DESINFECCION_MODALIDAD_LABELS:
            return raw
        if merged:
            return "TERCERO_CONTRATADO"
        return ""

    def _sst_desinf_normalize_state(value):
        raw = _sst_clean_upper(value)
        legacy_map = {
            "SIN REGISTRO": "SIN_REGISTRO",
            "PENDIENTE": "PENDIENTE_DE_PROGRAMACION",
            "PENDIENTE DE PROGRAMACION": "PENDIENTE_DE_PROGRAMACION",
            "PENDIENTE PROGRAMACION": "PENDIENTE_DE_PROGRAMACION",
            "PROGRAMADA": "PROGRAMADA",
            "REALIZADA": "REALIZADA",
            "VENCIDA": "VENCIDA",
            "OBSERVADA": "OBSERVADA",
            "CANCELADA": "CANCELADA",
        }
        normalized = legacy_map.get(raw, raw)
        return normalized if normalized in SST_DESINFECCION_STATE_LABELS else ""

    def _sst_desinf_auto_state(record, today_ref=None):
        today_value = today_ref or date.today()
        manual_state = _sst_desinf_normalize_state(record.get("estado"))
        if manual_state in {"OBSERVADA", "CANCELADA"}:
            return manual_state
        fecha_programada = _sst_calendar_parse_date(record.get("fecha_programada"))
        fecha_realizada = _sst_calendar_parse_date(record.get("fecha_realizada") or record.get("fecha"))
        if fecha_programada and not fecha_realizada:
            return "VENCIDA" if fecha_programada < today_value else "PROGRAMADA"
        if fecha_realizada:
            return "REALIZADA"
        return manual_state or "SIN_REGISTRO"

    def _sst_desinf_next_action(state_code):
        mapping = {
            "SIN_REGISTRO": "Registrar primera desinfeccion.",
            "PENDIENTE_DE_PROGRAMACION": "Programar proxima.",
            "PROGRAMADA": "Coordinar ejecucion.",
            "REALIZADA": "Definir proxima fecha.",
            "VENCIDA": "Reprogramar.",
            "OBSERVADA": "Resolver observacion.",
            "CANCELADA": "Definir nueva fecha.",
        }
        return mapping.get(_sst_desinf_normalize_state(state_code), "Revisar gestion de desinfecciones.")

    def _sst_desinf_fetch_records(con):
        ensure_sst_desinfecciones_tables(con)
        records = []
        if _table_exists(con, "desinfecciones_sede"):
            rows = con.execute("""
                SELECT
                    id,
                    UPPER(COALESCE(cod_sede, '')) AS sede_codigo,
                    COALESCE(fecha, '') AS fecha,
                    COALESCE(fecha_programada, '') AS fecha_programada,
                    COALESCE(fecha_realizada, '') AS fecha_realizada,
                    COALESCE(modalidad, '') AS modalidad,
                    COALESCE(responsable, '') AS responsable,
                    COALESCE(empresa, '') AS empresa,
                    COALESCE(producto_detalle, '') AS producto_detalle,
                    COALESCE(estado, '') AS estado,
                    COALESCE(observaciones, '') AS observaciones,
                    COALESCE(seguimiento_id, 0) AS seguimiento_id,
                    COALESCE(activo, 1) AS activo,
                    COALESCE(creado_por, '') AS creado_por,
                    COALESCE(actualizado_por, '') AS actualizado_por,
                    COALESCE(fecha_creacion, '') AS fecha_creacion,
                    COALESCE(fecha_actualizacion, '') AS fecha_actualizacion
                FROM desinfecciones_sede
                WHERE COALESCE(activo, 1) = 1
                ORDER BY COALESCE(fecha_realizada, fecha_programada, fecha, fecha_actualizacion, fecha_creacion, '') DESC, id DESC
            """).fetchall()
            for row in rows:
                responsable = (_row_value(row, "responsable", "") or "").strip() or (_row_value(row, "empresa", "") or "").strip()
                modalidad = _sst_desinf_normalize_modalidad(_row_value(row, "modalidad", ""), responsable)
                fecha_programada = (_row_value(row, "fecha_programada", "") or "").strip()
                fecha_realizada = (_row_value(row, "fecha_realizada", "") or "").strip()
                if not fecha_realizada and not fecha_programada:
                    fecha_realizada = (_row_value(row, "fecha", "") or "").strip()
                manual_state = _sst_desinf_normalize_state(_row_value(row, "estado", ""))
                state_code = manual_state or _sst_desinf_auto_state({
                    "fecha": _row_value(row, "fecha", ""),
                    "fecha_programada": fecha_programada,
                    "fecha_realizada": fecha_realizada,
                    "estado": manual_state,
                }, date.today())
                anchor_date = fecha_realizada or fecha_programada or (_row_value(row, "fecha", "") or "").strip() or (_row_value(row, "fecha_actualizacion", "") or "").strip()[:10]
                records.append({
                    "id": int(_row_value(row, "id", 0) or 0),
                    "source_id": int(_row_value(row, "id", 0) or 0),
                    "source": "desinfecciones_sede",
                    "editable": True,
                    "sede_codigo": (_row_value(row, "sede_codigo", "") or "").strip().upper(),
                    "fecha": (_row_value(row, "fecha", "") or "").strip(),
                    "fecha_programada": fecha_programada,
                    "fecha_realizada": fecha_realizada,
                    "modalidad": modalidad,
                    "modalidad_label": SST_DESINFECCION_MODALIDAD_LABELS.get(modalidad, "-"),
                    "responsable": responsable,
                    "producto_detalle": (_row_value(row, "producto_detalle", "") or "").strip(),
                    "estado": manual_state,
                    "state_code": state_code,
                    "state_meta": _sst_state_badge(state_code, SST_DESINFECCION_STATE_LABELS),
                    "observaciones": (_row_value(row, "observaciones", "") or "").strip(),
                    "seguimiento_id": int(_row_value(row, "seguimiento_id", 0) or 0),
                    "usuario": (_row_value(row, "actualizado_por", "") or "").strip() or (_row_value(row, "creado_por", "") or "").strip(),
                    "anchor_date": anchor_date,
                })
        if _table_exists(con, "obras_sede"):
            cols_obras = _table_cols(con, "obras_sede")

            def _obras_expr(col_name, alias_name):
                if col_name in cols_obras:
                    return f"COALESCE({col_name}, '') AS {alias_name}"
                return f"'' AS {alias_name}"

            rows = con.execute("""
                SELECT
                    id,
                    """ + _obras_expr("codigo_sede", "sede_codigo").replace("COALESCE(codigo_sede, '')", "UPPER(COALESCE(codigo_sede, ''))") + """,
                    """ + _obras_expr("estado", "estado") + """,
                    """ + _obras_expr("tipo", "tipo") + """,
                    """ + _obras_expr("titulo", "titulo") + """,
                    """ + _obras_expr("descripcion", "descripcion") + """,
                    """ + _obras_expr("observaciones", "observaciones") + """,
                    """ + _obras_expr("responsable_actual", "responsable_actual") + """,
                    """ + _obras_expr("fecha_solicitud", "fecha_solicitud") + """,
                    """ + _obras_expr("fecha_inicio", "fecha_inicio") + """,
                    """ + _obras_expr("fecha_fin_prevista", "fecha_fin_prevista") + """,
                    """ + _obras_expr("fecha_fin_real", "fecha_fin_real") + """
                FROM obras_sede
                WHERE
                    LOWER(COALESCE(tipo, '')) LIKE '%desinfecc%'
                    OR LOWER(COALESCE(titulo, '')) LIKE '%desinfecc%'
                    OR LOWER(COALESCE(descripcion, '')) LIKE '%desinfecc%'
                ORDER BY COALESCE(fecha_fin_real, fecha_inicio, fecha_fin_prevista, fecha_solicitud, '') DESC, id DESC
            """).fetchall()
            for row in rows:
                responsable = (_row_value(row, "responsable_actual", "") or "").strip()
                detalle = " | ".join([
                    (_row_value(row, "tipo", "") or "").strip(),
                    (_row_value(row, "titulo", "") or "").strip(),
                    (_row_value(row, "descripcion", "") or "").strip(),
                ]).strip(" |")
                modalidad = _sst_desinf_normalize_modalidad("", detalle)
                fecha_programada = (
                    (_row_value(row, "fecha_inicio", "") or "").strip()
                    or (_row_value(row, "fecha_fin_prevista", "") or "").strip()
                    or (_row_value(row, "fecha_solicitud", "") or "").strip()
                )
                fecha_realizada = (_row_value(row, "fecha_fin_real", "") or "").strip()
                raw_state = _sst_clean_upper(_row_value(row, "estado", ""))
                manual_state = "REALIZADA" if raw_state == "FINALIZADA" and fecha_realizada else ""
                state_code = manual_state or _sst_desinf_auto_state({
                    "fecha_programada": fecha_programada,
                    "fecha_realizada": fecha_realizada,
                    "estado": manual_state,
                }, date.today())
                anchor_date = fecha_realizada or fecha_programada
                records.append({
                    "id": f"obra-{int(_row_value(row, 'id', 0) or 0)}",
                    "source_id": int(_row_value(row, "id", 0) or 0),
                    "source": "obras_sede",
                    "editable": False,
                    "sede_codigo": (_row_value(row, "sede_codigo", "") or "").strip().upper(),
                    "fecha": (_row_value(row, "fecha_solicitud", "") or "").strip(),
                    "fecha_programada": fecha_programada,
                    "fecha_realizada": fecha_realizada,
                    "modalidad": modalidad,
                    "modalidad_label": SST_DESINFECCION_MODALIDAD_LABELS.get(modalidad, "-"),
                    "responsable": responsable,
                    "producto_detalle": detalle,
                    "estado": manual_state,
                    "state_code": state_code,
                    "state_meta": _sst_state_badge(state_code, SST_DESINFECCION_STATE_LABELS),
                    "observaciones": (_row_value(row, "observaciones", "") or "").strip() or detalle,
                    "seguimiento_id": 0,
                    "usuario": "",
                    "anchor_date": anchor_date,
                })
        return records

    def _sst_desinf_empty_summary(sede_info):
        return {
            "sede_codigo": (_row_value(sede_info, "codigo", "") or "").strip().upper(),
            "sede_nombre": (_row_value(sede_info, "nombre", "") or "").strip(),
            "ultima_desinfeccion": "",
            "modalidad": "",
            "modalidad_label": "-",
            "responsable": "",
            "proxima_prevista": "",
            "state_code": "SIN_REGISTRO",
            "state_meta": _sst_state_badge("SIN_REGISTRO", SST_DESINFECCION_STATE_LABELS),
            "next_action": _sst_desinf_next_action("SIN_REGISTRO"),
            "observaciones": "",
            "record_count": 0,
            "primary_record_id": 0,
            "seguimiento_id": 0,
            "history_records": [],
        }

    def _sst_desinf_aggregate_by_sede(records):
        grouped = defaultdict(list)
        for record in records:
            sede_codigo = (record.get("sede_codigo") or "").strip().upper()
            if sede_codigo:
                grouped[sede_codigo].append(record)
        summary_map = {}
        today_ref = date.today()
        for sede_codigo, items in grouped.items():
            ordered = sorted(items, key=lambda item: ((item.get("anchor_date") or ""), int(item.get("source_id") or 0)), reverse=True)
            latest_record = ordered[0]
            latest_realizadas = sorted(
                [item for item in items if item.get("fecha_realizada")],
                key=lambda item: item.get("fecha_realizada") or "",
                reverse=True,
            )
            pending_programadas = sorted(
                [
                    item for item in items
                    if item.get("fecha_programada")
                    and not item.get("fecha_realizada")
                    and item.get("state_code") not in {"CANCELADA", "REALIZADA"}
                ],
                key=lambda item: item.get("fecha_programada") or "",
            )
            manual_latest = next((item for item in ordered if item.get("state_code") in {"OBSERVADA", "CANCELADA"}), None)
            if manual_latest:
                state_code = manual_latest["state_code"]
            elif pending_programadas:
                first_pending = pending_programadas[0]
                pending_date = _sst_calendar_parse_date(first_pending.get("fecha_programada"))
                state_code = "VENCIDA" if pending_date and pending_date < today_ref else "PROGRAMADA"
            elif latest_realizadas:
                state_code = "PENDIENTE_DE_PROGRAMACION"
            else:
                state_code = "SIN_REGISTRO"
            current_record = next((item for item in pending_programadas if item.get("editable")), None)
            if not current_record:
                current_record = next((item for item in ordered if item.get("editable")), None)
            if not current_record:
                current_record = latest_record
            history_records = []
            for item in ordered[:24]:
                history_date = item.get("fecha_realizada") or item.get("fecha_programada") or item.get("fecha") or ""
                history_records.append({
                    "fecha": history_date,
                    "modalidad_label": item.get("modalidad_label") or "-",
                    "responsable": item.get("responsable") or "-",
                    "state_meta": item.get("state_meta") or _sst_state_badge(item.get("state_code"), SST_DESINFECCION_STATE_LABELS),
                    "observaciones": item.get("observaciones") or item.get("producto_detalle") or "",
                    "usuario": item.get("usuario") or "",
                    "editable": bool(item.get("editable")),
                    "source_id": int(item.get("source_id") or 0) if item.get("editable") else 0,
                })
            summary_map[sede_codigo] = {
                "sede_codigo": sede_codigo,
                "sede_nombre": "",
                "ultima_desinfeccion": (latest_realizadas[0].get("fecha_realizada") if latest_realizadas else ""),
                "modalidad": current_record.get("modalidad") or latest_record.get("modalidad") or "",
                "modalidad_label": current_record.get("modalidad_label") or latest_record.get("modalidad_label") or "-",
                "responsable": current_record.get("responsable") or latest_record.get("responsable") or "",
                "proxima_prevista": (pending_programadas[0].get("fecha_programada") if pending_programadas else ""),
                "state_code": state_code,
                "state_meta": _sst_state_badge(state_code, SST_DESINFECCION_STATE_LABELS),
                "next_action": _sst_desinf_next_action(state_code),
                "observaciones": current_record.get("observaciones") or latest_record.get("observaciones") or "",
                "record_count": len(items),
                "primary_record_id": int(current_record.get("source_id") or 0) if current_record.get("editable") else 0,
                "seguimiento_id": int(current_record.get("seguimiento_id") or 0) if current_record.get("editable") else 0,
                "history_records": history_records,
                "current_record": current_record,
                "show_followup": bool(int(current_record.get("source_id") or 0) > 0 and current_record.get("editable") and state_code in SST_DESINFECCION_PENDING_STATES and not int(current_record.get("seguimiento_id") or 0)),
            }
        return summary_map

    def _sst_desinfecciones_context(con):
        ensure_sst_general_table(con)
        ensure_sst_operativo_historial_tables(con)
        ensure_sst_desinfecciones_tables(con)
        sedes = list(_sst_fetch_sedes_base(con))
        all_records = _sst_desinf_fetch_records(con)
        summary_map = _sst_desinf_aggregate_by_sede(all_records)
        f_sede = (_sst_clean_upper(request.args.get("sede")) or "").strip().upper()
        f_estado = _sst_desinf_normalize_state(request.args.get("estado"))
        f_modalidad = _sst_desinf_normalize_modalidad(request.args.get("modalidad"))
        f_q = (request.args.get("q") or "").strip().lower()
        f_open_sede = (_sst_clean_upper(request.args.get("open_sede")) or "").strip().upper()
        f_registro = _sst_int_nonneg(request.args.get("registro") or request.args.get("edit"))
        try:
            f_year = max(int(request.args.get("year") or 0), 0)
        except Exception:
            f_year = 0
        try:
            f_month = max(int(request.args.get("month") or 0), 0)
        except Exception:
            f_month = 0
        visible_sedes = [item for item in sedes if not f_sede or item["codigo"] == f_sede]
        base_rows = []
        for sede_info in visible_sedes:
            sede_codigo = (_row_value(sede_info, "codigo", "") or "").strip().upper()
            sede_fuero_class, sede_fuero_color = _sst_sede_fuero_style(sede_codigo, _row_value(sede_info, "fuero", ""))
            row = dict(summary_map.get(sede_codigo) or _sst_desinf_empty_summary(sede_info))
            row["sede_codigo"] = sede_codigo
            row["sede_nombre"] = (_row_value(sede_info, "nombre", "") or "").strip()
            row["sede_fuero_class"] = sede_fuero_class
            row["sede_fuero_color"] = sede_fuero_color
            row["url"] = url_for(
                "sst_desinfecciones_home",
                sede=f_sede or None,
                estado=f_estado or None,
                modalidad=f_modalidad or None,
                year=(f_year or None),
                month=(f_month or None),
                q=f_q or None,
                open_sede=sede_codigo,
                registro=(int(row.get("primary_record_id") or 0) or None),
            )
            haystack = " ".join([
                row["sede_codigo"],
                row["sede_nombre"],
                row.get("modalidad_label") or "",
                row.get("responsable") or "",
                row.get("next_action") or "",
                row.get("observaciones") or "",
            ]).lower()
            row["haystack"] = haystack
            base_rows.append(row)
        filtered_rows = []
        for row in base_rows:
            if f_estado and row["state_code"] != f_estado:
                continue
            if f_modalidad and row.get("modalidad") != f_modalidad:
                continue
            if f_year or f_month:
                date_candidates = []
                for key in ("ultima_desinfeccion", "proxima_prevista"):
                    date_value = _sst_calendar_parse_date(row.get(key))
                    if date_value:
                        date_candidates.append(date_value)
                if not date_candidates:
                    continue
                if f_year and not any(item.year == f_year for item in date_candidates):
                    continue
                if f_month and not any(item.month == f_month for item in date_candidates):
                    continue
            if f_q and f_q not in row["haystack"]:
                continue
            filtered_rows.append(row)
        state_by_sede = sorted(filtered_rows, key=lambda item: item["sede_codigo"])
        selected_record = next((item for item in all_records if item.get("editable") and int(item.get("source_id") or 0) == f_registro), None)
        detail_sede = f_open_sede or (selected_record.get("sede_codigo") if selected_record else "")
        selected_summary = next((item for item in base_rows if item["sede_codigo"] == detail_sede), None)
        if selected_summary:
            selected_summary = dict(selected_summary)
            selected_summary["modal_close_url"] = url_for(
                "sst_desinfecciones_home",
                sede=f_sede or None,
                estado=f_estado or None,
                modalidad=f_modalidad or None,
                year=(f_year or None),
                month=(f_month or None),
                q=f_q or None,
            )
            selected_summary["modal_edit_url"] = url_for(
                "sst_desinfecciones_home",
                sede=f_sede or None,
                estado=f_estado or None,
                modalidad=f_modalidad or None,
                year=(f_year or None),
                month=(f_month or None),
                q=f_q or None,
                open_sede=selected_summary["sede_codigo"],
                registro=(int(selected_summary.get("primary_record_id") or 0) or None),
                prefill_sede=selected_summary["sede_codigo"],
                mostrar_form=1,
            )
            selected_summary["history_url"] = f"{selected_summary['modal_close_url']}#sst-desinfecciones-historial"
        prefill_sede = (_sst_clean_upper(request.args.get("prefill_sede") or detail_sede or f_sede) or "").strip().upper()
        show_form = bool(request.method == "POST" or request.args.get("mostrar_form"))
        form_defaults = {
            "edit_id": int(selected_record.get("source_id") or 0) if selected_record else 0,
            "sede_codigo": (selected_record.get("sede_codigo") if selected_record else prefill_sede),
            "fecha_programada": ((selected_record.get("fecha_programada") or "") if selected_record else ""),
            "fecha_realizada": ((selected_record.get("fecha_realizada") or "") if selected_record else ""),
            "modalidad": ((selected_record.get("modalidad") or "") if selected_record else ""),
            "responsable": ((selected_record.get("responsable") or "") if selected_record else ""),
            "producto_detalle": ((selected_record.get("producto_detalle") or "") if selected_record else ""),
            "estado": ((selected_record.get("estado") or "") if selected_record else ""),
            "observaciones": ((selected_record.get("observaciones") or "") if selected_record else ""),
        }
        if request.method == "POST" and (request.form.get("action") or "save").strip().lower() == "save":
            form_defaults.update({
                "edit_id": _sst_int_nonneg(request.form.get("edit_id")),
                "sede_codigo": (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper(),
                "fecha_programada": (request.form.get("fecha_programada") or "").strip(),
                "fecha_realizada": (request.form.get("fecha_realizada") or "").strip(),
                "modalidad": _sst_desinf_normalize_modalidad(request.form.get("modalidad")),
                "responsable": (request.form.get("responsable") or "").strip(),
                "producto_detalle": (request.form.get("producto_detalle") or "").strip(),
                "estado": _sst_desinf_normalize_state(request.form.get("estado")),
                "observaciones": (request.form.get("observaciones") or "").strip(),
            })
        history_rows = selected_summary["history_records"] if selected_summary else []
        if not history_rows:
            merged_history = []
            for row in state_by_sede:
                merged_history.extend(row.get("history_records") or [])
            history_rows = merged_history[:24]
        year_options = sorted({
            item.year
            for row in base_rows
            for item in [
                _sst_calendar_parse_date(row.get("ultima_desinfeccion")),
                _sst_calendar_parse_date(row.get("proxima_prevista")),
            ]
            if item
        })
        return {
            "sst_section": "desinfecciones",
            "sedes": sedes,
            "operativa_nav": build_operativa_nav_context(
                sedes,
                detail_sede or f_open_sede or f_sede or (state_by_sede[0]["sede_codigo"] if state_by_sede else ""),
                "sst_desinfecciones",
                filters={
                    "estado": f_estado,
                    "modalidad": f_modalidad,
                    "year": f_year,
                    "month": f_month,
                    "q": f_q,
                },
            ),
            "state_by_sede": state_by_sede,
            "selected_summary": selected_summary,
            "selected_record": selected_record,
            "history_rows": history_rows,
            "estado_options": [{"code": key, "label": value} for key, value in SST_DESINFECCION_STATE_LABELS.items()],
            "modalidad_options": [{"code": key, "label": value} for key, value in SST_DESINFECCION_MODALIDAD_LABELS.items()],
            "month_options": [{"value": number, "label": label} for number, label in SST_CALENDAR_MONTHS],
            "year_options": year_options,
            "f_sede": f_sede,
            "f_estado": f_estado,
            "f_modalidad": f_modalidad,
            "f_q": f_q,
            "f_year": f_year,
            "f_month": f_month,
            "show_form": show_form,
            "form_defaults": form_defaults,
            "kpi_sedes_con_registro": sum(1 for item in state_by_sede if int(item.get("record_count") or 0) > 0),
            "kpi_sedes_sin_registro": sum(1 for item in state_by_sede if int(item.get("record_count") or 0) == 0),
            "kpi_realizadas": sum(1 for item in state_by_sede if item.get("ultima_desinfeccion")),
            "kpi_programadas": sum(1 for item in state_by_sede if item.get("state_code") == "PROGRAMADA"),
            "kpi_pendientes": sum(1 for item in state_by_sede if item.get("state_code") in {"SIN_REGISTRO", "PENDIENTE_DE_PROGRAMACION", "OBSERVADA", "CANCELADA"}),
            "kpi_vencidas": sum(1 for item in state_by_sede if item.get("state_code") == "VENCIDA"),
            "fmt_fecha": _sst_fmt_fecha,
        }

    @app.route("/sst/desinfecciones", methods=["GET", "POST"], endpoint="sst_desinfecciones_home")
    def sst_desinfecciones_home():
        con = get_db()
        ensure_sst_general_table(con)
        ensure_sst_operativo_historial_tables(con)
        ensure_sst_desinfecciones_tables(con)
        if request.method == "POST":
            action = (request.form.get("action") or "save").strip().lower()
            user_name = _sst_current_user()
            if action == "save":
                edit_id = _sst_int_nonneg(request.form.get("edit_id"))
                sede_codigo = (_sst_clean_upper(request.form.get("sede_codigo")) or "").strip().upper()
                fecha_programada = (request.form.get("fecha_programada") or "").strip()
                fecha_realizada = (request.form.get("fecha_realizada") or "").strip()
                modalidad = _sst_desinf_normalize_modalidad(request.form.get("modalidad"), request.form.get("responsable"))
                responsable = (request.form.get("responsable") or "").strip()
                producto_detalle = (request.form.get("producto_detalle") or "").strip()
                observaciones = (request.form.get("observaciones") or "").strip()
                estado = _sst_desinf_normalize_state(request.form.get("estado"))
                if not sede_codigo:
                    flash("Selecciona una sede para guardar la desinfeccion.", "warning")
                elif not (fecha_programada or fecha_realizada):
                    flash("Carga una fecha programada o una fecha realizada.", "warning")
                else:
                    if not modalidad:
                        modalidad = _sst_desinf_normalize_modalidad("", responsable)
                    computed_state = estado or _sst_desinf_auto_state({
                        "fecha_programada": fecha_programada,
                        "fecha_realizada": fecha_realizada,
                    }, date.today())
                    previous_record = None
                    if edit_id:
                        previous_record = con.execute("""
                            SELECT fecha_programada, fecha_realizada, fecha, estado
                            FROM desinfecciones_sede
                            WHERE id = ?
                        """, (edit_id,)).fetchone()
                    alias_fecha = fecha_realizada or None
                    if edit_id:
                        con.execute("""
                            UPDATE desinfecciones_sede
                            SET cod_sede = ?,
                                fecha = ?,
                                fecha_programada = ?,
                                fecha_realizada = ?,
                                modalidad = ?,
                                responsable = ?,
                                empresa = ?,
                                producto_detalle = ?,
                                estado = ?,
                                observaciones = ?,
                                actualizado_por = ?,
                                fecha_actualizacion = ?
                            WHERE id = ?
                        """, (
                            sede_codigo,
                            alias_fecha,
                            fecha_programada or None,
                            fecha_realizada or None,
                            modalidad or None,
                            responsable or None,
                            responsable or None,
                            producto_detalle or None,
                            computed_state or None,
                            observaciones or None,
                            user_name,
                            _sst_now_ts(),
                            edit_id,
                        ))
                        record_id = edit_id
                        _sst_historial_log(con, "desinfecciones", "actualizacion", record_id, sede_codigo, "", "Actualizacion de desinfeccion por sede.")
                    else:
                        con.execute("""
                            INSERT INTO desinfecciones_sede(
                                cod_sede, fecha, fecha_programada, fecha_realizada,
                                modalidad, responsable, empresa, producto_detalle,
                                estado, observaciones, activo,
                                creado_por, actualizado_por, fecha_creacion, fecha_actualizacion
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                        """, (
                            sede_codigo,
                            alias_fecha,
                            fecha_programada or None,
                            fecha_realizada or None,
                            modalidad or None,
                            responsable or None,
                            responsable or None,
                            producto_detalle or None,
                            computed_state or None,
                            observaciones or None,
                            user_name,
                            user_name,
                            _sst_now_ts(),
                            _sst_now_ts(),
                        ))
                        record_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                        _sst_historial_log(con, "desinfecciones", "alta", record_id, sede_codigo, "", "Alta de desinfeccion por sede.")
                    previous_state = _sst_desinf_auto_state(dict(previous_record or {}), date.today()) if previous_record else ""
                    if previous_state != computed_state:
                        _sst_historial_log(
                            con,
                            "desinfecciones",
                            "cambio_estado",
                            record_id,
                            sede_codigo,
                            "",
                            f"{SST_DESINFECCION_STATE_LABELS.get(previous_state, 'Sin estado')} -> {SST_DESINFECCION_STATE_LABELS.get(computed_state, computed_state)}",
                        )
                    con.commit()
                    con.close()
                    flash("Registro de desinfeccion guardado.", "success")
                    return redirect(url_for("sst_desinfecciones_home", sede=sede_codigo, open_sede=sede_codigo, registro=record_id))
            elif action == "followup":
                record_id = _sst_int_nonneg(request.form.get("record_id"))
                record = next((item for item in _sst_desinf_fetch_records(con) if item.get("editable") and int(item.get("source_id") or 0) == record_id), None)
                summary = None
                if record:
                    summary = _sst_desinf_aggregate_by_sede([item for item in _sst_desinf_fetch_records(con) if item.get("sede_codigo") == record.get("sede_codigo")]).get(record.get("sede_codigo"))
                if not summary:
                    con.close()
                    flash("No se encontro la sede para crear seguimiento.", "warning")
                    return redirect(url_for("sst_desinfecciones_home"))
                if int(summary.get("seguimiento_id") or 0) > 0:
                    con.close()
                    flash("La sede ya tiene un seguimiento vinculado para desinfecciones.", "warning")
                    return redirect(url_for("sst_desinfecciones_home", sede=summary["sede_codigo"], open_sede=summary["sede_codigo"], registro=record_id))
                if summary.get("state_code") not in SST_DESINFECCION_PENDING_STATES:
                    con.close()
                    flash("La sede no tiene acciones pendientes para seguimiento.", "warning")
                    return redirect(url_for("sst_desinfecciones_home", sede=summary["sede_codigo"], open_sede=summary["sede_codigo"], registro=record_id))
                detalle = (
                    f"Estado: {summary['state_meta']['label']} | "
                    f"Ultima: {summary['ultima_desinfeccion'] or '-'} | "
                    f"Proxima: {summary['proxima_prevista'] or '-'} | "
                    f"Modalidad: {summary['modalidad_label']} | "
                    f"Accion: {summary['next_action']}"
                )
                if str(summary.get("observaciones") or "").strip():
                    detalle += f" | Observaciones: {summary['observaciones']}"
                con.execute("""
                    INSERT INTO sst_general(
                        fecha, sede_codigo, tipo, categoria, area, titulo, detalle,
                        estado, prioridad, responsable, accion_correctiva, fecha_objetivo,
                        origen_tipo, origen_id, origen_deposito_codigo
                    )
                    VALUES (?, ?, 'no_conformidad', 'Desinfecciones', 'SG-SST', ?, ?, 'ABIERTO', 'Media', ?, ?, ?, 'desinfecciones', ?, '')
                """, (
                    date.today().isoformat(),
                    summary["sede_codigo"],
                    f"Desinfecciones - {summary['sede_codigo']}",
                    detalle,
                    user_name,
                    summary["next_action"],
                    summary["proxima_prevista"] or None,
                    record_id,
                ))
                seguimiento_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                con.execute("""
                    UPDATE desinfecciones_sede
                    SET seguimiento_id = ?, actualizado_por = ?, fecha_actualizacion = ?
                    WHERE id = ?
                """, (seguimiento_id, user_name, _sst_now_ts(), record_id))
                _sst_historial_log(con, "desinfecciones", "seguimiento", record_id, summary["sede_codigo"], "", f"Seguimiento #{seguimiento_id} creado.")
                con.commit()
                con.close()
                flash("Seguimiento creado para desinfecciones.", "success")
                return redirect(url_for("sst_desinfecciones_home", sede=summary["sede_codigo"], open_sede=summary["sede_codigo"], registro=record_id))
        context = _sst_desinfecciones_context(con)
        con.close()
        return render_template("sst_desinfecciones.html", **context)

    @app.route("/sst/sedes/<codigo>", methods=["GET"], endpoint="sst_sede_ficha")
    def sst_sede_ficha(codigo):
        codigo = (codigo or "").strip().upper()
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)
        ensure_sst_control_tables(con)
        ensure_sst_carteleria_tables(con)
        ensure_sst_luces_tables(con)
        _seed_sst_control_objetivos(con)

        sede = con.execute("""
            SELECT codigo, nombre, fuero
            FROM sedes_mpd
            WHERE codigo = ?
        """, (codigo,)).fetchone()
        if not sede:
            con.close()
            flash("Sede no encontrada.", "warning")
            return redirect(url_for("sst_visitas"))

        visitas = con.execute("""
            SELECT id, fecha, tipo_visita, responsable, estado, observaciones
            FROM sst_visitas
            WHERE sede_codigo = ?
            ORDER BY fecha DESC, id DESC
        """, (codigo,)).fetchall()

        docs = con.execute("""
            SELECT id, tipo, fecha_documento, fecha_carga, archivo, drive_url, estado_revision, notas, visita_id
            FROM sst_documentos
            WHERE sede_codigo = ?
            ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
        """, (codigo,)).fetchall()

        pend = con.execute("""
            SELECT COUNT(*) AS cnt
            FROM sst_general
            WHERE tipo = 'no_conformidad'
              AND COALESCE(estado,'') <> 'CERRADO'
              AND sede_codigo = ?
        """, (codigo,)).fetchone()
        pend_hallazgos = int((pend["cnt"] if pend else 0) or 0)

        last_v = visitas[0] if visitas else None
        docs_map = {}
        for d in docs:
            tp = (d["tipo"] or "").strip().upper()
            if tp and tp not in docs_map:
                docs_map[tp] = d
        d351 = docs_map.get("DEC_351_79")
        drgrl = docs_map.get("RGRL")
        d351_ok = bool(d351 and (d351["drive_url"] or d351["archivo"]))
        drgrl_ok = bool(drgrl and (drgrl["drive_url"] or drgrl["archivo"]))
        docs_ok = d351_ok and drgrl_ok
        docs_pend = False
        if d351 and (str(d351["estado_revision"] or "").strip().upper() == "PENDIENTE"):
            docs_pend = True
        if drgrl and (str(drgrl["estado_revision"] or "").strip().upper() == "PENDIENTE"):
            docs_pend = True

        sem_cls, sem_label = _sst_calc_semaforo(bool(last_v), docs_ok, docs_pend, pend_hallazgos)
        fuero_class, fuero_color = _sst_fuero_style((sede["fuero"] if sede else None) or "")

        matafuegos = con.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN fecha_vencimiento IS NOT NULL
                                  AND date(fecha_vencimiento) <= date('now', '+45 day')
                            THEN 1 ELSE 0 END) AS proximos
            FROM matafuegos
            WHERE UPPER(COALESCE(sede, '')) = ?
              AND COALESCE(activo, 1) = 1
        """, (codigo,)).fetchone()
        mata_total = int((matafuegos["total"] if matafuegos else 0) or 0)
        mata_proximos = int((matafuegos["proximos"] if matafuegos else 0) or 0)
        carteleria_records = [item for item in _sst_fetch_carteleria_records(con) if item["sede_codigo"] == codigo]
        luces_records = [item for item in _sst_fetch_luces_records(con) if item["sede_codigo"] == codigo]
        luces_summary = _sst_luces_aggregate_by_sede(luces_records).get(codigo)

        controles = {}
        for control in con.execute("""
            SELECT LOWER(o.nombre) AS nombre, r.ok
            FROM sst_control_objetivos o
            LEFT JOIN sst_control_relevamientos r
              ON r.objetivo_id = o.id AND UPPER(r.sede_codigo) = ?
        """, (codigo,)).fetchall():
            controles[str(control["nombre"] or "")] = control["ok"]

        def _control_estado(fragmentos):
            valor = None
            for nombre, ok in controles.items():
                if any(fragmento in nombre for fragmento in fragmentos):
                    valor = ok
                    break
            if valor is None:
                return ("Sin relevamiento", "sin-dato")
            if int(valor or 0) == 1:
                return ("Correcto", "correcto")
            return ("Requiere atención", "atencion")

        if carteleria_records:
            cart_summary = _sst_carteleria_aggregate_by_sede(carteleria_records).get(sede_codigo)
            if cart_summary:
                cart_requeridos = int(cart_summary.get("cantidad_requerida") or 0)
                cart_instalados = int(cart_summary.get("cantidad_instalada") or 0)
                cart_faltantes = int(cart_summary.get("cantidad_faltante") or 0)
                cart_estado = cart_summary["state_meta"]["label"]
                cart_clase = cart_summary["state_meta"]["class"]
                cart_detail = f"{cart_requeridos} requeridos · {cart_instalados} instalados"
                if cart_faltantes:
                    cart_detail += f" · {cart_faltantes} faltantes"
            else:
                cart_estado, cart_clase = _control_estado(("cartel", "señal", "senal"))
                cart_detail = cart_estado
        else:
            cart_estado, cart_clase = _control_estado(("cartel", "señal", "senal"))
            cart_detail = cart_estado

        if luces_summary:
            luces_estado = luces_summary["state_meta"]["label"]
            luces_clase = luces_summary["state_meta"]["class"]
            if not _sst_bool_flag(luces_summary.get("aplica", 1)):
                luces_detail = luces_summary.get("motivo_no_aplica") or "No aplica"
            else:
                luces_detail = (
                    f"{int(luces_summary.get('cantidad_requerida') or 0)} requeridas · "
                    f"{int(luces_summary.get('cantidad_instalada') or 0)} instaladas · "
                    f"{int(luces_summary.get('cantidad_faltante') or 0)} faltantes"
                )
                if str(luces_summary.get("action_label") or "").strip():
                    luces_detail += f" · {luces_summary['action_label']}"
        else:
            luces_estado, luces_clase = _control_estado(("luz", "luces", "emergencia"))
            luces_detail = luces_estado

        plano_estado, plano_clase = _control_estado(("plano", "evacu"))
        estado_sede = [
            {
                "label": "Matafuegos",
                "detail": (f"{mata_total} activos · {mata_proximos} próximos a vencer" if mata_total else "Sin inventario cargado"),
                "state": ("Sin relevamiento" if not mata_total else ("Requiere atención" if mata_proximos else "Correcto")),
                "class": ("sin-dato" if not mata_total else ("atencion" if mata_proximos else "correcto")),
            },
            {"label": "Cartelería", "detail": cart_detail, "state": cart_estado, "class": cart_clase},
            {"label": "Luces de emergencia", "detail": luces_detail, "state": luces_estado, "class": luces_clase},
            {"label": "Planos de evacuación", "detail": plano_estado, "state": plano_estado, "class": plano_clase},
            {
                "label": "Hallazgos",
                "detail": (f"{pend_hallazgos} pendiente(s)" if pend_hallazgos else ("Sin hallazgos abiertos" if last_v else "Sin relevamiento")),
                "state": ("Requiere atención" if pend_hallazgos else ("Correcto" if last_v else "Sin relevamiento")),
                "class": ("atencion" if pend_hallazgos else ("correcto" if last_v else "sin-dato")),
            },
            {
                "label": "Última visita",
                "detail": (_sst_fmt_fecha(last_v["fecha"]) if last_v else "Sin relevamiento"),
                "state": ("Correcto" if last_v else "Sin relevamiento"),
                "class": ("correcto" if last_v else "sin-dato"),
            },
        ]
        con.close()

        return render_template(
            "sst_sede_ficha.html",
            sede=sede,
            fuero_class=fuero_class,
            fuero_color=fuero_color,
            visitas=visitas,
            docs=docs,
            pend_hallazgos=pend_hallazgos,
            d351=d351,
            drgrl=drgrl,
            docs_ok=docs_ok,
            docs_pend=docs_pend,
            semaforo_cls=sem_cls,
            semaforo_label=sem_label,
            estado_sede=estado_sede,
            fmt_fecha=_sst_fmt_fecha,
            fmt_estado_visita=_sst_sede_estado_label,
        )

    @app.route("/sst/ergonomia", methods=["GET"], endpoint="sst_ergonomia_panel")
    def sst_ergonomia_panel():
        context = build_sst_plan_context(show_carga=False, sst_view="ergonomia")
        return render_template("sst_plan.html", **context)

    @app.route("/sst/plan-gantt", methods=["GET"], endpoint="sst_plan_gantt")
    def sst_plan_gantt():
        context = build_sst_plan_context(show_carga=False, sst_view="gantt")
        return render_template("sst_plan.html", **context)

    @app.route("/sst/plan/accion/<int:aid>/eliminar", methods=["POST"], endpoint="sst_plan_accion_eliminar")
    def sst_plan_accion_eliminar(aid):
        con = get_db()
        con.execute("DELETE FROM sst_objetivo_acciones WHERE id = ?", (aid,))
        con.commit()
        con.close()
        flash("Accion eliminada.", "success")
        return _sst_plan_redirect_next()

    @app.route("/sst/control/estado/<int:oid>", methods=["POST"])
    def sst_control_estado(oid):
        consolidado_ok = 1 if request.form.get("consolidado_ok") else 0
        decision_ok = 1 if request.form.get("decision_ok") else 0
        impl_compra_necesaria = (request.form.get("impl_compra_necesaria") or "").strip()
        impl_pedido = (request.form.get("impl_pedido") or "").strip()
        impl_recibido = (request.form.get("impl_recibido") or "").strip()
        impl_ejecucion = (request.form.get("impl_ejecucion") or "").strip()
        impl_colocacion = (request.form.get("impl_colocacion") or "").strip()
        impl_pedido_fecha = (request.form.get("impl_pedido_fecha") or "").strip()
        impl_recibido_fecha = (request.form.get("impl_recibido_fecha") or "").strip()
        impl_ejecucion_fecha = (request.form.get("impl_ejecucion_fecha") or "").strip()
        impl_colocacion_fecha = (request.form.get("impl_colocacion_fecha") or "").strip()
        eval_verificado = (request.form.get("eval_verificado") or "").strip()
        eval_observaciones = (request.form.get("eval_observaciones") or "").strip()
        eval_cerrado = (request.form.get("eval_cerrado") or "").strip()

        con = get_db()
        con.execute("""
            UPDATE sst_control_objetivos
            SET consolidado_ok = ?,
                decision_ok = ?,
                impl_compra_necesaria = ?,
                impl_pedido = ?,
                impl_recibido = ?,
                impl_ejecucion = ?,
                impl_colocacion = ?,
                impl_pedido_fecha = ?,
                impl_recibido_fecha = ?,
                impl_ejecucion_fecha = ?,
                impl_colocacion_fecha = ?,
                eval_verificado = ?,
                eval_observaciones = ?,
                eval_cerrado = ?
            WHERE id = ?
        """, (
            consolidado_ok,
            decision_ok,
            impl_compra_necesaria or None,
            impl_pedido or None,
            impl_recibido or None,
            impl_ejecucion or None,
            impl_colocacion or None,
            impl_pedido_fecha or None,
            impl_recibido_fecha or None,
            impl_ejecucion_fecha or None,
            impl_colocacion_fecha or None,
            eval_verificado or None,
            eval_observaciones or None,
            eval_cerrado or None,
            oid,
        ))
        con.commit()
        con.close()
        flash("Estado actualizado.", "success")
        return _sst_plan_redirect_next()

    @app.route("/sst/control/relevamientos/<int:oid>", methods=["POST"])
    def sst_control_relevamientos(oid):
        con = get_db()
        sedes = con.execute("SELECT codigo FROM sedes_mpd ORDER BY codigo").fetchall()
        con.execute("DELETE FROM sst_control_relevamientos WHERE objetivo_id = ?", (oid,))
        for s in sedes:
            key = f"sede_{s['codigo']}"
            ok = 1 if request.form.get(key) else 0
            con.execute("""
                INSERT INTO sst_control_relevamientos (objetivo_id, sede_codigo, ok)
                VALUES (?, ?, ?)
            """, (oid, s["codigo"], ok))
        con.commit()
        con.close()
        flash("Relevamientos actualizados.", "success")
        return _sst_plan_redirect_next()

    @app.route("/sst/ergonomia/guardar", methods=["POST"], endpoint="sst_ergonomia_guardar")
    def sst_ergonomia_guardar():
        personal_id = _safe_int(request.form.get("personal_id"), 0)
        ergo_sede = (request.form.get("ergo_sede") or "").strip().upper()
        next_view = (request.form.get("next") or "plan").strip().lower()
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not personal_id:
            msg = "Selecciona una persona para guardar el relevamiento."
            if is_ajax:
                return jsonify({"ok": False, "message": msg}), 400
            flash(msg, "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))

        descripcion_puesto = (request.form.get("descripcion_puesto") or "").strip()
        tipo_silla = (request.form.get("tipo_silla") or "").strip()
        tipo_escritorio = (request.form.get("tipo_escritorio") or "").strip()
        soporte_monitor = (request.form.get("soporte_monitor") or "").strip()
        altura_monitor = (request.form.get("altura_monitor") or "").strip()
        espacio_piernas = (request.form.get("espacio_piernas") or "").strip()
        ajuste_altura = (request.form.get("ajuste_altura") or "").strip()
        horas_pc = _safe_int(request.form.get("horas_pc"), 0)
        uso_notebook = (request.form.get("uso_notebook") or "").strip()
        fecha_relevamiento = (request.form.get("fecha_relevamiento") or "").strip()
        evaluador = (request.form.get("evaluador") or "").strip()
        fecha_nacimiento = (request.form.get("fecha_nacimiento") or "").strip()
        fecha_implementacion = (request.form.get("fecha_implementacion") or "").strip()
        responsable = (request.form.get("responsable") or "").strip()
        evidencia_url = (request.form.get("evidencia_url") or "").strip()
        fecha_verificacion = (request.form.get("fecha_verificacion") or "").strip()
        verificado = 1 if request.form.get("verificado") in ("1", "on", "true", "True") else 0
        intervencion_realizada = (request.form.get("intervencion_realizada") or "").strip()
        descripcion_salud = (request.form.get("descripcion_salud") or "").strip()
        accion_tomar_input = (request.form.get("accion_tomar") or "").strip()
        observaciones = (request.form.get("observaciones") or "").strip()

        if descripcion_puesto not in ERGO_DESC_OPTIONS:
            descripcion_puesto = ERGO_DESC_OPTIONS[0]
        if tipo_silla not in ERGO_SILLA_OPTIONS:
            tipo_silla = ERGO_SILLA_OPTIONS[0]
        if tipo_escritorio not in ERGO_ESCRITORIO_OPTIONS:
            tipo_escritorio = ERGO_ESCRITORIO_OPTIONS[0]
        if soporte_monitor not in ERGO_SOPORTE_OPTIONS:
            soporte_monitor = ERGO_SOPORTE_OPTIONS[-1]
        if altura_monitor not in ERGO_ALTURA_MONITOR_OPTIONS:
            altura_monitor = ERGO_ALTURA_MONITOR_OPTIONS[0]
        if espacio_piernas not in ERGO_ESPACIO_PIERNAS_OPTIONS:
            espacio_piernas = ERGO_ESPACIO_PIERNAS_OPTIONS[0]
        if ajuste_altura not in ERGO_AJUSTE_ALTURA_OPTIONS:
            ajuste_altura = ERGO_AJUSTE_ALTURA_OPTIONS[0]
        if uso_notebook not in ERGO_NOTEBOOK_OPTIONS:
            uso_notebook = ERGO_NOTEBOOK_OPTIONS[0]
        if intervencion_realizada not in ERGO_INTERVENCION_OPTIONS:
            intervencion_realizada = ERGO_INTERVENCION_OPTIONS[0]
        if accion_tomar_input not in ERGO_ACCION_OPTIONS:
            accion_tomar_input = "Programado"

        score_puesto = 0
        if tipo_silla == "Silla fija":
            score_puesto += 2
        elif tipo_silla == "Silla giratoria":
            score_puesto += 1
        if soporte_monitor == "Sin soporte de monitor":
            score_puesto += 1
        if altura_monitor in ("Monitor bajo", "Monitor alto"):
            score_puesto += 1
        if espacio_piernas == "Espacio reducido":
            score_puesto += 1
        elif espacio_piernas == "Espacio insuficiente":
            score_puesto += 2
        if uso_notebook == "Si, sin base o soporte":
            score_puesto += 2
        if horas_pc >= 6:
            score_puesto += 1

        # Derivaciones paralelas para modelo PRO (etapa 1, sin impacto visual)
        puntaje_sistema = 0
        if soporte_monitor == "Sin soporte de monitor":
            puntaje_sistema += 1
        if altura_monitor in ("Monitor bajo", "Monitor alto"):
            puntaje_sistema += 1
        if uso_notebook == "Si, sin base o soporte":
            puntaje_sistema += 1

        puntaje_mobiliario = 0
        if tipo_silla == "Silla fija":
            puntaje_mobiliario += 1
        if tipo_escritorio in ("Mesa de PC", "Escritorio de PC solo"):
            puntaje_mobiliario += 1

        con = get_db()
        ensure_sst_ergonomia_table(con)
        ensure_sst_ergonomia_historial_table(con)
        before_row = con.execute("""
            SELECT *
            FROM sst_ergonomia
            WHERE personal_id = ?
        """, (personal_id,)).fetchone()
        current = con.execute("""
            SELECT edad, puntuacion_salud, accion_tomar
            FROM sst_ergonomia
            WHERE personal_id = ?
        """, (personal_id,)).fetchone()
        if not current:
            con.close()
            msg = "No se encontro el registro de la persona seleccionada."
            if is_ajax:
                return jsonify({"ok": False, "message": msg}), 404
            flash(msg, "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))

        edad_calc = _calc_age_from_birthdate(fecha_nacimiento)
        edad_final = edad_calc if edad_calc is not None else _safe_int(current["edad"], 0)
        punt_edad = _ergo_age_score(edad_final)
        punt_salud = _safe_int(current["puntuacion_salud"], 0)
        salud_completa = punt_salud > 0 or bool(descripcion_salud.strip())
        promedio = round((punt_edad + score_puesto + punt_salud) / 3, 2) if (edad_final > 0 and salud_completa) else None
        audit_payload = {
            "fecha_relevamiento": fecha_relevamiento,
            "evaluador": evaluador,
            "horas_pc": horas_pc,
            "uso_notebook": uso_notebook,
            "accion_tomar": accion_tomar_input,
            "responsable": responsable,
            "fecha_implementacion": fecha_implementacion,
            "fecha_verificacion": fecha_verificacion,
            "verificado": verificado,
            "observaciones": observaciones,
            "intervencion_realizada": intervencion_realizada,
            "edad": edad_final,
            "puntuacion_puesto": score_puesto,
            "altura_monitor": altura_monitor,
            "ajuste_altura": ajuste_altura,
        }
        audit_alertas = _ergo_build_audit_alerts(audit_payload)
        estado_flujo = _ergo_next_flow_state(audit_payload)
        pro = _pro_score_parallel({
            "puntaje_puesto": score_puesto,
            "puntaje_sistema": puntaje_sistema,
            "puntaje_mobiliario": puntaje_mobiliario,
            "puntaje_salud": punt_salud,
            "horas_pc": horas_pc,
            "edad": edad_final,
            "usa_notebook": uso_notebook,
            "dolor_reportado": 0,
            "restriccion_medica": 0,
            "altura_monitor": altura_monitor,
            "espacio_piernas": espacio_piernas,
            "tipo_silla": tipo_silla,
        })
        accion_tomar_auto = _accion_from_pro_bucket(pro.get("condicion_riesgo"))
        if (current["accion_tomar"] or "").strip() == "Cerrado":
            accion_tomar_auto = "Cerrado"
        audit_payload["accion_tomar"] = accion_tomar_auto
        fecha_recordatorio = None
        if accion_tomar_auto == "Programado" and fecha_relevamiento:
            try:
                base_d = datetime.strptime(fecha_relevamiento, "%Y-%m-%d").date()
                fecha_recordatorio = (base_d + timedelta(days=30)).strftime("%Y-%m-%d")
            except Exception:
                fecha_recordatorio = None
        fecha_cierre = date.today().strftime("%Y-%m-%d") if accion_tomar_auto == "Cerrado" else None
        usuario_cambio = (
            (request.headers.get("X-User") or "").strip()
            or evaluador
            or "sistema"
        )

        con.execute("""
            UPDATE sst_ergonomia
            SET descripcion_puesto = ?,
                tipo_silla = ?,
                tipo_escritorio = ?,
                soporte_monitor = ?,
                altura_monitor = ?,
                espacio_piernas = ?,
                ajuste_altura = ?,
                horas_pc = ?,
                uso_notebook = ?,
                fecha_relevamiento = ?,
                evaluador = ?,
                fecha_nacimiento = ?,
                puntuacion_edad = ?,
                edad = ?,
                fecha_implementacion = COALESCE(NULLIF(?, ''), fecha_implementacion),
                responsable = COALESCE(NULLIF(?, ''), responsable),
                evidencia_url = COALESCE(NULLIF(?, ''), evidencia_url),
                fecha_verificacion = COALESCE(NULLIF(?, ''), fecha_verificacion),
                verificado = CASE WHEN ? IN (0,1) THEN ? ELSE COALESCE(verificado,0) END,
                intervencion_realizada = ?,
                fecha_cierre = CASE
                    WHEN ? IS NOT NULL AND ? != '' THEN ?
                    ELSE fecha_cierre
                END,
                fecha_recordatorio = COALESCE(NULLIF(?, ''), fecha_recordatorio),
                pro_condicion_0_100 = ?,
                pro_expo_0_100 = ?,
                pro_vulner_0_100 = ?,
                pro_score_final = ?,
                pro_condicion_riesgo = ?,
                pro_motivos = ?,
                estado_flujo = ?,
                audit_alertas = ?,
                descripcion_salud = CASE
                    WHEN ? = '' THEN descripcion_salud
                    ELSE ?
                END,
                puntuacion_puesto = ?,
                promedio = ?,
                accion_tomar = ?,
                observaciones = ?,
                actualizado_en = datetime('now')
            WHERE personal_id = ?
        """, (
            descripcion_puesto,
            tipo_silla,
            tipo_escritorio,
            soporte_monitor,
            altura_monitor,
            espacio_piernas,
            ajuste_altura,
            horas_pc,
            uso_notebook,
            fecha_relevamiento or None,
            evaluador or None,
            fecha_nacimiento or None,
            punt_edad,
            edad_final,
            fecha_implementacion,
            responsable,
            evidencia_url,
            fecha_verificacion,
            verificado,
            verificado,
            intervencion_realizada,
            fecha_cierre,
            fecha_cierre,
            fecha_cierre,
            fecha_recordatorio,
            pro.get("condicion_0_100"),
            pro.get("expo_0_100"),
            pro.get("vulner_0_100"),
            pro.get("score_final"),
            pro.get("condicion_riesgo"),
            json.dumps(pro.get("motivos", []), ensure_ascii=False),
            estado_flujo,
            json.dumps(audit_alertas, ensure_ascii=False),
            descripcion_salud,
            descripcion_salud,
                score_puesto,
                promedio,
                accion_tomar_auto,
                observaciones or None,
                personal_id,
        ))

        updated_row = con.execute("""
            SELECT *
            FROM sst_ergonomia
            WHERE personal_id = ?
        """, (personal_id,)).fetchone()
        if updated_row:
            snapshot = dict(updated_row)
            before = dict(before_row) if before_row else {}
            changed = {}
            for key, new_val in snapshot.items():
                old_val = before.get(key)
                if str(old_val) != str(new_val):
                    changed[key] = {"old": old_val, "new": new_val}
            con.execute("""
                INSERT INTO sst_ergonomia_historial (
                    personal_id,
                    usuario_cambio,
                    accion_tomar,
                    puntuacion_puesto,
                    promedio,
                    evaluador,
                    fecha_relevamiento,
                    observaciones,
                    cambios_json,
                    snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                personal_id,
                usuario_cambio,
                snapshot.get("accion_tomar"),
                snapshot.get("puntuacion_puesto"),
                snapshot.get("promedio"),
                snapshot.get("evaluador"),
                snapshot.get("fecha_relevamiento"),
                snapshot.get("observaciones"),
                json.dumps(changed, ensure_ascii=False),
                json.dumps(snapshot, ensure_ascii=False),
            ))
        con.commit()
        con.close()

        if is_ajax:
            return jsonify({
                "ok": True,
                "personal_id": personal_id,
                "edad": edad_final,
                "punt_edad": punt_edad,
                "puntuacion_puesto": score_puesto,
                "promedio": promedio,
                "estado_flujo": estado_flujo,
                "audit_alertas": audit_alertas,
                "accion_raw": accion_tomar_auto,
                "accion_label": _ergo_action_label(accion_tomar_auto),
                "risk_flags": _ergo_risk_flags(audit_payload),
                "semaforo": _ergo_semaforo(_ergo_total_score(punt_edad, score_puesto, punt_salud)),
                "motivos_riesgo": _ergo_motivos_riesgo({
                    "altura_monitor": altura_monitor,
                    "espacio_piernas": espacio_piernas,
                    "tipo_silla": tipo_silla,
                    "edad": edad_final,
                    "uso_notebook": uso_notebook,
                }),
                "dias_desde_eval": _ergo_days_since(fecha_relevamiento),
                "pro": pro,
                "message": "Relevamiento ergonomico actualizado.",
            })

        flash("Relevamiento ergonomico actualizado.", "success")
        endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
        return redirect(url_for(endpoint, ergo_sede=ergo_sede or None, ergo_personal_id=personal_id))

    @app.route("/sst/ergonomia/manual", methods=["GET"], endpoint="sst_ergonomia_manual")
    def sst_ergonomia_manual():
        return render_template("sst_ergonomia_manual.html")

    @app.route("/sst/ergonomia/gestion-riesgo", methods=["GET"], endpoint="sst_ergonomia_gestion_riesgo")
    def sst_ergonomia_gestion_riesgo():
        personal_id = _safe_int(request.args.get("personal_id"), 0)
        persona = (request.args.get("persona") or "").strip()
        sede = (request.args.get("sede") or "").strip().upper()
        estado_flujo = (request.args.get("estado_flujo") or "").strip() or "Programado"
        accion = (request.args.get("accion") or "").strip()
        intervencion = (request.args.get("intervencion") or "").strip()
        motivos = (request.args.get("motivos") or "").strip()

        estado_ui, paso_actual = _ergo_ui_state_and_step(estado_flujo)
        pyramid_level = _ergo_recommended_pyramid_level({
            "intervencion_realizada": intervencion,
        })
        if not accion:
            accion = "Pendiente"

        volver_url = url_for(
            "sst_plan",
            ergo_sede=sede or None,
            ergo_personal_id=personal_id or None,
        )
        if personal_id:
            volver_url = f"{volver_url}#ergo-carga-box"

        return render_template(
            "sst_ergonomia_gestion_riesgo.html",
            persona=persona,
            sede=sede,
            estado_flujo=estado_flujo,
            estado_ui=estado_ui,
            paso_actual=paso_actual,
            accion=accion,
            intervencion=intervencion,
            motivos=motivos,
            pyramid_level=pyramid_level,
            volver_url=volver_url,
        )

    @app.route("/sst/ergonomia/salud/guardar", methods=["POST"], endpoint="sst_ergonomia_salud_guardar")
    def sst_ergonomia_salud_guardar():
        personal_id = _safe_int(request.form.get("personal_id"), 0)
        ergo_sede = (request.form.get("ergo_sede") or "").strip().upper()
        next_view = (request.form.get("next") or "plan").strip().lower()
        salud_desc = (request.form.get("descripcion_salud_med") or "").strip()
        salud_eval = (request.form.get("salud_evaluador") or "").strip()
        salud_fecha = (request.form.get("salud_fecha") or "").strip() or date.today().strftime("%Y-%m-%d")

        if not personal_id:
            flash("Selecciona una persona para cargar salud.", "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))

        punt_salud = _salud_score_from_desc(salud_desc)

        con = get_db()
        ensure_sst_ergonomia_table(con)
        ensure_sst_ergonomia_historial_table(con)
        row = con.execute("""
            SELECT *
            FROM sst_ergonomia
            WHERE personal_id = ?
        """, (personal_id,)).fetchone()
        if not row:
            con.close()
            flash("No se encontro la persona para carga medica.", "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))

        d = dict(row)
        punt_edad = _safe_int(d.get("puntuacion_edad"), _ergo_age_score(d.get("edad")))
        punt_puesto = _safe_int(d.get("puntuacion_puesto"), 0)
        promedio = round((punt_edad + punt_puesto + punt_salud) / 3, 2) if _safe_int(d.get("edad"), 0) > 0 else None

        puntaje_sistema = 0
        if (d.get("soporte_monitor") or "") == "Sin soporte de monitor":
            puntaje_sistema += 1
        if (d.get("altura_monitor") or "") in ("Monitor bajo", "Monitor alto"):
            puntaje_sistema += 1
        if (d.get("uso_notebook") or "") == "Si, sin base o soporte":
            puntaje_sistema += 1
        puntaje_mobiliario = 0
        if (d.get("tipo_silla") or "") == "Silla fija":
            puntaje_mobiliario += 1
        if (d.get("tipo_escritorio") or "") in ("Mesa de PC", "Escritorio de PC solo"):
            puntaje_mobiliario += 1

        pro = _pro_score_parallel({
            "puntaje_puesto": punt_puesto,
            "puntaje_sistema": puntaje_sistema,
            "puntaje_mobiliario": puntaje_mobiliario,
            "puntaje_salud": punt_salud,
            "horas_pc": _safe_int(d.get("horas_pc"), 0),
            "edad": _safe_int(d.get("edad"), 0),
            "usa_notebook": d.get("uso_notebook"),
            "dolor_reportado": 1 if salud_desc.strip().lower() in ("molestias frecuentes", "restriccion medica") else 0,
            "restriccion_medica": 1 if salud_desc.strip().lower() == "restriccion medica" else 0,
            "altura_monitor": d.get("altura_monitor"),
            "espacio_piernas": d.get("espacio_piernas"),
            "tipo_silla": d.get("tipo_silla"),
        })
        accion_auto = _accion_from_pro_bucket(pro.get("condicion_riesgo"))
        if (d.get("accion_tomar") or "").strip() == "Cerrado":
            accion_auto = "Cerrado"

        payload = {
            "fecha_relevamiento": d.get("fecha_relevamiento") or "",
            "evaluador": d.get("evaluador") or "",
            "horas_pc": d.get("horas_pc") or 0,
            "uso_notebook": d.get("uso_notebook") or "",
            "accion_tomar": accion_auto,
            "responsable": d.get("responsable") or "",
            "fecha_implementacion": d.get("fecha_implementacion") or "",
            "fecha_verificacion": d.get("fecha_verificacion") or "",
            "verificado": _safe_int(d.get("verificado"), 0),
            "observaciones": d.get("observaciones") or "",
            "edad": _safe_int(d.get("edad"), 0),
            "puntuacion_puesto": punt_puesto,
            "altura_monitor": d.get("altura_monitor") or "",
            "ajuste_altura": d.get("ajuste_altura") or "",
        }
        estado_flujo = _ergo_next_flow_state(payload)
        alertas = _ergo_build_audit_alerts(payload)

        con.execute("""
            UPDATE sst_ergonomia
            SET descripcion_salud = ?,
                puntuacion_salud = ?,
                salud_evaluador = ?,
                salud_fecha = ?,
                promedio = ?,
                accion_tomar = ?,
                estado_flujo = ?,
                pro_condicion_0_100 = ?,
                pro_expo_0_100 = ?,
                pro_vulner_0_100 = ?,
                pro_score_final = ?,
                pro_condicion_riesgo = ?,
                pro_motivos = ?,
                audit_alertas = ?,
                actualizado_en = datetime('now')
            WHERE personal_id = ?
        """, (
            salud_desc or None,
            punt_salud,
            salud_eval or None,
            salud_fecha,
            promedio,
            accion_auto,
            estado_flujo,
            pro.get("condicion_0_100"),
            pro.get("expo_0_100"),
            pro.get("vulner_0_100"),
            pro.get("score_final"),
            pro.get("condicion_riesgo"),
            json.dumps(pro.get("motivos", []), ensure_ascii=False),
            json.dumps(alertas, ensure_ascii=False),
            personal_id,
        ))

        snap = con.execute("SELECT * FROM sst_ergonomia WHERE personal_id = ?", (personal_id,)).fetchone()
        if snap:
            s = dict(snap)
            con.execute("""
                INSERT INTO sst_ergonomia_historial (
                    personal_id,
                    usuario_cambio,
                    accion_tomar,
                    puntuacion_puesto,
                    promedio,
                    evaluador,
                    fecha_relevamiento,
                    observaciones,
                    cambios_json,
                    snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                personal_id,
                salud_eval or "dpto_medico",
                s.get("accion_tomar"),
                s.get("puntuacion_puesto"),
                s.get("promedio"),
                s.get("evaluador"),
                s.get("fecha_relevamiento"),
                s.get("observaciones"),
                json.dumps({"evento": "Carga salud separada"}, ensure_ascii=False),
                json.dumps(s, ensure_ascii=False),
            ))
        con.commit()
        con.close()
        flash("Carga de salud guardada por separado.", "success")
        endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
        return redirect(url_for(endpoint, ergo_sede=ergo_sede or None, ergo_personal_id=personal_id))

    @app.route("/sst/ergonomia/reevaluar", methods=["POST"], endpoint="sst_ergonomia_reevaluar")
    def sst_ergonomia_reevaluar():
        personal_id = _safe_int(request.form.get("personal_id"), 0)
        ergo_sede = (request.form.get("ergo_sede") or "").strip().upper()
        next_view = (request.form.get("next") or "plan").strip().lower()
        if not personal_id:
            flash("No se pudo iniciar la reevaluacion.", "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))

        con = get_db()
        ensure_sst_ergonomia_table(con)
        ensure_sst_ergonomia_historial_table(con)
        current = con.execute("""
            SELECT *
            FROM sst_ergonomia
            WHERE personal_id = ?
        """, (personal_id,)).fetchone()
        if current:
            snap = dict(current)
            con.execute("""
                INSERT INTO sst_ergonomia_historial (
                    personal_id,
                    usuario_cambio,
                    accion_tomar,
                    puntuacion_puesto,
                    promedio,
                    evaluador,
                    fecha_relevamiento,
                    observaciones,
                    cambios_json,
                    snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                personal_id,
                "sistema",
                snap.get("accion_tomar"),
                snap.get("puntuacion_puesto"),
                snap.get("promedio"),
                snap.get("evaluador"),
                snap.get("fecha_relevamiento"),
                snap.get("observaciones"),
                json.dumps({"evento": "Reevaluacion iniciada"}, ensure_ascii=False),
                json.dumps(snap, ensure_ascii=False),
            ))
            con.execute("""
                UPDATE sst_ergonomia
                SET descripcion_salud = NULL,
                    puntuacion_salud = 0,
                    puntuacion_puesto = 0,
                    promedio = NULL,
                    accion_tomar = 'Programado',
                    estado_flujo = 'Programado',
                    fecha_implementacion = NULL,
                    fecha_verificacion = NULL,
                    verificado = 0,
                    evidencia_url = NULL,
                    audit_alertas = ?,
                    actualizado_en = datetime('now')
                WHERE personal_id = ?
            """, (json.dumps(["Reevaluacion iniciada"], ensure_ascii=False), personal_id))
            con.commit()
            flash("Reevaluacion iniciada.", "success")
        else:
            flash("No se encontro el registro para reevaluar.", "warning")
        con.close()
        endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
        return redirect(url_for(endpoint, ergo_sede=ergo_sede or None, ergo_personal_id=personal_id))

    @app.route("/sst/ergonomia/cerrar", methods=["POST"], endpoint="sst_ergonomia_cerrar")
    def sst_ergonomia_cerrar():
        personal_id = _safe_int(request.form.get("personal_id"), 0)
        ergo_sede = (request.form.get("ergo_sede") or "").strip().upper()
        next_view = (request.form.get("next") or "plan").strip().lower()
        if not personal_id:
            flash("No se pudo cerrar el caso.", "warning")
            endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
            return redirect(url_for(endpoint, ergo_sede=ergo_sede or None))
        con = get_db()
        ensure_sst_ergonomia_table(con)
        con.execute("""
            UPDATE sst_ergonomia
            SET accion_tomar = 'Cerrado',
                estado_flujo = 'Cerrado',
                verificado = 1,
                fecha_cierre = ?,
                fecha_verificacion = COALESCE(fecha_verificacion, ?),
                actualizado_en = datetime('now')
            WHERE personal_id = ?
        """, (date.today().strftime("%Y-%m-%d"), date.today().strftime("%Y-%m-%d"), personal_id))
        con.commit()
        con.close()
        flash("Caso cerrado.", "success")
        endpoint = "sst_plan_cargar" if next_view == "cargar" else "sst_plan"
        return redirect(url_for(endpoint, ergo_sede=ergo_sede or None, ergo_personal_id=personal_id))

    @app.route("/sst/ergonomia/reporte", methods=["GET"], endpoint="sst_ergonomia_reporte")
    def sst_ergonomia_reporte():
        con = get_db()
        ensure_sst_ergonomia_table(con)
        rows = con.execute("""
            SELECT
                codigo_sede,
                accion_tomar,
                estado_flujo,
                puntuacion_puesto,
                puntuacion_edad,
                puntuacion_salud,
                promedio,
                fecha_relevamiento,
                fecha_implementacion,
                fecha_verificacion,
                verificado,
                audit_alertas
            FROM sst_ergonomia
            ORDER BY codigo_sede, nombre_apellido
        """).fetchall()
        con.close()

        total = len(rows)
        urgentes = 0
        programados = 0
        sin_accion = 0
        verificados = 0
        pendientes_verificacion = 0
        pendientes_relevamiento = 0
        with_alerts = 0
        casos_60 = 0
        casos_70 = 0
        casos_notebook = 0
        flow_counts = {k: 0 for k in ERGO_SGI_FLOW_STATES}
        sedes = {}
        promedio_vals = []
        horas_vals = []
        edad_vals = []

        for r in rows:
            d = dict(r)
            accion = (d.get("accion_tomar") or "").strip().lower()
            if accion == "urgente":
                urgentes += 1
            elif accion == "programado":
                programados += 1
            else:
                sin_accion += 1

            estado = (d.get("estado_flujo") or "").strip() or _ergo_next_flow_state(d)
            if estado not in flow_counts:
                flow_counts[estado] = 0
            flow_counts[estado] += 1

            if _safe_int(d.get("verificado"), 0) == 1:
                verificados += 1
            elif (d.get("fecha_implementacion") or "").strip():
                pendientes_verificacion += 1
            if not (d.get("fecha_relevamiento") or "").strip():
                pendientes_relevamiento += 1

            alerts_raw = d.get("audit_alertas")
            try:
                alerts = json.loads(alerts_raw) if alerts_raw else []
            except Exception:
                alerts = []
            if alerts:
                with_alerts += 1

            edad = _safe_int(d.get("edad"), 0)
            if edad >= 60:
                casos_60 += 1
            if edad >= 70:
                casos_70 += 1
            if (d.get("uso_notebook") or "").strip().lower().startswith("si"):
                casos_notebook += 1

            sede = (d.get("codigo_sede") or "").strip() or "-"
            sedes[sede] = sedes.get(sede, 0) + 1

            try:
                promedio_vals.append(float(d.get("promedio") or 0))
            except Exception:
                pass
            if edad > 0:
                edad_vals.append(edad)
            horas = _safe_int(d.get("horas_pc"), 0)
            if horas > 0:
                horas_vals.append(horas)

        return jsonify({
            "ok": True,
            "total": total,
            "urgentes": urgentes,
            "programados": programados,
            "sin_accion_definida": sin_accion,
            "verificados": verificados,
            "pendientes_verificacion": pendientes_verificacion,
            "pendientes_relevamiento": pendientes_relevamiento,
            "registros_con_alertas_auditoria": with_alerts,
            "promedio_riesgo_general": round(sum(promedio_vals) / len(promedio_vals), 2) if promedio_vals else 0,
            "edad_promedio": round(sum(edad_vals) / len(edad_vals), 1) if edad_vals else 0,
            "casos_mayores_60": casos_60,
            "casos_mayores_70": casos_70,
            "casos_con_notebook": casos_notebook,
            "horas_pc_promedio": round(sum(horas_vals) / len(horas_vals), 1) if horas_vals else 0,
            "flujo_sgi": flow_counts,
            "relevamientos_por_sede": sedes,
        })

    @app.route("/sst/ergonomia/export.csv", methods=["GET"], endpoint="sst_ergonomia_export_csv")
    def sst_ergonomia_export_csv():
        con = get_db()
        ensure_sst_ergonomia_table(con)
        try:
            sedes = con.execute("""
                SELECT codigo, nombre, fuero
                FROM sedes_mpd
                ORDER BY codigo
            """).fetchall()
        except Exception:
            sedes = con.execute("""
                SELECT codigo, nombre
                FROM sedes_mpd
                ORDER BY codigo
            """).fetchall()

        ergo = build_ergonomia_context(con, sedes)
        con.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "sede",
            "nombre_apellido",
            "correo",
            "edad",
            "punt_edad",
            "punt_puesto",
            "punt_salud",
            "promedio",
            "semaforo",
            "accion_calculada",
            "estado_flujo",
            "fecha_relevamiento",
            "dias_desde_evaluacion",
            "evaluador",
            "horas_pc",
            "uso_notebook",
            "intervencion_realizada",
            "motivos_riesgo",
            "alertas_auditoria",
            "observaciones",
            "actualizado_en",
        ])

        for r in ergo.get("ergonomia_rows", []):
            motivos = r.get("motivos_riesgo") or []
            if isinstance(motivos, list):
                motivos_txt = " | ".join([str(x) for x in motivos if str(x).strip()])
            else:
                motivos_txt = str(motivos or "")
            alertas_raw = r.get("audit_alertas")
            try:
                alertas = json.loads(alertas_raw) if alertas_raw else []
                if isinstance(alertas, list):
                    alertas_txt = " | ".join([str(x) for x in alertas if str(x).strip()])
                else:
                    alertas_txt = str(alertas or "")
            except Exception:
                alertas_txt = str(alertas_raw or "")

            writer.writerow([
                r.get("codigo_sede", ""),
                r.get("nombre_apellido", ""),
                r.get("correo", ""),
                r.get("edad", ""),
                r.get("punt_edad", ""),
                r.get("punt_puesto", ""),
                r.get("punt_salud", ""),
                r.get("promedio", "") if r.get("promedio") is not None else "Pendiente",
                r.get("semaforo", ""),
                r.get("accion_label", r.get("accion", "")),
                r.get("estado_flujo", ""),
                r.get("fecha_relevamiento", ""),
                r.get("dias_desde_eval", ""),
                r.get("evaluador", ""),
                r.get("horas_pc", ""),
                r.get("uso_notebook", ""),
                r.get("intervencion_realizada", ""),
                motivos_txt,
                alertas_txt,
                r.get("observaciones", ""),
                r.get("actualizado_en", ""),
            ])

        csv_data = output.getvalue()
        output.close()

        sede_tag = (ergo.get("ergo_sede") or "todas").lower()
        fname = f"ergonomia_{sede_tag}_{date.today().strftime('%Y%m%d')}.csv"
        return Response(
            csv_data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )

    @app.route("/sst/ergonomia/pro_validacion", methods=["GET"], endpoint="sst_ergonomia_pro_validacion")
    def sst_ergonomia_pro_validacion():
        limit = _safe_int(request.args.get("limit"), 100)
        if limit <= 0:
            limit = 100
        limit = min(limit, 1000)

        con = get_db()
        ensure_sst_ergonomia_table(con)
        rows = con.execute("""
            SELECT
                personal_id,
                codigo_sede,
                nombre_apellido,
                accion_tomar,
                promedio,
                pro_score_final,
                pro_condicion_riesgo,
                pro_motivos,
                fecha_relevamiento,
                actualizado_en
            FROM sst_ergonomia
            ORDER BY actualizado_en DESC
            LIMIT ?
        """, (limit,)).fetchall()
        con.close()

        def _actual_to_bucket(action):
            a = (action or "").strip().lower()
            if a == "urgente":
                return "URGENTE"
            if a == "programado":
                return "PROGRAMADO"
            if a in ("no requiere atencion", "cerrado"):
                return "CONDICION_ADECUADA"
            return "PENDIENTE"

        out = []
        coincidencias = 0
        for r in rows:
            d = dict(r)
            actual = _actual_to_bucket(d.get("accion_tomar"))
            pro = (d.get("pro_condicion_riesgo") or "PENDIENTE").strip().upper()
            if actual == pro:
                coincidencias += 1
            try:
                motivos = json.loads(d.get("pro_motivos") or "[]")
            except Exception:
                motivos = []
            out.append({
                "personal_id": d.get("personal_id"),
                "sede": d.get("codigo_sede"),
                "nombre": d.get("nombre_apellido"),
                "actual_accion": d.get("accion_tomar"),
                "actual_bucket": actual,
                "pro_bucket": pro,
                "pro_score_final": d.get("pro_score_final"),
                "promedio_actual": d.get("promedio"),
                "motivos_pro": motivos,
                "fecha_relevamiento": d.get("fecha_relevamiento"),
                "actualizado_en": d.get("actualizado_en"),
                "coincide": actual == pro,
            })

        total = len(out)
        return jsonify({
            "ok": True,
            "total": total,
            "coincidencias": coincidencias,
            "diferencias": max(0, total - coincidencias),
            "ratio_coincidencia": round((coincidencias / total) * 100, 2) if total else 0,
            "items": out,
        })

    return rebuild_eventos_limpieza_sede

