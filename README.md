# transturing

`transturing` 是一个面向受限 WASM32 `i32` 子集的实验性运行时库。它把内部 `Instruction` 程序或受支持的 WebAssembly 二进制，统一映射到同一套执行协议，并输出完整执行轨迹 `Trace`。

当前仓库中的实现有两条后端路径：

- **NumPy 后端**：更接近参考解释器，逐条执行内部 ISA。
- **Torch 后端**：把执行语义编码进 transformer 风格的 embedding、attention 和解析式权重，通过逐步前向推理执行程序。

这两个后端的目标不是共享同一种实现方式，而是共享同一种**可验证语义**；测试会校验它们产生相同的执行轨迹。

> 详细设计说明见 [`docs/design.md`](docs/design.md)；长期演进规划见 [`docs/roadmap.md`](docs/roadmap.md)。

## 当前能力范围

- 统一的内部栈机 ISA，包含算术、比较、位运算、局部变量、线性内存、函数调用、分支与 trap 表示。
- 可直接执行 `list[Instruction]`。
- 可解析并降低一个受限的 WASM MVP 子集到内部 `Instruction` 程序。
- 返回完整执行轨迹，而不仅是最终结果。

当前**不是**完整 WebAssembly 运行时。现有代码明确只支持收窄后的 WASM 子集，不支持 imports、globals、tables、start、element、data、data_count 等 section，也不支持非 `i32` 类型、非零 memory offset 与非空 block signature。

## 项目结构

```text
transturing/
├── README.md
├── AGENTS.md
├── docs/
│   └── design.md
├── pyproject.toml
├── src/
│   └── transturing/
│       ├── __init__.py
│       ├── core/
│       │   ├── abc.py
│       │   ├── isa.py
│       │   ├── programs.py
│       │   ├── registry.py
│       │   └── wasm_binary.py
│       └── backends/
│           ├── numpy_backend.py
│           └── torch_backend.py
└── tests/
    ├── conftest.py
    ├── test_consolidated.py
    └── test_wasm_binary.py
```

## 环境要求

- Python **3.14+**
- 构建系统：`hatchling`
- 运行时默认无强制依赖

可选依赖见 `pyproject.toml`：

- `numpy` extra：启用 NumPy 后端
- `torch` extra：启用 Torch 后端
- `all` extra：启用全部后端

## 安装

### 使用 uv

安装开发环境：

```bash
uv sync --extra all --group dev
```

仅安装某一个后端依赖时，可以按需选择：

```bash
uv sync --extra numpy
uv sync --extra torch
```

### 使用 pip

```bash
pip install -e .
pip install -e .[numpy]
pip install -e .[torch]
pip install -e .[all]
```

## 快速开始

### 1. 获取执行器并运行内部程序

包根当前导出的公共 API 很小：

- `Trace`
- `TraceStep`
- `get_executor`
- `list_backends`

示例：

```python
from transturing import get_executor
from transturing.core.isa import Instruction, OP_ADD, OP_HALT, OP_PUSH

prog = [
    Instruction(OP_PUSH, 3),
    Instruction(OP_PUSH, 5),
    Instruction(OP_ADD),
    Instruction(OP_HALT),
]

executor = get_executor("numpy")
trace = executor.execute(prog)

print(trace.steps[-1].top)  # 8
print(trace.format_trace())
```

如果未显式指定后端，`get_executor()` 会按当前代码中的优先级自动选择：

1. `torch`
2. `numpy`

可以用 `list_backends()` 查看当前环境中成功可用的后端。

### 2. 从受支持的 WASM 二进制生成内部程序

WASM 入口没有从包根直接 re-export，需要显式从 `transturing.core.wasm_binary` 导入：

```python
from transturing import get_executor
from transturing.core.wasm_binary import compile_wasm_module

wasm_bytes = open("sample.wasm", "rb").read()
prog = compile_wasm_module(wasm_bytes)

trace = get_executor("numpy").execute(prog)
print(trace.steps[-1].top)
```

如果目标导出函数需要参数，当前实现约定是：

- 在执行开始前，先把参数按顺序压入操作数栈
- 然后执行由 `compile_wasm_module()` 生成的平面程序；函数入口的 local setup 会再按当前约定把这些参数弹入 parameter locals

仓库中的 `tests/test_wasm_binary.py` 展示了这一用法模式。

## 核心概念

### `Instruction`

内部执行的最小单元，包含：

- `op`：opcode
- `arg`：可选整数参数

### `TraceStep`

记录单步执行结果，包含：

- 指令 `op`
- 指令参数 `arg`
- 执行后栈指针 `sp`
- 执行后栈顶 `top`

### `Trace`

一次执行的完整轨迹，包含：

- 原始程序 `program`
- 每一步的 `steps`

项目的正确性标准不只是“最终结果对”，而是**执行轨迹也尽量一致**。测试中会直接比较 NumPy 与 Torch 两后端的 trace parity。

## 测试与校验

运行测试：

```bash
python -m pytest
```

仓库里最关键的测试文件：

- `tests/test_consolidated.py`：后端正确性与跨后端一致性
- `tests/test_wasm_binary.py`：WASM 二进制解析、降低与执行

`tests/conftest.py` 确实会根据依赖可用性给部分测试加 skip 标记，但当前测试树里也存在顶层直接导入后端模块的文件，因此**最稳妥的做法仍然是先安装所需后端依赖再运行测试**。

运行类型检查：

```bash
python -m basedpyright src tests
```

运行 lint：

```bash
python -m ruff check .
```

## 设计阅读建议

建议按下面顺序理解仓库：

1. `src/transturing/__init__.py`
2. `src/transturing/core/abc.py`
3. `src/transturing/core/isa.py`
4. `src/transturing/core/registry.py`
5. `src/transturing/backends/numpy_backend.py`
6. `src/transturing/backends/torch_backend.py`
7. `src/transturing/core/wasm_binary.py`
8. `tests/`

更完整的架构说明请看 [`docs/design.md`](docs/design.md)。

## 已知边界

- 这是一个**库**，当前没有 CLI 或 `__main__` 入口。
- 只支持受限 WASM `i32` 子集，不是完整虚拟机。
- Torch 路径虽以 transformer 风格表达执行语义，但外层执行循环仍由 Python 驱动。
- `OP_TRAP` 在当前实现中用于表达运行时陷阱事件，是一个特殊哨兵 opcode。

## 许可证

根据 `pyproject.toml` 中的 classifier，当前项目使用 **MIT License**。
