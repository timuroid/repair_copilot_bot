import os
from openai import OpenAI
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Подключение к OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден! Укажите его в .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# Загрузка промтов
def load_prompt(filename: str) -> str:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    prompt_path = os.path.join(base_dir, "../prompts", filename)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT_TEMPLATE = load_prompt("system_prompt.md")
HYPOTHESIS_SYSTEM_PROMPT = load_prompt("hypothesis_prompt.md")
SUMMARY_PROMPT_TEMPLATE = load_prompt("summary_prompt.md")

PROMPT_TEMPLATE = """


**История диалога:**
{history}

**Последнее сообщение пользователя:**
'{user_message}'   

🧩 **Гипотезы от второго генератора (для справки):**
{hypotheses}
"""

def generate_hypotheses(history: str, user_message: str) -> str:
    prompt = f"""
📂 **История диалога (контекст):**
{history}

👷 **Последнее сообщение пользователя:**
"{user_message}"

📌 ВАЖНО:
- Сначала определи, на каком этапе анализа сейчас находится диалог (технический, внешний, организационный или управленческий).
- Сгенерируй 10 разнообразных гипотез, которые соответствуют этому этапу.
- Гипотезы пиши кратко, с нребольшими пояснениями
"""

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
    prompt = PROMPT_TEMPLATE.format(history=formatted_history, user_message=user_message, hypotheses=hypotheses)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
    )
    return response.choices[0].message.content

def generate_summary(messages: list[tuple]) -> str:
    formatted_history = "\n".join([f"👷 {msg}\n🤖 {resp}" for (_, msg, resp, _, _) in messages])
    summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(messages=formatted_history)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": summary_prompt}],
    )
    return response.choices[0].message.content
