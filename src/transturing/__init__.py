"""
LLM-as-Computer: compiled transformer executor.

Three-layer architecture:
  - core: Zero-dependency ISA, types, programs, assemblers
  - backends.numpy: NumPy-based demo executor
  - backends.torch: PyTorch-based production executor
"""

from .core.isa import (
    D_MODEL,
    MASK32,
    N_OPCODES,
    TOKENS_PER_STEP,
    Instruction,
    Trace,
    TraceStep,
    compare_traces,
    program,
    test_algorithm,
    test_trap_algorithm,
)
from .core.registry import get_executor, list_backends

__all__ = [
    "D_MODEL",
    "MASK32",
    "N_OPCODES",
    "TOKENS_PER_STEP",
    "Instruction",
    "Trace",
    "TraceStep",
    "compare_traces",
    "get_executor",
    "list_backends",
    "program",
    "test_algorithm",
    "test_trap_algorithm",
]
