"""
Opcode constants and supporting utilities for the transturing WASM executor.

This module defines the opcode constants, their name mappings, and 32-bit
integer constants used throughout the transturing WASM executor. Each opcode
is a small integer that represents a virtual machine instruction in the
execution trace.

The opcodes are organised into logical groups mirroring the WebAssembly
instruction set: stack manipulation, arithmetic, comparison, bitwise,
shift, unary, local-variable, memory, and control-flow operations.

Attributes:
    OP_*: Integer constants, one per supported VM instruction.
    OP_NAMES: Mapping from opcode integers to human-readable names.
    MASK32: 32-bit mask for unsigned wrapping arithmetic.
    I32_SIGN_BIT / I32_MODULO: Constants for 32-bit sign handling.
    I8_SIGN_BIT / I8_RANGE: Constants for 8-bit sign extension.
    I16_SIGN_BIT / I16_RANGE: Constants for 16-bit sign extension.
    CLZ_THRESHOLDS / CLZ_SHIFTS: Lookup tables for branch-free CLZ.

"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stack operations
# ---------------------------------------------------------------------------
OP_PUSH = 1
OP_POP = 2
OP_ADD = 3
OP_DUP = 4
OP_HALT = 5

# ---------------------------------------------------------------------------
# Stack / control helpers
# ---------------------------------------------------------------------------
OP_SUB = 6
OP_JZ = 7
OP_JNZ = 8
OP_NOP = 9

# ---------------------------------------------------------------------------
# Stack manipulation helpers
# ---------------------------------------------------------------------------
OP_SWAP = 10
OP_OVER = 11
OP_ROT = 12

# ---------------------------------------------------------------------------
# Arithmetic operations
# ---------------------------------------------------------------------------
OP_MUL = 13
OP_DIV_S = 14
OP_DIV_U = 15
OP_REM_S = 16
OP_REM_U = 17

# ---------------------------------------------------------------------------
# Comparison operations
# ---------------------------------------------------------------------------
OP_EQZ = 18
OP_EQ = 19
OP_NE = 20
OP_LT_S = 21
OP_LT_U = 22
OP_GT_S = 23
OP_GT_U = 24
OP_LE_S = 25
OP_LE_U = 26
OP_GE_S = 27
OP_GE_U = 28

# ---------------------------------------------------------------------------
# Bitwise and shift operations
# ---------------------------------------------------------------------------
OP_AND = 29
OP_OR = 30
OP_XOR = 31

# Shift / rotate operations
OP_SHL = 32
OP_SHR_S = 33
OP_SHR_U = 34
OP_ROTL = 35
OP_ROTR = 36

# ---------------------------------------------------------------------------
# Unary operations
# ---------------------------------------------------------------------------
OP_CLZ = 37
OP_CTZ = 38
OP_POPCNT = 39
OP_ABS = 40
OP_NEG = 41
OP_SELECT = 42

# ---------------------------------------------------------------------------
# Local variable operations
# ---------------------------------------------------------------------------
OP_LOCAL_GET = 43
OP_LOCAL_SET = 44
OP_LOCAL_TEE = 45

# ---------------------------------------------------------------------------
# Memory operations
# ---------------------------------------------------------------------------
OP_I32_LOAD = 46
OP_I32_STORE = 47
OP_I32_LOAD8_U = 48
OP_I32_LOAD8_S = 49
OP_I32_LOAD16_U = 50
OP_I32_LOAD16_S = 51
OP_I32_STORE8 = 52
OP_I32_STORE16 = 53

# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------
OP_CALL = 54
OP_RETURN = 55

# ---------------------------------------------------------------------------
# Special
# ---------------------------------------------------------------------------
OP_TRAP = 99

N_OPCODES = 55

# Maps opcode integers to human-readable names for trace formatting.
OP_NAMES = {
    OP_PUSH: "PUSH",
    OP_POP: "POP",
    OP_ADD: "ADD",
    OP_DUP: "DUP",
    OP_HALT: "HALT",
    OP_SUB: "SUB",
    OP_JZ: "JZ",
    OP_JNZ: "JNZ",
    OP_NOP: "NOP",
    OP_SWAP: "SWAP",
    OP_OVER: "OVER",
    OP_ROT: "ROT",
    OP_MUL: "MUL",
    OP_DIV_S: "DIV_S",
    OP_DIV_U: "DIV_U",
    OP_REM_S: "REM_S",
    OP_REM_U: "REM_U",
    OP_EQZ: "EQZ",
    OP_EQ: "EQ",
    OP_NE: "NE",
    OP_LT_S: "LT_S",
    OP_LT_U: "LT_U",
    OP_GT_S: "GT_S",
    OP_GT_U: "GT_U",
    OP_LE_S: "LE_S",
    OP_LE_U: "LE_U",
    OP_GE_S: "GE_S",
    OP_GE_U: "GE_U",
    OP_AND: "AND",
    OP_OR: "OR",
    OP_XOR: "XOR",
    OP_SHL: "SHL",
    OP_SHR_S: "SHR_S",
    OP_SHR_U: "SHR_U",
    OP_ROTL: "ROTL",
    OP_ROTR: "ROTR",
    OP_CLZ: "CLZ",
    OP_CTZ: "CTZ",
    OP_POPCNT: "POPCNT",
    OP_ABS: "ABS",
    OP_NEG: "NEG",
    OP_SELECT: "SELECT",
    OP_LOCAL_GET: "LOCAL.GET",
    OP_LOCAL_SET: "LOCAL.SET",
    OP_LOCAL_TEE: "LOCAL.TEE",
    OP_I32_LOAD: "I32.LOAD",
    OP_I32_STORE: "I32.STORE",
    OP_I32_LOAD8_U: "I32.LOAD8_U",
    OP_I32_LOAD8_S: "I32.LOAD8_S",
    OP_I32_LOAD16_U: "I32.LOAD16_U",
    OP_I32_LOAD16_S: "I32.LOAD16_S",
    OP_I32_STORE8: "I32.STORE8",
    OP_I32_STORE16: "I32.STORE16",
    OP_CALL: "CALL",
    OP_RETURN: "RETURN",
    OP_TRAP: "TRAP",
}

# 32-bit mask used for unsigned wrapping arithmetic.
MASK32 = 0xFFFFFFFF

# Sign extension and modular arithmetic constants for i32, i8, and i16 values.
# These are used when interpreting unsigned bytes/words as signed integers
# and when performing modular wrap-around in 32-bit arithmetic.
I32_SIGN_BIT = 0x80000000
I32_MODULO = 0x100000000
I8_SIGN_BIT = 0x80
I8_RANGE = 0x100
I16_SIGN_BIT = 0x8000
I16_RANGE = 0x10000

# Lookup tables for the branch-free count-leading-zeros (CLZ) implementation.
# CLZ_THRESHOLDS holds bitmasks used at each stage; CLZ_SHIFTS holds the
# corresponding shift amounts that accumulate into the final result.
CLZ_THRESHOLDS = [0x0000FFFF, 0x00FFFFFF, 0x0FFFFFFF, 0x3FFFFFFF, 0x7FFFFFFF]
CLZ_SHIFTS = [16, 8, 4, 2, 1]

__all__ = [
    "CLZ_SHIFTS",
    "CLZ_THRESHOLDS",
    "I8_RANGE",
    "I8_SIGN_BIT",
    "I16_RANGE",
    "I16_SIGN_BIT",
    "I32_MODULO",
    "I32_SIGN_BIT",
    "MASK32",
    "N_OPCODES",
    "OP_ABS",
    "OP_ADD",
    "OP_AND",
    "OP_CALL",
    "OP_CLZ",
    "OP_CTZ",
    "OP_DIV_S",
    "OP_DIV_U",
    "OP_DUP",
    "OP_EQ",
    "OP_EQZ",
    "OP_GE_S",
    "OP_GE_U",
    "OP_GT_S",
    "OP_GT_U",
    "OP_HALT",
    "OP_I32_LOAD",
    "OP_I32_LOAD8_S",
    "OP_I32_LOAD8_U",
    "OP_I32_LOAD16_S",
    "OP_I32_LOAD16_U",
    "OP_I32_STORE",
    "OP_I32_STORE8",
    "OP_I32_STORE16",
    "OP_JNZ",
    "OP_JZ",
    "OP_LE_S",
    "OP_LE_U",
    "OP_LT_S",
    "OP_LT_U",
    "OP_MUL",
    "OP_NAMES",
    "OP_NE",
    "OP_NEG",
    "OP_NOP",
    "OP_OR",
    "OP_OVER",
    "OP_POP",
    "OP_POPCNT",
    "OP_PUSH",
    "OP_REM_S",
    "OP_REM_U",
    "OP_RETURN",
    "OP_ROT",
    "OP_ROTL",
    "OP_ROTR",
    "OP_SELECT",
    "OP_SHL",
    "OP_SHR_S",
    "OP_SHR_U",
    "OP_SUB",
    "OP_SWAP",
    "OP_TRAP",
    "OP_XOR",
]
