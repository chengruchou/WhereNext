from flask import Blueprint, jsonify, request
import json

db_bp = Blueprint("db", __name__, url_prefix="/api/db")

@db_bp.route('/fetch/<string:user_id>', methods=['GET'])
def fetch(user_id):
    with open('data/user_history.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data.get(user_id, []))