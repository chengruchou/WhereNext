"""What a visitor types must not reach the server log, even when reading it fails."""

import logging
from types import SimpleNamespace
from typing import Literal

import pytest
from flask import Flask
from pydantic import BaseModel, ValidationError

import routes.intent_api as intent_api
from services.intent_parser import CategoryVocabulary, IntentParser

REQUEST = "a quiet museum by the river, nothing with coffee"
VOCABULARY = CategoryVocabulary(["Museum", "Coffee Shop"])


class _Probe(BaseModel):
    mode: Literal["walk"]


def validation_error_quoting(text: str) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        _Probe(mode=text)
    return caught.value


def test_a_failed_parse_logs_neither_the_request_nor_the_error_text(monkeypatch, caplog):
    class Failing:
        config = None

        def parse(self, query):
            raise ValueError(f"cannot read {query!r}")

    monkeypatch.setattr(intent_api, "get_intent_parser", lambda: Failing())
    app = Flask(__name__)
    app.register_blueprint(intent_api.intent_bp)

    with caplog.at_level(logging.DEBUG):
        response = app.test_client().post("/api/intent/parse", json={"query": REQUEST})

    assert response.status_code == 500
    assert REQUEST in response.get_json()["error"]  # the visitor still sees what went wrong
    assert "ValueError" in caplog.text
    assert f"{len(REQUEST)} characters" in caplog.text
    assert "museum" not in caplog.text


def test_invalid_model_output_is_logged_by_field_not_by_content(caplog):
    error = validation_error_quoting(REQUEST)
    assert "museum" in str(error)  # the error text does quote its input

    def refuse(**_):
        raise error

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=refuse)))
    parser = IntentParser(SimpleNamespace(intent_model="test-model"), client=client)

    with caplog.at_level(logging.DEBUG):
        assert parser._parse_with_llm(REQUEST, VOCABULARY) is None

    assert "mode" in caplog.text
    assert "museum" not in caplog.text
