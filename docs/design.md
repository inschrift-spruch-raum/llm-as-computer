# transturing 设计文档

本文档仅基于当前仓库中的现有代码整理，不参考任何 git 提交历史。

## 1. 项目定位

`transturing` 是一个 Python 库，用于执行一套面向 WASM32 `i32` 子集的栈机运行时。其核心目标不是提供通用 WebAssembly 虚拟机，而是把一组受限的 WebAssembly 二进制或内部 `Instruction` 程序，转换为统一的执行模型，并输出完整执行轨迹 `Trace`。

从项目元数据可以看到这一定位：`pyproject.toml` 将项目描述为“executor-only transformer runtime for supported WASM32 bytes”，并且运行时依赖默认为空，`numpy` 和 `torch` 被作为可选后端依赖提供。

## 2. 顶层结构

仓库结构可以概括为四部分：

- `src/transturing/`：主包实现。
- `src/transturing/core/`：与后端无关的核心抽象、ISA、程序构造器、后端注册机制、WASM 二进制解析与降低逻辑。
- `src/transturing/backends/`：具体执行后端，当前包含 `numpy` 与 `torch` 两条实现路径。
- `tests/`：围绕执行正确性、跨后端一致性、WASM 二进制入口的回归测试。

根目录中的 `pyproject.toml` 表明：

- 构建系统使用 `hatchling`
- Python 版本要求为 `>=3.14`
- 开发工具为 `pytest`、`ruff`、`basedpyright`
- 包本身没有必选运行时依赖

## 3. 公共 API

包根入口位于 `src/transturing/__init__.py`。当前导出的公共接口很小，说明这个库强调“统一执行入口”，而不是大而散的表面 API：

- `Trace`
- `TraceStep`
- `get_executor`
- `list_backends`

也就是说，从使用者视角，最核心的交互方式是：

1. 获取一个执行器实例
2. 传入一段 `Instruction` 程序
3. 读取返回的完整 `Trace`

这一点由 `src/transturing/core/abc.py` 中的抽象接口进一步固定：所有后端都必须实现 `execute(self, prog: list[Instruction], max_steps: int = 50000) -> Trace`。

需要注意的是，WASM 相关入口虽然在代码中明确存在，但**没有被包根直接 re-export**。当前若要使用 WASM 摄入能力，需要从 `transturing.core.wasm_binary` 显式导入 `compile_wasm_module()`、`compile_wasm()` 或 `parse_wasm_binary()`；从现有代码看，它们属于“模块级公开能力”，但不是包根四个顶层导出的一部分。

## 4. 核心抽象层

### 4.1 `Instruction`、`TraceStep` 与 `Trace`

`src/transturing/core/isa.py` 定义了整个系统的基础数据模型：

- `Instruction`：单条指令，包含 `op` 和 `arg`
- `TraceStep`：一次指令执行后的记录，包含 `op`、`arg`、执行后 `sp`、执行后 `top`
- `Trace`：完整执行轨迹，包含原始程序 `program` 与逐步的 `steps`

这套设计有两个明显特点：

1. **执行语义被压缩成可对比的离散轨迹。** 这使得不同后端可以只要产生相同 `Trace`，就视为行为一致。
2. **用户看到的是“运行过程”，不只是最终结果。** 例如测试中会直接比较最后一步 `top`，也会进行 NumPy/Torch 两条路径的整条 trace 对比。

### 4.2 ISA 定义

`isa.py` 是整个仓库中最核心的协议文件。它不仅声明了 55 个 opcode，还定义了：

- 指令名称映射 `OP_NAMES`
- opcode 到嵌入维度的映射 `OPCODE_DIM_MAP`
- 统一的位运算、移位、截断除法、截断取模等帮助函数
- `program()` 这个从 tuple 形式构造 `Instruction` 列表的构造器

从常量可见，这套 ISA 覆盖了：

- 栈基本操作：`PUSH`、`POP`、`DUP`
- 算术：`ADD`、`SUB`、`MUL`、`DIV_S`、`DIV_U`、`REM_S`、`REM_U`
- 比较：`EQZ`、`EQ`、`NE`、`LT_*`、`GT_*`、`LE_*`、`GE_*`
- 位操作：`AND`、`OR`、`XOR`、`SHL`、`SHR_*`、`ROTL`、`ROTR`
- 一元与参数化操作：`CLZ`、`CTZ`、`POPCNT`、`ABS`、`NEG`、`SELECT`
- 局部变量：`LOCAL.GET`、`LOCAL.SET`、`LOCAL.TEE`
- 线性内存：`I32.LOAD*`、`I32.STORE*`
- 调用栈：`CALL`、`RETURN`
- 控制流：`JZ`、`JNZ`、`HALT`
- 异常终止：`TRAP`

其中 `OP_TRAP = 99` 的角色和其他 opcode 略有不同：它被用于表示运行时陷阱事件，但不属于 `1..55` 这一组常规执行 opcode 的连续编号集合。现有代码里，Torch 词表会单独为 `TRAP` 分配 token，而正常程序分发与建模主要围绕前 55 个常规 opcode 展开。

### 4.3 为什么 `isa.py` 同时包含执行协议和嵌入布局

`isa.py` 里除了运行时 opcode，还有 `D_MODEL = 51` 以及大量 `DIM_*` 常量。说明这份文件既服务于普通解释执行，也服务于 Torch 后端里的“编译 transformer”实现。换言之，这个库不是简单提供两套完全独立的执行器，而是让两条路径共享同一个抽象指令集与状态表示协议。

这使得：

- NumPy 后端可以作为更直观的参考实现
- Torch 后端可以把同一协议编码进 embedding / attention / state update 里
- 测试可以在统一语义层上比较两者输出

## 5. 后端发现与实例化

`src/transturing/core/registry.py` 负责后端注册与发现。

设计上采用了一个很轻量的插件式机制：

- `register_backend(cls)` 装饰器把后端类注册到 `_REGISTRY`
- `_discover()` 尝试导入 `transturing.backends.torch_backend` 与 `transturing.backends.numpy_backend`
- `get_executor(name=None)` 在未显式指定时，按 `torch > numpy` 的优先级自动选后端
- `list_backends()` 返回当前成功可用的后端名

这里的关键点是：

1. **导入驱动注册。** 后端模块只要可导入，类定义上的装饰器就会完成注册。
2. **后端是可选依赖。** `_discover()` 捕获 `ImportError`，因此未安装某个后端依赖不会破坏整个包的可用性。
3. **自动选择优先 Torch。** 这与项目定位相符：Torch 路径并不是附属实验品，而是优先实现。

## 6. NumPy 后端：参考解释器

`src/transturing/backends/numpy_backend.py` 实现 `NumPyExecutor`。从代码结构看，它承担的是“可直接理解、可逐条对应 ISA 语义”的参考后端角色。

### 6.1 状态模型

执行状态由内部 `_ExecCtx` 持有，主要包括：

- `ip`：指令指针
- `sp`：栈指针
- `stack`：栈存储
- `locals_store`：局部变量存储
- `heap`：线性内存存储
- `call_stack`：调用帧栈
- `locals_base`：当前函数的局部变量基址
- `trace`：执行输出

### 6.2 Parabolic Store

NumPy 路径最特殊的点是 `_ParabolicStore`。它不是普通数组，而是把地址写成二维 key：

- 写入时记录 `(2 * addr, -addr² + eps * write_count)`
- 读取时用查询向量 `[addr, 1.0]` 做点积，再 `argmax`

这让“按地址读取最近写入值”可以表示成一种 attention 式检索。这一点非常关键，因为 Torch 后端也在做类似的 embedding + 选择逻辑。可以把 NumPy 路径理解成：**用显式数值计算模拟同一类可检索内存机制**。

### 6.3 执行流程

`NumPyExecutor.execute()` 的主循环非常直接：

1. 从 `prog[ip]` 取出 `op` 和 `arg`
2. 预设 `next_ip = ip + 1`
3. 按 `_DISPATCH` 查找处理函数
4. 处理函数更新状态并追加 `TraceStep`
5. 若遇到 halt/trap 则退出，否则令 `ip = next_ip`

各类 handler 对应 ISA 语义分组：

- `_handle_push/_pop/_dup`
- `_handle_add_sub`
- `_handle_stack_manip`
- `_handle_arithmetic`
- `_handle_comparison`
- `_handle_bitwise`
- `_handle_unary`
- `_handle_select`
- `_handle_local_ops`
- `_handle_memory_ops`
- `_handle_call/_return`
- `_handle_branch/_halt`

### 6.4 错误与陷阱语义

NumPy 后端通过追加 `TraceStep(OP_TRAP, ...)` 的方式表示 trap，例如除零和空调用栈返回。这样 trap 也被建模为轨迹事件，而不是 Python 异常。这与整个系统“返回可比较 trace”的设计目标保持一致。

## 7. Torch 后端：编译型 transformer 执行器

`src/transturing/backends/torch_backend.py` 是仓库里最具辨识度的实现。它并不是简单用 PyTorch 重写解释器，而是把执行语义编码成一个确定性的模型结构。

这里要特别区分两条后端路径的性质：

- `NumPyExecutor` 更像一个参考解释器，逐条执行 opcode，并用可计算的 parabolic addressing 模拟内容寻址内存。
- `TorchExecutor` 则是把同一套语义编码进 transformer 风格的 embedding、attention 和解析式权重中，再通过逐步前向推理得到每一步结果。

因此，这两者不是“同一实现换了个张量库”，而是**两种架构上不同、但语义目标相同的执行方案**。

### 7.1 主要组成

该文件定义了几个层次：

- `CompiledAttentionHead`：硬最大值 attention 头
- `TokenVocab`：token 词表及解析式 embedding/unembedding 构造
- 一组 `embed_*` 函数：把程序 token、栈、局部变量、堆、调用帧、状态编码到共享向量空间
- `CompiledModel`：完整的编译模型
- `TorchExecutor`：用 `CompiledModel` 驱动逐步执行并生成 `Trace`

### 7.2 统一的向量空间

Torch 路径严格依赖 `isa.py` 中的维度定义，例如：

- 程序位置信息：`DIM_PROG_KEY_*`
- 栈地址：`DIM_STACK_KEY_*`
- 局部变量地址：`DIM_LOCAL_KEY_*`
- 堆地址：`DIM_HEAP_KEY_*`
- 调用帧字段：`DIM_CALL_*`
- 当前状态：`DIM_IP`、`DIM_SP`

这说明模型不是“学到”解释规则，而是把规则解析式地写进 embedding 和线性层权重中。

### 7.3 `TokenVocab` 的角色

`TokenVocab` 把系统 token 分成四类：

- `SPECIAL`
- `OPCODE`
- `VALUE`
- `SP_DELTA`

同时提供：

- `encode()` / `decode()`
- `compile_embedding()`
- `compile_unembedding()`

因此它既是符号字典，也是构建模型参数的一部分。程序 token、数值 token 和状态 token 最终被编码到同一维度空间中，供 `CompiledModel` 使用。

### 7.4 `CompiledModel` 的职责

从类结构和方法命名可见，`CompiledModel` 负责：

- 编译 attention 头参数
- 从程序 embedding 和内存 embedding 中读取当前指令与相关值
- 生成当前步的 `opcode`、`arg`、`sp_delta`、`top` 等结果
- 以解析方式计算非线性运算分支

也就是说，`CompiledModel.forward()` 并不是训练推理接口，而是“单步语义求值器”。

### 7.5 `TorchExecutor` 的运行流程

`TorchExecutor.execute()` 的主循环和 NumPy 后端在外部行为上对齐，但内部步骤不同：

1. 把整个程序预编为 `prog_embs`
2. 初始化 `_ExecState`
3. 每一步基于 `(ip, sp)` 生成 `query = embed_state(...)`
4. 组合当前 memory embeddings
5. 调用 `_forward_step()` 执行一次模型前向
6. 按结果处理 halt、trap、call、return 或普通写回
7. 更新 `sp` 与 `ip`，并附加 `TraceStep`

其中 `_apply_memory_writes()` 会把更新结果重新编码为 stack/local/heap embeddings；`_handle_call()` 和 `_handle_return()` 则显式维护调用栈及其 embedding。

这说明 Torch 后端虽然使用模型表达，但**运行时控制循环仍在 Python 中**，不是一次性把整段程序全部 rollout 完毕。

## 8. WASM 二进制入口

`src/transturing/core/wasm_binary.py` 提供从原始 `.wasm` 字节到内部 `Instruction` 的完整通路。

### 8.1 支持范围

模块头部文档字符串已经写得很明确：当前只支持一个收窄的 MVP WebAssembly 子集，重点是：

- 模块头 / 版本
- `type`、`function`、`memory`、`export`、`code` section
- `i32` 类型的函数签名、locals 与指令体
- 结构化控制流 `BLOCK / LOOP / IF / ELSE / END`
- 调用、分支、i32 算术 / 比较 / 位运算、参数化操作
- i32 线性内存操作

显式拒绝的内容包括：

- imports、tables、globals、start、element/data segments 等
- 非 `i32` 类型
- 不能表示成内部 `WasmInstr` 的 opcode 或二进制特性
- 非零 offset 的 memory op
- 非空 block signature

### 8.2 解码输出的数据结构

WASM 解码并不直接产出扁平程序，而是先构建结构化表示：

- `WasmFunctionType`
- `WasmMemory`
- `WasmExport`
- `WasmFunction`
- `WasmBinaryModule`

这让模块验证、导出函数选择、结构化控制流降低等步骤可以分层完成。

### 8.3 结构化控制流降低

内部类 `_StructuredControlFlowLowerer` 负责把结构化的 WASM 控制流标记，降低成当前运行时可执行的平面跳转指令。关键行为包括：

- 为 block / loop / if / else / end 分配和解析标签
- 把 `BR` / `BR_IF` / `BR_TABLE` 转换成内部跳转序列
- 生成适用于当前 ISA 的平面 `Instruction` 列表

因此，这个仓库的控制流策略是：**先保留 WASM 的结构，再在进入执行器前做一次内部 lowering**。

### 8.4 编译路径

对外最关键的入口是 `compile_wasm_module()`：

1. `parse_wasm_binary(data)` 解码模块
2. `_validate_supported_module(module)` 检查功能边界
3. 若指定 `func_name`，按导出名取函数；否则自动选第一个非样板导出函数
4. 单函数模块走 `compile_wasm_function()`
5. 多函数模块走 `_compile_module_functions()`，把入口函数和其他函数链接到一段扁平 ISA 程序

这里实际上存在一个很重要的分叉：

- **单函数模块**：直接把目标函数降低为内部程序，并确保终止指令为 `HALT`。
- **多函数模块**：先分别编译所有函数体，再用 `_compile_module_functions()` 构造统一入口、重写 `CALL` 目标地址，并以 `RETURN` 作为函数体内部终止语义，最后拼出一段可整体执行的平面程序。

`_compile_module_functions()` 的实现表明，链接后的平面程序采用：

- 开头插入 `CALL entry`
- 紧跟 wrapper 里的 `HALT`
- 后续顺序拼接各函数体
- 调整内部 `CALL` 目标地址
- 最后附加一个 `HALT`

这是一种很直接但清晰的“单段程序 + 显式调用地址”链接模型。

### 8.5 参数与 locals 约定

`_with_param_local_setup()` 展示了运行时对函数参数与额外 locals 的约定：

- 额外 locals 先初始化为 0
- 调用前已经压到栈上的参数，按从后到前的顺序弹出并写入 parameter locals

这个约定对于文档和使用者都很重要，因为它解释了为何测试里在执行编译后的 wasm 程序前，会手动用 `Instruction(OP_PUSH, arg)` 前缀压入参数。

## 9. 程序构造器与内建测试程序

`src/transturing/core/programs.py` 提供了大量程序生成函数，它们本质上承担两种职责：

1. 为测试提供回归样例
2. 作为这套 ISA 的“可执行示例库”

其中包含：

- 基础栈机程序，如 `test_basic()`、`test_push_pop()`
- 算法程序，如 `make_fibonacci()`、`make_sum_1_to_n()`、`make_multiply()`
- 原生 opcode 程序，如 `make_native_multiply()`、`make_factorial()`、`make_gcd()`
- 比较、位运算、一元运算、`SELECT` 等构造函数

这里非常有价值的一点是：这些函数通常返回 `(prog, expected)`，因此既是样例生成器，也是规格说明的一部分。

## 10. 测试体系

### 10.1 `tests/test_consolidated.py`

该文件覆盖三类关键目标：

- NumPy 后端正确性
- Torch 后端正确性
- 两个后端之间的 trace parity

测试内容覆盖面很广，包括：

- 基础栈机程序
- 控制流程序
- 算法程序
- 算术、比较、位运算、一元操作、`SELECT`
- trap 行为
- NumPy/Torch 的整条 trace 对比

其中 `compare_traces()` 被用于验证两个后端不仅最终栈顶一致，而且逐步轨迹也一致。这个事实说明“trace 一致性”是该项目的核心正确性标准之一。

### 10.2 `tests/test_wasm_binary.py`

该文件从另一个维度验证系统：不是直接喂 `Instruction`，而是先构造 `.wasm` 字节，再验证解码和执行。

它覆盖了：

- 支持子集的正向解码
- loop / locals / branch / `br_table` / 多函数调用图 / 参数调用图
- memory width 变体
- `parse_wasm_file()` 的文件路径入口
- 各种明确拒绝的场景，比如非零 memarg offset、非空 block type、非支持 opcode 家族等

此外，`_run_binary_program()` 会将 `compile_wasm_module()` 的结果同时送入 `NumPyExecutor` 与 `TorchExecutor`，说明 WASM 入口最终仍然收敛到统一的内部执行协议。

### 10.3 `tests/conftest.py`

这里的策略很务实：

- 若缺少 `numpy`，自动跳过 NumPy 相关测试
- 若缺少 `torch`，自动跳过 Torch 相关测试

这和前面“后端是可选依赖”的设计保持一致，保证核心仓库即使在不同依赖环境中也能有可预测测试行为。

## 11. 运行流程总结

从当前代码看，仓库存在两条输入路径，但会汇合到同一个执行协议：

### 路径 A：直接执行内部程序

1. 调用方构造 `list[Instruction]`
2. 通过 `get_executor()` 或直接实例化某个后端拿到执行器
3. 调用 `execute(prog)`
4. 获取 `Trace`

### 路径 B：执行受支持的 WASM 二进制

1. 调用 `compile_wasm_module()` / `compile_wasm()` 解析 `.wasm`
2. 选择目标函数并降低成内部 `Instruction` 列表
3. 必要时在程序前压入参数
4. 调用执行器 `execute(prog)`
5. 获取 `Trace`

统一点在于：**最终所有执行都落到相同的 `Instruction -> Trace` 契约。**

## 12. 当前设计的特点与边界

基于现有代码，可以明确看出以下设计特点：

### 12.1 优点

- **核心协议统一**：直接程序与 WASM 降低程序都落入同一 ISA。
- **双后端可比对**：NumPy 参考实现与 Torch 编译实现共享同一语义层。
- **trace-first**：输出完整轨迹，有利于验证、调试和后端 parity。
- **边界明确**：WASM 支持范围写在代码与测试中，拒绝条件可预测。
- **依赖可选**：后端按需发现，不强迫用户安装全部数值库。

### 12.2 当前边界

- 不是完整 WASM 运行时，只支持受限 `i32` 子集。
- 不是 CLI 工具，当前仅暴露库接口，没有 `__main__` 或脚本入口。
- Torch 后端虽然实现了“编译 transformer”语义，但执行主循环仍由 Python 驱动。
- `pyproject.toml` 指向 `README.md`，但当前仓库根目录中未看到该文件；这不会影响本文档结论，但说明包元数据引用的说明文件可能尚未落地或未包含在当前工作树中。

## 13. 面向维护者的阅读顺序建议

如果要继续维护这个仓库，建议按下面顺序阅读：

1. `src/transturing/__init__.py`：先理解公开 API 很小这一设计取向。
2. `src/transturing/core/abc.py`：看统一执行器接口。
3. `src/transturing/core/isa.py`：理解核心指令模型与 trace 协议。
4. `src/transturing/core/registry.py`：理解后端发现策略。
5. `src/transturing/backends/numpy_backend.py`：先从参考解释器读懂语义。
6. `src/transturing/backends/torch_backend.py`：再看如何把同一语义编码为 transformer 风格实现。
7. `src/transturing/core/wasm_binary.py`：最后看 WASM 如何被约束、解析、降低并链接成内部程序。
8. `tests/`：用测试确认哪些行为被视为当前规格的一部分。

## 14. 一句话总结

`transturing` 当前代码实现的是：**一个以统一 ISA 和执行轨迹为中心、同时提供 NumPy 参考解释器与 Torch 编译型执行器、并支持受限 WASM 二进制摄入的实验性运行时库。**
