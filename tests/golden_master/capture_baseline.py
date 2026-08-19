"""Capture deterministic DCF outputs for the Canonical Core decision.

The capture deliberately uses local inputs so it does not require API keys or
network access. External market-source comparison remains a separate decision
because it depends on live-source quality measurements.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.dcf_calculator import DCFCalculator as LegacyDCFCalculator
from app.services.dcf_calculator import DCFCalculator as LayeredDCFCalculator


DEFAULT_STOCK_CODES = [
    "1101", "1216", "1301", "1326", "1402", "1476", "2002", "2105",
    "2207", "2303", "2317", "2330", "2345", "2357", "2379", "2382",
    "2454", "2603", "2881", "3008",
]


def _serialize_result(result: Any) -> dict[str, Any]:
    """Convert either DCF result contract into JSON-compatible data."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result


def capture_golden_master(stock_codes: list[str]) -> dict[str, Any]:
    """Capture Legacy and Layered DCF outputs for representative stock codes.

    Args:
        stock_codes: Stock codes used as deterministic case identifiers.

    Returns:
        A JSON-compatible snapshot containing both result contracts.
    """
    legacy = LegacyDCFCalculator(enable_slippage=False)
    layered = LayeredDCFCalculator()
    cases: list[dict[str, Any]] = []

    for index, stock_code in enumerate(stock_codes):
        current_price = 80.0 + index * 7.5
        current_eps = 4.0 + index * 0.35
        growth_rates = [0.06 + (index % 4) * 0.01, 0.03 + (index % 3) * 0.01]
        arguments = {
            "current_price": current_price,
            "current_eps": current_eps,
            "growth_rates": growth_rates,
            "discount_rate": 0.08,
            "years": 10,
            "stock_code": stock_code,
        }
        legacy_result = legacy.calculate_dcf_value(**arguments)
        layered_result = layered.calculate_dcf_value(**arguments)
        cases.append(
            {
                "stock_code": stock_code,
                "inputs": arguments,
                "legacy": _serialize_result(legacy_result),
                "layered": _serialize_result(layered_result),
            }
        )

    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "deterministic_local_inputs",
        "market_scan": {
            "status": "not_captured",
            "reason": "Live source quality requires configured API credentials and network access.",
        },
        "cache": {
            "status": "not_captured",
            "reason": "Cache equivalence requires the source snapshot fixture from Task 3.4.",
        },
        "cases": cases,
    }


def main() -> None:
    """Write a Canonical Core comparison snapshot to disk."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/golden_master/baseline.json"),
    )
    args = parser.parse_args()
    snapshot = capture_golden_master(DEFAULT_STOCK_CODES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] captured {len(snapshot['cases'])} DCF cases: {args.output}")


if __name__ == "__main__":
    main()