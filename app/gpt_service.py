import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv
from prompts.prompt_loader import (
    MAIN_SYSTEM_PROMPT,
    HYPOTHESIS_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    MAIN_PROMPT,
    HYPOTHESIS_PROMPT
)

# ===== In-Memory =====
user_trees = {}  # user_id: dict

# Загрузка переменных окружения
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден!")

client = OpenAI(api_key=OPENAI_API_KEY)

def _format_history(history: list[tuple[str, str]]) -> str:
    return "\n".join([f"👷 {msg}\n🤖 {resp}" for msg, resp in history])

def extract_json_from_response(response_text: str) -> str:
    match = re.search(r"```json\n(.*?)\n```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()

# ===== Работа с деревом =====

def get_tree(user_id: int) -> dict:
    return user_trees.get(user_id, {})

def set_tree(user_id: int, new_tree: dict):
    user_trees[user_id] = new_tree

def clear_tree(user_id: int):
    user_trees[user_id] = {}  # просто пустое

# ===== Основной функционал =====

def generate_hypotheses(user_id: int, user_message: str, chat_history: list[tuple[str, str]]) -> dict:
    current_tree = get_tree(user_id)

    prompt = HYPOTHESIS_PROMPT.format(
        history=_format_history(chat_history),
        user_message=user_message,
        tree=json.dumps(current_tree, ensure_ascii=False,  separators=(",", ":"))
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[
            {"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    raw_content = response.choices[0].message.content.strip()
    try:
        cleaned_json = extract_json_from_response(raw_content)
        new_tree = json.loads(cleaned_json)
        set_tree(user_id, new_tree)
        return new_tree
    except json.JSONDecodeError:
        print("❌ Ошибка: JSON невалиден. Старое дерево сохраняется.")
        return current_tree

def generate_response(user_id: int, history: list[tuple[str, str]], user_message: str) -> str:
    formatted_history = _format_history(history)
    tree = get_tree(user_id)

    prompt = MAIN_PROMPT.format(
        history=formatted_history,
        user_message=user_message,
        tree=json.dumps(tree, ensure_ascii=False,  separators=(",", ":"))
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[
            {"role": "system", "content": MAIN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content

def generate_summary(history: list[tuple[str, str]]) -> str:
    formatted_history = _format_history(history)
    summary_prompt = SUMMARY_SYSTEM_PROMPT.format(messages=formatted_history)

    response = client.chat.completions.create(
        model="o4-mini-2025-04-16",
        messages=[{"role": "system", "content": summary_prompt}],
    )
    return response.choices[0].message.content
