import re
from typing import Final

# Verhoeff Dihedral Group D5 Multiplication Table
_VERHOEFF_D: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

# Verhoeff Permutation Table (Position mod 8)
_VERHOEFF_P: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

# Verhoeff Inverse Table
_VERHOEFF_INV: Final[tuple[int, ...]] = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

_PAN_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[A-Z]{3}[ABCFGHLJPTF][A-Z][0-9]{4}[A-Z]$"
)
_IFSC_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[A-Z]{4}0[A-Z0-9]{6}$"
)


def verify_verhoeff(number_str: str) -> bool:
    """
    Validates a 12-digit Indian national ID string using the Verhoeff algorithm.
    Must be 12 digits, start with 2-9, and pass the D5 dihedral checksum.
    """
    clean = re.sub(r"[\s\-]", "", number_str)
    if len(clean) != 12 or not clean.isdigit():
        return False
    if clean[0] not in "23456789":
        return False

    c = 0
    for i, digit_char in enumerate(reversed(clean)):
        digit = int(digit_char)
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][digit]]
    return c == 0


def generate_verhoeff_check_digit(eleven_digits: str) -> str:
    """
    Computes the 12th Verhoeff checksum digit for an 11-digit numeric prefix.
    Used by synthetic test generators so static ID literals are never hardcoded.
    """
    clean = re.sub(r"[\s\-]", "", eleven_digits)
    if len(clean) != 11 or not clean.isdigit() or clean[0] not in "23456789":
        raise ValueError("Input must be an 11-digit string starting with 2-9")

    c = 0
    for i, digit_char in enumerate(reversed(clean)):
        digit = int(digit_char)
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][digit]]
    return str(_VERHOEFF_INV[c])


def verify_luhn(card_str: str) -> bool:
    """
    Validates 13 to 19 digit payment card numbers via the Luhn mod-10 algorithm.
    """
    clean = re.sub(r"[\s\-]", "", card_str)
    if not (13 <= len(clean) <= 19) or not clean.isdigit():
        return False
    if len(set(clean)) == 1:
        return False

    total = 0
    reverse_digits = [int(d) for d in reversed(clean)]
    for idx, digit in enumerate(reverse_digits):
        if idx % 2 == 1:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += digit

    return total % 10 == 0


def verify_pan_structure(pan_str: str) -> bool:
    """
    Verifies Indian Permanent Account Number (PAN) 10-character structure,
    including the 4th-character Income Tax assessee status code.
    """
    clean = pan_str.strip().upper()
    return bool(_PAN_REGEX.match(clean))


def verify_ifsc_structure(ifsc_str: str) -> bool:
    """
    Verifies Indian Financial System Code (IFSC) 11-character structure.
    """
    clean = ifsc_str.strip().upper()
    return bool(_IFSC_REGEX.match(clean))