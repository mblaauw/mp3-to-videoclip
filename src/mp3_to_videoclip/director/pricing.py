"""What a model call probably cost, from the catalogue's stated prices.

An estimate, and it says so. With no counts from the provider or no stated price the answer
is unknown, never zero, because an unknown cost read as free is how money goes unnoticed.
"""

from __future__ import annotations

from decimal import Decimal

from .. import catalog
from .providers.base import Usage

ESTIMATE = "catalogue estimate"
UNPRICED = "unpriced"
UNREPORTED = "tokens not reported"


def _rate(price) -> Decimal | None:
    return Decimal(price.amount) / 1000 if price is not None else None


def _rates(provider: str, model: str) -> tuple[Decimal, Decimal] | None:
    entry = next(
        (m for m in catalog.load().models if m.id == model and m.provider == provider), None
    )
    if entry is None:
        return None
    prices = {price.unit: price for price in (entry.price, entry.price_out) if price is not None}
    per_in = _rate(prices.get("1k_tokens_in"))
    per_out = _rate(prices.get("1k_tokens_out"))
    return (per_in, per_out) if per_in is not None and per_out is not None else None


def is_priced(provider: str, model: str) -> bool:
    return _rates(provider, model) is not None


def most_for(provider: str, model: str, tokens: int) -> Decimal | None:
    """The most ``tokens`` could cost, each at the dearer rate. None when unpriced."""
    rates = _rates(provider, model)
    return max(rates) * tokens if rates is not None else None


def cost_of(provider: str, model: str, usage: Usage) -> tuple[str | None, str]:
    """``(cost in USD, basis)``, with a cost of None whenever it isn't known."""
    if not usage.reported:
        return None, UNREPORTED
    rates = _rates(provider, model)
    if rates is None:
        return None, UNPRICED
    per_in, per_out = rates
    cost = per_in * usage.prompt_tokens + per_out * usage.completion_tokens
    return f"{cost.quantize(Decimal('0.000001'))}", ESTIMATE
