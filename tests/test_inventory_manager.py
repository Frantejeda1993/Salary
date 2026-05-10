import pandas as pd
import pytest

from inventory_manager import (
    InventoryManager,
    MultiColumnMappingError,
    REQUIRED_VENTAS_COLUMNS,
)


def test_required_ventas_columns_include_sales_metrics_and_margin():
    assert {
        "Nombre Cliente",
        "Año Factura",
        "Mes Factura",
        "Importe Neto",
        "Unidades Venta",
        "Margen",
    }.issubset(REQUIRED_VENTAS_COLUMNS)


def test_validate_all_inputs_reports_ventas_and_stock_together():
    manager = InventoryManager()
    manager.ventas_df = pd.DataFrame({"Artículo": ["sku-1"]})
    manager.stock_df = pd.DataFrame({"Artículo": ["sku-1"]})

    with pytest.raises(MultiColumnMappingError) as exc_info:
        manager._validate_all_inputs({})

    assert [error.input_name for error in exc_info.value.errors] == ["Ventas", "Stock"]
    assert "Clave 1" in exc_info.value.errors[0].missing
    assert "Situación" in exc_info.value.errors[1].missing


def test_calculate_compras_accepts_manual_overrides_and_renames_to_canonical_columns():
    manager = InventoryManager(meses_compras=2)
    manager.current_year = 2026
    manager.current_month = 5
    manager.ventas_df = pd.DataFrame(
        {
            "sku": ["sku-1", "sku-1"],
            "brand": ["brand", "brand"],
            "desc": ["description", "description"],
            "cost": [10.0, 12.0],
            "client_name": ["client", "client"],
            "year": [2026, 2025],
            "month": [5, 5],
            "net": [100.0, 200.0],
            "units": [4, 8],
            "margin_value": [2.0, 3.0],
        }
    )
    manager.stock_df = pd.DataFrame(
        {
            "sku": ["sku-1"],
            "status": [None],
            "stock_units": [1],
            "orders": [0],
            "reserved": [0],
            "pending_purchase": [0],
            "pending_fab": [0],
            "in_transit": [0],
        }
    )

    result = manager.calculate_compras(
        column_overrides={
            "Ventas": {
                "Artículo": "sku",
                "Clave 1": "brand",
                "Descripción Artículo": "desc",
                "Precio Coste": "cost",
                "Nombre Cliente": "client_name",
                "Año Factura": "year",
                "Mes Factura": "month",
                "Importe Neto": "net",
                "Unidades Venta": "units",
                "Margen": "margin_value",
            },
            "Stock": {
                "Artículo": "sku",
                "Situación": "status",
                "Stock": "stock_units",
                "Cartera": "orders",
                "Reservas": "reserved",
                "Pendiente Recibir Compra": "pending_purchase",
                "Pendiente Entrar Fabricación": "pending_fab",
                "En Tránsito": "in_transit",
            },
        }
    )

    row = result.iloc[0]
    assert row["SKU"] == "sku-1"
    assert row["Marca"] == "brand"
    assert row["Precio Compra"] == 11.0
    assert row["Margen"] == 2.5
    assert row["Stock Unidades"] == 1
