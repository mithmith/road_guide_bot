from app.config import (
    CONVERSATIONS_DIR,
    MAX_HISTORY_MESSAGES,
    MODEL_NAME,
    SYSTEM_PROMPT_PATH,
)
from fastapi import FastAPI
from openai import OpenAI

from app.api.routes import router
from app.services.chat import ChatService
from app.services.conversation_store import ConversationStore
from app.utils.prompt_loader import PromptLoader


def create_app() -> FastAPI:
    app = FastAPI(title="GPT-5 Chat Service", version="1.0.0")

    @app.on_event("startup")
    def _startup():
        client = OpenAI()  # берет OPENAI_API_KEY из окружения
        prompt_loader = PromptLoader(SYSTEM_PROMPT_PATH)
        store = ConversationStore(CONVERSATIONS_DIR)
        chat_service = ChatService(
            client=client,
            prompt_loader=prompt_loader,
            store=store,
            model_name=MODEL_NAME,
            max_history_messages=MAX_HISTORY_MESSAGES,
        )
        app.state.chat_service = chat_service

    app.include_router(router, prefix="/api")
    return app


app = create_app()
