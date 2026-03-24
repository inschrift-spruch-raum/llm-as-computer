# src/
*Files: 5*

## Files

### benchmark.py
> Imports: `subprocess, sys, os, time, executor`...
- **instr_to_tokens** (f) `(prog)` :32
- **time_mojo** (f) `(prog, repeat: int)` :36
- **time_numpy** (f) `(prog, repeat: int)` :49
- **count_steps** (f) `(prog)` :61
- **verify_mojo** (f) `(prog, expected)` :70
- **main** (f) `()` :83

### benchmarks.py
> Imports: `sys, os, isa`
- **make_fnv1a** (f) `(data: list)` :25
- **make_bubble_sort** (f) `(arr: list)` :119
- **make_sum_of_primes** (f) `(limit: int)` :258

### llm_vs_native.py
> Imports: `subprocess, sys, os, time, executor`...
- **native_fnv1a** (f) `(data: list)` :37
- **native_bubble_sort_sum** (f) `(arr: list)` :45
- **native_sum_of_primes** (f) `(limit: int)` :55
- **instr_to_tokens** (f) `(prog)` :81
- **median_ns** (f) `(samples: list)` :85
- **time_native** (f) `(fn, repeat: int)` :90
- **time_numpy** (f) `(prog, repeat: int)` :99
- **time_mojo** (f) `(prog, repeat: int)` :109
- **time_torch** (f) `(prog, repeat: int)` :121
- **count_steps** (f) `(prog)` :133
- **main** (f) `()` :139

### run_mojo_tests.py
> Imports: `subprocess, sys, os, time, isa`...
- **instr_to_tokens** (f) `(prog: list)` :51
- **run_mojo** (f) `(prog: list)` :60
- **run_numpy** (f) `(prog: list)` :76
- **compare_program** (f) `(name: str, prog: list, verbose: bool = False,
                    expect_trap: bool = False)` :86
- **run_group** (f) `(label: str, tests: list, verbose: bool = False)` :130
- **build_all_tests** (f) `()` :146
- **build_tier2_tests** (f) `()` :259
- **build_structured_tests** (f) `()` :300
- **benchmark_mojo** (f) `(prog: list, n: int = 200)` :327
- **benchmark_numpy** (f) `(prog: list, n: int = 50)` :347
- **main** (f) `()` :361

## Other Files

- percepta_exec

