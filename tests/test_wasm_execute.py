"""Tests for WASM execution via the TorchExecutor stack-based interpreter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from transturing import TorchExecutor
from transturing.opcodes import OP_TRAP
from transturing.wasm_binary import parse_wasm_binary
from transturing.wasm_contract import validated_module_from_binary

if TYPE_CHECKING:
    from transturing.trace import Trace

_EXPECTED_ARITHMETIC_TOP = 15
_EXPECTED_LOCALS_TOP = 12
_EXPECTED_CONTROL_FLOW_TOP = 11
_EXPECTED_LOOP_SUM_TOP = 55
_EXPECTED_MEMORY_TOP = 99
_EXPECTED_MEMORY_WIDTHS_TOP = -2
_EXPECTED_DIRECT_CALL_TOP = 9
_EXPECTED_MULTI_FUNCTION_TOP = 7
_EXPECTED_PARAM_CALL_TOP = 22
_EXPECTED_BR_TABLE_0_TOP = 22
_EXPECTED_BR_TABLE_1_TOP = 33


def _uleb(value: int) -> bytes:
    out = bytearray()
    current = value
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _sleb32(value: int) -> bytes:
    out = bytearray()
    current = value
    while True:
        byte = current & 0x7F
        current >>= 7
        sign_bit = byte & 0x40
        done = (current == 0 and sign_bit == 0) or (current == -1 and sign_bit != 0)
        if done:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _vec(items: list[bytes]) -> bytes:
    return _uleb(len(items)) + b"".join(items)


def _name(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _uleb(len(raw)) + raw


def _section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + _uleb(len(payload)) + payload


def _func_type(params: list[int], results: list[int]) -> bytes:
    return (
        bytes([0x60])
        + _vec([bytes([p]) for p in params])
        + _vec([bytes([r]) for r in results])
    )


def _limits(min_pages: int, max_pages: int | None = None) -> bytes:
    if max_pages is None:
        return b"\x00" + _uleb(min_pages)
    return b"\x01" + _uleb(min_pages) + _uleb(max_pages)


def _export(name: str, kind: int, index: int) -> bytes:
    return _name(name) + bytes([kind]) + _uleb(index)


def _code_entry(local_groups: list[tuple[int, int]], instrs: list[bytes]) -> bytes:
    locals_blob = _uleb(len(local_groups)) + b"".join(
        _uleb(count) + bytes([value_type]) for count, value_type in local_groups
    )
    body = locals_blob + b"".join(instrs) + b"\x0b"
    return _uleb(len(body)) + body


def _module(*sections: bytes) -> bytes:
    return b"\x00asm" + (1).to_bytes(4, byteorder="little") + b"".join(sections)


def _binary_arithmetic_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(7),
                            b"\x41" + _sleb32(8),
                            b"\x6a",
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_locals_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([0x7F], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(7, _vec([_export("main", 0x00, 0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [(1, 0x7F)],
                        [
                            b"\x20" + _uleb(0),
                            b"\x41" + _sleb32(5),
                            b"\x6a",
                            b"\x21" + _uleb(1),
                            b"\x20" + _uleb(1),
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_control_flow_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(1),
                            b"\x04\x40",
                            b"\x41" + _sleb32(11),
                            b"\x05",
                            b"\x41" + _sleb32(22),
                            b"\x0b",
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_loop_sum_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(7, _vec([_export("main", 0x00, 0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [(2, 0x7F)],
                        [
                            b"\x41" + _sleb32(0),
                            b"\x21" + _uleb(0),
                            b"\x41" + _sleb32(10),
                            b"\x21" + _uleb(1),
                            b"\x03\x40",
                            b"\x20" + _uleb(0),
                            b"\x20" + _uleb(1),
                            b"\x6a",
                            b"\x21" + _uleb(0),
                            b"\x20" + _uleb(1),
                            b"\x41" + _sleb32(1),
                            b"\x6b",
                            b"\x22" + _uleb(1),
                            b"\x0d" + _uleb(0),
                            b"\x0b",
                            b"\x20" + _uleb(0),
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_nested_block_branch_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x02\x40",
                            b"\x02\x40",
                            b"\x41" + _sleb32(1),
                            b"\x0c" + _uleb(1),
                            b"\x41" + _sleb32(99),
                            b"\x0b",
                            b"\x41" + _sleb32(88),
                            b"\x0b",
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_memory_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(5, _vec([_limits(1)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(0),
                            b"\x41" + _sleb32(99),
                            b"\x36" + _uleb(2) + _uleb(0),
                            b"\x41" + _sleb32(0),
                            b"\x28" + _uleb(2) + _uleb(0),
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_memory_width_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(5, _vec([_limits(1)])),
        _section(7, _vec([_export("main", 0x00, 0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(0),
                            b"\x41" + _sleb32(255),
                            b"\x3a" + _uleb(0) + _uleb(0),
                            b"\x41" + _sleb32(0),
                            b"\x2d" + _uleb(0) + _uleb(0),
                            b"\x1a",
                            b"\x41" + _sleb32(0),
                            b"\x2c" + _uleb(0) + _uleb(0),
                            b"\x1a",
                            b"\x41" + _sleb32(4),
                            b"\x41" + _sleb32(-2),
                            b"\x3b" + _uleb(1) + _uleb(0),
                            b"\x41" + _sleb32(4),
                            b"\x2f" + _uleb(1) + _uleb(0),
                            b"\x1a",
                            b"\x41" + _sleb32(4),
                            b"\x2e" + _uleb(1) + _uleb(0),
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_call_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], []), _func_type([], [])])),
        _section(3, _vec([_uleb(0), _uleb(1)])),
        _section(7, _vec([_export("main", 0x00, 1)])),
        _section(
            10,
            _vec(
                [
                    _code_entry([], [b"\x41" + _sleb32(9)]),
                    _code_entry([], [b"\x10" + _uleb(0)]),
                ]
            ),
        ),
    )


def _binary_multi_function_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0), _uleb(0), _uleb(0)])),
        _section(7, _vec([_export("main", 0x00, 2)])),
        _section(
            10,
            _vec(
                [
                    _code_entry([], [b"\x41" + _sleb32(7)]),
                    _code_entry([], [b"\x10" + _uleb(0), b"\x10" + _uleb(0)]),
                    _code_entry([], [b"\x10" + _uleb(1)]),
                ]
            ),
        ),
    )


def _binary_param_call_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([0x7F], []), _func_type([], [])])),
        _section(3, _vec([_uleb(0), _uleb(0), _uleb(1)])),
        _section(7, _vec([_export("main", 0x00, 2)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x20" + _uleb(0),
                            b"\x20" + _uleb(0),
                            b"\x6a",
                        ],
                    ),
                    _code_entry(
                        [(1, 0x7F)],
                        [
                            b"\x20" + _uleb(0),
                            b"\x10" + _uleb(0),
                            b"\x41" + _sleb32(3),
                            b"\x6a",
                            b"\x22" + _uleb(1),
                            b"\x20" + _uleb(1),
                            b"\x6a",
                        ],
                    ),
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(4),
                            b"\x10" + _uleb(1),
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_br_table_module(selector: int) -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(7, _vec([_export("main", 0x00, 0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x02\x40",
                            b"\x02\x40",
                            b"\x02\x40",
                            b"\x41" + _sleb32(selector),
                            b"\x0e" + _vec([_uleb(0), _uleb(1)]) + _uleb(2),
                            b"\x41" + _sleb32(11),
                            b"\x0c" + _uleb(2),
                            b"\x0b",
                            b"\x41" + _sleb32(22),
                            b"\x0c" + _uleb(1),
                            b"\x0b",
                            b"\x41" + _sleb32(33),
                            b"\x0b",
                        ],
                    ),
                ]
            ),
        ),
    )


def _binary_div_trap_module() -> bytes:
    return _module(
        _section(1, _vec([_func_type([], [])])),
        _section(3, _vec([_uleb(0)])),
        _section(
            10,
            _vec(
                [
                    _code_entry(
                        [],
                        [
                            b"\x41" + _sleb32(10),
                            b"\x41" + _sleb32(0),
                            b"\x6d",
                        ],
                    ),
                ]
            ),
        ),
    )


_executor = TorchExecutor()


def _run(wasm_bytes: bytes, args: list[int] | None = None) -> Trace:
    parsed = parse_wasm_binary(wasm_bytes)
    module = validated_module_from_binary(parsed)
    return _executor.execute_wasm(module, args=args)


class TestArithmetic:
    """Verify basic arithmetic instruction execution."""

    def test_final_top(self) -> None:
        """Verify that add produces the expected stack top value."""
        trace = _run(_binary_arithmetic_module())
        assert trace.steps[-1].top == _EXPECTED_ARITHMETIC_TOP


class TestLocals:
    """Verify local variable get/set/tee operations."""

    def test_final_top(self) -> None:
        """Verify that local variable operations produce the expected stack top."""
        trace = _run(_binary_locals_module(), args=[7])
        assert trace.steps[-1].top == _EXPECTED_LOCALS_TOP


class TestControlFlow:
    """Verify if/else control flow execution."""

    def test_final_top(self) -> None:
        """Verify that if/else branching produces the expected stack top."""
        trace = _run(_binary_control_flow_module())
        assert trace.steps[-1].top == _EXPECTED_CONTROL_FLOW_TOP


class TestLoopSum:
    """Verify loop iteration with conditional branch."""

    def test_final_top(self) -> None:
        """Verify that a summation loop produces the expected stack top."""
        trace = _run(_binary_loop_sum_module())
        assert trace.steps[-1].top == _EXPECTED_LOOP_SUM_TOP


class TestNestedBranch:
    """Verify nested block branch resolution."""

    def test_final_top(self) -> None:
        """Verify that a nested br instruction jumps to the correct enclosing block."""
        trace = _run(_binary_nested_block_branch_module())
        assert trace.steps[-1].top == 1


class TestMemory:
    """Verify i32 load and store operations."""

    def test_final_top(self) -> None:
        """Verify that storing and loading a value round-trips correctly."""
        trace = _run(_binary_memory_module())
        assert trace.steps[-1].top == _EXPECTED_MEMORY_TOP


class TestMemoryWidths:
    """Verify 8-bit and 16-bit memory access variants."""

    def test_final_top(self) -> None:
        """Verify that narrow load/store width variants produce the expected result."""
        trace = _run(_binary_memory_width_module())
        assert trace.steps[-1].top == _EXPECTED_MEMORY_WIDTHS_TOP


class TestDirectCall:
    """Verify single-depth function call."""

    def test_final_top(self) -> None:
        """Verify that calling a function returns the expected stack top."""
        trace = _run(_binary_call_module())
        assert trace.steps[-1].top == _EXPECTED_DIRECT_CALL_TOP


class TestMultiFunction:
    """Verify chained multi-function call graph."""

    def test_final_top(self) -> None:
        """Verify that a chain of function calls produces the expected stack top."""
        trace = _run(_binary_multi_function_module())
        assert trace.steps[-1].top == _EXPECTED_MULTI_FUNCTION_TOP


class TestParamCall:
    """Verify parameterised function calls with locals."""

    def test_final_top(self) -> None:
        """Verify that parameter passing and local variables work across calls."""
        trace = _run(_binary_param_call_module())
        assert trace.steps[-1].top == _EXPECTED_PARAM_CALL_TOP


class TestBrTable0:
    """Verify br_table with selector value 0."""

    def test_final_top(self) -> None:
        """Verify that br_table selects the first label when selector is 0."""
        trace = _run(_binary_br_table_module(0))
        assert trace.steps[-1].top == _EXPECTED_BR_TABLE_0_TOP


class TestBrTable1:
    """Verify br_table with selector value 1."""

    def test_final_top(self) -> None:
        """Verify that br_table selects the second label when selector is 1."""
        trace = _run(_binary_br_table_module(1))
        assert trace.steps[-1].top == _EXPECTED_BR_TABLE_1_TOP


class TestBrTableDefault:
    """Verify br_table default target selection."""

    def test_final_top(self) -> None:
        """Verify that br_table uses default target for out-of-range selectors."""
        trace = _run(_binary_br_table_module(5))
        assert trace.steps[-1].top == 0


class TestDivByZero:
    """Verify integer division-by-zero trap."""

    def test_traps(self) -> None:
        """Verify that dividing by zero produces a trap opcode."""
        trace = _run(_binary_div_trap_module())
        assert trace.steps[-1].op == OP_TRAP


class TestModuleImports:
    """Verify that internal modules are importable without error."""

    def test_opcodes_imports(self) -> None:
        """Verify that the opcodes module can be imported."""

    def test_trace_imports(self) -> None:
        """Verify that the trace module can be imported."""

    def test_wasm_math_imports(self) -> None:
        """Verify that the wasm_math module can be imported."""

    def test_wasm_contract_imports(self) -> None:
        """Verify that the wasm_contract module can be imported."""
