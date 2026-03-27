from flask import Blueprint
bp = Blueprint('mapa', __name__)
from . import routes
