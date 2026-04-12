"""
WASM-compatible integer math operations for the i32 subset.

All functions operate on 32-bit unsigned values (masked with MASK32) and
implement WASM semantics including signed division truncation, unsigned/signed
shifts, bit rotation, and sign extension for narrow loads.
"""

from __future__ import annotations

from .opcodes import (
    CLZ_SHIFTS,
    CLZ_THRESHOLDS,
    I8_RANGE,
    I8_SIGN_BIT,
    I16_RANGE,
    I16_SIGN_BIT,
    I32_MODULO,
    I32_SIGN_BIT,
    MASK32,
)


def trunc_div(b: int, a: int) -> int:
    """
    WASM truncating division (toward zero).

    Args:
        b: Dividend.
        a: Divisor.

    Returns:
        Quotient truncated toward zero.

    """
    return int(b / a)


def trunc_rem(b: int, a: int) -> int:
    """
    WASM truncating remainder.

    Args:
        b: Dividend.
        a: Divisor.

    Returns:
        Remainder after truncating division.

    """
    return b - trunc_div(b, a) * a


def to_i32(val: int) -> int:
    """
    Mask a Python integer to 32-bit unsigned range [0, 0xFFFFFFFF].

    Args:
        val: Integer value to mask.

    Returns:
        Value masked to the unsigned 32-bit range.

    """
    return int(val) & MASK32


def shr_u(b: int, a: int) -> int:
    """
    WASM i32.shr_u -- unsigned right shift.

    Args:
        b: Value to shift.
        a: Shift amount (only the low 5 bits are used).

    Returns:
        Result of the unsigned right shift.

    """
    return to_i32(b) >> (int(a) & 31)


def shr_s(b: int, a: int) -> int:
    """
    WASM i32.shr_s -- signed right shift (sign-extending).

    Args:
        b: Value to shift.
        a: Shift amount (only the low 5 bits are used).

    Returns:
        Result of the signed right shift.

    """
    val = to_i32(b)
    if val >= I32_SIGN_BIT:
        val -= I32_MODULO
    shift = int(a) & 31
    result = val >> shift
    return result & MASK32 if result < 0 else result


def rotl32(b: int, a: int) -> int:
    """
    WASM i32.rotl -- rotate left by k bits.

    Args:
        b: Value to rotate.
        a: Rotation amount (only the low 5 bits are used).

    Returns:
        Result of the left rotation.

    """
    val = to_i32(b)
    shift = int(a) & 31
    return ((val << shift) | (val >> (32 - shift))) & MASK32 if shift else val


def rotr32(b: int, a: int) -> int:
    """
    WASM i32.rotr -- rotate right by k bits.

    Args:
        b: Value to rotate.
        a: Rotation amount (only the low 5 bits are used).

    Returns:
        Result of the right rotation.

    """
    val = to_i32(b)
    shift = int(a) & 31
    return ((val >> shift) | (val << (32 - shift))) & MASK32 if shift else val


def clz32(val: int) -> int:
    """
    WASM i32.clz -- count leading zero bits.

    Uses a branch-free binary search over precomputed thresholds.
    Returns 32 for a zero input.

    Args:
        val: Input value.

    Returns:
        Number of leading zero bits in the 32-bit representation.

    """
    v = to_i32(val)
    if v == 0:
        return 32
    n = 0
    for threshold, shift in zip(CLZ_THRESHOLDS, CLZ_SHIFTS, strict=True):
        if v <= threshold:
            n += shift
            v <<= shift
    return n


def ctz32(val: int) -> int:
    """
    WASM i32.ctz -- count trailing zero bits.

    Uses a de Bruijn-like cascade over power-of-two masks.
    Returns 32 for a zero input.

    Args:
        val: Input value.

    Returns:
        Number of trailing zero bits in the 32-bit representation.

    """
    v = to_i32(val)
    if v == 0:
        return 32
    n = 0
    if (v & 0x0000FFFF) == 0:
        n += 16
        v >>= 16
    if (v & 0x000000FF) == 0:
        n += 8
        v >>= 8
    if (v & 0x0000000F) == 0:
        n += 4
        v >>= 4
    if (v & 0x00000003) == 0:
        n += 2
        v >>= 2
    if (v & 0x00000001) == 0:
        n += 1
    return n


def popcnt32(val: int) -> int:
    """
    WASM i32.popcnt -- count the number of set bits (population count).

    Delegates to Python int.bit_count().

    Args:
        val: Input value.

    Returns:
        Number of bits set in the 32-bit representation.

    """
    return to_i32(val).bit_count()


def sign_extend_8(val: int) -> int:
    """
    Sign-extend an 8-bit value to a Python signed integer.

    Args:
        val: Input value (low 8 bits are used).

    Returns:
        Sign-extended integer value.

    """
    v = int(val) & 0xFF
    return v - I8_RANGE if v >= I8_SIGN_BIT else v


def sign_extend_16(val: int) -> int:
    """
    Sign-extend a 16-bit value to a Python signed integer.

    Args:
        val: Input value (low 16 bits are used).

    Returns:
        Sign-extended integer value.

    """
    v = int(val) & 0xFFFF
    return v - I16_RANGE if v >= I16_SIGN_BIT else v


__all__ = [
    "clz32",
    "ctz32",
    "popcnt32",
    "rotl32",
    "rotr32",
    "shr_s",
    "shr_u",
    "sign_extend_8",
    "sign_extend_16",
    "to_i32",
    "trunc_div",
    "trunc_rem",
]
