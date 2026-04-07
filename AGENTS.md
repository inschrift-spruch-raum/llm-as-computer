# LLM-as-Computer

**生成时间：** 2026-04-07  
**提交：** 01a26d1  
**分支：** main

面向受支持 WASM32 字节输入的 transformer 运行时。用户提供 `.wasm` 二进制模块，运行时在 transformer 自身的推理循环中执行它。每次取指与每次内存读取都由一个抛物线注意力头完成。transformer *就是* 这台计算机。内部执行表示仍是 55 操作码的 WASM 风格栈机，Python 后端以 PyTorch 为主，NumPy 为参考实现。

## 产品契约

- 公开边界是“受支持的 WASM32 bytes in, runtime trace/result out”
- source-language compilation、C toolchain、以及公开 private-ISA authoring helper 都是非目标
- 55 操作码 ISA 仍可作为内部实现和研究材料描述，但不再是对外产品契约
- 当前阶段把这次收缩视为破坏性契约重置，不保留旧 compile/toolchain API 的兼容承诺

## 结构

```text
./
├── src/
│   └── transturing/              # Python 包（可通过 pip 安装）
│       ├── __init__.py           # 顶层稳定公开面：Trace / TraceStep / get_executor / list_backends
│       ├── core/                 # 零依赖核心层
│       │   ├── __init__.py       # core 级公开面：ExecutorBackend + 注册表 + Trace 类型
│       │   ├── isa.py            # 55 个操作码、DIM 常量、数学辅助函数、Trace 类型
│       │   ├── abc.py            # ExecutorBackend 抽象基类
│       │   ├── registry.py       # 后端发现（get_executor, list_backends）
│       │   ├── programs.py       # 测试程序 + 算法生成器（fib、mul、gcd 等）
│       │   ├── wasm_binary.py    # 保留的 WASM bytes ingestion 路径（解码 + structured lowering）
│       └── backends/             # 隔离的后端实现
│           ├── __init__.py       # 仅文档字符串（保护动态导入）
│           ├── numpy_backend.py  # NumPyExecutor（参考/演示实现）
│           └── torch_backend.py  # CompiledAttentionHead、TokenVocab、CompiledModel、TorchExecutor
├── tests/
│   ├── __init__.py               # 测试包标记
│   ├── conftest.py               # 当后端未安装时自动跳过测试
│   ├── test_consolidated.py      # 执行器正确性 + 双后端一致性测试
│   └── test_wasm_binary.py       # WASM bytes ingestion / lowering / 解码边界测试
├── docs/
│   ├── architecture/             # overview.md、memory-model.md、compilation.md
│   ├── isa/                      # index.md、opcodes.md
│   ├── guides/                   # how-it-works.md、writing-programs.md
│   ├── development/              # findings-summary.md、rd-plan-summary.md
│   └── reference/                # api.md、file-map.md
├── pyproject.toml                # uv 项目配置（src 布局、hatchling 构建、可选依赖）
├── uv.lock                       # 可复现的依赖锁文件
└── .python-version               # Python 3.14
```

## 应该去哪里看

| 任务 | 位置 | 说明 |
|------|------|------|
| 新增一个操作码 | `src/transturing/core/isa.py` + 两个后端 | 必须同时更新 NumPyExecutor 和 CompiledModel |
| 扩展 WASM 支持 | `src/transturing/core/wasm_binary.py` + `tests/test_wasm_binary.py` | 先看支持的二进制解码与 lowering，再补回归测试 |
| 编写测试程序 | `src/transturing/core/programs.py` | 遵循 `make_*` 模式，并加入测试运行器 |
| 理解某个 embedding | `src/transturing/backends/torch_backend.py` → `embed_*` 函数 | 配合 `core/isa.py` 中的 DIM 布局一起看 |
| 调试执行轨迹 | `src/transturing/core/isa.py` → `compare_traces()` | 可逐步比较差异 |
| 理解内部 structured lowering | `src/transturing/core/wasm_binary.py` | 结构化控制流 lowering 已内联在此文件，由该模块自行承接 |
| 新增后端 | `src/transturing/core/abc.py` + `src/transturing/core/registry.py` | 实现 `ExecutorBackend` 并用 `@register_backend` 注册 |
| 使用后端 | `from transturing import get_executor` | `get_executor('numpy')` 或 `get_executor('torch')` |
| 阅读文档 | `docs/` | 建议从 `docs/guides/how-it-works.md` 开始 |

## 架构

**当前状态（Phase 20）：** `d_model=51`，`head_dim=2`，55 个操作码。强制使用 Float64。注意力必须使用 Hard-max（`argmax`，**绝不**使用 softmax）。51 维 embedding 包含：3 个类型标记 + 2×5 组抛物线 key 对（prog/stack/local/heap/call）+ 24 个操作码标志位 + 4 个状态维度（IP/SP/OPCODE/VALUE）+ `DIM_ONE` + local/heap/call 标志位 + 调用值维度（`ret_addr/saved_sp/locals_base`）。

**两个后端：**
- **PyTorch（主后端）：** `TorchExecutor` 封装 `CompiledModel`（`nn.Module`）。这是主要执行后端。
- **NumPy（参考/演示）：** `NumPyExecutor` 提供纯 NumPy 的等价执行。用于验证和参考实现。

**五个内存空间** 由不同注意力头分别寻址：
- 程序内存（操作码 + 参数取指）
- 栈内存（读取 SP、SP-1、SP-2）
- 局部变量（`LOCAL.GET/SET/TEE`）
- 堆 / 线性内存（`I32.LOAD/STORE` 及字节/短整数变体）
- 调用帧（`CALL/RETURN`，保存返回地址和 SP）

**抛物线编码：** `k = (2j, -j²)` 用于编码位置 `j`。点积注意力会在目标位置形成尖锐峰值。所有内存空间共用同一种编码方式。Float32 的上限大约只有 4K 索引；Float64 可扩展到 25M+。

**导入图：** `core/isa.py` 是共享根节点：`programs.py` 复用其 ISA/测试工具，`wasm_binary.py` 复用其操作码与 `Instruction` 类型以承接 `.wasm` bytes ingestion，两个后端也统一通过 `from transturing.core.isa import ...` 读取 DIM/OP 常量。包根 `transturing/__init__.py` 只保留运行时公开面；若要找 WASM 入口或内部表示，向下进入 `core/`，不要假设存在旧的 C pipeline 或独立 assembler 模块。

## 阶段

| Phase | 当前沉淀位置 | 状态 | 证明了什么 |
|-------|--------------|------|------------|
| 1 | 历史研究阶段（已并入现有实现） | 完成 | 基于抛物线 key 的三分搜索可实现 O(log t) 查找 |
| 2 | 历史研究阶段（已并入现有实现） | 完成 | 抛物线编码可以做精确内存寻址 |
| 2b | 历史研究阶段（已并入现有实现） | 完成 | 残差寻址可扩展到 25M+ 地址范围 |
| 3 | 历史研究阶段（已并入现有实现） | 完成 | 累积和能够跟踪 IP/SP |
| 4 | 历史研究阶段（已并入现有实现） | 完成 | 手工构造的 transformer 可执行 PUSH/POP/ADD/DUP/HALT |
| 5 | 历史研究阶段（已并入现有实现） | 完成 | 训练：56% 准确率，0/50 完整 trace——学到了结构，没学到路由 |
| 6 | 历史研究阶段（已并入现有实现） | 完成 | 课程学习：56%→85%，39/50 完整 trace |
| 7 | 历史研究阶段（已并入现有实现） | 完成 | Percepta 架构（d=36,h=18,L=7）与 Phase 6 上限相同 |
| 8 | 历史研究阶段（已并入现有实现） | 完成 | 检索 100% 解决；算术是唯一瓶颈 |
| 9 | 历史研究阶段（已并入现有实现） | 完成 | 加权损失能完美解决翻倍，但 DIFF+ADD 仍是 0% |
| 10 | 历史研究阶段（已并入现有实现） | 完成 | 数字分解（探索性工作） |
| 11 | `src/transturing/backends/` | 完成 | 编译执行器：100% 正确，compile > train |
| 12 | `src/transturing/backends/torch_backend.py` | 完成 | 真实 PyTorch `nn.Module`，权重可编译构造 |
| 13 | `src/transturing/core/isa.py` + 后端 | 完成 | SWAP/OVER/ROT + Fibonacci/乘法/奇偶判断 |
| 14 | `src/transturing/core/isa.py` + 后端 | 完成 | 完整 55 操作码 ISA：MUL/DIV/REM/AND/OR/XOR/SHL/SHR/CLZ/CTZ/POPCNT/SELECT/NEG/ABS |
| 15 | `src/transturing/core/isa.py` + 后端 | 完成 | LOCAL.GET/SET/TEE——命名变量作用域 |
| 16 | `src/transturing/core/isa.py` + 后端 | 完成 | 堆内存：I32.LOAD/STORE + 字节/短整数变体 |
| 17 | `src/transturing/core/isa.py` + 后端 | 完成 | CALL/RETURN——递归阶乘可运行 |
| 18 | `tests/test_consolidated.py` | 完成 | 冒泡排序、递归 fib、多函数程序 |
| 19 | `src/transturing/core/wasm_binary.py` | 完成 | block/loop/if/br/br_table 结构化控制流 lowering |
| 20 | `tests/test_consolidated.py` + `tests/test_wasm_binary.py` | 完成 | i32 溢出掩码（WASM 语义） |

**核心结论：** 编译，不要训练。Phase 5-10 证明了梯度下降在多任务上下文中学不会真正的加法（`a+b`, `a≠b`）。Phase 11-20 证明了：当通用执行器的关键机制通过解析方式固定到模型结构中时，可以得到 100% 正确的执行；而具体程序则作为 ISA 输入运行，包括算术、分支、函数调用与堆内存操作。详细结论见 `docs/development/findings-summary.md`。

## 反模式（本项目）

- **绝不要使用 softmax** —— 只能用 Hard-max（`argmax`）。当 key 相同时，softmax 会给出均匀权重。
- **绝不要训练编译后的模型** —— 所有权重都应通过 `_compile_weights()` 解析设定。训练路线（Phase 5-10）只是一次有价值的弯路。
- **绝不要在编译模型上使用 float32** —— 抛物线寻址要求 Float64。得分值按 `addr²` 增长；float32 上限大约只有 4K。
- **绝不要压制类型错误** —— 不允许 `as any`、`@ts-ignore`、`# type: ignore`。
- **绝不要盲读大文件** —— 先用 `docs/reference/api.md` 做函数索引，再按行段精读。`torch_backend.py`（约 1072 行）和 `wasm_binary.py`（约 1003 行）都是最大陷阱。
- **不要锁死精确依赖版本** —— 研究型仓库应优先使用 `>=` 下界。
- **不要使用裸模块导入** —— 始终使用 `from transturing.X import ...`，绝不要 `from isa import ...`。

## 约定

- **pytest** —— 测试套件使用 pytest，包含参数化测试与 fixtures。运行全部测试：`uv run pytest tests/ -v`
- **双执行器验证** —— 一致性测试要求 NumPyExecutor 和 TorchExecutor 通过 `compare_traces()` 产生完全一致的 trace。
- **i32 溢出语义** —— 所有算术都应用 `result & 0xFFFFFFFF`（WASM 标准）。例如：`PUSH 0xFFFFFFFF; PUSH 1; ADD` → `0`
- **TRAP 运行时错误** —— 除零、栈下溢等错误应发出 OP_TRAP（操作码 99），而不是抛 Python 异常。
- **自引用 EPS 值** —— NumPy 执行器使用 `eps=1e-10`；PyTorch 使用 `torch_backend.py` 里定义的 `EPS=1e-6`。两者不同是设计使然（精度上下文不同）。
- **近因偏置寻址** —— `eps * write_count` 让同一地址上的后写入获胜。这是架构特性，不是 hack。

## 命令

```bash
# 安装依赖（从 uv.lock 同步 .venv）
uv sync

# 安装开发工具依赖
uv sync --group dev

# 类型检查
uv run basedpyright src/ tests/

# Lint
uv run ruff check .

# 运行测试
uv run pytest tests/ -v

# 校验锁文件完整性
uv sync --locked
```

### 强制要求：每次修改后都要验证

**优先级：先使用代理内建检查，再退回项目命令。**

代理（例如 `deep`、`quick`、委派出去的子代理）通常自带验证流程——`lsp_diagnostics`、构建检查、测试执行等。**优先使用代理的内建检查系统。** 它更快、更了解上下文，而且已经和代理工作流集成。

只有当代理自带检查不足，或结果异常时，才退回到下面的完整项目验证。

**完整项目验证（回退方案）：**

1. **`uv run basedpyright src/ tests/`** —— 0 errors, 0 warnings, 0 notes
2. **`uv run ruff check .`** —— All checks passed
3. **`uv run pytest tests/ -v`** —— 全部测试通过

在验证（代理内建检查或完整项目检查）没有零错误通过之前，任何任务都不算完成。

## 备注

- **项目配置：** `[tool.uv]` 中 `package = true`，使用 src 布局；构建后端是 hatchling。`uv sync` 会以 editable mode 安装本包。
- **锁文件：** `uv.lock` 已提交，用于可复现依赖解析。执行 `uv sync` 即可按锁文件安装。
- **文件阅读：** 大文件先从 `docs/reference/api.md` 看函数索引，或从 `docs/reference/file-map.md` 看文件导航。对 >500 行文件，使用“先索引、再定点阅读”的模式。
- **WASM 运行时边界：** 对外只承诺执行受支持的 WASM32 二进制输入。源码编译工具链不是当前产品范围。当前记录的 WebAssembly 支持范围只覆盖已验证的 i32 子集。
