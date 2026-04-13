from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class POI(db.Model):
    __tablename__ = "pois"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, index=True)
    lat = db.Column(db.Float, nullable=False, index=True)
    lng = db.Column(db.Float, nullable=False, index=True)
    cat_name = db.Column(db.String(100), index=True)

    raw_data = db.Column(db.JSON, nullable=False)

    def to_dict(self):
        return self.raw_data


class UserHist(db.Model):
    __tablename__ = "userHis"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    poi_id = db.Column(db.Integer, nullable=False)
    visit_time = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        poi_record = POI.query.get(self.poi_id)
        return {
            "user_id": self.user_id,
            "visit_time": self.visit_time.strftime("%Y-%m-%dT%H:%M:%SZ") if self.visit_time else None,
            "poi_detail": poi_record.to_dict() if poi_record else None,
        }
