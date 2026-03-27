from flask import Blueprint
bp = Blueprint('auditorias', __name__)
from . import routes
