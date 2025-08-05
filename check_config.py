#!/usr/bin/env python3
"""
Скрипт для проверки настроек бота
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

print("🔍 Проверка настроек бота...")
print("-" * 50)

# Проверка наличия .env файла
env_file = Path(".env")
if env_file.exists():
    print("✅ Файл .env найден")
    print(f"   Путь: {env_file.absolute()}")
else:
    print("❌ Файл .env НЕ найден")
    print(f"   Ожидаемый путь: {env_file.absolute()}")

print("-" * 50)

# Проверка токена
token = os.getenv('BOT_TOKEN')
if token and token != 'YOUR_BOT_TOKEN_HERE':
    print("✅ Токен бота найден")
    print(f"   Токен: {token[:10]}...{token[-10:]}")  # Показываем только начало и конец
else:
    print("❌ Токен бота НЕ найден или не изменен")
    print("   Убедитесь, что в файле .env есть строка:")
    print("   BOT_TOKEN=ваш_токен_здесь")

print("-" * 50)

# Проверка админов
admin_ids = os.getenv('ADMIN_IDS', '')
if admin_ids:
    print("✅ ID администраторов найдены")
    print(f"   IDs: {admin_ids}")
else:
    print("⚠️  ID администраторов не указаны")
    print("   Добавьте в .env строку:")
    print("   ADMIN_IDS=ваш_telegram_id")

print("-" * 50)

# Проверка содержимого .env если файл существует
if env_file.exists():
    print("\n📄 Содержимое .env файла:")
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
        # Скрываем токен при выводе
        lines = content.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('#'):
                if 'BOT_TOKEN' in line and '=' in line:
                    key, value = line.split('=', 1)
                    if len(value) > 20:
                        print(f"{key}={value[:10]}...{value[-10:]}")
                    else:
                        print(line)
                else:
                    print(line)

print("\n" + "=" * 50)
print("💡 Подсказки:")
print("1. Убедитесь, что файл .env находится в корневой папке проекта")
print("2. Проверьте, что в .env нет пробелов вокруг знака =")
print("3. Токен должен быть без кавычек")
print("4. Пример правильного .env:")
print("   BOT_TOKEN=1234567890:ABCdefGHIjklmNOpqrsTUVwxyz")
print("   ADMIN_IDS=123456789")