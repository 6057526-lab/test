"""
Обработчики для подбора хоккейной экипировки
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers import get_back_button
from services.core_service import CoreService
from data.db import get_db_session
from config import CURRENCY_FORMAT


router = Router()


class GearStates(StatesGroup):
    """Состояния для подбора экипировки"""
    choosing_method = State()  # Выбор метода подбора
    questionnaire_position = State()  # Позиция игрока
    questionnaire_skill = State()  # Уровень игры
    questionnaire_age = State()  # Возрастная группа
    questionnaire_budget = State()  # Бюджет
    questionnaire_size = State()  # Предпочтения по размеру
    showing_results = State()  # Показ результатов


@router.message(F.text == "🏒 Подбор экипировки")
async def gear_menu(message: Message, state: FSMContext):
    """Главное меню подбора экипировки"""
    kb = InlineKeyboardBuilder()
    
    kb.button(text="📝 Анкета подбора", callback_data="gear_questionnaire")
    kb.button(text="📦 Готовые комплекты", callback_data="gear_kits")
    kb.row()
    kb.button(text="🔍 Поиск по товару", callback_data="gear_search_by_product")
    kb.row(get_back_button())
    
    await message.answer(
        "🏒 <b>Подбор хоккейной экипировки</b>\n\n"
        "Выберите способ подбора:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "gear_questionnaire")
async def start_questionnaire(callback: CallbackQuery, state: FSMContext):
    """Начать анкету подбора"""
    await state.set_state(GearStates.questionnaire_position)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🥅 Вратарь", callback_data="gear_pos_goalie")
    kb.button(text="🛡️ Защитник", callback_data="gear_pos_defender")
    kb.button(text="⚡ Нападающий", callback_data="gear_pos_forward")
    kb.button(text="🎯 Любая позиция", callback_data="gear_pos_all")
    kb.row(get_back_button())
    
    await callback.message.edit_text(
        "🎯 <b>Шаг 1: Позиция игрока</b>\n\n"
        "Выберите позицию игрока:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_pos_"))
async def save_position(callback: CallbackQuery, state: FSMContext):
    """Сохранить позицию и перейти к уровню игры"""
    position = callback.data.replace("gear_pos_", "")
    await state.update_data(position=position)
    await state.set_state(GearStates.questionnaire_skill)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🌱 Новичок", callback_data="gear_skill_beginner")
    kb.button(text="🏆 Любитель", callback_data="gear_skill_amateur")
    kb.button(text="⭐ Профессионал", callback_data="gear_skill_professional")
    kb.row(get_back_button())
    
    await callback.message.edit_text(
        "🏆 <b>Шаг 2: Уровень игры</b>\n\n"
        "Выберите уровень игры:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_skill_"))
async def save_skill(callback: CallbackQuery, state: FSMContext):
    """Сохранить уровень игры и перейти к возрасту"""
    skill = callback.data.replace("gear_skill_", "")
    await state.update_data(skill_level=skill)
    await state.set_state(GearStates.questionnaire_age)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="👶 Дети (до 12 лет)", callback_data="gear_age_kids")
    kb.button(text="👦 Юниоры (13-17 лет)", callback_data="gear_age_youth")
    kb.button(text="👨 Взрослые (18+)", callback_data="gear_age_adult")
    kb.row(get_back_button())
    
    await callback.message.edit_text(
        "👤 <b>Шаг 3: Возрастная группа</b>\n\n"
        "Выберите возрастную группу:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_age_"))
async def save_age(callback: CallbackQuery, state: FSMContext):
    """Сохранить возраст и перейти к бюджету"""
    age = callback.data.replace("gear_age_", "")
    await state.update_data(age_group=age)
    await state.set_state(GearStates.questionnaire_budget)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💸 Без ограничений", callback_data="gear_budget_none")
    kb.button(text="💰 До 10,000 ₽", callback_data="gear_budget_10000")
    kb.button(text="💵 До 20,000 ₽", callback_data="gear_budget_20000")
    kb.button(text="💎 До 50,000 ₽", callback_data="gear_budget_50000")
    kb.row(get_back_button())
    
    await callback.message.edit_text(
        "💰 <b>Шаг 4: Бюджет</b>\n\n"
        "Выберите бюджет (или введите свою сумму):",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_budget_"))
async def save_budget(callback: CallbackQuery, state: FSMContext):
    """Сохранить бюджет и завершить анкету"""
    budget_str = callback.data.replace("gear_budget_", "")
    
    if budget_str == "none":
        budget = None
    else:
        budget = int(budget_str)
    
    await state.update_data(budget=budget)
    
    # Завершаем анкету и показываем результаты
    await show_questionnaire_results(callback, state)


@router.message(GearStates.questionnaire_budget)
async def handle_budget_input(message: Message, state: FSMContext):
    """Обработка ввода бюджета вручную"""
    try:
        budget = int(message.text.replace(' ', '').replace('₽', '').replace(',', ''))
        await state.update_data(budget=budget)
        await show_questionnaire_results(message, state)
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректную сумму (например: 15000 или 15000 ₽)"
        )


async def show_questionnaire_results(update: Message | CallbackQuery, state: FSMContext):
    """Показать результаты подбора по анкете"""
    data = await state.get_data()
    
    with get_db_session() as db:
        results = CoreService.search_gear_by_questionnaire(db, data)
    
    if not results:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Начать заново", callback_data="gear_questionnaire")
        kb.row(get_back_button())
        
        text = (
            "😔 <b>К сожалению, не найдено подходящей экипировки</b>\n\n"
            "Попробуйте:\n"
            "• Изменить критерии поиска\n"
            "• Увеличить бюджет\n"
            "• Посмотреть готовые комплекты"
        )
        
        if isinstance(update, CallbackQuery):
            await update.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
            await update.answer()
        else:
            await update.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        return
    
    # Группируем результаты по категориям
    categorized = {}
    for item in results:
        category = item['category']
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(item)
    
    # Формируем текст с результатами
    text = "🏒 <b>Подобранная экипировка:</b>\n\n"
    
    for category, items in categorized.items():
        text += f"📦 <b>{category.title()}:</b>\n"
        for i, item in enumerate(items[:3], 1):  # Показываем топ-3 по каждой категории
            price = CURRENCY_FORMAT.format(item['price'])
            text += f"{i}. {item['name']}\n"
            text += f"   💰 {price} | 📦 {item['stock']} шт. | 🔹 {item['size']}\n\n"
    
    # Добавляем общую стоимость
    total_cost = sum(item['price'] for item in results)
    text += f"💎 <b>Общая стоимость: {CURRENCY_FORMAT.format(total_cost)}</b>\n\n"
    
    if data.get('budget') and total_cost > data['budget']:
        text += "⚠️ <i>Стоимость превышает указанный бюджет</i>\n\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Добавить в корзину", callback_data="gear_add_to_cart")
    kb.button(text="📋 Сохранить список", callback_data="gear_save_list")
    kb.row()
    kb.button(text="🔄 Новый поиск", callback_data="gear_questionnaire")
    kb.row(get_back_button())
    
    await state.set_state(GearStates.showing_results)
    await state.update_data(search_results=results)
    
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await update.answer()
    else:
        await update.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "gear_kits")
async def show_gear_kits(callback: CallbackQuery):
    """Показать готовые комплекты экипировки"""
    kits = CoreService.get_gear_kits()
    
    kb = InlineKeyboardBuilder()
    
    for kit_id, kit in kits.items():
        kb.button(
            text=f"📦 {kit['name']}", 
            callback_data=f"gear_kit_{kit_id}"
        )
    
    kb.row(get_back_button())
    
    await callback.message.edit_text(
        "📦 <b>Готовые комплекты экипировки</b>\n\n"
        "Выберите подходящий комплект:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_kit_"))
async def show_kit_details(callback: CallbackQuery, state: FSMContext):
    """Показать детали комплекта и товары"""
    kit_id = callback.data.replace("gear_kit_", "")
    kits = CoreService.get_gear_kits()
    
    if kit_id not in kits:
        await callback.answer("❌ Комплект не найден", show_alert=True)
        return
    
    kit = kits[kit_id]
    
    with get_db_session() as db:
        products = CoreService.search_gear_by_kit(db, kit_id)
    
    if not products:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Попробовать другой комплект", callback_data="gear_kits")
        kb.row(get_back_button())
        
        await callback.message.edit_text(
            f"😔 <b>Товары для комплекта не найдены</b>\n\n"
            f"Комплект: {kit['name']}\n"
            f"Описание: {kit['description']}\n\n"
            f"Попробуйте другой комплект или обратитесь к менеджеру.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Группируем по категориям
    categorized = {}
    for product in products:
        category = product['category']
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(product)
    
    text = f"📦 <b>{kit['name']}</b>\n"
    text += f"📝 {kit['description']}\n\n"
    
    for category, items in categorized.items():
        text += f"🔹 <b>{category.title()}:</b>\n"
        for i, item in enumerate(items[:2], 1):  # Топ-2 по каждой категории
            price = CURRENCY_FORMAT.format(item['price'])
            text += f"{i}. {item['name']}\n"
            text += f"   💰 {price} | 📦 {item['stock']} шт.\n\n"
    
    total_cost = sum(item['price'] for item in products)
    text += f"💎 <b>Примерная стоимость: {CURRENCY_FORMAT.format(total_cost)}</b>\n\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Заказать комплект", callback_data=f"gear_order_kit_{kit_id}")
    kb.button(text="📋 Подробный список", callback_data=f"gear_kit_details_{kit_id}")
    kb.row()
    kb.button(text="🔄 Другие комплекты", callback_data="gear_kits")
    kb.row(get_back_button())
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "gear_search_by_product")
async def gear_search_by_product(callback: CallbackQuery):
    """Поиск совместимых товаров по выбранному товару"""
    await callback.message.edit_text(
        "🔍 <b>Поиск совместимых товаров</b>\n\n"
        "Введите название товара или его ID для поиска совместимой экипировки:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gear_add_to_cart"))
async def add_gear_to_cart(callback: CallbackQuery, state: FSMContext):
    """Добавить подобранную экипировку в корзину"""
    data = await state.get_data()
    results = data.get('search_results', [])
    
    if not results:
        await callback.answer("❌ Нет товаров для добавления", show_alert=True)
        return
    
    # Здесь можно добавить логику корзины
    # Пока просто показываем сообщение
    await callback.answer(
        f"✅ Добавлено {len(results)} товаров в корзину!",
        show_alert=True
    )


@router.callback_query(F.data.startswith("gear_save_list"))
async def save_gear_list(callback: CallbackQuery, state: FSMContext):
    """Сохранить список подобранной экипировки"""
    data = await state.get_data()
    results = data.get('search_results', [])
    
    if not results:
        await callback.answer("❌ Нет списка для сохранения", show_alert=True)
        return
    
    # Здесь можно добавить логику сохранения
    # Пока просто показываем сообщение
    await callback.answer(
        f"💾 Список из {len(results)} товаров сохранен!",
        show_alert=True
    )


def register_handlers(dp):
    """Регистрация обработчиков подбора экипировки"""
    dp.include_router(router)
