"""Market benchmark prices for Philippine government procurement.

Conservative per-unit prices in PHP for common procurement items.
Used by heuristics to detect price anomalies.
Updated for 2025-2026 Philippine market conditions.
"""

from __future__ import annotations

# Benchmark prices (PHP) — conservative market rates for PH government procurement
BENCHMARKS: dict[str, float] = {
    # Computers
    "laptop": 55000,
    "notebook": 55000,
    "desktop": 40000,
    "computer": 40000,
    "workstation": 80000,
    "all-in-one": 50000,
    "thin client": 25000,
    # Peripherals
    "printer": 30000,
    "scanner": 25000,
    "plotter": 150000,
    "projector": 35000,
    "monitor": 15000,
    "keyboard": 1500,
    "mouse": 800,
    # Networking
    "server": 250000,
    "switch": 50000,
    "router": 30000,
    "access point": 15000,
    "firewall": 150000,
    "rack": 20000,
    "ups": 25000,
    "patch panel": 5000,
    "cable": 15,  # per meter
    # Storage
    "nas": 80000,
    "hard drive": 5000,
    "ssd": 5000,
    # Mobile
    "tablet": 25000,
    "phone": 15000,
    # Security
    "cctv": 50000,
    "camera": 50000,
    "dvr": 30000,
    # Software
    "license": 10000,
    "software": 10000,
    "subscription": 5000,  # per month
    # Furniture
    "table": 5000,
    "chair": 3000,
    "desk": 5000,
    "cabinet": 8000,
    # Generators / Power
    "generator": 150000,
    "aircon": 35000,
    "airconditioner": 35000,
    "air conditioning": 35000,
    # Vehicles
    "vehicle": 1200000,
    "car": 1200000,
    "motorcycle": 80000,
    # Misc IT
    "biometric": 15000,
    "attendance": 15000,
    "pos": 25000,
    "kiosk": 50000,
    # Fallback for unidentified items
    "item": 50000,
    "unit": 50000,
    "lot": 0,  # lot items are heterogeneous, skip benchmarking
}


def lookup_benchmark(unit_type: str) -> float:
    """Look up the benchmark price for a normalized item type.

    Returns 0 if type is unknown (skip benchmarking).
    """
    return BENCHMARKS.get(unit_type, 0)


def get_all_benchmark_keys() -> list[str]:
    """Return all benchmark keys, longest first (for substring matching)."""
    return sorted(BENCHMARKS.keys(), key=len, reverse=True)
