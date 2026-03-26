from importlib import import_module

def create_app():
    legacy = import_module("legacy_app")
    return legacy.app

# Compatibilidad con WSGI que espera "from app import app"
app = create_app()
