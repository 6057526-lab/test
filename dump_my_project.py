from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path.cwd()
DUMPS_DIR = PROJECT_DIR / "code_dumps"
TODAY_DIR = DUMPS_DIR / datetime.now().strftime("%Y-%m-%d")
TODAY_DIR.mkdir(parents=True, exist_ok=True)

# Файлы и категории
FILES_TO_DUMP = {
    "00_main_and_config.md": [
        "main.py", "config.py", "check_config.py", "migrate_db.py"
    ],
    "01_data.md": [
        "data/db.py", "data/models.py"
    ],
    "02_handlers.md": [
        "handlers/handlers.py"
    ],
    "03_services.md": [
        "services/core_service.py"
    ],
    "04_utils.md": [
        "utils/tools.py"
    ]
}

def dump_files_to_md():
    for md_name, file_list in FILES_TO_DUMP.items():
        out_path = TODAY_DIR / md_name
        with open(out_path, "w", encoding="utf-8") as out_file:
            out_file.write(f"# 📦 {md_name}\n\n")
            for rel_path_str in file_list:
                rel_path = Path(rel_path_str)
                full_path = PROJECT_DIR / rel_path
                if not full_path.exists():
                    out_file.write(f"\n⚠️ Файл не найден: {rel_path}\n")
                    continue
                out_file.write(f"\n## {rel_path}\n")
                out_file.write("```python\n")
                out_file.write(full_path.read_text(encoding="utf-8"))
                out_file.write("\n```\n")
    print(f"✅ Дамп завершён. Проверь папку: {TODAY_DIR}")

if __name__ == "__main__":
    dump_files_to_md()
