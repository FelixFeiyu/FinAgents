# FinAgent Portfolio Lab：多智能体投资组合构建框架 Spec

> 文档类型：SDD（Spec-Driven Development）项目规格  
> Spec 版本：**v0.2（As-Built 对齐版）**  
> 创建日期：2026-06-10  
> 最后更新：2026-06-10  
> 项目定位：可用于求职展示的多智能体金融投研与投资组合构建项目  
> 声明：仅用于研究、回测和模拟交易，不构成投资建议，不在 MVP 中接入真实资金交易。

## 0. Spec 状态与关键决策

### 0.0 实现快照（v0.2，对齐当前代码）

| 维度 | Spec 原设计 | **当前实现（test_cdx）** |
|---|---|---|
| Agent 数量 | 8 个（含 News、Holding Review、PM、Risk Explanation） | **4 个研究 Agent**：`fundamental` / `technical` / `macro` / `critic` |
| Agent 编排 | LangGraph 状态图 | **`ResearchGraph`**：同步 for 循环 + `LLMProvider` |
| 数据层 | Alpha Vantage + SEC + FRED + Parquet/DuckDB | **Yahoo + SEC XBRL + Yahoo 宏观**；JSON 于 `data/processed/` |
| 组合优化 | Black-Litterman + CVXPY | **`DeterministicOptimizer`** |
| 回测 | Backtrader / 事件驱动 | **`run_backtest()`** 逐周 pipeline |
| 状态机 | Paper Portfolio ledger | **`PortfolioStore`（SQLite）** |
| LLM | DeepSeek + Mock | **`MockLLMProvider` 默认** + **`DeepSeekProvider`（live）** |
| 测试 | 覆盖率 ≥80% | **25 pytest 用例**；见 `docs/TDD_TEST_SUMMARY.md` |

**P0 主链路已打通**：`ingest → build_evidence → firewall → agents → aggregate → optimize → risk → decision → state → audit`。

**尚未实现**：News Agent、Black-Litterman、FRED/ALFRED、Paper Portfolio、真实消融、token 成本追踪。

| 项目 | 决策 |
|---|---|
| 项目名称 | FinAgent Portfolio Lab |
| MVP 市场 | 美国股票，固定的高流动性股票池 |
| 决策频率 | 每周首个可交易日前生成研究快照，并选择 `HOLD`、`REBALANCE` 或 `REBUILD` |
| 投资约束 | Long-only，不使用杠杆，不做空 |
| Agent 模型 | MVP 默认使用官方 API 模型名 `deepseek-v4-pro` 并开启 thinking mode，通过适配层支持未来切换 |
| Agent 编排 | 轻量 Python 编排（`ResearchGraph`），借鉴 TradingAgents 角色分工，不复制其交易决策逻辑 |
| 组合优化 | MVP 使用 **`DeterministicOptimizer`**；Spec 目标仍为 PyPortfolioOpt/CVXPY Black-Litterman |
| 回测 | **Pipeline 驱动周频回测**（`finagent backtest`）；Spec 目标仍可升级为日频事件驱动 |
| 执行范围 | 回测 + Paper Portfolio，不自动连接券商实盘 |
| 核心卖点 | 可审计证据链、时间防火墙、持仓延续性评估、成本感知调仓门禁、多 Agent 消融实验 |

### 0.1 DeepSeek 模型命名说明

截至本 Spec 创建时间，未检索到可核验的官方 `DeepSeek-R3` 模型/API 名称。根据 [DeepSeek 官方模型文档](https://api-docs.deepseek.com/quick_start/pricing)，当前模型为 `deepseek-v4-pro` 和 `deepseek-v4-flash`；兼容名称 `deepseek-reasoner` 已计划在 2026-07-24 弃用。项目不得在 README 或简历中虚假宣称已使用 R3。

实现要求：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_REQUESTED_ALIAS=deepseek-r3
DEEPSEEK_THINKING_ENABLED=true
```

- 所有模型调用必须经过 `LLMProvider` 接口。
- 当官方 R3 可用时，只修改环境变量和模型能力配置，不修改 Agent 业务逻辑。
- 测试环境使用 `MockLLMProvider`，避免测试依赖 API 和产生费用。

## 1. 项目背景

现有开源多智能体交易项目通常让不同 Agent 扮演基本面分析师、技术分析师、新闻分析师和交易员，再由 LLM 直接给出买卖决策。该设计适合演示，但存在四个问题：

1. Agent 生成的事实、数据时间和来源难以审计。
2. LLM 直接分配仓位，结果不稳定且可能违反风险约束。
3. 历史回测容易发生未来数据泄漏和模型训练数据污染。
4. 多 Agent 的效果可能只是来自更多 token，而非协作本身。

本项目将多智能体用于**每周生成有证据的投资观点、评估当前持仓是否仍然成立并识别风险变化**。确定性优化器生成候选组合，决策门禁比较当前组合与候选组合，仅在预期改善足以覆盖交易成本和安全边际时执行调仓；硬风控模块决定组合是否可批准。

## 2. 项目目标与非目标

### 2.1 目标

- 构建端到端流程：数据采集、特征计算、每周 Agent 研究、当前持仓评估、观点聚合、候选组合优化、调仓决策、风险审批、回测、模拟持仓和报告生成。
- 每个 Agent 结论必须关联数据来源、数据时间、证据和置信度。
- 使用 DeepSeek 推理模型生成结构化研究结论，不允许模型直接提交订单。
- 使用确定性优化器将 Agent 信号转化为满足约束的组合权重。
- 每周在 `HOLD`、`REBALANCE` 和 `REBUILD` 中选择动作，避免无意义的强制调仓。
- 对单 Agent、多 Agent、无 LLM 基线进行等预算或明确成本的对比实验。
- 产出适合求职展示的架构图、实验报告、决策日志、困难记录和演示界面。

### 2.2 非目标

- 不承诺稳定盈利或战胜市场。
- 不在 MVP 中做高频交易、日内交易、期权、做空或杠杆。
- 不在 MVP 中自动执行真实资金订单。
- 不使用付费 Bloomberg、Refinitiv 等终端作为必需依赖。
- 不让 LLM 进行精确财务计算、组合优化或绕过风险约束。
- 不将历史回测结果描述为实盘收益。

## 3. 可复用开源项目与改造策略

### 3.1 借鉴项目

| 项目 | 链接 | 借鉴内容 | 本项目的改造 |
|---|---|---|---|
| TradingAgents | <https://github.com/TauricResearch/TradingAgents> | 多角色分析、研究辩论、交易与风险团队的工作流 | 从单标的交易改为组合构建；增加证据账本、结构化契约、时间防火墙、确定性优化器和消融实验 |
| Microsoft Qlib | <https://github.com/microsoft/qlib> | 量化研究、数据处理、模型评估思想 | MVP 不强依赖；后续可接入其数据/因子研究流程 |
| PyPortfolioOpt | <https://github.com/robertmartin8/PyPortfolioOpt> | 均值-方差、Black-Litterman、风险模型和组合约束 | 用于将 Agent views 转化为可复现权重 |
| Backtrader | <https://github.com/mementum/backtrader> | 事件驱动回测框架 | 增加数据时间检查、交易成本和决策日志关联 |

### 3.2 代码复用边界

- 优先借鉴架构思想和接口，不整仓复制 TradingAgents。
- 如复制或修改开源代码，必须保留许可证和来源说明。
- 本项目核心代码必须体现原创改造：`evidence_ledger`、`temporal_firewall`、`view_aggregator`、`risk_gate` 和 `experiment_runner`。

## 4. 用户与使用场景

### 4.1 目标用户

- 求职者：展示 Agent 工程、金融建模、评测和系统设计能力。
- 量化/投研开发者：研究 Agent 是否能改善组合研究流程。
- 面试官/评审者：通过可复现实验判断项目真实性，而非只看 UI。

### 4.2 核心用户故事

| ID | 用户故事 | 优先级 |
|---|---|---|
| US-01 | 作为研究员，我希望每周评估当前持仓并获得带来源的 `HOLD`、`REBALANCE` 或 `REBUILD` 建议 | P0 |
| US-02 | 作为风控人员，我希望任何组合都必须通过硬性约束检查，并看到拒绝原因 | P0 |
| US-03 | 作为评审者，我希望从最终权重追溯到 Agent 观点、原始数据和模型调用 | P0 |
| US-04 | 作为研究员，我希望回测不会使用决策时点之后的数据 | P0 |
| US-05 | 作为求职者，我希望一键运行基线与消融实验，并生成可放入项目介绍的报告 | P0 |
| US-06 | 作为开发者，我希望替换模型或数据提供商时不修改核心业务逻辑 | P1 |
| US-07 | 作为用户，我希望查看模拟持仓、收益、风险、费用和 Agent 决策历史 | P1 |
| US-08 | 作为评审者，我希望看到系统为何选择继续持有或调仓，以及候选组合相对当前组合是否值得支付交易成本 | P0 |

## 5. 资产池与投资规则

### 5.1 MVP 资产池

- 使用配置文件固定 20-30 只高流动性美国大型股票。
- 股票池在一次完整回测开始前冻结，不根据未来表现调整。
- 使用 `universe_version` 标记股票池版本。
- MVP 固定股票池不能消除幸存者偏差，报告中必须披露该限制。

选择固定股票池的原因：免费数据条件下难以可靠获得历史时点的指数成分股。后续版本可购买 point-in-time 成分股数据以降低幸存者偏差。

### 5.2 组合规则

| 参数 | MVP 默认值 |
|---|---|
| 初始资金 | USD 100,000 |
| 决策频率 | 每周首个可交易日前完成分析，使用前一交易日收盘后可获得的数据 |
| 允许动作 | `HOLD`、`REBALANCE`、`REBUILD` |
| 单只股票最大权重 | 10% |
| 单只股票最小有效权重 | 1% |
| 行业最大权重 | 30% |
| 现金最低比例 | 5% |
| 最大每周换手率 | 20%；`REBUILD` 经增强风控批准后最高 40% |
| Long-only | 是 |
| 杠杆/做空 | 禁止 |
| 交易成本 | 每次成交按 10 bps，作为可配置参数 |
| 滑点 | 默认 5 bps，作为可配置参数 |
| 最低调仓改善阈值 | 候选组合相对当前组合的预期净收益改善必须高于估算交易成本 + 10 bps 安全边际；风险效用另作硬约束 |
| 单周新建仓数量上限 | 5 |
| 默认执行时点 | 周末/首个交易日前完成决策，下一个交易日开盘后按回测成交规则执行 |

### 5.3 每周决策状态

| 状态 | 定义 | 默认触发条件 |
|---|---|---|
| `HOLD` | 保留当前持仓和权重，不主动交易 | 当前投资逻辑未失效；候选组合改善不足以覆盖交易成本与安全边际 |
| `REBALANCE` | 保留组合主体，仅调整部分权重或替换少量股票 | 候选组合通过风险门禁，且净改善超过阈值；换手率不超过 20% |
| `REBUILD` | 当前组合核心假设或风险结构显著失效，重新构建组合 | 多项核心观点失效或触发重大风险；需增强风控批准，换手率不超过 40% |

每周分析不等于每周交易。`HOLD` 必须作为正式、有证据的决策结果写入账本，而不是系统无动作时的默认状态。

若遇节假日，系统在当周首个交易日前完成决策。研究流程只能读取上一个已结束交易日及之前可获得的数据，禁止使用执行日开盘后的信息。

## 6. 金融数据渠道

### 6.1 数据源清单（As-Built）

| 数据类型 | **MVP 当前实现** | Spec 目标/备用 | 落盘路径 | 服务 Agent |
|---|---|---|---|---|
| 日线价格 | **Yahoo Finance Chart API**（免 key，带 `raw/yahoo/` 缓存） | Alpha Vantage | `data/processed/prices.json` | technical、critic |
| 公司财务 | **SEC EDGAR `companyfacts` XBRL**（按 `filed` 时点） | 同左 | `data/processed/fundamentals.json` | fundamental |
| 宏观 regime | **Yahoo `^TNX` / `^VIX`** | FRED / ALFRED vintage | `data/processed/macro.json` | macro |
| 新闻情绪 | 未实现 | Alpha Vantage News | — | （Spec: News Agent） |
| 行业分类 | `configs/universe_us_largecap.json` 冻结映射 | SEC SIC | configs | risk_gate |
| 离线合成 | `finagent ingest --dataset all --source synthetic` | — | `data/processed/*` | 全部（测试/CI） |

Agent 与数据集映射见 **`data/agent_datasets.json`** 与 **`data/README.md`**。

**Evidence 特征（当前）**

| Agent | 特征前缀/名称 | 来源 |
|---|---|---|
| technical | `momentum_4w`, `momentum_12w` | 价格序列 |
| fundamental | `growth_revenue_yoy`, `growth_earnings_yoy`, `quality_net_margin` | SEC 季报 |
| macro | `macro_rate_trend`, `macro_risk_appetite` | ^TNX / ^VIX |
| critic | `risk_drawdown_52w` | 价格序列（52 周高点回撤） |

共享辅助特征：`low_volatility`（混合分/风控参考，不分配给 macro Agent）。

### 6.1.1 Spec 原计划数据源（后续）

| 数据类型 | MVP 主数据源 | 备用/开发源 | 用途与注意事项 |
|---|---|---|---|
| 日线价格、成交量、复权数据 | [Alpha Vantage API](https://www.alphavantage.co/documentation/) | `yfinance` 仅用于本地原型，不作为可信生产源 | 计算收益、波动率、动量和回测成交价格；需缓存并遵守频率限制 |
| 公司财务事实 | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 无 | 使用 `companyfacts`/`submissions`；必须记录 filing date，禁止在披露前使用 |
| 宏观数据 | [FRED API](https://fred.stlouisfed.org/docs/api/fred/) | 无 | 利率、通胀、信用利差等；回测需使用 ALFRED vintage 才能严格避免修订泄漏 |
| 新闻与新闻情绪 | [Alpha Vantage News & Sentiment](https://www.alphavantage.co/documentation/) | 后续可替换为有历史授权的数据商 | 免费层历史覆盖和频率有限；MVP 主要用于实时 Paper Portfolio，不把新闻回测作为主要收益证据 |
| 行业分类 | SEC SIC 或项目内冻结映射表 | 无 | 用于行业约束；映射表必须版本化 |
| 无风险利率 | FRED | 无 | 计算 Sharpe、组合优化和报告 |

### 6.2 数据合规与可靠性规则

- 所有 HTTP 请求必须设置明确 `User-Agent`，遵守数据源条款和频率限制。
- 原始数据写入不可变的 `raw/` 分区，解析后数据写入 `processed/` 分区。
- 每条记录包含 `source`、`observed_at`、`available_at`、`fetched_at` 和内容哈希。
- 回测查询必须满足 `available_at <= decision_time`。
- 外部 API 不可用时，系统使用最近一次有效缓存并标记 `stale=true`；超过阈值则停止生成新组合。
- API Key 只从环境变量读取，不写入代码、日志或版本库。

### 6.3 明确的数据限制

- Alpha Vantage 免费层存在频率限制，首次构建历史缓存可能较慢。
- SEC XBRL 标签在公司之间并不完全一致，需要标准化映射和缺失值策略。
- FRED 最新值可能包含后续修订；严格回测应切换到 ALFRED vintage。
- 免费新闻数据通常不满足完整历史回测需求，因此新闻 Agent 的主要验收场景是前向 Paper Portfolio。
- `yfinance` 数据方便但不属于官方交易所数据，不作为最终结果的唯一来源。

## 7. 系统架构

### 7.1 总体流程（As-Built）

```text
CLI: finagent ingest / research / decide / backtest
      |
      v
Data Ingestion (Yahoo prices, SEC fundamentals, Yahoo macro)
      -> data/raw/* cache -> data/processed/*.json + manifest.json
      |
      v
build_evidence() -> point-in-time Evidence (available_at 规则)
      |
      v
Temporal Firewall -> filter(available_at <= decision_time)
      |
      v
ResearchGraph (fundamental | technical | macro | critic)
      -> MockLLMProvider / DeepSeekProvider
      |
      v
Evidence Ledger (SQLite) + ViewAggregator
      |
      v
DeterministicOptimizer (score -> weights, turnover cap)
      |
      v
Thesis review (previous vs current aggregated score)
      |
      v
RiskGate (current + candidate) -> DecisionGate (HOLD/REBALANCE/REBUILD)
      |
      v
PortfolioStore (SQLite state) + run-<uuid>.json audit artifact
      |
      +--> Streamlit dashboard / backtest equity curve
```

### 7.1.1 Spec 目标流程（后续）

```text
Scheduler / CLI
      |
      v
Data Ingestion -> Raw Data Lake -> Temporal Firewall -> Feature Store
                                                     |
                                                     v
             +---------------- Multi-Agent Research Graph ----------------+
             | Fundamental | Technical | Macro | News | Bear/Critic Agent |
             +------------------------------------------------------------+
                                      |
                                      v
                         Evidence Ledger + Structured Views
                                      |
                                      v
                     View Aggregator / Confidence Calibrator
                                      |
                                      v
                 Deterministic Portfolio Optimizer (Black-Litterman)
                                      |
                                      v
                 Current vs Candidate Decision Gate
                     (`HOLD` / `REBALANCE` / `REBUILD`)
                                      |
                                      v
                     Hard Risk Gate -> Approved Decision
                                      |
                         +------------+------------+
                         v                         v
                    Backtest                    Paper Ledger
                         \                         /
                          v                       v
                         Metrics + Audit Report + Dashboard
```

### 7.2 技术栈

| 层 | Spec 目标 | **当前实现** |
|---|---|---|
| 语言 | Python 3.12 | Python ≥3.9（CI 3.12）；`uv` 管理 |
| 包管理 | `uv` | `uv` + `pyproject.toml` |
| Agent 编排 | LangGraph 或轻量状态图 | **`ResearchGraph`（自研 for 循环）** |
| LLM API | OpenAI-compatible → DeepSeek | **`DeepSeekProvider` + `MockLLMProvider`** |
| 数据校验 | Pydantic v2 | **dataclass + `AgentView.__post_init__`** |
| 数据处理 | Polars/Pandas、NumPy | **标准库 + 可选 pandas（dashboard）** |
| 存储 | Parquet + DuckDB；SQLite 元数据 | **JSON processed + SQLite**（evidence / portfolio state） |
| 优化 | PyPortfolioOpt + CVXPY | **`DeterministicOptimizer`** |
| 回测 | Backtrader 或轻量事件驱动 | **`run_backtest()` pipeline 驱动** |
| 可视化 | Streamlit | **Streamlit 5 标签页 dashboard** |
| 实验追踪 | MLflow 或 SQLite 实验表 | **硬编码 demo 矩阵**（`experiments.py`） |
| 测试 | Pytest | **25 cases** |
| 质量工具 | Ruff、Mypy、pre-commit | **Ruff + pytest CI** |
| CI | GitHub Actions | **GitHub Actions**（push/PR） |

### 7.2.1 建议技术栈（Spec 目标，未全部落地）

| 层 | 选择 |
|---|---|
| 语言 | Python 3.12 |
| 包管理 | `uv` |
| Agent 编排 | LangGraph，或实现轻量状态图以减少框架锁定 |
| LLM API | OpenAI-compatible client 指向 DeepSeek API |
| 数据校验 | Pydantic v2 |
| 数据处理 | Polars/Pandas、NumPy |
| 存储 | Parquet + DuckDB；运行元数据使用 SQLite |
| 优化 | PyPortfolioOpt + CVXPY |
| 回测 | Backtrader 或轻量事件驱动实现 |
| 可视化 | Streamlit |
| 实验追踪 | MLflow 或项目内 SQLite 实验表 |
| 测试 | Pytest |
| 质量工具 | Ruff、Mypy、pre-commit |
| CI | GitHub Actions |

## 8. Agent 设计

### 8.1 Agent 列表

#### 8.1.1 当前已实现（4 个研究 Agent）

| Agent | 专属数据集 | 特征 | LLM 输入 | 实现文件 |
|---|---|---|---|---|
| **fundamental** | `data/processed/fundamentals.json`（SEC XBRL） | `growth_*`, `quality_*` | 按前缀过滤后的 features + `feature_score` | `agents.py`, `data.py` |
| **technical** | `data/processed/prices.json`（Yahoo） | `momentum_*` | 同上 | 同上 |
| **macro** | `data/processed/macro.json`（^TNX, ^VIX） | `macro_*` | 同上（宏观特征复制到每只股票） | 同上 |
| **critic** | 共用 `prices.json` | `risk_*`（如 `risk_drawdown_52w`） | 混合分 + 风险特征取反 | `providers.py` |

**确定性组件（非 LLM Agent，Spec 中曾规划为 Agent）**

| 组件 | 实现 | 职责 |
|---|---|---|
| Thesis review | `review_holding()` + `PortfolioStore` 分数快照 | 上周 vs 本周聚合分 → `intact/weakened/invalidated` |
| 组合优化 | `DeterministicOptimizer` | score→权重，不经过 LLM |
| 风控 | `RiskGate` | 硬约束，Agent 不可覆盖 |
| 决策 | `DecisionGate` | HOLD/REBALANCE/REBUILD + 成本门槛 |

#### 8.1.2 Spec 目标 Agent（尚未实现）

| Agent | 输入 | 输出 | 禁止行为 |
|---|---|---|---|
| News Agent | 决策前新闻及来源 | 事件摘要、方向、时效和可信度 | 无历史授权数据时不得参与历史回测 |
| Holding Review Agent（LLM 版） | 当前持仓、建仓时观点、本周证据 | thesis 状态 + 自然语言解释 | 不因短期价格波动直接要求卖出 |
| Portfolio Manager Agent | 已验证观点、持仓审查、风险摘要 | 结构化优化建议 | 不直接产生最终权重或订单 |
| Risk Explanation Agent | 优化与风控结果 | 面向人类的批准/拒绝说明 | 无权绕过风险门禁 |

### 8.2 统一 Agent 输出契约

```json
{
  "run_id": "uuid",
  "agent": "fundamental",
  "as_of": "2026-06-10T20:00:00Z",
  "symbol": "AAPL",
  "stance": "bullish",
  "score": 0.35,
  "confidence": 0.72,
  "horizon_days": 30,
  "thesis": "Structured short thesis",
  "risks": ["risk-1"],
  "evidence_ids": ["ev-uuid-1", "ev-uuid-2"],
  "missing_data": [],
  "model": "deepseek-v4-pro",
  "prompt_version": "fundamental-v1"
}
```

契约规则：

- `score` 范围为 `[-1, 1]`，仅表达观点方向和强度。
- `confidence` 范围为 `[0, 1]`，必须通过后续校准，不能直接视为概率。
- 没有 `evidence_ids` 的观点自动失效。
- 输出必须通过 Pydantic 校验；失败时最多重试两次，仍失败则降级为中性观点。
- Agent 只返回最终结构化结论，不保存或展示模型私有思维链。
- 持仓股票还必须输出 `thesis_status`：`intact`、`weakened` 或 `invalidated`，并说明相对上周新增或变化的证据。

## 9. 核心创新点

### 9.1 Evidence Ledger：可审计证据账本

每个观点链接到证据对象：

```json
{
  "evidence_id": "ev-uuid",
  "source": "sec_companyfacts",
  "source_url": "https://...",
  "observed_at": "2026-03-31",
  "available_at": "2026-05-01T16:30:00Z",
  "fetched_at": "2026-06-10T12:00:00Z",
  "content_hash": "sha256...",
  "value": 123.4,
  "unit": "USD",
  "stale": false
}
```

亮点：从最终组合权重可以反向追踪至观点、证据、原始数据和模型调用。

### 9.2 Temporal Firewall：时间防火墙

所有回测数据在进入 Agent 前经过时间防火墙。若 `available_at > decision_time`，数据不可见并产生审计事件。

亮点：将防未来数据泄漏从研究纪律变成系统强制约束。

### 9.3 Confidence-to-Risk Budget：置信度映射风险预算

Agent 不直接给权重。聚合器将经过证据质量、Agent 一致性和历史校准修正后的置信度，映射为 Black-Litterman view uncertainty 或风险预算。

示例：

```text
raw confidence
-> evidence quality penalty
-> disagreement penalty
-> calibration transform
-> view uncertainty
-> deterministic optimizer
```

亮点：将自然语言判断与可解释的组合数学连接，同时限制 LLM 权力。

### 9.4 Counterfactual Committee：反事实委员会

Critic Agent 必须寻找与主流观点冲突的证据。实验模块比较：

- 无 Critic；
- 有 Critic；
- Critic 但不影响置信度；
- Critic 通过冲突惩罚影响风险预算。

亮点：不是展示“Agent 在辩论”，而是量化反证机制是否降低回撤或错误集中。

### 9.5 Equal-Budget Ablation：等预算消融

对比多 Agent 和单 Agent 时，记录 token、调用次数、延迟和 API 成本。至少提供：

1. 等 token 预算对比；
2. 实际成本对比；
3. 移除单个 Agent 的消融；
4. 无 LLM 量化基线。

亮点：回答“多 Agent 增益是否只是因为花了更多推理成本”。

### 9.6 Cost-Aware Weekly Decision Gate：成本感知的每周决策门禁

系统每周生成候选组合，但不会每周强制交易。决策门禁比较当前组合与候选组合的预期收益、风险、交易成本、观点变化和换手率；风险要求由硬约束独立保证：

```text
net_improvement_bps =
  candidate_expected_return_bps
  - current_expected_return_bps
  - estimated_transaction_cost
  - safety_margin
```

- `net_improvement_bps <= 0`：选择 `HOLD`。
- `net_improvement_bps > 0` 且核心持仓逻辑仍有效：选择 `REBALANCE`。
- 当前组合多个核心投资逻辑失效或风险结构显著恶化：允许申请 `REBUILD`，但必须经过增强风控。

亮点：区分“每周重新思考”和“每周强制交易”，量化继续持有的价值，降低过度换手。

## 10. 组合构建与风控规格

### 10.1 信号聚合

每只股票的聚合 view：

```text
view_score =
  weighted_mean(valid_agent_scores)
  * evidence_quality
  * confidence_calibration
  * disagreement_penalty
```

- 无有效证据时，`view_score = 0`。
- Agent 严重冲突时降低 view confidence，不通过简单投票掩盖冲突。
- 所有权重和公式写入版本化配置。

### 10.2 组合优化

**当前实现（MVP）**：`DeterministicOptimizer`

- 正 score 比例分配 + 单股上限 + 最低现金 + 换手缩放；
- 论点失效 ≥2 时使用 `max_rebuild_turnover`（见 `configs/risk.json`）；
- 负分标的不参与余量分配（避免向失效名回填权重）。

**Spec 目标（后续）**：Black-Litterman

- 当前组合是每周决策的首要比较基线，优化器不得假设每周从现金重新建仓。
- 市场先验：可使用等权或市值权重；市值数据不可靠时默认等权。
- Agent 聚合观点作为 views。
- 校准置信度映射为 view uncertainty。
- 使用 Ledoit-Wolf 或其他稳健协方差估计。
- 在目标函数中加入交易成本和换手惩罚。
- 优化器输出必须可复现，同样输入得到同样结果。

### 10.3 每周持仓评估与决策门禁

系统每周对每项现有持仓执行 thesis review：

- 对比本周与建仓时、上周的观点和证据；
- 判断投资逻辑为 `intact`、`weakened` 或 `invalidated`；
- 检查风险、相关性和组合集中度是否显著变化；
- 生成候选目标权重，并估算从当前权重迁移所需的交易成本；
- 输出 `HOLD`、`REBALANCE` 或 `REBUILD`，以及机器可读的理由。

默认决策规则：

```text
if hard_risk_breach:
    REBALANCE or REBUILD
elif portfolio_thesis_invalidated and enhanced_risk_gate_passed:
    REBUILD
elif net_improvement_bps > rebalance_threshold_bps:
    REBALANCE
else:
    HOLD
```

`HOLD` 仍需通过风险检查。若当前组合违反硬约束，即使候选组合改善不足，系统也必须执行风险降低型调仓。

每周组合级决策输出契约：

```json
{
  "run_id": "uuid",
  "decision_time": "2026-06-14T20:00:00Z",
  "execute_after": "2026-06-15T13:30:00Z",
  "action": "HOLD",
  "current_portfolio_id": "portfolio-uuid",
  "candidate_portfolio_id": "portfolio-uuid",
  "net_improvement_bps": -4.2,
  "estimated_transaction_cost_bps": 8.0,
  "safety_margin_bps": 10.0,
  "weekly_turnover": 0.0,
  "risk_gate_status": "APPROVED",
  "reason_codes": ["INSUFFICIENT_NET_IMPROVEMENT"]
}
```

### 10.4 硬风控门禁

风险门禁为确定性代码，至少检查：

- 单股、行业、现金、每周换手和杠杆约束；
- 组合预期波动和历史最大回撤警戒线；
- 数据是否过期或缺失；
- 是否存在未解决的时间防火墙违规；
- 优化器是否收敛；
- 与上期权重变化是否异常；
- `REBUILD` 是否具有明确的 thesis 失效证据并通过增强风控。

任一 P0 风险规则失败，候选决策状态必须为 `REJECTED`，不得由 Agent 覆盖；系统应回退到合规的 `HOLD` 或风险降低型组合。

## 11. 功能需求

| ID | 功能需求 | 优先级 | 验收摘要 | **v0.2 状态** |
|---|---|---|---|---|
| FR-01 | 采集并缓存价格、SEC 财务、宏观和新闻数据 | P0 | 数据含来源和时间字段，可增量更新 | **部分完成**：价格/SEC/宏观 ✅；新闻 ❌ |
| FR-02 | 时间防火墙过滤决策时点之后的数据 | P0 | 自动测试构造未来数据并确认不可见 | **完成** ✅ |
| FR-03 | DeepSeek Provider 返回结构化 Agent 输出 | P0 | 输出通过 schema；异常可重试和降级 | **部分完成**：Mock 默认 ✅；DeepSeek 可选 live ✅；Pydantic schema ❌ |
| FR-04 | 多 Agent 生成观点并写入证据账本 | P0 | 每个有效观点至少关联一条证据 | **完成** ✅（4 Agent + SQLite ledger） |
| FR-05 | 聚合 views，并基于当前持仓生成确定性候选组合 | P0 | 同输入结果一致，满足优化约束 | **完成** ✅（DeterministicOptimizer） |
| FR-06 | 每周决策门禁输出 `HOLD`、`REBALANCE` 或 `REBUILD` | P0 | 决策包含当前与候选组合比较、净改善和理由 | **完成** ✅ |
| FR-07 | 运行含成本的历史回测 | P0 | 输出收益、风险、换手、成本和基准比较 | **部分完成**：pipeline 回测 ✅；SPY 基准 ❌ |
| FR-08 | 运行单 Agent、多 Agent、无 LLM 基线和消融实验 | P0 | 一条命令可复现实验矩阵 | **部分完成**：`experiment` 为 demo 硬编码 ⚠️ |
| FR-09 | 生成 HTML/Markdown 决策与实验报告 | P0 | 报告可追溯至 run_id 和证据 | **部分完成**：JSON audit + Markdown 实验表 ✅；HTML ❌ |
| FR-10 | 维护 Paper Portfolio | P1 | 记录建议权重、模拟成交和每日净值 | **未实现** ❌ |
| FR-11 | Streamlit 展示系统状态与组合 | P1 | 可查看组合、风险、证据和调用成本 | **部分完成**：5 标签页 dashboard ✅；API 成本 ❌ |
| FR-12 | 对当前持仓执行 thesis review | P0 | 每项持仓输出 thesis 状态 | **部分完成**：数值 `review_holding()` ✅；LLM 版 ❌ |
| FR-13 | 风控门禁批准或拒绝每周动作 | P0 | 违规动作始终被拒绝；硬风险违规时不得无条件 `HOLD` | **完成** ✅ |

## 12. 非功能需求

| ID | 要求 | 验收标准 |
|---|---|---|
| NFR-01 可复现性 | 同一数据快照、配置和 mock 模型输出产生相同权重与指标 |
| NFR-02 可审计性 | 100% 最终持仓可追溯到优化输入；100% Agent 有效观点可追溯到证据 |
| NFR-03 可靠性 | 外部 API 失败时执行重试、缓存降级或停止决策，不静默使用坏数据 |
| NFR-04 安全性 | API Key 不进入仓库、日志和报告；日志对敏感字段脱敏 |
| NFR-05 成本透明 | 每次运行记录 token、模型调用数、延迟和估算成本 |
| NFR-06 测试质量 | 核心模块单元测试覆盖率不低于 80%；P0 流程有集成测试 |
| NFR-07 性能 | 已有本地数据缓存时，30 只股票一次研究流程在可配置时间预算内完成 |

## 13. 回测与实验设计

### 13.1 基准

- `SPY` 买入持有；
- 固定股票池等权每周再平衡；
- 固定股票池等权买入后持有；
- 传统动量组合；
- 无 LLM 的多因子 + 同一优化器；
- 单 Agent + 同一优化器；
- 多 Agent + 同一优化器。

### 13.2 指标

| 分类 | 指标 |
|---|---|
| 收益 | CAGR、累计收益、周度胜率、月度胜率 |
| 风险 | 年化波动率、Sharpe、Sortino、最大回撤、Calmar |
| 交易 | 每周换手率、交易成本、持仓集中度、`HOLD` 比例、动作分布 |
| Agent | 观点方向准确率、置信度校准误差、冲突率、无证据率、thesis 失效判断准确率 |
| 工程 | API 成本、token、延迟、失败率、缓存命中率 |

### 13.3 实验矩阵

| 实验 | 目的 |
|---|---|
| E1 无 LLM 多因子基线 | 判断 Agent 是否提供增量 |
| E2 单 Agent | 测量统一推理的表现和成本 |
| E3 多 Agent | 测量分工协作表现 |
| E4 多 Agent 去除 Critic | 测量反证机制价值 |
| E5 多 Agent 去除基本面/技术面/宏观 Agent | 测量各 Agent 边际贡献 |
| E6 多 Agent 等 token 预算 | 排除更多计算预算造成的优势 |
| E7 无置信度校准 | 测量校准对风险的影响 |
| E8 风险约束压力测试 | 验证极端观点不能突破硬风控 |
| E9 每周强制调仓 vs 成本感知门禁 | 测量 `HOLD` 机制是否降低换手和净成本 |
| E10 禁用 Holding Review Agent | 测量持仓延续性评估的边际贡献 |
| E11 不同调仓改善阈值 | 分析收益、风险和换手之间的敏感性 |

### 13.4 防止误导的报告规则

- 不只报告最优区间，必须报告完整测试期。
- 明确区分样本内、验证期、样本外和前向 Paper Portfolio。
- 不以“收益最高”作为唯一成功标准。
- 报告所有失败运行、缺失数据和策略拒绝。
- 所有结果注明数据源、模型、提示版本、费用假设和运行时间。

## 14. CLI 与接口（As-Built）

```bash
# 初始化并校验配置（含四 Agent 数据集就绪状态）
uv run finagent doctor

# 拉取真实/合成数据集 -> data/processed/
uv run finagent ingest --dataset all --source yahoo      # 真实：Yahoo + SEC + 宏观
uv run finagent ingest --dataset all --source synthetic  # 离线确定性数据
uv run finagent ingest --dataset prices --source yahoo
uv run finagent ingest --dataset fundamentals            # SEC EDGAR（需 SEC_USER_AGENT）
uv run finagent ingest --dataset macro                   # ^TNX / ^VIX

# 只读研究（不推进 PortfolioStore 状态机）
uv run finagent research --as-of 2026-06-10 [--mode mock|live]

# 每周决策（持久化持仓状态 + 写 audit JSON）
uv run finagent decide --as-of 2026-06-10 [--mode mock|live]

# Pipeline 驱动周频回测（写 artifacts/backtest/backtest-report.json）
uv run finagent backtest --weeks 52

# 消融实验（当前为 demo 矩阵，Spec 目标为真实 pipeline 消融）
uv run finagent experiment

# 启动展示界面
uv run streamlit run app/dashboard.py
```

### 14.1 Spec 目标 CLI（尚未实现）

```bash
# 拉取截至指定日期可用的数据
uv run finagent ingest --as-of 2026-06-10

# 生成一次组合研究
uv run finagent research --as-of 2026-06-10 --universe configs/universe_us_largecap.yaml

# 每周比较当前组合与候选组合
uv run finagent decide --run-id <run_id> --current-portfolio latest

# 运行完整回测
uv run finagent backtest --config configs/backtest_mvp.yaml

# 运行消融实验矩阵
uv run finagent experiment --config configs/ablation_mvp.yaml
```

## 15. 目录结构（As-Built）

```text
test_cdx/
├── README.md
├── SPEC_MultiAgent_Portfolio_DeepSeek.md   # 本 Spec（v0.2）
├── docs/TDD_TEST_SUMMARY.md                # TDD 测试总结
├── pyproject.toml
├── .env.example
├── configs/
│   ├── universe_us_largecap.json           # 股票池 + 行业映射（已接线）
│   └── risk.json                           # 风控参数（已接线）
├── data/
│   ├── README.md
│   ├── agent_datasets.json                 # 四 Agent ↔ 数据集映射
│   ├── raw/                                # 原始缓存（gitignore）
│   └── processed/                          # 归一化 JSON（gitignore）
│       ├── prices.json
│       ├── fundamentals.json
│       ├── macro.json
│       └── manifest.json
├── src/finagent/                           # 扁平单包（非 Spec 子包结构）
│   ├── cli.py
│   ├── pipeline.py
│   ├── agents.py
│   ├── providers.py
│   ├── data.py                             # ingest + build_evidence
│   ├── evidence.py
│   ├── temporal_firewall.py
│   ├── aggregation.py
│   ├── portfolio.py
│   ├── decision.py
│   ├── risk.py
│   ├── state.py                            # PortfolioStore 状态机
│   ├── backtest.py
│   ├── config.py
│   ├── market_data.py                      # Alpha Vantage / SEC / FRED 适配器
│   ├── experiments.py
│   └── reporting.py
├── app/dashboard.py
├── tests/
│   ├── test_core.py
│   ├── test_integration.py
│   ├── test_data_state_backtest.py
│   ├── test_agent_datasets.py
│   └── test_tdd_enhancements.py
├── .github/workflows/ci.yml
└── artifacts/                              # run JSON / sqlite（gitignore）
```

### 15.1 Spec 目标目录（参考）

```text
finagent-portfolio-lab/
├── README.md
├── LICENSE
├── pyproject.toml
├── .env.example
├── configs/
│   ├── universe_us_largecap.yaml
│   ├── agents.yaml
│   ├── risk.yaml
│   ├── backtest_mvp.yaml
│   └── ablation_mvp.yaml
├── src/finagent/
│   ├── cli.py
│   ├── providers/
│   │   ├── llm.py
│   │   └── market_data.py
│   ├── ingestion/
│   ├── temporal_firewall/
│   ├── features/
│   ├── agents/
│   ├── evidence_ledger/
│   ├── aggregation/
│   ├── portfolio/
│   ├── risk/
│   ├── backtest/
│   ├── experiments/
│   └── reporting/
├── app/
│   └── dashboard.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── architecture.md
│   ├── decisions/
│   ├── experiment_reports/
│   ├── challenge_log.md
│   └── interview_story.md
└── data/
    └── README.md
```

## 16. SDD 实施阶段与验收门（v0.2 进度）

| Phase | 目标交付 | **当前状态** | 关键证据 |
|---|---|---|---|
| **0** 骨架/CI | Spec、CI、Mock Provider | **~90%** ✅ | `.github/workflows/ci.yml`；`MockLLMProvider` |
| **1** 数据/防火墙 | ingest、时间防火墙、可复现快照 | **~75%** ✅ | `data.py` ingest；`test_temporal_firewall_*`；Yahoo+SEC+宏观 JSON |
| **2** 多 Agent/证据 | 4 Agent + DeepSeek + ledger | **~80%** ✅ | `ResearchGraph`；`test_agent_datasets.py`；live 可选 |
| **3** 优化/决策/风控 | 聚合、优化、门禁、状态机 | **~85%** ✅ | `DeterministicOptimizer`；`PortfolioStore`；25 tests |
| **4** 回测/消融/Paper | 含成本回测、真实消融、Paper | **~40%** ⚠️ | pipeline 回测 ✅；`experiments.py` demo ⚠️；Paper ❌ |
| **5** 展示 | Dashboard、演示材料 | **~50%** ⚠️ | Streamlit 5 页 ✅；视频/面试文档部分 |

### Phase 0：规格冻结与项目骨架

交付：

- Spec、README 草案、架构图、ADR-001 模型选择、ADR-002 数据源选择；
- Python 项目骨架、CI、质量工具和 mock provider。

验收门：

- Spec 中所有 P0 需求有唯一 ID；
- CI 可运行；
- 无真实 API Key。

### Phase 1：数据与时间防火墙

交付：

- Alpha Vantage、SEC、FRED provider；
- Parquet/DuckDB 存储；
- temporal firewall 和数据质量报告。

验收门：

- 测试证明未来数据无法进入研究流程；
- API 失败有明确降级行为；
- 数据快照可复现。

### Phase 2：多 Agent 与证据账本

交付：

- DeepSeek/Mock provider；
- 基本面、技术面、宏观、Critic 和 Holding Review Agent；
- 结构化输出和 evidence ledger。

验收门：

- 100% 有效观点包含证据；
- schema 失败可重试并安全降级；
- Agent 不直接产生权重。

### Phase 3：组合优化、每周决策与风险门禁

交付：

- view aggregator、Black-Litterman、约束优化、current-vs-candidate decision gate、risk gate；
- 可解释的 `HOLD`、`REBALANCE`、`REBUILD` 和批准/拒绝报告。

验收门：

- 同输入结果确定；
- 所有约束有自动测试；
- 恶意或极端 Agent 输出不能突破硬风控。
- 候选组合净改善不足时选择 `HOLD`；
- 当前组合触发硬风险时不得无条件 `HOLD`；
- `REBUILD` 必须具有 thesis 失效证据并通过增强风控。

### Phase 4：回测、消融与 Paper Portfolio

交付：

- 含成本回测；
- 基线与消融实验；
- Paper Portfolio ledger；
- Markdown/HTML 实验报告。

验收门：

- 一条命令复现实验；
- 报告同时包含收益、风险、成本和 Agent 指标；
- 报告包含每周动作分布、`HOLD` 比例和强制周调仓对照实验；
- 不隐藏失败运行。

### Phase 5：求职展示

交付：

- Streamlit Dashboard；
- 3-5 分钟演示视频；
- 系统设计图、实验结果、困难记录和面试讲述文档。

验收门：

- 新用户按 README 可在 mock 模式运行；
- 面试演示不依赖实时外部 API；
- 能清楚解释项目未使用真实资金以及回测限制。

## 17. 项目困难记录模板

开发过程中必须持续维护 `docs/challenge_log.md`。每条记录使用以下模板，禁止在项目完成后一次性虚构。

```markdown
## CH-XXX：问题标题

- 日期：
- 所属阶段：
- 现象：
- 影响：
- 初始假设：
- 排查过程与证据：
- 尝试过但失败的方法：
- 最终方案：
- 为什么选择该方案：
- 权衡与遗留风险：
- 自动化测试/监控：
- 可量化结果：
- 关联 commit / issue / ADR：
```

### 17.1 预期会遇到的困难与建议方法

| 困难 | 可能原因 | 建议处理方式 | 可用于面试讲述的能力 |
|---|---|---|---|
| SEC XBRL 字段不统一 | 公司使用不同 taxonomy/tag | 建立标准化映射、单位检查、缺失降级和证据保留 | 数据工程与金融口径理解 |
| 历史数据泄漏 | 只按财报期间而非披露时间过滤 | 使用 `available_at` 和时间防火墙；构造泄漏测试 | 严谨回测设计 |
| Agent JSON 输出失败 | 模型输出不稳定 | Pydantic 校验、有限重试、修复提示、失败降级中性 | LLM 工程可靠性 |
| 多 Agent 成本过高 | 重复上下文和无效辩论 | 共享结构化事实、缓存、限制轮次、等预算实验 | 成本与性能优化 |
| 观点置信度虚高 | LLM 自报置信度未校准 | 根据历史 Brier/ECE 或方向正确率做校准 | 模型评测能力 |
| 优化器权重极端 | 预期收益和协方差估计不稳定 | Black-Litterman、收缩协方差、权重与换手约束 | 组合数学与风控 |
| 周频决策导致过度交易 | 小幅观点变化反复触发调仓 | 比较当前与候选组合净效用，加入交易成本、安全边际和 `HOLD` 状态 | 成本感知决策设计 |
| 持仓逻辑难以持续追踪 | 每周观点缺少与建仓时假设的关联 | 保存 position thesis，使用 Holding Review Agent 标记维持、减弱和失效 | Agent 记忆与可审计性 |
| 新闻历史不足 | 免费 API 覆盖有限 | 新闻仅用于前向 Paper Portfolio；历史回测禁用并披露 | 数据合规与研究诚信 |
| 外部 API 不稳定 | 限频、网络和配额 | 本地不可变缓存、指数退避、stale 阈值和停止决策 | 生产系统设计 |

## 18. 求职项目呈现方案

### 18.1 简历描述草案

> 设计并实现可审计的周频多智能体投资组合研究框架，使用 DeepSeek 推理模型生成带证据的基本面、技术面和宏观观点，并通过 Holding Review Agent、Black-Litterman 与确定性风险门禁在 `HOLD`、`REBALANCE`、`REBUILD` 中选择动作；实现 point-in-time 时间防火墙、成本感知调仓门禁、Agent 置信度校准及等预算消融实验。

### 18.2 面试重点

1. 为什么不让 LLM 直接分配仓位：稳定性、约束和责任边界。
2. 如何防止未来数据泄漏：`available_at`、不可变快照和自动化测试。
3. 如何证明多 Agent 有价值：无 LLM、单 Agent、多 Agent和等预算消融。
4. 如何处理 Agent 幻觉：工具数据、证据账本、结构化输出和失败降级。
5. 如何诚实解释回测：披露幸存者偏差、新闻覆盖、费用与模型污染限制。
6. 为什么每周分析但不强制每周交易：当前组合比较基线、成本门槛和持仓 thesis 延续性。

### 18.3 展示材料

- 一张系统架构图；
- 一次组合决策的完整追溯页面；
- 一次 `HOLD` 与一次 `REBUILD` 决策的当前组合/候选组合对比；
- 基线与消融实验表；
- 风控拒绝极端组合的演示；
- 一条真实困难记录及修复前后指标；
- Paper Portfolio 持续运行记录。

## 19. 风险与缓解

| 风险 | 严重度 | 缓解措施 |
|---|---|---|
| `deepseek-r3` 不存在或不可调用 | 高 | 使用模型适配层，默认 `deepseek-v4-pro` thinking mode，未来按配置切换 |
| 回测数据污染/泄漏 | 高 | 时间防火墙、数据快照、泄漏测试、实时 Paper Portfolio |
| LLM 幻觉导致错误观点 | 高 | 证据强制关联、schema、Critic、无证据即失效 |
| 组合违反风险约束 | 高 | 确定性 risk gate，Agent 无覆盖权限 |
| 免费数据不完整 | 中 | 明确降级、缓存、禁止将新闻历史实验作为核心证据 |
| API 成本和限流 | 中 | 缓存、批处理、调用预算、mock 模式 |
| 周频决策增加调用成本和换手 | 中 | 缓存未变化证据、增量研究、成本门禁和 `HOLD` 状态 |
| 项目范围过大 | 中 | 严格按 P0/P1 分阶段，MVP 只做固定美股池和周频决策 |
| 开源许可证问题 | 中 | 记录来源、保留许可证、优先重写核心模块 |

## 20. Definition of Done

项目 MVP 仅在满足以下条件时视为完成：

- 所有 P0 功能需求通过测试；
- 可在 mock 模式下一条命令运行完整流程；
- 使用真实数据 provider 成功生成至少一次可审计组合研究；
- 任何最终权重都能追溯到聚合观点和证据；
- 每个周频运行都输出可审计的 `HOLD`、`REBALANCE` 或 `REBUILD` 决策；
- `HOLD`、风险降低型 `REBALANCE` 和 `REBUILD` 均有自动化测试；
- 时间防火墙和风险门禁有明确的失败测试；
- 基线、单 Agent、多 Agent 和至少三项消融实验可复现；
- 报告包含收益、风险、交易成本、模型成本和局限；
- README、架构图、challenge log 和面试讲述文档完整；
- 未宣称使用不存在的 DeepSeek-R3，也未将回测收益描述为实盘表现。

## 21. 待确认问题

以下问题不阻塞 Spec，但应在实现前写入 ADR：

1. 回测器最终使用 Backtrader，还是为周频决策、日频估值场景实现轻量事件驱动版本？
2. DeepSeek 官方若发布 R3，API 的模型名、结构化输出和价格是否满足项目要求？
3. 是否申请 Alpha Vantage API Key，还是替换为其他有明确授权的行情源？
4. 严格历史宏观回测是否从 FRED 升级到 ALFRED vintage？
5. MVP 股票池的具体成分与冻结日期是什么？
6. `REBALANCE` 的净改善阈值与 `REBUILD` 的 thesis 失效门槛如何通过验证集校准？

## 22. 测试与 TDD 策略（v0.2）

### 22.1 测试概况

| 指标 | 数值 |
|---|---|
| 测试文件 | 5 |
| 测试用例 | **25** |
| 运行命令 | `uv run pytest -q` |
| CI | GitHub Actions：pytest + ruff |
| 详细清单 | **`docs/TDD_TEST_SUMMARY.md`** |

### 22.2 TDD 增强轮次（2026-06-10）

针对合并 cc 功能后的行为缺口，先写失败测试再改实现：

1. `research` 只读、`decide` 才持久化状态机  
2. Mock Agent 按角色读取专属特征前缀  
3. `ingest` 未知数据源抛出明确 `ValueError`  
4. `RiskConfig` 构造期校验非法参数  
5. 论点失效 `REBUILD` 使用 `max_rebuild_turnover` 预算  

上述 5 项均已 **红→绿** 闭环，并额外修复优化器向负分标的回填权重的 bug。

### 22.3 Spec 测试差距

| Spec 要求 | 当前差距 |
|---|---|
| NFR-06 覆盖率 ≥80% | 未度量覆盖率；核心 P0 路径有测试但未达 80% 声明 |
| FR-08 真实消融 | `experiments.py` 仍为硬编码数组 |
| 集成 live DeepSeek | 无 live API 集成测试（刻意避免 CI 费用） |
| Paper Portfolio | 无 E2E 测试 |
