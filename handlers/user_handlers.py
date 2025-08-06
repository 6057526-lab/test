"""
handlers/user_handlers.py
Пользовательские хендлеры: старт, меню, бонусы, история, навигация
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.db import get_db_session
from data.models import Agent, Bonus
from services.core_service import CoreService
from config import CURRENCY_FORMAT
from handlers import (
    is_admin, get_admin_keyboard, get_seller_keyboard,
    get_back_button, show_main_menu, BonusStates
)

router = Router()

# === ОСНОВНЫЕ КОМАНДЫ И МЕНЮ ===
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()  # Сбрасываем любые состояния

    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    with get_db_session() as db:
        agent = CoreService.get_or_create_agent(db, user_id, username, full_name)
        is_admin_user = is_admin(user_id)

        if is_admin_user:
            agent.is_admin = True
            db.commit()

    await show_main_menu(message, is_admin_user)

# === НАВИГАЦИЯ ===
@router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: CallbackQuery, state: FSMContext):
    """Возврат к главному меню"""
    await state.clear()
    await show_main_menu(callback)

@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Операция отменена\n\n"
        "Возвращаемся в главное меню...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_agents")
async def back_to_agents(callback: CallbackQuery):
    """Вернуться к списку агентов"""
    await bonus_view(callback.message)
    await callback.answer()

# === БОНУСЫ (для всех пользователей) ===
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
            # Подсчитываем невыплаченные бонусы
            unpaid_bonuses = db.query(Bonus).filter(
                Bonus.agent_id == agent.id,
                Bonus.is_paid == False
            ).all()
            unpaid_amount = sum(b.amount for b in unpaid_bonuses)

            display_text = f"👤 {agent.full_name}"
            if unpaid_amount > 0:
                display_text += f" ({CURRENCY_FORMAT.format(unpaid_amount)})"

            keyboard.button(
                text=display_text,
                callback_data=f"bonus_agent_{agent.id}"
            )

        keyboard.button(text="🔄 Обновить", callback_data="refresh_bonus_list")
        keyboard.row(get_back_button())
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
            )

            if bonuses:
                text += "<b>Последние операции:</b>\n"
                for bonus in bonuses[:10]:
                    status = "✅ Выплачено" if bonus.is_paid else "⏳ Ожидает"
                    text += (
                        f"\n{status} {CURRENCY_FORMAT.format(bonus.amount)} "
                        f"({bonus.percent_used}%) - {bonus.created_at.strftime('%d.%m.%Y')}"
                    )
            else:
                text += "У вас пока нет бонусов."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_my_bonus")],
            [get_back_button()]
        ])

        await message.reply(text, parse_mode="HTML", reply_markup=keyboard)

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
        keyboard.button(
            text="🗑️ Обнулить бонусы",
            callback_data=f"reset_bonus_{agent_id}"
        )
    keyboard.button(text="◀️ К списку", callback_data="back_to_agents")
    keyboard.button(text="🏠 Главное меню", callback_data="back_to_main")
    keyboard.adjust(2)

    text = (
        f"🎁 <b>Бонусы продавца {agent.full_name}</b>\n\n"
        f"<b>К выплате:</b> {CURRENCY_FORMAT.format(total_unpaid)}\n"
        f"<b>Выплачено всего:</b> {CURRENCY_FORMAT.format(total_paid)}\n"
    )

    if bonuses:
        text += "\n<b>История:</b>\n"
        for bonus in bonuses[:5]:
            status = "✅" if bonus.is_paid else "⏳"
            text += (
                f"{status} {CURRENCY_FORMAT.format(bonus.amount)} "
                f"({bonus.percent_used}%) - {bonus.created_at.strftime('%d.%m.%Y')}\n"
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К списку", callback_data="back_to_agents")],
        [get_back_button()]
    ])

    await callback.message.edit_text(
        f"✅ <b>Бонусы выплачены!</b>\n\n"
        f"<b>Продавец:</b> {agent.full_name}\n"
        f"<b>Сумма:</b> {CURRENCY_FORMAT.format(amount)}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reset_bonus_"))
async def reset_bonus_confirmation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение обнуления бонусов"""
    agent_id = int(callback.data.replace("reset_bonus_", ""))

    with get_db_session() as db:
        agent = db.query(Agent).get(agent_id)
        unpaid_bonuses = db.query(Bonus).filter(
            Bonus.agent_id == agent_id,
            Bonus.is_paid == False
        ).all()
        total_unpaid = sum(b.amount for b in unpaid_bonuses)

    await state.update_data(agent_id=agent_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, обнулить", callback_data="confirm_reset_bonus"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"bonus_agent_{agent_id}")
        ],
        [get_back_button()]
    ])

    await callback.message.edit_text(
        f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        f"Вы уверены, что хотите обнулить все невыплаченные бонусы продавца <b>{agent.full_name}</b>?\n\n"
        f"<b>Сумма к обнулению:</b> {CURRENCY_FORMAT.format(total_unpaid)}\n\n"
        f"❗ <i>Это действие нельзя отменить!</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(BonusStates.waiting_for_confirmation)
    await callback.answer()

@router.callback_query(BonusStates.waiting_for_confirmation, F.data == "confirm_reset_bonus")
async def confirm_reset_bonus(callback: CallbackQuery, state: FSMContext):
    """Подтверждение обнуления бонусов"""
    data = await state.get_data()
    agent_id = data['agent_id']

    try:
        with get_db_session() as db:
            # Получаем информацию об агенте
            agent = db.query(Agent).get(agent_id)

            # Находим все невыплаченные бонусы
            unpaid_bonuses = db.query(Bonus).filter(
                Bonus.agent_id == agent_id,
                Bonus.is_paid == False
            ).all()

            total_amount = sum(b.amount for b in unpaid_bonuses)

            # Удаляем невыплаченные бонусы
            for bonus in unpaid_bonuses:
                db.delete(bonus)

            db.commit()

            # Логируем действие
            CoreService.log_action(
                db, callback.from_user.id, 'bonuses_reset',
                'agent', agent_id,
                f'Обнулены бонусы на сумму {total_amount}'
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К списку", callback_data="back_to_agents")],
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"✅ <b>Бонусы обнулены!</b>\n\n"
            f"<b>Продавец:</b> {agent.full_name}\n"
            f"<b>Обнуленная сумма:</b> {CURRENCY_FORMAT.format(total_amount)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [get_back_button()]
        ])

        await callback.message.edit_text(
            f"❌ Ошибка при обнулении бонусов:\n{str(e)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "refresh_bonus_list")
async def refresh_bonus_list(callback: CallbackQuery):
    """Обновить список бонусов"""
    await bonus_view(callback.message)
    await callback.answer("🔄 Список обновлен")

@router.callback_query(F.data == "refresh_my_bonus")
async def refresh_my_bonus(callback: CallbackQuery):
    """Обновить мои бонусы"""
    await bonus_view(callback.message)
    await callback.answer("🔄 Бонусы обновлены")

# === ИСТОРИЯ ПРОДАЖ (для продавцов) ===
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_sales_history")],
        [get_back_button()]
    ])

    await message.reply(text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "refresh_sales_history")
async def refresh_sales_history(callback: CallbackQuery):
    """Обновить историю продаж"""
    await sales_history(callback.message)
    await callback.answer("🔄 История обновлена")

def register_handlers(dp):
    """Регистрация хендлеров пользователей"""
    dp.include_router(router)