from flask import Flask
from flask_cors import CORS
from routes.db_api import db_bp
from routes.model_api import model_bp

app = Flask(__name__)
CORS(app)

app.register_blueprint(db_bp)
app.register_blueprint(model_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)