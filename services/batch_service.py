"""
Сервис для работы с партиями товаров
"""
from datetime import datetime
from typing import List, Tuple
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from data.models import Batch, Product, StockLog, ActionLog
from config import EXCEL_TEMPLATE_COLUMNS, LOG_ACTIONS


class BatchService:
    """Сервис для работы с партиями товаров"""

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
            ean_first_row_index = {}

            for idx, row in df.iterrows():
                try:
                    # Валидация данных
                    if pd.isna(row['EAN']) or str(row['EAN']).strip() == '':
                        errors.append(f"Строка {idx+2}: отсутствует EAN")
                        continue

                    # Преобразуем типы данных
                    ean = str(row['EAN']).strip()

                    # Проверка на дубликаты в текущем файле
                    if ean in ean_first_row_index:
                        first_seen_row = ean_first_row_index[ean]
                        errors.append(
                            f"Строка {idx+2}: дубликат EAN {ean} (уже встречался в строке {first_seen_row})"
                        )
                        continue
                    else:
                        ean_first_row_index[ean] = idx + 2

                    name = str(row['Наименование']).strip() if not pd.isna(row['Наименование']) else 'Без названия'
                    model = str(row['Модель']).strip() if not pd.isna(row['Модель']) else ''
                    color = str(row['Цвет']).strip() if not pd.isna(row['Цвет']) else ''
                    size = str(row['Размер']).strip() if not pd.isna(row['Размер']) else ''
                    age = str(row['Возраст']).strip() if not pd.isna(row['Возраст']) else ''
                    fit = str(row['Фит']).lower().strip() if not pd.isna(row['Фит']) else 'regular'

                    # Числовые поля с валидацией
                    weight = float(row['Вес']) if not pd.isna(row['Вес']) else 0.1
                    if weight <= 0:
                        weight = 0.1

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
            BatchService.log_action(
                db, created_by_id, 'batch_created',
                'batch', batch.id,
                f'Создана партия {batch_number} с {len(products)} товарами'
            )

            return batch, products

        except Exception as e:
            db.rollback()
            raise e

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
