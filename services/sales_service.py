"""
Сервис для работы с продажами и бонусами
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, select

from data.models import Sale, Bonus, BonusRule, StockLog, ActionLog, Product, Batch
from config import LOG_ACTIONS


class SalesService:
    """Сервис для работы с продажами и бонусами"""

    @staticmethod
    def log_action(db: Session, agent_id: int, action_type: str,
                   entity_type: str = None, entity_id: int = None,
                   details: str = None):
        """Логирование действия"""
        if LOG_ACTIONS:
            log = ActionLog(
                agent_id=agent_id,
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details
            )
            db.add(log)
            db.commit()

    @staticmethod
    def create_sale(db: Session, product_id: int, agent_id: int,
                   sale_price: float, quantity: int = 1) -> Sale:
        """Создать продажу"""
        product = db.query(Product).options(
            joinedload(Product.batch)
        ).filter(Product.id == product_id).first()

        if not product:
            raise ValueError("Товар не найден")

        # Подсчитываем текущий остаток
        sold_quantity = db.query(func.sum(Sale.quantity)).filter(
            Sale.product_id == product_id,
            Sale.is_returned == False
        ).scalar() or 0

        current_stock = product.quantity - sold_quantity

        if current_stock < quantity:
            raise ValueError(f"Недостаточно товара. Доступно: {current_stock}")

        # Рассчитываем маржу
        margin_per_unit = sale_price - product.cost_price
        total_margin = margin_per_unit * quantity
        margin_percent = (margin_per_unit / sale_price * 100) if sale_price > 0 else 0

        # Создаем продажу
        sale = Sale(
            product_id=product_id,
            agent_id=agent_id,
            quantity=quantity,
            sale_price=sale_price,
            margin=total_margin,
            margin_percent=margin_percent,
            warehouse=product.batch.warehouse
        )
        db.add(sale)
        db.flush()

        # Логируем движение товара
        stock_log = StockLog(
            product_id=product_id,
            operation_type='out',
            quantity=quantity,
            warehouse=product.batch.warehouse,
            reference_id=sale.id
        )
        db.add(stock_log)

        # Рассчитываем бонус
        bonus_amount, bonus_rule = SalesService.calculate_bonus(db, agent_id, total_margin)
        if bonus_amount > 0 and bonus_rule:
            bonus = Bonus(
                agent_id=agent_id,
                sale_id=sale.id,
                rule_id=bonus_rule.id,
                amount=bonus_amount,
                percent_used=bonus_rule.percent
            )
            db.add(bonus)

        db.commit()

        # Логируем
        SalesService.log_action(
            db, agent_id, 'sale_created',
            'sale', sale.id,
            f'Продан {product.name} за {sale_price}'
        )

        return sale

    @staticmethod
    def calculate_bonus(db: Session, agent_id: int,
                       margin: float) -> Tuple[float, Optional[BonusRule]]:
        """Рассчитать бонус для агента"""
        # Получаем сумму продаж за текущий месяц
        current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)

        month_sales = db.query(func.sum(Sale.margin)).filter(
            and_(
                Sale.agent_id == agent_id,
                Sale.sale_date >= current_month_start,
                Sale.is_returned == False
            )
        ).scalar() or 0

        # Находим подходящее правило
        rule = db.query(BonusRule).filter(
            and_(
                BonusRule.is_active == True,
                BonusRule.min_amount <= month_sales,
                BonusRule.max_amount > month_sales
            )
        ).first()

        if rule:
            bonus_amount = margin * (rule.percent / 100)
            return bonus_amount, rule

        return 0, None

    @staticmethod
    def get_agent_bonuses(db: Session, agent_id: int,
                         unpaid_only: bool = False) -> List[Bonus]:
        """Получить бонусы агента"""
        query = db.query(Bonus).filter(Bonus.agent_id == agent_id)

        if unpaid_only:
            query = query.filter(Bonus.is_paid == False)

        return query.order_by(Bonus.created_at.desc()).all()

    @staticmethod
    def pay_bonuses(db: Session, agent_id: int, admin_id: int) -> float:
        """Выплатить бонусы агенту"""
        unpaid_bonuses = db.query(Bonus).filter(
            and_(
                Bonus.agent_id == agent_id,
                Bonus.is_paid == False
            )
        ).all()

        total_amount = sum(bonus.amount for bonus in unpaid_bonuses)

        for bonus in unpaid_bonuses:
            bonus.is_paid = True
            bonus.paid_at = datetime.utcnow()

        db.commit()

        # Логируем
        SalesService.log_action(
            db, admin_id, 'bonuses_paid',
            'agent', agent_id,
            f'Выплачено бонусов на сумму {total_amount}'
        )

        return total_amount

    @staticmethod
    def return_sale(db: Session, sale_id: int, reason: str, admin_id: int) -> Sale:
        """Оформить возврат продажи"""
        sale = db.get(Sale, sale_id)
        if not sale:
            raise ValueError("Продажа не найдена")

        if sale.is_returned:
            raise ValueError("Продажа уже возвращена")

        # Помечаем продажу как возвращенную
        sale.is_returned = True
        sale.returned_at = datetime.utcnow()
        sale.return_reason = reason

        # Возвращаем товар на склад
        stock_log = StockLog(
            product_id=sale.product_id,
            operation_type='return',
            quantity=sale.quantity,
            warehouse=sale.warehouse,
            reference_id=sale.id
        )
        db.add(stock_log)

        # Аннулируем бонус если был
        bonus = db.query(Bonus).filter_by(sale_id=sale_id).first()
        if bonus and not bonus.is_paid:
            db.delete(bonus)

        db.commit()

        # Логируем
        SalesService.log_action(
            db, admin_id, 'sale_returned',
            'sale', sale_id,
            f'Возврат продажи. Причина: {reason}'
        )

        return sale

    @staticmethod
    def get_last_sale_price(db: Session, product_id: int) -> Optional[float]:
        """Последняя цена продажи по товару (исключая возвраты)"""
        sale = (
            db.query(Sale)
            .filter(Sale.product_id == product_id, Sale.is_returned == False)
            .order_by(Sale.sale_date.desc())
            .first()
        )
        return sale.sale_price if sale else None

    @staticmethod
    def get_agent_sales_history(db: Session, agent_id: int,
                                days: int = 30) -> List[Sale]:
        """История продаж агента"""
        start_date = datetime.utcnow() - timedelta(days=days)

        sales = db.query(Sale).filter(
            and_(
                Sale.agent_id == agent_id,
                Sale.sale_date >= start_date
            )
        ).order_by(Sale.sale_date.desc()).all()

        return sales
