"""Show which keys in engine/.env are set (never prints values).  uv run python tools/check_env.py"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hive_engine.env import ENV_FILE, load_env  # noqa: E402

example = Path(__file__).resolve().parents[1] / ".env.example"
load_env()
print(f"{ENV_FILE} {'found' if ENV_FILE.exists() else 'MISSING (cp .env.example .env)'}")
for line in example.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        key = line.split("=", 1)[0]
        print(f"  {'✅' if os.environ.get(key) else '⬜'} {key}")
