# EvoSim Architecture Remediation Roadmap

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前“模块已拆分但主链路仍强耦合”的实现，整改为“平台模块、Agent Tools、Agent Skills 分层清晰，且由统一 runtime 编排”的架构。

**Architecture:** 先补 runtime 壳层与控制面状态容器，再把 `Simulation` 中直接串联的流程逐步迁移到标准 phase。平台模块先做适配包装，不直接大改内部业务逻辑；Agent Tools 和 Agent Skills 在第二轮收口，最后再处理事件语义、失败传播和快照兼容。

**Tech Stack:** Python, FastAPI, sqlite3, asyncio, dataclasses, existing `src/*` modules

## 1. 现状摘要

当前代码已经具备一部分模块级解耦：

- 推荐系统已经是独立流水线：[src/recommender/feed_pipeline.py](C:/Users/21462/Desktop/new/EvoSim/src/recommender/feed_pipeline.py)
- 审核系统已经有 `provider + actions + repository + service` 分层：[src/moderation/service.py](C:/Users/21462/Desktop/new/EvoSim/src/moderation/service.py)
- 攻击系统已经有 orchestrator + strategy 路由：[src/malicious_bots/attack_orchestrator.py](C:/Users/21462/Desktop/new/EvoSim/src/malicious_bots/attack_orchestrator.py)
- 快照系统独立成模块：[src/snapshot_manager.py](C:/Users/21462/Desktop/new/EvoSim/src/snapshot_manager.py)

但系统级耦合仍然集中在：

- `Simulation` 直接创建并调用几乎所有核心对象：[src/simulation.py](C:/Users/21462/Desktop/new/EvoSim/src/simulation.py)
- `control_flags` 作为全局可变状态被 API 和主循环直接共享
- 多个模块直接持有 `sqlite3.Connection` 并自行写 SQL
- 缺少统一 `contracts / registry / orchestrator / event model`
- 缺少后端测试基座，当前项目没有正式 `tests/` 目录

---

## 2. 整改原则

1. 先包裹，后重构。
2. 先 runtime 契约，后模块迁移。
3. 先去掉 `Simulation` 的系统编排职责，再细拆胖模块。
4. 明确失败优先于静默回退。
5. 所有阶段都要补测试，禁止只改结构不验证。

---

## 3. 阶段路线图

### Phase 0: 建立整改基线

**目标：** 在不改业务逻辑的前提下，先建立测试目录、架构基线文档、关键冒烟命令。

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/runtime/__init__.py`
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/test_imports.py`
- Modify: `requirements.txt`
- Reference: `run_quick_test.py`
- Reference: `run_system_test.py`

**Step 1: 建立最小后端测试目录**

创建：

```python
# tests/smoke/test_imports.py
def test_import_simulation():
    from src.simulation import Simulation  # noqa: F401
```

**Step 2: 确认测试依赖**

如果当前未安装 `pytest`，在 `requirements.txt` 中补充。

**Step 3: 运行最小测试**

Run: `pytest tests/smoke/test_imports.py -v`

Expected:
- 能收集测试
- 能导入主模块

**Step 4: 固化当前冒烟命令**

记录现有可用命令：

- `python run_quick_test.py`
- `python run_system_test.py`

**验收标准：**

- 有正式 `tests/` 目录
- 最小 smoke test 可运行
- 当前系统仍可按原方式启动

---

### Phase 1: 建立 Runtime 壳层

**目标：** 引入统一 runtime 基础设施，但暂时不替换现有业务逻辑。

**Files:**
- Create: `src/runtime/__init__.py`
- Create: `src/runtime/contracts.py`
- Create: `src/runtime/registry.py`
- Create: `src/runtime/orchestrator.py`
- Create: `src/runtime/context.py`
- Create: `src/runtime/control_plane.py`
- Create: `src/runtime/events.py`
- Create: `tests/runtime/test_contracts.py`
- Create: `tests/runtime/test_registry.py`
- Create: `tests/runtime/test_orchestrator_smoke.py`

**Step 1: 定义统一契约**

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RuntimeRequest:
    run_id: str
    tick: int
    phase: str
    name: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)

@dataclass
class RuntimeResult:
    status: str
    events: list[dict[str, Any]] = field(default_factory=list)
    writes: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
```

**Step 2: 建立注册表**

注册表至少支持：

- `name`
- `kind`
- `phase`
- `depends_on`
- `handler`

**Step 3: 建立最小 orchestrator**

先只支持：

- phase 顺序执行
- 按 name 查 handler
- 收集 `RuntimeResult`

**Step 4: 写最小测试**

Run: `pytest tests/runtime/test_contracts.py tests/runtime/test_registry.py tests/runtime/test_orchestrator_smoke.py -v`

**验收标准：**

- runtime 壳层可以注册一个 dummy handler
- 能按 phase 执行并收集结果
- 还未接入 `Simulation`

---

### Phase 2: 收口控制面状态

**目标：** 把 `control_flags` 从“全局变量穿透”整改为“统一 runtime state”。

**Files:**
- Create: `src/runtime/control_state.py`
- Modify: `src/control_flags.py`
- Modify: `src/main.py`
- Modify: `src/run_control_server.py`
- Modify: `src/simulation.py`
- Create: `tests/runtime/test_control_state.py`

**Step 1: 定义单一控制状态对象**

需要承载：

- `attack_enabled`
- `attack_mode`
- `moderation_enabled`
- `aftercare_enabled`
- `auto_status`

**Step 2: 保持兼容过渡**

`control_flags.py` 第一阶段不要直接删掉，改成兼容层，内部转发到统一状态对象。

**Step 3: API 改为只读写统一状态**

调整 [src/main.py](C:/Users/21462/Desktop/new/EvoSim/src/main.py) 和 [src/run_control_server.py](C:/Users/21462/Desktop/new/EvoSim/src/run_control_server.py)，避免多处直接修改模块级全局变量。

**Step 4: Simulation 改为接收 control state**

`Simulation` 不再直接依赖裸 `control_flags`，而通过 runtime context 读取开关。

**验收标准：**

- `/control/*` 仍能工作
- 状态来源唯一
- simulation 侧不再直接散读多个全局布尔值

---

### Phase 3: Platform Module 适配层接入

**目标：** 不大改模块内部实现，先为平台模块建立统一 adapter。

**Files:**
- Create: `src/runtime/adapters/__init__.py`
- Create: `src/runtime/adapters/recommender_adapter.py`
- Create: `src/runtime/adapters/moderation_adapter.py`
- Create: `src/runtime/adapters/news_adapter.py`
- Create: `src/runtime/adapters/snapshot_adapter.py`
- Create: `src/runtime/adapters/analytics_adapter.py`
- Create: `tests/runtime/test_platform_adapters.py`
- Reference: `src/recommender/feed_pipeline.py`
- Reference: `src/moderation/service.py`
- Reference: `src/news_manager.py`
- Reference: `src/snapshot_manager.py`

**Step 1: 先包装，不改模块内部**

每个 adapter 做三件事：

- 接收 `RuntimeRequest`
- 调用现有模块
- 产出 `RuntimeResult`

**Step 2: 优先接入 4 个低风险模块**

- `recommender`
- `platform-moderation`
- `news-injection`
- `experiment-lifecycle`

**Step 3: 统一输出事件名**

至少规范：

- `feed_exposed`
- `moderation_applied`
- `news_injected`
- `snapshot_saved`

**验收标准：**

- adapter 层可独立测试
- 平台模块对 runtime 输出统一格式结果
- 模块内部逻辑保持原样

---

### Phase 4: 剥离 Agent Tools

**目标：** 将 `agent-memory` 与 `evidence-rag` 明确为工具能力，而不是混在胖模块中的隐式依赖。

**Files:**
- Create: `src/runtime/tools/__init__.py`
- Create: `src/runtime/tools/memory_tool.py`
- Create: `src/runtime/tools/rag_tool.py`
- Modify: `src/agent_memory.py`
- Modify: `src/advanced_rag_system.py`
- Create: `tests/runtime/test_memory_tool.py`
- Create: `tests/runtime/test_rag_tool.py`

**Step 1: Memory tool 封装统一入口**

统一：

- 写记忆
- 取反思
- 取相关经验

**Step 2: RAG tool 封装统一入口**

统一：

- `type=evidence`
- `type=strategy`
- 非法输入直接报错

**Step 3: 拆掉工具与平台模块的隐式直连**

平台模块与 agent skill 不再直接 new `AdvancedRAGSystem` 或散调用 memory 细节。

**验收标准：**

- tool 层入口稳定
- `evidence-rag` 不再混着业务流随意 fallback
- tool 层可单测

---

### Phase 5: 提炼 Agent Skills

**目标：** 把真正的 agent 行为策略提炼成 skill handler，而不是继续埋在 manager 中。

**Files:**
- Create: `src/runtime/skills/__init__.py`
- Create: `src/runtime/skills/swarm_attack.py`
- Create: `src/runtime/skills/dispersed_attack.py`
- Create: `src/runtime/skills/chain_attack.py`
- Create: `src/runtime/skills/opinion_balance_defense.py`
- Create: `src/runtime/skills/post_hoc_intervention.py`
- Modify: `src/malicious_bots/malicious_bot_manager.py`
- Modify: `src/opinion_balance_manager.py`
- Modify: `src/fact_checker.py`
- Create: `tests/runtime/test_attack_skills.py`
- Create: `tests/runtime/test_defense_skill.py`
- Create: `tests/runtime/test_intervention_skill.py`

**Step 1: 攻击技能外部拆名、内部复用**

外部保留：

- `swarm-attack`
- `dispersed-attack`
- `chain-attack`

内部仍复用 [src/malicious_bots/attack_orchestrator.py](C:/Users/21462/Desktop/new/EvoSim/src/malicious_bots/attack_orchestrator.py)。

**Step 2: 防御技能从胖 manager 中抽出口**

把 [src/opinion_balance_manager.py](C:/Users/21462/Desktop/new/EvoSim/src/opinion_balance_manager.py) 中的：

- 监测触发
- 角色分工
- 干预执行
- 结果记录

拆成 skill handler + persistence helper。

**Step 3: 事后干预技能独立**

把 `fact-check` 决策逻辑从 `Simulation` 里挪出来，形成统一 `post-hoc-intervention` handler。

**验收标准：**

- 5 个 agent skill 有清晰 handler 入口
- 与 tool 层通过显式依赖连接
- manager 文件体积与职责显著收缩

---

### Phase 6: Simulation 主循环降级

**目标：** 让 `Simulation` 从 God Object 变为 runtime 容器。

**Files:**
- Modify: `src/simulation.py`
- Modify: `src/main.py`
- Create: `tests/runtime/test_simulation_runtime_integration.py`

**Step 1: 初始化改为装配 runtime**

`Simulation.__init__` 只保留：

- 核心依赖装配
- runtime 实例创建
- run metadata 初始化

**Step 2: 把 tick 内部直接调用改为 phase 执行**

推荐 phase：

1. `bootstrap`
2. `content_generation`
3. `distribution`
4. `governance`
5. `defense`
6. `intervention`
7. `analysis`
8. `snapshot`

**Step 3: 去掉直接串联**

重点移除：

- `if control_flags...`
- `self.moderation_service...`
- `self.snapshot_manager...`
- `self.malicious_bot_manager...`
- `self.opinion_balance_manager...`

这些应改为 runtime phase 调度。

**验收标准：**

- `Simulation.run()` 不再直接编排全部业务动作
- 主循环可读性显著提升
- phase 日志可观测

---

### Phase 7: 收口持久化边界

**目标：** 减少各模块散写 SQL，补 repository / gateway 边界。

**Files:**
- Create: `src/runtime/repositories/__init__.py`
- Create: `src/runtime/repositories/attack_repository.py`
- Create: `src/runtime/repositories/defense_repository.py`
- Create: `src/runtime/repositories/memory_repository.py`
- Modify: `src/malicious_bots/malicious_bot_manager.py`
- Modify: `src/opinion_balance_manager.py`
- Modify: `src/agent_memory.py`
- Create: `tests/runtime/test_repositories.py`

**Step 1: 先抽写路径，不强求读路径全抽**

优先收口：

- attack records
- intervention records
- memory writes

**Step 2: 约束事务边界**

每个 handler 不再到处 `commit()`，而是通过 repository 明确持久化。

**验收标准：**

- manager 中 SQL 数量显著下降
- 持久化写入路径集中
- 后续替换数据库成本下降

---

### Phase 8: 失败传播、事件语义、快照兼容

**目标：** 让新架构真正可插拔，而不是“只是多了一层壳”。

**Files:**
- Modify: `src/runtime/contracts.py`
- Modify: `src/runtime/registry.py`
- Modify: `src/runtime/orchestrator.py`
- Modify: `src/snapshot_manager.py`
- Create: `tests/runtime/test_failure_policy.py`
- Create: `tests/runtime/test_snapshot_compatibility.py`

**Step 1: registry 增加元数据**

需要支持：

- `kind`
- `phase`
- `depends_on`
- `criticality`
- `on_failure`

**Step 2: 失败传播策略落地**

至少区分：

- `abort_tick`
- `skip_downstream`
- `degrade_mode`

**Step 3: 快照记录 runtime 元数据**

至少记录：

- `contract_version`
- `registry_hash`
- `enabled_components`

**验收标准：**

- 失败策略清晰可测
- 快照恢复知道自己恢复的是什么架构版本
- phase 结果和事件可审计

---

## 4. 优先级排序

按投入产出比排序：

1. `Phase 0` 测试基线
2. `Phase 1` runtime 壳层
3. `Phase 2` control state 收口
4. `Phase 3` 平台模块适配
5. `Phase 6` Simulation 主循环降级
6. `Phase 4` Agent Tools
7. `Phase 5` Agent Skills
8. `Phase 7` persistence 边界
9. `Phase 8` 失败传播与快照兼容

说明：

- `Phase 6` 虽然编号靠后，但应在 platform adapter 成型后尽快做。
- `Phase 4` 和 `Phase 5` 可以局部交错推进，但不要在 runtime 壳层未建立前强拆胖模块。

---

## 5. 每阶段完成标准

一阶段只有同时满足下面三个条件，才算结束：

1. 有测试
2. 有真实接线或真实输出
3. 没有新增 silent fallback

禁止以下伪完成：

- 只有新目录，没有接线
- 只有包装类，没有测试
- 只有 handler 名字，没有真实执行
- 遇到不兼容就吞错继续跑

---

## 6. 最小交付顺序

如果你只想先做最小可见成果，建议只做到这里：

1. 建 `tests/`
2. 建 `src/runtime/contracts.py`
3. 建 `src/runtime/registry.py`
4. 建 `src/runtime/orchestrator.py`
5. 收口 `control_flags`
6. 先接 `recommender + moderation + snapshot`
7. 再让 `Simulation.run()` 改成 phase 调度

做到这一步，就已经从“模块分文件”升级到“运行时可编排”了。

---

## 7. 主要风险

- 风险：过早大拆 `Simulation`，导致主流程跑不通  
  缓解：先 adapter，后替换主循环

- 风险：把 runtime 做成空壳  
  缓解：每个 phase 必须接至少一个真实模块

- 风险：过度追求 event bus，导致复杂度先爆炸  
  缓解：初期先同步 phase 调度，不急着全面异步事件化

- 风险：RAG 和 memory 提前大改，影响防御链路  
  缓解：先做 tool wrapper，后做内部重构

---

## 8. 建议的第一批实施文件

第一批只碰这些文件：

- [src/runtime/contracts.py](C:/Users/21462/Desktop/new/EvoSim/src/runtime/contracts.py)
- [src/runtime/registry.py](C:/Users/21462/Desktop/new/EvoSim/src/runtime/registry.py)
- [src/runtime/orchestrator.py](C:/Users/21462/Desktop/new/EvoSim/src/runtime/orchestrator.py)
- [src/runtime/control_state.py](C:/Users/21462/Desktop/new/EvoSim/src/runtime/control_state.py)
- [src/simulation.py](C:/Users/21462/Desktop/new/EvoSim/src/simulation.py)
- [src/main.py](C:/Users/21462/Desktop/new/EvoSim/src/main.py)
- [src/run_control_server.py](C:/Users/21462/Desktop/new/EvoSim/src/run_control_server.py)
- [tests/runtime/test_contracts.py](C:/Users/21462/Desktop/new/EvoSim/tests/runtime/test_contracts.py)
- [tests/runtime/test_registry.py](C:/Users/21462/Desktop/new/EvoSim/tests/runtime/test_registry.py)
- [tests/runtime/test_orchestrator_smoke.py](C:/Users/21462/Desktop/new/EvoSim/tests/runtime/test_orchestrator_smoke.py)

这批改完后，再决定是先接平台模块还是先拆 agent skill。
