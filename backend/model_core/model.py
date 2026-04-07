import json
import random


def fake_model(user_id):
    with open("./data/user_history.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    lis = random.sample(data["test"], 5)
    return lis
