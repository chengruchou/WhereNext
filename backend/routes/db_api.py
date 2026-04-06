from flask import Blueprint, jsonify, request

db_bp = Blueprint("db", __name__, url_prefix="/api/db")