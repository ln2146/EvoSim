"""
预评分过滤器

阶段4: 在评分前过滤不合格的候选帖子
"""

from typing import List
from ..types import PostCandidate, UserContext
from ..config import FilterConfig


class PreScoringFilters:
    """
    预评分过滤器

    在评分阶段之前过滤掉不合格的候选帖子
    """

    def filter(
        self,
        candidates: List[PostCandidate],
        user_context: UserContext,
        config: FilterConfig
    ) -> List[PostCandidate]:
        """
        应用所有预评分过滤器

        Args:
            candidates: 候选帖子列表
            user_context: 用户上下文
            config: 过滤器配置

        Returns:
            过滤后的候选帖子列表
        """
        filtered = candidates

        # 1. 去重过滤
        filtered = self._drop_duplicates(filtered)

        # 2. 自己帖子过滤
        if config.filter_self_posts:
            filtered = self._filter_self_posts(filtered, user_context.user_id)

        # 3. 已下架过滤
        if config.filter_taken_down:
            filtered = self._filter_taken_down(filtered)

        # 4. 屏蔽作者过滤
        if config.filter_blocked_authors:
            filtered = self._filter_blocked_authors(filtered, user_context.blocked_ids)

        # 5. 已曝光过滤 (可选)
        if config.filter_seen_posts:
            filtered = self._filter_seen_posts(filtered, user_context.seen_post_ids)

        # 6. 屏蔽关键词过滤
        if user_context.muted_keywords:
            filtered = self._filter_muted_keywords(filtered, user_context.muted_keywords)

        # 7. 最小内容长度过滤
        if config.min_content_length > 0:
            filtered = self._filter_min_content_length(filtered, config.min_content_length)

        return filtered

    def _drop_duplicates(self, candidates: List[PostCandidate]) -> List[PostCandidate]:
        """去重过滤"""
        seen = set()
        unique = []
        for c in candidates:
            if c.post_id not in seen:
                seen.add(c.post_id)
                unique.append(c)
        return unique

    def _filter_self_posts(
        self,
        candidates: List[PostCandidate],
        user_id: str
    ) -> List[PostCandidate]:
        """过滤自己的帖子"""
        return [c for c in candidates if c.author_id != user_id]

    def _filter_taken_down(self, candidates: List[PostCandidate]) -> List[PostCandidate]:
        """过滤已下架帖子"""
        return [c for c in candidates if c.status != 'taken_down']

    def _filter_blocked_authors(
        self,
        candidates: List[PostCandidate],
        blocked_ids: set
    ) -> List[PostCandidate]:
        """过滤屏蔽作者的帖子"""
        if not blocked_ids:
            return candidates
        return [c for c in candidates if c.author_id not in blocked_ids]

    def _filter_seen_posts(
        self,
        candidates: List[PostCandidate],
        seen_post_ids: set
    ) -> List[PostCandidate]:
        """过滤已曝光帖子"""
        if not seen_post_ids:
            return candidates
        return [c for c in candidates if c.post_id not in seen_post_ids]

    def _filter_muted_keywords(
        self,
        candidates: List[PostCandidate],
        muted_keywords: List[str]
    ) -> List[PostCandidate]:
        """过滤包含屏蔽关键词的帖子"""
        if not muted_keywords:
            return candidates

        def contains_muted_keyword(content: str) -> bool:
            content_lower = (content or '').lower()
            return any(kw.lower() in content_lower for kw in muted_keywords)

        return [c for c in candidates if not contains_muted_keyword(c.content)]

    def _filter_min_content_length(
        self,
        candidates: List[PostCandidate],
        min_length: int
    ) -> List[PostCandidate]:
        """过滤内容长度不足的帖子"""
        return [c for c in candidates if len(c.content or '') >= min_length]
