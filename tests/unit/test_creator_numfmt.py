"""numfmt — canonical numeric parsing/serialization, determinism, rejections."""

from __future__ import annotations

import locale
from decimal import Decimal

import pytest
from godotforge_core.creator.numfmt import (
    MAX_SIGNIFICANT_DIGITS,
    format_canonical,
    parse_canonical_decimal,
)


def test_max_significant_digits_is_six() -> None:
    """Contract pins the precision cap at 6 significant digits."""
    assert MAX_SIGNIFICANT_DIGITS == 6


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (250, "250.0"),
        ("250", "250.0"),
        ("250.0", "250.0"),
        ("2.5e2", "250.0"),
        ("250.00", "250.0"),
        (Decimal("250.00"), "250.0"),
        (200, "200.0"),
        (-400, "-400.0"),
        ("-350.0", "-350.0"),
        ("0", "0.0"),
        ("0.0", "0.0"),
        ("1e-3", "0.001"),
        ("250.125", "250.125"),
        (".5", "0.5"),
        ("980", "980.0"),
    ],
)
def test_equivalent_inputs_normalize_identically(value: object, expected: str) -> None:
    """Integer, decimal, exponent, and padded forms produce identical bytes."""
    assert format_canonical(value) == expected


def test_output_always_has_decimal_point_and_no_exponent() -> None:
    """Every emitted literal contains '.' and never 'e'/'E'."""
    for value in (250, "250.0", "2.5e2", "1e-3", "0", "-350.0", "250.125"):
        text = format_canonical(value)
        assert "." in text
        assert "e" not in text.lower()
        assert text.isascii()


def test_trailing_zeros_normalized() -> None:
    """Insignificant trailing zeros never appear in output."""
    assert format_canonical("250.5000") == "250.5"
    assert format_canonical("0.100") == "0.1"


def test_six_significant_digits_accepted() -> None:
    """Exactly 6 significant digits is the inclusive limit."""
    assert format_canonical("250.125") == "250.125"
    assert parse_canonical_decimal("250.125") == Decimal("250.125")


@pytest.mark.parametrize("value", ["250.1255", "1.000001", "1234567.0"])
def test_excess_precision_rejected(value: str) -> None:
    """More than 6 significant digits -> ValueError."""
    with pytest.raises(ValueError, match="significant digits"):
        format_canonical(value)


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf", "Infinity", "-Infinity"])
def test_non_finite_rejected(value: str) -> None:
    """NaN and infinities are rejected."""
    with pytest.raises(ValueError, match="not allowed|numeric literal"):
        format_canonical(value)
    with pytest.raises(ValueError):
        format_canonical(Decimal(value))


@pytest.mark.parametrize(
    "value",
    ["-0.0", "-0", "-0.00", Decimal("-0"), Decimal("-0.0")],
)
def test_negative_zero_rejected(value: object) -> None:
    """Negative zero (sign bit 1, zero coefficient) is rejected, not normalized."""
    with pytest.raises(ValueError, match="negative zero"):
        format_canonical(value)


def test_positive_zero_accepted() -> None:
    """Positive zero is valid and formats canonically."""
    assert format_canonical("0.0") == "0.0"
    assert format_canonical(0) == "0.0"


@pytest.mark.parametrize("value", [True, False, None, "abc", "1,5", "", "２５０", "0x10"])
def test_non_numeric_rejected(value: object) -> None:
    """Booleans, non-numerics, locale separators, and non-ASCII are rejected."""
    with pytest.raises((ValueError, TypeError)):
        format_canonical(value)


@pytest.mark.parametrize("value", [0.1, 250.0, float("inf")])
def test_binary_float_input_forbidden(value: float) -> None:
    """Binary float input is forbidden in the emission path."""
    with pytest.raises(TypeError, match="binary float"):
        format_canonical(value)


def test_formatting_is_range_independent() -> None:
    """Formatting applies no range checks; bounds live in manifest validation."""
    assert format_canonical("9999.0") == "9999.0"
    assert format_canonical("-9999.0") == "-9999.0"


def test_deterministic_across_runs() -> None:
    """Repeated calls return byte-identical strings."""
    runs = {format_canonical("2.5e2") for _ in range(100)}
    assert runs == {"250.0"}


def test_locale_independent() -> None:
    """Output is unaffected by process locale where locales are available."""
    original = locale.setlocale(locale.LC_ALL)
    try:
        for loc in ("de_DE.UTF-8", "fr_FR.UTF-8", "C"):
            try:
                locale.setlocale(locale.LC_ALL, loc)
            except locale.Error:
                continue
            assert format_canonical("2.5e2") == "250.0"
    finally:
        locale.setlocale(locale.LC_ALL, original)


def test_error_messages_name_the_parameter() -> None:
    """Rejections name the offending parameter for CLI diagnostics."""
    with pytest.raises(ValueError, match="speed"):
        format_canonical("NaN", name="speed")
    with pytest.raises(ValueError, match="jump_velocity"):
        format_canonical("1.0000001", name="jump_velocity")
