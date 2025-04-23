import os

def load_prompt(filename: str) -> str:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    prompt_path = os.path.join(base_dir, "prompts_list", filename)  # 👈 тут путь
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()
    

# Заранее загружаем нужные шаблоны
MAIN_SYSTEM_PROMPT = load_prompt("MAIN_SYSTEM_PROMPT.md")
HYPOTHESIS_SYSTEM_PROMPT = load_prompt("HYPOTHESIS_SYSTEM_PROMPT.md")
SUMMARY_SYSTEM_PROMPT = load_prompt("SUMMARY_SYSTEM_PROMPT.md")
MAIN_PROMPT = load_prompt("MAIN_PROMPT.md")
HYPOTHESIS_PROMPT = load_prompt("HYPOTHESIS_PROMPT.md")