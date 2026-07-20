"""
Tests for restocking recommendation and order endpoints.
"""
from datetime import datetime

import pytest


class TestRestockingRecommendations:
    """Test suite for the restocking recommendations endpoint."""

    def test_recommendations_structure(self, client):
        """Test that recommendations response has the expected structure."""
        response = client.get("/api/restocking/recommendations?budget=10000")
        assert response.status_code == 200

        data = response.json()
        assert "budget" in data
        assert "recommended_items" in data
        assert "total_cost" in data
        assert "remaining_budget" in data
        assert "skipped_item_skus" in data
        assert isinstance(data["recommended_items"], list)

        for item in data["recommended_items"]:
            assert "item_sku" in item
            assert "item_name" in item
            assert "trend" in item
            assert "suggested_quantity" in item
            assert "unit_cost" in item
            assert "line_total" in item
            assert isinstance(item["suggested_quantity"], int)
            assert isinstance(item["unit_cost"], (int, float))

    def test_zero_budget_returns_no_items(self, client):
        """Test that a zero budget yields no recommendations."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["recommended_items"] == []
        assert data["total_cost"] == 0

    def test_negative_budget_returns_400(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400

    def test_increasing_trend_items_prioritized(self, client):
        """Test that increasing-trend items always precede stable/decreasing ones."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()

        trends = [item["trend"] for item in data["recommended_items"]]
        first_non_increasing = next(
            (i for i, t in enumerate(trends) if t != "increasing"), len(trends)
        )
        # Every "increasing" item must appear before every non-increasing item
        assert all(t == "increasing" for t in trends[:first_non_increasing])
        assert all(t != "increasing" for t in trends[first_non_increasing:])

    def test_within_trend_tier_sorted_by_largest_gap_first(self, client):
        """Test that items within the same trend tier are sorted by descending suggested quantity."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()

        for trend in ("increasing", "stable", "decreasing"):
            quantities = [
                item["suggested_quantity"]
                for item in data["recommended_items"]
                if item["trend"] == trend
            ]
            assert quantities == sorted(quantities, reverse=True)

    def test_greedy_skips_unaffordable_item_and_continues(self, client):
        """Test that an item too expensive for the budget is skipped (not
        reordered ahead of cheaper items) while the greedy walk continues
        through the rest of the priority-sorted list (classic greedy, not
        knapsack: it never revisits a skip to backfill it)."""
        # WDG-001 (increasing, gap 150 @ $45 = $6750) is the highest-priority
        # candidate and far exceeds this budget, so it's skipped. BRG-102
        # (stable, gap 2 @ $32 = $64) still fits out of what's left and gets
        # included - proving the walk continues past a skip instead of
        # stopping, while WDG-001 itself is never pulled in later.
        response = client.get("/api/restocking/recommendations?budget=100")
        data = response.json()

        assert "WDG-001" in data["skipped_item_skus"]
        recommended_skus = [item["item_sku"] for item in data["recommended_items"]]
        assert "WDG-001" not in recommended_skus
        assert "BRG-102" in recommended_skus

    def test_non_positive_gap_items_never_recommended(self, client):
        """Test that items with forecasted_demand <= current_demand are never
        recommended regardless of budget (e.g. the decreasing-trend item)."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()

        recommended_skus = [item["item_sku"] for item in data["recommended_items"]]
        assert "MTR-304" not in recommended_skus

    def test_total_cost_matches_sum_of_recommended_items(self, client):
        """Test that total_cost equals the sum of recommended line totals."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()

        calculated_total = sum(item["line_total"] for item in data["recommended_items"])
        assert abs(data["total_cost"] - calculated_total) < 0.01
        assert abs(data["remaining_budget"] - (data["budget"] - data["total_cost"])) < 0.01


class TestRestockingOrders:
    """Test suite for creating and listing restocking orders."""

    def test_create_order_success(self, client):
        """Test submitting a valid restocking order."""
        recommendations = client.get("/api/restocking/recommendations?budget=10000").json()
        items = [
            {
                "sku": item["item_sku"],
                "name": item["item_name"],
                "quantity": item["suggested_quantity"],
                "unit_cost": item["unit_cost"],
                "line_total": item["line_total"]
            }
            for item in recommendations["recommended_items"]
        ]

        response = client.post(
            "/api/restocking/orders",
            json={"budget": recommendations["budget"], "items": items}
        )
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith(f"RESTOCK-{datetime.now().year}-")
        assert order["status"] == "Submitted"
        assert order["lead_time_days"] == 14
        assert len(order["items"]) == len(items)

        created = datetime.fromisoformat(order["created_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery_date"])
        assert (expected_delivery - created).days == 14

    def test_create_order_empty_items_returns_400(self, client):
        """Test that submitting an order with no items is rejected."""
        response = client.post(
            "/api/restocking/orders",
            json={"budget": 1000, "items": []}
        )
        assert response.status_code == 400

    def test_list_orders_reflects_creation(self, client):
        """Test that a newly created order appears in the orders list."""
        before = client.get("/api/restocking/orders").json()

        response = client.post(
            "/api/restocking/orders",
            json={
                "budget": 100,
                "items": [
                    {"sku": "WDG-001", "name": "Industrial Widget Type A",
                     "quantity": 10, "unit_cost": 45.0, "line_total": 450.0}
                ]
            }
        )
        assert response.status_code == 201
        created_order = response.json()

        after = client.get("/api/restocking/orders").json()
        assert len(after) == len(before) + 1
        assert any(o["id"] == created_order["id"] for o in after)
