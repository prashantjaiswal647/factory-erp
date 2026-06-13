import re
from typing import Any


def normalize_carton_type(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def parse_allowed_sizes(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        text = ",".join(str(item) for item in value)
    else:
        text = str(value)
    text = text.strip().replace("，", ",")
    if not text:
        return []

    parts = re.split(r"[,/|;\n]+", text)
    sizes: set[int] = set()
    for part in parts:
        token = str(part).strip()
        if not token:
            continue
        matches = re.findall(r"\d+", token)
        if len(matches) > 1:
            sizes.update(int(match) for match in matches)
            continue
        if not matches:
            raise ValueError(f"Invalid product size '{token}'")
        digits = matches[0]
        # Excel may coerce a comma-formatted text cell such as 210,250,300
        # into the numeric value 210250300. Recover unambiguous 3-digit groups.
        if len(parts) == 1 and len(digits) > 3 and len(digits) % 3 == 0:
            sizes.update(int(digits[index:index + 3]) for index in range(0, len(digits), 3))
            continue
        size = int(digits)
        if size <= 0:
            raise ValueError("Product sizes must be positive")
        sizes.add(size)
    return sorted(sizes)


def serialize_finished_product_sizes(value: Any) -> str:
    return ",".join(str(size) for size in parse_allowed_sizes(value))


# Compatibility alias for callers introduced with the original carton mapping.
parse_finished_product_sizes = parse_allowed_sizes
