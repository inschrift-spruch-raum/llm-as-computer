"""Tests for WASM binary parsing, including section decoding and error handling."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

_EXPECTED_MAX_PAGES = 2

_wasm_binary = importlib.import_module("transturing.wasm_binary")
WasmBinaryDecodeError = _wasm_binary.WasmBinaryDecodeError
parse_wasm_binary = _wasm_binary.parse_wasm_binary
parse_wasm_file = _wasm_binary.parse_wasm_file


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


def _sample_module() -> bytes:
    type_section = _section(
        1,
        _vec(
            [
                _func_type([], []),
                _func_type([0x7F], []),
            ]
        ),
    )
    function_section = _section(3, _vec([_uleb(0), _uleb(1)]))
    memory_section = _section(5, _vec([_limits(1, 2)]))
    export_section = _section(
        7,
        _vec(
            [
                _export("helper", 0x00, 0),
                _export("main", 0x00, 1),
                _export("memory", 0x02, 0),
            ]
        ),
    )
    helper_body = _code_entry(
        [(2, 0x7F)],
        [
            b"\x41" + _sleb32(9),
            b"\x21" + _uleb(0),
            b"\x20" + _uleb(0),
            b"\x22" + _uleb(1),
            b"\x1a",
            b"\x41" + _sleb32(0),
            b"\x41" + _sleb32(42),
            b"\x36" + _uleb(2) + _uleb(0),
            b"\x41" + _sleb32(0),
            b"\x28" + _uleb(2) + _uleb(0),
            b"\x1a",
            b"\x0f",
        ],
    )
    main_body = _code_entry(
        [],
        [
            b"\x02\x40",
            b"\x03\x40",
            b"\x41" + _sleb32(1),
            b"\x0d" + _uleb(1),
            b"\x41" + _sleb32(0),
            b"\x0e" + _vec([_uleb(1), _uleb(0)]) + _uleb(1),
            b"\x0b",
            b"\x0b",
            b"\x41" + _sleb32(3),
            b"\x41" + _sleb32(5),
            b"\x6a",
            b"\x1a",
            b"\x20" + _uleb(0),
            b"\x04\x40",
            b"\x41" + _sleb32(1),
            b"\x05",
            b"\x41" + _sleb32(2),
            b"\x0b",
            b"\x1a",
            b"\x10" + _uleb(0),
        ],
    )
    code_section = _section(10, _vec([helper_body, main_body]))
    return _module(
        type_section, function_section, memory_section, export_section, code_section
    )


def _binary_loop_sum_module() -> bytes:
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    export_section = _section(7, _vec([_export("main", 0x00, 0)]))
    code_section = _section(
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
    )
    return _module(type_section, function_section, export_section, code_section)


def _binary_memory_width_module() -> bytes:
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    memory_section = _section(5, _vec([_limits(1)]))
    export_section = _section(7, _vec([_export("main", 0x00, 0)]))
    code_section = _section(
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
    )
    return _module(
        type_section, function_section, memory_section, export_section, code_section
    )


def _binary_multi_function_module() -> bytes:
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0), _uleb(0), _uleb(0)]))
    export_section = _section(7, _vec([_export("main", 0x00, 2)]))
    increment_body = _code_entry([], [b"\x41" + _sleb32(7)])
    twice_body = _code_entry([], [b"\x10" + _uleb(0), b"\x10" + _uleb(0)])
    main_body = _code_entry([], [b"\x10" + _uleb(1)])
    code_section = _section(10, _vec([increment_body, twice_body, main_body]))
    return _module(type_section, function_section, export_section, code_section)


def _binary_br_table_runtime_module(selector: int) -> bytes:
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    export_section = _section(7, _vec([_export("main", 0x00, 0)]))
    code_section = _section(
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
    )
    return _module(type_section, function_section, export_section, code_section)


def _binary_param_call_module() -> bytes:
    type_section = _section(
        1,
        _vec(
            [
                _func_type([0x7F], []),
                _func_type([], []),
            ]
        ),
    )
    function_section = _section(3, _vec([_uleb(0), _uleb(0), _uleb(1)]))
    export_section = _section(7, _vec([_export("main", 0x00, 2)]))
    double_body = _code_entry(
        [],
        [
            b"\x20" + _uleb(0),
            b"\x20" + _uleb(0),
            b"\x6a",
        ],
    )
    helper_body = _code_entry(
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
    )
    main_body = _code_entry(
        [],
        [
            b"\x41" + _sleb32(4),
            b"\x10" + _uleb(1),
        ],
    )
    code_section = _section(10, _vec([double_body, helper_body, main_body]))
    return _module(type_section, function_section, export_section, code_section)


def test_parse_wasm_binary_decodes_supported_subset() -> None:
    """Verify that a full sample module decodes types, exports, locals, and bodies."""
    module = parse_wasm_binary(_sample_module())

    assert [memory.min_pages for memory in module.memories] == [1]
    assert module.memories[0].max_pages == _EXPECTED_MAX_PAGES
    assert [export.name for export in module.exports] == ["helper", "main", "memory"]

    helper = module.get_exported_function("helper")
    assert helper.locals == ["i32", "i32"]
    assert helper.body == [
        ("PUSH", 9),
        ("LOCAL.SET", 0),
        ("LOCAL.GET", 0),
        ("LOCAL.TEE", 1),
        ("POP",),
        ("PUSH", 0),
        ("PUSH", 42),
        ("I32.STORE",),
        ("PUSH", 0),
        ("I32.LOAD",),
        ("POP",),
        ("RETURN",),
    ]

    main = module.get_exported_function("main")
    assert main.params == ["i32"]
    assert main.body == [
        ("BLOCK",),
        ("LOOP",),
        ("PUSH", 1),
        ("BR_IF", 1),
        ("PUSH", 0),
        ("BR_TABLE", [1, 0], 1),
        ("END",),
        ("END",),
        ("PUSH", 3),
        ("PUSH", 5),
        ("ADD",),
        ("POP",),
        ("LOCAL.GET", 0),
        ("IF",),
        ("PUSH", 1),
        ("ELSE",),
        ("PUSH", 2),
        ("END",),
        ("POP",),
        ("CALL", 0),
    ]


def test_parse_wasm_binary_decodes_loop_locals_and_branch_structure() -> None:
    """Verify that a loop-sum module decodes local variables and branch instructions."""
    module = parse_wasm_binary(_binary_loop_sum_module())

    main = module.get_exported_function("main")
    assert main.locals == ["i32", "i32"]
    assert main.body == [
        ("PUSH", 0),
        ("LOCAL.SET", 0),
        ("PUSH", 10),
        ("LOCAL.SET", 1),
        ("LOOP",),
        ("LOCAL.GET", 0),
        ("LOCAL.GET", 1),
        ("ADD",),
        ("LOCAL.SET", 0),
        ("LOCAL.GET", 1),
        ("PUSH", 1),
        ("SUB",),
        ("LOCAL.TEE", 1),
        ("BR_IF", 0),
        ("END",),
        ("LOCAL.GET", 0),
    ]


def test_parse_wasm_binary_decodes_memory_width_variants() -> None:
    """Verify that 8-bit and 16-bit load/store width variants decode correctly."""
    module = parse_wasm_binary(_binary_memory_width_module())

    main = module.get_exported_function("main")
    assert main.body == [
        ("PUSH", 0),
        ("PUSH", 255),
        ("I32.STORE8",),
        ("PUSH", 0),
        ("I32.LOAD8_U",),
        ("POP",),
        ("PUSH", 0),
        ("I32.LOAD8_S",),
        ("POP",),
        ("PUSH", 4),
        ("PUSH", -2),
        ("I32.STORE16",),
        ("PUSH", 4),
        ("I32.LOAD16_U",),
        ("POP",),
        ("PUSH", 4),
        ("I32.LOAD16_S",),
    ]


def test_parse_wasm_binary_decodes_multi_function_call_graph() -> None:
    """Verify that a multi-function module with chained calls decodes correctly."""
    module = parse_wasm_binary(_binary_multi_function_module())

    assert [func.export_names for func in module.functions] == [[], [], ["main"]]
    assert [func.params for func in module.functions] == [[], [], []]
    assert [func.results for func in module.functions] == [[], [], []]
    assert module.functions[0].body == [("PUSH", 7)]
    assert module.functions[1].body == [
        ("CALL", 0),
        ("CALL", 0),
    ]
    assert module.functions[2].body == [("CALL", 1)]


def test_parse_wasm_binary_decodes_br_table_runtime_structure() -> None:
    """Verify that br_table instructions decode with label vector and default target."""
    module = parse_wasm_binary(_binary_br_table_runtime_module(1))

    main = module.get_exported_function("main")
    assert main.body == [
        ("BLOCK",),
        ("BLOCK",),
        ("BLOCK",),
        ("PUSH", 1),
        ("BR_TABLE", [0, 1], 2),
        ("PUSH", 11),
        ("BR", 2),
        ("END",),
        ("PUSH", 22),
        ("BR", 1),
        ("END",),
        ("PUSH", 33),
        ("END",),
    ]


def test_parse_wasm_binary_decodes_param_call_graph_with_locals() -> None:
    """Verify that a parameterised call graph with local variables decodes correctly."""
    module = parse_wasm_binary(_binary_param_call_module())

    assert [func.params for func in module.functions] == [["i32"], ["i32"], []]
    assert [func.locals for func in module.functions] == [[], ["i32"], []]
    assert module.functions[0].body == [
        ("LOCAL.GET", 0),
        ("LOCAL.GET", 0),
        ("ADD",),
    ]
    assert module.functions[1].body == [
        ("LOCAL.GET", 0),
        ("CALL", 0),
        ("PUSH", 3),
        ("ADD",),
        ("LOCAL.TEE", 1),
        ("LOCAL.GET", 1),
        ("ADD",),
    ]
    assert module.functions[2].body == [
        ("PUSH", 4),
        ("CALL", 1),
    ]


def test_parse_wasm_file_reads_path_input(tmp_path: Path) -> None:
    """Verify that parse_wasm_file reads and parses a WASM binary from a file path."""
    wasm_path = tmp_path / "sample.wasm"
    wasm_path.write_bytes(_sample_module())

    module = parse_wasm_file(wasm_path)

    assert module.get_exported_function("helper").export_names == ["helper"]


def test_parse_wasm_binary_rejects_nonzero_memarg_offset() -> None:
    """Verify that non-zero memarg offsets are rejected during parsing."""
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    code_section = _section(
        10,
        _vec(
            [
                _code_entry([], [b"\x41" + _sleb32(0), b"\x28" + _uleb(2) + _uleb(4)]),
            ]
        ),
    )

    with pytest.raises(WasmBinaryDecodeError, match="non-zero offsets"):
        parse_wasm_binary(_module(type_section, function_section, code_section))


def test_parse_wasm_binary_rejects_unsupported_block_type() -> None:
    """Verify that non-empty block types are rejected during parsing."""
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    code_section = _section(
        10,
        _vec(
            [
                _code_entry([], [b"\x04\x7f", b"\x41" + _sleb32(1), b"\x0b"]),
            ]
        ),
    )

    with pytest.raises(
        WasmBinaryDecodeError, match="only empty block type is supported"
    ):
        parse_wasm_binary(_module(type_section, function_section, code_section))


def test_parse_wasm_binary_rejects_unsupported_opcode() -> None:
    """Verify that i64 instruction family opcodes are rejected."""
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    code_section = _section(10, _vec([_code_entry([], [b"\x42\x00"])]))

    with pytest.raises(WasmBinaryDecodeError, match="i64 instruction family"):
        parse_wasm_binary(_module(type_section, function_section, code_section))


def test_parse_wasm_binary_rejects_floating_point_instruction_family() -> None:
    """Verify that floating-point instruction family opcodes are rejected."""
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    code_section = _section(10, _vec([_code_entry([], [b"\x43\x00\x00\x00\x00"])]))

    with pytest.raises(
        WasmBinaryDecodeError, match="floating-point instruction family"
    ):
        parse_wasm_binary(_module(type_section, function_section, code_section))


@pytest.mark.parametrize(
    ("section_id", "payload", "match"),
    [
        (2, _vec([]), "import section is not supported"),
        (6, _vec([]), "global section is not supported"),
        (8, b"", "start section is not supported"),
        (11, _vec([]), "data section is not supported"),
    ],
    ids=["import", "global", "start", "data"],
)
def test_parse_wasm_binary_rejects_unsupported_sections(
    section_id: int, payload: bytes, match: str
) -> None:
    """Verify that import, global, start, and data sections are rejected."""
    with pytest.raises(WasmBinaryDecodeError, match=match):
        parse_wasm_binary(_module(_section(section_id, payload)))


@pytest.mark.parametrize(
    ("section_id", "match"),
    [
        (4, "table section is not supported"),
        (9, "element section is not supported"),
        (12, "data_count section is not supported"),
    ],
    ids=["table", "element", "data_count"],
)
def test_parse_wasm_binary_rejects_more_unsupported_sections(
    section_id: int, match: str
) -> None:
    """Verify that table, element, and data_count sections are rejected."""
    with pytest.raises(WasmBinaryDecodeError, match=match):
        parse_wasm_binary(_module(_section(section_id, _vec([]))))


def test_parse_wasm_binary_rejects_non_i32_local_type() -> None:
    """Verify that non-i32 local variable types are rejected."""
    type_section = _section(1, _vec([_func_type([], [])]))
    function_section = _section(3, _vec([_uleb(0)]))
    body = _uleb(1) + _uleb(1) + b"\x7e" + b"\x0b"
    code_section = _section(10, _vec([_uleb(len(body)) + body]))

    with pytest.raises(WasmBinaryDecodeError, match="only i32 is supported"):
        parse_wasm_binary(_module(type_section, function_section, code_section))


def test_parse_wasm_binary_rejects_multi_value_results() -> None:
    """Verify that function types with multiple result values are rejected."""
    type_section = _section(1, _vec([_func_type([], [0x7F, 0x7F])]))

    with pytest.raises(
        WasmBinaryDecodeError, match="multi-value function results are not supported"
    ):
        parse_wasm_binary(_module(type_section))


def test_parse_wasm_binary_rejects_bad_header() -> None:
    """Verify that an invalid WASM magic header is rejected."""
    with pytest.raises(WasmBinaryDecodeError, match="invalid WASM magic header"):
        parse_wasm_binary(b"not wasm")


def test_parse_wasm_binary_rejects_unsupported_version() -> None:
    """Verify that an unsupported WASM version number is rejected."""
    bad_version = b"\x00asm" + (2).to_bytes(4, byteorder="little")

    with pytest.raises(WasmBinaryDecodeError, match="unsupported WASM version 2"):
        parse_wasm_binary(bad_version)


def test_parse_wasm_binary_rejects_duplicate_sections() -> None:
    """Verify that duplicate section IDs are rejected."""
    type_section = _section(1, _vec([_func_type([], [])]))

    with pytest.raises(WasmBinaryDecodeError, match="duplicate section id 1"):
        parse_wasm_binary(_module(type_section, type_section))


def test_parse_wasm_binary_rejects_out_of_order_sections() -> None:
    """Verify that out-of-order section IDs are rejected."""
    type_section = _section(1, _vec([_func_type([], [])]))
    code_section = _section(10, _vec([]))

    with pytest.raises(WasmBinaryDecodeError, match="section id 1 is out of order"):
        parse_wasm_binary(_module(code_section, type_section))


def test_parse_wasm_binary_allows_custom_sections_with_payload() -> None:
    """Verify that custom sections with arbitrary payload are accepted and skipped."""
    custom_payload = _name("producers") + b"extra-custom-bytes"
    custom_section = _section(0, custom_payload)

    module = parse_wasm_binary(_module(custom_section, _section(1, _vec([]))))

    assert module.types == []
    assert module.functions == []
