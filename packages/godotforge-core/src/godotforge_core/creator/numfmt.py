"""Canonical numeric parsing and serialization for generated Godot files.

All floats emitted into generated ``.gd`` and ``.tscn`` files pass through
this module so that identical numeric values always produce identical bytes,
regardless of input form (``250``, ``250.0``, ``"2.5e2"``), platform, or
locale. Parsing is decimal-only (``decimal.Decimal``); binary ``float``
formatting is forbidden in the emission path.

Canonical form (PATCH-0016 contract §5):

- ASCII only, ``.`` decimal separator, locale-independent.
- No exponent notation in emitted output.
- A decimal point is always emitted (``250`` -> ``250.0``).
- Trailing zeros are normalized away beyond the mandatory decimal point.
- At most 6 significant decimal digits; more is rejected.
- ``NaN``, ``inf``, ``-inf`` are rejected.
- Negative zero (sign bit 1 with zero coefficient) is rejected.

No AI, network, or telemetry dependency.
"""

from __future__ import annotations

import decimal
import re
from decimal import Decimal

MAX_SIGNIFICANT_DIGITS = 6

_NUMERIC_TEXT_RE = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")


def parse_canonical_decimal(value: object, *, name: str = "value") -> Decimal:
    """Parse ``value`` into a validated :class:`~decimal.Decimal`.

    Accepts ``int``, ``str``, and ``Decimal`` inputs. ``float`` is rejected
    outright because binary-to-decimal conversion would smuggle platform
    rounding noise into deterministic output. Booleans are rejected even
    though ``bool`` is an ``int`` subclass.

    Raises:
        ValueError: If the value is not finite, is negative zero, is not a
            plain ASCII numeric literal, or has more than
            ``MAX_SIGNIFICANT_DIGITS`` significant digits.
        TypeError: If ``value`` is of an unsupported type.
    """
    dec = _to_decimal(value, name=name)
    _reject_non_finite(dec, name=name)
    _reject_negative_zero(dec, name=name)
    _reject_excess_precision(dec, name=name)
    return dec


def format_canonical(value: object, *, name: str = "value") -> str:
    """Return the canonical string form of ``value`` for generated files.

    The result is locale-independent ASCII, always contains a decimal point,
    never uses exponent notation, and has trailing zeros normalized. Equal
    numeric values always format to byte-identical strings.
    """
    dec = parse_canonical_decimal(value, name=name)
    normalized = dec.normalize()
    if normalized == normalized.to_integral_value():
        # Integer-valued: emit as fixed-point with mandatory ".0".
        return f"{normalized:.1f}"
    text = format(normalized, "f")
    # "f" formatting of a normalized non-integral Decimal never emits an
    # exponent and never carries insignificant trailing zeros; the fractional
    # part is guaranteed non-empty by the branch above.
    return text


def _to_decimal(value: object, *, name: str) -> Decimal:
    """Convert a supported input to :class:`~decimal.Decimal` without float noise."""
    if isinstance(value, bool):
        raise TypeError(f"{name}: bool is not a numeric parameter")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise TypeError(
            f"{name}: binary float input is forbidden; pass int, str, or Decimal"
        )
    if isinstance(value, str):
        text = value.strip()
        if not _NUMERIC_TEXT_RE.match(text):
            raise ValueError(f"{name}: not a plain ASCII numeric literal: {value!r}")
        try:
            return Decimal(text)
        except decimal.InvalidOperation as exc:
            raise ValueError(f"{name}: not a parseable decimal: {value!r}") from exc
    raise TypeError(f"{name}: unsupported type {type(value).__name__}")


def _reject_non_finite(dec: Decimal, *, name: str) -> None:
    """Reject NaN and infinities; they are forbidden in deterministic output."""
    if not dec.is_finite():
        raise ValueError(f"{name}: NaN and infinity are not allowed: {dec}")


def _reject_negative_zero(dec: Decimal, *, name: str) -> None:
    """Reject negative zero: sign bit 1 with a zero coefficient."""
    if dec.is_zero() and dec.as_tuple().sign == 1:
        raise ValueError(f"{name}: negative zero is rejected, use 0.0")


def _reject_excess_precision(dec: Decimal, *, name: str) -> None:
    """Reject values with more than ``MAX_SIGNIFICANT_DIGITS`` significant digits.

    Significant digits are the coefficient digits of the normalized value with
    insignificant trailing zeros stripped.
    """
    digits = dec.normalize().as_tuple().digits
    significant = len(_strip_trailing_zeros(digits))
    if significant > MAX_SIGNIFICANT_DIGITS:
        raise ValueError(
            f"{name}: {dec} has {significant} significant digits; "
            f"maximum is {MAX_SIGNIFICANT_DIGITS}"
        )


def _strip_trailing_zeros(digits: tuple[int, ...]) -> tuple[int, ...]:
    """Return ``digits`` with insignificant trailing zeros removed."""
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
    return digits[:end]
