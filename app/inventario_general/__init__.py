from flask import Blueprint
bp = Blueprint('inventario_general', __name__)
from . import routes
