import os

import uvicorn

# Позволяет запускать:  python -m app
# Хост/порт можно настроить через переменные окружения.
host = os.getenv("APP_HOST", "0.0.0.0")
port = int(os.getenv("APP_PORT", "8080"))
reload_opt = os.getenv("APP_RELOAD", "false").lower() == "true"

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_opt)
