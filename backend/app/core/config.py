import os
from pathlib import Path


APP_NAME = os.getenv("APP_NAME", "RiskTrace AI")
API_PREFIX = "/api"
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
PROJECT_ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH_PATH = Path(
    os.getenv("GROUND_TRUTH_PATH", str(PROJECT_ROOT / "ground_truth" / "generated" / "truth_2026.jsonl"))
)
