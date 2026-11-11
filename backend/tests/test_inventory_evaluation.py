
import pytest

from recommendation_engine import evaluate_warehouse_inventory


@pytest.fixture
def warehouse():
    return {
        "id": 1,
        "name": "Test Warehouse",
        "food": 1300,
        "water": 2600,
        "medicine": 450
    }


def test_full_stock_coverage(warehouse):
    requirements = {
        "food": 500,
        "water": 1000,
        "medicine": 100
    }

    result = evaluate_warehouse_inventory(
        warehouse, requirements
    )

    assert result["stock_status"] == "full"
    assert result["coverage_percent"] == 100.0
    assert result["shortages"] == {
        "food": 0,
        "water": 0,
        "medicine": 0
    }


def test_partial_stock_coverage(warehouse):
    requirements = {
        "food": 2000,
        "water": 3000,
        "medicine": 600
    }

    result = evaluate_warehouse_inventory(
        warehouse, requirements
    )

    assert result["stock_status"] == "partial"
    assert result["coverage_percent"] == pytest.approx(75.6)
    assert result["shortages"] == {
        "food": 700,
        "water": 400,
        "medicine": 150
    }


def test_insufficient_stock():
    warehouse = {
        "name": "Empty Warehouse",
        "food": 0,
        "water": 0,
        "medicine": 0
    }

    result = evaluate_warehouse_inventory(
        warehouse,
        {"food": 100, "water": 200, "medicine": 10}
    )

    assert result["stock_status"] == "insufficient"
    assert result["coverage_percent"] == 0.0


def test_negative_requirements_rejected(warehouse):
    with pytest.raises(ValueError):
        evaluate_warehouse_inventory(
            warehouse,
            {"food": -10, "water": 100, "medicine": 0}
        )


def test_zero_requirements_rejected(warehouse):
    with pytest.raises(ValueError):
        evaluate_warehouse_inventory(
            warehouse,
            {"food": 0, "water": 0, "medicine": 0}
        )
