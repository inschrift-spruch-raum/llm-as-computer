# transturing

**v0.2.0**

面向 transformer 推理循环的 WASM32 执行器运行时。`transturing` 解析 WASM 二进制模块,对齐验证后在纯 Python 解释器中逐步执行,输出结构化的运行时执行追踪 (execution trace)。追踪结果可直接喂入 transformer 的训练或推理管线。

## 特性

- 纯 Python 实现,核心依赖 PyTorch >= 2.0
- 完整的 WASM 二进制解析器,支持 LEB128 编解码
- 模块验证阶段,将原始二进制结构转化为执行契约
- 逐步执行,每条指令产生一个 `TraceStep` 记录
- 运行时追踪输出 `Trace`,包含完整的操作码、参数、栈指针和栈顶值
- 仅支持 i32 值类型子集,精简且专注

## 支持范围

### 支持的 WASM Section

| Section | 说明 |
|---------|------|
| Type (1) | 函数类型签名 |
| Function (3) | 函数索引到类型的映射 |
| Memory (5) | 线性内存声明 |
| Export (7) | 函数和内存导出 |
| Code (10) | 函数体字节码 |
| Custom (0) | 自定义段 (跳过内容) |

### 不支持的 WASM Section

Import (2), Table (4), Global (6), Start (8), Element (9), Data (11), Data Count (12)。模块中包含以上任一段时,解析阶段会直接报错。

### 值类型

仅支持 `i32`。`i64`, `f32`, `f64`, `v128` 均不支持。

### 支持的指令

**算术运算**

`i32.add`, `i32.sub`, `i32.mul`, `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u`

**比较运算**

`i32.eqz`, `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`, `i32.gt_u`, `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u`

**位运算**

`i32.and`, `i32.or`, `i32.xor`

**移位运算**

`i32.shl`, `i32.shr_s`, `i32.shr_u`, `i32.rotl`, `i32.rotr`

**一元运算**

`i32.clz`, `i32.ctz`, `i32.popcnt`

**内存操作**

`i32.load`, `i32.load8_s`, `i32.load8_u`, `i32.load16_s`, `i32.load16_u`, `i32.store`, `i32.store8`, `i32.store16`

**局部变量**

`local.get`, `local.set`, `local.tee`

**控制流**

`block`, `loop`, `if`, `else`, `end`, `br`, `br_if`, `br_table`

**其他**

`call`, `return`, `select`, `nop`, `drop` (内部编码为 `POP`), 常量压栈 (`i32.const`, 内部编码为 `PUSH`)

## 安装

要求 Python >= 3.14,核心依赖 PyTorch >= 2.0。构建系统使用 hatchling。

```bash
uv sync --group dev
```

## 快速开始

```python
from transturing import TorchExecutor, Trace
from transturing.wasm_binary import parse_wasm_binary, parse_wasm_file
from transturing.wasm_contract import validated_module_from_binary

# 方式一: 从文件解析
binary_module = parse_wasm_file("example.wasm")

# 方式二: 从字节解析
# binary_module = parse_wasm_binary(raw_bytes)

# 验证并构建执行模块
module = validated_module_from_binary(binary_module)

# 创建执行器并运行
executor = TorchExecutor()
trace = executor.execute_wasm(module, args=[10, 20])

# 查看执行追踪
print(trace.format_trace())

# 也可以编程方式读取每一步
for i, step in enumerate(trace.steps):
    print(f"步骤 {i}: op={step.op} arg={step.arg} sp={step.sp} top={step.top}")

# 将追踪转为 token 序列 (用于 transformer 输入)
tokens = []
for step in trace.steps:
    tokens.extend(step.tokens())
```

## 架构概览

```
WASM 二进制文件
      |
      v
parse_wasm_binary()          -- 二进制解析: 魔数校验, 版本校验, 段遍历, LEB128 解码
      |
      v
WasmBinaryModule             -- 原始结构化模块: 类型表, 函数列表, 内存声明, 导出表
      |
      v
validated_module_from_binary()  -- 契约构建: 函数签名提取, 入口函数自动检测
      |
      v
ValidatedWasmModule          -- 已验证模块: 执行契约, 函数体, 参数/局部变量数量
      |
      v
TorchExecutor.execute_wasm() -- 逐步执行: 栈式解释器, 操作码分派, 追踪记录
      |
      v
Trace                        -- 执行追踪: TraceStep 列表, 可格式化输出或转为 token
```

核心模块说明:

| 模块 | 职责 |
|------|------|
| `wasm_binary` | WASM 二进制格式解析, 包含 `parse_wasm_binary` 和 `parse_wasm_file` |
| `wasm_contract` | 模块验证与契约构建, 定义 `ValidatedWasmModule` 和 `WasmFunctionContract` |
| `executor` | 栈式解释器, 包含 `TorchExecutor` 及全部指令分派逻辑 |
| `opcodes` | 操作码常量定义, 操作码到名称的映射 |
| `wasm_math` | WASM 语义的数学运算实现 (截断除法, 循环移位, 前导零计数等) |
| `trace` | 追踪数据结构: `Trace`, `TraceStep`, `WasmInstr` 类型别名 |

## API 参考

### 公共 API (`transturing`)

#### `TorchExecutor`

执行器主类, 实现了 `WasmDirectExecutor` 协议。

```python
class TorchExecutor:
    def execute_wasm(
        self,
        module: ValidatedWasmModule,
        *,
        args: list[int] | None = None,
        max_steps: int = 50000,
    ) -> Trace
```

**参数:**

- `module` -- 已验证的 WASM 模块, 由 `validated_module_from_binary()` 生成
- `args` -- 入口函数的参数列表, 默认为空
- `max_steps` -- 最大执行步数, 防止无限循环, 默认 50000

**返回:** `Trace` 对象, 包含完整的执行追踪。

#### `Trace`

执行追踪的容器。

```python
@dataclass
class Trace:
    program: list[object]
    steps: list[TraceStep]

    def format_trace(self) -> str
```

- `program` -- 预留的程序描述字段
- `steps` -- 执行步骤列表
- `format_trace()` -- 将追踪格式化为可读的表格字符串

#### `TraceStep`

单步执行记录。

```python
@dataclass
class TraceStep:
    op: int    # 操作码 (参见 opcodes.py)
    arg: int   # 操作数 (如 PUSH 的值, LOCAL.GET 的索引, CALL 的函数索引)
    sp: int    # 执行后的栈指针位置
    top: int   # 执行后的栈顶值

    def tokens(self) -> list[int]
```

`tokens()` 返回 `[op, arg, sp, top]` 四元组, 可直接用作 transformer 的 token 输入。

### 解析 API (`transturing.wasm_binary`)

#### `parse_wasm_binary(data: bytes | bytearray | memoryview) -> WasmBinaryModule`

从原始字节解析 WASM 二进制模块。会校验魔数 (`\x00asm`) 和版本号 (1), 按顺序遍历各段。遇到不支持的段或不支持的值类型时抛出 `WasmBinaryDecodeError`。

#### `parse_wasm_file(path: str | Path) -> WasmBinaryModule`

从文件路径读取并解析 WASM 模块, 内部调用 `parse_wasm_binary`。

#### `auto_detect_function(module: WasmBinaryModule) -> WasmFunction`

自动检测入口函数。优先选择第一个非样板导出函数 (排除 `memory`, `__stack_high` 等链接器生成的符号), 若无导出则回退到函数索引 0。

### 验证 API (`transturing.wasm_contract`)

#### `validated_module_from_binary(module: WasmBinaryModule) -> ValidatedWasmModule`

将解析后的二进制模块转换为验证后的执行契约。提取每个函数的参数数量、结果数量、局部变量数量, 并自动检测入口函数。

#### `ValidatedWasmModule`

已验证的模块数据结构, 包含函数契约列表、内存契约和入口函数索引。

#### `WasmDirectExecutor`

执行器协议 (Protocol), 定义了 `execute_wasm` 方法签名。`TorchExecutor` 实现了此协议。

### 数据结构

#### `WasmBinaryModule`

```python
@dataclass(frozen=True)
class WasmBinaryModule:
    types: list[WasmFunctionType]
    functions: list[WasmFunction]
    memories: list[WasmMemory]
    exports: list[WasmExport]
```

#### `WasmFunction`

```python
@dataclass(frozen=True)
class WasmFunction:
    index: int
    type_index: int
    params: list[str]
    results: list[str]
    locals: list[str]
    body: list[WasmInstr]
    export_names: list[str]
```

#### `WasmFunctionType`

```python
@dataclass(frozen=True)
class WasmFunctionType:
    params: list[str]
    results: list[str]
```

#### `WasmExport`

```python
@dataclass(frozen=True)
class WasmExport:
    name: str
    kind: str       # "func" 或 "memory"
    index: int
```

## 开发

### 开发依赖

- `pytest >= 9.0.2` -- 测试框架
- `ruff >= 0.8` -- 代码格式化和 lint
- `basedpyright >= 1.39.0` -- 严格类型检查

### 运行测试

```bash
pytest
```

### 代码检查

```bash
ruff check .
ruff format --check .
```

### 类型检查

```bash
basedpyright
```

项目配置了严格的类型检查模式 (`typeCheckingMode = "strict"`), 目标 Python 版本为 3.14。
