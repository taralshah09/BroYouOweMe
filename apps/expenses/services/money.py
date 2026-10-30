"""Exact INR conversion and deterministic allocation; never use floats."""

import re
from decimal import Decimal

MAX_PAISE = 2**63 - 1


def rupees_to_paise(amount):
    """Accept plain rupee strings, integers or Decimals with at most two decimals."""
    if isinstance(amount, bool) or not isinstance(amount, (str, int, Decimal)):
        raise ValueError("Use a rupee string, integer or Decimal, never a float.")
    text = str(amount)
    if not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", text, flags=re.ASCII):
        raise ValueError("Rupees must be a finite number with at most two decimals.")
    whole, _, fraction = text.lstrip("-").partition(".")
    paise = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if text.startswith("-"):
        paise = -paise
    return validate_paise(paise)


def validate_paise(amount):
    if type(amount) is not int or not -MAX_PAISE <= amount <= MAX_PAISE:
        raise ValueError("Paise must be an integer in the supported bigint range.")
    return amount


def paise_to_rupees(amount):
    """Return an exact two-decimal string suitable for display and JSON."""
    validate_paise(amount)
    whole, fraction = divmod(abs(amount), 100)
    return f"{'-' if amount < 0 else ''}{whole}.{fraction:02d}"


def allocate_equal(total_paise, user_ids):
    """Floor-divide, then assign remainder paise in ascending user-ID order.

    Negative totals support receipt discounts. Zero shares are retained here;
    expense validation belongs to the later expense service.
    """
    validate_paise(total_paise)
    participants = list(user_ids)
    if not participants or any(type(pk) is not int or pk <= 0 for pk in participants):
        raise ValueError("Participants must be positive integer user IDs.")
    if len(set(participants)) != len(participants):
        raise ValueError("Participant IDs must be unique.")
    base, remainder = divmod(total_paise, len(participants))
    return {
        pk: base + (index < remainder)
        for index, pk in enumerate(sorted(participants))
    }
