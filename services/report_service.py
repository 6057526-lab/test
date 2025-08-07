"""
Сервис для отчетов и графиков
"""
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from data.models import Sale, Product


class ReportService:
    """Сервис для отчетов и графиков"""

    @staticmethod
    def get_sales_report(db: Session, start_date: datetime = None,
                        end_date: datetime = None, agent_id: int = None,
                        warehouse: str = None) -> Dict:
        """Получить отчет по продажам"""
        query = db.query(Sale).filter(Sale.is_returned == False)

        if start_date:
            query = query.filter(Sale.sale_date >= start_date)
        if end_date:
            query = query.filter(Sale.sale_date <= end_date)
        if agent_id:
            query = query.filter(Sale.agent_id == agent_id)
        if warehouse:
            query = query.filter(Sale.warehouse == warehouse)

        sales = query.all()

        # Подсчет статистики
        total_sales = len(sales)
        total_revenue = sum(sale.sale_price for sale in sales)
        total_margin = sum(sale.margin for sale in sales)
        avg_margin_percent = (
            sum(sale.margin_percent for sale in sales) / total_sales
            if total_sales > 0 else 0
        )

        # Группировка по агентам
        agent_stats = {}
        for sale in sales:
            # Проверяем, что у продажи есть агент
            if sale.agent:
                agent_name = sale.agent.full_name
            else:
                agent_name = "Неизвестный агент"

            if agent_name not in agent_stats:
                agent_stats[agent_name] = {
                    'sales_count': 0,
                    'revenue': 0,
                    'margin': 0
                }
            agent_stats[agent_name]['sales_count'] += 1
            agent_stats[agent_name]['revenue'] += sale.sale_price
            agent_stats[agent_name]['margin'] += sale.margin

        return {
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_margin': total_margin,
            'avg_margin_percent': avg_margin_percent,
            'agent_stats': agent_stats,
            'period': {
                'start': start_date,
                'end': end_date
            }
        }

    # === ГРАФИКИ / АГРЕГАЦИИ ДЛЯ ВИЗУАЛИЗАЦИИ ===
    @staticmethod
    def get_sales_timeseries(db: Session, days: int = 30) -> List[Dict]:
        """Агрегация продаж по дням за последние N дней: [{'date': 'YYYY-MM-DD', 'count': n, 'revenue': x, 'margin': y}]"""
        start_date = datetime.utcnow() - timedelta(days=days)
        # Для SQLite подойдёт DATE(sale_date)
        day_col = func.date(Sale.sale_date)
        rows = (
            db.query(
                day_col.label('day'),
                func.count(Sale.id),
                func.sum(Sale.sale_price),
                func.sum(Sale.margin)
            )
            .filter(and_(Sale.sale_date >= start_date, Sale.is_returned == False))
            .group_by(day_col)
            .order_by(day_col)
            .all()
        )
        result: List[Dict] = []
        for day, cnt, revenue, margin in rows:
            result.append({
                'date': str(day),
                'count': int(cnt or 0),
                'revenue': float(revenue or 0),
                'margin': float(margin or 0),
            })
        return result

    @staticmethod
    def get_margin_by_category(db: Session, days: int = 30) -> Dict[str, float]:
        """Сумма маржи по категориям за период (категория по названию товара)."""
        start_date = datetime.utcnow() - timedelta(days=days)

        sales = (
            db.query(Sale)
            .options(joinedload(Sale.product))
            .filter(and_(Sale.sale_date >= start_date, Sale.is_returned == False))
            .all()
        )
        cats: Dict[str, float] = {}
        for s in sales:
            name = (s.product.name if s.product else '').lower()
            if 'конь' in name or 'boot' in name:
                cat = 'Коньки'
            elif 'клюш' in name or 'stick' in name:
                cat = 'Клюшки'
            elif 'шлем' in name or 'helmet' in name:
                cat = 'Шлемы'
            elif 'перчатк' in name or 'glove' in name:
                cat = 'Перчатки'
            elif 'защита' in name or 'pad' in name:
                cat = 'Защита'
            else:
                cat = 'Прочее'
            cats[cat] = cats.get(cat, 0.0) + float(s.margin or 0)
        return dict(sorted(cats.items(), key=lambda x: x[1], reverse=True))

    @staticmethod
    def get_product_price_timeseries(db: Session, product_id: int, days: int = 90) -> List[Dict]:
        """Динамика РРЦ по товару (история PriceHistory) + текущая цена"""
        from data.models import PriceHistory
        start_date = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(PriceHistory.changed_at, PriceHistory.old_price, PriceHistory.new_price)
            .filter(PriceHistory.product_id == product_id, PriceHistory.changed_at >= start_date)
            .order_by(PriceHistory.changed_at)
            .all()
        )
        data: List[Dict] = []
        for ts, old_p, new_p in rows:
            data.append({'ts': ts, 'old': float(old_p or 0), 'new': float(new_p or 0)})
        # Добавим текущую цену точкой now
        prod = db.get(Product, product_id)
        if prod:
            data.append({'ts': datetime.utcnow(), 'old': float(prod.retail_price or 0), 'new': float(prod.retail_price or 0)})
        return data

    @staticmethod
    def get_product_sales_timeseries(db: Session, product_id: int, days: int = 90) -> List[Dict]:
        """Динамика продаж товара по дням"""
        start_date = datetime.utcnow() - timedelta(days=days)
        day_col = func.date(Sale.sale_date)
        rows = (
            db.query(day_col, func.sum(Sale.quantity), func.sum(Sale.sale_price))
            .filter(Sale.product_id == product_id, Sale.sale_date >= start_date, Sale.is_returned == False)
            .group_by(day_col)
            .order_by(day_col)
            .all()
        )
        data: List[Dict] = []
        for day, qty, revenue in rows:
            data.append({'date': str(day), 'qty': int(qty or 0), 'revenue': float(revenue or 0)})
        return data
