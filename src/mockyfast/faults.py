"""Latency and failure simulation.

`delay_ms` accepts a fixed number or a `{min, max}` range, so a mock can behave
like a service whose latency varies. `fault` replaces the normal response some
of the time, which is what a client's retry and timeout handling needs to be
exercised against.
"""

import random
from typing import Any

DEFAULT_FAULT_STATUS = 500

DEFAULT_FAULT_BODY = {"detail": "Injected fault"}


def resolve_delay_ms(response_config: dict) -> int:
    delay = response_config.get("delay_ms", 0)

    if isinstance(delay, dict):
        low = int(delay.get("min", 0) or 0)
        high = int(delay.get("max", low) or 0)

        if high < low:
            low, high = high, low

        return random.randint(low, high)

    return int(delay or 0)


def should_fault(fault: dict) -> bool:
    probability = fault.get("probability", 1.0)

    try:
        probability = float(probability)
    except (TypeError, ValueError):
        return False

    if probability >= 1:
        return True

    if probability <= 0:
        return False

    return random.random() < probability


def fault_delay_ms(fault: dict) -> int | None:
    """A fault may take its own time, typically to simulate a timeout."""
    if "delay_ms" not in fault:
        return None

    return resolve_delay_ms(fault)


def fault_status_code(fault: dict) -> int:
    return fault.get("status_code", DEFAULT_FAULT_STATUS)


def fault_body(fault: dict) -> Any:
    return fault.get("body", DEFAULT_FAULT_BODY)
