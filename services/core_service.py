"""
Бизнес-логика для работы с хоккейной экипировкой
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, select

from data.db import get_db_session
from data.models import (
    Agent, Batch, Product, Sale, BonusRule,
    Bonus, PriceHistory, StockLog, ActionLog
)
from config import EXCEL_TEMPLATE_COLUMNS, LOG_ACTIONS


class CoreService:
    """Основной сервис с бизнес-логикой"""

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
    def get_or_create_agent(db: Session, telegram_id: int,
                           telegram_username: str = None,
                           full_name: str = None) -> Agent:
        """Получить или создать агента"""
        agent = db.query(Agent).filter_by(telegram_id=telegram_id).first()
        if not agent:
            agent = Agent(
                telegram_id=telegram_id,
                telegram_username=telegram_username or 'unknown',
                full_name=full_name or f'User {telegram_id}',
                is_admin=False
            )
            db.add(agent)
            db.commit()
        return agent

    @staticmethod
    def create_batch_from_excel(db: Session, file_path: str,
                               warehouse: str, created_by_id: int) -> Tuple[Batch, List[Product]]:
        """Создать партию из Excel файла"""
        try:
            # Читаем Excel
            df = pd.read_excel(file_path, engine='openpyxl')

            # Проверяем наличие всех колонок
            missing_cols = set(EXCEL_TEMPLATE_COLUMNS) - set(df.columns)
            if missing_cols:
                raise ValueError(f"Отсутствуют колонки: {missing_cols}")

            # Удаляем пустые строки
            df = df.dropna(how='all')

            if df.empty:
                raise ValueError("Excel файл не содержит данных")

            # Создаем партию
            batch_number = f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            batch = Batch(
                batch_number=batch_number,
                warehouse=warehouse,
                created_by_id=created_by_id
            )
            db.add(batch)
            db.flush()

            products = []
            errors = []
            ean_count = {}  # Для отслеживания дубликатов EAN в файле

            for idx, row in df.iterrows():
                try:
                    # Валидация данных
                    if pd.isna(row['EAN']) or str(row['EAN']).strip() == '':
                        errors.append(f"Строка {idx+2}: отсутствует EAN")
                        continue

                    # Преобразуем типы данных
                    ean = str(row['EAN']).strip()

                    # Проверка на дубликаты в текущем файле
                    if ean in ean_count:
                        ean_count[ean] += 1
                        errors.append(f"Строка {idx+2}: дубликат EAN {ean} (уже встречался в строке {ean_count[ean]})")
                        continue
                    else:
                        ean_count[ean] = idx + 2
                    name = str(row['Наименование']).strip() if not pd.isna(row['Наименование']) else 'Без названия'
                    model = str(row['Модель']).strip() if not pd.isna(row['Модель']) else ''
                    color = str(row['Цвет']).strip() if not pd.isna(row['Цвет']) else ''
                    size = str(row['Размер']).strip() if not pd.isna(row['Размер']) else ''
                    age = str(row['Возраст']).strip() if not pd.isna(row['Возраст']) else ''
                    fit = str(row['Фит']).lower().strip() if not pd.isna(row['Фит']) else 'regular'

                    # Числовые поля с валидацией
                    weight = float(row['Вес']) if not pd.isna(row['Вес']) else 0.1
                    if weight <= 0:
                        weight = 0.1  # Минимальный вес

                    quantity = int(row['Кол-во']) if not pd.isna(row['Кол-во']) else 0
                    if quantity < 0:
                        errors.append(f"Строка {idx+2}: отрицательное количество")
                        continue

                    price_eur = float(row['Цена в евро']) if not pd.isna(row['Цена в евро']) else 0.0
                    if price_eur < 0:
                        errors.append(f"Строка {idx+2}: отрицательная цена")
                        continue

                    exchange_rate = float(row['Курс']) if not pd.isna(row['Курс']) else 1.0
                    if exchange_rate <= 0:
                        exchange_rate = 1.0

                    coefficient = float(row['Коэффициент']) if not pd.isna(row['Коэффициент']) else 1.0
                    if coefficient <= 0:
                        coefficient = 1.0

                    logistics_per_kg = float(row['Логистика (на кг)']) if not pd.isna(row['Логистика (на кг)']) else 0.0
                    if logistics_per_kg < 0:
                        logistics_per_kg = 0.0

                    # Проверка валидности фита
                    if fit not in ['regular', 'tapered', 'wide']:
                        fit = 'regular'

                    # Расчет себестоимости
                    cost_price = (
                        price_eur * exchange_rate * coefficient +
                        weight * logistics_per_kg
                    )

                    # Проверка на существующий товар с таким EAN в этой партии
                    existing_product = db.query(Product).filter_by(
                        ean=ean,
                        batch_id=batch.id
                    ).first()

                    if existing_product:
                        # Если товар уже есть в партии, обновляем количество
                        existing_product.quantity += quantity

                        # Обновляем запись в stock_log
                        stock_log = StockLog(
                            product_id=existing_product.id,
                            operation_type='in',
                            quantity=quantity,
                            warehouse=warehouse,
                            reference_id=batch.id
                        )
                        db.add(stock_log)

                        errors.append(f"Строка {idx+2}: товар с EAN {ean} уже есть в партии, количество добавлено")
                        continue

                    product = Product(
                        ean=ean,
                        name=name,
                        model=model,
                        color=color,
                        size=size,
                        age=age,
                        fit=fit,
                        weight=weight,
                        quantity=quantity,
                        price_eur=price_eur,
                        exchange_rate=exchange_rate,
                        coefficient=coefficient,
                        logistics_per_kg=logistics_per_kg,
                        cost_price=cost_price,
                        batch_id=batch.id
                    )
                    db.add(product)
                    products.append(product)

                except Exception as e:
                    errors.append(f"Строка {idx+2}: {str(e)}")
                    continue

            if not products:
                db.rollback()
                error_msg = "Не удалось загрузить ни одного товара"
                if errors:
                    error_msg += "\n\nОшибки:\n" + "\n".join(errors[:5])
                    if len(errors) > 5:
                        error_msg += f"\n... и еще {len(errors)-5} ошибок"
                raise ValueError(error_msg)

            # Сохраняем продукты в БД чтобы получить их ID
            db.flush()

            # Теперь создаем записи в stock_log
            for product in products:
                stock_log = StockLog(
                    product_id=product.id,
                    operation_type='in',
                    quantity=product.quantity,
                    warehouse=warehouse,
                    reference_id=batch.id
                )
                db.add(stock_log)

            db.commit()

            # Логируем действие
            CoreService.log_action(
                db, created_by_id, 'batch_created',
                'batch', batch.id,
                f'Создана партия {batch_number} с {len(products)} товарами'
            )

            return batch, products

        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def set_retail_price(db: Session, product_id: int,
                        retail_price: float, changed_by_id: int) -> Product:
        """Установить розничную цену"""
        product = db.get(Product, product_id)
        if not product:
            raise ValueError("Товар не найден")

        # Сохраняем историю
        if product.retail_price:
            history = PriceHistory(
                product_id=product_id,
                old_price=product.retail_price,
                new_price=retail_price,
                changed_by_id=changed_by_id
            )
            db.add(history)

        product.retail_price = retail_price
        db.commit()

        # Логируем
        CoreService.log_action(
            db, changed_by_id, 'price_changed',
            'product', product_id,
            f'Цена изменена с {product.retail_price} на {retail_price}'
        )

        return product

    @staticmethod
    def create_sale(db: Session, product_id: int, agent_id: int,
                   sale_price: float, quantity: int = 1) -> Sale:
        """Создать продажу"""
        from sqlalchemy.orm import joinedload

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
            margin=total_margin,  # Общая маржа за все единицы
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

        # Рассчитываем бонус (используем общую маржу)
        bonus_amount, bonus_rule = CoreService.calculate_bonus(db, agent_id, total_margin)
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
        CoreService.log_action(
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
    def get_stock(db: Session, warehouse: str = None,
                 category: str = None, size: str = None) -> List[Dict]:
        """Получить остатки товаров"""
        from sqlalchemy import func, select

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
        CoreService.log_action(
            db, admin_id, 'bonuses_paid',
            'agent', agent_id,
            f'Выплачено бонусов на сумму {total_amount}'
        )

        return total_amount

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
        CoreService.log_action(
            db, admin_id, 'sale_returned',
            'sale', sale_id,
            f'Возврат продажи. Причина: {reason}'
        )

        return sale

    @staticmethod
    def search_products(db: Session, query: str) -> List[Dict]:
        """Поиск товаров с информацией об остатках"""
        search = f"%{query}%"

        # Подзапрос для подсчета проданного количества
        from sqlalchemy import func, select

        # Считаем проданное количество для каждого товара
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
    def generate_excel_template() -> bytes:
        """Генерация шаблона Excel для загрузки"""
        # Примеры данных
        sample_data = {
            'EAN': ['1234567890123', '2234567890123', '3234567890123'],
            'Наименование': [
                'Коньки хоккейные Bauer Vapor X3.7',
                'Клюшка CCM Ribcor Trigger 7',
                'Шлем Bauer Re-Akt 150'
            ],
            'Модель': ['Vapor X3.7', 'Ribcor Trigger 7', 'Re-Akt 150'],
            'Цвет': ['Black', 'Black/Red', 'White'],
            'Размер': ['42', '75', 'M'],
            'Возраст': ['SR', 'SR', 'SR'],
            'Фит': ['regular', 'tapered', 'regular'],
            'Вес': [1.5, 0.45, 0.6],
            'Кол-во': [10, 15, 8],
            'Цена в евро': [120.0, 180.0, 90.0],
            'Курс': [95.0, 95.0, 95.0],
            'Коэффициент': [1.2, 1.2, 1.2],
            'Логистика (на кг)': [500.0, 500.0, 500.0],
            'Склад': ['Олег', 'Олег', 'Максим']
        }

        df = pd.DataFrame(sample_data)

        # Сохраняем в bytes
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Товары', index=False)

            # Добавляем форматирование
            worksheet = writer.sheets['Товары']

            # Заголовки жирным
            from openpyxl.styles import Font, PatternFill, Alignment
            header_font = Font(bold=True)
            header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

            for cell in worksheet[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center')

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

        output.seek(0)
        return output.getvalue()

    @staticmethod
    def get_stock_optimized(db: Session, warehouse: str = None,
                           category: str = None, size: str = None) -> List[Dict]:
        """Получить остатки товаров (оптимизированная версия с CTE)"""
        from sqlalchemy import text

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
    def get_warehouse_list(db: Session) -> List[str]:
        """Получить список складов"""
        warehouses = db.query(Batch.warehouse).distinct().all()
        return [w[0] for w in warehouses]

    @staticmethod
    async def create_batch_from_excel_async(db: Session, file_path: str,
                                            warehouse: str, created_by_id: int) -> Tuple[Batch, List[Product]]:
        """Создать партию из Excel файла (асинхронная версия)"""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        # Выполняем блокирующую операцию в отдельном потоке
        with ThreadPoolExecutor() as executor:
            result = await asyncio.get_event_loop().run_in_executor(
                executor,
                CoreService.create_batch_from_excel,
                db, file_path, warehouse, created_by_id
            )
        return result

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