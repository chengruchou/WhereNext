"""The verifier keeps sentences the evidence supports and removes ones it does not."""

import pytest
from contracts.evidence import ExplanationSentence
from services.explanation_verifier import verify_sentence

CATEGORIES = sorted(
    ["Museum", "History Museum", "Coffee Shop", "Starbucks", "Best Buy", "Subway"],
    key=len,
    reverse=True,
)

EVIDENCE = {
    "history": [
        {"category_name": "Coffee Shop", "raw_poi_id": 1},
        {"category_name": "Coffee Shop", "raw_poi_id": 2},
        {"category_name": "Starbucks", "raw_poi_id": 3},
    ],
    "intent": {
        "query": "a museum, nothing with coffee",
        "want": [{"category_name": "Museum", "phrase": "museum"}],
        "avoid": [{"category_name": "Coffee Shop", "phrase": "coffee"}],
        "num_stops": 3,
    },
    "controls": {"habit_intent": 0.5, "explore": 0.1},
    "steps": [
        {
            "step": 1, "rank": 1, "pool_size": 6,
            "poi": {"category_name": "Museum", "raw_poi_id": 10, "checkins_count": 412},
            "travel": {"distance_km": 0.11, "mode": "drive"},
            "intent": {"matched_want": ["Museum"], "in_range": 6, "search_radius_km": 40.0},
            "history": {"history_window": 3, "same_category_visits": 0,
                        "visited_this_poi": False},
        },
        {
            "step": 2, "rank": 1, "pool_size": 5,
            "poi": {"category_name": "History Museum", "raw_poi_id": 11, "checkins_count": 37},
            "travel": {"distance_km": 0.73, "mode": "drive"},
            "intent": {"matched_want": ["History Museum"], "in_range": 5,
                       "search_radius_km": 40.0},
            "history": {"history_window": 3, "same_category_visits": 0,
                        "visited_this_poi": False},
        },
    ],
}


def verdict(text: str, refs: list[str], step: int | None = 1) -> str:
    sentence = ExplanationSentence(text=text, evidence_refs=refs)
    return verify_sentence(sentence, EVIDENCE, CATEGORIES, step=step, index=0).verdict


@pytest.mark.parametrize(
    ("text", "refs"),
    [
        ("It is 0.11 km from your last stop.", ["steps[0].travel.distance_km"]),
        ("It is 110 m from your last stop.", ["steps[0].travel.distance_km"]),
        ("It is about 0.1 km away.", ["steps[0].travel.distance_km"]),
        ("The 1st stop is 0.11 km away.", ["steps[0].travel.distance_km"]),
        ("First, a Museum, one of the places you asked for, just 0.11 km away and new to you.",
         ["steps[0].poi.category_name", "steps[0].intent.matched_want",
          "steps[0].travel.distance_km"]),
        ("It is a Museum, not a Coffee Shop, as you asked.",
         ["steps[0].poi.category_name", "intent.avoid[0].category_name"]),
        ("It is a Museum instead of another Coffee Shop.", ["steps[0].poi.category_name"]),
        ("It is one of 6 museums within 40 km.",
         ["steps[0].intent.in_range", "steps[0].intent.search_radius_km"]),
        ("None of your last 3 visits were to a Museum.",
         ["steps[0].history.history_window", "steps[0].poi.category_name"]),
    ],
)
def test_keeps_true_sentences(text, refs):
    assert verdict(text, refs) == "supported"


@pytest.mark.parametrize(
    ("text", "refs"),
    [
        ("It is 0.6 km from your last stop.", ["steps[0].travel.distance_km"]),
        ("It is 0.11 miles from your last stop.", ["steps[0].travel.distance_km"]),
        ("It is 0.73 km from your last stop.", ["steps[1].travel.distance_km"]),
        ("It is 0.11 km away.", ["steps[0].travel.distance_km", "steps[0].poi.rating"]),
        ("It is a Starbucks.", ["steps[0].poi.category_name", "intent.avoid[0].category_name"]),
        ("This stop is a Coffee Shop.", ["intent.avoid[0].category_name"]),
        ("It is not a Museum.", ["steps[0].poi.category_name"]),
        ("You often visit Museum places.",
         ["steps[0].poi.category_name", "steps[0].history.same_category_visits"]),
        ("A Coffee Shop is new to you.", ["history[0].category_name"]),
        ("It is the closest Museum to your last stop.",
         ["steps[0].poi.category_name", "steps[0].travel.distance_km"]),
        ("It is a Museum popular with locals.", ["steps[0].poi.category_name"]),
        ("It is a highly rated Museum.", ["steps[0].poi.category_name"]),
        ("You visited Museum places three times.",
         ["steps[0].poi.category_name", "steps[0].history.same_category_visits"]),
        ("You have been to 3 museums.", ["steps[0]"]),
        ("50% of your visits were to museums.", ["controls"]),
    ],
)
def test_removes_false_sentences(text, refs):
    assert verdict(text, refs) == "unsupported"


def test_the_number_of_stops_is_a_fact_of_the_route():
    text = "This route takes you to two museums you asked for."
    assert verdict(text, ["steps[0].intent.matched_want"], step=None) == "supported"
    assert verdict("It visits three museums.", ["steps[0].intent.matched_want"],
                   step=None) == "unsupported"


def test_usual_habits_are_not_a_claim_about_visiting_a_type():
    text = "A Museum 0.11 km away that fits the way you usually move between places."
    assert verdict(text, ["steps[0].poi.category_name", "steps[0].travel.distance_km"]) == (
        "supported")
    assert verdict("You usually visit Museum places.", ["steps[0].poi.category_name"]) == (
        "unsupported")


ARENAS = {
    "history": [{"category_name": "Bar", "raw_poi_id": 1}],
    "intent": {"want": [{"category_name": "Arena", "phrase": "arena"}], "avoid": []},
    "steps": [
        {"step": k, "poi": {"category_name": c, "raw_poi_id": 10 + k},
         "travel": {"distance_km": 1.0}, "intent": {"matched_want": m},
         "history": {"history_window": 1, "same_category_visits": 0, "visited_this_poi": False}}
        for k, c, m in ((1, "Arena", ["Arena"]), (2, "Arena", ["Arena"]),
                        (3, "Convention Center", []))
    ],
}


def test_counts_of_some_stops():
    names = ["Convention Center", "Arena", "Bar"]

    def check(text: str) -> str:
        sentence = ExplanationSentence(text=text, evidence_refs=["steps[0].intent.matched_want"])
        return verify_sentence(sentence, ARENAS, names, step=None, index=0).verdict

    assert check("Two Arenas you asked for, then a Convention Center.") == "supported"
    assert check("It starts at an Arena, then follows your habits to two more stops.") == (
        "supported")
    assert check("Four Arenas you asked for.") == "unsupported"


def test_frequency_words_apply_to_their_own_clause():
    fits_habit = ("A History Museum 0.73 km away, which fits the order of places you usually "
                  "visit.")
    assert verdict(fits_habit, ["steps[1].poi.category_name", "steps[1].travel.distance_km"],
                   step=2) == "supported"
    assert verdict("You usually visit History Museum places.",
                   ["steps[1].poi.category_name"], step=2) == "unsupported"


def test_not_been_here_is_about_the_place():
    text = "A Museum 0.11 km away; you have not been to this place before."
    refs = ["steps[0].poi.category_name", "steps[0].travel.distance_km",
            "steps[0].history.visited_this_poi"]
    assert verdict(text, refs) == "supported"


def test_a_type_name_is_not_a_comparison():
    sentence = ExplanationSentence(text="It is a Best Buy.", evidence_refs=["intent.query"])
    result = verify_sentence(sentence, EVIDENCE, CATEGORIES, step=None, index=0)
    assert "comparison" not in (result.reason or "")  # "Best" here is part of a type's name


def test_a_sentence_with_nothing_to_check_is_unverifiable():
    assert verdict("It fits your request.", ["steps[0].intent.matched_want"]) == "unverifiable"
