"""
handlers/sales_handlers.py
Продажи и остатки - функции доступные и админам и продавцам
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.db import get_db_session
from services.core_service import CoreService
from config import CURRENCY_FORMAT, PERCENT_FORMAT
from handlers import (
    SaleStates, is_admin, get_cancel_back_keyboard,
    get_back_button
)

router = Router()

# === ПРОДАЖИ С УЛУЧШЕННЫМИ ФИЛЬТРАМИ ===
@router.message(F.text.in_(["🚀 Продажа", "🚀 Продать"]))
async def sale_start(message: Message, state: FSMContext):
    """Начало процесса продажи с выбором способа поиска"""
    keyboard = InlineKeyboardBuilder()

    # Основные способы поиска
    keyboard.button(text="🔍 Поиск по названию/EAN", callback_data="search_text")
    keyboard.button(text="📂 Фильтры", callback_data="search_filters")
    keyboard.button(text="📋 Все товары в наличии", callback_data="search_all")

    keyboard.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        get_back_button()
    )
    keyboard.adjust(1)

    await message.reply(
        "🚀 <b>Оформление продажи</b>\n\n"
        "Как будем искать товар?",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.choosing_filter)

@router.callback_query(SaleStates.choosing_filter, F.data == "search_text")
async def search_by_text(callback: CallbackQuery, state: FSMContext):
    """Поиск по тексту - старый способ"""
    keyboard = get_cancel_back_keyboard()

    await callback.message.edit_text(
        "🔍 <b>Поиск товара</b>\n\n"
        "Введите EAN или название товара:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.waiting_for_product)
    await callback.answer()

@router.callback_query(SaleStates.choosing_filter, F.data == "search_filters")
async def show_filters_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню фильтров"""
    keyboard = InlineKeyboardBuilder()

    # Получаем доступные значения для фильтров
    with get_db_session() as db:
        available_data = CoreService.get_available_filter_values(db)

    # Кнопки фильтров
    if available_data['categories']:
        keyboard.button(text="🏒 По категории товара", callback_data="filter_category")
    if available_data['sizes']:
        keyboard.button(text="📏 По размеру", callback_data="filter_size")
    if available_data['ages']:
        keyboard.button(text="👥 По возрасту", callback_data="filter_age")
    if available_data['warehouses']:
        keyboard.button(text="📦 По складу", callback_data="filter_warehouse")
    if available_data['colors']:
        keyboard.button(text="🎨 По цвету", callback_data="filter_color")

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад к поиску", callback_data="back_to_search"),
        get_back_button()
    )
    keyboard.adjust(2)

    await callback.message.edit_text(
        "📂 <b>Фильтрация товаров</b>\n\n"
        "Выберите способ фильтрации:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_search")
async def back_to_search(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору способа поиска"""
    await sale_start(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "filter_category")
async def filter_by_category(callback: CallbackQuery, state: FSMContext):
    """Фильтр по категории товара"""
    with get_db_session() as db:
        categories = CoreService.get_product_categories_in_stock(db)

    keyboard = InlineKeyboardBuilder()
    for category, count in categories.items():
        keyboard.button(
            text=f"{category} ({count})",
            callback_data=f"cat_{category[:20]}"
        )

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="search_filters"),
        get_back_button()
    )
    keyboard.adjust(2)

    await callback.message.edit_text(
        "🏒 <b>Выберите категорию товара:</b>\n\n"
        "<i>Показаны только категории с товарами в наличии</i>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.filter_by_category)
    await callback.answer()

@router.callback_query(F.data == "filter_size")
async def filter_by_size(callback: CallbackQuery, state: FSMContext):
    """Фильтр по размеру"""
    with get_db_session() as db:
        sizes = CoreService.get_available_sizes_in_stock(db)

    keyboard = InlineKeyboardBuilder()
    for size, count in sizes.items():
        keyboard.button(
            text=f"{size} ({count})",
            callback_data=f"size_{size}"
        )

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="search_filters"),
        get_back_button()
    )
    keyboard.adjust(3)

    await callback.message.edit_text(
        "📏 <b>Выберите размер:</b>\n\n"
        "<i>Показаны только размеры с товарами в наличии</i>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.filter_by_size)
    await callback.answer()

@router.callback_query(F.data == "filter_age")
async def filter_by_age(callback: CallbackQuery, state: FSMContext):
    """Фильтр по возрастной группе"""
    with get_db_session() as db:
        ages = CoreService.get_available_ages_in_stock(db)

    keyboard = InlineKeyboardBuilder()
    age_names = {
        'YTH': 'Детский',
        'JR': 'Юниорский',
        'INT': 'Промежуточный',
        'SR': 'Взрослый'
    }

    for age, count in ages.items():
        display_name = age_names.get(age, age)
        keyboard.button(
            text=f"{display_name} ({count})",
            callback_data=f"age_{age}"
        )

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="search_filters"),
        get_back_button()
    )
    keyboard.adjust(2)

    await callback.message.edit_text(
        "👥 <b>Выберите возрастную группу:</b>\n\n"
        "<i>Показаны только группы с товарами в наличии</i>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.filter_by_age)
    await callback.answer()

@router.callback_query(F.data == "filter_warehouse")
async def filter_by_warehouse(callback: CallbackQuery, state: FSMContext):
    """Фильтр по складу"""
    with get_db_session() as db:
        warehouses = CoreService.get_warehouses_with_stock(db)

    keyboard = InlineKeyboardBuilder()
    for warehouse, count in warehouses.items():
        keyboard.button(
            text=f"📦 {warehouse} ({count})",
            callback_data=f"wh_{warehouse[:15]}"
        )

    keyboard.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="search_filters"),
        get_back_button()
    )
    keyboard.adjust(2)

    await callback.message.edit_text(
        "📦 <b>Выберите склад:</b>\n\n"
        "<i>Показаны только склады с товарами в наличии</i>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.filter_by_warehouse)
    await callback.answer()

# === ОБРАБОТКА РЕЗУЛЬТАТОВ ФИЛЬТРОВ ===
@router.callback_query(SaleStates.filter_by_category, F.data.startswith("cat_"))
async def show_products_by_category(callback: CallbackQuery, state: FSMContext):
    """Показать товары по выбранной категории"""
    category = callback.data.replace("cat_", "")

    with get_db_session() as db:
        products_data = CoreService.get_products_by_category(db, category)

    await show_filtered_products(callback, state, products_data, f"категории '{category}'")

@router.callback_query(SaleStates.filter_by_size, F.data.startswith("size_"))
async def show_products_by_size(callback: CallbackQuery, state: FSMContext):
    """Показать товары по размеру"""
    size = callback.data.replace("size_", "")

    with get_db_session() as db:
        products_data = CoreService.get_products_by_size(db, size)

    await show_filtered_products(callback, state, products_data, f"размеру '{size}'")

@router.callback_query(SaleStates.filter_by_age, F.data.startswith("age_"))
async def show_products_by_age(callback: CallbackQuery, state: FSMContext):
    """Показать товары по возрасту"""
    age = callback.data.replace("age_", "")

    with get_db_session() as db:
        products_data = CoreService.get_products_by_age(db, age)

    age_names = {'YTH': 'Детский', 'JR': 'Юниорский', 'INT': 'Промежуточный', 'SR': 'Взрослый'}
    display_name = age_names.get(age, age)

    await show_filtered_products(callback, state, products_data, f"возрасту '{display_name}'")

@router.callback_query(SaleStates.filter_by_warehouse, F.data.startswith("wh_"))
async def show_products_by_warehouse(callback: CallbackQuery, state: FSMContext):
    """Показать товары по складу"""
    warehouse = callback.data.replace("wh_", "")

    with get_db_session() as db:
        products_data = CoreService.get_products_by_warehouse(db, warehouse)

    await show_filtered_products(callback, state, products_data, f"складу '{warehouse}'")

@router.callback_query(SaleStates.choosing_filter, F.data == "search_all")
async def show_all_products(callback: CallbackQuery, state: FSMContext):
    """Показать все товары в наличии"""
    with get_db_session() as db:
        products_data = CoreService.get_all_products_in_stock(db)

    await show_filtered_products(callback, state, products_data, "всем товарам в наличии")

async def show_filtered_products(callback: CallbackQuery, state: FSMContext,
                                products_data: list, filter_description: str):
    """Универсальная функция показа отфильтрованных товаров"""
    if not products_data:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к фильтрам", callback_data="search_filters")],
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"❌ Нет товаров в наличии по {filter_description}",
            reply_markup=keyboard
        )
        await callback.answer()
        return

    # Пагинация - показываем по 8 товаров на страницу
    page_size = 8
    total_pages = (len(products_data) + page_size - 1) // page_size
    current_page = 0

    await state.update_data(
        filtered_products=products_data,
        current_page=current_page,
        total_pages=total_pages,
        filter_description=filter_description
    )

    await show_products_page(callback, state, current_page)

async def show_products_page(callback: CallbackQuery, state: FSMContext, page: int):
    """Показать страницу с товарами"""
    data = await state.get_data()
    products_data = data['filtered_products']
    total_pages = data['total_pages']
    filter_description = data['filter_description']

    page_size = 8
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(products_data))
    page_products = products_data[start_idx:end_idx]

    keyboard = InlineKeyboardBuilder()

    # Товары
    for item in page_products:
        product = item['product']
        stock = item['current_stock']
        price_info = f" - {CURRENCY_FORMAT.format(product.retail_price)}" if product.retail_price else ""

        text = f"{product.name} ({product.size}){price_info} | {stock} шт."
        keyboard.button(text=text, callback_data=f"sell_{product.id}")

    keyboard.adjust(1)

    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"page_{page+1}"))

    if nav_buttons:
        keyboard.row(*nav_buttons)

    # Кнопки управления
    keyboard.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="back_to_search"),
        InlineKeyboardButton(text="📂 Фильтры", callback_data="search_filters")
    )
    keyboard.row(get_back_button())

    text = (
        f"📋 <b>Товары по {filter_description}</b>\n\n"
        f"Страница {page + 1} из {total_pages}\n"
        f"Показано {len(page_products)} из {len(products_data)} товаров\n\n"
        "Выберите товар для продажи:"
    )

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("page_"))
async def navigate_pages(callback: CallbackQuery, state: FSMContext):
    """Навигация по страницам"""
    page = int(callback.data.replace("page_", ""))
    await show_products_page(callback, state, page)

# === СТАРЫЙ ПОИСК ПО ТЕКСТУ ===
@router.message(SaleStates.waiting_for_product)
async def search_product_for_sale(callback: CallbackQuery, state: FSMContext):
    """Поиск товара для продажи (старый способ)"""
    query = callback.text

    with get_db_session() as db:
        products_data = CoreService.search_products(db, query)

    if not products_data:
        keyboard = get_cancel_back_keyboard()
        await callback.reply(
            "❌ Товары не найдены. Попробуйте другой запрос.",
            reply_markup=keyboard
        )
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
        keyboard = get_cancel_back_keyboard()
        await callback.reply(
            "❌ Нет товаров в наличии по вашему запросу",
            reply_markup=keyboard
        )
        return

    keyboard.adjust(1)
    keyboard.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search_sale"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        get_back_button()
    )

    await callback.reply(
        "📋 Выберите товар для продажи:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "new_search_sale")
async def new_search_sale(callback: CallbackQuery, state: FSMContext):
    """Новый поиск товара для продажи"""
    keyboard = get_cancel_back_keyboard()

    await callback.message.edit_text(
        "🚀 <b>Оформление продажи</b>\n\n"
        "Введите EAN или название товара:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(SaleStates.waiting_for_product)
    await callback.answer()

# === ОСТАЛЬНАЯ ЛОГИКА ПРОДАЖ (без изменений) ===
@router.callback_query(F.data.startswith("sell_"))
async def select_product_for_sale(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для продажи"""
    product_id = int(callback.data.replace("sell_", ""))

    with get_db_session() as db:
        info = CoreService.get_product_info(db, product_id)
        product = info['product']
        current_stock = info['current_stock']

    await state.update_data(product_id=product_id, product=product, current_stock=current_stock)

    price_text = CURRENCY_FORMAT.format(product.retail_price) if product.retail_price else "не установлена"

    keyboard = get_cancel_back_keyboard()

    await callback.message.edit_text(
        f"<b>Товар:</b> {product.name}\n"
        f"<b>Размер:</b> {product.size}\n"
        f"<b>Остаток:</b> {current_stock} шт.\n"
        f"<b>РРЦ:</b> {price_text}\n\n"
        f"Введите цену продажи в рублях:",
        reply_markup=keyboard,
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
        keyboard = get_cancel_back_keyboard()
        await message.reply(
            "❌ Введите корректную цену (число больше 0)",
            reply_markup=keyboard
        )
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
        ],
        [get_back_button()]
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

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"❌ Ошибка при оформлении продажи:\n{str(e)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    await state.clear()
    await callback.answer()

# === ОСТАТКИ (без изменений) ===
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

    keyboard.button(text="🔄 Обновить", callback_data="refresh_stock")
    keyboard.row(get_back_button())
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_stock")],
            [get_back_button()]
        ])

        await callback.message.edit_text(
            "📦 Нет товаров в наличии",
            reply_markup=keyboard
        )
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"stock_wh_{warehouse if warehouse else 'all'}")],
        [get_back_button()]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "refresh_stock")
async def refresh_stock(callback: CallbackQuery):
    """Обновить список остатков"""
    await stock_view(callback.message)
    await callback.answer("🔄 Остатки обновлены")

def register_handlers(dp):
    """Регистрация хендлеров продаж и остатков"""
    dp.include_router(router)