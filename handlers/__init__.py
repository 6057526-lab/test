"""
handlers/__init__.py
Общие функции, состояния FSM и регистрация всех хендлеров
"""
from aiogram import Dispatcher
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from config import ADMIN_IDS

# Импорт модулей с хендлерами будет после определения классов

# === СОСТОЯНИЯ FSM ===
class BatchStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_warehouse = State()

class PriceStates(StatesGroup):
    waiting_for_product = State()
    waiting_for_price = State()

class SaleStates(StatesGroup):
    waiting_for_product = State()
    waiting_for_price = State()
    confirm_sale = State()
    # Новые состояния для фильтров
    choosing_filter = State()
    filter_by_category = State()
    filter_by_size = State()
    filter_by_age = State()
    filter_by_warehouse = State()

class StockStates(StatesGroup):
    waiting_for_filters = State()

class ReturnStates(StatesGroup):
    waiting_for_sale_id = State()
    waiting_for_reason = State()

class BonusStates(StatesGroup):
    waiting_for_confirmation = State()

# === ОБЩИЕ ФУНКЦИИ ===
def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def get_back_button() -> InlineKeyboardButton:
    """Универсальная кнопка "Назад" """
    return InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")

def get_cancel_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопками Отмена и Назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
        ]
    ])

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура администратора"""
    keyboard = [
        [KeyboardButton(text="📅 Приемка партии"), KeyboardButton(text="💳 Установить цены")],
        [KeyboardButton(text="🚀 Продажа"), KeyboardButton(text="📦 Остатки")],
        [KeyboardButton(text="🎁 Бонусы"), KeyboardButton(text="📊 Отчёты")],
        [KeyboardButton(text="↩️ Возврат"), KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_seller_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура продавца"""
    keyboard = [
        [KeyboardButton(text="🚀 Продать"), KeyboardButton(text="📦 Мои остатки")],
        [KeyboardButton(text="🎁 Мой бонус"), KeyboardButton(text="📈 История продаж")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def show_main_menu(message_or_callback, is_admin_user: bool = None):
    """Показать главное меню"""
    if isinstance(message_or_callback, CallbackQuery):
        user_id = message_or_callback.from_user.id
        username = message_or_callback.from_user.username
        full_name = message_or_callback.from_user.full_name

        # Определяем права если не переданы
        if is_admin_user is None:
            is_admin_user = is_admin(user_id)

        keyboard = get_admin_keyboard() if is_admin_user else get_seller_keyboard()
        role = "администратор" if is_admin_user else "продавец"

        await message_or_callback.message.edit_text(
            f"👋 {full_name}!\n"
            f"Вы вошли как <b>{role}</b>.\n\n"
            "Выберите действие из меню:",
            parse_mode="HTML"
        )
        # Отправляем новое сообщение с клавиатурой
        await message_or_callback.message.answer(
            "📱 Выберите действие:",
            reply_markup=keyboard
        )
        await message_or_callback.answer()
    else:
        # Обычное сообщение
        user_id = message_or_callback.from_user.id
        if is_admin_user is None:
            is_admin_user = is_admin(user_id)

        keyboard = get_admin_keyboard() if is_admin_user else get_seller_keyboard()
        role = "администратор" if is_admin_user else "продавец"

        await message_or_callback.reply(
            f"👋 {message_or_callback.from_user.full_name}!\n"
            f"Вы вошли как <b>{role}</b>.\n\n"
            "Выберите действие из меню:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

# === РЕГИСТРАЦИЯ ВСЕХ ХЕНДЛЕРОВ ===
def register_all_handlers(dp: Dispatcher):
    """Регистрация всех хендлеров"""
    # Импортируем здесь, чтобы избежать циклических импортов
    from . import admin_handlers, sales_handlers, user_handlers

    user_handlers.register_handlers(dp)      # Основные: старт, меню, навигация
    sales_handlers.register_handlers(dp)     # Продажи, остатки (общие)
    admin_handlers.register_handlers(dp)     # Админские функции