"""
用户特征水合器

阶段1: 获取用户画像和 Embedding
"""

from typing import Optional, List
from ..types import UserContext
from ..repositories.user_repository import UserRepository


class UserFeaturesHydrator:
    """
    用户特征水合器

    获取用户画像信息，可选计算 persona embedding
    """

    def __init__(self, embedding_manager=None):
        """
        初始化

        Args:
            embedding_manager: 可选的 EmbeddingManager 实例
        """
        self.user_repo = UserRepository()
        self.embedding_manager = embedding_manager

    def set_embedding_manager(self, embedding_manager):
        """设置 EmbeddingManager"""
        self.embedding_manager = embedding_manager

    def hydrate(self, user_context: UserContext) -> UserContext:
        """
        水合用户特征

        Args:
            user_context: 已有的用户上下文

        Returns:
            填充了画像信息的 UserContext
        """
        # 获取用户画像
        persona_data = self.user_repo.get_user_persona(user_context.user_id)

        if persona_data:
            user_context.persona = persona_data.get('persona')

            # 如果有 embedding manager，计算 persona embedding
            if self.embedding_manager and user_context.persona:
                user_context.persona_embedding = self._compute_persona_embedding(
                    user_context.persona
                )

        return user_context

    def _compute_persona_embedding(self, persona: str) -> Optional[List[float]]:
        """
        计算 persona 的 embedding

        Args:
            persona: 用户画像文本

        Returns:
            embedding 向量

        Raises:
            RuntimeError: If embedding_manager is not set or encoding fails
        """
        # NO FALLBACK: Require embedding_manager to be set
        if not self.embedding_manager:
            raise RuntimeError(
                "UserFeaturesHydrator._compute_persona_embedding() called but embedding_manager is None. "
                "Either disable embedding in config or ensure embedding_manager is properly initialized."
            )

        # NO FALLBACK: Propagate encoding errors instead of returning None
        return self.embedding_manager.encode_text(persona)
