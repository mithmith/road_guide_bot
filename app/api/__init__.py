from fastapi import FastAPI
from app.config import logger

from app.api.routes import router
from app.config import CONVERSATIONS_DIR, MAX_HISTORY_MESSAGES, MODEL_NAME, OPENAI_API_KEY, SYSTEM_PROMPT_PATH
from app.integration.chatgpt import OpenAIClient
from app.integration.http_clients import close_http_clients
from app.services.chat import ChatService
from app.services.conversation_store import ConversationStore
from app.utils.prompt_loader import PromptLoader


def create_app() -> FastAPI:
    app = FastAPI(title="GPT-5 Chat Service", version="1.0.0")

    @app.on_event("startup")
    def _startup():
        logger.info("Starting up application")
        client = OpenAIClient(api_key=OPENAI_API_KEY, model_name=MODEL_NAME)
        prompt_loader = PromptLoader(SYSTEM_PROMPT_PATH)
        store = ConversationStore(CONVERSATIONS_DIR)
        logger.debug(
            "ChatService init with model=%s, system_prompt_path=%s, conversations_dir=%s, max_history=%s",
            MODEL_NAME,
            SYSTEM_PROMPT_PATH,
            CONVERSATIONS_DIR,
            MAX_HISTORY_MESSAGES,
        )
        chat_service = ChatService(
            client=client,
            prompt_loader=prompt_loader,
            store=store,
            max_history_messages=MAX_HISTORY_MESSAGES,
        )
        app.state.chat_service = chat_service
        logger.info("ChatService initialized")

    app.include_router(router, prefix="/api")
    app.add_event_handler("shutdown", close_http_clients)
    logger.info("Router mounted at /api and shutdown handler registered")
    return app


app = create_app()
