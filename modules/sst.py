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
        ])
        con.commit()

    SST_VISITA_TIPOS = [
        "ART",
        "Interna",
        "Seguimiento",
        "Relevamiento inicial",
    ]
    SST_VISITA_ESTADOS = [
        "SIN_OBS",
        "CON_OBS",
        "REQUIERE_CORRECCION",
        "PEND_ANALISIS",
    ]
    SST_DOC_TIPOS = [
        "DEC_351_79",
        "RGRL",
        "RAR",
        "ACTA",
        "FOTO",
        "OTRO",
    ]
    SST_DOC_ESTADOS_REVISION = [
        "PENDIENTE",
        "REVISADO",
    ]

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
    import sqlite3
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
            return _estado_norm(item.get("estado")) not in (
                "no va a ir", "no va ir", "sin aire", "n/a", "no aplica"
            )

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
            return redirect(url_for("sede_aires", codigo=codigo))

            # si algo falla, vuelve a mostrar el formulario

        return render_template("aire_form.html", sede=sede, aire=None, locales_opts=locales_opts)


    @app.route("/sedes/<codigo>/aires/<int:aid>/editar", methods=["GET", "POST"])
    def aire_editar(codigo, aid):
        con, cur, sede = obtener_sede(codigo)
        locales_opts = _locales_sede(cur, codigo)

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
            return redirect(url_for("sede_aires", codigo=codigo))

        return render_template("aire_form.html", sede=sede, aire=aire, locales_opts=locales_opts)


    @app.route("/sedes/<codigo>/aires/<int:aid>/borrar", methods=["POST"])
    def aire_borrar(codigo, aid):
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            DELETE FROM aires_mpd
            WHERE id = ? AND sede_codigo = ?
        """, (aid, codigo))
        con.commit()
        return redirect(url_for("sede_aires", codigo=codigo))

    def rebuild_eventos_sst():
        # Placeholder para mantener compatibilidad si se llama desde SST.
        return None

    @app.route("/sst", methods=["GET", "POST"], endpoint="sst_general")
    def sst_general():
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

        context = build_sst_plan_context(show_carga=False, sst_view=(request.args.get("vista") or "all"))
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

    def _sst_sede_estado_label(estado_code):
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

    @app.route("/sst/visitas", methods=["GET"], endpoint="sst_visitas")
    def sst_visitas():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)

        q = (request.args.get("q") or "").strip().lower()
        q_estado = (request.args.get("estado") or "").strip().lower()

        sedes_rows = con.execute("""
            SELECT codigo, nombre, fuero
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        last_visita = {}
        for r in con.execute("""
            SELECT id, sede_codigo, fecha, tipo_visita, responsable, estado, observaciones
            FROM sst_visitas
            ORDER BY fecha DESC, id DESC
        """).fetchall():
            sc = (r["sede_codigo"] or "").strip().upper()
            if sc and sc not in last_visita:
                last_visita[sc] = r

        docs_latest = defaultdict(dict)  # docs_latest[sede][tipo] = row
        for r in con.execute("""
            SELECT id, sede_codigo, tipo, fecha_documento, fecha_carga, archivo, drive_url, estado_revision
            FROM sst_documentos
            ORDER BY COALESCE(fecha_documento, fecha_carga) DESC, id DESC
        """).fetchall():
            sc = (r["sede_codigo"] or "").strip().upper()
            tp = (r["tipo"] or "").strip().upper()
            if not sc or not tp:
                continue
            if tp not in docs_latest[sc]:
                docs_latest[sc][tp] = r

        pend_hallazgos = {}
        for r in con.execute("""
            SELECT sede_codigo, COUNT(*) AS cnt
            FROM sst_general
            WHERE tipo = 'no_conformidad'
              AND COALESCE(estado,'') <> 'CERRADO'
              AND sede_codigo IS NOT NULL
              AND TRIM(COALESCE(sede_codigo,'')) <> ''
            GROUP BY sede_codigo
        """).fetchall():
            pend_hallazgos[(r["sede_codigo"] or "").strip().upper()] = int(r["cnt"] or 0)

        sedes = []
        stats_total = 0
        stats_sin_visita = 0
        stats_docs_pend = 0
        stats_en_seguimiento = 0

        for s in sedes_rows:
            codigo = (s["codigo"] or "").strip().upper()
            nombre = (s["nombre"] or "").strip()
            fuero = (s["fuero"] or "").strip()
            fuero_class, fuero_color = _sst_fuero_style(fuero)
            v = last_visita.get(codigo)
            v_fecha = v["fecha"] if v else None
            v_estado = v["estado"] if v else None

            d351 = docs_latest.get(codigo, {}).get("DEC_351_79")
            drgrl = docs_latest.get(codigo, {}).get("RGRL")
            d351_ok = bool(d351 and (d351["drive_url"] or d351["archivo"]))
            drgrl_ok = bool(drgrl and (drgrl["drive_url"] or drgrl["archivo"]))
            docs_ok = d351_ok and drgrl_ok
            docs_pend = False
            if d351 and (str(d351["estado_revision"] or "").strip().upper() == "PENDIENTE"):
                docs_pend = True
            if drgrl and (str(drgrl["estado_revision"] or "").strip().upper() == "PENDIENTE"):
                docs_pend = True

            pend = int(pend_hallazgos.get(codigo, 0) or 0)
            sem_cls, sem_label = _sst_calc_semaforo(bool(v), docs_ok, docs_pend, pend)

            item = {
                "codigo": codigo,
                "nombre": nombre,
                "fuero": fuero,
                "fuero_class": fuero_class,
                "fuero_color": fuero_color,
                "ultima_visita": _sst_fmt_fecha(v_fecha),
                "ultima_visita_estado": _sst_sede_estado_label(v_estado),
                "doc_351": d351,
                "doc_rgrl": drgrl,
                "docs_ok": docs_ok,
                "docs_pend": docs_pend,
                "pend_hallazgos": pend,
                "semaforo_cls": sem_cls,
                "semaforo_label": sem_label,
            }

            hay_texto = f"{codigo} {nombre}".lower()
            if q and q not in hay_texto:
                continue
            if q_estado and q_estado not in (sem_label or "").lower() and q_estado != sem_cls.lower():
                continue

            stats_total += 1
            if not v:
                stats_sin_visita += 1
            if not docs_ok or docs_pend:
                stats_docs_pend += 1
            if pend > 0:
                stats_en_seguimiento += 1

            sedes.append(item)

        con.close()

        return render_template(
            "sst_visitas.html",
            sedes=sedes,
            q=q,
            q_estado=q_estado,
            stats_total=stats_total,
            stats_sin_visita=stats_sin_visita,
            stats_docs_pend=stats_docs_pend,
            stats_en_seguimiento=stats_en_seguimiento,
        )

    @app.route("/sst/visitas/cargar", methods=["GET", "POST"], endpoint="sst_visita_cargar")
    def sst_visita_cargar():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)

        sedes = con.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        pre_sede = (request.args.get("sede") or "").strip().upper()
        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            fecha = (request.form.get("fecha") or "").strip()
            tipo_visita = (request.form.get("tipo_visita") or "").strip()
            responsable = (request.form.get("responsable") or "").strip()
            estado = (request.form.get("estado") or "").strip()
            observaciones = (request.form.get("observaciones") or "").strip()

            if not sede_codigo or not fecha:
                flash("Sede y fecha son obligatorios.", "error")
                con.close()
                return redirect(url_for("sst_visita_cargar", sede=pre_sede or None))

            con.execute("""
                INSERT INTO sst_visitas (sede_codigo, fecha, tipo_visita, responsable, estado, observaciones)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sede_codigo,
                fecha,
                (tipo_visita or None),
                (responsable or None),
                (estado or None),
                (observaciones or None),
            ))
            con.commit()
            con.close()
            flash("Visita cargada.", "success")
            return redirect(url_for("sst_sede_ficha", codigo=sede_codigo))

        con.close()
        return render_template(
            "sst_visita_form.html",
            sedes=sedes,
            pre_sede=pre_sede,
            tipos=SST_VISITA_TIPOS,
            estados=SST_VISITA_ESTADOS,
        )

    @app.route("/sst/docs/subir", methods=["GET", "POST"], endpoint="sst_doc_subir")
    def sst_doc_subir():
        con = get_db()
        ensure_sst_visitas_docs_tables(con)

        sedes = con.execute("""
            SELECT codigo, nombre
            FROM sedes_mpd
            ORDER BY codigo
        """).fetchall()

        pre_sede = (request.args.get("sede") or "").strip().upper()
        pre_visita_id = (request.args.get("visita_id") or "").strip()

        if request.method == "POST":
            sede_codigo = (request.form.get("sede_codigo") or "").strip().upper()
            visita_id_raw = (request.form.get("visita_id") or "").strip()
            doc_tipo = (request.form.get("tipo") or "").strip().upper()
            fecha_documento = (request.form.get("fecha_documento") or "").strip()
            drive_url = (request.form.get("drive_url") or "").strip()
            estado_revision = (request.form.get("estado_revision") or "").strip().upper()
            notas = (request.form.get("notas") or "").strip()

            visita_id = int(visita_id_raw) if visita_id_raw.isdigit() else None
            archivo_name = None

            file = request.files.get("archivo")
            if file and getattr(file, "filename", ""):
                if not allowed_sst_doc(file.filename):
                    flash("Archivo no permitido. Use PDF/JPG/PNG.", "error")
                    con.close()
                    return redirect(url_for("sst_doc_subir", sede=pre_sede or None))
                safe = secure_filename(file.filename)
                unique = f"{sede_codigo}_{doc_tipo}_{uuid.uuid4().hex}_{safe}"
                file.save(os.path.join(SST_DOCS_FOLDER, unique))
                archivo_name = unique

            if not sede_codigo or not doc_tipo:
                flash("Sede y tipo de documento son obligatorios.", "error")
                con.close()
                return redirect(url_for("sst_doc_subir", sede=pre_sede or None))

            if not drive_url and not archivo_name:
                flash("Pegue un enlace Drive o suba un archivo.", "error")
                con.close()
                return redirect(url_for("sst_doc_subir", sede=pre_sede or None))

            con.execute("""
                INSERT INTO sst_documentos (
                    sede_codigo, visita_id, tipo,
                    fecha_documento, archivo, drive_url,
                    estado_revision, notas
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sede_codigo,
                visita_id,
                doc_tipo,
                (fecha_documento or None),
                archivo_name,
                (drive_url or None),
                (estado_revision or None),
                (notas or None),
            ))
            con.commit()
            con.close()
            flash("Documento cargado.", "success")
            return redirect(url_for("sst_sede_ficha", codigo=sede_codigo))

        con.close()
        return render_template(
            "sst_doc_form.html",
            sedes=sedes,
            pre_sede=pre_sede,
            pre_visita_id=pre_visita_id,
            tipos=SST_DOC_TIPOS,
            estados_revision=SST_DOC_ESTADOS_REVISION,
        )

    @app.route("/sst/docs/archivo/<path:filename>", methods=["GET"], endpoint="sst_doc_archivo")
    def sst_doc_archivo(filename):
        return send_from_directory(SST_DOCS_FOLDER, filename, as_attachment=False)

    @app.route("/sst/sedes/<codigo>", methods=["GET"], endpoint="sst_sede_ficha")
    def sst_sede_ficha(codigo):
        codigo = (codigo or "").strip().upper()
        con = get_db()
        ensure_sst_visitas_docs_tables(con)
        ensure_sst_general_table(con)

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

