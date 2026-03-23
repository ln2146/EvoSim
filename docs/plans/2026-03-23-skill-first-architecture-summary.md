# Skill-First 架构

## 1. 介绍

当前项目已经有不少模块级拆分，但真正面向 Agent 的能力仍然混在平台主流程里。

这一版不做完整平台重构，只处理一个核心问题：

- 让真正属于 Agent 的部分先形成清晰边界
- 让这些边界变成可调用的运行时结构
- 同时尽量不影响现有平台模块

因此，这份方案不是终局架构，而是一版过渡性的 `skill-first` 方案。

它的目标不是一次性把平台完全解耦，而是先把下面三类东西区分清楚：

- `Agent Skills`
- `Agent Tools`
- `Platform Modules`

## 2. 范围与原则

### 2.1 本方案处理的范围

只处理以下内容：

- 攻击技能
- 防御技能
- 事后干预技能
- 记忆工具
- 检索工具
- skill 调用入口

### 2.2 本方案不处理的范围

下面这些暂时保持原样：

- `recommender`
- `platform-moderation`
- `news-injection`
- `experiment-lifecycle`
- `platform-analytics`
- 完整 runtime / orchestrator / event bus

### 2.3 核心原则

- 平台模块先不强行 skill 化
- skill 只抽真正面向 Agent 的行为能力
- tool 只抽 skill 的共用依赖
- 主循环只改 skill 相关接线点

## 3. 框架设计

### 3.1 三层结构

```text
Simulation
└─ SkillDispatcher
   ├─ Agent Skills
   │  ├─ swarm-attack
   │  ├─ dispersed-attack
   │  ├─ chain-attack
   │  ├─ opinion-balance-defense
   │  └─ fact-checking-skill
   └─ Agent Tools
      ├─ agent-memory
      ├─ evidence-rag
      └─ action-result-log-rag
```

平台模块继续留在原位置，不进入这层结构。

### 3.2 最小运行时对象

建议新增：

```text
src/runtime/
├─ skill_types.py
├─ skill_dispatcher.py
├─ tools/
│  ├─ memory_tool.py
│  ├─ evidence_rag_tool.py
│  └─ action_result_log_tool.py
└─ skills/
   ├─ attack_skill.py
   ├─ defense_skill.py
   └─ fact_checking_skill.py
```

### 3.3 最小契约

不做完整 contracts 系统，只保留最小结构：

- `SkillContext`

  - `tick`
  - `run_id`
  - `flags`
  - `payload`
- `SkillOutcome`

  - `status`
  - `data`
  - `events`
  - `errors`

### 3.4 Dispatcher 职责

`SkillDispatcher` 只做三件事：

- 注册 skill 名称
- 根据名称执行 skill
- 返回统一结果

它不是完整 orchestrator，不负责整个平台 phase 调度。

---

## 4. Skill 与 Tool 设计

### 4.1 Attack Skills

对外保留 3 个 skill 名称：

- `swarm-attack`
- `dispersed-attack`
- `chain-attack`

但内部只保留 1 份实现入口，复用现有 [src/malicious_bots/attack_orchestrator.py](C:/Users/21462/Desktop/new/EvoSim/src/malicious_bots/attack_orchestrator.py)。

也就是说：

- 外部 3 个 skill，便于观察和调用
- 内部 1 个 attack skill handler，按 mode 路由

### 4.2 Defense Skill

把 `opinion-balance-defense` 从 [src/opinion_balance_manager.py](C:/Users/21462/Desktop/new/EvoSim/src/opinion_balance_manager.py) 里抽成统一 skill 入口。

这个 skill 的职责是：

- 接收监测信号
- 组织角色协作
- 调用 memory / rag
- 返回防御动作结果

原 manager 先保留内部逻辑和 DB 记录，不在这一版彻底拆细。

### 4.3 Fact-Checking Skill

把原先偏宽泛的 `post-hoc-intervention` 改成更明确的 `fact-checking-skill`。

这个 skill 从 `Simulation + FactChecker` 的散逻辑中收敛成统一入口。

这个 skill 的职责是：

- 选择待纠偏内容
- 执行事实核查
- 必要时调用证据检索
- 返回纠偏结果

---

### 4.4 Memory Tool

`agent-memory` 不当作 skill，而是做成统一 tool wrapper。

它负责暴露：

- 写记忆
- 取反思
- 取相关经验

内部仍复用 [src/agent_memory.py](C:/Users/21462/Desktop/new/EvoSim/src/agent_memory.py)。

### 4.5 Evidence RAG Tool

证据检索这一部分保留为 `evidence-rag` tool。

它负责暴露：

- `retrieve_evidence`

它只负责事实论据、证据包、外部依据，不负责历史行动经验。

同时保留一个最关键约束：

- 禁止缺省 type
- 禁止隐式 fallback 到策略检索

内部仍复用 [src/advanced_rag_system.py](C:/Users/21462/Desktop/new/EvoSim/src/advanced_rag_system.py)。

### 4.6 Action-Result Log Tool

原来写在 `RAG Tool` 里的另一半，更适合单独表达成“行动-结果日志检索”。

这个 tool 负责暴露：

- `retrieve_action_results`
- `retrieve_strategy_cases`

它服务的是：

- 历史动作
- 历史结果
- 可复用的策略经验

这部分不应再和事实证据混成一个检索概念。

---

## 5. 需要做的调整

### 5.1 新增最小 runtime 目录

新增：

- `src/runtime/skill_types.py`
- `src/runtime/skill_dispatcher.py`
- `src/runtime/tools/*`
- `src/runtime/skills/*`

### 5.2 调整攻击入口

调整 [src/malicious_bots/malicious_bot_manager.py](C:/Users/21462/Desktop/new/EvoSim/src/malicious_bots/malicious_bot_manager.py)：

- 不再把它当成外部 skill 调用入口
- 让它退回到“攻击执行/数据落库”的角色

### 5.3 调整防御入口

调整 [src/opinion_balance_manager.py](C:/Users/21462/Desktop/new/EvoSim/src/opinion_balance_manager.py)：

- 保留内部 helper 和 DB 逻辑
- 对外 skill 入口迁移到 `defense_skill.py`

### 5.4 调整干预入口

调整 [src/fact_checker.py](C:/Users/21462/Desktop/new/EvoSim/src/fact_checker.py) 和 [src/simulation.py](C:/Users/21462/Desktop/new/EvoSim/src/simulation.py)：

- 事实核查不再由 `Simulation` 直接铺开调用
- 统一改为 `fact_checking_skill.py`

### 5.5 调整主循环接线

调整 [src/simulation.py](C:/Users/21462/Desktop/new/EvoSim/src/simulation.py)：

- 初始化 `SkillDispatcher`
- 注册 5 个 skill
- 在攻击、防御、事实核查位置改为 dispatcher 调用

除此之外，其余平台逻辑先不动。

---

## 6. 推荐顺序

建议按这个顺序推进：

1. 建 `skill_types.py`
2. 建 `skill_dispatcher.py`
3. 建 `memory_tool.py`
4. 建 `evidence_rag_tool.py`
5. 建 `action_result_log_tool.py`
6. 建 `attack_skill.py`
7. 建 `defense_skill.py`
8. 建 `fact_checking_skill.py`
9. 改 `simulation.py` 接线

这个顺序的核心目的是：

- 先有壳层
- 再有工具
- 再抽技能
- 最后改主循环

---

## 7. 完成后的结果

如果这一版做完，你会得到：

- skill 和 platform module 的边界清楚了
- tool 和 skill 的边界清楚了
- 5 个真正的 Agent Skill 有统一入口了
- 证据检索和行动-结果日志检索不再混在一个 tool 语义里
- 后续继续做完整 runtime 时，有稳定的起点
