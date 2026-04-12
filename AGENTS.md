# AGENTS.md

## Commands

```bash
uv sync --group dev          # install everything
uv run pytest                 # run all tests (43 tests, <1s)
uv run pytest tests/test_wasm_binary.py -k "test_parse_wasm_binary_decodes_supported_subset"  # single test
uv run ruff check .           # lint
uv run ruff format --check .  # format check
uv run basedpyright           # type check (strict mode)
```

Verification order: `ruff check -> ruff format --check -> basedpyright -> pytest`

## Architecture

Single-package Python library. No CLI, no server, no entrypoints beyond the Python API.

**Data pipeline (strict order):**

```
WASM bytes -> parse_wasm_binary() -> WasmBinaryModule -> validated_module_from_binary() -> ValidatedWasmModule -> TorchExecutor.execute_wasm() -> Trace
```

**Module responsibilities:**

| Module | Role |
|---|---|
| `wasm_binary` | WASM binary parser. LEB128 decoding, section parsing, instruction decoding. Largest module (~1000 lines). |
| `wasm_contract` | Validation layer. Converts raw parsed types into execution-ready contracts (`ValidatedWasmModule`, `WasmFunctionContract`). |
| `executor` | Stack-based interpreter. Two dispatch tables: `_CF_DISPATCH` (control flow, returns new IP) and `_STEP_DISPATCH` (all other ops, mutates stack + records trace). |
| `opcodes` | Opcode integer constants + name mappings. |
| `wasm_math` | WASM-semantic math (truncating div/rem, rotations, CLZ/CTZ, sign extension). |
| `trace` | `Trace` and `TraceStep` data structures. |

**Public API** (`__init__.py`): `TorchExecutor`, `Trace`, `TraceStep`. Everything else is internal.

## Constraints

- **Python 3.14+** required. Uses `type` statement for type aliases (3.12+ syntax).
- **PyTorch >= 2.0** is a required dependency (not optional).
- **i32 only**. The entire codebase only supports 32-bit integers. No i64, f32, f64, SIMD, or multi-value returns.
- **No imports/tables/globals/start/element/data sections**. The binary parser rejects these with `WasmBinaryDecodeError`.
- `basedpyright` runs in **strict** mode. Never use `as any`, `@ts-ignore` equivalents, or suppress type errors.
- Ruff uses `ALL` rules with these ignores: `COM812`, `D203`, `D212`. Docstring convention: **D213** (multi-line summary starts on second line). **No additional ignores may be added** — fix the error instead.

## Testing

- Tests construct WASM binaries programmatically using helper functions (`_uleb`, `_sleb32`, `_vec`, `_section`, `_func_type`, `_code_entry`, `_module`). No `.wasm` fixture files.
- `conftest.py` auto-skips tests if `torch` is not installed (but torch is required, so this is a no-op in normal dev).
- Test files: `test_wasm_binary.py` (parser tests, 25 cases), `test_wasm_execute.py` (execution tests, 18 cases).

## Style

- Google-style docstrings throughout.
- `from __future__ import annotations` is the first import in every source file.
- Internal/private symbols prefixed with `_`. Only `__init__.py` exports are public.
- Non-local control flow in the executor uses private exceptions (`_TrapError`, `_ReturnError`) — not error returns.
- WASM instruction names in code use upper-case without the `i32.` prefix: `"ADD"` not `"i32.add"`, `"I32.LOAD"` not `"i32.load"`.
