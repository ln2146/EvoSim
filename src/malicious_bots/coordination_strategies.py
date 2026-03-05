"""
CoordinationStrategy - 恶意水军协同策略系统

定义三种可选的攻击协同模式：
    SWARM     (蜂群式) : 全部 bot 集中攻击同一目标 + cross-like（默认，与现有行为等价）
    DISPERSED (游离式) : bot 随机分散到多条帖子，低组织度攻击
    CHAIN     (链式)   : 三层结构（LeaderBot → AmplifierBot → CommentFloodBot）

当前已实现：
    - CoordinationMode 枚举
    - SwarmStrategy（复用现有 coordinate_attack 逻辑，叠加角色分配）
    - DispersedStrategy（Step 3）

待实现（后续 Step 4）：
    - ChainStrategy + AttackBlackboard
"""

import asyncio
import logging
import random
from enum import Enum
from typing import List, Dict, Any, Optional

from .bot_role_overlay import assign_bot_roles

logger = logging.getLogger(__name__)


# ─── 策略枚举 ──────────────────────────────────────────────────────────────────

class CoordinationMode(Enum):
    """
    攻击协同模式。

    在 MaliciousBotConfig.coordination_mode 中设置：
        CoordinationMode.SWARM     - 蜂群式（默认）
        CoordinationMode.DISPERSED - 游离式
        CoordinationMode.CHAIN     - 链式传播
    """
    DISPERSED = "dispersed"  # 游离式：低组织度，随机分散到多条帖子
    SWARM     = "swarm"      # 蜂群式：集中火力攻击单一目标（当前默认行为）
    CHAIN     = "chain"      # 链式传播：三层结构，参考 MultiAgent4Collusion


# ─── 蜂群式策略 ────────────────────────────────────────────────────────────────

class SwarmStrategy:
    """
    蜂群式攻击策略（Swarm）。

    行为特征：
    - 全部 cluster_size 个 bot 集中攻击同一目标帖子
    - 通过 assign_bot_roles() 注入三种战术角色（Agitator / ConcernTroll / Spammer）
    - 执行 cross-like，操控推荐算法的热度评分
    - 与现有 SimpleMaliciousCluster.coordinate_attack() 完全等价，是其规范化封装

    这是 Step 2 的实现，已完全覆盖现有功能并新增角色分化能力。
    """

    async def execute(
        self,
        target_post_id: str,
        target_content: str,
        cluster_size: int,
        bot_cluster,
        role_distribution: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        执行蜂群式攻击。

        Args:
            target_post_id   : 目标帖子 ID
            target_content   : 目标帖子内容（用于生成评论提示词）
            cluster_size     : 本轮参与攻击的 bot 数量
            bot_cluster      : SimpleMaliciousCluster 实例
            role_distribution: 角色分布比例字典，如 {"agitator": 0.4, ...}

        Returns:
            List[Dict]: 每个 bot 生成的评论结果，结构同 coordinate_attack() 返回值。
            每条记录新增 "bot_role" 和 "disguise_level" 字段（来自 RoleOverlay）。
        """
        # 生成角色分配列表
        # 用 dummy list 生成 cluster_size 个角色覆盖配置（无需真实 persona）
        dummy_personas = [None] * cluster_size
        paired = assign_bot_roles(dummy_personas, role_distribution)
        role_overlays = [overlay for _, overlay in paired]

        # 统计角色分布，写入日志
        role_counts = {}
        for overlay in role_overlays:
            role_name = overlay.role.value
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        logger.info(
            f"[SwarmStrategy] Attacking post {target_post_id} | "
            f"cluster_size={cluster_size} | roles={role_counts}"
        )

        # 调用 bot_cluster.coordinate_attack（已支持 role_overlays 参数）
        responses = await bot_cluster.coordinate_attack(
            target_post_id=target_post_id,
            target_content=target_content,
            attack_size=cluster_size,
            role_overlays=role_overlays,
        )

        return responses


# ─── 游离式策略（Step 3） ──────────────────────────────────────────────────────

# 游离式默认角色分布：Agitator 为主，无 ConcernTroll（低组织度场景不需要精密伪装）
_DISPERSED_DEFAULT_ROLE_DIST: Dict[str, float] = {
    "agitator": 0.60,
    "concern_troll": 0.00,
    "spammer": 0.40,
}

# 每条帖子分配的 bot 数量范围
_DISPERSED_MIN_BOTS_PER_POST = 3
_DISPERSED_MAX_BOTS_PER_POST = 5


class DispersedStrategy:
    """
    游离式攻击策略（Dispersed）。

    行为特征：
    - 无中心协调，bot 随机分散到多条帖子（模拟低组织度的自发性舆论攻击）
    - 每条帖子最多分配 3~5 个 bot，避免集中轰炸被审核系统识别
    - 不执行 cross-like（无协调互动）
    - 角色以 Agitator 为主（60%），Spammer 为辅（40%）
    - 若 post_pool 过小（仅 1 条），则等同于 swarm 但不执行 cross-like

    与 MultiAgent4Collusion 对应：类似 bad_type="bad" 的默认行为，
    agents 各自独立行动，没有共享任务黑板。
    """

    async def execute(
        self,
        post_pool: List[Dict[str, Any]],
        cluster_size: int,
        bot_cluster,
        role_distribution: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        执行游离式攻击：将 cluster_size 个 bot 随机分散到 post_pool 中的多条帖子。

        Args:
            post_pool        : 候选帖子列表，每条格式为 {"post_id": str, "content": str, ...}
            cluster_size     : 本轮参与攻击的 bot 总数
            bot_cluster      : SimpleMaliciousCluster 实例
            role_distribution: 角色比例，None 则使用游离式默认值（agitator 60% / spammer 40%）

        Returns:
            所有子组攻击结果的合并列表，格式同 SwarmStrategy 返回值。
            每条记录额外包含 "target_post_id" 字段，标明该评论属于哪条帖子。
        """
        if not post_pool:
            logger.warning("[DispersedStrategy] post_pool is empty, aborting.")
            return []

        dist = role_distribution if role_distribution is not None else _DISPERSED_DEFAULT_ROLE_DIST

        # ── 将 cluster_size 个 bot 分组，随机分配给 post_pool 中的帖子 ──────────
        assignments = self._assign_bots_to_posts(post_pool, cluster_size)

        # 统计日志
        logger.info(
            f"[DispersedStrategy] cluster_size={cluster_size} | "
            f"posts_targeted={len(assignments)} / {len(post_pool)} | "
            f"groups={[(p['post_id'], n) for p, n in assignments]}"
        )

        # ── 并发执行各子组攻击（无协调，真正游离式） ──────────────────────────
        tasks = []
        for target_post, group_size in assignments:
            tasks.append(
                self._attack_single_post(
                    target_post=target_post,
                    group_size=group_size,
                    bot_cluster=bot_cluster,
                    role_distribution=dist,
                )
            )

        group_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果，过滤异常
        all_results: List[Dict[str, Any]] = []
        for i, result in enumerate(group_results):
            if isinstance(result, Exception):
                target_id = assignments[i][0].get("post_id", "?")
                logger.warning(
                    f"[DispersedStrategy] Group targeting post {target_id} failed: {result}"
                )
            else:
                all_results.extend(result)

        logger.info(
            f"[DispersedStrategy] Done | "
            f"total_comments={len(all_results)} across {len(assignments)} posts"
        )
        return all_results

    # ── 私有方法 ────────────────────────────────────────────────────────────────

    def _assign_bots_to_posts(
        self,
        post_pool: List[Dict[str, Any]],
        cluster_size: int,
    ) -> List[tuple]:
        """
        将 cluster_size 个 bot 随机分配到 post_pool 的多条帖子中。

        策略：
        1. 随机打乱 post_pool，逐条帖子随机分配 3~5 个 bot。
        2. 分配至 cluster_size 耗尽为止；若 post_pool 不够分，剩余 bot 追加到随机帖子上
           （但仍限制每条帖子最多 _DISPERSED_MAX_BOTS_PER_POST 个）。
        3. 若 post_pool 只有 1 条帖子，所有 bot 攻击该帖（退化为无 cross-like 的 swarm）。

        Returns:
            [(post_dict, bot_count), ...] 列表，仅包含 bot_count > 0 的帖子。
        """
        if len(post_pool) == 1:
            return [(post_pool[0], cluster_size)]

        shuffled_posts = list(post_pool)
        random.shuffle(shuffled_posts)

        assignments: List[tuple] = []
        remaining = cluster_size

        for post in shuffled_posts:
            if remaining <= 0:
                break
            # 每组随机分配 3~5 个 bot，不超过剩余数量
            group_size = random.randint(
                _DISPERSED_MIN_BOTS_PER_POST,
                _DISPERSED_MAX_BOTS_PER_POST,
            )
            group_size = min(group_size, remaining)
            assignments.append((post, group_size))
            remaining -= group_size

        # 如果还有剩余 bot（post_pool 全部遍历完仍有剩余），随机追加到已有目标
        if remaining > 0 and assignments:
            random.shuffle(assignments)
            for i in range(len(assignments)):
                post, count = assignments[i]
                can_add = _DISPERSED_MAX_BOTS_PER_POST - count
                if can_add <= 0:
                    continue
                add = min(can_add, remaining)
                assignments[i] = (post, count + add)
                remaining -= add
                if remaining <= 0:
                    break

        return assignments

    async def _attack_single_post(
        self,
        target_post: Dict[str, Any],
        group_size: int,
        bot_cluster,
        role_distribution: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        用 group_size 个 bot 攻击单条帖子，返回评论结果列表。
        不执行 cross-like（游离式的核心特征）。
        """
        post_id = target_post.get("post_id", "")
        content = target_post.get("content", "")

        # 分配角色（用 dummy personas 只为生成 role_overlays）
        dummy_personas = [None] * group_size
        paired = assign_bot_roles(dummy_personas, role_distribution)
        role_overlays = [overlay for _, overlay in paired]

        role_counts = {}
        for overlay in role_overlays:
            role_name = overlay.role.value
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        logger.debug(
            f"[DispersedStrategy] post={post_id} | group_size={group_size} | roles={role_counts}"
        )

        # 调用 coordinate_attack，传入 role_overlays；不调用 cross-like
        responses = await bot_cluster.coordinate_attack(
            target_post_id=post_id,
            target_content=content,
            attack_size=group_size,
            role_overlays=role_overlays,
        )

        # 为每条结果注入 target_post_id，方便上层聚合统计
        for r in responses:
            r["target_post_id"] = post_id

        return responses


# ─── 链式传播策略（Stub，Step 4 实现） ─────────────────────────────────────────

class ChainStrategy:
    """
    链式传播攻击策略（Chain）——待实现（Step 4）。

    行为特征：
    - 三层水军结构：LeaderBot → AmplifierBot → CommentFloodBot
    - 通过 AttackBlackboard 协调各层执行顺序
    - LeaderBot 伪造高 followers_count 大V身份，首先发帖
    - AmplifierBot 转发 LeaderBot 帖子，添加情绪化评论
    - CommentFloodBot 在 LeaderBot 帖子下批量评论 + cross-like
    """

    async def execute(self, *args, **kwargs):
        raise NotImplementedError(
            "ChainStrategy not yet implemented. "
            "Set coordination_mode = CoordinationMode.SWARM to use the current default."
        )
