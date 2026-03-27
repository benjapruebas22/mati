from flask import Blueprint
bp = Blueprint('obras', __name__)
from . import routes
