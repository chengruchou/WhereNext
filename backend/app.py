from database import db
from flask import Flask
from flask_cors import CORS
from routes.model_api import model_bp
from routes.poi_api import poi_bp
from routes.route_api import route_bp
from routes.user_api import user_bp
from routes.chat_api import chat_bp

app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()

app.register_blueprint(user_bp)
app.register_blueprint(model_bp)
app.register_blueprint(poi_bp)
app.register_blueprint(route_bp)
app.register_blueprint(chat_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
