import sys
from pathlib import Path

from openai import OpenAI

from app.config import OPENAI_API_KEY, OUT_PATH, PROMPT_PATH


def main() -> int:
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Не найден файл промпта: {PROMPT_PATH}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=OPENAI_API_KEY)  # ключ OPENAI_API_KEY

    try:
        resp = client.responses.create(
            model="gpt-5-mini",
            input=prompt,
        )
        text = resp.output_text  # удобное свойство Responses API
    except Exception as e:
        print(f"Ошибка обращения к OpenAI API: {e}", file=sys.stderr)
        return 2

    # Вывод в консоль
    print(text)

    # Дублирование в Markdown-файл
    try:
        OUT_PATH.write_text(text, encoding="utf-8")
    except Exception as e:
        print(f"Не удалось записать {OUT_PATH}: {e}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
