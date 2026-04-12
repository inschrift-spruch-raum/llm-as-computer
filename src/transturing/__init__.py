"""
transturing - An executor-only transformer runtime for the i32 subset of WASM32.

This package provides tools to parse WASM binary modules, validate them,
and execute them while recording detailed execution traces suitable for
transformer model input.

Public exports:

    TorchExecutor: Stack-based WASM interpreter that executes validated modules
        and produces structured execution traces.
    Trace: Container for a complete execution trace, holding all recorded steps.
    TraceStep: Individual execution step record capturing opcode, operand,
        stack pointer, and stack-top value.
"""

from .executor import TorchExecutor
from .trace import Trace, TraceStep

__all__ = [
    "TorchExecutor",
    "Trace",
    "TraceStep",
]
