"""
作者多样性评分器

阶段5: 对同一作者的后续帖子进行惩罚
防止单个水军账号刷屏
"""

from typing import List, Dict
from collections import defaultdict
from ..types import PostCandidate
from ..config import DiversityConfig


class AuthorDiversityScorer:
    """
    作者多样性评分器

    如果不惩罚重复作者，一个水军账号发 100 条相同的假新闻，
    Feed 流可能就全是他。

    实现: 在同一个 Feed 列表里，同一个账号出现的次数越多，
    后续帖子的排名得分就被打个折扣。

    这逼迫水军必须采用"分布式账号矩阵"（蚁群战术）而不是单点输出。

    分类隔离:
    惩罚仅在同一内容类型（real_news / fake_news / non_news）内部施加。
    假新闻不会"占用"真实新闻的作者多样性配额，反之亦然。

    最低惩罚下限 (min_penalty):
    防止 0.7^n 指数衰减导致后位帖子分数趋近于零，保留最低竞争力。
    """

    def __init__(self, config: DiversityConfig):
        self.config = config

    def apply_penalty(self, candidates: List[PostCandidate]) -> List[PostCandidate]:
        """
        应用作者多样性惩罚（分类隔离）

        Args:
            candidates: 候选帖子列表 (已按分数排序)

        Returns:
            应用惩罚后的候选帖子列表
        """
        if not self.config.enabled:
            return candidates

        # 按内容类型分组，独立施加惩罚
        real_news = [c for c in candidates if c.is_news and c.news_type != 'fake']
        fake_news = [c for c in candidates if c.is_news and c.news_type == 'fake']
        non_news  = [c for c in candidates if not c.is_news]

        result = []
        for pool in (real_news, fake_news, non_news):
            result.extend(self._apply_to_pool(pool))

        return result

    def _apply_to_pool(self, pool: List[PostCandidate]) -> List[PostCandidate]:
        """
        在单个内容类型池内施加作者多样性惩罚

        Args:
            pool: 同类型候选帖子

        Returns:
            应用惩罚后的列表
        """
        if not pool:
            return pool

        sorted_pool = sorted(pool, key=lambda c: c.final_score, reverse=True)
        author_count: Dict[str, int] = defaultdict(int)

        for c in sorted_pool:
            count = author_count[c.author_id]

            if count > 0:
                # 惩罚公式: max(min_penalty, penalty_factor ^ count)
                raw_penalty = self.config.penalty_factor ** count
                c.diversity_penalty = max(self.config.min_penalty, raw_penalty)
                c.final_score *= c.diversity_penalty

            author_count[c.author_id] += 1

            # 超过最大出现次数，额外施加 0.1x 惩罚
            if author_count[c.author_id] > self.config.max_same_author:
                c.final_score *= 0.1

        return sorted_pool
