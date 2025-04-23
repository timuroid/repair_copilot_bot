from openai import OpenAI
from dotenv import load_dotenv
from prompts.prompt_loader import (
    MAIN_SYSTEM_PROMPT,
    HYPOTHESIS_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    MAIN_PROMPT,
    HYPOTHESIS_PROMPT
)

import os

# Загрузка переменных окружения
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден!")

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_hypotheses(formatted_history: str, user_message: str) -> str:
    
    prompt = HYPOTHESIS_PROMPT.format(history=formatted_history, user_message=user_message)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
    )

    return response.choices[0].message.content.strip()

def generate_response(user_id: int, history: list[tuple[str, str]], user_message: str) -> str:
    formatted_history = "\n".join([f"👷 {msg}\n🤖 {resp}" for msg, resp in history])
    hypotheses = generate_hypotheses(formatted_history, user_message)
    prompt = MAIN_PROMPT.format(history=formatted_history, user_message=user_message, hypotheses=hypotheses)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": MAIN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
    )
    return response.choices[0].message.content

def generate_summary(messages: list[tuple]) -> str:
    formatted_history = "\n".join([f"👷 {msg}\n🤖 {resp}" for (_, msg, resp, _, _) in messages])
    summary_prompt = SUMMARY_SYSTEM_PROMPT.format(messages=formatted_history)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": summary_prompt}],
    )
    return response.choices[0].message.content
