"""
CoordinationStrategy - 恶意水军协同策略系统

定义三种可选的攻击协同模式：
    SWARM     (蜂群式) : 全部 bot 集中攻击同一目标 + cross-like（默认，与现有行为等价）
    DISPERSED (游离式) : bot 随机分散到多条帖子，低组织度攻击
    CHAIN     (链式)   : 三层结构（LeaderBot → AmplifierBot → CommentFloodBot）

当前已实现：
    - CoordinationMode 枚举
    - SwarmStrategy（复用现有 coordinate_attack 逻辑，叠加角色分配）

待实现（后续 Step 3/4）：
    - DispersedStrategy
    - ChainStrategy + AttackBlackboard
"""

import logging
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


# ─── 游离式策略（Stub，Step 3 实现） ───────────────────────────────────────────

class DispersedStrategy:
    """
    游离式攻击策略（Dispersed）——待实现（Step 3）。

    行为特征：
    - 无中心协调，bot 随机分散到多条帖子
    - 每条帖子最多分配 3~5 个 bot
    - 不执行 cross-like
    - 角色以 Agitator 为主（60%），Spammer 为辅（40%）
    """

    async def execute(
        self,
        post_pool: List[Dict[str, Any]],
        cluster_size: int,
        bot_cluster,
        role_distribution: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "DispersedStrategy not yet implemented. "
            "Set coordination_mode = CoordinationMode.SWARM to use the current default."
        )


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
