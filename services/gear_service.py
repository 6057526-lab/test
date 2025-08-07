"""
Сервис для подбора хоккейной экипировки
"""
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from data.models import Product, Batch


class GearService:
    """Сервис для подбора хоккейной экипировки"""

    # === КОНСТАНТЫ ДЛЯ ПОДБОРА ===
    POSITIONS = {
        'goalie': 'Вратарь',
        'defender': 'Защитник', 
        'forward': 'Нападающий',
        'all': 'Любая позиция'
    }
    
    SKILL_LEVELS = {
        'beginner': 'Новичок',
        'amateur': 'Любитель',
        'professional': 'Профессионал'
    }
    
    AGE_GROUPS = {
        'kids': 'Дети (до 12 лет)',
        'youth': 'Юниоры (13-17 лет)',
        'adult': 'Взрослые (18+)'
    }

    # === ГОТОВЫЕ КОМПЛЕКТЫ ===
    GEAR_KITS = {
        'goalie_full': {
            'name': 'Полная экипировка вратаря',
            'description': 'Все необходимое для вратаря',
            'items': ['шлем', 'нагрудник', 'блокер', 'ловушка', 'панты', 'щитки'],
            'position': 'goalie'
        },
        'player_basic': {
            'name': 'Базовая защита игрока',
            'description': 'Основная защита для полевого игрока',
            'items': ['шлем', 'нагрудник', 'налокотники', 'перчатки', 'панты'],
            'position': 'all'
        },
        'player_pro': {
            'name': 'Профессиональный комплект',
            'description': 'Полная защита для серьезных игроков',
            'items': ['шлем', 'нагрудник', 'налокотники', 'перчатки', 'панты', 'щитки', 'ракушка'],
            'position': 'all'
        }
    }

    @staticmethod
    def get_gear_questionnaire() -> Dict:
        """Получить структуру анкеты для подбора экипировки"""
        return {
            'position': {
                'question': '🎯 Выберите позицию игрока:',
                'options': GearService.POSITIONS,
                'required': True
            },
            'skill_level': {
                'question': '🏆 Уровень игры:',
                'options': GearService.SKILL_LEVELS,
                'required': True
            },
            'age_group': {
                'question': '👤 Возрастная группа:',
                'options': GearService.AGE_GROUPS,
                'required': True
            },
            'budget': {
                'question': '💰 Бюджет (в рублях):',
                'type': 'number',
                'required': False
            },
            'size_preferences': {
                'question': '📏 Есть ли предпочтения по размеру?',
                'type': 'text',
                'required': False
            }
        }

    @staticmethod
    def get_gear_kits() -> Dict:
        """Получить список готовых комплектов экипировки"""
        return GearService.GEAR_KITS

    @staticmethod
    def search_gear_by_kit(db: Session, kit_id: str) -> List[Dict]:
        """Поиск товаров для готового комплекта"""
        if kit_id not in GearService.GEAR_KITS:
            return []
        
        kit = GearService.GEAR_KITS[kit_id]
        items = kit['items']
        
        # Поиск товаров по ключевым словам в названии
        products = []
        for item in items:
            query = db.query(Product).join(Batch).filter(
                and_(
                    Product.quantity > 0,
                    or_(
                        func.lower(Product.name).contains(func.lower(item)),
                        func.lower(Product.name).contains('хоккей'),
                        func.lower(Product.name).contains('hockey')
                    )
                )
            ).limit(5).all()
            
            for product in query:
                products.append({
                    'id': product.id,
                    'name': product.name,
                    'size': product.size,
                    'age': product.age,
                    'price': product.retail_price or product.price_eur,
                    'stock': product.quantity,
                    'warehouse': product.batch.warehouse,
                    'category': item
                })
        
        return products

    @staticmethod
    def search_gear_by_questionnaire(db: Session, answers: Dict) -> List[Dict]:
        """Поиск экипировки по ответам анкеты"""
        position = answers.get('position', 'all')
        skill_level = answers.get('skill_level', 'amateur')
        age_group = answers.get('age_group', 'adult')
        budget = answers.get('budget')
        
        # Базовые фильтры
        filters = [Product.quantity > 0]
        
        # Фильтр по возрасту
        if age_group == 'kids':
            filters.append(Product.age.in_(['kids', 'youth']))
        elif age_group == 'youth':
            filters.append(Product.age.in_(['youth', 'adult']))
        elif age_group == 'adult':
            filters.append(Product.age == 'adult')
        
        # Фильтр по позиции (если указана)
        if position != 'all':
            position_keywords = {
                'goalie': ['вратарь', 'goalie', 'блокер', 'ловушка', 'щитки'],
                'defender': ['защитник', 'defender', 'нагрудник'],
                'forward': ['нападающий', 'forward', 'налокотники']
            }
            
            if position in position_keywords:
                keywords = position_keywords[position]
                name_filters = []
                for keyword in keywords:
                    name_filters.append(func.lower(Product.name).contains(func.lower(keyword)))
                filters.append(or_(*name_filters))
        
        # Фильтр по бюджету
        if budget:
            filters.append(Product.retail_price <= budget)
        
        # Фильтр по уровню (качество товара)
        quality_filters = {
            'beginner': ['базовый', 'начальный', 'basic'],
            'amateur': ['любительский', 'amateur', 'средний'],
            'professional': ['профессиональный', 'pro', 'elite']
        }
        
        if skill_level in quality_filters:
            keywords = quality_filters[skill_level]
            quality_name_filters = []
            for keyword in keywords:
                quality_name_filters.append(func.lower(Product.name).contains(func.lower(keyword)))
            filters.append(or_(*quality_name_filters))
        
        # Выполняем поиск
        query = db.query(Product).join(Batch).filter(and_(*filters))
        
        # Группируем по категориям
        products = query.all()
        categorized = {}
        
        for product in products:
            category = GearService._categorize_product(product.name)
            if category not in categorized:
                categorized[category] = []
            
            categorized[category].append({
                'id': product.id,
                'name': product.name,
                'size': product.size,
                'age': product.age,
                'price': product.retail_price or product.price_eur,
                'stock': product.quantity,
                'warehouse': product.batch.warehouse,
                'category': category
            })
        
        # Возвращаем лучшие варианты по каждой категории
        result = []
        for category, items in categorized.items():
            # Сортируем по цене и берем лучшие варианты
            sorted_items = sorted(items, key=lambda x: x['price'])
            result.extend(sorted_items[:3])  # Топ-3 по каждой категории
        
        return result

    @staticmethod
    def _categorize_product(name: str) -> str:
        """Определить категорию товара по названию"""
        name_lower = name.lower()
        
        if any(word in name_lower for word in ['шлем', 'helmet']):
            return 'шлем'
        elif any(word in name_lower for word in ['нагрудник', 'chest']):
            return 'нагрудник'
        elif any(word in name_lower for word in ['налокотники', 'elbow']):
            return 'налокотники'
        elif any(word in name_lower for word in ['перчатки', 'glove']):
            return 'перчатки'
        elif any(word in name_lower for word in ['панты', 'pant']):
            return 'панты'
        elif any(word in name_lower for word in ['щитки', 'shin']):
            return 'щитки'
        elif any(word in name_lower for word in ['блокер', 'blocker']):
            return 'блокер'
        elif any(word in name_lower for word in ['ловушка', 'catch']):
            return 'ловушка'
        elif any(word in name_lower for word in ['ракушка', 'cup']):
            return 'ракушка'
        else:
            return 'другое'

    @staticmethod
    def get_gear_recommendations(db: Session, product_id: int) -> List[Dict]:
        """Получить рекомендации по совместимым товарам"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return []
        
        category = GearService._categorize_product(product.name)
        
        # Ищем совместимые товары
        compatible_categories = {
            'шлем': ['нагрудник', 'налокотники'],
            'нагрудник': ['шлем', 'налокотники', 'перчатки'],
            'налокотники': ['нагрудник', 'перчатки', 'панты'],
            'перчатки': ['налокотники', 'панты'],
            'панты': ['налокотники', 'щитки'],
            'щитки': ['панты']
        }
        
        if category not in compatible_categories:
            return []
        
        compatible = []
        for comp_category in compatible_categories[category]:
            items = GearService._search_by_category(db, comp_category, product.age, product.size)
            compatible.extend(items[:2])  # Топ-2 совместимых товара
        
        return compatible

    @staticmethod
    def _search_by_category(db: Session, category: str, age: str, size: str) -> List[Dict]:
        """Поиск товаров по категории с учетом возраста и размера"""
        query = db.query(Product).join(Batch).filter(
            and_(
                Product.quantity > 0,
                Product.age == age,
                Product.size == size
            )
        )
        
        # Фильтруем по ключевым словам категории
        category_keywords = {
            'шлем': ['шлем', 'helmet'],
            'нагрудник': ['нагрудник', 'chest'],
            'налокотники': ['налокотники', 'elbow'],
            'перчатки': ['перчатки', 'glove'],
            'панты': ['панты', 'pant'],
            'щитки': ['щитки', 'shin']
        }
        
        if category in category_keywords:
            keywords = category_keywords[category]
            name_filters = []
            for keyword in keywords:
                name_filters.append(func.lower(Product.name).contains(func.lower(keyword)))
            query = query.filter(or_(*name_filters))
        
        products = query.limit(5).all()
        
        return [{
            'id': p.id,
            'name': p.name,
            'price': p.retail_price or p.price_eur,
            'stock': p.quantity,
            'category': category
        } for p in products]
