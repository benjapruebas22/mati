from flask import Blueprint

bp = Blueprint('agentes', __name__)

from . import routes
