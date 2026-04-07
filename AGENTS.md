# AGENTS.md

本文件给后续在本仓库中工作的代理（agent）提供仓库级约束与操作指南。内容仅基于当前工作树可见代码整理。

## 1. 仓库目标

`transturing` 是一个实验性运行时库：

- 统一执行内部栈机 ISA
- 支持受限 WASM32 `i32` 子集的二进制摄入与降低
- 维护 NumPy 与 Torch 两条后端路径的**语义一致性**
- 用 `Trace` / `TraceStep` 暴露完整执行轨迹

后续任何改动都应优先保护这一目标，而不是只让单个后端“能跑”。

## 2. 代码结构速览

- `src/transturing/__init__.py`：包根公开 API，仅导出 `Trace`、`TraceStep`、`get_executor`、`list_backends`
- `src/transturing/core/abc.py`：统一后端接口 `ExecutorBackend`
- `src/transturing/core/isa.py`：最核心协议文件，定义 opcode、trace 类型、帮助函数、嵌入维度布局
- `src/transturing/core/registry.py`：后端发现与自动选择
- `src/transturing/core/programs.py`：测试/示例程序生成器
- `src/transturing/core/wasm_binary.py`：WASM 解码、验证、structured control flow lowering、链接
- `src/transturing/backends/numpy_backend.py`：参考解释器风格实现
- `src/transturing/backends/torch_backend.py`：transformer 风格的编译执行器
- `tests/test_consolidated.py`：执行正确性与 NumPy/Torch parity
- `tests/test_wasm_binary.py`：WASM 入口端到端验证
- `docs/design.md`：当前设计文档

## 3. 修改优先级规则

### 3.1 先保协议，再改实现

如果你需要改动执行逻辑，默认先检查：

1. `isa.py` 中的数据模型和 opcode 语义是否需要变化
2. `numpy_backend.py` 和 `torch_backend.py` 是否都需要同步更新
3. `tests/test_consolidated.py` 与 `tests/test_wasm_binary.py` 是否需要补充或调整
4. `docs/design.md`、`README.md` 是否需要更新

不要只修单个后端而忽略另一条路径，除非改动目标明确限定在某个后端专属实现上。

### 3.2 NumPy 是参考语义，Torch 是模型化语义

当前代码库里：

- NumPy 后端更适合先读懂和先修语义
- Torch 后端更适合验证“同样语义如何被 embedding / attention / 解析式权重表达”

如果要修执行错误，通常应先在 NumPy 路径上确认正确语义，再把同样语义映射到 Torch 路径。

### 3.3 Parity 是一等约束

本仓库最重要的质量指标之一，是相同程序在 NumPy 和 Torch 两后端中产生一致或兼容的执行轨迹。

任何会改变：

- `TraceStep.op`
- `TraceStep.arg`
- `TraceStep.sp`
- `TraceStep.top`

的修改，都应被视为高风险改动，必须补测试并重新跑 parity 验证。

## 4. 工作时的具体准则

### 4.1 改 ISA 时

如果你改 `src/transturing/core/isa.py`：

- 同步检查 `numpy_backend.py` 的 dispatch 与 handler 语义
- 同步检查 `torch_backend.py` 中的 token、embedding、forward 逻辑
- 必要时更新 `programs.py` 里的样例程序
- 必须补或改测试

注意：当前 `D_MODEL = 51`，维度布局已被全部占用。若增加新的状态地址空间或 embedding 语义，通常意味着需要系统性修改 Torch 路径，而不是只加一个常量。

### 4.2 改 WASM 摄入路径时

如果你改 `src/transturing/core/wasm_binary.py`：

- 明确修改的是**支持范围**还是**lowering/链接策略**
- 为新增支持或拒绝条件补测试
- 确保生成的 `Instruction` 程序仍可被两个执行后端正确消费
- 若更改参数/locals 约定，必须同步更新 README、设计文档和测试

当前实现显式拒绝 imports、globals、tables、start、element、data、data_count 等；也拒绝非 `i32` 类型、非零 memarg offset 和非空 block signature。除非明确扩展支持范围，否则不要在无测试的情况下悄悄放宽边界。

### 4.3 改公共 API 时

如果你改 `src/transturing/__init__.py` 或 `core/registry.py`：

- 保持 README 的安装/使用示例同步
- 说明是新增包根导出，还是仍要求从 `core.*` 子模块显式导入
- 检查自动后端选择顺序是否改变

## 5. 测试与验证要求

完成代码修改后，至少执行：

```bash
python -m pytest tests/test_consolidated.py tests/test_wasm_binary.py
python -m basedpyright src tests
```

如果环境里使用的是本仓库 `.venv`，则可用：

```bash
.venv\Scripts\python.exe -m pytest tests/test_consolidated.py tests/test_wasm_binary.py
.venv\Scripts\python.exe -m basedpyright src tests
```

如有必要，再执行：

```bash
python -m ruff check .
```

说明：`tests/conftest.py` 会尝试在缺少 `numpy` 或 `torch` 时给相关测试打 skip 标记，但当前测试树也包含顶层直接导入后端模块的文件，因此不要把“自动跳过”理解为对所有测试场景都完全可靠。要获得稳定结果，优先安装所需后端依赖后再执行测试，并区分“通过”和“被环境跳过”。

## 6. 文档维护要求

以下类型的变更，默认需要同步更新文档：

- 新增/修改公共 API → 更新 `README.md`
- 改变系统架构、运行流或模块职责 → 更新 `docs/design.md`
- 改变仓库级协作约束、验证方式或重点文件 → 更新 `AGENTS.md`

文档中不要引用不可从当前工作树验证的历史信息；当前仓库的文档策略偏向“只写当前代码能证明的事实”。

## 7. 不要做的事

- 不要只改一个后端却宣称系统语义已修复
- 不要在没有测试覆盖的情况下扩展 WASM 支持边界
- 不要把 README 写成 CLI 文档——当前仓库没有 CLI
- 不要假定 `compile_wasm_module()` 已从包根导出——当前没有
- 不要把 `TorchExecutor` 描述成训练得到的模型——当前权重是解析式设置的，不存在训练流水线

## 8. 建议阅读顺序

1. `README.md`
2. `docs/design.md`
3. `src/transturing/core/isa.py`
4. `src/transturing/backends/numpy_backend.py`
5. `src/transturing/backends/torch_backend.py`
6. `src/transturing/core/wasm_binary.py`
7. `tests/`

## 9. 一句话原则

在这个仓库里，**任何实现修改都应围绕统一 ISA、完整 Trace，以及 NumPy/Torch 双后端语义一致性来做决策。**
