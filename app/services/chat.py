import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app.services.conversation_store import ConversationStore
from app.utils.prompt_loader import PromptLoader


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatResult:
    conversation_id: str
    assistant_text: str
    response_id: Optional[str]


class ChatService:
    """
    Сервис ведения диалогов и общения с моделью.
    Инкапсулирует:
      - загрузку системного промпта
      - восстановление истории
      - сбор сообщений и вызов OpenAI Responses API
      - логирование истории в ConversationStore
    """

    def __init__(
        self,
        client: OpenAI,
        prompt_loader: PromptLoader,
        store: ConversationStore,
        model_name: str,
        max_history_messages: Optional[int] = None,
    ):
        self.client = client
        self.prompt_loader = prompt_loader
        self.store = store
        self.model_name = model_name
        self.max_history_messages = max_history_messages

    def _build_messages(
        self, system_prompt: str, history: List[Dict[str, Any]], new_user_text: str
    ):
        msgs: List[Dict[str, Any]] = []
        # 1) system
        msgs.append(
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            }
        )
        # 2) (опционально) ограничим длину истории сообщениями с ролями user/assistant
        hist = history
        if (
            self.max_history_messages is not None
            and len(history) > self.max_history_messages
        ):
            hist = history[-self.max_history_messages :]

        for m in hist:
            if m.get("role") in {"user", "assistant"}:
                msgs.append(
                    {
                        "role": m["role"],
                        "content": [
                            {"type": "text", "text": str(m.get("content", ""))}
                        ],
                    }
                )

        # 3) новое сообщение пользователя
        msgs.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": new_user_text}],
            }
        )
        return msgs

    def chat(self, user_text: str, conversation_id: Optional[str] = None) -> ChatResult:
        conv_id = conversation_id or str(uuid.uuid4())
        system_prompt = self.prompt_loader.load()
        history = self.store.load(conv_id)

        msgs = self._build_messages(system_prompt, history, user_text)

        resp = self.client.responses.create(
            model=self.model_name,
            input=msgs,
        )
        assistant_text = resp.output_text
        response_id = getattr(resp, "id", None)

        # Логируем обе стороны
        user_msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "role": "user",
            "content": user_text,
            "ts": utcnow_iso(),
            "model": None,
            "response_id": None,
        }
        self.store.append(conv_id, user_msg)

        assistant_msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "role": "assistant",
            "content": assistant_text,
            "ts": utcnow_iso(),
            "model": self.model_name,
            "response_id": response_id,
        }
        self.store.append(conv_id, assistant_msg)

        return ChatResult(
            conversation_id=conv_id,
            assistant_text=assistant_text,
            response_id=response_id,
        )
