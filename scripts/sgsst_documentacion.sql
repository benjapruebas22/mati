-- SG-SST - Bloque documental interno (SQLite)
-- Tablas base para documentación interna (sin Drive)

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
);

CREATE INDEX IF NOT EXISTS idx_sgsst_documentos_bloque ON sgsst_documentos(bloque);
CREATE INDEX IF NOT EXISTS idx_sgsst_documentos_activo ON sgsst_documentos(activo);

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
);

CREATE INDEX IF NOT EXISTS idx_sgsst_protocolos_categoria ON sgsst_protocolos(categoria);
CREATE INDEX IF NOT EXISTS idx_sgsst_protocolos_activo ON sgsst_protocolos(activo);

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
);

CREATE INDEX IF NOT EXISTS idx_sgsst_instructivos_categoria ON sgsst_instructivos(categoria);
CREATE INDEX IF NOT EXISTS idx_sgsst_instructivos_activo ON sgsst_instructivos(activo);

