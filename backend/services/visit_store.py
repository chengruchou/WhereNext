"""Where a traveler's visits are kept.

Dataset users' visits live in the database. The reserved demo travelers (user IDs from
DEMO_USER_ID_MIN up) live in this process's memory only: loading or editing one at a booth
writes nothing to disk, and a restart forgets it. With WHERENEXT_BOOTH=true, edits to any other
user are refused as well, so nothing a visitor does reaches the database.
"""

from __future__ import annotations

import itertools
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database import POI, UserHist, db

DEMO_USER_ID_MIN = 900000
# In-memory visits get log IDs far above any database row's, so one delete route serves both.
_LOG_ID_START = 10**12


class EditRefused(Exception):
    """A change the server is not allowed to write."""


@dataclass
class Visit:
    """A demo traveler's visit, shaped like a UserHist row."""

    id: int
    user_id: int
    poi_id: int
    visit_time: datetime | None

    def to_dict(self) -> dict[str, Any]:
        poi = db.session.get(POI, self.poi_id)
        return {
            "log_id": self.id,
            "user_id": self.user_id,
            "visit_time": self.visit_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.visit_time
            else None,
            "poi_detail": poi.to_dict() if poi else None,
        }


_lock = threading.Lock()
_demo: dict[int, list[Visit]] = {}
_log_ids = itertools.count(_LOG_ID_START)


def is_demo(user_id: int) -> bool:
    return user_id >= DEMO_USER_ID_MIN


def booth_mode() -> bool:
    return os.getenv("WHERENEXT_BOOTH", "").strip().lower() in {"1", "true", "yes"}


def visits(user_id: int) -> list[Any]:
    """The user's visits, oldest first: Visit for demo travelers, UserHist rows otherwise."""

    if is_demo(user_id):
        with _lock:
            kept = list(_demo.get(user_id, []))
        return sorted(kept, key=lambda v: (v.visit_time or datetime.min, v.id))
    return UserHist.query.filter_by(user_id=user_id).order_by(UserHist.visit_time).all()


def add(user_id: int, poi_id: int, visit_time: datetime | None) -> None:
    if is_demo(user_id):
        with _lock:
            _demo.setdefault(user_id, []).append(
                Visit(id=next(_log_ids), user_id=user_id, poi_id=poi_id, visit_time=visit_time)
            )
        return
    _check_writable()
    db.session.add(UserHist(user_id=user_id, poi_id=poi_id, visit_time=visit_time))
    db.session.commit()


def clear(user_id: int) -> None:
    if is_demo(user_id):
        with _lock:
            _demo.pop(user_id, None)
        return
    _check_writable()
    UserHist.query.filter(UserHist.user_id == user_id).delete()
    db.session.commit()


def remove(log_id: int) -> None:
    if log_id >= _LOG_ID_START:
        with _lock:
            for user_visits in _demo.values():
                user_visits[:] = [v for v in user_visits if v.id != log_id]
        return
    _check_writable()
    row = db.session.get(UserHist, log_id)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


def _check_writable() -> None:
    if booth_mode():
        raise EditRefused("At the booth, only the demo travelers' visits can be changed.")
