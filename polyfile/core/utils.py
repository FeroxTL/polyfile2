"""Small helpers shared by core modules."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Final

_SIZE_UNITS: Final[dict[str, int]] = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 ** 2,
    "gb": 1024 ** 3,
    "tb": 1024 ** 4,
    "kib": 1024,
    "mib": 1024 ** 2,
    "gib": 1024 ** 3,
    "tib": 1024 ** 4,
}

_DURATION_UNITS: Final[dict[str, int]] = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}

_SIZE_UNITS_BY_LENGTH: Final[tuple[str, ...]] = tuple(
    sorted(_SIZE_UNITS, key=len, reverse=True),
)


def parse_duration(value: str) -> timedelta:
    """Parse a short duration such as ``30s``, ``15m``, ``24h`` or ``7d``."""
    value = value.strip().lower()
    if len(value) < 2 or value[-1] not in _DURATION_UNITS:
        raise ValueError(f"Invalid duration: {value!r}")
    try:
        amount = float(value[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid duration: {value!r}") from exc
    return timedelta(seconds=amount * _DURATION_UNITS[value[-1]])


def parse_size(value: str | int) -> int:
    """Parse a byte size such as ``512B``, ``10MB`` or ``10GiB``.

    Units are binary (``1KB`` is 1024 bytes). A value without a unit is treated
    as bytes, which keeps integer overrides and older configurations working.
    """
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"Invalid size: {value!r}")
        return value

    text = value.strip().lower().replace(" ", "")
    if not text:
        raise ValueError(f"Invalid size: {value!r}")

    multiplier = 1
    number = text
    for unit in _SIZE_UNITS_BY_LENGTH:
        if text.endswith(unit):
            number = text[:-len(unit)]
            multiplier = _SIZE_UNITS[unit]
            break

    try:
        amount = Decimal(number)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid size: {value!r}") from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Invalid size: {value!r}")

    return int(amount * multiplier)
