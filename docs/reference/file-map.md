# 仓库文件地图

按功能区域组织的完整文件索引。每个文件附一行说明和行数。

---

## 核心执行引擎

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/llm_as_computer/isa.py` | 869 | 55 操作码定义、TokenVocab 词表、抛物线嵌入函数、CompiledAttentionHead、compare_traces 对比工具 |
| `src/llm_as_computer/executor.py` | 1360 | NumPyExecutor（NumPy 后端）、CompiledModel（PyTorch nn.Module）、TorchExecutor（PyTorch 后端） |

这两个文件构成了整个系统的核心：`src/llm_as_computer/isa.py` 定义指令集和编码方案，`src/llm_as_computer/executor.py` 实现两个等价的执行器。所有操作码的权重通过 `_compile_weights()` 解析计算，不依赖训练。

---

## 程序与测试

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/llm_as_computer/programs.py` | 703 | 测试程序生成器：fib、multiply、gcd、factorial、位运算等 30+ 个 `make_*` 函数 |
| `tests/test_consolidated.py` | 485 | 集成测试：NumPy 执行器等价性、PyTorch 执行器等价性、双执行器交叉验证 |
| `tests/test_wat_parser.py` | 496 | WAT 解析器测试套件：解析、编译、执行全链路验证 |

每个测试都必须通过 `compare_traces()` 验证 NumPyExecutor 和 TorchExecutor 产生完全一致的执行轨迹。

---

## 编译工具链

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/llm_as_computer/assembler.py` | 229 | WASM 风格结构化控制流编译器（block/loop/if/br/br_table → 扁平 ISA） |
| `src/llm_as_computer/wat_parser.py` | 777 | WebAssembly 文本格式（WAT）解析器，完整支持 WAT 语法 |
| `src/llm_as_computer/c_pipeline.py` | 647 | C → WAT → ISA 编译管线（需要 clang + wasm2wat） |

编译方向：C 源码 → clang 编译为 WASM → wasm2wat 转 WAT 文本 → wat_parser 解析 → assembler 编译为扁平 ISA → executor 执行。所有编译工具链模块位于 `src/llm_as_computer/` 包中。

---

## 文档 (`docs/`)

| 文件 | 行数 | 说明 |
|------|------|------|
| `docs/README.md` | 108 | 文档导航主页，含阅读路线推荐 |
| `docs/quickstart.md` | 76 | 快速开始：环境搭建与第一个程序 |
| **架构** | | |
| `docs/architecture/overview.md` | 182 | 架构概览：抛物线编码、注意力头、内存空间 |
| `docs/architecture/memory-model.md` | 295 | 五大内存空间的寻址机制 |
| `docs/architecture/compilation.md` | 171 | 编译流程：从程序到 transformer 权重 |
| **指南** | | |
| `docs/guides/how-it-works.md` | 170 | 逐步跟踪一个 4 指令程序的执行过程 |
| `docs/guides/writing-programs.md` | 451 | 程序编写指南：汇编器和 WAT 用法 |
| **ISA 参考** | | |
| `docs/isa/index.md` | 127 | 55 操作码分类索引 |
| `docs/isa/opcodes.md` | 297 | 操作码详解：语义、参数、执行行为 |
| **开发** | | |
| `docs/development/findings-summary.md` | 104 | 20 个研究阶段的核心结论摘要 |
| `docs/development/rd-plan-summary.md` | 58 | R&D 路线图与阶段演进 |
| **参考** | | |
| [docs/reference/api.md](api.md) | | API 参考：NumPyExecutor、TorchExecutor 等核心接口 |
| `docs/reference/file-map.md` | | 本文件 — 仓库文件结构与职责 |

---

## 项目元文件

| 文件 | 说明 |
|------|------|
| `AGENTS.md` | 项目级 AI 代理指令 |
| `README.md` | 项目主页和 ISA 参考表 |

---

## 导航

- [API 参考](api.md)
- [文档主页](../README.md)
- [项目主页](../../README.md)
