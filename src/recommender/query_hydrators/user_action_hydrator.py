"""
用户行为水合器

阶段1: 获取用户关注列表和屏蔽列表
"""

from ..types import UserContext
from ..repositories.user_repository import UserRepository


class UserActionHydrator:
    """
    用户行为水合器

    获取用户的社交图谱信息（关注、屏蔽）
    """

    def __init__(self):
        self.user_repo = UserRepository()

    def hydrate(self, user_id: str) -> UserContext:
        """
        水合用户上下文

        Args:
            user_id: 用户 ID

        Returns:
            填充了关注和屏蔽信息的 UserContext
        """
        # 获取关注列表
        followed_ids = self.user_repo.get_followed_ids(user_id)

        # 获取屏蔽列表
        blocked_ids = self.user_repo.get_blocked_users(user_id)

        # 获取屏蔽关键词
        muted_keywords = self.user_repo.get_muted_keywords(user_id)

        # 获取已曝光帖子
        seen_post_ids = self.user_repo.get_exposed_post_ids(user_id)

        # 获取最近交互
        recent_interactions = self.user_repo.get_recent_interactions(user_id)

        return UserContext(
            user_id=user_id,
            followed_ids=followed_ids,
            blocked_ids=blocked_ids,
            muted_keywords=muted_keywords,
            seen_post_ids=seen_post_ids,
            recent_interactions=recent_interactions,
        )
