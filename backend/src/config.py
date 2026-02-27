import os
from dotenv import dotenv_values

config = dotenv_values()


def get(key: str) -> str:
    return config.get(key) or os.environ.get(key, "")
