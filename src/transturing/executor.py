"""
Core WASM interpreter executor.

This module implements the core WASM interpreter executor.  It executes
validated WASM modules instruction by instruction, recording each step as a
``TraceStep``.  The interpreter supports stack-based arithmetic, comparison,
bitwise, shift, unary, memory, local variable, and control flow operations on
the i32 subset of WebAssembly.

Architecture:
    The executor is structured around two dispatch tables:

    - **Control-flow dispatch** (``_CF_DISPATCH``): handles ``BLOCK``, ``LOOP``,
      ``IF``, ``ELSE``, ``END``, ``BR``, ``BR_IF``, and ``BR_TABLE``.  Each
      handler returns the new instruction pointer.
    - **Step dispatch** (``_STEP_DISPATCH``): handles all other instructions
      (arithmetic, comparison, bitwise, shift, unary, memory, local variable,
      ``CALL``, ``PUSH``, ``POP``, ``SELECT``, ``RETURN``, ``NOP``).  Each
      handler mutates the operand stack and records a ``TraceStep``.

Execution state is split into:

    - ``_ExecState``: shared mutable state across function calls (memory,
      trace recorder, stack pointer, step limit, module reference).
    - ``_ExecCtx``: per-function execution context (instruction body, IP,
      operand stack, label stack, local variables).

Non-local control flow (traps and returns) is implemented via private
exceptions (``_TrapError``, ``_ReturnError``) that are caught in the main
interpreter loop.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from transturing.opcodes import (
    MASK32,
    OP_ADD,
    OP_AND,
    OP_CALL,
    OP_CLZ,
    OP_CTZ,
    OP_DIV_S,
    OP_DIV_U,
    OP_EQ,
    OP_EQZ,
    OP_GE_S,
    OP_GE_U,
    OP_GT_S,
    OP_GT_U,
    OP_HALT,
    OP_I32_LOAD,
    OP_I32_LOAD8_S,
    OP_I32_LOAD8_U,
    OP_I32_LOAD16_S,
    OP_I32_LOAD16_U,
    OP_I32_STORE,
    OP_I32_STORE8,
    OP_I32_STORE16,
    OP_LE_S,
    OP_LE_U,
    OP_LOCAL_GET,
    OP_LOCAL_SET,
    OP_LOCAL_TEE,
    OP_LT_S,
    OP_LT_U,
    OP_MUL,
    OP_NE,
    OP_NOP,
    OP_OR,
    OP_POP,
    OP_POPCNT,
    OP_PUSH,
    OP_REM_S,
    OP_REM_U,
    OP_RETURN,
    OP_ROTL,
    OP_ROTR,
    OP_SELECT,
    OP_SHL,
    OP_SHR_S,
    OP_SHR_U,
    OP_SUB,
    OP_TRAP,
    OP_XOR,
)
from transturing.trace import Trace, TraceStep, WasmInstr
from transturing.wasm_math import (
    clz32,
    ctz32,
    popcnt32,
    rotl32,
    rotr32,
    shr_s,
    shr_u,
    to_i32,
    trunc_div,
    trunc_rem,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from transturing.wasm_contract import ValidatedWasmModule, WasmFunctionContract

_I8_SIGN_THRESHOLD = 128
_I16_SIGN_THRESHOLD = 32768

_CMP_NAME_TO_OP: dict[str, int] = {
    "EQ": OP_EQ,
    "NE": OP_NE,
    "LT_S": OP_LT_S,
    "LT_U": OP_LT_U,
    "GT_S": OP_GT_S,
    "GT_U": OP_GT_U,
    "LE_S": OP_LE_S,
    "LE_U": OP_LE_U,
    "GE_S": OP_GE_S,
    "GE_U": OP_GE_U,
}

_CMP_FUNCS: dict[str, Callable[[int, int], bool]] = {
    "EQ": operator.eq,
    "NE": operator.ne,
    "LT_S": operator.lt,
    "LT_U": operator.lt,
    "GT_S": operator.gt,
    "GT_U": operator.gt,
    "LE_S": operator.le,
    "LE_U": operator.le,
    "GE_S": operator.ge,
    "GE_U": operator.ge,
}

_SIMPLE_ARITH: dict[str, Callable[[int, int], int]] = {
    "ADD": lambda a, b: (a + b) & MASK32,
    "SUB": lambda a, b: (a - b) & MASK32,
    "MUL": lambda a, b: (a * b) & MASK32,
}
_SIMPLE_ARITH_OP: dict[str, int] = {"ADD": OP_ADD, "SUB": OP_SUB, "MUL": OP_MUL}

_BITWISE_OPS: dict[str, Callable[[int, int], int]] = {
    "AND": lambda a, b: to_i32(a) & to_i32(b),
    "OR": lambda a, b: to_i32(a) | to_i32(b),
    "XOR": lambda a, b: to_i32(a) ^ to_i32(b),
}
_BITWISE_OP: dict[str, int] = {"AND": OP_AND, "OR": OP_OR, "XOR": OP_XOR}

_SHIFT_OPS: dict[str, Callable[[int, int], int]] = {
    "SHL": lambda a, b: (to_i32(a) << (to_i32(b) & 31)) & MASK32,
    "SHR_S": shr_s,
    "SHR_U": shr_u,
    "ROTL": rotl32,
    "ROTR": rotr32,
}
_SHIFT_OP: dict[str, int] = {
    "SHL": OP_SHL,
    "SHR_S": OP_SHR_S,
    "SHR_U": OP_SHR_U,
    "ROTL": OP_ROTL,
    "ROTR": OP_ROTR,
}

_UNARY_OPS: dict[str, Callable[[int], int]] = {
    "CLZ": clz32,
    "CTZ": ctz32,
    "POPCNT": popcnt32,
}
_UNARY_OP: dict[str, int] = {"CLZ": OP_CLZ, "CTZ": OP_CTZ, "POPCNT": OP_POPCNT}


def _extract_i8s(raw: int) -> int:
    val = raw & 0xFF
    return val - 256 if val >= _I8_SIGN_THRESHOLD else val


def _extract_i16s(raw: int) -> int:
    val = raw & 0xFFFF
    return val - 65536 if val >= _I16_SIGN_THRESHOLD else val


_LOAD_EXTRACT: dict[str, Callable[[int], int]] = {
    "I32.LOAD": lambda raw: raw,
    "I32.LOAD8_U": lambda raw: raw & 0xFF,
    "I32.LOAD8_S": _extract_i8s,
    "I32.LOAD16_U": lambda raw: raw & 0xFFFF,
    "I32.LOAD16_S": _extract_i16s,
}
_LOAD_OP: dict[str, int] = {
    "I32.LOAD": OP_I32_LOAD,
    "I32.LOAD8_U": OP_I32_LOAD8_U,
    "I32.LOAD8_S": OP_I32_LOAD8_S,
    "I32.LOAD16_U": OP_I32_LOAD16_U,
    "I32.LOAD16_S": OP_I32_LOAD16_S,
}

_STORE_OP: dict[str, int] = {
    "I32.STORE": OP_I32_STORE,
    "I32.STORE8": OP_I32_STORE8,
    "I32.STORE16": OP_I32_STORE16,
}

_STORE_MASK: dict[str, int] = {
    "I32.STORE": MASK32,
    "I32.STORE8": 0xFF,
    "I32.STORE16": 0xFFFF,
}


# ── Exceptions for non-local control flow ──────────────────────────────────


class _TrapError(Exception):
    """Internal exception raised when a WASM trap occurs (e.g., division by zero)."""


class _ReturnError(Exception):
    """Internal exception carrying a return value for non-local WASM returns."""

    def __init__(self, value: int) -> None:
        self.value = value


# ── Shared mutable state ───────────────────────────────────────────────────


@dataclass
class _ExecState:
    """
    Shared mutable execution state.

    This dataclass holds state that persists across nested function calls within
    a single ``execute_wasm`` invocation.

    Attributes:
        memory: Sparse linear memory, mapping byte addresses to 32-bit values.
        trace: The trace recorder that collects ``TraceStep`` entries.
        sp: The global stack pointer (tracks the depth of the operand stack).
        max_steps: Upper bound on the number of non-control-flow steps to
            execute before halting (prevents infinite loops).
        module: The validated WASM module being executed.

    """

    memory: dict[int, int]
    trace: Trace
    sp: int
    max_steps: int
    module: ValidatedWasmModule


@dataclass
class _ExecCtx:
    """
    Per-function execution context.

    A fresh ``_ExecCtx`` is created for every WASM function invocation (including
    the entry function and any nested ``CALL`` targets).

    Attributes:
        body: The instruction body of the current function (list of ``WasmInstr``).
        ip: The instruction pointer — index into ``body`` for the next instruction.
        stack: The local operand stack for this function invocation.
        label_stack: Stack of ``(kind, target_ip)`` tuples used for control-flow
            branching.  ``kind`` is one of ``"block"``, ``"loop"``, or ``"if"``.
        locals_vals: Values of local variables (params followed by declared locals).

    """

    body: list[WasmInstr]
    ip: int
    stack: list[int]
    label_stack: list[tuple[str, int]]
    locals_vals: list[int]


# ── Small helpers ──────────────────────────────────────────────────────────


def _ctx_top(ctx: _ExecCtx) -> int:
    """
    Return the top of the operand stack, or 0 if empty.

    Args:
        ctx: The current execution context.

    Returns:
        The topmost value on the operand stack, or ``0`` when the stack is
        empty.

    """
    return ctx.stack[-1] if ctx.stack else 0


def _scan_end_else(body: list[WasmInstr], start_ip: int) -> int:
    """
    Scan forward to find the matching END instruction, accounting for nesting depth.

    Starting at ``start_ip``, walks the instruction body forward and tracks the
    nesting depth of ``BLOCK`` / ``LOOP`` / ``IF`` constructs.  Returns the
    index of the first ``END`` instruction that balances the nesting depth back
    to zero.

    Args:
        body: The full instruction body of the current function.
        start_ip: The instruction pointer from which to begin scanning
            (typically the instruction after a ``BLOCK``, ``LOOP``, or ``IF``).

    Returns:
        The index of the matching ``END`` instruction, or ``len(body) - 1``
        if no matching ``END`` is found (should not happen in validated code).

    """
    depth = 0
    ip = start_ip
    while ip < len(body):
        name = body[ip][0]
        if name in ("BLOCK", "LOOP", "IF"):
            depth += 1
        elif name == "END":
            if depth == 0:
                return ip
            depth -= 1
        ip += 1
    return len(body) - 1


def _find_else(body: list[WasmInstr], start: int, end: int) -> int | None:
    """
    Find the ELSE instruction at the current nesting level within a range.

    Scans ``body[start : end + 1]`` for an ``ELSE`` that sits at depth zero
    (i.e. is not nested inside a deeper ``BLOCK`` / ``LOOP`` / ``IF``).

    Args:
        body: The full instruction body of the current function.
        start: The first index to inspect (inclusive).
        end: The last index to inspect (inclusive).

    Returns:
        The index of the matching ``ELSE`` instruction, or ``None`` if the
        ``IF`` block has no ``ELSE`` clause.

    """
    depth = 0
    for si in range(start, end + 1):
        sn = body[si][0]
        if sn in ("BLOCK", "LOOP", "IF"):
            depth += 1
        elif sn == "END" and depth > 0:
            depth -= 1
        elif sn == "ELSE" and depth == 0:
            return si
    return None


def _branch_target(
    label_stack: list[tuple[str, int]], depth: int, body_len: int
) -> int:
    """
    Compute the target instruction pointer for a branch given a label depth.

    For ``block`` / ``if`` labels the branch targets the continuation point
    (the instruction after the matching ``END``), and all labels at or above
    the target depth are popped.  For ``loop`` labels the branch targets the
    loop header (the instruction after the ``LOOP``) and the label stack is
    left intact so the loop can be re-entered.

    Args:
        label_stack: The current label stack (modified in place for non-loop
            branches).
        depth: The label depth to branch to (0 = innermost label).
        body_len: The length of the instruction body (used as a fallback).

    Returns:
        The instruction pointer to jump to.

    """
    target = len(label_stack) - 1 - depth
    if 0 <= target < len(label_stack):
        kind, addr = label_stack[target]
        if kind != "loop":
            del label_stack[target:]
        return addr
    return body_len


# ── Control-flow handlers (return new ip) ──────────────────────────────────


def _cf_block(_instr: WasmInstr, ctx: _ExecCtx, _state: _ExecState) -> int:
    """
    Handle a BLOCK instruction.

    Pushes a ``("block", end_ip + 1)`` label onto the label stack so that
    ``br`` targeting this block jumps to the instruction after the matching
    ``END``.

    Args:
        _instr: The BLOCK instruction (unused beyond identification).
        ctx: The current execution context.
        _state: The shared execution state (unused).

    Returns:
        The instruction pointer for the next instruction (the first
        instruction inside the block).

    """
    end_ip = _scan_end_else(ctx.body, ctx.ip + 1)
    ctx.label_stack.append(("block", end_ip + 1))
    return ctx.ip + 1


def _cf_loop(_instr: WasmInstr, ctx: _ExecCtx, _state: _ExecState) -> int:
    """
    Handle a LOOP instruction.

    Pushes a ``("loop", ip + 1)`` label onto the label stack so that ``br``
    targeting this loop jumps back to the top of the loop body.

    Args:
        _instr: The LOOP instruction (unused beyond identification).
        ctx: The current execution context.
        _state: The shared execution state (unused).

    Returns:
        The instruction pointer for the next instruction (the first
        instruction inside the loop body).

    """
    ctx.label_stack.append(("loop", ctx.ip + 1))
    return ctx.ip + 1


def _cf_if(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> int:
    """
    Handle an IF instruction.

    Pops the condition value from the operand stack.  If the condition is
    non-zero, execution continues at the next instruction (the "then" branch).
    If the condition is zero, execution jumps to the ELSE clause if one exists,
    or to the instruction after the matching END otherwise.

    Args:
        _instr: The IF instruction (unused beyond identification).
        ctx: The current execution context.
        state: The shared execution state (``sp`` is decremented).

    Returns:
        The instruction pointer for the chosen branch.

    """
    cond = ctx.stack.pop() if ctx.stack else 0
    state.sp -= 1
    end_ip = _scan_end_else(ctx.body, ctx.ip + 1)
    else_ip = _find_else(ctx.body, ctx.ip + 1, end_ip)
    ctx.label_stack.append(("if", end_ip + 1))
    if cond == 0:
        return else_ip + 1 if else_ip is not None else end_ip + 1
    return ctx.ip + 1


def _cf_else(_instr: WasmInstr, ctx: _ExecCtx, _state: _ExecState) -> int:
    """
    Handle an ELSE instruction.

    When encountered during execution of the "then" branch of an IF block,
    jumps to the continuation point (the instruction after the matching END).

    Args:
        _instr: The ELSE instruction (unused beyond identification).
        ctx: The current execution context.
        _state: The shared execution state (unused).

    Returns:
        The instruction pointer for the continuation after the IF block.

    """
    _, cont = ctx.label_stack[-1]
    ctx.label_stack.pop()
    return cont


def _cf_end(_instr: WasmInstr, ctx: _ExecCtx, _state: _ExecState) -> int:
    """
    Handle an END instruction.

    Pops the innermost label from the label stack (if any), signalling the
    end of a BLOCK, LOOP, or IF construct.

    Args:
        _instr: The END instruction (unused beyond identification).
        ctx: The current execution context.
        _state: The shared execution state (unused).

    Returns:
        The instruction pointer for the next instruction.

    """
    if ctx.label_stack:
        ctx.label_stack.pop()
    return ctx.ip + 1


def _cf_br(instr: WasmInstr, ctx: _ExecCtx, _state: _ExecState) -> int:
    """
    Handle an unconditional BR (branch) instruction.

    Reads the branch depth from the instruction operand and computes the
    target instruction pointer via ``_branch_target``.

    Args:
        instr: The BR instruction; ``instr[1]`` is the label depth (default 0).
        ctx: The current execution context.
        _state: The shared execution state (unused).

    Returns:
        The target instruction pointer for the branch.

    """
    depth: int = instr[1] if len(instr) > 1 else 0  # type: ignore[index]
    return _branch_target(ctx.label_stack, depth, len(ctx.body))


def _cf_br_if(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> int:
    """
    Handle a conditional BR_IF instruction.

    Pops the condition value from the operand stack.  If the condition is
    non-zero, performs an unconditional branch to the label at the given
    depth.  Otherwise, continues to the next instruction.

    Args:
        instr: The BR_IF instruction; ``instr[1]`` is the label depth.
        ctx: The current execution context.
        state: The shared execution state (``sp`` is decremented).

    Returns:
        The target instruction pointer if the branch is taken, otherwise
        ``ctx.ip + 1``.

    """
    cond = ctx.stack.pop() if ctx.stack else 0
    state.sp -= 1
    if cond != 0:
        br_depth: int = instr[1] if len(instr) > 1 else 0  # type: ignore[index]
        return _branch_target(ctx.label_stack, br_depth, len(ctx.body))
    return ctx.ip + 1


def _cf_br_table(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> int:
    """
    Handle a BR_TABLE (computed branch) instruction.

    Pops an index from the operand stack and uses it to select a branch
    target from the label list in the instruction.  If the index is out of
    range, the default label depth is used instead.

    Args:
        instr: The BR_TABLE instruction; ``instr[1]`` is the list of label
            depths and ``instr[2]`` is the default depth.
        ctx: The current execution context.
        state: The shared execution state (``sp`` is decremented).

    Returns:
        The target instruction pointer for the selected branch.

    """
    labels: list[int] = instr[1]  # type: ignore[index]
    default: int = instr[2]  # type: ignore[index]
    idx = ctx.stack.pop() if ctx.stack else 0
    state.sp -= 1
    bt_depth = labels[idx] if idx < len(labels) else default
    return _branch_target(ctx.label_stack, bt_depth, len(ctx.body))


_CF_DISPATCH: dict[str, Callable[[WasmInstr, _ExecCtx, _ExecState], int]] = {
    "BLOCK": _cf_block,
    "LOOP": _cf_loop,
    "IF": _cf_if,
    "ELSE": _cf_else,
    "END": _cf_end,
    "BR": _cf_br,
    "BR_IF": _cf_br_if,
    "BR_TABLE": _cf_br_table,
}


# ── Step handlers ──────────────────────────────────────────────────────────


def _step_arith(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute an arithmetic instruction (ADD, SUB, MUL, DIV_S, DIV_U, REM_S, REM_U).

    Pops two operands, applies the operation, pushes the result, and records
    a ``TraceStep``.  Division and remainder by zero trigger a trap.

    Args:
        instr: The arithmetic instruction (name identifies the operation).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented, trace is
            updated).

    """
    name = instr[0]
    b = ctx.stack.pop() if ctx.stack else 0
    a = ctx.stack.pop() if ctx.stack else 0
    if name in _SIMPLE_ARITH:
        r = _SIMPLE_ARITH[name](a, b)
        state.trace.steps.append(TraceStep(_SIMPLE_ARITH_OP[name], 0, state.sp, r))
    elif name in ("DIV_S", "DIV_U"):
        if b == 0:
            state.trace.steps.append(TraceStep(OP_TRAP, 0, state.sp, 0))
            raise _TrapError
        r = trunc_div(a, b) & MASK32
        opcode = OP_DIV_S if name == "DIV_S" else OP_DIV_U
        state.trace.steps.append(TraceStep(opcode, 0, state.sp, r))
    else:  # REM_S, REM_U
        if b == 0:
            state.trace.steps.append(TraceStep(OP_TRAP, 0, state.sp, 0))
            raise _TrapError
        r = trunc_rem(a, b) & MASK32
        opcode = OP_REM_S if name == "REM_S" else OP_REM_U
        state.trace.steps.append(TraceStep(opcode, 0, state.sp, r))
    state.sp -= 1
    ctx.stack.append(r)


def _step_cmp(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a comparison instruction (EQZ, EQ, NE, LT_S, LT_U, etc.).

    For ``EQZ``, pops one operand; for all others pops two.  Pushes ``1`` if
    the comparison holds, ``0`` otherwise.  Records a ``TraceStep``.

    Args:
        instr: The comparison instruction (name identifies the operation).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented for two-operand
            comparisons, trace is updated).

    """
    name = instr[0]
    if name == "EQZ":
        a = ctx.stack.pop() if ctx.stack else 0
        r = 1 if a == 0 else 0
        state.trace.steps.append(TraceStep(OP_EQZ, 0, state.sp, r))
        ctx.stack.append(r)
        return
    b = ctx.stack.pop() if ctx.stack else 0
    a = ctx.stack.pop() if ctx.stack else 0
    r = 1 if _CMP_FUNCS[name](a, b) else 0
    state.sp -= 1
    ctx.stack.append(r)
    state.trace.steps.append(TraceStep(_CMP_NAME_TO_OP[name], 0, state.sp, r))


def _step_bitwise(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a bitwise instruction (AND, OR, XOR).

    Pops two operands, applies the bitwise operation, pushes the result, and
    records a ``TraceStep``.

    Args:
        instr: The bitwise instruction (name identifies the operation).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented, trace is
            updated).

    """
    name = instr[0]
    b = ctx.stack.pop() if ctx.stack else 0
    a = ctx.stack.pop() if ctx.stack else 0
    r = _BITWISE_OPS[name](a, b)
    state.sp -= 1
    ctx.stack.append(r)
    state.trace.steps.append(TraceStep(_BITWISE_OP[name], 0, state.sp, r))


def _step_shift(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a shift instruction (SHL, SHR_S, SHR_U, ROTL, ROTR).

    Pops the shift amount (``b``) and the value (``a``), applies the shift
    operation, pushes the result, and records a ``TraceStep``.

    Args:
        instr: The shift instruction (name identifies the operation).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented, trace is
            updated).

    """
    name = instr[0]
    b = ctx.stack.pop() if ctx.stack else 0
    a = ctx.stack.pop() if ctx.stack else 0
    r = _SHIFT_OPS[name](a, b)
    state.sp -= 1
    ctx.stack.append(r)
    state.trace.steps.append(TraceStep(_SHIFT_OP[name], 0, state.sp, r))


def _step_unary(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a unary instruction (CLZ, CTZ, POPCNT).

    Pops one operand, applies the unary operation, pushes the result, and
    records a ``TraceStep``.

    Args:
        instr: The unary instruction (name identifies the operation).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (trace is updated; ``sp`` is
            unchanged).

    """
    name = instr[0]
    a = ctx.stack.pop() if ctx.stack else 0
    r = _UNARY_OPS[name](a)
    ctx.stack.append(r)
    state.trace.steps.append(TraceStep(_UNARY_OP[name], 0, state.sp, r))


def _step_load(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a memory load instruction (I32.LOAD, I32.LOAD8_S, etc.).

    Pops the address from the stack, reads the value from linear memory,
    applies the appropriate extraction/sign-extension function, pushes the
    result, and records a ``TraceStep``.

    Args:
        instr: The load instruction (name identifies width and signedness).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (memory is read, trace is updated).

    """
    name = instr[0]
    addr = ctx.stack.pop() if ctx.stack else 0
    raw = state.memory.get(int(addr), 0)
    val = _LOAD_EXTRACT[name](raw)
    ctx.stack.append(val)
    state.trace.steps.append(TraceStep(_LOAD_OP[name], 0, state.sp, val))


def _step_store(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a memory store instruction (I32.STORE, I32.STORE8, etc.).

    Pops the value and then the address from the stack, writes the masked
    value into linear memory, and records a ``TraceStep``.

    Args:
        instr: The store instruction (name identifies width).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (memory is written, ``sp`` is
            decremented by 2, trace is updated).

    """
    name = instr[0]
    val = ctx.stack.pop() if ctx.stack else 0
    addr = ctx.stack.pop() if ctx.stack else 0
    state.memory[int(addr)] = val & _STORE_MASK[name]
    state.sp -= 2
    state.trace.steps.append(TraceStep(_STORE_OP[name], 0, state.sp, _ctx_top(ctx)))


def _step_local(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a local variable instruction (LOCAL.GET, LOCAL.SET, LOCAL.TEE).

    - ``LOCAL.GET``: pushes the value of the local at the given index.
    - ``LOCAL.SET``: pops a value and stores it into the local at the given
      index.
    - ``LOCAL.TEE``: copies the top of the stack into the local at the given
      index without popping.

    Args:
        instr: The local variable instruction; ``instr[1]`` is the local index.
        ctx: The current execution context (operand stack / locals modified).
        state: The shared execution state (``sp`` is adjusted, trace is
            updated).

    """
    name = instr[0]
    idx: int = instr[1]  # type: ignore[index]
    if name == "LOCAL.GET":
        val = ctx.locals_vals[idx] if idx < len(ctx.locals_vals) else 0
        ctx.stack.append(val)
        state.sp += 1
        state.trace.steps.append(TraceStep(OP_LOCAL_GET, idx, state.sp, val))
    elif name == "LOCAL.SET":
        val = ctx.stack.pop() if ctx.stack else 0
        if idx < len(ctx.locals_vals):
            ctx.locals_vals[idx] = val
        state.sp -= 1
        state.trace.steps.append(TraceStep(OP_LOCAL_SET, idx, state.sp, _ctx_top(ctx)))
    else:  # LOCAL.TEE
        val = _ctx_top(ctx)
        if idx < len(ctx.locals_vals):
            ctx.locals_vals[idx] = val
        state.trace.steps.append(TraceStep(OP_LOCAL_TEE, idx, state.sp, val))


def _step_call(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a CALL instruction.

    Pops the callee arguments from the stack, recursively invokes
    ``_exec_wasm_function`` for the callee, and pushes the return value.
    If the callee traps, the trap propagates upward.

    Args:
        _instr: The CALL instruction; ``_instr[1]`` is the function index.
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` tracks the cross-function
            stack, trace is updated with both the CALL and RETURN steps).

    """
    func_idx: int = _instr[1]  # type: ignore[index]
    callee = state.module.functions[func_idx]
    callee_args: list[int] = []
    for _ in range(callee.n_params):
        callee_args.insert(0, ctx.stack.pop() if ctx.stack else 0)
    state.sp -= callee.n_params
    state.trace.steps.append(TraceStep(OP_CALL, func_idx, state.sp, _ctx_top(ctx)))
    ret_val, state.sp, trapped = _exec_wasm_function(callee, callee_args, state)
    if trapped:
        raise _TrapError
    ctx.stack.append(ret_val)
    state.sp += 1
    state.trace.steps.append(TraceStep(OP_RETURN, 0, state.sp, ret_val))


def _step_push(instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a PUSH (i32.const) instruction.

    Pushes the immediate value onto the operand stack and records a
    ``TraceStep``.

    Args:
        instr: The PUSH instruction; ``instr[1]`` is the constant value.
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is incremented, trace is
            updated).

    """
    val: int = instr[1]  # type: ignore[index]
    ctx.stack.append(val)
    state.sp += 1
    state.trace.steps.append(TraceStep(OP_PUSH, val, state.sp, val))


def _step_pop(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a POP (drop) instruction.

    Pops and discards the top value from the operand stack and records a
    ``TraceStep``.

    Args:
        _instr: The POP instruction (unused beyond identification).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented, trace is
            updated).

    """
    if ctx.stack:
        ctx.stack.pop()
    state.sp -= 1
    state.trace.steps.append(TraceStep(OP_POP, 0, state.sp, _ctx_top(ctx)))


def _step_select(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a SELECT instruction.

    Pops three values (``c``, ``b``, ``a``).  If ``c`` is non-zero the result
    is ``a``; otherwise the result is ``b``.  The result is pushed back onto
    the operand stack and a ``TraceStep`` is recorded.

    Args:
        _instr: The SELECT instruction (unused beyond identification).
        ctx: The current execution context (operand stack is modified).
        state: The shared execution state (``sp`` is decremented by 2, trace
            is updated).

    """
    c = ctx.stack.pop() if ctx.stack else 0
    b = ctx.stack.pop() if ctx.stack else 0
    a = ctx.stack.pop() if ctx.stack else 0
    r = a if c != 0 else b
    ctx.stack.append(r)
    state.sp -= 2
    state.trace.steps.append(TraceStep(OP_SELECT, 0, state.sp, r))


def _step_return(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a RETURN instruction.

    Records a ``TraceStep`` with the current top-of-stack as the return value,
    then raises ``_ReturnError`` to unwind back to the caller.

    Args:
        _instr: The RETURN instruction (unused beyond identification).
        ctx: The current execution context (read for the return value).
        state: The shared execution state (trace is updated).

    """
    ret_val = _ctx_top(ctx)
    state.trace.steps.append(TraceStep(OP_RETURN, 0, state.sp, ret_val))
    raise _ReturnError(ret_val)


def _step_nop(_instr: WasmInstr, ctx: _ExecCtx, state: _ExecState) -> None:
    """
    Execute a NOP (no-operation) instruction.

    Records a ``TraceStep`` without modifying the operand stack.

    Args:
        _instr: The NOP instruction (unused beyond identification).
        ctx: The current execution context (read for the current stack top).
        state: The shared execution state (trace is updated).

    """
    state.trace.steps.append(TraceStep(OP_NOP, 0, state.sp, _ctx_top(ctx)))


# ── Step dispatch table ────────────────────────────────────────────────────
# Maps WASM instruction names to their corresponding step handler functions.
# The table is populated below by iterating over the instruction-name dicts
# defined at module level (_SIMPLE_ARITH, _BITWISE_OPS, _SHIFT_OPS, etc.).
# Control-flow instructions (BLOCK, LOOP, IF, ELSE, END, BR, BR_IF, BR_TABLE)
# are handled separately by _CF_DISPATCH and are NOT included here.
# ──────────────────────────────────────────────────────────────────────────

_STEP_DISPATCH: dict[str, Callable[[WasmInstr, _ExecCtx, _ExecState], None]] = {}

for _n in _SIMPLE_ARITH:
    _STEP_DISPATCH[_n] = _step_arith
for _n in ("DIV_S", "DIV_U", "REM_S", "REM_U"):
    _STEP_DISPATCH[_n] = _step_arith
for _n in _CMP_FUNCS:
    _STEP_DISPATCH[_n] = _step_cmp
_STEP_DISPATCH["EQZ"] = _step_cmp
for _n in _BITWISE_OPS:
    _STEP_DISPATCH[_n] = _step_bitwise
for _n in _SHIFT_OPS:
    _STEP_DISPATCH[_n] = _step_shift
for _n in _UNARY_OPS:
    _STEP_DISPATCH[_n] = _step_unary
for _n in _LOAD_EXTRACT:
    _STEP_DISPATCH[_n] = _step_load
for _n in _STORE_OP:
    _STEP_DISPATCH[_n] = _step_store
for _n in ("LOCAL.GET", "LOCAL.SET", "LOCAL.TEE"):
    _STEP_DISPATCH[_n] = _step_local
_STEP_DISPATCH["CALL"] = _step_call
_STEP_DISPATCH["PUSH"] = _step_push
_STEP_DISPATCH["POP"] = _step_pop
_STEP_DISPATCH["SELECT"] = _step_select
_STEP_DISPATCH["RETURN"] = _step_return
_STEP_DISPATCH["NOP"] = _step_nop


# ── Main interpreter loop ─────────────────────────────────────────────────
# The _exec_wasm_function below is the heart of the interpreter.  It creates
# a fresh _ExecCtx per function call and loops through instructions, first
# checking _CF_DISPATCH for control-flow instructions (which return a new IP)
# and falling through to _STEP_DISPATCH for all other instructions (which
# mutate the operand stack and record a TraceStep).  Non-local exits are
# implemented via _TrapError and _ReturnError exceptions.
# ──────────────────────────────────────────────────────────────────────────


def _exec_wasm_function(
    func: WasmFunctionContract,
    params: list[int],
    state: _ExecState,
) -> tuple[int, int, bool]:
    """
    Execute a single WASM function with the given parameters, recording trace steps.

    Creates a fresh ``_ExecCtx`` for the function, initialises locals with the
    supplied parameters and zeros, then enters the main interpreter loop.
    The loop dispatches each instruction to either a control-flow handler
    (which returns the new IP) or a step handler (which mutates the stack and
    records a trace step).  Execution terminates when the IP reaches the end
    of the body, the step limit is exceeded, a trap occurs, or a ``RETURN``
    instruction is executed.

    Args:
        func: The validated WASM function contract to execute.
        params: The argument values to bind to the function's parameters.
        state: The shared execution state (memory, trace, stack pointer, etc.).

    Returns:
        A tuple of ``(return_value, final_sp, trapped_flag)`` where:

        - **return_value** is the top-of-stack value when execution finishes
          (``0`` on trap).
        - **final_sp** is the global stack pointer after execution.
        - **trapped_flag** is ``True`` if a trap (e.g. division by zero)
          occurred, ``False`` otherwise.

    """
    ctx = _ExecCtx(
        body=func.body,
        ip=0,
        stack=[],
        label_stack=[],
        locals_vals=list(params) + [0] * func.n_locals,
    )
    steps = 0

    try:
        while ctx.ip < len(ctx.body) and steps < state.max_steps:
            instr = ctx.body[ctx.ip]
            name = instr[0]

            cf_handler = _CF_DISPATCH.get(name)
            if cf_handler is not None:
                ctx.ip = cf_handler(instr, ctx, state)
                continue

            steps += 1
            step_handler = _STEP_DISPATCH.get(name)
            if step_handler is not None:
                step_handler(instr, ctx, state)
            ctx.ip += 1
    except _TrapError:
        return 0, state.sp, True
    except _ReturnError as ret:
        return ret.value, state.sp, False

    return _ctx_top(ctx), state.sp, False


# ── Public API ─────────────────────────────────────────────────────────────


class TorchExecutor:
    """
    WASM interpreter executor that produces a step-by-step execution trace.

    Implements the ``WasmDirectExecutor`` protocol.  Given a validated WASM
    module and optional arguments, runs the entry function and returns a
    ``Trace`` containing a ``TraceStep`` for every instruction executed.
    """

    def execute_wasm(
        self,
        module: ValidatedWasmModule,
        *,
        args: list[int] | None = None,
        max_steps: int = 50000,
    ) -> Trace:
        """
        Execute the entry function of a validated WASM module.

        Initialises empty linear memory and a fresh ``Trace``, pushes the
        supplied arguments onto the stack, then delegates to
        ``_exec_wasm_function``.  On normal termination an ``OP_HALT`` step is
        appended; on trap the trace ends without a HALT step.

        Args:
            module: A validated WASM module produced by
                ``validated_module_from_binary``.
            args: Optional list of integer arguments to pass to the entry
                function.  Defaults to an empty list.
            max_steps: Maximum number of non-control-flow steps the
                interpreter will execute before stopping.  Prevents infinite
                loops.  Defaults to ``50000``.

        Returns:
            A ``Trace`` object containing the complete execution trace,
            including argument pushes, every instruction step, and a final
            HALT step (unless a trap occurred).

        """
        trace = Trace(program=[])
        entry = module.functions[module.entry_function_index]
        state = _ExecState(
            memory={},
            trace=trace,
            sp=0,
            max_steps=max_steps,
            module=module,
        )
        for arg in args or []:
            state.sp += 1
            trace.steps.append(TraceStep(OP_PUSH, arg, state.sp, arg))
        ret_val, state.sp, trapped = _exec_wasm_function(
            entry,
            list(args or []),
            state,
        )
        if not trapped:
            trace.steps.append(TraceStep(OP_HALT, 0, state.sp, ret_val))
        return trace
