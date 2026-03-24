"""Tests for the WAT parser.

Verifies:
1. WAT versions of Phase 4 test programs produce identical traces
2. WAT Fibonacci, factorial, bubble sort execute correctly
3. All WAT instruction categories parse and execute
"""

import sys
from wat_parser import parse_wat
from isa import Instruction, OP_PUSH, OP_HALT, compare_traces
from executor import NumPyExecutor
from programs import ALL_TESTS, fib


def run_and_compare(name, wat_text, expected_top, *, tuple_prog=None, verbose=False):
    """Parse WAT, execute, check top-of-stack, and optionally compare traces."""
    exe = NumPyExecutor()
    wat_prog = parse_wat(wat_text)

    trace_wat = exe.execute(wat_prog)
    got_top = trace_wat.steps[-1].top if trace_wat.steps else None

    ok = True
    if got_top != expected_top:
        print(f"  FAIL: {name} — expected top={expected_top}, got {got_top}")
        ok = False

    if tuple_prog is not None:
        trace_tuple = exe.execute(tuple_prog)
        match, msg = compare_traces(trace_tuple, trace_wat)
        if not match:
            print(f"  FAIL: {name} — trace mismatch: {msg}")
            ok = False

    if ok:
        print(f"  PASS: {name}")
    return ok


# ─── Phase 4 Test Programs in WAT ────────────────────────────────

WAT_PHASE4 = {
    "basic_add": """
        i32.const 3
        i32.const 5
        i32.add
        halt
    """,
    "push_halt": """
        i32.const 42
        halt
    """,
    "push_pop": """
        i32.const 10
        i32.const 20
        drop
        halt
    """,
    "dup_add": """
        i32.const 7
        dup
        i32.add
        halt
    """,
    "multi_add": """
        i32.const 1
        i32.const 2
        i32.const 3
        i32.add
        i32.add
        halt
    """,
    "stack_depth": """
        i32.const 1
        i32.const 2
        i32.const 3
        drop
        drop
        halt
    """,
    "overwrite": """
        i32.const 5
        drop
        i32.const 9
        halt
    """,
    "complex": """
        i32.const 10
        i32.const 20
        i32.const 30
        i32.add
        dup
        i32.add
        halt
    """,
    "many_pushes": """
        i32.const 1  i32.const 2  i32.const 3  i32.const 4  i32.const 5
        i32.const 6  i32.const 7  i32.const 8  i32.const 9  i32.const 10
        i32.add i32.add i32.add i32.add i32.add
        i32.add i32.add i32.add i32.add
        halt
    """,
    "alternating": """
        i32.const 1  i32.const 2  i32.add
        i32.const 3  i32.add
        i32.const 4  i32.add
        halt
    """,
}


# ─── Algorithm Programs in WAT ───────────────────────────────────

WAT_FIBONACCI_10 = """
    ;; Compute fib(10) = 55 using iterative algorithm
    ;; Stack layout: [counter, a, b]
    i32.const 0          ;; a = fib(0)
    i32.const 1          ;; b = fib(1)
    i32.const 9          ;; counter = n-1 = 9
    rot                  ;; [1, 9, 0]
    rot                  ;; [9, 0, 1] = [counter, a, b]

    ;; Loop body
    loop $fib_loop
      swap               ;; [counter, b, a]
      over               ;; [counter, b, a, b]
      i32.add            ;; [counter, b, a+b]
      rot                ;; [b, a+b, counter]
      i32.const 1
      i32.sub            ;; [b, a+b, counter-1]
      dup                ;; [..., counter-1, counter-1]
      i32.eqz
      if
        drop             ;; drop counter=0
        swap             ;; put result on top (drop old_a below)
        drop             ;; drop old_a
        halt
      end
      ;; Restore stack to [counter, a, b] for next iteration
      rot                ;; [a+b, counter-1, b]
      rot                ;; [counter-1, b, a+b] = [counter, a, b]
      br 0               ;; continue loop
    end

    ;; Should not reach here
    halt
"""

WAT_FACTORIAL_5 = """
    ;; Compute 5! = 120 using accumulator pattern
    ;; Stack: [accumulator, counter]
    i32.const 1          ;; accumulator = 1
    i32.const 5          ;; counter = 5

    loop $fact_loop
      ;; stack: [acc, counter]
      dup                ;; [acc, counter, counter]
      rot                ;; [counter, counter, acc]
      i32.mul            ;; [counter, acc*counter]
      swap               ;; [acc*counter, counter]
      i32.const 1
      i32.sub            ;; [new_acc, counter-1]
      dup                ;; [new_acc, counter-1, counter-1]
      br_if 0            ;; if counter-1 != 0, continue
    end

    drop                 ;; drop counter=0
    halt                 ;; top = 120
"""

WAT_BUBBLE_SORT = """
    ;; Bubble sort [5, 3, 1, 4, 2] -> result: top = 5 (largest)
    ;; Uses locals as array storage
    ;; local 0-4: array elements
    ;; local 5: swap flag
    ;; local 6: temp for comparison

    (func $sort
      (local i32 i32 i32 i32 i32 i32 i32)
      ;; Initialize array in locals
      i32.const 5  local.set 0
      i32.const 3  local.set 1
      i32.const 1  local.set 2
      i32.const 4  local.set 3
      i32.const 2  local.set 4

      ;; Outer loop (repeat until no swaps)
      loop $outer
        i32.const 0  local.set 5   ;; swap_flag = 0

        ;; Compare and swap pairs [0,1], [1,2], [2,3], [3,4]

        ;; Pair [0, 1]
        local.get 0  local.get 1  i32.gt_s
        if
          local.get 0  local.set 6    ;; temp = arr[0]
          local.get 1  local.set 0    ;; arr[0] = arr[1]
          local.get 6  local.set 1    ;; arr[1] = temp
          i32.const 1  local.set 5    ;; swap_flag = 1
        end

        ;; Pair [1, 2]
        local.get 1  local.get 2  i32.gt_s
        if
          local.get 1  local.set 6
          local.get 2  local.set 1
          local.get 6  local.set 2
          i32.const 1  local.set 5
        end

        ;; Pair [2, 3]
        local.get 2  local.get 3  i32.gt_s
        if
          local.get 2  local.set 6
          local.get 3  local.set 2
          local.get 6  local.set 3
          i32.const 1  local.set 5
        end

        ;; Pair [3, 4]
        local.get 3  local.get 4  i32.gt_s
        if
          local.get 3  local.set 6
          local.get 4  local.set 3
          local.get 6  local.set 4
          i32.const 1  local.set 5
        end

        ;; Check swap_flag
        local.get 5
        br_if 0            ;; if swapped, repeat outer loop
      end

      ;; Push sorted array onto stack (ascending order)
      local.get 0         ;; 1 (smallest)
      local.get 1         ;; 2
      local.get 2         ;; 3
      local.get 3         ;; 4
      local.get 4         ;; 5 (largest, on top)
    )

    halt
"""

WAT_SUM_1_TO_10 = """
    ;; Compute 1+2+...+10 = 55
    i32.const 0          ;; accumulator
    i32.const 10         ;; counter

    loop $sum_loop
      ;; stack: [acc, counter]
      dup                ;; [acc, counter, counter]
      rot                ;; [counter, counter, acc]
      i32.add            ;; [counter, acc+counter]
      swap               ;; [acc+counter, counter]
      i32.const 1
      i32.sub            ;; [new_acc, counter-1]
      dup                ;; [new_acc, counter-1, counter-1]
      br_if 0            ;; if counter-1 != 0, continue
    end

    drop                 ;; drop counter=0
    halt                 ;; top = 55
"""

WAT_POWER_2_7 = """
    ;; Compute 2^7 = 128 via repeated doubling
    i32.const 1          ;; value = 1
    i32.const 7          ;; counter = 7

    loop $pow_loop
      ;; stack: [value, counter]
      dup
      i32.eqz
      if
        ;; counter == 0 -> done
        drop             ;; drop counter
        halt
      end
      i32.const 1
      i32.sub            ;; [value, counter-1]
      swap               ;; [counter-1, value]
      dup
      i32.add            ;; [counter-1, value*2]
      swap               ;; [value*2, counter-1]
      dup                ;; dup counter for check
      br_if 0            ;; if counter-1 != 0, continue
    end

    drop                 ;; drop counter=0
    halt
"""

WAT_IF_ELSE = """
    ;; Test if/else: push 10 if 5 > 3, else 20
    i32.const 5
    i32.const 3
    i32.gt_s
    if
      i32.const 10
    else
      i32.const 20
    end
    halt
"""

WAT_NESTED_BLOCKS = """
    ;; Test nested blocks with br
    i32.const 42
    block $outer
      block $inner
        i32.const 1
        br $outer      ;; skip inner and outer
        i32.const 99   ;; unreachable
      end
      i32.const 88     ;; unreachable
    end
    ;; top should still be 1 (last pushed before br)
    halt
"""

WAT_ARITHMETIC = """
    ;; Test various arithmetic: (10 - 3) * 2 = 14
    i32.const 10
    i32.const 3
    i32.sub
    i32.const 2
    i32.mul
    halt
"""

WAT_COMPARISON_CHAIN = """
    ;; Test comparison chain: (5 == 5) AND (3 < 7) => 1 AND 1 => 1
    i32.const 5
    i32.const 5
    i32.eq          ;; 1
    i32.const 3
    i32.const 7
    i32.lt_s        ;; 1
    i32.and         ;; 1 AND 1 = 1
    halt
"""

WAT_BITWISE = """
    ;; Test bitwise: (0xFF AND 0x0F) OR 0xF0 = 0xFF
    i32.const 0xFF
    i32.const 0x0F
    i32.and          ;; 0x0F
    i32.const 0xF0
    i32.or           ;; 0xFF = 255
    halt
"""


# ─── Main test runner ─────────────────────────────────────────────

def main():
    print("=== WAT Parser Integration Tests ===\n")
    passed = 0
    failed = 0

    def run(name, wat, expected, tuple_prog=None):
        nonlocal passed, failed
        if run_and_compare(name, wat, expected, tuple_prog=tuple_prog):
            passed += 1
        else:
            failed += 1

    # ── Phase 4 trace-level comparison ──
    print("Phase 4 programs (trace comparison with tuple versions):")
    for test_name, test_fn in ALL_TESTS:
        tuple_prog, expected = test_fn()
        wat_text = WAT_PHASE4.get(test_name)
        if wat_text is None:
            print(f"  SKIP: {test_name} (no WAT version)")
            continue
        run(test_name, wat_text, expected, tuple_prog=tuple_prog)

    # ── Algorithm tests ──
    print("\nAlgorithm programs:")
    run("fibonacci(10)", WAT_FIBONACCI_10, 55)
    run("factorial(5)", WAT_FACTORIAL_5, 120)
    run("sum(1..10)", WAT_SUM_1_TO_10, 55)
    run("power(2,7)", WAT_POWER_2_7, 128)
    run("bubble_sort", WAT_BUBBLE_SORT, 5)

    # ── Control flow tests ──
    print("\nControl flow:")
    run("if/else", WAT_IF_ELSE, 10)
    run("nested_blocks", WAT_NESTED_BLOCKS, 1)

    # ── Instruction category tests ──
    print("\nInstruction categories:")
    run("arithmetic", WAT_ARITHMETIC, 14)
    run("comparison_chain", WAT_COMPARISON_CHAIN, 1)
    run("bitwise", WAT_BITWISE, 255)

    # ── Edge cases ──
    print("\nEdge cases:")

    # Empty program
    prog = parse_wat("")
    ok = len(prog) == 0
    if ok:
        print("  PASS: empty input")
        passed += 1
    else:
        print(f"  FAIL: empty input — got {prog}")
        failed += 1

    # Comments only
    prog = parse_wat(";; just a comment\n(; block ;)")
    ok = len(prog) == 0
    if ok:
        print("  PASS: comments only")
        passed += 1
    else:
        print(f"  FAIL: comments only — got {prog}")
        failed += 1

    # Negative integer
    prog = parse_wat("i32.const -5 halt")
    exe = NumPyExecutor()
    trace = exe.execute(prog)
    top = trace.steps[-1].top
    if top == -5:
        print("  PASS: negative integer")
        passed += 1
    else:
        print(f"  FAIL: negative integer — expected -5, got {top}")
        failed += 1

    # Hex literal
    prog = parse_wat("i32.const 0x1A halt")
    trace = exe.execute(prog)
    top = trace.steps[-1].top
    if top == 26:
        print("  PASS: hex literal execution")
        passed += 1
    else:
        print(f"  FAIL: hex literal — expected 26, got {top}")
        failed += 1

    # S-expression form
    prog = parse_wat("""
        (i32.add
          (i32.const 3)
          (i32.const 5))
        halt
    """)
    trace = exe.execute(prog)
    top = trace.steps[-1].top
    if top == 8:
        print("  PASS: s-expression form")
        passed += 1
    else:
        print(f"  FAIL: s-expression form — expected 8, got {top}")
        failed += 1

    # Module + func wrapper
    prog = parse_wat("""
        (module
          (func $main
            i32.const 99
          )
        )
    """)
    if prog[0] == Instruction(OP_PUSH, 99):
        print("  PASS: module+func wrapper")
        passed += 1
    else:
        print(f"  FAIL: module+func wrapper — got {prog}")
        failed += 1

    # Error handling
    try:
        parse_wat("i32.const")
        print("  FAIL: missing arg should raise")
        failed += 1
    except ValueError:
        print("  PASS: missing arg raises ValueError")
        passed += 1

    try:
        parse_wat("invalid_instruction")
        print("  FAIL: unknown instruction should raise")
        failed += 1
    except ValueError:
        print("  PASS: unknown instruction raises ValueError")
        passed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All tests passed!")


if __name__ == '__main__':
    main()
