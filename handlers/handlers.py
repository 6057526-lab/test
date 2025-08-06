"""
Обработчики команд для Telegram бота
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Dispatcher, F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.db import get_db_session
from data.models import Agent, Sale
from services.core_service import CoreService
from config import ADMIN_IDS, UPLOADS_DIR, CURRENCY_FORMAT, PERCENT_FORMAT
from utils.tools import format_number, format_product_info, create_sales_report


# Состояния FSM
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


class StockStates(StatesGroup):
    waiting_for_filters = State()


class ReturnStates(StatesGroup):
    waiting_for_sale_id = State()
    waiting_for_reason = State()


# Роутер
router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь администратором"""
    return user_id in ADMIN_IDS


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


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    with get_db_session() as db:
        agent = CoreService.get_or_create_agent(db, user_id, username, full_name)

        if is_admin(user_id):
            agent.is_admin = True
            db.commit()
            keyboard = get_admin_keyboard()
            role = "администратор"
        else:
            keyboard = get_seller_keyboard()
            role = "продавец"

    await message.reply(
        f"👋 Привет, {full_name}!\n"
        f"Вы вошли как <b>{role}</b>.\n\n"
        "Выберите действие из меню:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# === ПРИЕМКА ПАРТИИ ===
@router.message(F.text == "📅 Приемка партии")
async def batch_start(message: Message, state: FSMContext):
    """Начало приемки партии"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Скачать шаблон Excel", callback_data="download_template")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
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
        await message.reply("❌ Пожалуйста, загрузите Excel файл (.xlsx или .xls)")
        return

    # Скачиваем файл
    file_path = os.path.join(UPLOADS_DIR, f"{message.from_user.id}_{document.file_name}")
    await message.bot.download(document, file_path)

    # Сохраняем путь к файлу
    await state.update_data(file_path=file_path)

    # Запрашиваем склад
    warehouses = ["Олег", "Максим", "Общий"]
    keyboard = InlineKeyboardBuilder()
    for warehouse in warehouses:
        keyboard.button(text=warehouse, callback_data=f"warehouse_{warehouse}")
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

        await callback.message.edit_text(
            f"✅ <b>Партия успешно создана!</b>\n\n"
            f"📋 Номер партии: {batch_number}\n"
            f"📦 Склад: {warehouse}\n"
            f"📊 Количество товаров: {products_count}\n"
            f"📅 Дата: {batch_date}",
            parse_mode="HTML"
        )

        # Удаляем временный файл
        os.remove(file_path)

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при создании партии:\n{str(e)}",
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

    await message.reply(
        "💳 <b>Установка розничной цены</b>\n\n"
        "Введите EAN или название товара для поиска:",
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
        await message.reply("❌ Товары не найдены. Попробуйте другой запрос.")
        return

    keyboard = InlineKeyboardBuilder()
    for item in products_data[:10]:  # Показываем максимум 10
        product = item['product']
        text = f"{product.name} ({product.size}) - {product.ean}"
        keyboard.button(text=text, callback_data=f"setprice_{product.id}")
    keyboard.adjust(1)
    keyboard.button(text="❌ Отмена", callback_data="cancel")

    await message.reply(
        "📋 Найденные товары:",
        reply_markup=keyboard.as_markup()
    )


@router.callback_query(F.data.startswith("setprice_"))
async def select_product_for_price(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для установки цены"""
    product_id = int(callback.data.replace("setprice_", ""))

    with get_db_session() as db:
        info = CoreService.get_product_info(db, product_id)
        product = info['product']

    await state.update_data(product_id=product_id)

    await callback.message.edit_text(
        f"<b>Товар:</b> {product.name}\n"
        f"<b>Размер:</b> {product.size}\n"
        f"<b>Себестоимость:</b> {CURRENCY_FORMAT.format(product.cost_price)}\n"
        f"<b>Текущая РРЦ:</b> {CURRENCY_FORMAT.format(product.retail_price or 0)}\n\n"
        f"Введите новую розничную цену в рублях:",
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
        await message.reply("❌ Введите корректную цену (число больше 0)")
        return

    data = await state.get_data()
    product_id = data['product_id']

    with get_db_session() as db:
        product = CoreService.set_retail_price(db, product_id, price, message.from_user.id)

        margin = product.margin
        margin_percent = product.margin_percent

    await message.reply(
        f"✅ <b>Цена установлена!</b>\n\n"
        f"<b>Новая РРЦ:</b> {CURRENCY_FORMAT.format(price)}\n"
        f"<b>Маржа:</b> {CURRENCY_FORMAT.format(margin)}\n"
        f"<b>Маржинальность:</b> {PERCENT_FORMAT.format(margin_percent)}",
        parse_mode="HTML"
    )
    await state.clear()


# === ПРОДАЖИ ===
@router.message(F.text.in_(["🚀 Продажа", "🚀 Продать"]))
async def sale_start(message: Message, state: FSMContext):
    """Начало процесса продажи"""
    await message.reply(
        "🚀 <b>Оформление продажи</b>\n\n"
        "Введите EAN или название товара:",
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.waiting_for_product)


@router.message(SaleStates.waiting_for_product)
async def search_product_for_sale(message: Message, state: FSMContext):
    """Поиск товара для продажи"""
    query = message.text

    with get_db_session() as db:
        products_data = CoreService.search_products(db, query)

    if not products_data:
        await message.reply("❌ Товары не найдены. Попробуйте другой запрос.")
        return

    keyboard = InlineKeyboardBuilder()
    has_products = False

    for item in products_data[:10]:
        if item['current_stock'] > 0:
            product = item['product']
            text = f"{product.name} ({product.size}) - Остаток: {item['current_stock']}"
            keyboard.button(text=text, callback_data=f"sell_{product.id}")
            has_products = True

    if not has_products:
        await message.reply("❌ Нет товаров в наличии по вашему запросу")
        return

    keyboard.adjust(1)
    keyboard.button(text="❌ Отмена", callback_data="cancel")

    await message.reply(
        "📋 Выберите товар для продажи:",
        reply_markup=keyboard.as_markup()
    )


@router.callback_query(F.data.startswith("sell_"))
async def select_product_for_sale(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для продажи"""
    product_id = int(callback.data.replace("sell_", ""))

    with get_db_session() as db:
        info = CoreService.get_product_info(db, product_id)
        product = info['product']
        current_stock = info['current_stock']  # Используем уже вычисленный остаток

    await state.update_data(product_id=product_id, product=product, current_stock=current_stock)

    price_text = CURRENCY_FORMAT.format(product.retail_price) if product.retail_price else "не установлена"

    await callback.message.edit_text(
        f"<b>Товар:</b> {product.name}\n"
        f"<b>Размер:</b> {product.size}\n"
        f"<b>Остаток:</b> {current_stock} шт.\n"
        f"<b>РРЦ:</b> {price_text}\n\n"
        f"Введите цену продажи в рублях:",
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.waiting_for_price)
    await callback.answer()


@router.message(SaleStates.waiting_for_price)
async def set_sale_price(message: Message, state: FSMContext):
    """Ввод цены продажи"""
    try:
        price = float(message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError("Цена должна быть больше 0")
    except ValueError:
        await message.reply("❌ Введите корректную цену (число больше 0)")
        return

    data = await state.get_data()
    product = data['product']

    # Рассчитываем маржу
    margin = price - product.cost_price
    margin_percent = (margin / price * 100) if price > 0 else 0

    await state.update_data(sale_price=price)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_sale"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ])

    await message.reply(
        f"<b>Подтверждение продажи:</b>\n\n"
        f"<b>Товар:</b> {product.name} ({product.size})\n"
        f"<b>Цена продажи:</b> {CURRENCY_FORMAT.format(price)}\n"
        f"<b>Себестоимость:</b> {CURRENCY_FORMAT.format(product.cost_price)}\n"
        f"<b>Маржа:</b> {CURRENCY_FORMAT.format(margin)}\n"
        f"<b>Маржинальность:</b> {PERCENT_FORMAT.format(margin_percent)}\n\n"
        f"Подтвердить продажу?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.confirm_sale)


@router.callback_query(SaleStates.confirm_sale, F.data == "confirm_sale")
async def confirm_sale(callback: CallbackQuery, state: FSMContext):
    """Подтверждение продажи"""
    data = await state.get_data()

    try:
        with get_db_session() as db:
            sale = CoreService.create_sale(
                db,
                product_id=data['product_id'],
                agent_id=callback.from_user.id,
                sale_price=data['sale_price']
            )

            # Сохраняем нужные данные до закрытия сессии
            product_name = sale.product.name
            sale_price = sale.sale_price
            sale_margin = sale.margin

            # Получаем информацию о бонусе
            bonus = sale.bonus
            bonus_info = None
            if bonus:
                bonus_info = {
                    'amount': bonus.amount,
                    'percent': bonus.percent_used
                }

        # Формируем сообщение вне сессии
        text = (
            f"✅ <b>Продажа оформлена!</b>\n\n"
            f"<b>Товар:</b> {product_name}\n"
            f"<b>Цена:</b> {CURRENCY_FORMAT.format(sale_price)}\n"
            f"<b>Маржа:</b> {CURRENCY_FORMAT.format(sale_margin)}"
        )

        if bonus_info:
            text += f"\n<b>Бонус:</b> {CURRENCY_FORMAT.format(bonus_info['amount'])} ({bonus_info['percent']}%)"

        await callback.message.edit_text(text, parse_mode="HTML")

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при оформлении продажи:\n{str(e)}",
            parse_mode="HTML"
        )

    await state.clear()
    await callback.answer()


# === ОСТАТКИ ===
@router.message(F.text.in_(["📦 Остатки", "📦 Мои остатки"]))
async def stock_view(message: Message):
    """Просмотр остатков"""
    is_admin_user = is_admin(message.from_user.id)

    keyboard = InlineKeyboardBuilder()

    if is_admin_user:
        # Для админа - выбор склада
        with get_db_session() as db:
            warehouses = CoreService.get_warehouse_list(db)

        for warehouse in warehouses:
            keyboard.button(text=f"📦 {warehouse}", callback_data=f"stock_wh_{warehouse}")
        keyboard.button(text="📊 Все склады", callback_data="stock_wh_all")
    else:
        # Для продавца - показываем все доступные остатки
        keyboard.button(text="📊 Показать остатки", callback_data="stock_wh_all")

    keyboard.adjust(2)

    await message.reply(
        "📦 <b>Просмотр остатков</b>\n\n"
        "Выберите склад:" if is_admin_user else "📦 <b>Доступные остатки</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("stock_wh_"))
async def show_stock(callback: CallbackQuery):
    """Показать остатки по складу"""
    warehouse = callback.data.replace("stock_wh_", "")
    warehouse = None if warehouse == "all" else warehouse

    with get_db_session() as db:
        stock = CoreService.get_stock(db, warehouse=warehouse)

    if not stock:
        await callback.message.edit_text("📦 Нет товаров в наличии")
        await callback.answer()
        return

    # Формируем сообщение с остатками
    text = f"📦 <b>Остатки{f' на складе {warehouse}' if warehouse else ' (все склады)'}</b>\n\n"

    for i, item in enumerate(stock[:20], 1):  # Показываем первые 20
        text += (
            f"{i}. <b>{item['name']}</b>\n"
            f"   Размер: {item['size']}, Цвет: {item['color']}\n"
            f"   Остаток: {item['stock']} шт.\n"
            f"   РРЦ: {CURRENCY_FORMAT.format(item['retail_price'] or 0)}\n"
            f"   Склад: {item['warehouse']}\n\n"
        )

    if len(stock) > 20:
        text += f"\n<i>Показаны первые 20 из {len(stock)} товаров</i>"

    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


# === БОНУСЫ ===
@router.message(F.text.in_(["🎁 Бонусы", "🎁 Мой бонус"]))
async def bonus_view(message: Message):
    """Просмотр бонусов"""
    user_id = message.from_user.id
    is_admin_user = is_admin(user_id)

    if is_admin_user:
        # Админ видит всех агентов
        with get_db_session() as db:
            agents = db.query(Agent).filter(Agent.is_active == True).all()

        keyboard = InlineKeyboardBuilder()
        for agent in agents:
            if agent.telegram_id != user_id:  # Исключаем самого админа
                keyboard.button(
                    text=f"👤 {agent.full_name}",
                    callback_data=f"bonus_agent_{agent.id}"
                )
        keyboard.adjust(2)

        await message.reply(
            "🎁 <b>Управление бонусами</b>\n\n"
            "Выберите продавца:",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
    else:
        # Продавец видит свои бонусы
        with get_db_session() as db:
            agent = CoreService.get_or_create_agent(db, user_id)
            bonuses = CoreService.get_agent_bonuses(db, agent.id)

            total_unpaid = sum(b.amount for b in bonuses if not b.is_paid)
            total_paid = sum(b.amount for b in bonuses if b.is_paid)

            text = (
                f"🎁 <b>Ваши бонусы</b>\n\n"
                f"<b>К выплате:</b> {CURRENCY_FORMAT.format(total_unpaid)}\n"
                f"<b>Выплачено всего:</b> {CURRENCY_FORMAT.format(total_paid)}\n\n"
                f"<b>Последние операции:</b>\n"
            )

            for bonus in bonuses[:10]:
                status = "✅ Выплачено" if bonus.is_paid else "⏳ Ожидает"
                text += (
                    f"\n{status} {CURRENCY_FORMAT.format(bonus.amount)} "
                    f"({bonus.percent_used}%) - {bonus.created_at.strftime('%d.%m.%Y')}"
                )

        await message.reply(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("bonus_agent_"))
async def show_agent_bonuses(callback: CallbackQuery):
    """Показать бонусы агента (для админа)"""
    agent_id = int(callback.data.replace("bonus_agent_", ""))

    with get_db_session() as db:
        agent = db.query(Agent).get(agent_id)
        bonuses = CoreService.get_agent_bonuses(db, agent_id)

        total_unpaid = sum(b.amount for b in bonuses if not b.is_paid)
        total_paid = sum(b.amount for b in bonuses if b.is_paid)

    keyboard = InlineKeyboardBuilder()
    if total_unpaid > 0:
        keyboard.button(
            text=f"💰 Выплатить {CURRENCY_FORMAT.format(total_unpaid)}",
            callback_data=f"pay_bonus_{agent_id}"
        )
    keyboard.button(text="◀️ Назад", callback_data="back_to_agents")

    text = (
        f"🎁 <b>Бонусы продавца {agent.full_name}</b>\n\n"
        f"<b>К выплате:</b> {CURRENCY_FORMAT.format(total_unpaid)}\n"
        f"<b>Выплачено всего:</b> {CURRENCY_FORMAT.format(total_paid)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_bonus_"))
async def pay_agent_bonus(callback: CallbackQuery):
    """Выплатить бонус агенту"""
    agent_id = int(callback.data.replace("pay_bonus_", ""))

    with get_db_session() as db:
        amount = CoreService.pay_bonuses(db, agent_id, callback.from_user.id)
        agent = db.query(Agent).get(agent_id)

    await callback.message.edit_text(
        f"✅ <b>Бонусы выплачены!</b>\n\n"
        f"<b>Продавец:</b> {agent.full_name}\n"
        f"<b>Сумма:</b> {CURRENCY_FORMAT.format(amount)}",
        parse_mode="HTML"
    )
    await callback.answer()


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

    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


# === ИСТОРИЯ ПРОДАЖ ===
@router.message(F.text == "📈 История продаж")
async def sales_history(message: Message):
    """История продаж продавца"""
    with get_db_session() as db:
        agent = CoreService.get_or_create_agent(db, message.from_user.id)
        sales = CoreService.get_agent_sales_history(db, agent.id, days=30)

        if not sales:
            text = "📈 <b>История продаж</b>\n\nУ вас пока нет продаж."
        else:
            text = "📈 <b>История продаж за 30 дней</b>\n\n"

            for i, sale in enumerate(sales[:20], 1):
                status = "❌ Возврат" if sale.is_returned else "✅"
                text += (
                    f"{i}. {status} {sale.product.name} ({sale.product.size})\n"
                    f"   Цена: {CURRENCY_FORMAT.format(sale.sale_price)}\n"
                    f"   Маржа: {CURRENCY_FORMAT.format(sale.margin)}\n"
                    f"   Дата: {sale.sale_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                )

            if len(sales) > 20:
                text += f"\n<i>Показаны первые 20 из {len(sales)} продаж</i>"

    await message.reply(text, parse_mode="HTML")


# === ВОЗВРАТЫ ===
@router.message(F.text == "↩️ Возврат")
async def return_start(message: Message, state: FSMContext):
    """Начало оформления возврата"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return

    await message.reply(
        "↩️ <b>Оформление возврата</b>\n\n"
        "Введите ID продажи для возврата:",
        parse_mode="HTML"
    )
    await state.set_state(ReturnStates.waiting_for_sale_id)


@router.message(ReturnStates.waiting_for_sale_id)
async def return_sale_id(message: Message, state: FSMContext):
    """Ввод ID продажи"""
    try:
        sale_id = int(message.text)
    except ValueError:
        await message.reply("❌ Введите корректный ID продажи (число)")
        return

    with get_db_session() as db:
        sale = db.query(Sale).get(sale_id)

        if not sale:
            await message.reply("❌ Продажа не найдена")
            return

        if sale.is_returned:
            await message.reply("❌ Эта продажа уже возвращена")
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

    await message.reply(text, parse_mode="HTML")
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

        await message.reply(
            f"✅ <b>Возврат оформлен!</b>\n\n"
            f"<b>Товар:</b> {sale.product.name}\n"
            f"<b>Возвращен на склад:</b> {sale.warehouse}\n"
            f"<b>Причина:</b> {reason}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.reply(
            f"❌ Ошибка при оформлении возврата:\n{str(e)}",
            parse_mode="HTML"
        )

    await state.clear()


# === ОБЩИЕ ОБРАБОТЧИКИ ===
@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены"""
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена")
    await callback.answer()


@router.callback_query(F.data == "back_to_agents")
async def back_to_agents(callback: CallbackQuery):
    """Вернуться к списку агентов"""
    await bonus_view(callback.message)
    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрация всех хендлеров"""
    dp.include_router(router)