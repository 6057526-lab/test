"""
Сервис для работы с остатками и поиском товаров
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, select, text

from data.models import Product, Sale, Batch


class StockService:
    """Сервис для работы с остатками и поиском товаров"""

    @staticmethod
    def get_stock(db: Session, warehouse: str = None,
                 category: str = None, size: str = None) -> List[Dict]:
        """Получить остатки товаров"""
        # Подзапрос для подсчета проданного количества
        sold_subquery = (
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label('sold_quantity')
            )
            .filter(Sale.is_returned == False)
            .group_by(Sale.product_id)
            .subquery()
        )

        # Основной запрос
        query = (
            db.query(
                Product,
                func.coalesce(sold_subquery.c.sold_quantity, 0).label('sold'),
                (Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0)).label('current_stock'),
                Batch.warehouse
            )
            .join(Batch)
            .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
        )

        if warehouse:
            query = query.filter(Batch.warehouse == warehouse)

        if category:
            query = query.filter(Product.name.contains(category))

        if size:
            query = query.filter(Product.size == size)

        # Получаем все товары и фильтруем в Python
        items = query.all()

        result = []
        for product, sold, current_stock, warehouse in items:
            if current_stock > 0:  # Фильтруем только товары с остатком
                result.append({
                    'id': product.id,
                    'ean': product.ean,
                    'name': product.name,
                    'size': product.size,
                    'color': product.color,
                    'stock': current_stock,
                    'cost_price': product.cost_price,
                    'retail_price': product.retail_price,
                    'warehouse': warehouse
                })

        return result

    @staticmethod
    def get_stock_optimized(db: Session, warehouse: str = None,
                           category: str = None, size: str = None) -> List[Dict]:
        """Получить остатки товаров (оптимизированная версия с CTE)"""
        # Базовый SQL с CTE
        sql = """
        WITH stock_calc AS (
            SELECT 
                p.*,
                b.warehouse,
                COALESCE(SUM(CASE WHEN s.is_returned = 0 THEN s.quantity ELSE 0 END), 0) as sold,
                p.quantity - COALESCE(SUM(CASE WHEN s.is_returned = 0 THEN s.quantity ELSE 0 END), 0) as current_stock
            FROM products p
            JOIN batches b ON b.id = p.batch_id
            LEFT JOIN sales s ON s.product_id = p.id
            WHERE 1=1
        """

        params = {}

        if warehouse:
            sql += " AND b.warehouse = :warehouse"
            params['warehouse'] = warehouse

        if category:
            sql += " AND p.name LIKE :category"
            params['category'] = f'%{category}%'

        if size:
            sql += " AND p.size = :size"
            params['size'] = size

        sql += """
            GROUP BY p.id
        )
        SELECT * FROM stock_calc WHERE current_stock > 0
        """

        result_proxy = db.execute(text(sql), params)

        result = []
        for row in result_proxy:
            result.append({
                'id': row.id,
                'ean': row.ean,
                'name': row.name,
                'size': row.size,
                'color': row.color,
                'stock': row.current_stock,
                'cost_price': row.cost_price,
                'retail_price': row.retail_price,
                'warehouse': row.warehouse
            })

        return result

    @staticmethod
    def search_products(db: Session, query: str) -> List[Dict]:
        """Поиск товаров с информацией об остатках"""
        search = f"%{query}%"

        # Подзапрос для подсчета проданного количества
        sold_subquery = (
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label('sold_quantity')
            )
            .filter(Sale.is_returned == False)
            .group_by(Sale.product_id)
            .subquery()
        )

        # Основной запрос с остатками
        products = (
            db.query(
                Product,
                func.coalesce(sold_subquery.c.sold_quantity, 0).label('sold'),
                (Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0)).label('current_stock')
            )
            .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
            .filter(
                or_(
                    Product.ean.like(search),
                    Product.name.like(search),
                    Product.model.like(search)
                )
            )
            .limit(20)
            .all()
        )

        # Формируем результат
        result = []
        for product, sold, current_stock in products:
            result.append({
                'product': product,
                'sold': sold,
                'current_stock': current_stock,
                'id': product.id,
                'name': product.name,
                'size': product.size,
                'ean': product.ean
            })

        return result

    @staticmethod
    def get_product_info(db: Session, product_id: int) -> Dict:
        """Получить полную информацию о товаре"""
        from sqlalchemy.orm import joinedload

        product = db.query(Product).options(
            joinedload(Product.batch)
        ).filter(Product.id == product_id).first()

        if not product:
            raise ValueError("Товар не найден")

        # История продаж
        sales = db.query(Sale).filter_by(product_id=product_id).all()

        # Подсчет текущего остатка
        sold_quantity = db.query(func.sum(Sale.quantity)).filter(
            Sale.product_id == product_id,
            Sale.is_returned == False
        ).scalar() or 0

        current_stock = product.quantity - sold_quantity

        # История цен
        from data.models import PriceHistory
        price_history = db.query(PriceHistory).filter_by(
            product_id=product_id
        ).order_by(PriceHistory.changed_at.desc()).all()

        return {
            'product': product,
            'batch': product.batch,
            'current_stock': current_stock,
            'sales_count': len(sales),
            'total_revenue': sum(s.sale_price for s in sales),
            'total_margin': sum(s.margin for s in sales),
            'price_history': price_history
        }

    @staticmethod
    def get_warehouse_list(db: Session) -> List[str]:
        """Получить список складов"""
        warehouses = db.query(Batch.warehouse).distinct().all()
        return [w[0] for w in warehouses]

    # === МЕТОДЫ ФИЛЬТРАЦИИ ===
    @staticmethod
    def get_available_filter_values(db: Session) -> Dict:
        """Получить доступные значения для фильтров (только товары с остатками)"""
        # Подзапрос для товаров с остатками
        sold_subquery = (
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label('sold_quantity')
            )
            .filter(Sale.is_returned == False)
            .group_by(Sale.product_id)
            .subquery()
        )

        # Основной запрос - товары с остатками > 0
        products_in_stock = (
            db.query(Product, Batch.warehouse)
            .join(Batch)
            .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
            .filter(
                Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0) > 0
            )
            .all()
        )

        categories = set()
        sizes = set()
        ages = set()
        warehouses = set()
        colors = set()

        for product, warehouse in products_in_stock:
            # Извлекаем категории из названий
            name_lower = product.name.lower()
            if 'конь' in name_lower or 'boot' in name_lower:
                categories.add('Коньки')
            elif 'клюш' in name_lower or 'stick' in name_lower:
                categories.add('Клюшки')
            elif 'шлем' in name_lower or 'helmet' in name_lower:
                categories.add('Шлемы')
            elif 'перчатк' in name_lower or 'glove' in name_lower:
                categories.add('Перчатки')
            elif 'защита' in name_lower or 'pad' in name_lower:
                categories.add('Защита')
            else:
                categories.add('Прочее')

            if product.size:
                sizes.add(product.size)
            if product.age:
                ages.add(product.age)
            if warehouse:
                warehouses.add(warehouse)
            if product.color:
                colors.add(product.color)

        return {
            'categories': sorted(categories),
            'sizes': sorted(sizes),
            'ages': sorted(ages),
            'warehouses': sorted(warehouses),
            'colors': sorted(colors)
        }

    @staticmethod
    def get_product_categories_in_stock(db: Session) -> Dict[str, int]:
        """Получить категории товаров с количеством в наличии"""
        # Получаем товары с остатками
        stock_data = StockService.get_stock(db)

        categories = {}
        for item in stock_data:
            name = item['name'].lower()

            # Определяем категорию
            if 'конь' in name or 'boot' in name:
                category = 'Коньки'
            elif 'клюш' in name or 'stick' in name:
                category = 'Клюшки'
            elif 'шлем' in name or 'helmet' in name:
                category = 'Шлемы'
            elif 'перчатк' in name or 'glove' in name:
                category = 'Перчатки'
            elif 'защита' in name or 'pad' in name:
                category = 'Защита'
            else:
                category = 'Прочее'

            categories[category] = categories.get(category, 0) + 1

        return dict(sorted(categories.items()))

    @staticmethod
    def get_available_sizes_in_stock(db: Session) -> Dict[str, int]:
        """Получить размеры с количеством товаров"""
        stock_data = StockService.get_stock(db)

        sizes = {}
        for item in stock_data:
            size = item['size']
            if size:
                sizes[size] = sizes.get(size, 0) + 1

        return dict(sorted(sizes.items()))

    @staticmethod
    def get_available_ages_in_stock(db: Session) -> Dict[str, int]:
        """Получить возрастные группы с количеством товаров"""
        stock_data = StockService.get_stock(db)

        ages: Dict[str, int] = {}
        if not stock_data:
            return ages

        product_ids = [item['id'] for item in stock_data]
        # Предзагружаем только необходимые поля
        products = (
            db.query(Product.id, Product.age)
            .filter(Product.id.in_(product_ids))
            .all()
        )
        for pid, age in products:
            if age:
                ages[age] = ages.get(age, 0) + 1

        return dict(sorted(ages.items()))

    @staticmethod
    def get_warehouses_with_stock(db: Session) -> Dict[str, int]:
        """Получить склады с количеством товаров"""
        stock_data = StockService.get_stock(db)

        warehouses = {}
        for item in stock_data:
            warehouse = item['warehouse']
            if warehouse:
                warehouses[warehouse] = warehouses.get(warehouse, 0) + 1

        return dict(sorted(warehouses.items()))

    @staticmethod
    def get_products_by_category(db: Session, category: str) -> List[Dict]:
        """Получить товары по категории"""
        all_products = StockService.search_products(db, "")  # Получаем все товары

        filtered = []
        for item in all_products:
            if item['current_stock'] <= 0:
                continue

            name = item['product'].name.lower()
            product_category = 'Прочее'

            if 'конь' in name or 'boot' in name:
                product_category = 'Коньки'
            elif 'клюш' in name or 'stick' in name:
                product_category = 'Клюшки'
            elif 'шлем' in name or 'helmet' in name:
                product_category = 'Шлемы'
            elif 'перчатк' in name or 'glove' in name:
                product_category = 'Перчатки'
            elif 'защита' in name or 'pad' in name:
                product_category = 'Защита'

            if product_category == category:
                filtered.append(item)

        return filtered[:50]  # Ограничиваем до 50 товаров

    @staticmethod
    def get_products_by_size(db: Session, size: str) -> List[Dict]:
        """Получить товары по размеру"""
        # Подзапрос для остатков
        sold_subquery = (
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label('sold_quantity')
            )
            .filter(Sale.is_returned == False)
            .group_by(Sale.product_id)
            .subquery()
        )

        products = (
            db.query(
                Product,
                func.coalesce(sold_subquery.c.sold_quantity, 0).label('sold'),
                (Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0)).label('current_stock')
            )
            .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
            .filter(
                Product.size == size,
                Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0) > 0
            )
            .limit(50)
            .all()
        )

        result = []
        for product, sold, current_stock in products:
            result.append({
                'product': product,
                'sold': sold,
                'current_stock': current_stock
            })

        return result

    @staticmethod
    def get_products_by_age(db: Session, age: str) -> List[Dict]:
        """Получить товары по возрасту"""
        sold_subquery = (
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label('sold_quantity')
            )
            .filter(Sale.is_returned == False)
            .group_by(Sale.product_id)
            .subquery()
        )

        products = (
            db.query(
                Product,
                func.coalesce(sold_subquery.c.sold_quantity, 0).label('sold'),
                (Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0)).label('current_stock')
            )
            .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)
            .filter(
                Product.age == age,
                Product.quantity - func.coalesce(sold_subquery.c.sold_quantity, 0) > 0
            )
            .limit(50)
            .all()
        )

        result = []
        for product, sold, current_stock in products:
            result.append({
                'product': product,
                'sold': sold,
                'current_stock': current_stock
            })

        return result

    @staticmethod
    def get_products_by_warehouse(db: Session, warehouse: str) -> List[Dict]:
        """Получить товары по складу"""
        stock_data = StockService.get_stock(db, warehouse=warehouse)

        # Преобразуем в формат для показа
        if not stock_data:
            return []

        limited_items = stock_data[:50]
        ids = [item['id'] for item in limited_items]
        products = (
            db.query(Product)
            .filter(Product.id.in_(ids))
            .all()
        )
        id_to_product = {p.id: p for p in products}

        result: List[Dict] = []
        for item in limited_items:
            product = id_to_product.get(item['id'])
            if product is None:
                continue
            result.append({
                'product': product,
                'current_stock': item['stock'],
                'sold': 0
            })

        return result

    @staticmethod
    def get_all_products_in_stock(db: Session) -> List[Dict]:
        """Получить все товары в наличии"""
        stock_data = StockService.get_stock(db)

        # Преобразуем в формат для показа
        if not stock_data:
            return []

        limited_items = stock_data[:100]
        ids = [item['id'] for item in limited_items]
        products = (
            db.query(Product)
            .filter(Product.id.in_(ids))
            .all()
        )
        id_to_product = {p.id: p for p in products}

        result: List[Dict] = []
        for item in limited_items:
            product = id_to_product.get(item['id'])
            if product is None:
                continue
            result.append({
                'product': product,
                'current_stock': item['stock'],
                'sold': 0
            })

        return result
