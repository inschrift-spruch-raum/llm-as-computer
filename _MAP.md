# lac-repo/
*Files: 12 | Subdirectories: 2*

## Subdirectories

- [dev/](./dev/_MAP.md)
- [src/](./src/_MAP.md)

## Files

### AGENTS.md
- LLM-as-Computer `h1` :1
- Muninn Boot `h2` :5
- Project Context `h2` :33
- Phases `h2` :47
- Development Notes `h2` :173

### README.md
- llm-as-computer `h1` :1
- Blog Posts `h2` :7
- Benchmark Results `h2` :12
- ISA Reference `h2` :16
- Files `h2` :111

### WRITEUP.md
- Writeup `h1` :1

### assembler.py
> Imports: `isa`
- **compile_structured** (f) `(wasm_instrs)` :52

### c_pipeline.py
> Imports: `os, re, shutil, subprocess, tempfile`...
- **compile_c_to_wat** (f) `(
    source: str,
    *,
    opt_level: str = '-O1',
    extra_clang_args: Optional[List[str]] = None,
)` :168
- **compile_c** (f) `(
    source: str,
    *,
    func_name: Optional[str] = None,
    opt_level: str = '-O1',
    extra_clang_args: Optional[List[str]] = None,
    strict: bool = True,
)` :253
- **compile_and_run** (f) `(
    source: str,
    args: List[int],
    *,
    func_name: Optional[str] = None,
    opt_level: str = '-O1',
    max_steps: int = 50000,
)` :395
- **main** (f) `()` :433

### executor.py
> Imports: `torch, isa`
- **NumPyExecutor** (C) :55
  - **execute** (m) `(self, prog, max_steps=50000)` :61
- **CompiledModel** (C) :456
  - **__init__** (m) `(self, d_model=D_MODEL)` :478
  - **_compile_weights** (m) `(self)` :503
  - **forward** (m) `(self, query_emb, prog_embs, stack_embs, local_embs=None, heap_embs=None,
                call_embs=None, locals_base=0)` :720
- **TorchExecutor** (C) :881
  - **__init__** (m) `(self, model=None)` :887
  - **execute** (m) `(self, prog, max_steps=50000)` :891

### isa.py
> Imports: `torch, typing, dataclasses`
- **program** (f) `(*instrs)` :37
- **TokenVocab** (C) :430
  - **__init__** (m) `(self)` :489
  - **encode** (m) `(self, token)` :506
  - **decode** (m) `(self, tid)` :548
  - **compile_embedding** (m) `(self, d_model=None)` :572
  - **compile_unembedding** (m) `(self, embedding=None, d_model=None)` :628
  - **opcode_name** (m) `(self, op_code)` :658
  - **token_name** (m) `(self, tid)` :662
  - **__repr__** (m) `(self)` :675
- **CompiledAttentionHead** (C) :684
  - **__init__** (m) `(self, d_model=D_MODEL, head_dim=2, v_dim=1, use_bias_q=False)` :698
  - **forward** (m) `(self, query_emb, memory_embs)` :705
- **embed_program_token** (f) `(pos, instr)` :733
- **embed_stack_entry** (f) `(addr, value, write_order)` :748
- **embed_local_entry** (f) `(local_idx, value, write_order)` :759
- **embed_heap_entry** (f) `(addr, value, write_order)` :770
- **embed_call_frame** (f) `(depth, ret_addr, saved_sp, locals_base, write_order)` :781
- **embed_state** (f) `(ip, sp)` :794
- **compare_traces** (f) `(trace_a, trace_b)` :806
- **test_algorithm** (f) `(name, prog, expected, np_exec, pt_exec, verbose=False)` :816
- **test_trap_algorithm** (f) `(name, prog, np_exec, pt_exec, verbose=False)` :845

### programs.py
> Imports: `math, isa`
- **test_basic** (f) `()` :30
- **test_push_halt** (f) `()` :35
- **test_push_pop** (f) `()` :40
- **test_dup_add** (f) `()` :45
- **test_multi_add** (f) `()` :50
- **test_stack_depth** (f) `()` :55
- **test_overwrite** (f) `()` :60
- **test_complex** (f) `()` :65
- **test_many_pushes** (f) `()` :71
- **test_alternating** (f) `()` :79
- **fib** (f) `(n)` :103
- **make_fibonacci** (f) `(n)` :112
- **make_power_of_2** (f) `(n)` :149
- **make_sum_1_to_n** (f) `(n)` :176
- **make_multiply** (f) `(a, b)` :202
- **make_is_even** (f) `(n)` :232
- **make_native_multiply** (f) `(a, b)` :261
- **make_native_divmod** (f) `(a, b)` :271
- **make_native_remainder** (f) `(a, b)` :288
- **make_native_is_even** (f) `(n)` :305
- **make_factorial** (f) `(n)` :320
- **make_gcd** (f) `(a, b)` :349
- **make_compare_eqz** (f) `(a)` :375
- **make_compare_binary** (f) `(op, a, b)` :384
- **make_native_max** (f) `(a, b)` :407
- **make_native_abs** (f) `(n)` :427
- **make_native_clamp** (f) `(val, lo, hi)` :445
- **make_bitwise_binary** (f) `(op, a, b)` :471
- **make_popcount_loop** (f) `(n)` :493
- **make_bit_extract** (f) `(n, bit_pos)` :519
- **make_native_clz** (f) `(n)` :535
- **make_native_ctz** (f) `(n)` :543
- **make_native_popcnt** (f) `(n)` :551
- **make_native_abs_unary** (f) `(n)` :559
- **make_native_neg** (f) `(n)` :567
- **make_select** (f) `(a, b, c)` :575
- **make_select_max** (f) `(a, b)` :586
- **make_log2_floor** (f) `(n)` :600
- **make_is_power_of_2** (f) `(n)` :615

### test_consolidated.py
> Imports: `sys, os, time, isa, executor`...
- **test_numpy_equivalence** (f) `()` :48
- **test_torch_equivalence** (f) `()` :253
- **test_new_np_vs_new_pt** (f) `()` :356
- **main** (f) `()` :431

### test_wat_parser.py
> Imports: `sys, wat_parser, isa, executor, programs`
- **run_and_compare** (f) `(name, wat_text, expected_top, *, tuple_prog=None, verbose=False)` :16
- **main** (f) `()` :358

### wat_parser.py
> Imports: `re, typing, isa, assembler`
- **parse_wat** (f) `(text: str, *, append_halt: bool = True)` :508

## Other Files

- requirements.txt

