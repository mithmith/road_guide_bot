import os
from pathlib import Path

# Сетевые параметры
HOST: str = "127.0.0.1"
PORT: int = 8000

# Модель и пути
MODEL_NAME: str = "gpt-5-mini"
SYSTEM_PROMPT_PATH: Path = Path("app/prompts/main_guide.md")
CONVERSATIONS_DIR: Path = Path("conversations")

# Прочие настройки (можете расширять по необходимости)
MAX_HISTORY_MESSAGES: int | None = None  # например, ограничение «окна» истории

# Значения берутся из окружения. Ранее переменные были пустыми строками,
# из-за чего приложение сразу падало с ``RuntimeError``, даже если
# соответствующие переменные окружения были заданы при запуске. Читаем
# значения через ``os.getenv``.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
YANDEX_GEOCODER_API_KEY = os.getenv("YANDEX_GEOCODER_API_KEY", "")
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
PROMPT_PATH = os.getenv("PROMPT_PATH", "")
OUT_PATH = os.getenv("OUT_PATH", "")

# -------------------- Конфигурация --------------------

if not YANDEX_GEOCODER_API_KEY:
    raise RuntimeError("Set YANDEX_GEOCODER_API_KEY")
if not ORS_API_KEY:
    raise RuntimeError("Set ORS_API_KEY")

YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/v1"
ORS_DIRECTIONS_URL = (
    "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
)

# Троттлинг reverse-геокодера, чтобы не долбить Яндекс слишком агрессивно
REV_GEOCODER_CONCURRENCY: int = 4
