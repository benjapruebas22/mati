from importlib import import_module
from modules.ordenes_mantenimiento import register_ordenes_mantenimiento
from modules.recorridos_operativos import register_recorridos_operativos

def create_app():
    legacy = import_module("legacy_app")
    register_ordenes_mantenimiento(legacy.app)
    register_recorridos_operativos(legacy.app)

    # Sin tocar legacy_app.py: habilita rutas extra bajo permisos de dashboard.
    if hasattr(legacy, "module_from_path") and not getattr(legacy, "_ordenes_module_patch", False):
        _orig_module_from_path = legacy.module_from_path

        def _module_from_path_with_ordenes(path: str) -> str:
            if str(path or "").startswith("/ordenes"):
                return "dashboard"
            return _orig_module_from_path(path)

        legacy.module_from_path = _module_from_path_with_ordenes
        legacy._ordenes_module_patch = True

    return legacy.app

# Compatibilidad con WSGI que espera "from app import app"
app = create_app()
