# transturing 文档

> 面向受支持 WASM32 字节输入的 transformer 运行时。用户提供 `.wasm` 二进制模块，运行时在 transformer 自身的推理循环中执行它。每条取指和内存读取都是一个抛物线注意力头。transformer **就是** 计算机。

本项目独立验证了 [Percepta 的声明](https://percepta.ai/blog/can-llms-be-computers): 通过 2D 凸包注意力实现 O(log t) 的每步解码, transformer 能够执行任意程序。经过 20 个研究阶段的探索，核心结论是“编译而非训练”：**执行器的寻址/路由逻辑**需要通过解析方式写入模型结构。当前公开产品边界是**执行受支持的 WASM32 二进制输入，返回运行时轨迹与结果**。内部 55 操作码表示仍存在，但属于实现细节；源码编译、C toolchain 和面向用户的私有 ISA 编写 helper 都不在支持范围内。

## 关键数据

| 指标 | 值 |
|------|-----|
| ISA 操作码数 | 55 (WASM 风格栈机) |
| 模型维度 | d_model=51, head_dim=2 |
| 编译参数量 | ~2656 |
| 注意力机制 | Hard-max (argmax), 禁止 softmax |
| 数值精度 | Float64 (强制) |
| 后端 | Python (PyTorch/NumPy) |
| 研究阶段 | 20 个, 全部完成 |
| Python 执行速度 | 2.1-3.1M steps/sec |

## 文档导航

### 快速开始

| 文档 | 说明 |
|------|------|
| [快速开始](quickstart.md) | 新的运行时契约、安装与执行 `.wasm` 模块 |

### 架构文档

| 文档 | 说明 |
|------|------|
| [架构概览](architecture/overview.md) | 整体设计: 抛物线编码、注意力头、内存空间 |
| [内存模型](architecture/memory-model.md) | 五大内存空间的寻址机制 |
| [编译流程](architecture/compilation.md) | 执行器权重的编译过程, 以及程序如何降到 ISA |

### 内部实现 / 研究参考

| 文档 | 说明 |
|------|------|
| [程序编写](guides/writing-programs.md) | 以 `.wasm` bytes 执行为主线，附带内部实现背景 |
| [完整 ISA 参考](isa/index.md) | 55 个操作码的内部执行表示索引 |
| [操作码详解](isa/opcodes.md) | 每个操作码的语义、参数和执行行为 |

### 使用指南

| 文档 | 说明 |
|------|------|
| [工作原理](guides/how-it-works.md) | 逐步跟踪一个 4 指令程序的执行 |

### 开发文档

| 文档 | 说明 |
|------|------|
| [关键发现摘要](development/findings-summary.md) | 20 个研究阶段的核心结论 |
| [R&D 计划摘要](development/rd-plan-summary.md) | 研发路线图与各阶段演进 |

### 参考文档

| 文档 | 说明 |
|------|------|
| [API 参考](reference/api.md) | 包根公开 API 与保留的 WASM bytes ingestion helper 说明 |
| [文件地图](reference/file-map.md) | 仓库文件结构与职责 |

### 其他

| 文档 | 说明 |
|------|------|
| [变更日志](CHANGELOG.md) | 版本变更记录 |
| [贡献指南](contributing.md) | 如何参与本项目 |

## 阅读指南

### 新手入门

如果你第一次接触这个项目, 建议按以下顺序阅读:

1. **[快速开始](quickstart.md)**, 先理解新的运行时契约、安装步骤与 `.wasm` 执行方式
2. **[工作原理](guides/how-it-works.md)**, 理解 transformer 如何"变成"计算机
3. **[架构概览](architecture/overview.md)**, 了解整体设计思路

### 开发者

如果你想在项目中写代码:

1. **[架构概览](architecture/overview.md)**, 理解核心机制
2. **[编译流程](architecture/compilation.md)**, 了解执行器权重如何编译出来
3. **[程序编写](guides/writing-programs.md)**, 查看 `.wasm` bytes 执行入口与内部实现补充
4. **[API 参考](reference/api.md)**, 查阅具体接口
5. **[文件地图](reference/file-map.md)**, 快速定位代码位置

### 研究者

如果你关注技术细节和研究结论:

1. **[关键发现摘要](development/findings-summary.md)**, 了解"编译优于训练"的实验证据
2. **[内存模型](architecture/memory-model.md)**, 抛物线编码和五大内存空间的技术细节
3. **[完整 ISA 参考](isa/index.md)**, 55 个操作码的内部定义
4. **[R&D 计划摘要](development/rd-plan-summary.md)**, 20 个研究阶段的演进路线

## 相关博文

- **[Yes, LLMs Can Be Computers. Now What?](https://muninn.austegard.com/blog/yes-llms-can-be-computers-now-what)**, 13 个阶段验证的完整叙述, 包括训练路线上的弯路和最终的突破
- **[The Free Computer: Why Offloading to CPU Is a Win for Everyone](https://muninn.austegard.com/blog/the-free-computer-why-offloading-to-cpu-is-a-win-for-everyone)**, 编译型 CPU 执行的经济学论点

## 返回

[返回项目主页](../README.md)
