import os
from pathlib import Path
from dotenv import dotenv_values

config = dotenv_values(Path(__file__).parent.parent / ".env")


def get(key: str) -> str:
    return config.get(key) or os.environ.get(key, "")
