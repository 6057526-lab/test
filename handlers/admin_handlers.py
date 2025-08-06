"""
handlers/admin_handlers.py
Админские хендлеры: приемка, цены, возвраты, отчеты, настройки
"""
import os
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.db import get_db_session
from data.models import Agent, Sale
from services.core_service import CoreService
from config import UPLOADS_DIR, CURRENCY_FORMAT, PERCENT_FORMAT
from utils.tools import create_sales_report
from handlers import (
    BatchStates, PriceStates, ReturnStates,
    is_admin, get_cancel_back_keyboard, get_back_button
)

router = Router()

# === ПРИЕМКА ПАРТИЙ ===
@router.message(F.text == "📅 Приемка партии")
async def batch_start(message: Message, state: FSMContext):
    """Начало приемки партии"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Скачать шаблон Excel", callback_data="download_template")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
         get_back_button()]
    ])

    await message.reply(
        "📅 <b>Приемка новой партии</b>\n\n"
        "Загрузите Excel файл с товарами или скачайте шаблон:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(BatchStates.waiting_for_file)

@router.callback_query(F.data == "download_template")
async def download_template(callback: CallbackQuery):
    """Скачать шаблон Excel"""
    with get_db_session() as db:
        template_bytes = CoreService.generate_excel_template()

    file_name = f"template_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    await callback.message.answer_document(
        types.BufferedInputFile(
            template_bytes,
            filename=file_name
        ),
        caption="📄 Шаблон для загрузки товаров"
    )
    await callback.answer()

@router.message(BatchStates.waiting_for_file, F.document)
async def process_batch_file(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    document = message.document

    if not document.file_name.endswith(('.xlsx', '.xls')):
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Пожалуйста, загрузите Excel файл (.xlsx или .xls)",
            reply_markup=keyboard
        )
        return

    # Скачиваем файл
    file_path = os.path.join(UPLOADS_DIR, f"{message.from_user.id}_{document.file_name}")
    await message.bot.download(document, file_path)

    await state.update_data(file_path=file_path)

    # Получаем список складов из БД или конфига
    with get_db_session() as db:
        existing_warehouses = CoreService.get_warehouse_list(db)

    # Добавляем предустановленные склады из конфига
    from config import DEFAULT_WAREHOUSES
    all_warehouses = list(set(existing_warehouses + DEFAULT_WAREHOUSES))

    keyboard = InlineKeyboardBuilder()
    for warehouse in all_warehouses:
        keyboard.button(text=warehouse, callback_data=f"warehouse_{warehouse}")
    keyboard.button(text="➕ Новый склад", callback_data="warehouse_new")
    keyboard.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        get_back_button()
    )
    keyboard.adjust(2)

    await message.reply(
        "📦 Выберите склад для партии:",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(BatchStates.waiting_for_warehouse)

@router.callback_query(BatchStates.waiting_for_warehouse, F.data.startswith("warehouse_"))
async def process_warehouse_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора склада"""
    warehouse = callback.data.replace("warehouse_", "")
    data = await state.get_data()
    file_path = data['file_path']

    try:
        with get_db_session() as db:
            batch, products = CoreService.create_batch_from_excel(
                db, file_path, warehouse, callback.from_user.id
            )
            # Сохраняем нужные данные до закрытия сессии
            batch_number = batch.batch_number
            batch_date = batch.received_date.strftime('%d.%m.%Y %H:%M')
            products_count = len(products)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"✅ <b>Партия успешно создана!</b>\n\n"
            f"📋 Номер партии: {batch_number}\n"
            f"📦 Склад: {warehouse}\n"
            f"📊 Количество товаров: {products_count}\n"
            f"📅 Дата: {batch_date}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # Удаляем временный файл
        os.remove(file_path)

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"❌ Ошибка при создании партии:\n{str(e)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    await state.clear()
    await callback.answer()

# === УСТАНОВКА ЦЕН ===
@router.message(F.text == "💳 Установить цены")
async def price_start(message: Message, state: FSMContext):
    """Начало установки цен"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = get_cancel_back_keyboard()

    await message.reply(
        "💳 <b>Установка розничной цены</b>\n\n"
        "Введите EAN или название товара для поиска:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PriceStates.waiting_for_product)

@router.message(PriceStates.waiting_for_product)
async def search_product_for_price(message: Message, state: FSMContext):
    """Поиск товара для установки цены"""
    query = message.text

    with get_db_session() as db:
        products_data = CoreService.search_products(db, query)

    if not products_data:
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Товары не найдены. Попробуйте другой запрос.",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardBuilder()
    for item in products_data[:10]:  # Показываем максимум 10
        product = item['product']
        text = f"{product.name} ({product.size}) - {product.ean}"
        keyboard.button(text=text, callback_data=f"setprice_{product.id}")
    keyboard.adjust(1)
    keyboard.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search_price"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        get_back_button()
    )

    await message.reply(
        "📋 Найденные товары:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "new_search_price")
async def new_search_price(callback: CallbackQuery, state: FSMContext):
    """Новый поиск товара для установки цены"""
    keyboard = get_cancel_back_keyboard()

    await callback.message.edit_text(
        "💳 <b>Установка розничной цены</b>\n\n"
        "Введите EAN или название товара для поиска:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PriceStates.waiting_for_product)
    await callback.answer()

@router.callback_query(F.data.startswith("setprice_"))
async def select_product_for_price(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для установки цены"""
    product_id = int(callback.data.replace("setprice_", ""))

    with get_db_session() as db:
        info = CoreService.get_product_info(db, product_id)
        product = info['product']

    await state.update_data(product_id=product_id)

    keyboard = get_cancel_back_keyboard()

    await callback.message.edit_text(
        f"<b>Товар:</b> {product.name}\n"
        f"<b>Размер:</b> {product.size}\n"
        f"<b>Себестоимость:</b> {CURRENCY_FORMAT.format(product.cost_price)}\n"
        f"<b>Текущая РРЦ:</b> {CURRENCY_FORMAT.format(product.retail_price or 0)}\n\n"
        f"Введите новую розничную цену в рублях:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PriceStates.waiting_for_price)
    await callback.answer()

@router.message(PriceStates.waiting_for_price)
async def set_new_price(message: Message, state: FSMContext):
    """Установка новой цены"""
    try:
        price = float(message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError("Цена должна быть больше 0")
    except ValueError:
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Введите корректную цену (число больше 0)",
            reply_markup=keyboard
        )
        return

    data = await state.get_data()
    product_id = data['product_id']

    with get_db_session() as db:
        product = CoreService.set_retail_price(db, product_id, price, message.from_user.id)
        margin = product.margin
        margin_percent = product.margin_percent

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [get_back_button()]
    ])

    await message.reply(
        f"✅ <b>Цена установлена!</b>\n\n"
        f"<b>Новая РРЦ:</b> {CURRENCY_FORMAT.format(price)}\n"
        f"<b>Маржа:</b> {CURRENCY_FORMAT.format(margin)}\n"
        f"<b>Маржинальность:</b> {PERCENT_FORMAT.format(margin_percent)}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.clear()

# === ВОЗВРАТЫ ===
@router.message(F.text == "↩️ Возврат")
async def return_start(message: Message, state: FSMContext):
    """Начало оформления возврата"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = get_cancel_back_keyboard()

    await message.reply(
        "↩️ <b>Оформление возврата</b>\n\n"
        "Введите ID продажи для возврата:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(ReturnStates.waiting_for_sale_id)

@router.message(ReturnStates.waiting_for_sale_id)
async def return_sale_id(message: Message, state: FSMContext):
    """Ввод ID продажи"""
    try:
        sale_id = int(message.text)
    except ValueError:
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Введите корректный ID продажи (число)",
            reply_markup=keyboard
        )
        return

    with get_db_session() as db:
        sale = db.query(Sale).get(sale_id)

        if not sale:
            keyboard = get_cancel_back_keyboard()
            await message.reply(
                "❌ Продажа не найдена",
                reply_markup=keyboard
            )
            return

        if sale.is_returned:
            keyboard = get_cancel_back_keyboard()
            await message.reply(
                "❌ Эта продажа уже возвращена",
                reply_markup=keyboard
            )
            return

        await state.update_data(sale_id=sale_id)

        text = (
            f"<b>Информация о продаже:</b>\n\n"
            f"<b>ID:</b> {sale.id}\n"
            f"<b>Товар:</b> {sale.product.name} ({sale.product.size})\n"
            f"<b>Продавец:</b> {sale.agent.full_name}\n"
            f"<b>Цена:</b> {CURRENCY_FORMAT.format(sale.sale_price)}\n"
            f"<b>Дата:</b> {sale.sale_date.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Введите причину возврата:"
        )

    keyboard = get_cancel_back_keyboard()

    await message.reply(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(ReturnStates.waiting_for_reason)

@router.message(ReturnStates.waiting_for_reason)
async def return_reason(message: Message, state: FSMContext):
    """Ввод причины возврата"""
    reason = message.text
    data = await state.get_data()
    sale_id = data['sale_id']

    try:
        with get_db_session() as db:
            sale = CoreService.return_sale(db, sale_id, reason, message.from_user.id)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await message.reply(
            f"✅ <b>Возврат оформлен!</b>\n\n"
            f"<b>Товар:</b> {sale.product.name}\n"
            f"<b>Возвращен на склад:</b> {sale.warehouse}\n"
            f"<b>Причина:</b> {reason}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await message.reply(
            f"❌ Ошибка при оформлении возврата:\n{str(e)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    await state.clear()

# === ОТЧЕТЫ ===
@router.message(F.text == "📊 Отчёты")
async def reports_menu(message: Message):
    """Меню отчетов"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📈 Продажи за сегодня", callback_data="report_sales_today")
    keyboard.button(text="📊 Продажи за неделю", callback_data="report_sales_week")
    keyboard.button(text="📅 Продажи за месяц", callback_data="report_sales_month")
    keyboard.button(text="👥 По продавцам", callback_data="report_by_agents")
    keyboard.row(get_back_button())
    keyboard.adjust(2)

    await message.reply(
        "📊 <b>Отчеты</b>\n\n"
        "Выберите тип отчета:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("report_"))
async def generate_report(callback: CallbackQuery):
    """Генерация отчета"""
    report_type = callback.data.replace("report_", "")

    # Определяем период
    end_date = datetime.now()
    if report_type == "sales_today":
        start_date = end_date.replace(hour=0, minute=0, second=0)
        period_name = "сегодня"
    elif report_type == "sales_week":
        start_date = end_date - timedelta(days=7)
        period_name = "за неделю"
    elif report_type == "sales_month":
        start_date = end_date - timedelta(days=30)
        period_name = "за месяц"
    else:
        start_date = None
        period_name = "весь период"

    with get_db_session() as db:
        report = CoreService.get_sales_report(db, start_date, end_date)

    # Формируем текст отчета
    text = create_sales_report(report, period_name)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=callback.data)],
        [get_back_button()]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

# === НАСТРОЙКИ ===
@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    """Меню настроек"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👥 Управление пользователями", callback_data="manage_users")
    keyboard.button(text="💰 Настройки бонусов", callback_data="manage_bonus_rules")
    keyboard.button(text="📊 Экспорт данных", callback_data="export_data")
    keyboard.button(text="🗑️ Очистка логов", callback_data="clear_logs")
    keyboard.row(get_back_button())
    keyboard.adjust(2)

    await message.reply(
        "⚙️ <b>Настройки системы</b>\n\n"
        "Выберите раздел:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "manage_users")
async def manage_users(callback: CallbackQuery):
    """Управление пользователями"""
    with get_db_session() as db:
        agents = db.query(Agent).all()

    keyboard = InlineKeyboardBuilder()
    for agent in agents[:10]:  # Показываем первых 10
        status = "✅" if agent.is_active else "❌"
        role = "👑" if agent.is_admin else "👤"
        keyboard.button(
            text=f"{status} {role} {agent.full_name}",
            callback_data=f"user_{agent.id}"
        )
    keyboard.row(get_back_button())
    keyboard.adjust(1)

    text = "👥 <b>Управление пользователями</b>\n\n"
    text += f"Всего пользователей: {len(agents)}\n"
    text += f"Активных: {sum(1 for a in agents if a.is_active)}\n"
    text += f"Администраторов: {sum(1 for a in agents if a.is_admin)}\n\n"
    text += "Выберите пользователя:"

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# Заглушки для остальных функций настроек
@router.callback_query(F.data == "manage_bonus_rules")
async def manage_bonus_rules(callback: CallbackQuery):
    """Настройки бонусов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    await callback.message.edit_text(
        "💰 <b>Настройки бонусов</b>\n\n🚧 В разработке...",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "export_data")
async def export_data(callback: CallbackQuery):
    """Экспорт данных"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    await callback.message.edit_text(
        "📊 <b>Экспорт данных</b>\n\n🚧 В разработке...",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "clear_logs")
async def clear_logs(callback: CallbackQuery):
    """Очистка логов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    await callback.message.edit_text(
        "🗑️ <b>Очистка логов</b>\n\n🚧 В разработке...",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

def register_handlers(dp):
    """Регистрация админских хендлеров"""
    dp.include_router(router)