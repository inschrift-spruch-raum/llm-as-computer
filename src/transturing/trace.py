"""
Execution trace data structures.

This module defines the execution trace data structures. A Trace captures the
step-by-step record of a WASM execution, including the opcode executed, its
argument, the stack pointer position, and the top-of-stack value at each step.
The WasmInstr type alias represents decoded WASM instructions in tuple form.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .opcodes import (
    OP_CALL,
    OP_JNZ,
    OP_JZ,
    OP_LOCAL_GET,
    OP_LOCAL_SET,
    OP_LOCAL_TEE,
    OP_NAMES,
    OP_PUSH,
)

type WasmInstr = tuple[str] | tuple[str, int] | tuple[str, list[int], int]
"""Decoded WASM instruction represented as a tuple.

The three possible tuple shapes are:

- ``(name,)`` -- a simple instruction with no argument (e.g. ``add``, ``drop``).
- ``(name, arg)`` -- an instruction with a single integer argument (e.g.
  ``("local.get", 0)``).
- ``(name, labels, default)`` -- a branch instruction with a list of label
  targets and a default fall-through index (e.g. ``("br_table", [1, 2], 0)``).
"""


@dataclass
class TraceStep:
    """
    Represents a single step in the execution trace.

    Attributes:
        op: Opcode constant identifying the instruction that was executed.
        arg: Instruction argument, e.g. a local variable index or a push value.
        sp: Stack pointer position after this step.
        top: Value on top of the stack after this step.

    """

    op: int
    arg: int
    sp: int
    top: int

    def tokens(self) -> list[int]:
        """
        Return the trace step as a flat list of four integers.

        Returns:
            A list ``[op, arg, sp, top]`` suitable for tokenization in
            transformer input.

        """
        return [self.op, self.arg, self.sp, self.top]


@dataclass
class Trace:
    """
    An execution trace of a WASM program.

    The ``program`` field is reserved for future use (e.g. storing the WASM
    module metadata). The ``steps`` list records each instruction execution in
    order.

    Attributes:
        program: Optional program descriptor or metadata.
        steps: Ordered list of individual trace steps.

    """

    program: list[object]
    steps: list[TraceStep] = field(default_factory=list)

    def format_trace(self) -> str:
        """
        Format the entire execution trace as a human-readable table.

        The table includes columns for step number, instruction name (with
        argument if applicable), stack pointer, and top-of-stack value.

        Returns:
            A multi-line string representing the formatted trace.

        """
        lines: list[str] = []
        lines.append(f"Program: {' ; '.join(str(i) for i in self.program)}")
        lines.append(f"{'Step':>4}  {'Instruction':<10} {'SP':>3}  {'TOP':>5}")
        lines.append("-" * 35)
        for i, s in enumerate(self.steps):
            name = OP_NAMES.get(s.op, "?")
            instr_str = (
                f"{name} {s.arg}"
                if s.op
                in (
                    OP_PUSH,
                    OP_JZ,
                    OP_JNZ,
                    OP_LOCAL_GET,
                    OP_LOCAL_SET,
                    OP_LOCAL_TEE,
                    OP_CALL,
                )
                else name
            )
            lines.append(f"{i:4d}  {instr_str:<10} {s.sp:3d}  {s.top:5d}")
        return "\n".join(lines)


__all__ = [
    "Trace",
    "TraceStep",
    "WasmInstr",
]
