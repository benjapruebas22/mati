from flask import Blueprint

bp = Blueprint('sst', __name__)

from . import routes
