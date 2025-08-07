"""
Основной сервис - фасад для всех бизнес-операций
"""
from services.batch_service import BatchService
from services.sales_service import SalesService
from services.stock_service import StockService
from services.price_service import PriceService
from services.report_service import ReportService
from services.agent_service import AgentService
from services.gear_service import GearService


class CoreService:
    """
    Основной сервис - фасад для всех бизнес-операций.
    
    Этот класс предоставляет единую точку входа для всех бизнес-операций,
    делегируя выполнение соответствующим специализированным сервисам.
    """

    # === АГЕНТЫ ===
    get_or_create_agent = staticmethod(AgentService.get_or_create_agent)

    # === ПАРТИИ ===
    create_batch_from_excel = staticmethod(BatchService.create_batch_from_excel)
    generate_excel_template = staticmethod(BatchService.generate_excel_template)
    log_action = staticmethod(BatchService.log_action)

    # === ПРОДАЖИ ===
    create_sale = staticmethod(SalesService.create_sale)
    calculate_bonus = staticmethod(SalesService.calculate_bonus)
    get_agent_bonuses = staticmethod(SalesService.get_agent_bonuses)
    pay_bonuses = staticmethod(SalesService.pay_bonuses)
    return_sale = staticmethod(SalesService.return_sale)
    get_last_sale_price = staticmethod(SalesService.get_last_sale_price)
    get_agent_sales_history = staticmethod(SalesService.get_agent_sales_history)

    # === ОСТАТКИ И ПОИСК ===
    get_stock = staticmethod(StockService.get_stock)
    get_stock_optimized = staticmethod(StockService.get_stock_optimized)
    search_products = staticmethod(StockService.search_products)
    get_product_info = staticmethod(StockService.get_product_info)
    get_warehouse_list = staticmethod(StockService.get_warehouse_list)
    
    # Фильтрация
    get_available_filter_values = staticmethod(StockService.get_available_filter_values)
    get_product_categories_in_stock = staticmethod(StockService.get_product_categories_in_stock)
    get_available_sizes_in_stock = staticmethod(StockService.get_available_sizes_in_stock)
    get_available_ages_in_stock = staticmethod(StockService.get_available_ages_in_stock)
    get_warehouses_with_stock = staticmethod(StockService.get_warehouses_with_stock)
    get_products_by_category = staticmethod(StockService.get_products_by_category)
    get_products_by_size = staticmethod(StockService.get_products_by_size)
    get_products_by_age = staticmethod(StockService.get_products_by_age)
    get_products_by_warehouse = staticmethod(StockService.get_products_by_warehouse)
    get_all_products_in_stock = staticmethod(StockService.get_all_products_in_stock)

    # === ЦЕНЫ ===
    set_retail_price = staticmethod(PriceService.set_retail_price)
    bulk_update_retail_price_by_ids = staticmethod(PriceService.bulk_update_retail_price_by_ids)
    preview_bulk_price_update = staticmethod(PriceService.preview_bulk_price_update)
    select_products_for_bulk_pricing = staticmethod(PriceService.select_products_for_bulk_pricing)

    # === ОТЧЕТЫ И ГРАФИКИ ===
    get_sales_report = staticmethod(ReportService.get_sales_report)
    get_sales_timeseries = staticmethod(ReportService.get_sales_timeseries)
    get_margin_by_category = staticmethod(ReportService.get_margin_by_category)
    get_product_price_timeseries = staticmethod(ReportService.get_product_price_timeseries)
    get_product_sales_timeseries = staticmethod(ReportService.get_product_sales_timeseries)

    # === ПОДБОР ЭКИПИРОВКИ ===
    get_gear_questionnaire = staticmethod(GearService.get_gear_questionnaire)
    get_gear_kits = staticmethod(GearService.get_gear_kits)
    search_gear_by_kit = staticmethod(GearService.search_gear_by_kit)
    search_gear_by_questionnaire = staticmethod(GearService.search_gear_by_questionnaire)
    get_gear_recommendations = staticmethod(GearService.get_gear_recommendations)