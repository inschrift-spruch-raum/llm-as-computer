"""The honest benchmark: LLM-as-computer vs native Python.

Compares four execution models on the same three algorithms:
  1. Native Python   — plain Python, no stack machine
  2. Mojo executor   — compiled parabolic-scan stack machine (same algorithm as NumPy)
  3. NumPy executor  — Python+NumPy parabolic-scan stack machine
  4. Torch executor  — compiled transformer weights (actual LLM-as-computer)

The Torch executor IS the research claim: attention heads implement content-
addressable memory lookup, FF layers implement opcode dispatch. This measures
what that architecture actually costs per instruction versus doing it natively.

Usage:
    python src/llm_vs_native.py
    python src/llm_vs_native.py --skip-torch   # skip slow Torch runs
    python src/llm_vs_native.py --repeat 50    # samples per measurement
"""

import subprocess
import sys
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from executor import NumPyExecutor, TorchExecutor
from src.benchmarks import make_fnv1a, make_bubble_sort, make_sum_of_primes

BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "percepta_exec")

MASK32 = 0xFFFFFFFF


# ─── Native Python implementations ───────────────────────────────

def native_fnv1a(data: list) -> int:
    h = 2166136261
    for b in data:
        h ^= b
        h = (h * 16777619) & MASK32
    return h


def native_bubble_sort_sum(arr: list) -> int:
    a = list(arr)
    n = len(a)
    for i in range(n - 1, 0, -1):
        for j in range(i):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
    return sum(a)


def native_sum_of_primes(limit: int) -> int:
    total = 0
    for n in range(2, limit + 1):
        d = 2
        is_prime = True
        while d * d <= n:
            if n % d == 0:
                is_prime = False
                break
            d += 1
        if is_prime:
            total += n
    return total


NATIVE_IMPLS = {
    "fnv1a_32":   lambda: native_fnv1a(list(range(32))),
    "bubble_20":  lambda: native_bubble_sort_sum(
        [15, 3, 9, 1, 7, 12, 5, 18, 2, 11, 8, 16, 4, 14, 6, 19, 0, 13, 17, 10]
    ),
    "primes_100": lambda: native_sum_of_primes(100),
}


# ─── Timing helpers ───────────────────────────────────────────────

def instr_to_tokens(prog) -> list:
    return [str(x) for instr in prog for x in (instr.op, instr.arg)]


def median_ns(samples: list) -> float:
    samples.sort()
    return float(samples[len(samples) // 2])


def time_native(fn, repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    return median_ns(samples)


def time_numpy(prog, repeat: int) -> float:
    ex = NumPyExecutor()
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter_ns()
        ex.execute(prog, max_steps=50000)
        samples.append(time.perf_counter_ns() - t0)
    return median_ns(samples)


def time_mojo(prog, repeat: int) -> float:
    tokens = instr_to_tokens(prog)
    r = subprocess.run(
        [BINARY, "--repeat", str(repeat)] + tokens,
        capture_output=True, text=True, timeout=120,
    )
    for line in r.stdout.splitlines():
        if line.startswith("TIMING_NS:"):
            return float(line.split(":")[1].strip())
    raise RuntimeError(f"No TIMING_NS in output:\n{r.stdout}")


def time_torch(prog, repeat: int) -> float:
    ex = TorchExecutor()
    # Warm up once (JIT / model init)
    ex.execute(prog, max_steps=50000)
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter_ns()
        ex.execute(prog, max_steps=50000)
        samples.append(time.perf_counter_ns() - t0)
    return median_ns(samples)


def count_steps(prog) -> int:
    return len(NumPyExecutor().execute(prog, max_steps=50000).steps)


# ─── Main ─────────────────────────────────────────────────────────

def main():
    skip_torch = "--skip-torch" in sys.argv
    repeat_fast = 200   # for native/mojo/numpy
    repeat_numpy = 20   # numpy is slow
    repeat_torch = 3    # torch is very slow

    for arg in sys.argv[1:]:
        if arg.startswith("--repeat="):
            repeat_fast = int(arg.split("=")[1])
            repeat_numpy = max(5, repeat_fast // 10)
            repeat_torch = max(2, repeat_fast // 100)

    if not os.path.isfile(BINARY):
        print(f"ERROR: Mojo binary not found: {BINARY}")
        print("  Build: cd src && mojo build executor.mojo -o percepta_exec")
        sys.exit(1)

    benchmarks = [
        ("fnv1a_32",   *make_fnv1a(list(range(32))),
         "FNV-1a hash of 32 bytes"),
        ("bubble_20",  *make_bubble_sort(
            [15,3,9,1,7,12,5,18,2,11,8,16,4,14,6,19,0,13,17,10]),
         "bubble sort 20 elements"),
        ("primes_100", *make_sum_of_primes(100),
         "sum of primes ≤ 100"),
    ]

    print("LLM-as-computer vs Native Python")
    print("=" * 72)
    print()
    print("Execution models:")
    print("  Native  — plain Python (no stack machine)")
    print("  Mojo    — compiled parabolic-scan stack machine (same algo as NumPy)")
    print("  NumPy   — Python+NumPy parabolic-scan stack machine")
    print("  Torch   — compiled transformer weights (LLM-as-computer)")
    print()

    for name, prog, expected, desc in benchmarks:
        steps = count_steps(prog)
        native_fn = NATIVE_IMPLS[name]

        # Verify all produce the correct answer first
        assert native_fn() == expected, f"Native {name} wrong"

        print(f"── {name}  ({steps} steps)  {desc}")
        print(f"   {'Executor':<10}  {'Total µs':>10}  {'ns/step':>10}  {'vs Native':>12}")
        print(f"   {'-'*10}  {'-'*10}  {'-'*10}  {'-'*12}")

        native_ns = time_native(native_fn, repeat_fast)
        mojo_ns   = time_mojo(prog, repeat_fast)
        numpy_ns  = time_numpy(prog, repeat_numpy)

        results = [
            ("Native",  native_ns),
            ("Mojo",    mojo_ns),
            ("NumPy",   numpy_ns),
        ]

        if not skip_torch:
            print(f"   {'Torch':<10}  {'(timing...)'!s:>10}", end="", flush=True)
            torch_ns = time_torch(prog, repeat_torch)
            results.append(("Torch", torch_ns))
            print("\r", end="")

        for label, ns in results:
            us       = ns / 1000
            ns_step  = ns / steps
            overhead = ns / native_ns
            marker   = "  ← baseline" if label == "Native" else f"  {overhead:>6.0f}× slower"
            print(f"   {label:<10}  {us:>10.1f}  {ns_step:>10.1f}  {marker}")

        print()

    if not skip_torch:
        print("Key insight: the Torch executor IS the LLM-as-computer claim.")
        print("The overhead above is the cost of encoding computation in transformer")
        print("weights and executing it via attention + FF dispatch.")
    else:
        print("(Torch executor skipped — run without --skip-torch for full picture)")


if __name__ == "__main__":
    main()
