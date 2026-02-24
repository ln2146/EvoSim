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
    """

    def __init__(self, config: DiversityConfig):
        self.config = config

    def apply_penalty(self, candidates: List[PostCandidate]) -> List[PostCandidate]:
        """
        应用作者多样性惩罚

        Args:
            candidates: 候选帖子列表 (已按分数排序)

        Returns:
            应用惩罚后的候选帖子列表
        """
        if not self.config.enabled:
            return candidates

        # 先按当前分数排序
        sorted_candidates = sorted(
            candidates,
            key=lambda c: c.final_score,
            reverse=True
        )

        # 统计每个作者出现次数
        author_count: Dict[str, int] = defaultdict(int)

        for c in sorted_candidates:
            count = author_count[c.author_id]

            if count > 0:
                # 应用惩罚: penalty = penalty_factor ^ count
                c.diversity_penalty = self.config.penalty_factor ** count
                c.final_score *= c.diversity_penalty

            author_count[c.author_id] += 1

            # 如果超过最大出现次数，大幅降低分数
            if author_count[c.author_id] > self.config.max_same_author:
                c.final_score *= 0.1  # 额外惩罚

        return sorted_candidates
