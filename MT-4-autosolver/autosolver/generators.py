"""Synthetic case generator for development before official data arrives."""

from __future__ import annotations

import random
from collections.abc import Callable

from autosolver.model import BundleDiscount, Edge, Instance, Order, Rider


def tiny_manual() -> Instance:
    return Instance(
        name="tiny_manual",
        orders=(Order("o1"), Order("o2")),
        riders=(Rider("r1", max_orders=1), Rider("r2", max_orders=1)),
        max_riders_per_order=1,
        edges=(
            Edge("o1", "r1", cost=1.0, accept_prob=0.90),
            Edge("o1", "r2", cost=8.0, accept_prob=0.40),
            Edge("o2", "r1", cost=7.0, accept_prob=0.30),
            Edge("o2", "r2", cost=1.0, accept_prob=0.90),
        ),
        metadata={"expected_best": {"expected_accepted": 1.8, "total_cost": 2.0}},
    )


def single_best_rider() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 7))
    riders = tuple(Rider(f"r{i}", max_orders=3) for i in range(1, 4))
    edges: list[Edge] = []
    for index, order in enumerate(orders):
        best = riders[index % len(riders)]
        for rider in riders:
            is_best = rider.id == best.id
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=1.0 if is_best else 5.0 + index,
                    accept_prob=0.92 if is_best else 0.45,
                )
            )
    return Instance(
        name="single_best_rider",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=1,
    )


def bundle_wins() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 4))
    riders = (Rider("solo", max_orders=3), Rider("bundle", max_orders=3))
    edges = tuple(
        [
            Edge("o1", "solo", cost=2.0, accept_prob=0.90),
            Edge("o2", "solo", cost=2.0, accept_prob=0.90),
            Edge("o3", "solo", cost=2.0, accept_prob=0.90),
            Edge("o1", "bundle", cost=3.2, accept_prob=0.90),
            Edge("o2", "bundle", cost=3.2, accept_prob=0.90),
            Edge("o3", "bundle", cost=3.2, accept_prob=0.90),
        ]
    )
    return Instance(
        name="bundle_wins",
        orders=orders,
        riders=riders,
        edges=edges,
        max_riders_per_order=1,
        bundle_discounts=(BundleDiscount("bundle", ("o1", "o2", "o3"), discount=5.0),),
    )


def multi_offer_probability() -> Instance:
    return Instance(
        name="multi_offer_probability",
        orders=(Order("o1"), Order("o2")),
        riders=(Rider("r1", 2), Rider("r2", 2), Rider("r3", 2)),
        max_riders_per_order=3,
        edges=(
            Edge("o1", "r1", 1.0, 0.40),
            Edge("o1", "r2", 1.2, 0.35),
            Edge("o1", "r3", 1.1, 0.30),
            Edge("o2", "r1", 1.0, 0.20),
            Edge("o2", "r2", 1.1, 0.25),
            Edge("o2", "r3", 1.0, 0.80),
        ),
    )


def rider_shortage() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 9))
    riders = (Rider("r1", max_orders=2), Rider("r2", max_orders=2))
    edges = tuple(
        Edge(order.id, rider.id, cost=1.0 + (index % 4), accept_prob=0.55 + 0.04 * (index % 5))
        for index, order in enumerate(orders)
        for rider in riders
    )
    return Instance(
        name="rider_shortage",
        orders=orders,
        riders=riders,
        edges=edges,
        max_riders_per_order=1,
    )


def dense_conflict() -> Instance:
    orders = tuple(Order(f"o{i}") for i in range(1, 25))
    riders = tuple(Rider(f"r{i}", max_orders=6) for i in range(1, 6))
    edges: list[Edge] = []
    for order_index, order in enumerate(orders):
        for rider_index, rider in enumerate(riders):
            preferred = rider_index == 0
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=1.0 + rider_index * 1.7 + (order_index % 3) * 0.2,
                    accept_prob=0.88 if preferred else 0.62 - rider_index * 0.03,
                )
            )
    return Instance(
        name="dense_conflict",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=1,
    )


def large_random(seed: int = 42, order_count: int = 220, rider_count: int = 45) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i}") for i in range(1, order_count + 1))
    riders = tuple(Rider(f"r{i}", max_orders=rng.randint(5, 9)) for i in range(1, rider_count + 1))
    edges: list[Edge] = []
    for order in orders:
        candidate_count = rng.randint(4, min(12, rider_count))
        for rider in rng.sample(riders, candidate_count):
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    cost=round(rng.uniform(1.0, 18.0), 3),
                    accept_prob=round(rng.uniform(0.08, 0.92), 3),
                )
            )
    return Instance(
        name="large_random",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=2,
        metadata={"seed": seed},
    )


def random_case(
    name: str = "random",
    seed: int = 0,
    order_count: int = 30,
    rider_count: int = 8,
    density: float = 0.45,
    max_riders_per_order: int = 2,
) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i}") for i in range(1, order_count + 1))
    riders = tuple(Rider(f"r{i}", max_orders=max(1, order_count // rider_count + 2)) for i in range(1, rider_count + 1))
    edges: list[Edge] = []
    for order in orders:
        order_edges = []
        for rider in riders:
            if rng.random() <= density:
                order_edges.append(
                    Edge(
                        order.id,
                        rider.id,
                        cost=round(rng.uniform(1.0, 12.0), 3),
                        accept_prob=round(rng.uniform(0.10, 0.95), 3),
                    )
                )
        if not order_edges:
            rider = rng.choice(riders)
            order_edges.append(Edge(order.id, rider.id, cost=5.0, accept_prob=0.5))
        edges.extend(order_edges)
    return Instance(
        name=name,
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=max_riders_per_order,
        metadata={"seed": seed, "density": density},
    )


CASE_GENERATORS: dict[str, Callable[[], Instance]] = {
    "tiny_manual": tiny_manual,
    "single_best_rider": single_best_rider,
    "bundle_wins": bundle_wins,
    "multi_offer_probability": multi_offer_probability,
    "rider_shortage": rider_shortage,
    "dense_conflict": dense_conflict,
    "large_random": large_random,
}


def complex_mixed_city(seed: int = 1001, order_count: int = 650, rider_count: int = 120) -> Instance:
    rng = random.Random(seed)
    zones = [f"z{i}" for i in range(8)]
    orders = tuple(
        Order(f"o{i + 1}", priority=rng.choice([1.0, 1.0, 1.0, 1.2, 1.5]))
        for i in range(order_count)
    )
    riders = tuple(Rider(f"r{i + 1}", max_orders=rng.randint(4, 10)) for i in range(rider_count))
    rider_zones = {rider.id: rng.choice(zones) for rider in riders}
    edges: list[Edge] = []
    for index, order in enumerate(orders):
        order_zone = zones[(index * 7 + seed) % len(zones)]
        for rider in random_sample(rng, riders, rng.randint(7, min(18, rider_count))):
            same_zone = rider_zones[rider.id] == order_zone
            cost = rng.uniform(2.0, 24.0) * (0.55 if same_zone else 1.25)
            probability = rng.uniform(0.12, 0.92) + (0.12 if same_zone else -0.05)
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    round(max(0.7, cost), 3),
                    round(min(0.97, max(0.03, probability)), 3),
                )
            )

    discounts: list[BundleDiscount] = []
    for rider in random_sample(rng, riders, min(60, len(riders))):
        feasible_orders = [edge.order_id for edge in edges if edge.rider_id == rider.id]
        if len(feasible_orders) < 3:
            continue
        for _ in range(rng.randint(1, 3)):
            group = tuple(random_sample(rng, feasible_orders, min(rng.choice([2, 3, 4]), len(feasible_orders))))
            discounts.append(BundleDiscount(rider.id, group, round(rng.uniform(2.0, 9.0), 3)))

    return Instance(
        name=f"complex_mixed_city_{order_count}x{rider_count}",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=3,
        bundle_discounts=tuple(discounts),
        metadata={"seed": seed, "scenario": "mixed city, zone affinity, bundles, multiposting"},
    )


def complex_sparse_bottleneck(seed: int = 2002, order_count: int = 900, rider_count: int = 90) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i + 1}", priority=1.0 + (0.4 if i % 17 == 0 else 0.0)) for i in range(order_count))
    riders = tuple(Rider(f"r{i + 1}", max_orders=rng.randint(6, 14)) for i in range(rider_count))
    hot_riders = riders[: max(8, rider_count // 8)]
    edges: list[Edge] = []
    for index, order in enumerate(orders):
        pool = hot_riders if index % 3 != 0 else riders
        for rider in random_sample(rng, pool, min(len(pool), rng.randint(3, 8))):
            hot = rider in hot_riders
            probability = rng.uniform(0.45, 0.94) if hot else rng.uniform(0.16, 0.62)
            cost = rng.uniform(1.2, 8.5) if hot else rng.uniform(6.0, 21.0)
            edges.append(Edge(order.id, rider.id, round(cost, 3), round(probability, 3)))
    return Instance(
        name=f"complex_sparse_bottleneck_{order_count}x{rider_count}",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=2,
        metadata={"seed": seed, "scenario": "sparse graph with overloaded attractive riders"},
    )


def complex_bundle_trap(seed: int = 3003, order_count: int = 420, rider_count: int = 70) -> Instance:
    rng = random.Random(seed)
    orders = tuple(Order(f"o{i + 1}") for i in range(order_count))
    riders = tuple(Rider(f"r{i + 1}", max_orders=rng.randint(4, 9)) for i in range(rider_count))
    edges: list[Edge] = []
    for order in orders:
        for rider in random_sample(rng, riders, rng.randint(5, 12)):
            expensive_bundle_rider = int(rider.id[1:]) % 5 == 0
            cost = rng.uniform(8.0, 20.0) if expensive_bundle_rider else rng.uniform(2.0, 12.0)
            probability = rng.uniform(0.55, 0.93) if expensive_bundle_rider else rng.uniform(0.35, 0.84)
            edges.append(Edge(order.id, rider.id, round(cost, 3), round(probability, 3)))

    discounts: list[BundleDiscount] = []
    for rider in riders:
        if int(rider.id[1:]) % 5 != 0:
            continue
        feasible_orders = [edge.order_id for edge in edges if edge.rider_id == rider.id]
        rng.shuffle(feasible_orders)
        for start in range(0, min(len(feasible_orders), 18), 3):
            group = tuple(feasible_orders[start : start + 3])
            if len(group) >= 2:
                discounts.append(BundleDiscount(rider.id, group, round(rng.uniform(10.0, 28.0), 3)))
    return Instance(
        name=f"complex_bundle_trap_{order_count}x{rider_count}",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=1,
        bundle_discounts=tuple(discounts),
        metadata={"seed": seed, "scenario": "single-edge greedy misses expensive-but-discounted bundles"},
    )


def complex_mega_mixed(seed: int = 4004, order_count: int = 1500, rider_count: int = 250) -> Instance:
    rng = random.Random(seed)
    zones = [f"z{i}" for i in range(12)]
    orders = tuple(
        Order(f"o{i + 1}", priority=rng.choice([1.0, 1.0, 1.0, 1.15, 1.35]))
        for i in range(order_count)
    )
    riders = tuple(Rider(f"r{i + 1}", max_orders=rng.randint(5, 12)) for i in range(rider_count))
    rider_zones = {rider.id: rng.choice(zones) for rider in riders}
    edges: list[Edge] = []
    for index, order in enumerate(orders):
        order_zone = zones[(index * 5 + rng.randint(0, 3)) % len(zones)]
        candidates = set(random_sample(rng, riders, rng.randint(8, 20)))
        preferred = [rider for rider in riders if rider_zones[rider.id] == order_zone]
        if preferred:
            candidates.update(random_sample(rng, preferred, min(len(preferred), rng.randint(2, 5))))
        for rider in sorted(candidates, key=lambda item: int(item.id[1:])):
            same_zone = rider_zones[rider.id] == order_zone
            crowd_penalty = 1.35 if int(rider.id[1:]) % 13 == 0 else 1.0
            cost = rng.uniform(1.5, 26.0) * (0.58 if same_zone else 1.18) * crowd_penalty
            probability = rng.uniform(0.10, 0.93) + (0.10 if same_zone else -0.04)
            edges.append(
                Edge(
                    order.id,
                    rider.id,
                    round(max(cost, 0.6), 3),
                    round(min(0.98, max(0.02, probability)), 3),
                )
            )

    discounts: list[BundleDiscount] = []
    for rider in random_sample(rng, riders, min(100, len(riders))):
        feasible_orders = [edge.order_id for edge in edges if edge.rider_id == rider.id]
        rng.shuffle(feasible_orders)
        for start in range(0, min(len(feasible_orders), 20), 4):
            group = tuple(feasible_orders[start : start + rng.choice([2, 3, 4])])
            if len(group) >= 2:
                discounts.append(BundleDiscount(rider.id, group, round(rng.uniform(2.0, 12.0), 3)))

    return Instance(
        name=f"complex_mega_mixed_{order_count}x{rider_count}",
        orders=orders,
        riders=riders,
        edges=tuple(edges),
        max_riders_per_order=3,
        bundle_discounts=tuple(discounts),
        metadata={"seed": seed, "scenario": "mega mixed stress case with zones, multiposting, bundles"},
    )


def random_sample(rng: random.Random, population: tuple | list, count: int) -> list:
    return rng.sample(list(population), min(count, len(population)))


STRESS_CASE_GENERATORS: dict[str, Callable[[], Instance]] = {
    "complex_mixed_city": complex_mixed_city,
    "complex_sparse_bottleneck": complex_sparse_bottleneck,
    "complex_bundle_trap": complex_bundle_trap,
    "complex_mega_mixed": complex_mega_mixed,
}


def generate_case(name: str) -> Instance:
    generators = {**CASE_GENERATORS, **STRESS_CASE_GENERATORS}
    try:
        return generators[name]()
    except KeyError as exc:
        available = ", ".join(sorted(generators))
        raise ValueError(f"unknown case {name!r}; available cases: {available}") from exc
