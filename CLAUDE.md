# LLM-as-Computer

Research repo exploring whether vanilla transformer primitives can implement a working computer (stack machine). Inspired by Percepta's "Can LLMs Be Computers?" blog post (Mar 2026).

## Muninn Boot

This repository is developed by Oskar Austegard using Claude sessions sharing persistent memory via Muninn. Boot loads profile, operational context, and prior findings into the session.

**Boot is automatic.** The SessionStart hook (`.claude/hooks/session-start.sh`) runs `boot()` at the beginning of every Claude Code on the web session.

Credentials auto-detect from environment or well-known paths (`/mnt/project/turso.env`, `/mnt/project/muninn.env`, `~/.muninn/.env`). If boot fails, the hook logs a warning and continues.

### Decision Traces

After completing meaningful work (new phase, training run, key finding), store a memory:

```python
remember(
    "Phase N result: [what was found]. Key insight: [what it means]. "
    "Constraint: [if any]. Next: [what follows].",
    "analysis",
    tags=["LLM", "architecture", "research", "phase-N"],
    priority=1
)
```

Lead with *why*, not *what* — the diff shows what. Include surprises, rejected approaches, and architectural implications.

## Project Context

### What This Is

A bottom-up validation of whether transformer attention + FF layers can implement program execution. Each phase isolates a primitive, tests it numerically, then composes with prior phases.

### Key Architectural Insight

**Attention is lookup; feed-forward is routing.** Attention is cheap and reliable (pattern matching, memory addressing). FF layers must learn crisp categorical decisions (opcode dispatch) — this is the hard part. Width > depth for learning execution.

### Parabolic Encoding

The workhorse primitive: `k = (2j, -j²)` encodes position j such that dot-product attention peaks sharply at the target position. Same encoding addresses both program memory and stack memory without interference. Phase 2b extended this past float32 limits via residual (bit-split) addressing.

## Phases

| Phase | File | Status | What It Proves |
|-------|------|--------|----------------|
| 1 | phase1_hull_cache.py | Complete | O(log t) lookup via ternary search on parabolic keys |
| 2 | phase2_parabolic.py | Complete | Parabolic encoding as exact memory addressing |
| 2b | phase2b_address_limits.py | Complete | Residual addressing scales to 25M+ range |
| 3 | phase3_cumsum.py | Complete | Cumulative sum tracks instruction pointer / stack pointer |
| 4 | phase4_stack_machine.py | Complete | Hand-wired transformer executes PUSH/POP/ADD/DUP/HALT correctly |
| 5 | phase5_training.py | Complete | Tiny model learns execution grammar (56% acc) but not perfect traces |
| 6 | phase6_curriculum.py | In progress | Curriculum learning: PUSH-only → PUSH+POP → full instruction set |

### Phase 5 Key Finding

Wide model (d=64, heads=4, layers=2, 137K params) reaches 56% token accuracy (vs 0.5% chance) but 0/50 perfect traces. The model learns *structure* but not *precise routing*. This is the attention-vs-FF gap made concrete: good at finding operands, bad at dispatching operations.

### Phase 6 Hypothesis

Curriculum learning may close the gap: train on PUSH-only first (trivial routing), then incrementally add opcodes. Each stage has simpler FF routing to learn before complexity increases.

## Development Notes

### Container Constraints
- Claude.ai containers time out on long training runs (~15 min)
- CCotw sessions are better suited for compute-heavy phases
- Store checkpoint memories every ~5 min during training to survive cutoffs

### Testing
Always run phase scripts and verify output before committing. Each phase file is self-contained with its own test harness.

### Recall Tags
Use `recall("llm-as-computer", n=10)` or `recall("percepta", n=5)` to load prior context. Key tags: `LLM`, `architecture`, `research`, `percepta`, `transformer-executor`, `phase-N`.
