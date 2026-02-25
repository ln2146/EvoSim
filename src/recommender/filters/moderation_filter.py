"""
审核过滤集成

将审核系统与推荐系统连接
"""

import logging
from typing import List, Optional

from ...moderation.types import ModerationSeverity, ModerationFilterConfig
from ..types import PostCandidate


logger = logging.getLogger(__name__)


class ModerationFilter:
    """
    审核过滤集成

    在推荐系统中应用审核结果:
    1. 过滤掉已被硬删的帖子
    2. 应用可见性降级（降低推荐权重）
    3. 保留警告标签（用于前端显示）
    """

    def __init__(self, config: ModerationFilterConfig = None):
        """
        初始化审核过滤

        Args:
            config: 过滤配置
        """
        self.config = config or ModerationFilterConfig()

    def filter(
        self,
        candidates: List[PostCandidate],
        apply_degradation: bool = None
    ) -> List[PostCandidate]:
        """
        应用审核过滤

        Args:
            candidates: 候选帖子列表
            apply_degradation: 是否应用降级，None 时使用配置

        Returns:
            过滤后的候选列表
        """
        if not self.config.enabled:
            return candidates

        apply_degradation = (
            apply_degradation
            if apply_degradation is not None
            else self.config.apply_degradation
        )

        filtered = []
        removed_count = 0
        degraded_count = 0

        for candidate in candidates:
            # 1. 过滤已删帖
            if self.config.filter_taken_down and candidate.status == 'taken_down':
                removed_count += 1
                continue

            # 2. 应用可见性降级
            if apply_degradation:
                degraded = self._apply_degradation(candidate)
                if degraded:
                    degraded_count += 1

            # 3. 应用封号用户过滤
            if self._is_user_banned(candidate):
                removed_count += 1
                continue

            filtered.append(candidate)

        if removed_count > 0 or degraded_count > 0:
            logger.debug(
                f"Moderation filter: removed={removed_count}, "
                f"degraded={degraded_count}, remaining={len(filtered)}"
            )

        return filtered

    def _apply_degradation(self, candidate: PostCandidate) -> bool:
        """
        应用可见性降级

        Args:
            candidate: 候选帖子

        Returns:
            是否应用了降级
        """
        # 检查是否有降级系数
        degradation_factor = getattr(
            candidate,
            'moderation_degradation_factor',
            None
        )

        if degradation_factor is not None and degradation_factor < 1.0:
            # 降低最终分数
            candidate.final_score *= degradation_factor
            return True

        return False

    def _is_user_banned(self, candidate: PostCandidate) -> bool:
        """
        检查用户是否被封禁

        Args:
            candidate: 候选帖子

        Returns:
            用户是否被封禁
        """
        # 这里可以检查候选者的用户状态
        # 简化实现：如果需要可以从数据库查询
        return False

    def get_warning_label(self, post_id: str) -> Optional[str]:
        """
        获取帖子的警告标签

        Args:
            post_id: 帖子 ID

        Returns:
            警告标签文字，如果没有则返回 None
        """
        # 这里可以从数据库查询或从候选对象获取
        # 简化实现
        return None

    def get_degradation_factor(self, severity: ModerationSeverity) -> float:
        """
        获取指定严重程度的降级系数

        Args:
            severity: 严重程度

        Returns:
            降级系数
        """
        return self.config.visibility_factors.get(severity, 1.0)

    def set_config(self, config: ModerationFilterConfig):
        """
        更新配置

        Args:
            config: 新配置
        """
        self.config = config
