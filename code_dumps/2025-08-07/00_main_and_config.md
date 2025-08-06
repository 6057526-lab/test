# 📦 00_main_and_config.md


## main.py
```python
#!/usr/bin/env python3
"""
Главный файл для запуска Telegram-бота учёта хоккейной экипировки
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import TOKEN
from data.db import init_db
from handlers import register_all_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция запуска бота"""
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    init_db()

    # Создание бота и диспетчера
    bot = Bot(token=TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация хендлеров
    logger.info("Регистрация хендлеров...")
    register_all_handlers(dp)  # ← Исправлено: было register_handlers(dp)

    # Запуск бота
    try:
        logger.info("Бот запущен и готов к работе!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
```

## config.py
```python
"""
Конфигурационный файл для Telegram-бота учёта хоккейной экипировки
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env файла
# Сначала ищем в текущей папке, потом в родительской
env_path = Path('.env')
if not env_path.exists():
    env_path = Path('../.env')

load_dotenv(env_path)

# Токен бота (замените на ваш реальный токен)
# Получаем из переменной окружения или используем значение по умолчанию
TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Проверка токена
if TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("⚠️  ВНИМАНИЕ: Необходимо указать токен бота!")
    print("📝 Варианты настройки токена:")
    print("   1. Создайте файл .env и добавьте: BOT_TOKEN=ваш_токен_здесь")
    print("   2. Или замените 'YOUR_BOT_TOKEN_HERE' прямо в config.py")
    print("   3. Или установите переменную окружения: export BOT_TOKEN=ваш_токен")
    print("\n🤖 Как получить токен:")
    print("   1. Найдите @BotFather в Telegram")
    print("   2. Отправьте /newbot")
    print("   3. Следуйте инструкциям")
    print("   4. Скопируйте токен вида: 1234567890:ABCdefGHIjklmNOpqrsTUVwxyz")
    exit(1)

# Пути
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'db.sqlite3'
UPLOADS_DIR = BASE_DIR / 'uploads'

# Создаем директории если их нет
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# База данных
DATABASE_URL = f'sqlite:///{DB_PATH}'

# ID администраторов (Telegram ID)
# Получаем из переменной окружения или используем пустой список
admin_ids_env = os.getenv('ADMIN_IDS', '')
if admin_ids_env:
    ADMIN_IDS = [int(id.strip()) for id in admin_ids_env.split(',') if id.strip().isdigit()]
else:
    ADMIN_IDS = [
        # 123456789,  # Добавьте сюда ID администраторов
    ]

# Предупреждение если нет админов
if not ADMIN_IDS:
    print("⚠️  ВНИМАНИЕ: Не указаны ID администраторов!")
    print("   Добавьте их в переменную ADMIN_IDS в config.py или в .env файл")

# Настройки для расчётов
DEFAULT_CURRENCY = 'EUR'
DEFAULT_COEFFICIENT = 1.2  # Коэффициент по умолчанию

# Типы фита
FIT_TYPES = ['regular', 'tapered', 'wide']

# Размеры
SIZES = ['YTH', 'JR', 'INT', 'SR', 'XS', 'S', 'M', 'L', 'XL', '2XL', '3XL']

# Возрастные категории
AGE_CATEGORIES = ['YTH', 'JR', 'INT', 'SR']

# Шаблон Excel для загрузки
EXCEL_TEMPLATE_COLUMNS = [
    'EAN', 'Наименование', 'Модель', 'Цвет', 'Размер',
    'Возраст', 'Фит', 'Вес', 'Кол-во', 'Цена в евро',
    'Курс', 'Коэффициент', 'Логистика (на кг)', 'Склад'
]

# Склады по умолчанию
DEFAULT_WAREHOUSES = ['Олег', 'Максим', 'Общий']

# Настройки бонусной программы по умолчанию
DEFAULT_BONUS_RULES = [
    {'min_amount': 0, 'max_amount': 50000, 'percent': 5},
    {'min_amount': 50000, 'max_amount': 100000, 'percent': 7},
    {'min_amount': 100000, 'max_amount': 200000, 'percent': 10},
    {'min_amount': 200000, 'max_amount': float('inf'), 'percent': 12},
]

# Форматирование
CURRENCY_FORMAT = '{:,.2f} ₽'
PERCENT_FORMAT = '{:.1f}%'

# Лимиты
MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_PRODUCTS_PER_BATCH = 1000

# Логирование
LOG_ACTIONS = True  # Логировать все действия в action_log
```

## check_config.py
```python
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
```

## migrate_db.py
```python
#!/usr/bin/env python3
"""
Скрипт для миграции существующей БД
"""
import sqlite3
from pathlib import Path
from data.db import DATABASE_URL, init_db


def migrate_database():
    """Добавляет уникальное ограничение на EAN в рамках партии"""

    # Путь к БД
    db_path = DATABASE_URL.replace('sqlite:///', '')

    if not Path(db_path).exists():
        print("❌ БД не найдена. Создаем новую...")
        init_db()
        return

    print("🔧 Начинаем миграцию БД...")

    # Подключаемся к БД
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем, есть ли уже такое ограничение
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)
        table_sql = cursor.fetchone()[0]

        if 'unique_ean_per_batch' not in table_sql:
            print("📝 Добавляем уникальное ограничение на EAN в рамках партии...")

            # SQLite не поддерживает ALTER TABLE ADD CONSTRAINT
            # Поэтому создаем новую таблицу с ограничением

            # 1. Переименовываем старую таблицу
            cursor.execute("ALTER TABLE products RENAME TO products_old")

            # 2. Создаем новую таблицу с ограничением
            cursor.execute("""
                CREATE TABLE products (
                    id INTEGER NOT NULL PRIMARY KEY,
                    ean VARCHAR(13) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    model VARCHAR(100),
                    color VARCHAR(50),
                    size VARCHAR(20),
                    age VARCHAR(20),
                    fit VARCHAR(20),
                    weight FLOAT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price_eur FLOAT NOT NULL,
                    exchange_rate FLOAT NOT NULL,
                    coefficient FLOAT NOT NULL,
                    logistics_per_kg FLOAT NOT NULL,
                    cost_price FLOAT NOT NULL,
                    retail_price FLOAT,
                    batch_id INTEGER NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES batches (id),
                    CONSTRAINT unique_ean_per_batch UNIQUE (ean, batch_id),
                    CONSTRAINT check_quantity_positive CHECK (quantity >= 0),
                    CONSTRAINT check_price_positive CHECK (price_eur >= 0),
                    CONSTRAINT check_weight_positive CHECK (weight > 0),
                    CONSTRAINT check_fit_type CHECK (fit IN ('regular', 'tapered', 'wide'))
                )
            """)

            # 3. Копируем данные
            cursor.execute("""
                INSERT INTO products SELECT * FROM products_old
            """)

            # 4. Удаляем старую таблицу
            cursor.execute("DROP TABLE products_old")

            # 5. Создаем индекс на EAN для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_products_ean ON products (ean)")

            print("✅ Ограничение добавлено успешно!")
        else:
            print("✅ Ограничение уже существует")

        # Проверяем и исправляем дубликаты EAN в существующих партиях
        cursor.execute("""
            SELECT ean, batch_id, COUNT(*) as cnt 
            FROM products 
            GROUP BY ean, batch_id 
            HAVING cnt > 1
        """)

        duplicates = cursor.fetchall()
        if duplicates:
            print(f"⚠️  Найдено {len(duplicates)} дубликатов EAN в партиях")
            for ean, batch_id, count in duplicates:
                print(f"   EAN: {ean}, Партия: {batch_id}, Количество: {count}")

            # Здесь можно добавить логику для обработки дубликатов
            # Например, объединение количества или удаление

        conn.commit()
        print("✅ Миграция завершена успешно!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка при миграции: {e}")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
```
