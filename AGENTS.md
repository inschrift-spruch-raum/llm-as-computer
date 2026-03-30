# LLM-as-Computer

**Generated:** 2026-03-29
**Commit:** adda013
**Branch:** main

Compiled transformer executor — programs run inside a transformer's own inference loop. Each instruction fetch and memory read is a parabolic attention head. The transformer *is* the computer. 55-opcode WASM-style ISA, Python backends (PyTorch primary, NumPy reference).

## STRUCTURE

```
./
├── src/
│   └── llm_as_computer/    # Python package (pip installable)
│       ├── __init__.py
│       ├── isa.py          # 55 opcodes, TokenVocab, embeddings, CompiledAttentionHead
│       ├── executor.py     # NumPyExecutor, CompiledModel (PyTorch nn.Module), TorchExecutor
│       ├── programs.py     # Test programs + algorithm generators (fib, mul, gcd, etc.)
│       ├── assembler.py    # WASM-style structured control flow → flat ISA compiler
│       ├── wat_parser.py   # WebAssembly text format parser
│       └── c_pipeline.py   # C → WAT → ISA compilation (requires clang + wasm2wat)
├── tests/
│   ├── test_consolidated.py # Executor correctness + dual-backend consistency tests
│   └── test_wat_parser.py   # WAT parser test suite
├── docs/
│   ├── architecture/       # overview.md, memory-model.md, compilation.md
│   ├── isa/                # index.md, opcodes.md
│   ├── guides/             # how-it-works.md, writing-programs.md
│   ├── development/        # findings-summary.md, rd-plan-summary.md
│   └── reference/          # api.md, file-map.md
├── pyproject.toml          # uv project config (src/ layout, hatchling build)
├── uv.lock                 # Reproducible dependency lockfile
└── .python-version         # Python 3.14
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add an opcode | `src/llm_as_computer/isa.py` + `executor.py` | Must update both NumPyExecutor AND CompiledModel |
| Write a test program | `src/llm_as_computer/programs.py` | Follow `make_*` pattern, add to test runner |
| Understand an embedding | `src/llm_as_computer/isa.py` → `embed_*` functions | Line 733+ |
| Debug execution trace | `src/llm_as_computer/isa.py` → `compare_traces()` | Step-by-step diff |
| Add structured control flow | `src/llm_as_computer/assembler.py` | WASM-style block/loop/if/br |
| Parse WAT text | `src/llm_as_computer/wat_parser.py` | Handles full WAT syntax |
| Read documentation | `docs/` | Start with `docs/guides/how-it-works.md` |

## ARCHITECTURE

**Current state (Phase 14+):** d_model=36, head_dim=2, 55 opcodes, ~964 compiled parameters. Float64 mandatory. Hard-max attention (argmax, NEVER softmax).

**Two backends:**
- **PyTorch (primary):** `TorchExecutor` wraps `CompiledModel` (nn.Module). This is the main execution backend.
- **NumPy (reference/demo):** `NumPyExecutor` provides equivalent execution in pure NumPy. Used for verification and as a reference implementation.

**Five memory spaces** addressed by separate attention heads:
- Program memory (opcode + arg fetch)
- Stack memory (SP, SP-1, SP-2 reads)
- Local variables (LOCAL.GET/SET/TEE)
- Heap/linear memory (I32.LOAD/STORE + byte/short variants)
- Call frames (CALL/RETURN with return address + saved SP)

**Parabolic encoding:** `k = (2j, -j²)` encodes position j. Dot-product attention peaks sharply at target. Same encoding for all memory spaces. Float32 limit ~4K indices; float64 extends to 25M+.

**Import chain:** `isa.py` ← `executor.py` ← `programs.py` ← `assembler.py` ← `wat_parser.py` ← `c_pipeline.py`. Relative imports within the `llm_as_computer` package. External consumers use `from llm_as_computer.X import ...`.

## PHASES

| Phase | File | Status | What It Proves |
|-------|------|--------|----------------|
| 1 | phase1_hull_cache.py | Complete | O(log t) lookup via ternary search on parabolic keys |
| 2 | phase2_parabolic.py | Complete | Parabolic encoding as exact memory addressing |
| 2b | phase2b_address_limits.py | Complete | Residual addressing scales to 25M+ range |
| 3 | phase3_cumsum.py | Complete | Cumulative sum tracks IP/SP |
| 4 | phase4_stack_machine.py | Complete | Hand-wired transformer executes PUSH/POP/ADD/DUP/HALT |
| 5 | phase5_training.py | Complete | Training: 56% acc, 0/50 traces — learns structure, not routing |
| 6 | phase6_curriculum.py | Complete | Curriculum: 56%→85% acc, 39/50 traces |
| 7 | phase7_percepta_arch.py | Complete | Percepta arch (d=36,h=18,L=7): same ceiling as Phase 6 |
| 8 | phase8_microop_traces.py | Complete | Retrieval 100% solved; arithmetic is sole bottleneck |
| 9 | phase9_weighted_arithmetic.py | Complete | Weighted loss perfects doubling; DIFF+ADD stays 0% |
| 10 | phase10_digit_decomposition.py | Complete | Digit decomposition (exploratory) |
| 11 | phase11_compile_executor.py | Complete | Compiled execution: 100% correct, compile > train |
| 12 | phase12_percepta_model.py | Complete | Real PyTorch nn.Module with compiled weights |
| 13 | phase13_isa_completeness.py | Complete | SWAP/OVER/ROT + Fibonacci, multiply, parity |
| 14 | phase14_extended_isa.py | Complete | Full 55-opcode ISA: MUL/DIV/REM/AND/OR/XOR/SHL/SHR/CLZ/CTZ/POPCNT/SELECT/NEG/ABS |
| 15 | phase15_local_variables.py | Complete | LOCAL.GET/SET/TEE — named variable scoping |
| 16 | phase16_linear_memory.py | Complete | Heap: I32.LOAD/STORE + byte/short variants |
| 17 | phase17_function_calls.py | Complete | CALL/RETURN — recursive factorial works |
| 18 | phase18_integration_tests.py | Complete | Bubble sort, recursive fib, multi-function programs |
| 19 | phase19_structured_assembler.py | Complete | Block/loop/if/br/br_table structured control flow |
| 20 | phase20_type_masking_tests.py | Complete | i32 overflow masking (WASM semantics) |

**Core conclusion:** Compile, don't train. Phases 5-10 proved gradient descent cannot learn true addition (a+b, a≠b) in multi-task context. Phases 11-20 proved compilation into weights gives 100% correct execution including arithmetic, branching, function calls, and heap memory. Detailed findings documented in `docs/development/findings-summary.md`.

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER use softmax** — Hard-max (argmax) only. Softmax gives uniform weights when keys are identical.
- **NEVER train the compiled model** — All weights set analytically via `_compile_weights()`. Training path (Phases 5-10) was a productive wrong turn.
- **NEVER use float32 for compiled models** — Float64 mandatory for parabolic addressing correctness. Score values scale as `addr²`; float32 limit ~4K indices.
- **NEVER suppress type errors** — No `as any`, `@ts-ignore`, `# type: ignore`.
- **NEVER read large files blind** — Use `docs/reference/api.md` as function index, then targeted line-range reads. `executor.py` (~1360 lines) is the main trap.
- **Do NOT pin exact dependency versions** — Research repo; use `>=` lower bounds.
- **Do NOT use bare module imports** — Always `from llm_as_computer.X import ...`, never `from isa import ...`.

## CONVENTIONS

- **pytest** — Test suite uses pytest with parametrized tests and fixtures. `uv run pytest tests/ -v` to run all.
- **Dual-executor validation** — Consistency tests verify NumPyExecutor AND TorchExecutor produce identical traces via `compare_traces()`.
- **i32 overflow semantics** — All arithmetic applies `result & 0xFFFFFFFF` (WASM standard). `PUSH 0xFFFFFFFF; PUSH 1; ADD` → `0`.
- **TRAP for runtime errors** — Division by zero, stack underflow emit OP_TRAP (opcode 99), not Python exceptions.
- **Self-referencing EPS values** — NumPy executors use `eps=1e-10`; PyTorch uses `EPS=1e-6` from isa.py. These are different by design (different precision contexts).
- **Recency bias in addressing** — `eps * write_count` term ensures later writes at same address win. Architectural feature, not a hack.

## COMMANDS

```bash
# Install dependencies (syncs .venv from uv.lock)
uv sync

# Install with dev tools
uv sync --group dev

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check .

# Verify lockfile integrity
uv sync --locked
```

## NOTES

- **Project configuration:** `package = true` in `[tool.uv]` with src/ layout. Build backend: hatchling. `uv sync` installs the package in editable mode.
- **Lockfile:** `uv.lock` is committed for reproducible dependency resolution. Run `uv sync` to install from lockfile.
- **File reading:** Start with `docs/reference/api.md` for function-level indexing, or `docs/reference/file-map.md` for file-level navigation. For files >500 lines, use index-then-target pattern.
- **C pipeline dependencies:** Requires `clang` with wasm32 target support + `wasm2wat`. Raises `EnvironmentError` if missing.
