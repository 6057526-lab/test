"""
Сервис для работы с ценами и массовыми операциями
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from data.models import Product, PriceHistory, ActionLog, Batch
from config import LOG_ACTIONS


class PriceService:
    """Сервис для работы с ценами и массовыми операциями"""

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
    def set_retail_price(db: Session, product_id: int,
                        retail_price: float, changed_by_id: int) -> Product:
        """Установить розничную цену"""
        product = db.get(Product, product_id)
        if not product:
            raise ValueError("Товар не найден")

        # Сохраняем историю
        old_price = product.retail_price
        if old_price:
            history = PriceHistory(
                product_id=product_id,
                old_price=old_price,
                new_price=retail_price,
                changed_by_id=changed_by_id
            )
            db.add(history)

        product.retail_price = retail_price
        db.commit()

        # Логируем
        PriceService.log_action(
            db, changed_by_id, 'price_changed',
            'product', product_id,
            f'Цена изменена с {old_price} на {retail_price}'
        )

        return product

    @staticmethod
    def bulk_update_retail_price_by_ids(
        db: Session,
        product_ids: List[int],
        new_price: Optional[float] = None,
        increase_percent: Optional[float] = None,
        changed_by_id: Optional[int] = None
    ) -> int:
        """Массовое обновление РРЦ: либо установка фиксированной цены, либо повышение на %.

        Возвращает количество изменённых товаров.
        """
        if not product_ids:
            return 0

        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        changed = 0

        for product in products:
            old_price = product.retail_price or 0
            if increase_percent is not None:
                # Устанавливаем РРЦ как наценку от себестоимости
                base = product.cost_price or 0
                updated = round(base * (1 + increase_percent / 100), 2)
            elif new_price is not None:
                updated = new_price
            else:
                continue

            # История изменения
            if old_price:
                db.add(PriceHistory(
                    product_id=product.id,
                    old_price=old_price,
                    new_price=updated,
                    changed_by_id=changed_by_id
                ))

            product.retail_price = updated
            changed += 1

        if changed:
            db.commit()

            # Лог одной строкой
            if changed_by_id:
                action_details = (
                    f"Обновлено цен: {changed}; "
                    f"режим={'percent' if increase_percent is not None else 'fixed'}; "
                    f"value={increase_percent if increase_percent is not None else new_price}"
                )
                PriceService.log_action(db, changed_by_id, 'bulk_price_update', 'product', None, action_details)

        return changed

    @staticmethod
    def preview_bulk_price_update(
        db: Session,
        product_ids: List[int],
        new_price: Optional[float] = None,
        increase_percent: Optional[float] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Предпросмотр изменений цен: возвращает список {id, name, old, new, diff_percent}"""
        if not product_ids:
            return []
        products = (
            db.query(Product.id, Product.name, Product.size, Product.cost_price, Product.retail_price)
            .filter(Product.id.in_(product_ids))
            .limit(limit)
            .all()
        )
        preview: List[Dict] = []
        for pid, name, size, cost_price, retail_price in products:
            old_price = retail_price or 0
            if increase_percent is not None:
                newp = round((cost_price or 0) * (1 + increase_percent / 100), 2)
            elif new_price is not None:
                newp = float(new_price)
            else:
                continue
            diff_percent = 0.0
            if old_price:
                diff_percent = round((newp - old_price) / old_price * 100, 2)
            preview.append({
                'id': pid,
                'name': name,
                'size': size,
                'old': old_price,
                'new': newp,
                'diff_percent': diff_percent,
            })
        return preview

    @staticmethod
    def select_products_for_bulk_pricing(
        db: Session,
        category: Optional[str] = None,
        size: Optional[str] = None,
        age: Optional[str] = None,
        warehouse: Optional[str] = None,
        color: Optional[str] = None,
        only_in_stock: bool = True,
        limit: Optional[int] = 200
    ) -> List[Product]:
        """Подборка товаров для массовой установки цен по фильтрам (как в продаже)."""
        from sqlalchemy import func, select

        # Базовый запрос
        query = db.query(Product).join(Batch)

        # Фильтры
        if warehouse:
            query = query.filter(Batch.warehouse == warehouse)
        if category:
            # Категория по эвристике из названия, совпадает с логикой get_product_categories_in_stock
            name_filter = []
            cat = category.lower()
            if cat == 'коньки':
                name_filter = [Product.name.ilike('%конь%'), Product.name.ilike('%boot%')]
            elif cat == 'клюшки':
                name_filter = [Product.name.ilike('%клюш%'), Product.name.ilike('%stick%')]
            elif cat == 'шлемы':
                name_filter = [Product.name.ilike('%шлем%'), Product.name.ilike('%helmet%')]
            elif cat == 'перчатки':
                name_filter = [Product.name.ilike('%перчатк%'), Product.name.ilike('%glove%')]
            elif cat == 'защита':
                name_filter = [Product.name.ilike('%защита%'), Product.name.ilike('%pad%')]
            if name_filter:
                query = query.filter(or_(*name_filter))
        if size:
            query = query.filter(Product.size == size)
        if age:
            query = query.filter(Product.age == age)
        if color:
            query = query.filter(Product.color == color)

        if only_in_stock:
            # Подсчитываем остаток и фильтруем > 0
            from data.models import Sale
            sold_subquery = (
                select(
                    Sale.product_id,
                    func.sum(Sale.quantity).label('sold_quantity')
                ).filter(Sale.is_returned == False)
                .group_by(Sale.product_id)
                .subquery()
            )
            query = (
                query.outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
                .filter((Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0)) > 0)
            )

        if limit is not None:
            query = query.limit(limit)
        return query.all()
