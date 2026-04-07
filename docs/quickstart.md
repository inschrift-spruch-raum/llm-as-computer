# 快速开始

5 分钟理解 transturing 当前支持什么、不支持什么，以及如何把一个受支持的 `.wasm` 模块交给执行器运行。

## 当前公开契约

transturing 现在按**执行受支持 WASM32 字节输入的运行时**来定义自己。

- 你提供受支持的 `.wasm` 二进制模块
- 运行时返回 transformer 支持的执行轨迹与结果
- 内部 55 操作码表示不是公开 authoring 接口
- C 源码编译、外部 toolchain 集成、以及公开 private-ISA helper 都不属于当前支持范围

这是一轮破坏性契约重置。如果你是从旧文档或旧导出名过来，请把 compile/toolchain 相关工作流视为已退场。

## 前置条件

- Python 3.14
- Git

## 安装

```bash
git clone https://github.com/oaustegard/transturing.git
cd transturing
uv sync
```

> 执行 `uv sync` 会把项目和依赖安装到 `.venv`。

## 执行一个 `.wasm` 模块

当前仓库中，推荐你把“执行受支持 WASM32 bytes”理解为两段：

1. 用包根公开 API 选择后端
2. 用保留在 `transturing.core.wasm_binary` 的 WASM bytes ingestion helper 把模块转成可执行程序，再交给后端执行

```python
from pathlib import Path

from transturing import get_executor
from transturing.core.wasm_binary import compile_wasm_module

wasm_bytes = Path("program.wasm").read_bytes()

executor = get_executor()          # torch > numpy
program = compile_wasm_module(wasm_bytes)
trace = executor.execute(program)

print(trace.steps[-1].top)
```

如果你的模块导出多个函数，可以显式指定入口：

```python
program = compile_wasm_module(wasm_bytes, func_name="main")
trace = executor.execute(program)
```

> 这里的重点是“`.wasm` bytes 输入 → 后端执行 → trace/result 输出”。不要把 `core.wasm_binary` 中保留的 helper 理解为旧 compile/toolchain 产品面的恢复；它只是当前运行时支持受支持 `.wasm` 输入的仓库内入口。

## 现在先读什么

如果你读完上面的最小执行示例，再继续看下面这些文档会更顺。

1. 看 [项目首页](../README.md) 里的产品边界说明
2. 看 [文档首页](README.md) 里的范围重置说明
3. 如果你关心实现细节，再读 [工作原理](guides/how-it-works.md) 和 [架构概览](architecture/overview.md)
4. 如果你研究内部执行表示，再读 [ISA 参考](isa/index.md)

如果你只是想确认仓库环境可运行，可以在项目根目录执行：

```bash
uv run pytest tests/ -v
```

这只是仓库验证命令，不代表公开产品契约是“手写 ISA 程序”或“旧式 compile/toolchain 流程”。

## 非目标提醒

- 不要把 C 源码编译看成支持路径
- 不要把 toolchain 管理看成本项目职责
- 不要把私有 ISA authoring helper 看成稳定公共 API

## 下一步

- **[工作原理](guides/how-it-works.md)**, 看一个最小执行示例在注意力层里到底发生了什么
- **[架构概览](architecture/overview.md)**, 了解抛物线编码和五大内存空间
- **[程序编写](guides/writing-programs.md)**, 先看 `.wasm` bytes 执行路径，再决定是否阅读内部实现补充
- **[完整 ISA 参考](isa/index.md)**, 查阅全部 55 个操作码

[返回文档首页](README.md)
