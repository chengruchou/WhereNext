"""The keyword parser, which reads requests when Claude is unavailable."""

import pytest
from services.intent_parser import CategoryVocabulary, parse_with_keywords, resolve_intent

VOCABULARY = CategoryVocabulary(
    ["Museum", "History Museum", "Coffee Shop", "Bar", "AT&T", "Subway", "London Underground",
     "Hostel", "Hotel", "Plaza / Square", "Beach", "Rental Car"]
)


def read(text: str):
    parsed = parse_with_keywords(text, VOCABULARY)
    return resolve_intent(parsed, query=text, vocabulary=VOCABULARY, source="keyword")


def names(matches) -> set[str]:
    return {m.category_name for m in matches}


@pytest.mark.parametrize(
    ("text", "avoided"),
    [
        ("no coffee", "Coffee Shop"),
        ("I don't want coffee", "Coffee Shop"),
        ("I do not want a bar", "Bar"),
        ("anything but a museum", "Museum"),
        ("not in the mood for a bar", "Bar"),
    ],
)
def test_negations_avoid_the_type(text, avoided):
    intent = read(text)
    assert avoided in names(intent.avoid)
    assert avoided not in names(intent.want)


def test_a_wanted_and_an_avoided_type():
    intent = read("a museum, no coffee")
    assert "Museum" in names(intent.want)
    assert "Coffee Shop" in names(intent.avoid)


def test_whole_names_with_short_words():
    assert "AT&T" in names(read("take me to an AT&T").want)


def test_a_typo_still_finds_the_type():
    assert "Museum" in names(read("a musuem").want)


@pytest.mark.parametrize(
    ("text", "mode"),
    [("a bar on foot", "walk"), ("walk to a bar", "walk"), ("a bar by car", "drive"),
     ("a bar by bus", "transit"), ("a bar by subway", "transit")],
)
def test_travel_mode(text, mode):
    assert read(text).travel_mode == mode


def test_by_subway_is_a_mode_not_a_place():
    assert "Subway" not in names(read("a bar by subway").want)


@pytest.mark.parametrize(
    ("text", "km"),
    [("a bar within 2 km", 2.0), ("a bar within 3 miles", 4.827),
     ("a bar less than 500 m away", 0.5), ("a bar under 1 km", 1.0)],
)
def test_maximum_hop(text, km):
    assert read(text).max_hop_km == pytest.approx(km, rel=0.01)


def test_a_distance_is_not_a_place():
    assert "London Underground" not in names(read("a bar under 1 km").want)


@pytest.mark.parametrize("text", ["un musée", "博物館に行きたい", "a zzqx place"])
def test_nothing_is_dropped_silently(text):
    intent = read(text)
    assert intent.want or intent.avoid or intent.unresolved
