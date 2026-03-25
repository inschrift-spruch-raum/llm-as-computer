# dev/
*Files: 3 | Subdirectories: 1*

## Subdirectories

- [phases/](./phases/_MAP.md)

## Files

### FINDINGS.md
- Percepta "Can LLMs Be Computers?" — R&D Findings `h1` :1
- Context `h2` :5
- Phase 1: Convex Hull KV Cache — Does the Geometry Work? `h2` :12
- Phase 2: Parabolic Key Encoding — Numerical Precision `h2` :30
- Phase 2b: Breaking the Float32 Address Limit `h2` :61
- Phase 3: Cumulative Sum via Attention `h2` :97
- Summary: Primitive Viability `h2` :123
- Phase 4: Minimal Stack Machine via Attention `h2` :134
- Updated Summary: All Phases `h2` :203
- Phase 5: Trained Micro-Executor `h2` :215
- Updated Summary: All Phases `h2` :264
- Phase 6: Curriculum Learning `h2` :277
- Phase 7: Percepta Architecture (d=36, h=18, L=7) `h2` :419
- Phase 8: Micro-Op Trace Diagnostics — THE RETRIEVAL/ARITHMETIC SEPARATION `h2` :436
- Phase 9: Weighted Arithmetic Loss `h2` :457
- Inflection Point: Return to Compilation `h2` :481
- Phase 11: Compiled Executor (Numpy) `h2` :489
- Phase 12: Real PyTorch Compiled Transformer `h2` :507
- Phase 13: ISA Completeness `h2` :528
- Final Summary: All Phases `h2` :551
- Key Insights Across All Phases `h2` :569
- Tier 3: Type System and Float Scope (Issue #37) `h2` :579
- Files `h2` :617

### RD-PLAN.md
- R&D Plan: Prototyping 2D Convex Hull Attention for In-Model Execution `h1` :1
- Phase 1: Convex Hull KV Cache — Does the Geometry Work? ✅ `h2` :11
- Phase 2: Parabolic Key Encoding — Does Index Lookup Work? ✅ `h2` :21
- Phase 2b: Extended Addressing ✅ `h2` :29
- Phase 3: Cumulative Sum Attention — Tracking Running State ✅ `h2` :37
- Phase 4: Minimal Stack Machine via Attention ✅ `h2` :45
- Phases 5–9: The Training Detour ✅ `h2` :55
- Phase 11: Compiled Executor (Numpy) ✅ `h2` :101
- Phase 12: Real PyTorch Compiled Transformer ✅ `h2` :111
- Phase 13: ISA Completeness ✅ `h2` :119
- Success Criteria — Final Status `h2` :127
- Overall Conclusion `h2` :140

### benchmark_scaling.py
> Imports: `sys, os, time, tracemalloc, programs`...
- **make_countdown** (f) `(n)` :26
- **count_steps_python** (f) `(prog, max_steps=2_000_000)` :67
- **time_mojo** (f) `(prog, max_steps=2_000_000, repeat=50)` :73
- **time_python** (f) `(prog, max_steps=2_000_000)` :113
- **measure_memory_python** (f) `(prog, max_steps=2_000_000)` :121
- **fmt_time** (f) `(ns)` :132
- **fmt_mem** (f) `(b)` :142
- **main** (f) `()` :150

