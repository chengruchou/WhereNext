import sys
from pathlib import Path

# Tests import the backend the way the app does: `services.*`, `contracts.*`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
