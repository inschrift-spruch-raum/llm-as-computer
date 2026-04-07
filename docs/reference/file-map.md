# 仓库文件地图

按功能区域组织的完整文件索引。每个文件附一行说明和行数。项目采用 `src/` 布局，核心代码在 `src/transturing/core/`（零依赖 ISA、类型、后端抽象），后端实现在 `src/transturing/backends/`（隔离的 NumPy 和 PyTorch 实现）。

---

## 包入口

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/transturing/__init__.py` | 9 | 顶层稳定公开面：`Trace`、`TraceStep`、`get_executor()`、`list_backends()` |

从 `transturing` 直接导入时，只应假定上述 4 个符号稳定可用。其余 helper 与内部类型请从 `transturing.core.*` 或具体后端模块进入。

---

## 核心子包 (`src/transturing/core/`)

零依赖的 ISA 定义、类型系统、后端抽象和公共 API。

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/__init__.py` | 12 | core 级公开面：`ExecutorBackend`、`Trace`、`TraceStep`、`get_executor()`、`list_backends()`、`register_backend()` |
| `core/isa.py` | 640 | 55 操作码定义、DIM 维度常量（51 维）、数学辅助函数、`Trace`/`TraceStep`/`Instruction`/`WasmInstr` 类型、`program()` 构建器、`compare_traces()`/`test_algorithm()` 测试工具 |
| `core/abc.py` | 13 | `ExecutorBackend` 抽象基类，定义 `execute(prog, max_steps) -> Trace` 接口 |
| `core/registry.py` | 49 | 后端注册表：`get_executor()` 工厂函数、`list_backends()` 发现函数、`register_backend()` 装饰器 |
| `core/programs.py` | 604 | 测试程序生成器：`make_*` 风格算法样例（fib、multiply、gcd、factorial、位运算、select 等） |
| `core/wasm_binary.py` | 1003 | 保留的 WASM bytes ingestion 路径。解码当前已验证的 i32 子集，内联结构化控制流 lowering，并暴露 `compile_wasm*` / `parse_wasm*` 供内部运行时入口与测试使用 |

依赖方向：`isa.py` 是共享根模块。`programs.py` 复用其 ISA/测试工具；`wasm_binary.py` 复用其操作码与 `Instruction`/`WasmInstr` 类型承接 `.wasm` bytes ingestion；两个后端也从 `isa.py` 引用 DIM/OP 常量。

---

## 后端子包 (`src/transturing/backends/`)

隔离的后端实现，通过 `core/abc.py` 的 `ExecutorBackend` 接口统一。

| 文件 | 行数 | 说明 |
|------|------|------|
| `backends/__init__.py` | 1 | 仅含 docstring，防止直接导入。后端通过 `get_executor()` 按需加载 |
| `backends/numpy_backend.py` | 508 | `NumPyExecutor`：纯 NumPy 编译执行器。内部类 `_ParabolicStore`（抛物线键值存储，eps=1e-10）和 `_ExecCtx`（执行上下文） |
| `backends/torch_backend.py` | 1072 | `TorchExecutor`、`CompiledModel`（nn.Module，10 个注意力头，2656 参数）、`CompiledAttentionHead`、`TokenVocab`、6 个 `embed_*` 嵌入函数、`DTYPE`/`EPS` 常量。内部类 `_ForwardResult`、`_ExecState`、`_MemoryEmbs` |

后端通过 `from transturing.core.isa import ...` 引用核心模块，彼此完全隔离。

---

## 测试 (`tests/`)

| 文件 | 行数 | 说明 |
|------|------|------|
| `tests/__init__.py` | 1 | 测试包标记 |
| `tests/conftest.py` | 23 | pytest 配置：后端未安装时自动跳过测试 |
| `tests/test_consolidated.py` | 552 | 集成测试：NumPy 执行器等价性、PyTorch 执行器等价性、双执行器交叉验证 |
| `tests/test_wasm_binary.py` | 886 | `.wasm` bytes ingestion、结构化 lowering、解码失败路径、双后端运行回归 |

每个测试都通过 `compare_traces()` 验证 NumPyExecutor 和 TorchExecutor 产生完全一致的执行轨迹。

---

## WASM 二进制导入路径

```
.wasm 字节 → wasm_binary 最小前端解码 → 结构化控制流 lowering → 扁平 ISA → executor 执行
```

程序通过 `wasm_binary.py` 的 `compile_wasm()` / `compile_wasm_module()` / `compile_wasm_function()` 进入既有 lowering 语义。当前记录的支持范围只覆盖已验证的 i32 子集；这里描述的是保留的内部/参考入口，不是新的公开 toolchain 承诺。

---

## 文档 (`docs/`)

| 文件 | 说明 |
|------|------|
| **架构** | |
| `docs/architecture/overview.md` | 架构概览：抛物线编码、注意力头、内存空间 |
| `docs/architecture/memory-model.md` | 五大内存空间的寻址机制 |
| `docs/architecture/compilation.md` | 编译流程：执行器权重如何固定，程序如何降到 ISA |
| **指南** | |
| `docs/guides/how-it-works.md` | 逐步跟踪一个 4 指令程序的执行过程 |
| `docs/guides/writing-programs.md` | 程序编写指南：`.wasm` bytes 执行主线 + 内部 ISA/研究补充 |
| **ISA 参考** | |
| `docs/isa/index.md` | 55 操作码分类索引 |
| `docs/isa/opcodes.md` | 操作码详解：语义、参数、执行行为 |
| **开发** | |
| `docs/development/findings-summary.md` | 20 个研究阶段的核心结论摘要 |
| `docs/development/rd-plan-summary.md` | R&D 路线图与阶段演进 |
| **参考** | |
| [docs/reference/api.md](api.md) | API 参考：包根公开面、后端、内部运行时入口与研究型 helper |
| `docs/reference/file-map.md` | 本文件，仓库文件结构与职责 |

---

## 项目元文件

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 项目配置（src/ 布局、hatchling 构建、可选依赖） |
| `uv.lock` | 可复现的依赖锁定文件 |
| `.python-version` | Python 版本要求（3.14） |
| `AGENTS.md` | 项目级 AI 代理指令 |
| `README.md` | 项目主页与运行时边界概览 |

---

## 导航

- [API 参考](api.md)
- [文档主页](../README.md)
- [项目主页](../../README.md)
