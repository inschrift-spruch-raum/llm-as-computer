# 程序编写指南

本文面向**当前对外支持的使用方式**：准备一个受支持的 `.wasm` 二进制模块，把它交给 transturing 的运行时后端执行，并读取 trace/result。

> **边界提醒：** 55 操作码 ISA、`Instruction` 列表、结构化 lowering helper、以及 `programs.py` 里的生成器都属于内部实现/研究材料，不是当前顶层产品契约。真正面向用户的故事线只有一条：**supported WASM32 bytes in, runtime trace/result out**。

这里提到的 WebAssembly 支持范围只限于当前已验证的 i32 子集。关于执行器内部如何运行这些程序 (注意力头、抛物线编码等), 请参考 [工作原理](how-it-works.md)。完整的 55 个操作码定义见 [ISA 参考](../isa/index.md)。

## 基本概念

运行时执行时内部会维护以下状态:

- **栈** (stack)
- **局部变量** (locals)
- **堆内存** (heap)
- **调用帧** (call stack)

这些结构会在 trace 中体现出来，但对外你不需要手写它们；你只需要提供受支持的 `.wasm` bytes。

---

## 推荐路径：执行二进制 `.wasm`

如果你的程序已经是一个 WebAssembly 模块，当前支持的使用方式就是直接导入二进制 `.wasm` 并交给后端执行。

```python
from pathlib import Path

from transturing import get_executor
from transturing.core.wasm_binary import compile_wasm_module
```

### 基本用法

```python
wasm_bytes = Path("add.wasm").read_bytes()
executor = get_executor("numpy")
prog = compile_wasm_module(wasm_bytes, func_name="add")

trace = executor.execute(prog)
print(trace.steps[-1].top)
```

### 可选：先检查模块结构

如果你需要先查看导出的函数或内存信息，可以先解析模块，再选择入口函数：

```python
from transturing.core.wasm_binary import parse_wasm_file

module = parse_wasm_file("add.wasm")
print([export.name for export in module.exports])

prog = compile_wasm_module(Path("add.wasm").read_bytes(), func_name="add")
```

这些 helper 都只面向当前已验证的 i32 子集。作为使用者，你只需要把它们理解为“运行时接受受支持 `.wasm` bytes 的入口”；不需要把内部执行表示当成公开 authoring 工作流。

---

## 内部实现/研究补充

下面这些材料保留给研究者和维护者：

- 直接构造 `Instruction` 列表
- 结构化控制流 helper
- `programs.py` 中的 `make_*` 生成器
- `compare_traces()` 驱动的双后端一致性测试模式

它们仍然有助于理解执行器内部如何工作，但**不是当前建议给用户的入口**。

> **不要把下面内容当成第二条公开工作流。** 从这一节开始，示例都会进入内部表示、测试工具和研究型 helper。它们的目的，是帮助你理解仓库如何验证与解释运行时；如果你的目标是使用当前支持的产品边界，请停留在上面的 `.wasm` bytes 路径。

## 内部示例：使用程序生成器

`programs.py` 提供了一系列 `make_*` 函数, 自动生成常见算法的**内部指令序列**。这套入口主要服务于测试、回归和研究讨论:

```python
from transturing.core.programs import make_fibonacci, make_factorial, make_gcd, make_multiply
from transturing.backends.numpy_backend import NumPyExecutor

# Fibonacci: fib(10) = 55
prog, expected = make_fibonacci(10)
trace = NumPyExecutor().execute(prog)
assert trace.steps[-1].top == expected

# 阶乘: 5! = 120
prog, expected = make_factorial(5)

# 最大公约数: gcd(12, 8) = 4
prog, expected = make_gcd(12, 8)

# 乘法 (重复加法): 7 * 8 = 56
prog, expected = make_multiply(7, 8)
```

所有生成器返回 `(prog, expected_value)` 元组, `expected_value` 是预期的栈顶结果。

---

## 内部验证模式

### 用 compare_traces() 验证

`isa.py` 提供了 `compare_traces()` 函数, 对比两次执行的每一步是否完全一致。这是项目中最核心的**内部验证方式**: NumPy 执行器和 PyTorch 执行器必须产生完全相同的 trace。这里展示的是维护者/研究者工作流, 不是当前对外支持的主使用方式。

```python
from transturing.core.isa import compare_traces
from transturing.backends.numpy_backend import NumPyExecutor
from transturing.backends.torch_backend import TorchExecutor

prog, expected = make_fibonacci(10)

np_trace = NumPyExecutor().execute(prog)
pt_trace = TorchExecutor().execute(prog)

# 对比每一步的状态 (IP、栈、局部变量等)
match, detail = compare_traces(np_trace, pt_trace)
assert match, f"Traces differ: {detail}"

# 验证结果
assert np_trace.steps[-1].top == expected
assert pt_trace.steps[-1].top == expected
```

### 查看执行跟踪（内部调试）

`trace.format_trace()` 输出每一步的详细状态:

```python
trace = NumPyExecutor().execute(prog)
print(trace.format_trace())
```

输出包含每条指令执行后的 IP、操作码、栈内容、局部变量等信息。

### 常用测试模式（内部）

项目中的测试遵循固定模式。下面的例子用于说明仓库内部如何验证执行器一致性, 不应理解为公开产品鼓励用户直接手写 `Instruction`:

```python
from transturing.core.isa import Instruction, compare_traces
from transturing.backends.numpy_backend import NumPyExecutor
from transturing.backends.torch_backend import TorchExecutor
from transturing.core.programs import make_factorial

def test_my_program():
    prog = [
        Instruction(OP_PUSH, 42),
        Instruction(OP_HALT),
    ]
    expected = 42

    np_exec = NumPyExecutor()
    pt_exec = TorchExecutor()

    np_trace = np_exec.execute(prog)
    pt_trace = pt_exec.execute(prog)

    # 1. 两个执行器 trace 必须完全一致
    match, detail = compare_traces(np_trace, pt_trace)
    assert match, detail

    # 2. 结果必须符合预期
    assert np_trace.steps[-1].top == expected
    assert pt_trace.steps[-1].top == expected

    print("PASS")
```

---

## i32 溢出语义（内部表示补充）

所有算术运算遵循 WASM 的 i32 溢出规则: 结果会与 `0xFFFFFFFF` 做按位与。例如 `0xFFFFFFFF + 1 = 0`。除以零会触发 TRAP (操作码 99), 不是 Python 异常。下面的例子继续沿用内部 `Instruction` 表示, 只是为了说明语义如何在运行时内部落地。

```python
# 溢出示例
from transturing.core.isa import Instruction, OP_PUSH, OP_ADD, OP_HALT, MASK32
from transturing.backends.numpy_backend import NumPyExecutor

prog = [
    Instruction(OP_PUSH, 0xFFFFFFFF),
    Instruction(OP_PUSH, 1),
    Instruction(OP_ADD),
    Instruction(OP_HALT),
]

trace = NumPyExecutor().execute(prog)
print(trace.steps[-1].top)    # 输出: 0 (不是 0x100000000)
```

---

## 进一步阅读

- [工作原理](how-it-works.md): 追踪一个 4 指令程序的完整执行过程
- [ISA 参考](../isa/index.md): 完整的 55 个操作码分类索引
- [操作码详解](../isa/opcodes.md): 每个操作码的语义和参数说明
- [架构概览](../architecture/overview.md): 系统设计和关键概念
- [项目 README](../../README.md): 项目总览和 `.wasm` bytes 执行主线
