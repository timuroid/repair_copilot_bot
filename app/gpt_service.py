"""Stateless GPT service utilities.

Exposes helpers to update a JSON hypothesis tree, generate a user-facing reply,
and produce a final summary. No server-side state: all inputs are passed in.
"""

from __future__ import annotations

import os
import re
import json
from typing import Any, Dict, List
from openai import OpenAI
from dotenv import load_dotenv
from prompts.prompt_loader import (
    MAIN_SYSTEM_PROMPT,
    HYPOTHESIS_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    MAIN_PROMPT,
    HYPOTHESIS_PROMPT,
)

# Load env (expects Yandex Cloud OpenAI-compatible settings)
load_dotenv()

YC_API_KEY = os.getenv("YC_API_KEY")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID")
YC_BASE_URL = os.getenv("YC_BASE_URL", "https://llm.api.cloud.yandex.net/v1")
YC_MODEL = os.getenv("YC_MODEL", "quen")  # base model name; full path is built below

if not YC_API_KEY:
    raise ValueError("Не найден YC_API_KEY (IAM) в окружении")
if not YC_FOLDER_ID:
    raise ValueError("Не найден YC_FOLDER_ID в окружении")

# Compose full model identifier like: gpt://<FOLDER_ID>/<MODEL>/latest
YC_MODEL_FULL = f"gpt://{YC_FOLDER_ID}/{YC_MODEL}/latest"

client = OpenAI(api_key=YC_API_KEY, base_url=YC_BASE_URL)


def _format_history(history: List[Dict[str, str]]) -> str:
    """Render list of message pairs {user, bot} into a compact text block.

    history: [{"user": "...", "bot": "..."}, ...]
    """
    chunks: List[str] = []
    for pair in history or []:
        user = (pair.get("user") or "").strip()
        bot = (pair.get("bot") or "").strip()
        if user or bot:
            chunks.append(f"Пользователь: {user}\nАссистент: {bot}")
    return "\n".join(chunks)


def extract_json_from_response(response_text: str) -> str:
    """Extract JSON payload from ```json fenced block, fallback to raw text."""
    match = re.search(r"```json\n(.*?)\n```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()


def _ensure_tree_dict(tree: Any) -> Dict[str, Any]:
    if isinstance(tree, dict):
        return tree
    return {}


def generate_hypotheses(user_message: str, chat_history: List[Dict[str, str]], tree: Any) -> Dict[str, Any]:
    """Return updated hypothesis tree based on history + new message.

    Args:
        user_message: Current user input.
        chat_history: List of message pairs [{user, bot}].
        tree: Current hypothesis tree (dict or None).
    """
    current_tree = _ensure_tree_dict(tree)

    prompt = HYPOTHESIS_PROMPT.format(
        history=_format_history(chat_history),
        user_message=user_message,
        tree=json.dumps(current_tree, ensure_ascii=False, separators=(",", ":")),
    )

    response = client.chat.completions.create(
        model=YC_MODEL_FULL,
        messages=[
            {"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        stream=False,
    )

    raw_content = (response.choices[0].message.content or "").strip()
    try:
        cleaned_json = extract_json_from_response(raw_content)
        new_tree = json.loads(cleaned_json)
        if isinstance(new_tree, dict):
            return new_tree
        # If model returned a list or other type, keep previous
        return current_tree
    except json.JSONDecodeError:
        # Keep previous tree on parse error
        return current_tree


def generate_response(history: List[Dict[str, str]], user_message: str, tree: Any) -> str:
    """Generate assistant reply using history and the hypothesis tree."""
    formatted_history = _format_history(history)
    safe_tree = _ensure_tree_dict(tree)

    prompt = MAIN_PROMPT.format(
        history=formatted_history,
        user_message=user_message,
        tree=json.dumps(safe_tree, ensure_ascii=False, separators=(",", ":")),
    )

    response = client.chat.completions.create(
        model=YC_MODEL_FULL,
        messages=[
            {"role": "system", "content": MAIN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        stream=False,
    )
    return response.choices[0].message.content or ""


def generate_summary(history: List[Dict[str, str]]) -> str:
    """Summarize the dialog history."""
    formatted_history = _format_history(history)
    summary_prompt = SUMMARY_SYSTEM_PROMPT.format(messages=formatted_history)

    response = client.chat.completions.create(
        model=YC_MODEL_FULL,
        messages=[{"role": "system", "content": summary_prompt}],
        stream=False,
    )
    return response.choices[0].message.content or ""
