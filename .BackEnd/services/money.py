from decimal import Decimal, ROUND_HALF_UP


def d(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def quantize_money(value) -> Decimal:
    return d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_cents(value) -> int:
    return int((quantize_money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents) -> Decimal:
    if cents is None:
        return Decimal("0")
    return (Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

