from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache
from math import pi, sin
from random import Random
from typing import Iterable


TENANT_IDS = ("tenant_northstar", "tenant_apex")
REGIONS = ("North America", "EMEA", "APAC", "LATAM")
SEGMENTS = ("enterprise", "wholesale", "regional")
DEMO_RISK_SKU = "NSI-VAL-100"
DEMO_DECLINING_CUSTOMERS = (
    "tenant_northstar_customer_declining_anchor",
    "tenant_northstar_customer_declining_concentrated",
)


@dataclass(frozen=True)
class Product:
    tenant_id: str
    product_id: str
    sku: str
    name: str
    category: str
    base_weekly_demand: int
    unit_price: float


@dataclass(frozen=True)
class Customer:
    tenant_id: str
    customer_id: str
    name: str
    segment: str
    region: str
    reliability: float
    revenue_weight: float
    demo_profile: str = "standard"


@dataclass(frozen=True)
class OrderRecord:
    tenant_id: str
    tenant_name: str
    product_id: str
    sku: str
    product_name: str
    customer_id: str
    customer_name: str
    customer_segment: str
    region: str
    order_date: str
    quantity: int
    unit_price: float
    promotion: bool
    stockout: bool
    lead_time_days: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SyntheticDataset:
    products: tuple[Product, ...]
    customers: tuple[Customer, ...]
    orders: tuple[OrderRecord, ...]

    def tenant_names(self) -> dict[str, str]:
        return {
            "tenant_northstar": "Northstar Industrial",
            "tenant_apex": "Apex Distribution",
        }


def _week_start(index: int) -> date:
    return date(2024, 1, 1) + timedelta(days=index * 7)


def _tenant_name(tenant_id: str) -> str:
    return {
        "tenant_northstar": "Northstar Industrial",
        "tenant_apex": "Apex Distribution",
    }.get(tenant_id, tenant_id)


def _product_sku(tenant_id: str, category: str, index: int) -> str:
    prefix = "NSI" if tenant_id == "tenant_northstar" else "APX"
    return f"{prefix}-{category[:3].upper()}-{100 + index}"


def _build_products(rng: Random, tenant_id: str, count: int) -> list[Product]:
    categories = (
        "valves",
        "pumps",
        "filters",
        "sensors",
        "controllers",
        "bearings",
        "actuators",
        "compressors",
        "gaskets",
        "motors",
    )
    products: list[Product] = []
    for index in range(count):
        category = categories[index % len(categories)]
        sku = _product_sku(tenant_id, category, index)
        base_weekly_demand = rng.randint(38, 124)
        unit_price = round(rng.uniform(28, 340), 2)
        if tenant_id == "tenant_northstar" and index == 0:
            base_weekly_demand = 124
            unit_price = 184.0
        products.append(
            Product(
                tenant_id=tenant_id,
                product_id=f"{tenant_id}_product_{index + 1}",
                sku=sku,
                name=f"{category.title()} Kit {index + 1}",
                category=category,
                base_weekly_demand=base_weekly_demand,
                unit_price=unit_price,
            )
        )
    return products


def _build_customers(rng: Random, tenant_id: str, count: int) -> list[Customer]:
    names = (
        "Atlas Manufacturing",
        "Beacon Supply",
        "Cobalt Works",
        "Delta Assembly",
        "Evergreen Logistics",
        "Forge Partners",
        "Granite Systems",
        "Harbor Components",
        "Ion Fabrication",
        "Juniper Equipment",
    )
    customers: list[Customer] = []
    for index in range(count):
        segment = SEGMENTS[index % len(SEGMENTS)]
        region = REGIONS[(index + (0 if tenant_id == "tenant_northstar" else 1)) % len(REGIONS)]
        top_customer = index < max(8, count // 20)
        strategic_customer = index < max(24, count // 8)
        customers.append(
            Customer(
                tenant_id=tenant_id,
                customer_id=f"{tenant_id}_customer_{index + 1}",
                name=f"{names[index % len(names)]} {index + 1}",
                segment=segment,
                region=region,
                reliability=round(rng.uniform(0.86, 1.18), 3),
                revenue_weight=round(
                    rng.uniform(4.2, 7.5) if top_customer else rng.uniform(1.75, 3.2) if strategic_customer else rng.uniform(0.42, 1.2),
                    3,
                ),
            )
        )
    if tenant_id == "tenant_northstar" and count >= 2:
        customers[0] = Customer(
            tenant_id=tenant_id,
            customer_id=DEMO_DECLINING_CUSTOMERS[0],
            name="Atlas Manufacturing Strategic",
            segment="enterprise",
            region="North America",
            reliability=1.14,
            revenue_weight=7.8,
            demo_profile="declining",
        )
        customers[1] = Customer(
            tenant_id=tenant_id,
            customer_id=DEMO_DECLINING_CUSTOMERS[1],
            name="Beacon Supply National",
            segment="wholesale",
            region="North America",
            reliability=1.08,
            revenue_weight=6.9,
            demo_profile="declining",
        )
    return customers


def _customer_product_portfolio(
    tenant_products: list[Product],
    customer_index: int,
    customer: Customer,
) -> list[Product]:
    """Return a stable subset of SKUs with broader coverage for top customers."""
    if customer.demo_profile == "declining":
        portfolio_size = 18
    elif customer_index < 10:
        portfolio_size = 24
    elif customer_index < 40:
        portfolio_size = 14
    else:
        portfolio_size = 7
    product_count = len(tenant_products)
    stride = 7 + (customer_index % 5)
    selected_indexes = {
        (customer_index * 3 + offset * stride) % product_count
        for offset in range(min(portfolio_size, product_count))
    }
    if customer.tenant_id == "tenant_northstar":
        selected_indexes.add(0)
    return [tenant_products[index] for index in sorted(selected_indexes)]


def _demo_decline_multiplier(customer: Customer, week_index: int, weeks: int) -> float:
    if customer.demo_profile != "declining":
        return 1.0
    start = int(weeks * 0.58)
    if week_index < start:
        return 1.0
    progress = (week_index - start) / max(1, weeks - start - 1)
    floor = 0.34 if customer.customer_id == DEMO_DECLINING_CUSTOMERS[0] else 0.46
    return max(floor, 1.0 - progress * (1.0 - floor))


def generate_synthetic_erp_dataset(
    seed: int = 42,
    weeks: int = 104,
    products_per_tenant: int = 50,
    customers_per_tenant: int = 200,
) -> SyntheticDataset:
    """Generate realistic-enough B2B ERP order history for the demo."""
    rng = Random(seed)
    products: list[Product] = []
    customers: list[Customer] = []
    orders: list[OrderRecord] = []

    for tenant_id in TENANT_IDS:
        tenant_products = _build_products(rng, tenant_id, products_per_tenant)
        tenant_customers = _build_customers(rng, tenant_id, customers_per_tenant)
        products.extend(tenant_products)
        customers.extend(tenant_customers)

        for week_index in range(weeks):
            week = _week_start(week_index)
            seasonal = 1.0 + 0.18 * sin((2 * pi * week_index) / 52)
            quarter_end = week_index % 13 in (11, 12)

            for customer_index, customer in enumerate(tenant_customers):
                customer_portfolio = _customer_product_portfolio(tenant_products, customer_index, customer)
                for product_index, product in enumerate(customer_portfolio):
                    original_product_index = tenant_products.index(product)
                    product_cycle = 1.0 + 0.08 * sin((2 * pi * (week_index + original_product_index * 3)) / 26)
                    promotion = (week_index + original_product_index) % 17 == 0 or quarter_end
                    stockout = (week_index + original_product_index + customer_index) % 53 == 0
                    segment_multiplier = {
                        "enterprise": 1.32,
                        "wholesale": 0.93,
                        "regional": 0.62,
                    }[customer.segment]
                    region_multiplier = {
                        "North America": 1.08,
                        "EMEA": 0.98,
                        "APAC": 1.16,
                        "LATAM": 0.91,
                    }[customer.region]
                    promo_multiplier = 1.28 if promotion else 1.0
                    stockout_multiplier = 0.48 if stockout else 1.0
                    demo_decline_multiplier = (
                        _demo_decline_multiplier(customer, week_index, weeks)
                        if product.sku == DEMO_RISK_SKU
                        else 1.0
                    )
                    noise = rng.uniform(0.82, 1.22)
                    raw_quantity = (
                        product.base_weekly_demand
                        * seasonal
                        * product_cycle
                        * segment_multiplier
                        * region_multiplier
                        * customer.reliability
                        * customer.revenue_weight
                        * promo_multiplier
                        * stockout_multiplier
                        * demo_decline_multiplier
                        * noise
                        / 18
                    )
                    quantity = max(0, round(raw_quantity))
                    if quantity == 0:
                        continue

                    orders.append(
                        OrderRecord(
                            tenant_id=tenant_id,
                            tenant_name=_tenant_name(tenant_id),
                            product_id=product.product_id,
                            sku=product.sku,
                            product_name=product.name,
                            customer_id=customer.customer_id,
                            customer_name=customer.name,
                            customer_segment=customer.segment,
                            region=customer.region,
                            order_date=week.isoformat(),
                            quantity=quantity,
                            unit_price=product.unit_price,
                            promotion=promotion,
                            stockout=stockout,
                            lead_time_days=rng.randint(3, 21) + (7 if stockout else 0),
                        )
                    )

    return SyntheticDataset(tuple(products), tuple(customers), tuple(orders))


@lru_cache(maxsize=1)
def get_default_dataset() -> SyntheticDataset:
    return generate_synthetic_erp_dataset()


def filter_orders(
    orders: Iterable[OrderRecord],
    tenant_id: str,
    sku: str | None = None,
    customer_segment: str = "all",
) -> list[OrderRecord]:
    normalized_segment = customer_segment.lower()
    return [
        order
        for order in orders
        if order.tenant_id == tenant_id
        and (sku is None or order.sku == sku)
        and (normalized_segment == "all" or order.customer_segment == normalized_segment)
    ]


def weekly_series(orders: Iterable[OrderRecord]) -> list[dict[str, object]]:
    weekly: dict[str, int] = {}
    for order in orders:
        weekly[order.order_date] = weekly.get(order.order_date, 0) + order.quantity
    return [
        {"week": week, "quantity": weekly[week]}
        for week in sorted(weekly)
    ]


def dataset_summary(dataset: SyntheticDataset) -> dict[str, object]:
    tenants = dataset.tenant_names()
    order_count = len(dataset.orders)
    total_units = sum(order.quantity for order in dataset.orders)
    revenue = sum(order.quantity * order.unit_price for order in dataset.orders)
    return {
        "tenant_count": len(tenants),
        "product_count": len(dataset.products),
        "customer_count": len(dataset.customers),
        "order_count": order_count,
        "total_units": total_units,
        "revenue": round(revenue, 2),
        "weeks": len({order.order_date for order in dataset.orders}),
        "tenants": [{"id": key, "name": value} for key, value in tenants.items()],
        "top_skus": _top_skus(dataset.orders, limit=6),
        "top_customers": _top_customers(dataset.orders, limit=10),
        "customer_revenue_concentration": _customer_revenue_concentration(dataset.orders),
        "demo_declining_customers": list(DEMO_DECLINING_CUSTOMERS),
        "demo_risk_sku": DEMO_RISK_SKU,
    }


def _top_skus(orders: Iterable[OrderRecord], limit: int) -> list[dict[str, object]]:
    totals: dict[str, int] = {}
    for order in orders:
        totals[order.sku] = totals.get(order.sku, 0) + order.quantity
    return [
        {"sku": sku, "units": units}
        for sku, units in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _top_customers(orders: Iterable[OrderRecord], limit: int) -> list[dict[str, object]]:
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    for order in orders:
        totals[order.customer_id] = totals.get(order.customer_id, 0.0) + order.quantity * order.unit_price
        names[order.customer_id] = order.customer_name
    return [
        {"customer_id": customer_id, "customer_name": names[customer_id], "revenue": round(revenue, 2)}
        for customer_id, revenue in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _customer_revenue_concentration(orders: Iterable[OrderRecord]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for order in orders:
        totals[order.customer_id] = totals.get(order.customer_id, 0.0) + order.quantity * order.unit_price
    values = sorted(totals.values(), reverse=True)
    total = sum(values) or 1.0
    return {
        "top_10_share_pct": round(sum(values[:10]) / total * 100, 2),
        "top_25_share_pct": round(sum(values[:25]) / total * 100, 2),
    }


def list_products(dataset: SyntheticDataset, tenant_id: str) -> list[dict[str, object]]:
    return [
        {
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "unit_price": product.unit_price,
        }
        for product in dataset.products
        if product.tenant_id == tenant_id
    ]


def list_segments() -> list[str]:
    return ["all", *SEGMENTS]
