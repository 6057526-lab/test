#!/usr/bin/env python3
"""
Скрипт для миграции существующей БД
"""
import sqlite3
from pathlib import Path
from data.db import DATABASE_URL, init_db


def migrate_database():
    """Добавляет уникальное ограничение на EAN в рамках партии"""

    # Путь к БД
    db_path = DATABASE_URL.replace('sqlite:///', '')

    if not Path(db_path).exists():
        print("❌ БД не найдена. Создаем новую...")
        init_db()
        return

    print("🔧 Начинаем миграцию БД...")

    # Подключаемся к БД
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем, есть ли уже такое ограничение
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)
        table_sql = cursor.fetchone()[0]

        if 'unique_ean_per_batch' not in table_sql:
            print("📝 Добавляем уникальное ограничение на EAN в рамках партии...")

            # SQLite не поддерживает ALTER TABLE ADD CONSTRAINT
            # Поэтому создаем новую таблицу с ограничением

            # 1. Переименовываем старую таблицу
            cursor.execute("ALTER TABLE products RENAME TO products_old")

            # 2. Создаем новую таблицу с ограничением
            cursor.execute("""
                CREATE TABLE products (
                    id INTEGER NOT NULL PRIMARY KEY,
                    ean VARCHAR(13) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    model VARCHAR(100),
                    color VARCHAR(50),
                    size VARCHAR(20),
                    age VARCHAR(20),
                    fit VARCHAR(20),
                    weight FLOAT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price_eur FLOAT NOT NULL,
                    exchange_rate FLOAT NOT NULL,
                    coefficient FLOAT NOT NULL,
                    logistics_per_kg FLOAT NOT NULL,
                    cost_price FLOAT NOT NULL,
                    retail_price FLOAT,
                    batch_id INTEGER NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES batches (id),
                    CONSTRAINT unique_ean_per_batch UNIQUE (ean, batch_id),
                    CONSTRAINT check_quantity_positive CHECK (quantity >= 0),
                    CONSTRAINT check_price_positive CHECK (price_eur >= 0),
                    CONSTRAINT check_weight_positive CHECK (weight > 0),
                    CONSTRAINT check_fit_type CHECK (fit IN ('regular', 'tapered', 'wide'))
                )
            """)

            # 3. Копируем данные
            cursor.execute("""
                INSERT INTO products SELECT * FROM products_old
            """)

            # 4. Удаляем старую таблицу
            cursor.execute("DROP TABLE products_old")

            # 5. Создаем индекс на EAN для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_products_ean ON products (ean)")

            print("✅ Ограничение добавлено успешно!")
        else:
            print("✅ Ограничение уже существует")

        # Проверяем и исправляем дубликаты EAN в существующих партиях
        cursor.execute("""
            SELECT ean, batch_id, COUNT(*) as cnt 
            FROM products 
            GROUP BY ean, batch_id 
            HAVING cnt > 1
        """)

        duplicates = cursor.fetchall()
        if duplicates:
            print(f"⚠️  Найдено {len(duplicates)} дубликатов EAN в партиях")
            for ean, batch_id, count in duplicates:
                print(f"   EAN: {ean}, Партия: {batch_id}, Количество: {count}")

            # Здесь можно добавить логику для обработки дубликатов
            # Например, объединение количества или удаление

        conn.commit()
        print("✅ Миграция завершена успешно!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка при миграции: {e}")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()