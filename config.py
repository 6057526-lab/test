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
    error_message = (
        "⚠️  ВНИМАНИЕ: Необходимо указать токен бота!\n"
        "📝 Варианты настройки токена:\n"
        "   1. Создайте файл .env и добавьте: BOT_TOKEN=ваш_токен_здесь\n"
        "   2. Или замените 'YOUR_BOT_TOKEN_HERE' прямо в config.py\n"
        "   3. Или установите переменную окружения: export BOT_TOKEN=ваш_токен\n\n"
        "🤖 Как получить токен:\n"
        "   1. Найдите @BotFather в Telegram\n"
        "   2. Отправьте /newbot\n"
        "   3. Следуйте инструкциям\n"
        "   4. Скопируйте токен вида: 1234567890:ABCdefGHIjklmNOpqrsTUVwxyz"
    )
    raise ValueError(error_message)

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
# Получаем из переменной окружения или используем пустый список
admin_ids_env = os.getenv('ADMIN_IDS', '')
if admin_ids_env:
    ADMIN_IDS = [int(id.strip()) for id in admin_ids_env.split(',') if id.strip().isdigit()]
else:
    ADMIN_IDS = [
        # 123456789,  # Добавьте сюда ID администраторов
    ]

# Предупреждение если нет админов
if not ADMIN_IDS:
    import warnings
    warnings.warn(
        "⚠️  ВНИМАНИЕ: Не указаны ID администраторов! "
        "Добавьте их в переменную ADMIN_IDS в config.py или в .env файл",
        UserWarning
    )

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