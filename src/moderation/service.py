"""
审核服务核心

遵循 AGENT_ENVIRONMENT_SPEC.md: Service 层协调业务逻辑
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from .types import (
    ModerationVerdict,
    ModerationAction,
    ModerationSeverity,
    ModerationStats,
)
from .config import ModerationConfig
from .providers import CompositeProvider
from .actions import (
    VisibilityDegradationAction,
    WarningLabelAction,
    HardTakedownAction,
)
from .repository import get_repository


logger = logging.getLogger(__name__)


class ModerationService:
    """
    审核服务核心

    职责:
    1. 接收待审核内容
    2. 调用审核提供者
    3. 根据配置确定干预动作
    4. 执行干预动作
    5. 记录审核结果
    """

    def __init__(self, config: ModerationConfig = None):
        """
        初始化审核服务

        Args:
            config: 审核配置
        """
        self.config = config or ModerationConfig()
        self.repository = get_repository()
        self.provider = None
        self.actions = {}

        # 统计
        self.stats = ModerationStats()

        # 初始化组件
        self._init_components()

    def _init_components(self):
        """初始化提供者和动作"""
        # 初始化提供者
        if self.config.enabled:
            self.provider = CompositeProvider(self.config)
            logger.info("Composite moderation provider initialized")

        # 初始化动作
        self.actions = {
            ModerationAction.VISIBILITY_DEGRADATION: VisibilityDegradationAction(
                self.config.actions
            ),
            ModerationAction.WARNING_LABEL: WarningLabelAction(
                self.config.actions
            ),
            ModerationAction.HARD_TAKEDOWN: HardTakedownAction(
                self.config.actions
            ),
        }

        logger.info(f"ModerationService initialized (enabled={self.config.enabled})")

    def check_post(
        self,
        post_id: str,
        user_id: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """
        检查单个帖子

        Args:
            post_id: 帖子 ID
            user_id: 用户 ID
            content: 帖子内容
            metadata: 额外元数据

        Returns:
            审核裁决，None 表示不需要干预
        """
        # NO FALLBACK: Require service to be enabled and provider initialized
        if not self.config.enabled:
            raise RuntimeError(f"ModerationService is not enabled but check_post() was called for post {post_id}")
        if not self.provider:
            raise RuntimeError(f"ModerationProvider not initialized but check_post() was called for post {post_id}")

        # 更新统计
        self.stats.total_checked += 1

        # 1. 调用审核提供者
        verdict = self.provider.check(content, metadata)

        if verdict is None:
            return None

        # 填充基础信息
        verdict.post_id = post_id
        verdict.user_id = user_id

        # 2. 确定干预动作
        action = self._determine_action(verdict)

        if action == ModerationAction.NONE:
            return None

        verdict.action = action

        # 3. 设置动作参数
        self._setup_action_params(verdict)

        # 4. 执行干预动作
        success = self._execute_action(verdict)

        if success:
            # 5. 记录
            self.repository.save(verdict)

            # 更新统计
            self.stats.total_flagged += 1
            self.stats.action_counts[action] = (
                self.stats.action_counts.get(action, 0) + 1
            )
            self.stats.severity_counts[verdict.severity] = (
                self.stats.severity_counts.get(verdict.severity, 0) + 1
            )
            self.stats.category_counts[verdict.category] = (
                self.stats.category_counts.get(verdict.category, 0) + 1
            )

            logger.info(
                f"Moderation action executed: post={post_id}, "
                f"action={action.value}, severity={verdict.severity.value}, "
                f"category={verdict.category.value}"
            )

        return verdict

    def check_batch(self, posts: List[Dict[str, Any]]) -> List[ModerationVerdict]:
        """
        批量检查帖子

        Args:
            posts: 帖子字典列表，每个包含 post_id, user_id, content

        Returns:
            裁决列表
        """
        # NO FALLBACK: Require service to be enabled and provider initialized
        if not self.config.enabled:
            raise RuntimeError("ModerationService is not enabled but check_batch() was called")
        if not self.provider:
            raise RuntimeError("ModerationProvider not initialized but check_batch() was called")

        verdicts = []

        for post in posts:
            verdict = self.check_post(
                post_id=post.get("post_id"),
                user_id=post.get("user_id") or post.get("author_id"),
                content=post.get("content", ""),
                metadata=post,
            )
            if verdict:
                verdicts.append(verdict)

        logger.info(f"Batch moderation completed: {len(verdicts)} actions taken")
        return verdicts

    def check_news_posts(
        self,
        posts: List[Dict[str, Any]],
        min_engagement: int = None
    ) -> List[ModerationVerdict]:
        """
        检查新闻帖子（根据配置）

        Args:
            posts: 帖子列表
            min_engagement: 最小互动数阈值

        Returns:
            裁决列表
        """
        if not self.config.enabled:
            return []

        # 应用互动数阈值
        threshold = min_engagement or self.config.check_threshold_engagement

        # 过滤出需要检查的帖子
        posts_to_check = [
            post for post in posts
            if post.get("is_news", False)
            and (post.get("num_likes", 0) + post.get("num_shares", 0)) >= threshold
        ]

        if not posts_to_check:
            logger.debug(f"No news posts meet engagement threshold {threshold}")
            return []

        logger.info(f"Checking {len(posts_to_check)} news posts (threshold={threshold})")
        return self.check_batch(posts_to_check)

    def _determine_action(self, verdict: ModerationVerdict) -> ModerationAction:
        """
        根据严重程度和置信度确定动作

        Args:
            verdict: 审核裁决

        Returns:
            应采取的动作
        """
        # 检查硬性打击阈值
        for severity, threshold in self.config.actions.takedown_thresholds.items():
            if verdict.severity == severity and verdict.confidence >= threshold:
                return ModerationAction.HARD_TAKEDOWN

        # 使用配置的映射
        return self.config.actions.severity_to_action.get(
            verdict.severity,
            ModerationAction.NONE
        )

    def _setup_action_params(self, verdict: ModerationVerdict):
        """
        设置动作参数

        Args:
            verdict: 审核裁决
        """
        if verdict.action == ModerationAction.VISIBILITY_DEGRADATION:
            verdict.degradation_factor = self.config.actions.visibility_degradation_factors.get(
                verdict.severity, 0.5
            )

        elif verdict.action == ModerationAction.WARNING_LABEL:
            category = verdict.category.value
            verdict.label_text = self.config.actions.warning_labels.get(
                category,
                self.config.actions.warning_labels.get("other", "⚠️ 此内容需谨慎参考")
            )

    def _execute_action(self, verdict: ModerationVerdict) -> bool:
        """
        执行干预动作

        Args:
            verdict: 审核裁决

        Returns:
            是否执行成功
        """
        action_executor = self.actions.get(verdict.action)

        if not action_executor:
            logger.warning(f"No executor for action: {verdict.action}")
            return False

        try:
            return action_executor.execute(verdict)
        except Exception as e:
            logger.error(f"Error executing action {verdict.action}: {e}")
            return False

    def get_stats(self) -> ModerationStats:
        """获取审核统计"""
        return self.stats

    def reset_stats(self):
        """重置统计"""
        self.stats = ModerationStats()

    def get_post_verdicts(self, post_id: str) -> List[ModerationVerdict]:
        """获取帖子的所有审核记录"""
        return self.repository.get_by_post_id(post_id)

    def get_user_verdicts(self, user_id: str, limit: int = 100) -> List[ModerationVerdict]:
        """获取用户的审核记录"""
        return self.repository.get_by_user_id(user_id, limit)

    def is_user_banned(self, user_id: str) -> bool:
        """检查用户是否被封禁"""
        takedown_action = self.actions.get(ModerationAction.HARD_TAKEDOWN)
        if takedown_action:
            return takedown_action.check_user_banned(user_id)
        return False

    def revert_action(self, post_id: str) -> bool:
        """
        撤销帖子的审核动作

        Args:
            post_id: 帖子 ID

        Returns:
            是否成功
        """
        try:
            # 获取最新的审核记录
            verdicts = self.repository.get_by_post_id(post_id)

            if not verdicts:
                logger.warning(f"No moderation record found for post {post_id}")
                return False

            latest_verdict = verdicts[0]

            # 根据动作类型执行撤销
            if latest_verdict.action == ModerationAction.VISIBILITY_DEGRADATION:
                return self.actions[ModerationAction.VISIBILITY_DEGRADATION].revert(post_id)

            elif latest_verdict.action == ModerationAction.WARNING_LABEL:
                return self.actions[ModerationAction.WARNING_LABEL].revert(post_id)

            elif latest_verdict.action == ModerationAction.HARD_TAKEDOWN:
                return self.actions[ModerationAction.HARD_TAKEDOWN].restore_post(post_id)

            return False

        except Exception as e:
            logger.error(f"Error reverting action for post {post_id}: {e}")
            return False


# 单例实例
_service_instance: Optional[ModerationService] = None


def get_service(config: ModerationConfig = None) -> ModerationService:
    """
    获取审核服务单例

    Args:
        config: 配置，首次调用时使用

    Returns:
        审核服务实例
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = ModerationService(config)
    return _service_instance


def reset_service():
    """重置服务单例"""
    global _service_instance
    _service_instance = None
