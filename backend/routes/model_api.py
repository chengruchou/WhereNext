from flask import Blueprint, jsonify, request

model_bp = Blueprint("model", __name__, url_prefix="/api/model")