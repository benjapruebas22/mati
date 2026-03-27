from flask import Blueprint
bp = Blueprint('inventario_checklist', __name__)
from . import routes
