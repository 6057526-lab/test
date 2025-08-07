"""
Вспомогательные функции и утилиты
"""
from typing import Dict, List, Any
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO

from config import CURRENCY_FORMAT, PERCENT_FORMAT


def format_number(number: float, decimals: int = 2) -> str:
    """Форматирование числа с разделителями тысяч"""
    return f"{number:,.{decimals}f}".replace(',', ' ')


def format_currency(amount: float) -> str:
    """Форматирование суммы в рублях"""
    return CURRENCY_FORMAT.format(amount)


def format_percent(percent: float) -> str:
    """Форматирование процентов"""
    return PERCENT_FORMAT.format(percent)


def format_product_info(product) -> str:
    """Форматирование информации о товаре"""
    return (
        f"<b>{product.name}</b>\n"
        f"EAN: {product.ean}\n"
        f"Модель: {product.model}\n"
        f"Размер: {product.size}, Цвет: {product.color}\n"
        f"Возраст: {product.age}, Фит: {product.fit}\n"
        f"Остаток: {product.current_stock} шт.\n"
        f"Себестоимость: {format_currency(product.cost_price)}\n"
        f"РРЦ: {format_currency(product.retail_price or 0)}\n"
        f"Маржа: {format_currency(product.margin)} ({format_percent(product.margin_percent)})"
    )


def create_sales_report(report: Dict, period_name: str) -> str:
    """Создание текстового отчета по продажам"""
    text = f"📊 <b>Отчет по продажам {period_name}</b>\n\n"

    # Общая статистика
    text += (
        f"<b>Общие показатели:</b>\n"
        f"• Количество продаж: {report['total_sales']}\n"
        f"• Общая выручка: {format_currency(report['total_revenue'])}\n"
        f"• Общая маржа: {format_currency(report['total_margin'])}\n"
        f"• Средняя маржинальность: {format_percent(report['avg_margin_percent'])}\n\n"
    )

    # Статистика по продавцам
    if report['agent_stats']:
        text += "<b>По продавцам:</b>\n"

        # Сортируем по выручке
        sorted_agents = sorted(
            report['agent_stats'].items(),
            key=lambda x: x[1]['revenue'],
            reverse=True
        )

        for agent_name, stats in sorted_agents[:10]:
            text += (
                f"\n<b>{agent_name}</b>\n"
                f"• Продаж: {stats['sales_count']}\n"
                f"• Выручка: {format_currency(stats['revenue'])}\n"
                f"• Маржа: {format_currency(stats['margin'])}\n"
            )

    return text


def calculate_cost_price(price_eur: float, exchange_rate: float,
                        coefficient: float, weight: float,
                        logistics_per_kg: float) -> float:
    """Расчет себестоимости товара"""
    return price_eur * exchange_rate * coefficient + weight * logistics_per_kg


def validate_excel_data(df: pd.DataFrame, required_columns: List[str]) -> List[str]:
    """Валидация данных из Excel"""
    errors = []

    # Проверка наличия колонок
    missing_cols = set(required_columns) - set(df.columns)
    if missing_cols:
        errors.append(f"Отсутствуют колонки: {', '.join(missing_cols)}")

    # Проверка типов данных
    if 'EAN' in df.columns:
        # Проверка длины EAN
        invalid_ean = df[df['EAN'].astype(str).str.len() != 13]
        if not invalid_ean.empty:
            errors.append(f"Некорректные EAN (должно быть 13 символов): строки {invalid_ean.index.tolist()}")

    # Проверка числовых полей
    numeric_fields = ['Вес', 'Кол-во', 'Цена в евро', 'Курс', 'Коэффициент', 'Логистика (на кг)']
    for field in numeric_fields:
        if field in df.columns:
            try:
                df[field] = pd.to_numeric(df[field])
                if (df[field] < 0).any():
                    errors.append(f"Отрицательные значения в колонке '{field}'")
            except:
                errors.append(f"Некорректные числовые значения в колонке '{field}'")

    # Проверка фита
    if 'Фит' in df.columns:
        valid_fits = ['regular', 'tapered', 'wide']
        invalid_fits = df[~df['Фит'].str.lower().isin(valid_fits)]
        if not invalid_fits.empty:
            errors.append(f"Некорректный фит (должен быть {', '.join(valid_fits)}): строки {invalid_fits.index.tolist()}")

    return errors


def export_stock_to_excel(stock_data: List[Dict]) -> bytes:
    """Экспорт остатков в Excel"""
    df = pd.DataFrame(stock_data)

    # Переименование колонок для удобства
    column_mapping = {
        'ean': 'EAN',
        'name': 'Наименование',
        'size': 'Размер',
        'color': 'Цвет',
        'stock': 'Остаток',
        'cost_price': 'Себестоимость',
        'retail_price': 'РРЦ',
        'warehouse': 'Склад'
    }

    df = df.rename(columns=column_mapping)

    # Сортировка
    df = df.sort_values(['Склад', 'Наименование', 'Размер'])

    # Сохранение в bytes
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Остатки', index=False)

        # Форматирование
        worksheet = writer.sheets['Остатки']

        # Автоширина колонок
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    return output.getvalue()


def create_bonus_report(bonuses: List[Any], period_name: str = "весь период") -> str:
    """Создание отчета по бонусам"""
    total_amount = sum(b.amount for b in bonuses)
    paid_amount = sum(b.amount for b in bonuses if b.is_paid)
    unpaid_amount = sum(b.amount for b in bonuses if not b.is_paid)

    text = (
        f"🎁 <b>Отчет по бонусам за {period_name}</b>\n\n"
        f"<b>Общая сумма бонусов:</b> {format_currency(total_amount)}\n"
        f"<b>Выплачено:</b> {format_currency(paid_amount)}\n"
        f"<b>К выплате:</b> {format_currency(unpaid_amount)}\n\n"
        f"<b>Детализация:</b>\n"
    )

    for bonus in bonuses[:20]:
        status = "✅" if bonus.is_paid else "⏳"
        text += (
            f"{status} {bonus.agent.full_name}: "
            f"{format_currency(bonus.amount)} ({bonus.percent_used}%) - "
            f"{bonus.created_at.strftime('%d.%m.%Y')}\n"
        )

    if len(bonuses) > 20:
        text += f"\n<i>Показаны первые 20 из {len(bonuses)} записей</i>"

    return text


def parse_date_range(text: str) -> tuple:
    """Парсинг диапазона дат из текста"""
    # Простая реализация для примера
    today = datetime.now()

    if "сегодня" in text.lower():
        start = today.replace(hour=0, minute=0, second=0)
        end = today
    elif "вчера" in text.lower():
        yesterday = today - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
    elif "неделя" in text.lower():
        start = today - timedelta(days=7)
        end = today
    elif "месяц" in text.lower():
        start = today - timedelta(days=30)
        end = today
    else:
        # По умолчанию - последние 30 дней
        start = today - timedelta(days=30)
        end = today

    return start, end


def generate_sale_receipt(sale) -> str:
    """Генерация чека продажи"""
    return (
        f"📄 <b>ЧЕК ПРОДАЖИ</b>\n"
        f"{'=' * 30}\n"
        f"<b>Дата:</b> {sale.sale_date.strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>№:</b> {sale.id}\n"
        f"{'=' * 30}\n"
        f"<b>Товар:</b> {sale.product.name}\n"
        f"<b>Размер:</b> {sale.product.size}\n"
        f"<b>Количество:</b> {sale.quantity} шт.\n"
        f"<b>Цена:</b> {format_currency(sale.sale_price)}\n"
        f"{'=' * 30}\n"
        f"<b>ИТОГО:</b> {format_currency(sale.sale_price * sale.quantity)}\n"
        f"{'=' * 30}\n"
        f"<b>Продавец:</b> {sale.agent.full_name}\n"
        f"<b>Склад:</b> {sale.warehouse}\n"
    )


# === РЕНДЕР ГРАФИКОВ ===
def render_sales_timeseries_png(points: List[Dict]) -> bytes:
    """Рендер PNG графика продаж по дням: выручка и маржа"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    dates = [p['date'] for p in points]
    revenue = [p['revenue'] for p in points]
    margin = [p['margin'] for p in points]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, revenue, label='Выручка', color='#1f77b4')
    ax.plot(dates, margin, label='Маржа', color='#ff7f0e')
    ax.set_title('Продажи по дням')
    ax.set_xlabel('Дата')
    ax.set_ylabel('Сумма, ₽')
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate(rotation=45)

    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_margin_by_category_png(cat_to_value: Dict[str, float]) -> bytes:
    """Рендер PNG горизонтального барчарта маржи по категориям"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    cats = list(cat_to_value.keys())
    values = list(cat_to_value.values())

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(cats, values, color='#2ca02c')
    ax.set_title('Маржа по категориям')
    ax.set_xlabel('Маржа, ₽')
    ax.grid(True, axis='x', alpha=0.3)

    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_dual_axis_price_sales_png(price_points: List[Dict], sales_points: List[Dict]) -> bytes:
    """Рендер комбинированного графика: РРЦ (линия) + продажи (столбцы)"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from datetime import datetime

    # Подготовка данных
    price_dates = [p['ts'] if isinstance(p['ts'], datetime) else p['ts'] for p in price_points]
    price_values = [p.get('new') or p.get('old') or 0 for p in price_points]

    sales_dates = [s['date'] for s in sales_points]
    sales_qty = [s['qty'] for s in sales_points]

    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(price_dates, price_values, color='#1f77b4', label='РРЦ')
    ax1.set_ylabel('РРЦ, ₽', color='#1f77b4')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')

    ax2 = ax1.twinx()
    ax2.bar(sales_dates, sales_qty, color='#ff7f0e', alpha=0.4, label='Кол-во продаж')
    ax2.set_ylabel('Продажи, шт.', color='#ff7f0e')
    ax2.tick_params(axis='y', labelcolor='#ff7f0e')

    plt.title('Динамика РРЦ и продаж по товару')
    fig.autofmt_xdate(rotation=45)

    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()