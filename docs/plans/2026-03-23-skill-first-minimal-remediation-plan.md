# Skill-First Minimal Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不重构整个平台模块的前提下，先把 EvoSim 中真正面向 agent 的 5 个技能独立出来，并补上最小 tool 层与 dispatcher，使 skill 边界变成真实存在的运行时边界。

**Architecture:** 保持 `recommender`、`platform-moderation`、`news-injection`、`experiment-lifecycle` 等平台模块原样不动，只新增一层轻量 `runtime/skills + runtime/tools + runtime/dispatcher`。`Simulation` 只做最小接线修改，把攻击、防御、事后干预改成走统一 dispatcher；其他流程仍保留原逻辑。

**Tech Stack:** Python, asyncio, sqlite3, dataclasses, existing `src/*` modules

## 1. 方案边界

### 本方案处理的内容

- 5 个 `Agent Skill`
- 2 个 `Agent Tool`
- 1 个最小 skill dispatcher
- `Simulation` 中与 skill 直接相关的接线点

### 本方案明确不处理的内容

- 不重构推荐系统
- 不重构审核系统
- 不重构快照系统
- 不引入完整 registry / orchestrator / event bus
- 不全面去掉 `control_flags`
- 不一次性清理所有 SQL 直写

### 本方案要达到的效果

- skill 不再只是概念命名，而是真有统一入口
- tool 不再散落在 skill 内部直接调用
- 主循环不再直接嵌入大块攻击/防御/事后干预逻辑
- 后续如果继续做全架构整改，这一层不会推倒重来

---

## 2. 最小目标架构

```text
Simulation
└─ SkillDispatcher
   ├─ Agent Skills
   │  ├─ swarm-attack
   │  ├─ dispersed-attack
   │  ├─ chain-attack
   │  ├─ opinion-balance-defense
   │  └─ post-hoc-intervention
   └─ Agent Tools
      ├─ agent-memory
      └─ evidence-rag

Platform modules remain unchanged:
- recommender
- platform-moderation
- news-injection
- experiment-lifecycle
- platform-analytics
```

---

## 3. 需要落地的对象

### 3.1 Agent Skills（5）

1. `swarm-attack`
2. `dispersed-attack`
3. `chain-attack`
4. `opinion-balance-defense`
5. `post-hoc-intervention`

### 3.2 Agent Tools（2）

6. `agent-memory`
7. `evidence-rag`

### 3.3 Runtime Glue（1）

8. `skill-dispatcher`

---

## 4. 目录设计

新增目录：

```text
src/runtime/
├─ __init__.py
├─ skill_types.py
├─ skill_dispatcher.py
├─ tools/
│  ├─ __init__.py
│  ├─ memory_tool.py
│  └─ rag_tool.py
└─ skills/
   ├─ __init__.py
   ├─ attack_skill.py
   ├─ defense_skill.py
   └─ intervention_skill.py
```

说明：

- 攻击层对外保留 3 个 skill 名称，但实现层不拆成 3 份文件
- `attack_skill.py` 内部按 mode 路由
- `defense_skill.py` 对应 `opinion-balance-defense`
- `intervention_skill.py` 对应 `post-hoc-intervention`

---

## 5. 契约范围

本方案不需要完整 runtime contracts，但需要一个最小 skill 契约。

### 5.1 最小请求结构

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SkillContext:
    tick: int
    run_id: str
    flags: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
```

### 5.2 最小结果结构

```python
@dataclass
class SkillOutcome:
    status: str  # ok | skip | error
    data: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
```

### 5.3 最小 dispatcher 接口

```python
class SkillDispatcher:
    async def run(self, name: str, context: SkillContext) -> SkillOutcome:
        ...
```

---

## 6. 文件级实施计划

### Task 1: 建立最小 runtime 目录与类型

**Files:**
- Create: `src/runtime/__init__.py`
- Create: `src/runtime/skill_types.py`
- Test: `tests/runtime/test_skill_types.py`

**Step 1: 写失败测试**

```python
from src.runtime.skill_types import SkillContext, SkillOutcome

def test_skill_types_can_be_instantiated():
    context = SkillContext(tick=1, run_id="r1")
    outcome = SkillOutcome(status="ok")
    assert context.tick == 1
    assert outcome.status == "ok"
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/runtime/test_skill_types.py -v`

Expected: import error or module not found

**Step 3: 写最小实现**

在 `src/runtime/skill_types.py` 中定义 `SkillContext` 与 `SkillOutcome`。

**Step 4: 运行测试确认通过**

Run: `pytest tests/runtime/test_skill_types.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/runtime/__init__.py src/runtime/skill_types.py tests/runtime/test_skill_types.py
git commit -m "feat: add minimal skill runtime types"
```

---

### Task 2: 建立 Skill Dispatcher

**Files:**
- Create: `src/runtime/skill_dispatcher.py`
- Test: `tests/runtime/test_skill_dispatcher.py`

**Step 1: 写失败测试**

```python
import pytest
from src.runtime.skill_dispatcher import SkillDispatcher
from src.runtime.skill_types import SkillContext

@pytest.mark.asyncio
async def test_dispatcher_runs_registered_skill():
    dispatcher = SkillDispatcher()

    async def handler(context):
        return {"status": "ok"}

    dispatcher.register("demo-skill", handler)
    result = await dispatcher.run("demo-skill", SkillContext(tick=1, run_id="r1"))
    assert result.status == "ok"
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/runtime/test_skill_dispatcher.py -v`

**Step 3: 写最小实现**

`SkillDispatcher` 只需要支持：

- `register(name, handler)`
- `run(name, context)`
- 未注册 skill 时报明确错误

**Step 4: 运行测试确认通过**

Run: `pytest tests/runtime/test_skill_dispatcher.py -v`

**Step 5: Commit**

```bash
git add src/runtime/skill_dispatcher.py tests/runtime/test_skill_dispatcher.py
git commit -m "feat: add minimal skill dispatcher"
```

---

### Task 3: 建立 Agent Tools Wrapper

**Files:**
- Create: `src/runtime/tools/__init__.py`
- Create: `src/runtime/tools/memory_tool.py`
- Create: `src/runtime/tools/rag_tool.py`
- Modify: `src/advanced_rag_system.py`
- Reference: `src/agent_memory.py`
- Test: `tests/runtime/test_memory_tool.py`
- Test: `tests/runtime/test_rag_tool.py`

**Step 1: Memory tool 统一入口**

包装目标：

- `add_memory`
- `get_cached_reflection`
- `get_relevant_memories`

Memory tool 不重写内部存储逻辑，只提供统一调用面。

**Step 2: RAG tool 统一入口**

包装目标：

- `retrieve_evidence(...)`
- `retrieve_strategy(...)`

同时补最小强约束：

- 非法 `type` 直接报错
- 禁止隐式走默认 mixed 模式

**Step 3: 写测试**

至少验证：

- memory tool 能代理到现有实现
- rag tool 对 `evidence/strategy` 之外的类型报错

**Step 4: Commit**

```bash
git add src/runtime/tools src/advanced_rag_system.py tests/runtime/test_memory_tool.py tests/runtime/test_rag_tool.py
git commit -m "feat: add agent tool wrappers"
```

---

### Task 4: 建立 Attack Skill

**Files:**
- Create: `src/runtime/skills/__init__.py`
- Create: `src/runtime/skills/attack_skill.py`
- Reference: `src/malicious_bots/attack_orchestrator.py`
- Modify: `src/malicious_bots/malicious_bot_manager.py`
- Test: `tests/runtime/test_attack_skill.py`

**Step 1: 定义外部 skill 名称**

Dispatcher 层对外保留：

- `swarm-attack`
- `dispersed-attack`
- `chain-attack`

**Step 2: 内部统一复用 orchestrator**

不要复制三套攻击逻辑。

`attack_skill.py` 内部按 `mode` 路由到现有 [attack_orchestrator.py](C:/Users/21462/Desktop/new/EvoSim/src/malicious_bots/attack_orchestrator.py)。

**Step 3: 修改 manager，只保留 orchestration/data access 职责**

`MaliciousBotManager` 不再同时充当“平台入口 + skill 入口”。
第一阶段只把对外触发入口让给 `attack_skill.py`。

**Step 4: 测试**

验证：

- 3 个外部 skill 名称能调到统一实现
- mode 不同，输出路径不同

**Step 5: Commit**

```bash
git add src/runtime/skills/attack_skill.py src/malicious_bots/malicious_bot_manager.py tests/runtime/test_attack_skill.py
git commit -m "feat: extract attack skill entrypoint"
```

---

### Task 5: 建立 Defense Skill

**Files:**
- Create: `src/runtime/skills/defense_skill.py`
- Modify: `src/opinion_balance_manager.py`
- Reference: `src/agents/simple_coordination_system.py`
- Test: `tests/runtime/test_defense_skill.py`

**Step 1: 抽出 defense skill 入口**

把下面职责变成 skill handler：

- 接收监测信号
- 组织角色协作
- 调用 memory / rag tool
- 返回干预结果

**Step 2: OpinionBalanceManager 保留什么**

保留：

- 现有 DB 记录逻辑
- 原有内部 helper
- 协调系统实例持有

移出：

- 对外统一 skill 入口
- 直接由 `Simulation` 驱动的行为触发

**Step 3: 测试**

验证：

- skill handler 能调用现有 manager
- 缺失前置条件时显式返回 `skip` 或 `error`

**Step 4: Commit**

```bash
git add src/runtime/skills/defense_skill.py src/opinion_balance_manager.py tests/runtime/test_defense_skill.py
git commit -m "feat: extract opinion balance defense skill"
```

---

### Task 6: 建立 Post-Hoc Intervention Skill

**Files:**
- Create: `src/runtime/skills/intervention_skill.py`
- Modify: `src/simulation.py`
- Modify: `src/fact_checker.py`
- Test: `tests/runtime/test_intervention_skill.py`

**Step 1: 抽出事后干预入口**

当前 `Simulation` 中 fact-check 相关逻辑较散，需要收敛成一个统一 skill handler。

skill 负责：

- 选择待纠偏内容
- 调用事实核查逻辑
- 必要时调用 `rag_tool.retrieve_evidence`
- 返回纠偏结果

**Step 2: 保持平台其它逻辑不动**

不重构 moderation、snapshot、analytics。

**Step 3: 测试**

验证：

- 开关关闭时返回 `skip`
- 存在待纠偏内容时能执行真实流程

**Step 4: Commit**

```bash
git add src/runtime/skills/intervention_skill.py src/simulation.py src/fact_checker.py tests/runtime/test_intervention_skill.py
git commit -m "feat: extract post hoc intervention skill"
```

---

### Task 7: 在 Simulation 中接入最小 Skill Dispatcher

**Files:**
- Modify: `src/simulation.py`
- Test: `tests/runtime/test_simulation_skill_dispatch.py`

**Step 1: 初始化 dispatcher**

在 `Simulation.__init__` 中：

- 创建 `SkillDispatcher`
- 注册 5 个 skill 名称
- 注入需要的 tool wrapper

**Step 2: 只替换 skill 相关调用点**

替换：

- 攻击触发逻辑
- 防御触发逻辑
- 事后干预逻辑

保留：

- 推荐
- 审核
- 快照
- 新闻注入
- 分析

**Step 3: 测试**

验证：

- 主循环能通过 dispatcher 调 skill
- 未开启 skill 时不影响其余平台链路

**Step 4: Commit**

```bash
git add src/simulation.py tests/runtime/test_simulation_skill_dispatch.py
git commit -m "feat: wire simulation to skill dispatcher"
```

---

## 7. 建议的最小实现顺序

如果要控制风险，建议按这个顺序推进：

1. `skill_types`
2. `skill_dispatcher`
3. `memory_tool`
4. `rag_tool`
5. `attack_skill`
6. `defense_skill`
7. `intervention_skill`
8. `simulation` 接线

理由：

- 前四步先把运行时壳层和依赖面搭起来
- 后三步再逐个抽 skill
- 最后一步才改主循环，降低回归风险

---

## 8. 验收标准

本方案完成后，至少满足以下条件：

### 8.1 结构层面

- 存在独立 `src/runtime/skills/`
- 存在独立 `src/runtime/tools/`
- skill 有统一 dispatcher 入口

### 8.2 行为层面

- 3 种攻击模式可通过 skill 名称调用
- 防御技能可通过统一 skill 入口触发
- 事后干预可通过统一 skill 入口触发

### 8.3 回归层面

- 推荐链路不受影响
- 审核链路不受影响
- 快照链路不受影响

### 8.4 语义层面

- skill 不再和平台模块混用
- tool 不再伪装成 skill

---

## 9. 风险与约束

### 风险 1：只抽 skill 名字，没形成真实边界

缓解：

- 必须有 dispatcher
- 必须有 tool wrapper
- `Simulation` 必须改为调用 dispatcher，而不是继续直接调旧逻辑

### 风险 2：skill 内部反而复制原逻辑

缓解：

- 攻击 skill 必须复用现有 orchestrator
- 防御 skill 必须复用现有 manager / coordination system
- 干预 skill 必须复用现有 fact-check 逻辑

### 风险 3：tool wrapper 只是薄壳，没有约束价值

缓解：

- `rag_tool` 必须增加 `type` 强约束
- memory tool 必须成为 skill 访问记忆的唯一入口

### 风险 4：改动 `Simulation` 过多导致牵一发而动全身

缓解：

- 只改 skill 相关调用点
- 其余平台模块暂时不动

---

## 10. 本方案不该做的事

- 不要顺手把 `recommender` 也塞进 skill
- 不要顺手重构 `platform-moderation`
- 不要同时推进完整 runtime registry
- 不要在这轮里解决所有 SQL 直写
- 不要把 `control_flags` 全部重写

如果做了这些，这就不再是“方案二”，而会重新膨胀成全架构整改。

---

## 11. 预计收益

完成本方案后，你会得到：

- 一套真实存在的 `Agent Skill` 边界
- 一套最小可用的 `Agent Tool` 边界
- skill 与 platform module 的语义分离
- 后续继续做 runtime / contracts / registry 时的稳定起点

但你不会立刻得到：

- 完整可插拔平台
- 完整 phase orchestration
- 完整 persistence 解耦
- 完整 control plane 重构

所以这是一个“先把 skill 做真”的过渡方案，不是假装一步到位的终局方案。

---

## 12. 第一批建议改动文件

第一批建议只动这些文件：

- `src/runtime/__init__.py`
- `src/runtime/skill_types.py`
- `src/runtime/skill_dispatcher.py`
- `src/runtime/tools/__init__.py`
- `src/runtime/tools/memory_tool.py`
- `src/runtime/tools/rag_tool.py`
- `src/runtime/skills/__init__.py`
- `src/runtime/skills/attack_skill.py`
- `src/runtime/skills/defense_skill.py`
- `src/runtime/skills/intervention_skill.py`
- `src/simulation.py`
- `src/opinion_balance_manager.py`
- `src/malicious_bots/malicious_bot_manager.py`
- `src/advanced_rag_system.py`
- `src/fact_checker.py`
- `tests/runtime/test_skill_types.py`
- `tests/runtime/test_skill_dispatcher.py`
- `tests/runtime/test_memory_tool.py`
- `tests/runtime/test_rag_tool.py`
- `tests/runtime/test_attack_skill.py`
- `tests/runtime/test_defense_skill.py`
- `tests/runtime/test_intervention_skill.py`
- `tests/runtime/test_simulation_skill_dispatch.py`

这批改完，就可以判断“skill-first”这条路径是否成立，再决定要不要继续做全面 runtime 整改。
