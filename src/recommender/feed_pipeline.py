"""
Feed 推荐管道

对应 X 算法的 Home Mixer，编排 7 阶段推荐流程
"""

import logging
import os
from collections import Counter
from datetime import datetime
from typing import List, Optional

from .types import (
    FeedRequest, FeedResponse, UserContext, PostCandidate,
    PipelineContext, FeedSource
)
from .config import RecommenderConfig
from .repositories.post_repository import PostRepository
from .query_hydrators import UserActionHydrator, UserFeaturesHydrator
from .sources import InNetworkSource, OutNetworkSource
from .hydrators import CoreDataHydrator, AuthorHydrator
from .filters import PreScoringFilters, PostSelectionFilters
from .filters.moderation_filter import ModerationFilter
from .scorers import WeightedScorer, EmbeddingScorer, AuthorDiversityScorer, OONScorer, AuthorCredibilityScorer
from .selectors import TopKSelector

logger = logging.getLogger(__name__)

# 创建专门的推荐算法详细日志记录器
_pipeline_logger = None


def _get_pipeline_logger():
    """获取或创建推荐管道详细日志记录器（只写入文件，不输出到终端）"""
    global _pipeline_logger
    if _pipeline_logger is None:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'logs', 'recommender'
        )
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f'pipeline_{datetime.now().strftime("%Y%m%d")}.log')

        _pipeline_logger = logging.getLogger('recommender.pipeline')
        _pipeline_logger.setLevel(logging.INFO)
        _pipeline_logger.propagate = False  # 阻止日志传播到父 logger（不在终端显示）

        if not _pipeline_logger.handlers:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            _pipeline_logger.addHandler(file_handler)

    return _pipeline_logger


class FeedPipeline:
    """
    Feed 推荐管道

    对应 X 算法的 Home Mixer，编排 7 阶段推荐流程:
    1. Query Hydration - 用户上下文补充
    2. Candidate Sources - 双轨召回
    3. Candidate Hydration - 候选数据补充
    4. Pre-Scoring Filters - 前置过滤
    5. Scoring - 多层评分
    6. Selection - Top-K 选择
    7. Post-Selection Filters - 后置过滤
    """

    def __init__(self, config: RecommenderConfig = None):
        """
        初始化管道

        Args:
            config: 推荐系统配置，为 None 时使用默认配置
        """
        self.config = config or RecommenderConfig()
        self._init_stages()

    @property
    def pipeline_log(self):
        """返回推荐管道详细日志记录器（惰性初始化）"""
        return _get_pipeline_logger()

    def _init_stages(self):
        """初始化管道各阶段组件"""
        # 数据仓库
        self.post_repo = PostRepository()

        # Stage 1: Query Hydrators
        self.user_action_hydrator = UserActionHydrator()
        self.user_features_hydrator = UserFeaturesHydrator()

        # Stage 2: Sources
        self.in_network_source = InNetworkSource()
        self.out_network_source = OutNetworkSource()

        # Stage 3: Hydrators
        self.core_data_hydrator = CoreDataHydrator()
        self.author_hydrator = AuthorHydrator()

        # Stage 4: Pre-Scoring Filters
        self.pre_scoring_filters = PreScoringFilters()

        # Stage 5: Scorers
        self.weighted_scorer = WeightedScorer(self.config.scoring)
        self.embedding_scorer = None
        if self.config.embedding.enabled:
            self.embedding_scorer = EmbeddingScorer(self.config.embedding)
            # NO FALLBACK: Require embedding_manager to be initialized if embedding is enabled
            if not self.embedding_scorer.embedding_manager:
                raise RuntimeError(
                    "RecommenderConfig.embedding.enabled=True but EmbeddingScorer.embedding_manager is None. "
                    "Either disable embedding in config or ensure dependencies are properly installed."
                )
            self.user_features_hydrator.set_embedding_manager(
                self.embedding_scorer.embedding_manager
            )
        self.diversity_scorer = AuthorDiversityScorer(self.config.diversity)
        self.oon_scorer = OONScorer(self.config.oon)
        self.credibility_scorer = AuthorCredibilityScorer(self.config.author_credibility)

        # Stage 6: Selector
        self.selector = TopKSelector(self.config.selection)

        # Stage 7: Post-Selection Filters
        self.post_selection_filters = PostSelectionFilters()

        # Moderation Filter (applied after selection)
        self.moderation_filter = ModerationFilter()

    def execute(self, request: FeedRequest) -> FeedResponse:
        """
        执行完整推荐管道

        Args:
            request: Feed 请求

        Returns:
            Feed 响应
        """
        plog = self.pipeline_log
        start_time = datetime.now()

        plog.info("=" * 60)
        plog.info(f"[PIPELINE START] user={request.user_id}, time_step={request.time_step}")

        logger.debug(f"Executing feed pipeline for user {request.user_id}")

        ctx = self._create_context(request)

        # Stage 1: Query Hydration
        t0 = datetime.now()
        ctx = self._stage1_query_hydration(ctx)
        d1 = (datetime.now() - t0).total_seconds()
        plog.info(
            f"[Stage 1: Query Hydration] "
            f"persona={ctx.user_context.persona or 'N/A'} | "
            f"followed={len(ctx.user_context.followed_ids)} | "
            f"blocked={len(ctx.user_context.blocked_ids)} | "
            f"muted_kw={len(ctx.user_context.muted_keywords)} | "
            f"duration={d1:.3f}s"
        )
        logger.debug(f"Stage 1: User context hydrated, followed={len(ctx.user_context.followed_ids)}")

        # Stage 2: Candidate Sources
        t0 = datetime.now()
        ctx = self._stage2_candidate_retrieval(ctx)
        d2 = (datetime.now() - t0).total_seconds()
        in_count = ctx.metadata.get('in_network_count', 0)
        out_count = ctx.metadata.get('out_network_count', 0)
        plog.info(
            f"[Stage 2: Candidate Retrieval] "
            f"total={len(ctx.candidates)}, in_network={in_count}, "
            f"out_network={out_count}, duration={d2:.3f}s"
        )
        for c in ctx.candidates:
            plog.info(
                f"  [CANDIDATE] post={c.post_id[:8]} | "
                f"src={str(c.source):<13} | "
                f"is_news={str(c.is_news):<5} | "
                f"type={c.news_type or 'N/A':<4} | "
                f"author={c.author_id} | "
                f"likes={c.num_likes} shares={c.num_shares}"
            )
        logger.debug(f"Stage 2: Retrieved {len(ctx.candidates)} candidates")

        # Stage 3: Candidate Hydration
        t0 = datetime.now()
        ctx = self._stage3_data_hydration(ctx)
        d3 = (datetime.now() - t0).total_seconds()
        plog.info(f"[Stage 3: Data Hydration] candidates_hydrated={len(ctx.candidates)}, duration={d3:.3f}s")
        for c in ctx.candidates:
            if c.author_influence_score is not None:
                plog.info(
                    f"  [AUTHOR] post={c.post_id[:8]} | "
                    f"author={c.author_id} | "
                    f"influence={c.author_influence_score:.3f} | "
                    f"followers={c.author_follower_count or 0}"
                )
        logger.debug(f"Stage 3: Data hydration complete")

        # Stage 4: Pre-Scoring Filters
        t0 = datetime.now()
        before_filter = len(ctx.candidates)
        ctx = self._stage4_pre_scoring_filter(ctx)
        d4 = (datetime.now() - t0).total_seconds()
        filtered_out = before_filter - len(ctx.candidates)
        plog.info(
            f"[Stage 4: Pre-Scoring Filters] "
            f"before={before_filter}, after={len(ctx.candidates)}, "
            f"filtered_out={filtered_out}, duration={d4:.3f}s"
        )
        logger.debug(f"Stage 4: {len(ctx.candidates)} candidates after filtering")

        # Stage 5: Scoring
        t0 = datetime.now()
        ctx = self._stage5_scoring(ctx)
        d5 = (datetime.now() - t0).total_seconds()
        top_scores = [
            f"{c.post_id[:8]}:{c.final_score:.3f}"
            for c in sorted(ctx.candidates, key=lambda x: x.final_score, reverse=True)[:5]
        ]
        plog.info(
            f"[Stage 5: Scoring] "
            f"candidates_scored={len(ctx.candidates)}, "
            f"top5=[{', '.join(top_scores)}], duration={d5:.3f}s"
        )
        logger.debug(f"Stage 5: Scoring complete")

        # Stage 6: Selection
        t0 = datetime.now()
        before_selection = len(ctx.candidates)
        ctx = self._stage6_selection(ctx)
        d6 = (datetime.now() - t0).total_seconds()
        plog.info(
            f"[Stage 6: Selection] "
            f"before={before_selection}, selected={len(ctx.candidates)}, duration={d6:.3f}s"
        )
        logger.debug(f"Stage 6: Selected {len(ctx.candidates)} candidates")

        # Stage 7: Post-Selection Filters
        t0 = datetime.now()
        before_post = len(ctx.candidates)
        ctx = self._stage7_post_selection_filter(ctx)
        d7 = (datetime.now() - t0).total_seconds()
        post_filtered = before_post - len(ctx.candidates)
        import control_flags
        moderation_status = "enabled" if control_flags.moderation_enabled else "disabled"
        plog.info(
            f"[Stage 7: Post-Selection Filters] "
            f"before={before_post}, final={len(ctx.candidates)}, "
            f"filtered={post_filtered}, moderation={moderation_status}, duration={d7:.3f}s"
        )
        logger.debug(f"Stage 7: Final {len(ctx.candidates)} candidates")

        total_duration = (datetime.now() - start_time).total_seconds()
        plog.info(
            f"[PIPELINE END] user={request.user_id}, "
            f"final_feed_size={len(ctx.candidates)}, total_duration={total_duration:.3f}s"
        )
        plog.info("")

        return self._build_response(ctx)

    def _create_context(self, request: FeedRequest) -> PipelineContext:
        """创建管道上下文"""
        post_timesteps = self.post_repo.get_post_timesteps()
        return PipelineContext(
            request=request,
            user_context=UserContext(user_id=request.user_id),
            candidates=[],
            post_timesteps=post_timesteps,
        )

    def _stage1_query_hydration(self, ctx: PipelineContext) -> PipelineContext:
        """阶段1: 查询水合 - 获取用户上下文"""
        ctx.user_context = self.user_action_hydrator.hydrate(ctx.request.user_id)
        ctx.user_context = self.user_features_hydrator.hydrate(ctx.user_context)
        return ctx

    def _stage2_candidate_retrieval(self, ctx: PipelineContext) -> PipelineContext:
        """阶段2: 候选召回 - 双轨召回"""
        max_per_source = self.config.source.max_candidates_per_source

        in_network = self.in_network_source.retrieve(
            ctx.user_context,
            max_candidates=max_per_source
        )
        out_network = self.out_network_source.retrieve(
            ctx.user_context,
            max_candidates=max_per_source
        )
        ctx.candidates = in_network + out_network

        ctx.add_metadata('in_network_count', len(in_network))
        ctx.add_metadata('out_network_count', len(out_network))

        return ctx

    def _stage3_data_hydration(self, ctx: PipelineContext) -> PipelineContext:
        """阶段3: 数据水合 - 补充候选数据"""
        ctx.candidates = self.core_data_hydrator.hydrate(
            ctx.candidates,
            ctx.post_timesteps,
            ctx.request.time_step
        )
        ctx.candidates = self.author_hydrator.hydrate(ctx.candidates)
        return ctx

    def _stage4_pre_scoring_filter(self, ctx: PipelineContext) -> PipelineContext:
        """阶段4: 预评分过滤（带审计日志）"""
        plog = self.pipeline_log

        candidates, audit = self.pre_scoring_filters.filter_with_audit(
            ctx.candidates,
            ctx.user_context,
            self.config.filter
        )
        ctx.candidates = candidates

        if audit:
            reason_counts = Counter(entry['reason'] for entry in audit)
            for entry in audit:
                plog.info(
                    f"  [FILTERED] post={entry['post_id'][:8]} | "
                    f"reason={entry['reason']:<20} | "
                    f"author={entry['author_id']}"
                )
            plog.info(
                f"  [FILTER_SUMMARY] " +
                " | ".join(f"{r}={c}" for r, c in sorted(reason_counts.items()))
            )

        return ctx

    def _stage5_scoring(self, ctx: PipelineContext) -> PipelineContext:
        """阶段5: 评分（带完整评分表日志）"""
        plog = self.pipeline_log

        # 5.1 基础加权评分
        ctx.candidates = self.weighted_scorer.score(
            ctx.candidates,
            self.config.freshness
        )

        # 5.2 Embedding 评分 (可选)
        if self.embedding_scorer and ctx.request.include_embedding_score:
            ctx.candidates = self.embedding_scorer.score(
                ctx.candidates,
                ctx.user_context
            )

        # 5.3 OON 评分
        ctx.candidates = self.oon_scorer.score(ctx.candidates)

        # 5.35 作者信誉调整
        ctx.candidates = self.credibility_scorer.score(ctx.candidates)

        # 5.4 作者多样性惩罚
        ctx.candidates = self.diversity_scorer.apply_penalty(ctx.candidates)

        # 完整评分表（按 final_score 降序）
        for c in sorted(ctx.candidates, key=lambda x: x.final_score, reverse=True):
            src_tag = str(c.source).split('.')[-1] if '.' in str(c.source) else str(c.source)
            src_tag = src_tag[:3].upper()
            news_tag = f"news/{c.news_type or 'N/A'}" if c.is_news else "non-news    "
            plog.info(
                f"  [SCORE] post={c.post_id[:8]} | "
                f"weighted={c.weighted_score:7.2f} | "
                f"embed={c.embedding_score:.3f} | "
                f"oon={c.oon_adjustment:.2f} | "
                f"div={c.diversity_penalty:.2f} | "
                f"final={c.final_score:7.3f} | "
                f"{src_tag} | {news_tag}"
            )

        return ctx

    def _stage6_selection(self, ctx: PipelineContext) -> PipelineContext:
        """阶段6: 选择（带每个入选帖子的日志）"""
        plog = self.pipeline_log
        ctx.candidates = self.selector.select(ctx.candidates)

        for rank, c in enumerate(ctx.candidates, 1):
            src_tag = str(c.source).split('.')[-1] if '.' in str(c.source) else str(c.source)
            src_tag = src_tag[:3].upper()
            news_tag = f"news/{c.news_type or 'N/A'}" if c.is_news else "non-news"
            plog.info(
                f"  [SELECTED] rank={rank:2d} | "
                f"post={c.post_id[:8]} | "
                f"segment={c.feed_segment:<9} | "
                f"score={c.final_score:7.3f} | "
                f"{news_tag:<14} | {src_tag}"
            )

        return ctx

    def _stage7_post_selection_filter(self, ctx: PipelineContext) -> PipelineContext:
        """阶段7: 后选择过滤（带审核降级/移除日志）"""
        plog = self.pipeline_log
        ctx.candidates = self.post_selection_filters.filter(ctx.candidates)

        import control_flags
        if control_flags.moderation_enabled:
            # 在审核前快照分数和 ID，用于对比
            before_scores = {c.post_id: c.final_score for c in ctx.candidates}
            before_ids = {c.post_id for c in ctx.candidates}

            ctx.candidates = self.moderation_filter.filter(ctx.candidates)

            after_ids = {c.post_id for c in ctx.candidates}

            # 记录被降级的帖子（分数发生变化）
            for c in ctx.candidates:
                old_score = before_scores.get(c.post_id, c.final_score)
                if c.final_score < old_score - 0.001:
                    plog.info(
                        f"  [MOD:DEGRADED] post={c.post_id[:8]} | "
                        f"factor={c.moderation_degradation_factor:.2f} | "
                        f"score {old_score:.3f}->{c.final_score:.3f} | "
                        f"label={c.moderation_label or 'none'}"
                    )

            # 记录被移除的帖子
            for post_id in before_ids - after_ids:
                plog.info(f"  [MOD:REMOVED] post={post_id[:8]}")
        else:
            plog.info("  [MOD:SKIP] moderation disabled")

        return ctx

    def _build_response(self, ctx: PipelineContext) -> FeedResponse:
        """构建响应"""
        return FeedResponse(
            posts=ctx.candidates,
            metadata=ctx.metadata
        )


def create_pipeline(config_dict: dict = None) -> FeedPipeline:
    """
    工厂函数: 从配置字典创建管道

    Args:
        config_dict: 配置字典

    Returns:
        FeedPipeline 实例
    """
    config = RecommenderConfig.from_dict(config_dict)
    return FeedPipeline(config)
