"""zxbyd — Probe Philippine government procurement."""

__version__ = "0.1.0"

# Windows-safe currency label (cp1252 can't render ₱ U+20B1)
PHP = "PHP"


def fmt_php(amount: float | int | None) -> str:
    """Format a PHP amount safe for Windows terminal."""
    if amount is None:
        return "—"
    return f"{PHP} {amount:,.0f}"
