from importlib import import_module

def create_app():
    legacy = import_module("legacy_app")
    return legacy.app
