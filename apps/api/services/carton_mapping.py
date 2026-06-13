import re
from typing import Any


def normalize_carton_type(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def parse_allowed_sizes(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts = value
    else:
        parts = re.split(r"[,;\n]+", str(value))
    sizes: list[int] = []
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        match = re.fullmatch(r"(\d+)(?:\.0+)?(?:\s*ml)?", text, re.IGNORECASE)
        if not match:
            raise ValueError(f"Invalid product size '{text}'")
        size = int(match.group(1))
        if size <= 0:
            raise ValueError("Product sizes must be positive")
        if size not in sizes:
            sizes.append(size)
    return sizes


def serialize_finished_product_sizes(value: Any) -> str:
    return ",".join(str(size) for size in parse_allowed_sizes(value))


# Compatibility alias for callers introduced with the original carton mapping.
parse_finished_product_sizes = parse_allowed_sizes
