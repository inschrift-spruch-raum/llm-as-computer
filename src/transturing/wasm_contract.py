"""
Validated contract types for the WASM execution pipeline.

This module defines the validated contract types that sit between the raw
binary decoder (``wasm_binary``) and the executor (``executor``).  It provides
a clean, validated representation of a WASM module ready for execution, along
with the :class:`WasmDirectExecutor` protocol that executors must implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .trace import Trace
    from .wasm_binary import WasmBinaryModule

from .wasm_binary import auto_detect_function


@dataclass(frozen=True)
class WasmFunctionContract:
    """
    A validated WASM function ready for execution.

    Contains pre-computed counts (``n_params``, ``n_results``, ``n_locals``)
    instead of full type lists, and the decoded instruction body.

    Attributes:
        index: Function index within the module.
        n_params: Number of parameters the function accepts.
        n_results: Number of values the function returns.
        n_locals: Number of local variables declared in the function body.
        body: Decoded instruction tuples representing the function body.
        export_names: Names under which this function is exported.

    """

    index: int
    n_params: int
    n_results: int
    n_locals: int
    body: list[tuple[str] | tuple[str, int] | tuple[str, list[int], int]]
    export_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WasmMemoryContract:
    """
    A validated memory declaration with optional maximum page limit.

    Attributes:
        min_pages: Minimum number of 64 KiB pages the memory must have.
        max_pages: Maximum number of pages the memory may grow to, or
            ``None`` for unbounded growth.

    """

    min_pages: int
    max_pages: int | None = None


@dataclass(frozen=True)
class ValidatedWasmModule:
    """
    A fully validated WASM module ready for execution.

    Contains all function contracts, an optional memory contract, and the
    index of the entry-point function.

    Attributes:
        functions: List of validated function contracts in module order.
        memory: Memory contract if the module declares linear memory, otherwise
            ``None``.
        entry_function_index: Index into :attr:`functions` of the auto-detected
            entry-point function.

    """

    functions: list[WasmFunctionContract]
    memory: WasmMemoryContract | None
    entry_function_index: int


def validated_module_from_binary(module: WasmBinaryModule) -> ValidatedWasmModule:
    """
    Convert a raw decoded ``WasmBinaryModule`` into a validated ``ValidatedWasmModule``.

    Validates that the module contains at least one function and auto-detects
    the entry point using :func:`~transturing.wasm_binary.auto_detect_function`.

    Args:
        module: The raw decoded WASM binary module produced by
            :func:`~transturing.wasm_binary.parse_wasm_binary`.

    Returns:
        A fully validated :class:`ValidatedWasmModule` ready for execution.

    Raises:
        ValueError: If the module contains no functions.

    """
    if not module.functions:
        msg = "Cannot create ValidatedWasmModule: module has no functions"
        raise ValueError(msg)

    entry = auto_detect_function(module)
    functions = [
        WasmFunctionContract(
            index=f.index,
            n_params=len(f.params),
            n_results=len(f.results),
            n_locals=len(f.locals),
            body=list(f.body),
            export_names=list(f.export_names),
        )
        for f in module.functions
    ]
    memory = (
        WasmMemoryContract(
            min_pages=module.memories[0].min_pages,
            max_pages=module.memories[0].max_pages,
        )
        if module.memories
        else None
    )
    return ValidatedWasmModule(
        functions=functions,
        memory=memory,
        entry_function_index=entry.index,
    )


class WasmDirectExecutor(Protocol):
    """
    Protocol (interface) that WASM executors must implement.

    Implementations receive a validated module and produce a structured
    execution trace by stepping through the module's instructions.
    """

    def execute_wasm(
        self,
        module: ValidatedWasmModule,
        *,
        args: list[int] | None = None,
        max_steps: int = 50000,
    ) -> Trace:
        """
        Execute a validated WASM module and return the execution trace.

        Args:
            module: A fully validated WASM module produced by
                :func:`validated_module_from_binary`.
            args: Arguments to pass to the entry-point function.  Defaults to
                an empty list.
            max_steps: Safety limit on the number of instructions to execute.
                Defaults to 50 000.

        Returns:
            A :class:`~transturing.trace.Trace` containing every recorded
            execution step.

        """
        ...


__all__ = [
    "ValidatedWasmModule",
    "WasmDirectExecutor",
    "WasmFunctionContract",
    "WasmMemoryContract",
    "validated_module_from_binary",
]
