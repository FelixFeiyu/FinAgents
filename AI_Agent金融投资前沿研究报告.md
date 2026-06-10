# AI Agent 在金融投资领域的前沿研究报告（2025-2026）

> 调研日期：2026-06-10  
> 收录范围：仅收录首次发布于 **2025 年或 2026 年**、与投资研究、资产配置、交易决策或金融 Agent 评测直接相关的论文。  
> 重要提醒：多数成果仍是 arXiv 预印本，尚未经过长期实盘和顶级期刊同行评审；本文不构成投资建议。

## 一、结论摘要

2025-2026 年，AI Agent 金融投资研究正在从“让 LLM 给出买卖建议”转向更严格的系统研究：

1. **细粒度多智能体工作流**：不再只模拟分析师、交易员等角色，而是将真实投研流程拆成可检查的细任务。
2. **实时、无数据污染评测**：让 Agent 在实时市场中自主搜索和决策，减少历史数据已进入训练集造成的虚假优势。
3. **可审计金融研究 Agent**：评测重点从最终答案转向来源、定义、假设、计算过程和完整推导。
4. **推理模型与强化学习交易**：通过监督微调和强化学习，让模型形成结构化投资论点和风险调整决策。
5. **多模态与高频 Agent**：结合新闻、财报、K 线、技术指标等数据，但相关收益主张仍缺少独立复现。
6. **Agent 风险与治理**：研究自主 Agent 对市场稳定、监管、可解释性和系统性风险的影响。

当前最可靠的结论不是“Agent 已经能稳定战胜市场”，而是：

- 现有 Agent 在真实金融研究任务上的正确率仍明显不足；
- 风控能力比通用模型能力更能决定跨市场稳健性；
- 工作流拆解、可靠工具调用和可审计推导，是比增加角色数量更重要的研究方向；
- 公开成果主要是预印本，2025/2026 年尚缺乏高引用、顶级金融期刊发表且经过长期实盘验证的投资 Agent 研究。

## 二、重点论文清单

### 2.1 2026 年论文

| 论文 | 时间与机构/作者背景 | 核心贡献 | 可信度与局限 |
|---|---|---|---|
| [Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks](https://arxiv.org/abs/2602.23330) | 2026-02；作者包括牛津大学机器学习与量化金融研究者 Stefan Zohren、Stephen Roberts | 将投资分析拆成细粒度任务，在日本股票、多源数据和泄漏控制回测中，对比粗粒度多 Agent 设计；发现中间分析与下游决策偏好的一致性很关键 | **2026 年最值得跟踪的交易 Agent 论文之一**；实验设计比角色模拟更严谨，但仍是预印本和历史回测 |
| [Agentic Artificial Intelligence in Finance: A Comprehensive Survey](https://arxiv.org/abs/2604.21672) | 2026-04；综合综述 | 系统讨论 Agentic AI 的金融架构、市场应用、监管框架和系统性风险 | 适合作为 2026 年研究入口；属于综述，不证明具体策略有效 |
| [BigFinanceBench: A Workflow-Grounded Benchmark for Financial-Research Agents](https://arxiv.org/abs/2606.03829) | 2026-06；专家编写的金融研究 Agent 基准 | 提供 928 个开放式金融研究任务和 36,241 个可评分推导步骤；最佳系统仅达到 58.8% rubric 得分 | **非常前沿的可审计评测方向**；关注投研过程而非交易收益，发布较新，尚待广泛复现 |

### 2.2 2025 年论文

| 论文 | 时间与机构/作者背景 | 核心贡献 | 可信度与局限 |
|---|---|---|---|
| [AI-Trader: Benchmarking Autonomous Agents in Real-Time Financial Markets](https://arxiv.org/abs/2512.10971) | 2025-12；香港大学数据智能实验室相关团队 | 构建覆盖美股、A 股和加密资产的实时、自动化、低数据污染评测；Agent 需自主搜索、验证和综合市场信息 | **最重要的实时交易 Agent 基准之一**；结果显示多数 Agent 收益和风控较弱，通用智能不等于交易能力 |
| [Finance Agent Benchmark: Benchmarking LLMs on Real-world Financial Research Tasks](https://arxiv.org/abs/2508.00828) | 2025；任务由银行、对冲基金和私募股权专家参与设计 | 537 个基于近期 SEC 文件的真实投研问题，Agent 可调用搜索与 EDGAR；最佳模型准确率仅 46.8%，平均每题成本 3.79 美元 | 对生产可用性具有直接参考价值；主要评测投研任务，不是组合收益 |
| [FinGAIA: A Chinese Benchmark for AI Agents in Real-World Financial Domain](https://arxiv.org/abs/2507.17186) | 2025-07；上海财经大学 AIFLM Lab 等 | 407 个端到端任务，覆盖证券、基金、银行、保险、期货、信托与资管；最佳 Agent 准确率 48.9%，落后专家超过 35 个百分点 | **中文金融 Agent 的重要基准**；揭示跨模态、术语和业务流程理解缺陷 |
| [LLM-Powered Multi-Agent System for Automated Crypto Portfolio Management](https://arxiv.org/abs/2501.00826) | 2025-01；作者包括伦敦大学学院相关研究者 Paolo Tasca 等 | 多模态、多智能体加密资产组合管理；使用团队内和团队间协作、置信度调整及实时数据 | 直接研究资产配置与组合；加密市场样本期较短，收益结果需独立复现 |
| [Trading-R1: Financial Trading with LLM Reasoning via Reinforcement Learning](https://arxiv.org/abs/2509.11420) | 2025-09；预印本/开源项目 | 通过监督微调和强化学习训练金融推理模型，生成结构化、证据支持、考虑波动率的投资论点 | 代表“推理模型 + RL 交易”方向；仅覆盖有限股票和 ETF，泛化能力待验证 |
| [QuantAgent: Price-Driven Multi-Agent LLMs for High-Frequency Trading](https://arxiv.org/abs/2509.09995) | 2025-09；预印本 | 将指标、形态、趋势和风险拆给不同 Agent，探索 LLM 在高频、短周期交易中的应用 | 方向新颖，但高频交易对延迟、费用和市场冲击极其敏感，回测优势不能直接外推至实盘 |
| [P1GPT: A Multi-Agent LLM Workflow Module for Multi-Modal Financial Information Analysis](https://arxiv.org/abs/2510.23032) | 2025-10；预印本 | 强调结构化推理流水线，而非简单角色模仿；融合技术面、基本面和新闻信息 | 结构化工作流设计值得关注；收益主张仍主要来自回测 |
| [MountainLion: A Multi-Modal LLM-Based Agent System for Interpretable and Adaptive Financial Trading](https://arxiv.org/abs/2507.20474) | 2025-07；预印本 | 结合新闻、K 线图、交易信号图及反思模块，生成可解释交易报告和建议 | 多模态交易 Agent 代表作；“改善收益”尚缺少独立实盘验证 |
| [QuantAgents: Towards Multi-agent Financial System via Simulated Trading](https://arxiv.org/abs/2510.04643) | 2025-10；预印本 | 结合新闻分析、交易、风控与基金经理 Agent，使用模拟交易研究协作效果 | 可用于寻找系统设计思路；强收益结论必须谨慎看待 |

## 三、优先精读排序

### 第一梯队：研究设计与评测最重要

1. [AI-Trader](https://arxiv.org/abs/2512.10971)：理解为何实时、无污染评测比传统回测更可信。
2. [Toward Expert Investment Teams](https://arxiv.org/abs/2602.23330)：理解细粒度任务拆解与 Agent 协作设计。
3. [BigFinanceBench](https://arxiv.org/abs/2606.03829)：理解如何评测可审计的金融研究过程。
4. [Finance Agent Benchmark](https://arxiv.org/abs/2508.00828)：了解 Agent 在真实 SEC 投研任务上的能力上限。
5. [FinGAIA](https://arxiv.org/abs/2507.17186)：了解中文金融业务场景中的 Agent 缺陷。

### 第二梯队：新型交易 Agent 架构

6. [Trading-R1](https://arxiv.org/abs/2509.11420)：推理模型与强化学习交易。
7. [LLM-Powered Multi-Agent System for Automated Crypto Portfolio Management](https://arxiv.org/abs/2501.00826)：多 Agent 组合管理。
8. [P1GPT](https://arxiv.org/abs/2510.23032)：结构化多模态投研工作流。
9. [QuantAgent](https://arxiv.org/abs/2509.09995)：高频交易 Agent。
10. [MountainLion](https://arxiv.org/abs/2507.20474)：多模态分析和反思机制。

## 四、2025-2026 年前沿趋势

### 4.1 细粒度任务拆解取代角色扮演

早期多 Agent 系统常让模型扮演基本面分析师、技术分析师和交易员。2026 年研究开始关注更具体的问题：每个步骤输入什么、产出什么、如何验证，以及中间结论能否支持最终决策。

值得研究：

- 细粒度工作流相对粗粒度角色提示的真实增益；
- Agent 之间的信息接口和错误传播；
- 在相同 token、模型和工具预算下进行消融实验。

### 4.2 从最终答案评测转向完整推导审计

BigFinanceBench 表明，只检查最终数字会掩盖来源选择、会计口径、时间范围、假设和计算过程中的错误。投研 Agent 的输出必须允许另一位分析师复核。

生产系统应记录：

- 数据来源与抓取时间；
- 使用的财务口径和期间；
- 中间计算、代码与假设；
- Agent 调用链、模型版本和提示词；
- 最终决策与风险约束。

### 4.3 实时评测与数据污染控制

AI-Trader 直接挑战传统历史回测：模型可能在训练阶段见过历史新闻、财报甚至行情。实时或严格时间隔离的评测正在成为 Agent 投资研究的核心标准。

合格实验至少应包括 point-in-time 数据、手续费、滑点、市场冲击、成交限制、模型版本冻结、多次重复运行，以及与简单因子和指数基准比较。

### 4.4 推理强化学习与结构化投资论点

Trading-R1 代表通过监督微调和强化学习，将通用推理模型变成金融决策模型的路线。前沿问题是：模型生成的“投资论点”是否真正驱动了决策，还是仅仅对买卖结果进行语言包装。

必须同时检查事实依据、风险调整收益、回撤、决策稳定性和跨资产泛化。

### 4.5 多模态、组合管理与高频 Agent

2025 年出现了加密组合、多模态分析和高频 Agent。它们扩大了 Agent 的应用边界，但也是最容易高估回测效果的方向：

- 加密资产制度变化快、样本短；
- 图表视觉理解可能遗漏精确数值；
- 高频策略对延迟、费用、冲击成本和基础设施极其敏感；
- 多 Agent 的额外推理延迟可能与高频要求冲突。

### 4.6 自主 Agent 的监管与系统性风险

2026 年综合综述开始将 Agent 视为潜在市场参与者，而非单纯分析工具。多个机构若使用相似模型和公开信息，可能同时形成相近仓位，放大拥挤交易和市场反馈循环。

关键问题包括模型责任归属、异常交易处置、提示注入、数据投毒、决策可解释性和模型升级后的行为漂移。

## 五、论文阅读时的风险检查表

| 检查项 | 需要追问的问题 |
|---|---|
| 数据污染 | 模型是否可能见过测试期新闻、财报或价格？ |
| 时间一致性 | 使用的是当时可获得的数据，还是后来修订的数据？ |
| 交易成本 | 是否计入手续费、滑点、冲击成本、借券成本和成交失败？ |
| 基准选择 | 是否与指数、简单因子、传统 ML 和等预算单 Agent 比较？ |
| 风险指标 | 是否报告最大回撤、换手、容量、因子暴露和尾部风险？ |
| 统计稳健性 | 是否跨市场、跨时期、多次重复，是否报告显著性？ |
| Agent 增益 | 多 Agent 的提升是否只是因为使用了更多 token 和调用次数？ |
| 可复现性 | 是否公开代码、数据、提示词、模型版本和完整交易日志？ |
| 实盘证据 | 是否经过长期纸面交易或真实资金测试？ |

## 六、推荐研究路线

### 路线 A：可审计金融研究 Agent

以 Finance Agent Benchmark 和 BigFinanceBench 为基线，构建能访问公告、财报和行情的 Agent。重点优化证据引用、计算正确率、完整推导和人工复核效率，而不是直接追求交易收益。

### 路线 B：实时 Agent 评测平台

参考 AI-Trader，建立预注册的持续纸面交易环境。冻结模型和策略版本，记录每次信息获取、推理、仓位和风控动作，并公开完整成本与风险指标。

### 路线 C：细粒度多 Agent 投研系统

参考 Toward Expert Investment Teams，围绕真实工作流拆任务。与等预算单 Agent 和粗粒度多 Agent 做严格对照，判断协作本身是否创造增量价值。

### 路线 D：确定性风控层

让 Agent 负责研究和候选信号，确定性程序负责组合优化、仓位约束、流动性检查、止损熔断和执行。禁止 LLM 绕过硬性风控直接下单。

## 七、最终判断

2025-2026 年最有价值的进展，不是出现了一个已经被证明可以稳定赚钱的自主交易 Agent，而是研究界开始认真解决**实时评测、数据污染、细粒度工作流、可审计推导和系统性风险**。

截至 2026 年 6 月，公开研究仍不足以证明 LLM Agent 在计入完整成本和风险后，能够长期稳定战胜市场。近期最值得投入的方向是可审计投研 Agent、严格实时评测和确定性风控，而不是依据短期回测直接部署自主交易。

