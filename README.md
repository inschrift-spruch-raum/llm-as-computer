# transturing

一个**面向受支持 WASM32 字节输入的 transformer 运行时**。你提供 `.wasm` 二进制模块，运行时在 transformer 自身的推理循环里执行它，并返回执行轨迹与结果。每一次取指、每一次栈/局部变量/堆/调用帧读取，都是一个抛物线注意力头。transformer **就是** 这台计算机。

本项目用于独立验证 [Percepta 的论断](https://percepta.ai/blog/can-llms-be-computers)：transformer 能否通过 2D 凸包注意力，以每步 `O(log t)` 的复杂度执行任意程序。

## 产品边界

当前公开契约很窄：**受支持的 WASM32 bytes in, runtime trace/result out**。

- 输入是受支持的 `.wasm` 二进制模块
- 输出是 NumPy 或 PyTorch 后端产生的执行轨迹与最终结果
- 对外产品定位是运行时，不是源码编译器
- C 源码编译、外部 toolchain 管理、以及面向用户的私有 ISA 编写，都不属于当前支持范围
- 内部 55 操作码执行表示仍然存在，但应视为实现细节与研究材料，而不是公开 authoring 接口

这是一次**破坏性契约重置**。如果你是从旧文档或旧分支进入本仓库，请忽略历史上的 compile/toolchain 叙事。

## 5 分钟上手

先安装依赖：

```bash
git clone https://github.com/oaustegard/transturing.git
cd transturing
uv sync
```

然后准备一个受支持的 `.wasm` 模块，并用运行时执行它：

```python
from pathlib import Path

from transturing import get_executor
from transturing.core.wasm_binary import compile_wasm_module

wasm_bytes = Path("examples/add.wasm").read_bytes()

# 选择后端：None 时按 torch > numpy 自动选择
executor = get_executor("torch")

# 当前仓库保留的 WASM bytes ingestion helper 位于 core.wasm_binary
program = compile_wasm_module(wasm_bytes, func_name="add")
trace = executor.execute(program)

print(trace.steps[-1].top)
print(trace.format_trace())
```

> 注意：当前 package root 的稳定公开导出只有 `get_executor()`、`list_backends()`、`Trace`、`TraceStep`。`transturing.core.wasm_binary` 中的 WASM bytes ingestion helper 仍然保留并可用，但应按“当前运行时入口支撑代码”理解，而不是旧式 compile/toolchain 产品面。

## 当前支持什么

- 已验证的 WASM i32 子集
- 通过 `get_executor('numpy')` 或 `get_executor('torch')` 选择后端执行
- 完整执行轨迹输出（便于做 NumPy/Torch 一致性验证）
- 支持的 `.wasm` 导出函数自动探测或按 `func_name` 选择入口

## 当前不支持什么

- 把本仓库当作 C→WASM 编译工具链
- 把私有 55-opcode ISA 当作面向用户的手写程序接口
- 把内部 lowering 路径当作公开工作流承诺
- 未验证的更广泛 WebAssembly 特性

## 为什么这不是“普通解释器”

如果你是第一次接触这个项目，建议先看 **[How It Works](docs/guides/how-it-works.md)**。它会逐步演示一个极小程序在注意力机制里的执行过程，说明为什么这里的“内存读取”本质上是点积 + `argmax`。

简短版本是：

- 程序内存、栈、局部变量、堆、调用帧都编码成 transformer 上下文中的键值对
- 地址 `j` 用抛物线 key `k=(2j,-j²)` 编码
- 读取地址 `i` 时，用查询向量做点积并取 `argmax`
- 因而每次取指和每次内存读取都落在注意力机制内部完成

## 文档入口

- **[Quick Start](docs/quickstart.md)** —— 当前契约、安装、执行一个 `.wasm` 模块
- **[How It Works](docs/guides/how-it-works.md)** —— 4 指令示例的逐步执行解释
- **[Architecture Overview](docs/architecture/overview.md)** —— 抛物线寻址、五个内存空间、两个后端
- **[Writing Programs](docs/guides/writing-programs.md)** —— 以 `.wasm` bytes 执行为主线；内部 ISA 资料仅作研究补充
- **[API Reference](docs/reference/api.md)** —— 包根公开 API 与保留的内部模块入口说明
- **[Development Findings](docs/development/findings-summary.md)** —— “编译优于训练”的研究结论

## 两个执行后端

- **PyTorch**：主后端。`TorchExecutor` 封装解析构造出的 `CompiledModel`
- **NumPy**：参考/演示后端。`NumPyExecutor` 提供纯 NumPy 等价执行

推荐总是先通过注册表获取：

```python
from transturing import get_executor, list_backends

print(list_backends())
executor = get_executor()  # 自动选择可用后端
```

## 内部实现概览

运行时内部仍使用一套 55 操作码的 WASM 风格栈机表示，语义以 WebAssembly i32 子集为蓝本。前馈层负责操作码分发；注意力头负责程序、栈、局部变量、堆和调用帧寻址。

这些内容仍然重要，但它们属于**内部实现与研究材料**。如果你只想使用当前支持的产品边界，请把重点放在：

1. 准备受支持的 `.wasm` 字节
2. 选择后端
3. 执行并读取 trace/result

完整 ISA 细节见 **[docs/isa/index.md](docs/isa/index.md)**。

## 基准结果

百万步级别的执行基准见：[Issue #52](https://github.com/oaustegard/transturing/issues/52#issuecomment-2752773503)。

关键数据：Python 执行速度 **2.1–3.1M steps/sec**，120 万步执行时间约 561ms。

## 仓库结构

```text
src/transturing/
├── __init__.py                包根公开 API（Trace / TraceStep / get_executor / list_backends）
├── core/
│   ├── isa.py                 内部 55-opcode 表示、Trace 类型、数学辅助函数
│   ├── registry.py            后端发现与注册
│   ├── programs.py            测试/研究程序生成器
│   └── wasm_binary.py         保留的 WASM bytes ingestion helper
└── backends/
    ├── numpy_backend.py       NumPyExecutor
    └── torch_backend.py       TorchExecutor / CompiledModel
```

## 相关博文

- **[Yes, LLMs Can Be Computers. Now What?](https://muninn.austegard.com/blog/yes-llms-can-be-computers-now-what)** —— 13 个阶段验证过程的完整叙述，包括一次虽走弯路但很有价值的训练尝试。
- **[The Free Computer: Why Offloading to CPU Is a Win for Everyone](https://muninn.austegard.com/blog/the-free-computer-why-offloading-to-cpu-is-a-win-for-everyone)** —— 关于编译型 CPU 执行路径的经济学论证。
