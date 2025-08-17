import os

import uvicorn

# Позволяет запускать:  python -m app
# Хост/порт можно настроить через переменные окружения.
host = os.getenv("APP_HOST", "0.0.0.0")
port = int(os.getenv("APP_PORT", "8080"))
reload_opt = os.getenv("APP_RELOAD", "false").lower() == "true"

if __name__ == "__main__":
    # ``app.main`` no longer exists.  The FastAPI application instance is
    # created in ``app/api/__init__.py`` and can be imported as
    # ``app.api:app``.  Using the old import path resulted in ``uvicorn``
    # failing to start with ``Error loading ASGI app`` because the module did
    # not exist.  Point ``uvicorn`` to the correct location so running
    # ``python -m app`` boots the service as expected.
    uvicorn.run("app.api:app", host=host, port=port, reload=reload_opt)
