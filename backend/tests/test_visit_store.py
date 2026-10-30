"""Demo travelers' visits stay in memory; at the booth nothing else can be changed."""

from datetime import datetime

import pytest
from database import POI, UserHist, db
from flask import Flask
from routes.user_api import user_bp
from services import visit_store

DEMO = visit_store.DEMO_USER_ID_MIN + 1
DATASET_USER = 42


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("WHERENEXT_BOOTH", raising=False)
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db.init_app(app)
    app.register_blueprint(user_bp)
    with app.app_context():
        db.create_all()
        db.session.add(POI(id=18417, lat=30.27, lng=-97.74, cat_name="Coffee Shop",
                           raw_data={"raw_poi_id": 18417, "category_name": "Coffee Shop"}))
        db.session.commit()
        yield app.test_client()
        visit_store.clear(DEMO)
        db.drop_all()


def test_demo_visits_never_reach_the_database(client):
    response = client.post(f"/api/user/{DEMO}",
                           json={"poi_id": 18417, "visit_time": "2010-05-31T17:00:00Z"})
    assert response.status_code == 200
    assert UserHist.query.count() == 0
    shown = client.get(f"/api/user/{DEMO}").get_json()
    assert [p["category_name"] for p in shown["userHistPlace"]] == ["Coffee Shop"]
    assert [v.poi_id for v in visit_store.visits(DEMO)] == [18417]


def test_one_demo_visit_can_be_removed(client):
    visit_store.add(DEMO, 18417, datetime(2010, 5, 31, 17))
    visit_store.add(DEMO, 18417, datetime(2010, 5, 31, 19))
    first = client.get(f"/api/user/{DEMO}").get_json()["userHist"][0]["log_id"]
    assert client.delete(f"/api/user/delone/{first}").status_code == 200
    assert len(visit_store.visits(DEMO)) == 1


def test_dataset_users_are_written_to_the_database(client):
    client.post(f"/api/user/{DATASET_USER}",
                json={"poi_id": 18417, "visit_time": "2010-05-31T17:00:00Z"})
    assert UserHist.query.filter_by(user_id=DATASET_USER).count() == 1


def test_at_the_booth_only_demo_travelers_change(client, monkeypatch):
    monkeypatch.setenv("WHERENEXT_BOOTH", "true")
    refused = client.post(f"/api/user/{DATASET_USER}",
                          json={"poi_id": 18417, "visit_time": "2010-05-31T17:00:00Z"})
    assert refused.status_code == 403
    assert client.delete(f"/api/user/{DATASET_USER}").status_code == 403
    assert UserHist.query.count() == 0
    assert client.post(f"/api/user/{DEMO}", json={"poi_id": 18417}).status_code == 200
