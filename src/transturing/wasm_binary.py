"""
WASM binary format parser for the i32 subset of WebAssembly.

This module decodes the binary encoding of WASM modules (.wasm files) into
structured Python dataclasses. Only a restricted subset of WASM is supported:
i32 value types, no imports/tables/globals/start/element/data sections, and no
floating-point or i64/SIMD instructions.

The main entry points are:

- ``parse_wasm_binary`` -- parse raw bytes into a ``WasmBinaryModule``.
- ``parse_wasm_file`` -- convenience wrapper that reads a file first.
- ``auto_detect_function`` -- heuristically pick the user-defined entry-point
  function from a decoded module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .trace import WasmInstr

_WASM_MAGIC = b"\x00asm"
_WASM_VERSION = 1

_SECTION_TYPE = 1
_SECTION_IMPORT = 2
_SECTION_FUNCTION = 3
_SECTION_TABLE = 4
_SECTION_MEMORY = 5
_SECTION_GLOBAL = 6
_SECTION_EXPORT = 7
_SECTION_START = 8
_SECTION_ELEMENT = 9
_SECTION_CODE = 10
_SECTION_DATA = 11
_SECTION_DATA_COUNT = 12

_VALTYPE_I32 = 0x7F
_FUNC_TYPE = 0x60
_EMPTY_BLOCK_TYPE = 0x40

_VALTYPE_NAMES: dict[int, str] = {
    0x7F: "i32",
    0x7E: "i64",
    0x7D: "f32",
    0x7C: "f64",
    0x7B: "v128",
    0x70: "funcref",
    0x6F: "externref",
}

_EXPORT_KIND_FUNC = 0x00
_EXPORT_KIND_TABLE = 0x01
_EXPORT_KIND_MEMORY = 0x02
_EXPORT_KIND_GLOBAL = 0x03

_KIND_NAMES = {
    _EXPORT_KIND_FUNC: "func",
    _EXPORT_KIND_TABLE: "table",
    _EXPORT_KIND_MEMORY: "memory",
    _EXPORT_KIND_GLOBAL: "global",
}

_CONTROL_OPS: dict[int, str] = {
    0x1A: "POP",
    0x1B: "SELECT",
    0x01: "NOP",
    0x0F: "RETURN",
}

_ARG_OPS: dict[int, str] = {
    0x20: "LOCAL.GET",
    0x21: "LOCAL.SET",
    0x22: "LOCAL.TEE",
    0x10: "CALL",
    0x0C: "BR",
    0x0D: "BR_IF",
}

_MEMORY_OPS: dict[int, str] = {
    0x28: "I32.LOAD",
    0x2C: "I32.LOAD8_S",
    0x2D: "I32.LOAD8_U",
    0x2E: "I32.LOAD16_S",
    0x2F: "I32.LOAD16_U",
    0x36: "I32.STORE",
    0x3A: "I32.STORE8",
    0x3B: "I32.STORE16",
}

# LEB128 encoding limits
_U32_MAX = 0xFFFFFFFF
_I32_BIT_WIDTH = 32

# Opcode constants for _opcode_family_name
_OP_I64_CONST = 0x42
_OP_I64_LOAD = 0x50
_OP_I64_LOAD_END = 0x5A
_OP_I64_LANE_LOAD_START = 0x79
_OP_I64_LANE_LOAD_END = 0x8A
_OP_F32_CONST = 0x43
_OP_F64_CONST = 0x44
_OP_F32_LOAD = 0x5B
_OP_F64_OP_END = 0x66
_OP_SIMD_START = 0x8B
_OP_SIMD_END = 0xBF
_OP_CALL_INDIRECT = 0x11
_OP_GLOBAL_GET = 0x23
_OP_GLOBAL_SET = 0x24

# Opcode constants for _decode_expr
_OP_END = 0x0B
_OP_ELSE = 0x05
_OP_I32_CONST = 0x41
_OP_BR_TABLE = 0x0E

_SIMPLE_BINARY_OPS: dict[int, str] = {
    0x45: "i32.eqz",
    0x46: "i32.eq",
    0x47: "i32.ne",
    0x48: "i32.lt_s",
    0x49: "i32.lt_u",
    0x4A: "i32.gt_s",
    0x4B: "i32.gt_u",
    0x4C: "i32.le_s",
    0x4D: "i32.le_u",
    0x4E: "i32.ge_s",
    0x4F: "i32.ge_u",
    0x67: "i32.clz",
    0x68: "i32.ctz",
    0x69: "i32.popcnt",
    0x6A: "i32.add",
    0x6B: "i32.sub",
    0x6C: "i32.mul",
    0x6D: "i32.div_s",
    0x6E: "i32.div_u",
    0x6F: "i32.rem_s",
    0x70: "i32.rem_u",
    0x71: "i32.and",
    0x72: "i32.or",
    0x73: "i32.xor",
    0x74: "i32.shl",
    0x75: "i32.shr_s",
    0x76: "i32.shr_u",
    0x77: "i32.rotl",
    0x78: "i32.rotr",
}

_SUPPORTED_DECODED_INSTRS = frozenset(
    {
        "PUSH",
        "POP",
        "SELECT",
        "NOP",
        "RETURN",
        "LOCAL.GET",
        "LOCAL.SET",
        "LOCAL.TEE",
        "CALL",
        "BR",
        "BR_IF",
        "BR_TABLE",
        "I32.LOAD",
        "I32.LOAD8_S",
        "I32.LOAD8_U",
        "I32.LOAD16_S",
        "I32.LOAD16_U",
        "I32.STORE",
        "I32.STORE8",
        "I32.STORE16",
        "BLOCK",
        "LOOP",
        "IF",
        "ELSE",
        "END",
        "ADD",
        "SUB",
        "MUL",
        "DIV_S",
        "DIV_U",
        "REM_S",
        "REM_U",
        "EQZ",
        "EQ",
        "NE",
        "LT_S",
        "LT_U",
        "GT_S",
        "GT_U",
        "LE_S",
        "LE_U",
        "GE_S",
        "GE_U",
        "AND",
        "OR",
        "XOR",
        "SHL",
        "SHR_S",
        "SHR_U",
        "ROTL",
        "ROTR",
        "CLZ",
        "CTZ",
        "POPCNT",
    }
)

_WAT_TO_WASM_INSTR: dict[str, str] = {
    "i32.add": "ADD",
    "i32.sub": "SUB",
    "i32.mul": "MUL",
    "i32.div_s": "DIV_S",
    "i32.div_u": "DIV_U",
    "i32.rem_s": "REM_S",
    "i32.rem_u": "REM_U",
    "i32.eqz": "EQZ",
    "i32.eq": "EQ",
    "i32.ne": "NE",
    "i32.lt_s": "LT_S",
    "i32.lt_u": "LT_U",
    "i32.gt_s": "GT_S",
    "i32.gt_u": "GT_U",
    "i32.le_s": "LE_S",
    "i32.le_u": "LE_U",
    "i32.ge_s": "GE_S",
    "i32.ge_u": "GE_U",
    "i32.and": "AND",
    "i32.or": "OR",
    "i32.xor": "XOR",
    "i32.shl": "SHL",
    "i32.shr_s": "SHR_S",
    "i32.shr_u": "SHR_U",
    "i32.rotl": "ROTL",
    "i32.rotr": "ROTR",
    "i32.clz": "CLZ",
    "i32.ctz": "CTZ",
    "i32.popcnt": "POPCNT",
}

_NO_ARG_OPS: dict[int, str] = {
    **_CONTROL_OPS,
    **{k: _WAT_TO_WASM_INSTR[v] for k, v in _SIMPLE_BINARY_OPS.items()},
}

_UNSUPPORTED_SECTIONS: dict[int, str] = {
    _SECTION_IMPORT: "import",
    _SECTION_TABLE: "table",
    _SECTION_GLOBAL: "global",
    _SECTION_START: "start",
    _SECTION_ELEMENT: "element",
    _SECTION_DATA: "data",
    _SECTION_DATA_COUNT: "data_count",
}

_STRUCTURED_CF_NAMES = frozenset(
    {"BLOCK", "LOOP", "IF", "ELSE", "END", "BR", "BR_IF", "BR_TABLE"}
)

_BOILERPLATE_EXPORTS = frozenset(
    {
        "__wasm_call_ctors",
        "memory",
        "__dso_handle",
        "__data_end",
        "__stack_low",
        "__stack_high",
        "__global_base",
        "__heap_base",
        "__heap_end",
        "__memory_base",
        "__table_base",
    }
)

_BR_ARGS_LEN = 2
_BR_TABLE_ARGS_LEN = 3


class WasmBinaryDecodeError(ValueError):
    """
    Raised when the WASM binary cannot be decoded.

    This covers invalid format, unsupported sections, unsupported opcodes,
    truncated data, and any other structural or semantic errors encountered
    while parsing a ``.wasm`` file.
    """


@dataclass(frozen=True)
class WasmFunctionType:
    """
    Represents a WASM function type signature (params and results lists).

    Attributes:
        params: List of value type names for the function parameters.
        results: List of value type names for the function return values.

    """

    params: list[str]
    results: list[str]


@dataclass(frozen=True)
class WasmMemory:
    """
    Represents a WASM memory limits declaration.

    Attributes:
        min_pages: Minimum number of 64 KiB pages.
        max_pages: Maximum number of pages, or ``None`` for unbounded memory.

    """

    min_pages: int
    max_pages: int | None = None


@dataclass(frozen=True)
class WasmExport:
    """
    Represents a single WASM export entry.

    Attributes:
        name: The export name exposed to the host environment.
        kind: Export kind (``"func"`` or ``"memory"``).
        index: Zero-based index into the corresponding section's vector.

    """

    name: str
    kind: str
    index: int


@dataclass(frozen=True)
class WasmFunction:
    """
    Represents a decoded WASM function with its type, locals, body, and export names.

    Attributes:
        index: Zero-based function index within the module.
        type_index: Index into the module's type section for this function's
            signature.
        params: Value type names for each parameter.
        results: Value type names for each return value.
        locals: Value type names for each local variable (after parameters).
        body: Decoded instruction tuples forming the function body.
        export_names: Names under which this function is exported (may be
            empty).

    """

    index: int
    type_index: int
    params: list[str]
    results: list[str]
    locals: list[str]
    body: list[WasmInstr]
    export_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WasmBinaryModule:
    """
    Top-level decoded WASM module containing types, functions, memories, and exports.

    Attributes:
        types: Function type signatures declared in the type section.
        functions: Fully decoded functions with bodies.
        memories: Memory limit declarations.
        exports: Export entries mapping names to indices.

    """

    types: list[WasmFunctionType]
    functions: list[WasmFunction]
    memories: list[WasmMemory]
    exports: list[WasmExport]

    def get_exported_function(self, name: str) -> WasmFunction:
        """
        Look up a function by its export name.

        Args:
            name: The exported name to search for.

        Returns:
            The ``WasmFunction`` referenced by the export.

        Raises:
            KeyError: If no exported function with the given name exists.

        """
        for export in self.exports:
            if export.kind == "func" and export.name == name:
                return self.functions[export.index]
        msg = f"No exported function named {name!r}"
        raise KeyError(msg)


class _Reader:
    """
    Binary reader with LEB128 decoding and contextual error messages.

    Wraps a ``bytes`` buffer and provides sequential read primitives used by
    the section and instruction decoders. Every error raised includes the
    current byte offset and an optional *context* label for easier debugging.
    """

    def __init__(self, data: bytes, *, context: str = "module") -> None:
        self.data = data
        self.pos = 0
        self.context = context

    def _fail(self, message: str) -> WasmBinaryDecodeError:
        return WasmBinaryDecodeError(
            f"{self.context} decode error at byte {self.pos}: {message}",
        )

    def fail(self, message: str) -> WasmBinaryDecodeError:
        return self._fail(message)

    def remaining(self) -> int:
        """Return the number of unread bytes remaining in the buffer."""
        return len(self.data) - self.pos

    def read_byte(self) -> int:
        """Read and return a single byte, advancing the position by one."""
        if self.pos >= len(self.data):
            msg = "unexpected end of input"
            raise self._fail(msg)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def read_exact(self, size: int) -> bytes:
        """
        Read exactly *size* bytes from the buffer.

        Args:
            size: Number of bytes to read. Must be non-negative.

        Returns:
            A ``bytes`` object of exactly *size* bytes.

        Raises:
            WasmBinaryDecodeError: If fewer than *size* bytes remain.

        """
        if size < 0:
            msg = f"negative read size {size}"
            raise self._fail(msg)
        end = self.pos + size
        if end > len(self.data):
            msg = f"expected {size} bytes, found only {self.remaining()}"
            raise self._fail(msg)
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def read_u32(self) -> int:
        """Decode and return an unsigned LEB128-encoded ``u32`` value."""
        result = 0
        shift = 0
        for _ in range(5):
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift
            if byte & 0x80 == 0:
                if result > _U32_MAX:
                    msg = f"uleb128 value {result} exceeds u32"
                    raise self._fail(msg)
                return result
            shift += 7
        msg = "invalid u32 leb128: too many bytes"
        raise self._fail(msg)

    def read_i32(self) -> int:
        """Decode and return a signed LEB128-encoded ``i32`` value."""
        result = 0
        shift = 0
        byte = 0
        for _ in range(5):
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift
            shift += 7
            if byte & 0x80 == 0:
                break
        else:
            msg = "invalid i32 leb128: too many bytes"
            raise self._fail(msg)

        if shift < _I32_BIT_WIDTH and (byte & 0x40):
            result |= -1 << shift
        if result < -(1 << 31) or result > (1 << 31) - 1:
            msg = f"sleb128 value {result} exceeds i32"
            raise self._fail(msg)
        return result

    def read_name(self) -> str:
        """
        Read a WASM name: a length-prefixed UTF-8 string.

        Returns:
            The decoded name string.

        Raises:
            WasmBinaryDecodeError: If the bytes are not valid UTF-8.

        """
        size = self.read_u32()
        raw = self.read_exact(size)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = "invalid UTF-8 name"
            raise self._fail(msg) from exc

    def skip_remaining(self) -> None:
        """Advance the position to the end of the buffer, discarding unread bytes."""
        self.pos = len(self.data)


def _expect_fully_consumed(reader: _Reader, *, where: str) -> None:
    if reader.remaining() != 0:
        msg = f"{where} has {reader.remaining()} trailing bytes after decode"
        raise WasmBinaryDecodeError(
            msg,
        )


def _read_vec[ItemT](
    reader: _Reader, item_reader: Callable[[_Reader], ItemT]
) -> list[ItemT]:
    count = reader.read_u32()
    return [item_reader(reader) for _ in range(count)]


def _read_valtype(reader: _Reader, *, what: str) -> str:
    value = reader.read_byte()
    if value != _VALTYPE_I32:
        type_name = _VALTYPE_NAMES.get(value, f"unknown(0x{value:02x})")
        msg = (
            f"unsupported {what} value type {type_name} (0x{value:02x}); "
            "only i32 is supported"
        )
        raise reader.fail(msg)
    return "i32"


def _read_func_type(reader: _Reader) -> WasmFunctionType:
    form = reader.read_byte()
    if form != _FUNC_TYPE:
        msg = f"unsupported type form 0x{form:02x}; expected func type 0x60"
        raise reader.fail(msg)
    params = _read_vec(
        reader, lambda typed_reader: _read_valtype(typed_reader, what="parameter")
    )
    results = _read_vec(
        reader, lambda typed_reader: _read_valtype(typed_reader, what="result")
    )
    if len(results) > 1:
        msg = "multi-value function results are not supported"
        raise reader.fail(msg)
    return WasmFunctionType(params=params, results=results)


def _read_limits(reader: _Reader) -> WasmMemory:
    flags = reader.read_byte()
    if flags == 0x00:
        return WasmMemory(min_pages=reader.read_u32())
    if flags == 0x01:
        minimum = reader.read_u32()
        maximum = reader.read_u32()
        return WasmMemory(min_pages=minimum, max_pages=maximum)
    msg = f"unsupported memory limits flag 0x{flags:02x}"
    raise reader.fail(msg)


def _read_export(reader: _Reader) -> WasmExport:
    name = reader.read_name()
    kind_byte = reader.read_byte()
    kind = _KIND_NAMES.get(kind_byte)
    if kind is None:
        msg = f"unsupported export kind 0x{kind_byte:02x}"
        raise reader.fail(msg)
    index = reader.read_u32()
    if kind not in {"func", "memory"}:
        msg = (
            f"unsupported export kind {kind!r}; only func and memory exports "
            "are supported"
        )
        raise reader.fail(msg)
    return WasmExport(name=name, kind=kind, index=index)


def _read_block_type(reader: _Reader, opname: str) -> None:
    block_type = reader.read_byte()
    if block_type != _EMPTY_BLOCK_TYPE:
        msg = (
            f"unsupported {opname} block type 0x{block_type:02x}; only empty "
            "block type is supported"
        )
        raise reader.fail(
            msg,
        )


def _read_memarg(reader: _Reader, opname: str) -> None:
    align = reader.read_u32()
    offset = reader.read_u32()
    if offset != 0:
        msg = (
            f"unsupported {opname} memarg offset {offset}; WasmInstr cannot "
            "represent non-zero offsets"
        )
        raise reader.fail(
            msg,
        )
    _ = align


def _opcode_family_name(opcode: int) -> str | None:
    if (
        opcode == _OP_I64_CONST
        or _OP_I64_LOAD <= opcode <= _OP_I64_LOAD_END
        or _OP_I64_LANE_LOAD_START <= opcode <= _OP_I64_LANE_LOAD_END
    ):
        return "i64 instruction family"
    if (
        opcode in {_OP_F32_CONST, _OP_F64_CONST}
        or _OP_F32_LOAD <= opcode <= _OP_F64_OP_END
        or _OP_SIMD_START <= opcode <= _OP_SIMD_END
    ):
        return "floating-point instruction family"
    if opcode == _OP_CALL_INDIRECT:
        return "indirect call instruction family"
    if opcode in {_OP_GLOBAL_GET, _OP_GLOBAL_SET}:
        return "global instruction family"
    return None


def _raise_unsupported_opcode(reader: _Reader, opcode: int) -> None:
    family = _opcode_family_name(opcode)
    if family is not None:
        msg = (
            f"unsupported {family} opcode 0x{opcode:02x}; only the i32 subset "
            "is supported"
        )
        raise reader.fail(
            msg,
        )
    msg_0 = f"unsupported opcode 0x{opcode:02x}"
    raise reader.fail(msg_0)


def _decode_structured_instr(reader: _Reader, opcode: int) -> list[WasmInstr]:
    """
    Decode BLOCK/LOOP/IF constructs and their nested bodies.

    Reads the block type byte, recursively decodes the nested instruction
    sequence, and handles the optional ELSE branch for IF blocks.

    Args:
        reader: Binary reader positioned after the structured-control-flow
            opcode.
        opcode: The opcode that triggered this call (``0x02`` BLOCK,
            ``0x03`` LOOP, or ``0x04`` IF).

    Returns:
        A flat list of instruction tuples including the opening op, nested
        body, optional ELSE clause, and closing END.

    """
    opname = {0x02: "BLOCK", 0x03: "LOOP", 0x04: "IF"}[opcode]
    _read_block_type(reader, opname)
    instrs: list[WasmInstr] = [(opname,)]
    nested_instrs, terminator = _decode_expr(reader, nested=True)
    instrs.extend(nested_instrs)
    if terminator == "else":
        if opname != "IF":
            msg = f"unexpected else inside {opname.lower()} construct"
            raise reader.fail(msg)
        instrs.append(("ELSE",))
        else_instrs, else_terminator = _decode_expr(reader, nested=True)
        instrs.extend(else_instrs)
        if else_terminator != "end":
            msg = "if-else construct did not terminate with end"
            raise reader.fail(msg)
    instrs.append(("END",))
    return instrs


def _check_else_allowed(reader: _Reader, *, nested: bool) -> None:
    if not nested:
        msg = "unexpected else at function body level"
        raise reader.fail(msg)


def _decode_expr(reader: _Reader, *, nested: bool) -> tuple[list[WasmInstr], str]:
    """
    Decode a sequence of WASM instructions from binary, handling nested blocks.

    Reads opcodes one by one until an ``END`` or ``ELSE`` sentinel is
    encountered. Structured control-flow instructions (BLOCK, LOOP, IF) are
    decoded recursively via ``_decode_structured_instr``.

    Args:
        reader: Binary reader positioned at the first opcode of the
            expression.
        nested: ``True`` when decoding inside a BLOCK/LOOP/IF body (where
            ELSE is a valid terminator); ``False`` for the top-level
            function body.

    Returns:
        A tuple ``(instructions, terminator)`` where *instructions* is the
        list of decoded instruction tuples and *terminator* is either
        ``"end"`` or ``"else"`` indicating what stopped the decode loop.

    Raises:
        WasmBinaryDecodeError: On unsupported or malformed opcodes.

    """
    instrs: list[WasmInstr] = []
    while True:
        opcode = reader.read_byte()
        if opcode == _OP_END:
            return instrs, "end"
        if opcode == _OP_ELSE:
            _check_else_allowed(reader, nested=nested)
            return instrs, "else"
        if opcode == _OP_I32_CONST:
            instrs.append(("PUSH", reader.read_i32()))
            continue
        if opcode in _NO_ARG_OPS:
            instrs.append((_NO_ARG_OPS[opcode],))
            continue
        if opcode in _ARG_OPS:
            instrs.append((_ARG_OPS[opcode], reader.read_u32()))
            continue
        if opcode == _OP_BR_TABLE:
            labels = _read_vec(reader, lambda typed_reader: typed_reader.read_u32())
            default = reader.read_u32()
            instrs.append(("BR_TABLE", labels, default))
            continue
        if opcode in _MEMORY_OPS:
            opname = _MEMORY_OPS[opcode]
            _read_memarg(reader, opname)
            instrs.append((opname,))
            continue
        if opcode in {0x02, 0x03, 0x04}:
            instrs.extend(_decode_structured_instr(reader, opcode))
            continue
        _raise_unsupported_opcode(reader, opcode)


def _read_code_entry(
    reader: _Reader, func_index: int
) -> tuple[list[str], list[WasmInstr]]:
    body_size = reader.read_u32()
    body_reader = _Reader(
        reader.read_exact(body_size),
        context=f"function {func_index} body",
    )
    local_groups = body_reader.read_u32()
    locals_flat: list[str] = []
    for _ in range(local_groups):
        count = body_reader.read_u32()
        local_type = _read_valtype(body_reader, what="local")
        locals_flat.extend([local_type] * count)
    body, terminator = _decode_expr(body_reader, nested=False)
    if terminator != "end":
        msg = "function body did not terminate with end"
        raise body_reader.fail(msg)
    _expect_fully_consumed(body_reader, where=f"function {func_index} body")
    return locals_flat, body


def _read_custom_section(section_reader: _Reader) -> None:
    _ = section_reader.read_name()
    section_reader.skip_remaining()


def _read_code_section(
    section_reader: _Reader,
) -> list[tuple[list[str], list[WasmInstr]]]:
    code_count = section_reader.read_u32()
    return [
        _read_code_entry(section_reader, func_index) for func_index in range(code_count)
    ]


def _raise_unsupported_section(section_reader: _Reader, section_name: str) -> None:
    msg = f"{section_name} section is not supported"
    raise section_reader.fail(msg)


def _process_section(
    section_id: int,
    section_reader: _Reader,
) -> tuple[
    list[WasmFunctionType],
    list[int],
    list[WasmMemory],
    list[WasmExport],
    list[tuple[list[str], list[WasmInstr]]],
]:
    """Dispatch a single section and return collected data."""
    types: list[WasmFunctionType] = []
    function_type_indices: list[int] = []
    memories: list[WasmMemory] = []
    exports: list[WasmExport] = []
    code_entries: list[tuple[list[str], list[WasmInstr]]] = []

    if section_id == 0:
        _read_custom_section(section_reader)
    elif section_id == _SECTION_TYPE:
        types = _read_vec(section_reader, _read_func_type)
    elif section_id == _SECTION_FUNCTION:
        function_type_indices = _read_vec(
            section_reader,
            lambda typed_reader: typed_reader.read_u32(),
        )
    elif section_id == _SECTION_MEMORY:
        memories = _read_vec(section_reader, _read_limits)
        if len(memories) > 1:
            msg = "multiple memories are not supported"
            raise section_reader.fail(msg)
    elif section_id == _SECTION_EXPORT:
        exports = _read_vec(section_reader, _read_export)
    elif section_id == _SECTION_CODE:
        code_entries = _read_code_section(section_reader)
    elif section_id in _UNSUPPORTED_SECTIONS:
        _raise_unsupported_section(
            section_reader,
            _UNSUPPORTED_SECTIONS[section_id],
        )
    else:
        msg = f"unknown section id {section_id}"
        raise section_reader.fail(msg)

    return types, function_type_indices, memories, exports, code_entries


def _build_functions(
    types: list[WasmFunctionType],
    function_type_indices: list[int],
    code_entries: list[tuple[list[str], list[WasmInstr]]],
    exports: list[WasmExport],
) -> list[WasmFunction]:
    """Build WasmFunction objects from collected section data."""
    function_export_names: dict[int, list[str]] = {}
    for export in exports:
        if export.kind == "func":
            function_export_names.setdefault(export.index, []).append(export.name)

    functions: list[WasmFunction] = []
    for func_index, (type_index, code_entry) in enumerate(
        zip(function_type_indices, code_entries, strict=True),
    ):
        if type_index >= len(types):
            msg = f"function {func_index} references missing type index {type_index}"
            raise WasmBinaryDecodeError(msg)
        locals_flat, body = code_entry
        signature = types[type_index]
        functions.append(
            WasmFunction(
                index=func_index,
                type_index=type_index,
                params=list(signature.params),
                results=list(signature.results),
                locals=locals_flat,
                body=body,
                export_names=function_export_names.get(func_index, []),
            ),
        )
    return functions


def _validate_exports(
    exports: list[WasmExport],
    functions: list[WasmFunction],
    memories: list[WasmMemory],
) -> None:
    """Validate that all exports reference valid indices."""
    for export in exports:
        if export.kind == "func" and export.index >= len(functions):
            msg = (
                f"export {export.name!r} references missing function index "
                f"{export.index}"
            )
            raise WasmBinaryDecodeError(msg)
        if export.kind == "memory" and export.index >= len(memories):
            msg = (
                f"export {export.name!r} references missing memory index {export.index}"
            )
            raise WasmBinaryDecodeError(msg)


def parse_wasm_binary(data: bytes | bytearray | memoryview) -> WasmBinaryModule:
    """
    Parse a WASM binary module from raw bytes.

    Validates the magic header and version, then iterates over all sections
    to decode types, function signatures, memories, exports, and code bodies.

    Args:
        data: The raw WASM binary content (``bytes``, ``bytearray``, or
            ``memoryview``).

    Returns:
        A fully populated ``WasmBinaryModule``.

    Raises:
        WasmBinaryDecodeError: If the binary is malformed, uses unsupported
            features, or fails structural validation.

    """
    raw = bytes(data)
    reader = _Reader(raw)
    if reader.read_exact(4) != _WASM_MAGIC:
        msg = "invalid WASM magic header"
        raise reader.fail(msg)

    version = int.from_bytes(reader.read_exact(4), byteorder="little", signed=False)
    if version != _WASM_VERSION:
        msg = f"unsupported WASM version {version}; expected 1"
        raise reader.fail(msg)

    types: list[WasmFunctionType] = []
    function_type_indices: list[int] = []
    memories: list[WasmMemory] = []
    exports: list[WasmExport] = []
    code_entries: list[tuple[list[str], list[WasmInstr]]] = []

    seen_sections: set[int] = set()
    last_section_id = 0

    while reader.remaining() > 0:
        section_id = reader.read_byte()
        payload_size = reader.read_u32()
        section_reader = _Reader(
            reader.read_exact(payload_size),
            context=f"section {section_id}",
        )

        if section_id != 0:
            if section_id in seen_sections:
                msg = f"duplicate section id {section_id}"
                raise reader.fail(msg)
            if section_id < last_section_id:
                msg = (
                    f"section id {section_id} is out of order after section id "
                    f"{last_section_id}"
                )
                raise reader.fail(msg)
            seen_sections.add(section_id)
            last_section_id = section_id

        sec_types, sec_indices, sec_mems, sec_exports, sec_code = _process_section(
            section_id,
            section_reader,
        )
        types.extend(sec_types)
        function_type_indices.extend(sec_indices)
        memories.extend(sec_mems)
        exports.extend(sec_exports)
        code_entries.extend(sec_code)

        _expect_fully_consumed(section_reader, where=f"section {section_id}")

    if function_type_indices and not types:
        msg = "function section present without a type section"
        raise WasmBinaryDecodeError(msg)
    if len(function_type_indices) != len(code_entries):
        msg = "function and code section function counts do not match"
        raise WasmBinaryDecodeError(msg)

    functions = _build_functions(types, function_type_indices, code_entries, exports)
    _validate_exports(exports, functions, memories)

    return WasmBinaryModule(
        types=types,
        functions=functions,
        memories=memories,
        exports=exports,
    )


def parse_wasm_file(path: str | Path) -> WasmBinaryModule:
    """
    Parse a WASM binary module from a file path.

    Args:
        path: Filesystem path to a ``.wasm`` file.

    Returns:
        A fully populated ``WasmBinaryModule``.

    Raises:
        WasmBinaryDecodeError: If the file content is not a valid WASM module.
        OSError: If the file cannot be read.

    """
    wasm_path = Path(path)
    return parse_wasm_binary(wasm_path.read_bytes())


def auto_detect_function(module: WasmBinaryModule) -> WasmFunction:
    """
    Auto-detect the entry-point function from a module.

    Iterates over exported functions and returns the first one whose export
    name is not in the set of known boilerplate exports (e.g. ``memory``,
    ``__heap_base``, ``__dso_handle``, etc.). If no such export exists,
    falls back to the first function in the module.

    Args:
        module: A decoded ``WasmBinaryModule`` to search.

    Returns:
        The best-guess entry-point ``WasmFunction``.

    Raises:
        WasmBinaryDecodeError: If the module contains no functions at all.

    """
    for export in module.exports:
        if export.kind == "func" and export.name not in _BOILERPLATE_EXPORTS:
            return module.functions[export.index]
    if module.functions:
        return module.functions[0]
    msg = "No user-defined functions found in WASM module"
    raise WasmBinaryDecodeError(msg)


__all__ = [
    "WasmBinaryDecodeError",
    "WasmBinaryModule",
    "WasmExport",
    "WasmFunction",
    "WasmFunctionType",
    "WasmMemory",
    "auto_detect_function",
    "parse_wasm_binary",
    "parse_wasm_file",
]
