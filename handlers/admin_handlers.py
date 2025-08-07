"""
handlers/admin_handlers.py
Админские хендлеры: приемка, цены, возвраты, отчеты, настройки
"""
import os
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.db import get_db_session
from data.models import Agent, Sale
from services.core_service import CoreService
from config import UPLOADS_DIR, CURRENCY_FORMAT, PERCENT_FORMAT
from utils.tools import create_sales_report, render_sales_timeseries_png, render_margin_by_category_png
from handlers import (
    BatchStates, PriceStates, ReturnStates, ChartStates,
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

    # Проверяем размер файла
    try:
        file_size = document.file_size or 0
    except Exception:
        file_size = 0

    from config import MAX_EXCEL_FILE_SIZE
    if file_size and file_size > MAX_EXCEL_FILE_SIZE:
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Файл слишком большой. Максимальный размер 10 MB",
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

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔍 Поиск по названию/EAN", callback_data="price_search_text")
    keyboard.button(text="📂 Фильтры (массово)", callback_data="price_search_filters")
    keyboard.button(text="📋 Все товары в наличии", callback_data="price_search_all")
    keyboard.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        get_back_button()
    )
    keyboard.adjust(1)

    await message.reply(
        "💳 <b>Установка розничной цены</b>\n\n"
        "Как будем выбирать товары?",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(PriceStates.choosing_filter)

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

# === РАСШИРЕННЫЙ ПОИСК ДЛЯ МАССОВОЙ УСТАНОВКИ ===
@router.callback_query(PriceStates.choosing_filter, F.data == "price_search_text")
async def price_search_text(callback: CallbackQuery, state: FSMContext):
    keyboard = get_cancel_back_keyboard()
    await callback.message.edit_text(
        "💳 <b>Установка розничной цены</b>\n\nВведите EAN или название товара:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PriceStates.waiting_for_product)
    await callback.answer()

@router.callback_query(PriceStates.choosing_filter, F.data == "price_search_filters")
async def price_search_filters(callback: CallbackQuery, state: FSMContext):
    """Меню фильтров как в продаже для массовой проставки цен"""
    keyboard = InlineKeyboardBuilder()
    with get_db_session() as db:
        available_data = CoreService.get_available_filter_values(db)

    if available_data['categories']:
        keyboard.button(text="🏒 По категории", callback_data="price_filter_category")
    if available_data['sizes']:
        keyboard.button(text="📏 По размеру", callback_data="price_filter_size")
    if available_data['ages']:
        keyboard.button(text="👥 По возрасту", callback_data="price_filter_age")
    if available_data['warehouses']:
        keyboard.button(text="📦 По складу", callback_data="price_filter_warehouse")
    if available_data['colors']:
        keyboard.button(text="🎨 По цвету", callback_data="price_filter_color")

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main"),
        get_back_button()
    )
    keyboard.adjust(2)

    await callback.message.edit_text(
        "📂 <b>Фильтры для массовой установки цен</b>\n\nВыберите критерий:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(PriceStates.choosing_filter, F.data == "price_search_all")
async def price_search_all(callback: CallbackQuery, state: FSMContext):
    """Выбрать все товары с наличием и показать массовые действия"""
    with get_db_session() as db:
        products = CoreService.select_products_for_bulk_pricing(db, only_in_stock=True, limit=None)
        product_ids = [p.id for p in products]

    if not product_ids:
        await callback.message.edit_text(
            "❌ Нет товаров в наличии",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]]),
        )
        await callback.answer()
        return

    await _show_bulk_actions(callback, state, product_ids)

def _render_bulk_price_preview(products, increase_percent: float | None, new_price: float | None) -> str:
    header = "🧮 <b>Массовая установка цен</b>\n\n"
    if increase_percent is not None:
        mode_line = f"Режим: повышение на {increase_percent}%\n"
    else:
        mode_line = f"Режим: установка фиксированной цены {CURRENCY_FORMAT.format(new_price or 0)}\n"
    count_line = f"Выбрано товаров: {len(products)} (показаны первые 10)\n\n"
    lines = []
    for p in products[:10]:
        old = p.retail_price or 0
        if increase_percent is not None:
            newp = round(old * (1 + increase_percent / 100), 2)
        else:
            newp = new_price or 0
        lines.append(f"• {p.name} ({p.size}) — {CURRENCY_FORMAT.format(old)} → {CURRENCY_FORMAT.format(newp)}")
    return header + mode_line + count_line + "\n".join(lines)

async def _show_bulk_actions(callback: CallbackQuery, state: FSMContext, product_ids: list[int]):
    await state.update_data(bulk_product_ids=product_ids)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="⬆️ Повысить на %", callback_data="bulk_price_percent")
    keyboard.button(text="💲 Установить фикс. цену", callback_data="bulk_price_fixed")
    keyboard.button(text="👀 Предпросмотр", callback_data="bulk_price_preview")
    keyboard.row(get_back_button())
    keyboard.adjust(2)
    await callback.message.edit_text(
        "🧮 <b>Массовая установка цен</b>\nВыберите режим:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("price_filter_"))
async def price_filters_select(callback: CallbackQuery, state: FSMContext):
    """Выбор по конкретному значению фильтра и показ действий"""
    data_key = callback.data.replace("price_filter_", "")
    with get_db_session() as db:
        # Загружаем конкретные значения
        if data_key == 'category':
            options = CoreService.get_product_categories_in_stock(db)
            items = sorted(options.keys())
        elif data_key == 'size':
            options = CoreService.get_available_sizes_in_stock(db)
            items = sorted(options.keys())
        elif data_key == 'age':
            options = CoreService.get_available_ages_in_stock(db)
            items = sorted(options.keys())
        elif data_key == 'warehouse':
            options = CoreService.get_warehouses_with_stock(db)
            items = sorted(options.keys())
        elif data_key == 'color':
            items = sorted(CoreService.get_available_filter_values(db)['colors'])
        else:
            items = []

    keyboard = InlineKeyboardBuilder()
    for value in items[:60]:  # ограничим список
        keyboard.button(text=str(value), callback_data=f"price_pick_{data_key}_{value}")
    keyboard.row(get_back_button())
    keyboard.adjust(2)
    await callback.message.edit_text(
        f"Выберите значение: ({data_key})",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("price_pick_"))
async def price_pick_apply(callback: CallbackQuery, state: FSMContext):
    """Применение фильтра и выбор режима массовой установки"""
    _, key, value = callback.data.split('_', 2)
    with get_db_session() as db:
        selected = CoreService.select_products_for_bulk_pricing(
            db,
            category=value if key == 'category' else None,
            size=value if key == 'size' else None,
            age=value if key == 'age' else None,
            warehouse=value if key == 'warehouse' else None,
            color=value if key == 'color' else None,
        )
        product_ids = [p.id for p in selected]

    await _show_bulk_actions(callback, state, product_ids)

@router.callback_query(F.data == "bulk_price_percent")
async def bulk_price_percent(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PriceStates.bulk_percent_input)
    keyboard = get_cancel_back_keyboard()
    await callback.message.edit_text(
        "Введите процент повышения (например, 5 или 7.5)",
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(PriceStates.bulk_percent_input)
async def bulk_price_percent_input(message: Message, state: FSMContext):
    try:
        inc = float(message.text.replace(',', '.'))
    except ValueError:
        await message.reply("❌ Введите число, например 5 или 7.5", reply_markup=get_cancel_back_keyboard())
        return

    data = await state.get_data()
    product_ids = data.get('bulk_product_ids', [])
    if not product_ids:
        await message.reply("❌ Не выбраны товары", reply_markup=get_cancel_back_keyboard())
        return

    with get_db_session() as db:
        # Сохраняем выбранный режим для предпросмотра/подтверждения
        await state.update_data(bulk_inc_percent=inc, bulk_fixed_price=None)
        changed = CoreService.bulk_update_retail_price_by_ids(
            db, product_ids, increase_percent=inc, changed_by_id=message.from_user.id
        )

    await state.clear()
    await message.reply(
        f"✅ Изменено цен у {changed} товаров (повышение на {inc}%)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    )

@router.callback_query(F.data == "bulk_price_fixed")
async def bulk_price_fixed(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PriceStates.bulk_fixed_input)
    keyboard = get_cancel_back_keyboard()
    await callback.message.edit_text(
        "Введите новую фиксированную цену (руб.)",
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(PriceStates.bulk_fixed_input)
async def bulk_price_fixed_input(message: Message, state: FSMContext):
    try:
        new_price = float(message.text.replace(',', '.'))
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await message.reply("❌ Введите корректную цену (число > 0)", reply_markup=get_cancel_back_keyboard())
        return

    data = await state.get_data()
    product_ids = data.get('bulk_product_ids', [])
    if not product_ids:
        await message.reply("❌ Не выбраны товары", reply_markup=get_cancel_back_keyboard())
        return

    with get_db_session() as db:
        await state.update_data(bulk_inc_percent=None, bulk_fixed_price=new_price)
        changed = CoreService.bulk_update_retail_price_by_ids(
            db, product_ids, new_price=new_price, changed_by_id=message.from_user.id
        )

    await state.clear()
    await message.reply(
        f"✅ Установлена цена {CURRENCY_FORMAT.format(new_price)} у {changed} товаров",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    )

@router.callback_query(F.data == "bulk_price_preview")
async def bulk_price_preview(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_ids = data.get('bulk_product_ids', [])
    inc = data.get('bulk_inc_percent')
    fixed = data.get('bulk_fixed_price')

    if not product_ids:
        await callback.answer("Нет выбранных товаров", show_alert=True)
        return

    if inc is None and fixed is None:
        # Если режим не выбран — попросим сначала указать процент или цену
        await callback.answer("Сначала выберите режим (процент или фикс. цену)", show_alert=True)
        return

    with get_db_session() as db:
        preview = CoreService.preview_bulk_price_update(
            db, product_ids,
            new_price=fixed, increase_percent=inc, limit=20
        )

    if not preview:
        await callback.message.edit_text("Нет данных для предпросмотра", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]]))
        await callback.answer()
        return

    # Формируем текст предпросмотра
    lines = ["👀 <b>Предпросмотр изменений цен</b>", "", "Товар — старая → новая (Δ%)", ""]
    for item in preview:
        lines.append(
            f"• {item['name']} ({item['size'] or '-'}): "
            f"{CURRENCY_FORMAT.format(item['old'])} → {CURRENCY_FORMAT.format(item['new'])} "
            f"({item['diff_percent']}%)"
        )
    text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="bulk_price_apply")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        [get_back_button()]
    ])

    await state.set_state(PriceStates.bulk_preview_confirm)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@router.callback_query(PriceStates.bulk_preview_confirm, F.data == "bulk_price_apply")
async def bulk_price_apply(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_ids = data.get('bulk_product_ids', [])
    inc = data.get('bulk_inc_percent')
    fixed = data.get('bulk_fixed_price')

    if not product_ids:
        await callback.answer("Нет выбранных товаров", show_alert=True)
        return

    with get_db_session() as db:
        changed = CoreService.bulk_update_retail_price_by_ids(
            db, product_ids, new_price=fixed, increase_percent=inc, changed_by_id=callback.from_user.id
        )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Применено к {changed} товарам",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    )
    await callback.answer()


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
        sale = db.get(Sale, sale_id)

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

# === ГРАФИКИ (админ) ===
@router.message(F.text == "📈 Графики")
async def charts_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Эта функция доступна только администраторам")
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Продажи: 7 дней", callback_data="chart_sales_7")
    kb.button(text="📈 Продажи: 30 дней", callback_data="chart_sales_30")
    kb.button(text="📈 Продажи: 90 дней", callback_data="chart_sales_90")
    kb.button(text="📊 Категории: 30 дней", callback_data="chart_margin_cats_30")
    kb.button(text="📊 Категории: 90 дней", callback_data="chart_margin_cats_90")
    kb.button(text="🏷 По товару (РРЦ/продажи)", callback_data="chart_product_pick")
    kb.row(get_back_button())
    kb.adjust(1)
    await message.reply("📈 <b>Графики</b>\nВыберите график:", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.in_(["chart_sales_7", "chart_sales_30", "chart_sales_90"]))
async def chart_sales_period(callback: CallbackQuery):
    mapping = {"chart_sales_7": 7, "chart_sales_30": 30, "chart_sales_90": 90}
    days = mapping.get(callback.data, 30)
    with get_db_session() as db:
        points = CoreService.get_sales_timeseries(db, days=days)
    if not points:
        await callback.message.edit_text("Нет данных для графика", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]]))
        await callback.answer()
        return
    png = render_sales_timeseries_png(points)
    await callback.message.answer_photo(types.BufferedInputFile(png, filename=f"sales_{days}.png"), caption=f"Продажи за {days} дней")
    await callback.answer()

@router.callback_query(F.data.in_(["chart_margin_cats_30", "chart_margin_cats_90"]))
async def chart_margin_cats_period(callback: CallbackQuery):
    mapping = {"chart_margin_cats_30": 30, "chart_margin_cats_90": 90}
    days = mapping.get(callback.data, 30)
    with get_db_session() as db:
        cat_map = CoreService.get_margin_by_category(db, days=days)
    if not cat_map:
        await callback.message.edit_text("Нет данных для графика", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]]))
        await callback.answer()
        return
    png = render_margin_by_category_png(cat_map)
    await callback.message.answer_photo(types.BufferedInputFile(png, filename=f"margin_cats_{days}.png"), caption=f"Маржа по категориям ({days} дней)")
    await callback.answer()

@router.callback_query(F.data == "chart_product_pick")
async def chart_product_pick(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChartStates.waiting_for_product_query)
    await callback.message.edit_text(
        "Введите EAN или название товара для построения графика (90 дней):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_back_button()]])
    )
    await callback.answer()

@router.message(StateFilter(ChartStates.waiting_for_product_query), F.text)
async def chart_product_query(message: Message, state: FSMContext):
    query = message.text
    with get_db_session() as db:
        items = CoreService.search_products(db, query)
    if not items:
        await message.reply("Товары не найдены. Попробуйте другой запрос.")
        return
    # Берём первый совпавший для простоты
    product = items[0]['product']
    pid = product.id
    with get_db_session() as db:
        price_ts = CoreService.get_product_price_timeseries(db, pid, days=90)
        sales_ts = CoreService.get_product_sales_timeseries(db, pid, days=90)
    from utils.tools import render_dual_axis_price_sales_png
    png = render_dual_axis_price_sales_png(price_ts, sales_ts)
    await message.answer_photo(
        types.BufferedInputFile(png, filename=f"product_{pid}_90.png"),
        caption=f"{product.name} — РРЦ и продажи (90 дней)"
    )
    await state.clear()

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