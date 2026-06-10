# TDD 测试总结 — FinAgent Portfolio Lab

> 文档版本：v1.0  
> 更新日期：2026-06-10  
> 项目路径：`test_cdx/`  
> 运行命令：`uv sync --no-editable --extra dev && uv run pytest -q`

## 1. 总览

| 指标 | 数值 |
|---|---|
| 测试文件数 | 5 |
| 测试用例数 | **25** |
| 当前状态 | **25/25 通过** |
| CI | GitHub Actions（`pytest` + `ruff`） |
| 关联 Spec | `SPEC_MultiAgent_Portfolio_DeepSeek.md` §22 |

测试分层：

| 层级 | 文件 | 用例数 | 目的 |
|---|---|---:|---|
| 核心单元 | `tests/test_core.py` | 7 | P0 门禁：防火墙、聚合、优化、风控、决策 |
| 集成 | `tests/test_integration.py` | 1 | 端到端 mock pipeline + audit 产物 |
| 数据/状态/回测 | `tests/test_data_state_backtest.py` | 6 | 配置、证据、状态机、pipeline 回测 |
| Agent 数据集 | `tests/test_agent_datasets.py` | 6 | 四 Agent 专属数据与 `build_evidence` |
| TDD 增强 | `tests/test_tdd_enhancements.py` | 5 | 红→绿驱动的行为缺口修复 |

---

## 2. TDD 方法论在本项目中的运用

### 2.1 流程

```text
发现行为缺口 → 写失败测试（红）→ 最小实现修改（绿）→ 全量回归 pytest
```

### 2.2 2026-06-10 TDD 增强轮（`test_tdd_enhancements.py`）

| # | 测试 | 暴露的缺口 | 修复位置 |
|---|---|---|---|
| 1 | `test_research_is_read_only_but_decide_persists` | `research` 与 `decide` 都会推进状态机 | `cli.py`：`persist_state=(command=="decide")` |
| 2 | `test_mock_agents_differentiate_by_role` | 四 Agent 共享同一 score | `providers.py`：`ROLE_FEATURE_PREFIXES` 按前缀分流 |
| 3 | `test_ingest_rejects_unknown_source` | 未知数据源抛裸 `KeyError` | `data.py`：明确 `ValueError` |
| 4 | `test_risk_config_validates_limits` | 风控配置无合法性校验 | `config.py`：`RiskConfig.__post_init__` |
| 5 | `test_thesis_rebuild_uses_rebuild_turnover_budget` | REBUILD 被周度 0.20 换手卡死 | `pipeline.py` + `portfolio.py`（论点失效用 rebuild 预算；负分不吸收余量） |

**意外收获（测试 5 钓出）**：`DeterministicOptimizer` 曾把剩余权重平摊给负分股票；修复为仅正分标的吸收余量。

---

## 3. 测试用例清单

### 3.1 `tests/test_core.py` — P0 核心门禁

| 测试 | 验证内容 | 对应 Spec |
|---|---|---|
| `test_temporal_firewall_blocks_future_data` | `available_at > decision_time` 的数据被过滤 | FR-02 |
| `test_view_without_evidence_is_invalid` | 无 evidence_ids 的 view 不参与聚合 | FR-04 |
| `test_optimizer_is_deterministic_and_respects_limits` | 优化器确定性；单股≤10%；现金≥5% | FR-05 |
| `test_risk_gate_rejects_extreme_agent_result` | 单股 95% 组合被拒绝 | FR-13 |
| `test_decision_gate_hold_and_risk_rebalance` | 净改善不足 HOLD；当前组合 risk breach → REBALANCE | FR-06, FR-13 |
| `test_rebuild_requires_multiple_invalidated_theses` | ≥2 论点失效 → REBUILD | FR-06, FR-12 |
| `test_current_risk_breach_never_falls_back_to_hold` | 当前组合违规时不得无条件 HOLD | FR-13 |

### 3.2 `tests/test_integration.py` — 端到端

| 测试 | 验证内容 | 对应 Spec |
|---|---|---|
| `test_mock_pipeline_writes_auditable_run` | pipeline 产出 views、aggregated、run JSON、evidence.sqlite | FR-04, FR-09 |

### 3.3 `tests/test_data_state_backtest.py` — 数据层与状态机

| 测试 | 验证内容 | 对应 Spec |
|---|---|---|
| `test_risk_config_loads_from_file` | `configs/risk.json` 被正确加载 | FR-05, FR-13 |
| `test_universe_config_includes_sectors` | 股票池与行业映射外置 | §5.1 |
| `test_price_evidence_is_point_in_time` | 价格证据 `available_at ≤ as_of` | FR-01, FR-02 |
| `test_portfolio_store_roundtrip` | SQLite 持仓/决策/分数快照读写 | 状态机 |
| `test_pipeline_state_machine_first_run_rebuilds_then_persists` | 首次 REBUILD；第二次读取真实上周持仓 | FR-06, FR-12 |
| `test_backtest_is_pipeline_driven_and_deterministic` | 回测逐周跑 pipeline；确定性；写 equity 报告 | FR-07 |

### 3.4 `tests/test_agent_datasets.py` — 四 Agent 专属数据

| 测试 | 验证内容 | 对应 Agent |
|---|---|---|
| `test_agent_dataset_manifest_exists` | `data/agent_datasets.json` 存在 | 全部 |
| `test_synthetic_ingest_builds_all_four_agent_datasets` | 合成 ingest 落盘三份 processed + manifest | 全部 |
| `test_build_evidence_emits_agent_specific_features` | momentum/growth/macro/risk 特征齐全且点时正确 | technical, fundamental, macro, critic |
| `test_fundamental_features_respect_filing_date` | SEC 数据按 `filed` 时点过滤 | fundamental |
| `test_mock_provider_reads_each_agent_dataset_features` | Mock 按前缀读取各 Agent 特征 | 全部 |
| `test_dataset_status_reflects_files` | `dataset_status()` 反映文件存在性 | ingest/doctor |

### 3.5 `tests/test_tdd_enhancements.py` — TDD 红→绿

见 §2.2。

---

## 4. 四 Agent 与测试覆盖映射

| Agent | 数据集 | 特征 | 覆盖测试 |
|---|---|---|---|
| **technical** | `prices.json` | `momentum_*` | `test_build_evidence_*`, `test_mock_provider_*`, `test_price_evidence_*` |
| **fundamental** | `fundamentals.json` | `growth_*`, `quality_*` | `test_fundamental_features_*`, `test_build_evidence_*` |
| **macro** | `macro.json` | `macro_*` | `test_build_evidence_*`, `test_mock_provider_*` |
| **critic** | 共用 `prices.json` | `risk_*` | `test_build_evidence_*`, `test_tdd mock differentiate` |

---

## 5. 未覆盖 / 后续 TDD 候选

| 缺口 | 建议测试 |
|---|---|
| Live DeepSeek 集成 | mock HTTP 层的 provider 契约测试（不调用真实 API） |
| `finagent ingest --dataset all` CLI | subprocess 或 `main()` 集成测试 |
| SPY 基准对比 | 回测报告含 benchmark 字段 |
| 真实消融矩阵 | `experiment` 驱动 pipeline 而非硬编码数组 |
| Paper Portfolio | 模拟成交与净值 E2E |
| 覆盖率 ≥80% | 引入 `pytest-cov` 并在 CI 设阈值 |

---

## 6. 本地运行

```bash
# 全量测试
uv run pytest -q

# 仅 TDD 增强套件
uv run pytest tests/test_tdd_enhancements.py -v

# 仅 Agent 数据集
uv run pytest tests/test_agent_datasets.py -v

# 静态检查
uv run ruff check src tests app
```

**macOS 注意**：若 `finagent` CLI 报 `ModuleNotFoundError`，使用 `uv sync --no-editable --extra dev`（editable `.pth` 可能被 hidden 标志跳过）。

---

## 7. 与 Spec Definition of Done 的对照

| DoD 条目 | 测试证据 |
|---|---|
| P0 功能有自动化测试 | `test_core.py` + `test_tdd_enhancements.py` |
| mock 模式一条命令跑通 | `test_integration.py` |
| 时间防火墙失败测试 | `test_temporal_firewall_blocks_future_data` |
| HOLD/REBALANCE/REBUILD 测试 | `test_decision_gate_*`, `test_rebuild_*`, `test_pipeline_state_*` |
| 风险门禁不可绕过 | `test_risk_gate_*`, `test_current_risk_breach_*` |
| 真实数据 provider 可生成研究 | 手动验证 + `test_agent_datasets`（合成/真实同路径） |
| 消融可复现 | **未满足** — `experiments.py` 仍为 demo |

**结论**：P0 控制流与四 Agent 数据层已有较完整 TDD 覆盖；Spec 中的 BL 优化、Paper Portfolio、真实消融仍为后续 TDD 迭代目标。
