"""
Feed 推荐管道

对应 X 算法的 Home Mixer，编排 7 阶段推荐流程
"""

import logging
import os
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
    """获取或创建推荐管道详细日志记录器"""
    global _pipeline_logger
    if _pipeline_logger is None:
        # 确保日志目录存在
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'recommender')
        os.makedirs(log_dir, exist_ok=True)

        # 创建以日期命名的日志文件
        log_file = os.path.join(log_dir, f'pipeline_{datetime.now().strftime("%Y%m%d")}.log')

        _pipeline_logger = logging.getLogger('recommender.pipeline')
        _pipeline_logger.setLevel(logging.INFO)

        # 避免重复添加 handler
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
        pipeline_log = _get_pipeline_logger()
        start_time = datetime.now()

        # 记录管道开始
        pipeline_log.info(f"="*60)
        pipeline_log.info(f"[PIPELINE START] user={request.user_id}, time_step={request.time_step}")

        logger.debug(f"Executing feed pipeline for user {request.user_id}")

        # 创建管道上下文
        ctx = self._create_context(request)

        # Stage 1: Query Hydration
        stage1_start = datetime.now()
        ctx = self._stage1_query_hydration(ctx)
        stage1_duration = (datetime.now() - stage1_start).total_seconds()
        pipeline_log.info(f"[Stage 1: Query Hydration] followed_count={len(ctx.user_context.followed_ids)}, duration={stage1_duration:.3f}s")
        logger.debug(f"Stage 1: User context hydrated, followed={len(ctx.user_context.followed_ids)}")

        # Stage 2: Candidate Sources
        stage2_start = datetime.now()
        ctx = self._stage2_candidate_retrieval(ctx)
        stage2_duration = (datetime.now() - stage2_start).total_seconds()
        in_count = ctx.metadata.get('in_network_count', 0)
        out_count = ctx.metadata.get('out_network_count', 0)
        neg_count = ctx.metadata.get('negative_news_count', 0)
        pipeline_log.info(f"[Stage 2: Candidate Retrieval] total={len(ctx.candidates)}, in_network={in_count}, out_network={out_count}, negative_news={neg_count}, duration={stage2_duration:.3f}s")
        logger.debug(f"Stage 2: Retrieved {len(ctx.candidates)} candidates")

        # Stage 3: Candidate Hydration
        stage3_start = datetime.now()
        ctx = self._stage3_data_hydration(ctx)
        stage3_duration = (datetime.now() - stage3_start).total_seconds()
        pipeline_log.info(f"[Stage 3: Data Hydration] candidates_hydrated={len(ctx.candidates)}, duration={stage3_duration:.3f}s")
        logger.debug(f"Stage 3: Data hydration complete")

        # Stage 4: Pre-Scoring Filters
        stage4_start = datetime.now()
        before_filter = len(ctx.candidates)
        ctx = self._stage4_pre_scoring_filter(ctx)
        stage4_duration = (datetime.now() - stage4_start).total_seconds()
        filtered_out = before_filter - len(ctx.candidates)
        pipeline_log.info(f"[Stage 4: Pre-Scoring Filters] before={before_filter}, after={len(ctx.candidates)}, filtered_out={filtered_out}, duration={stage4_duration:.3f}s")
        logger.debug(f"Stage 4: {len(ctx.candidates)} candidates after filtering")

        # Stage 5: Scoring
        stage5_start = datetime.now()
        ctx = self._stage5_scoring(ctx)
        stage5_duration = (datetime.now() - stage5_start).total_seconds()
        # 记录评分详情
        top_scores = []
        for i, c in enumerate(ctx.candidates[:5]):
            top_scores.append(f"{c.post_id[:8]}:{c.final_score:.3f}" if c.final_score else f"{c.post_id[:8]}:N/A")
        pipeline_log.info(f"[Stage 5: Scoring] candidates_scored={len(ctx.candidates)}, top5_scores=[{', '.join(top_scores)}], duration={stage5_duration:.3f}s")
        logger.debug(f"Stage 5: Scoring complete")

        # Stage 6: Selection
        stage6_start = datetime.now()
        before_selection = len(ctx.candidates)
        ctx = self._stage6_selection(ctx)
        stage6_duration = (datetime.now() - stage6_start).total_seconds()
        pipeline_log.info(f"[Stage 6: Selection] before={before_selection}, selected={len(ctx.candidates)}, duration={stage6_duration:.3f}s")
        logger.debug(f"Stage 6: Selected {len(ctx.candidates)} candidates")

        # Stage 7: Post-Selection Filters
        stage7_start = datetime.now()
        before_post = len(ctx.candidates)
        ctx = self._stage7_post_selection_filter(ctx)
        stage7_duration = (datetime.now() - stage7_start).total_seconds()
        post_filtered = before_post - len(ctx.candidates)

        # 检查审核过滤状态
        import control_flags
        moderation_status = "enabled" if control_flags.moderation_enabled else "disabled"
        pipeline_log.info(f"[Stage 7: Post-Selection Filters] before={before_post}, final={len(ctx.candidates)}, filtered={post_filtered}, moderation={moderation_status}, duration={stage7_duration:.3f}s")
        logger.debug(f"Stage 7: Final {len(ctx.candidates)} candidates")

        # 记录管道完成
        total_duration = (datetime.now() - start_time).total_seconds()
        pipeline_log.info(f"[PIPELINE END] user={request.user_id}, final_feed_size={len(ctx.candidates)}, total_duration={total_duration:.3f}s")
        pipeline_log.info(f"")

        return self._build_response(ctx)

    def _create_context(self, request: FeedRequest) -> PipelineContext:
        """创建管道上下文"""
        # 获取帖子时间步映射
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

        # In-Network 召回 (关注流)
        in_network = self.in_network_source.retrieve(
            ctx.user_context,
            max_candidates=max_per_source
        )

        # Out-Network 召回 (热点流)
        out_network = self.out_network_source.retrieve(
            ctx.user_context,
            max_candidates=max_per_source
        )

        # 负面新闻召回
        negative_news = self.out_network_source.retrieve_negative_news(ctx.user_context)

        # 合并候选
        ctx.candidates = in_network + out_network + negative_news

        # 记录召回统计
        ctx.add_metadata('in_network_count', len(in_network))
        ctx.add_metadata('out_network_count', len(out_network))
        ctx.add_metadata('negative_news_count', len(negative_news))

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
        """阶段4: 预评分过滤"""
        ctx.candidates = self.pre_scoring_filters.filter(
            ctx.candidates,
            ctx.user_context,
            self.config.filter
        )
        return ctx

    def _stage5_scoring(self, ctx: PipelineContext) -> PipelineContext:
        """阶段5: 评分"""
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

        return ctx

    def _stage6_selection(self, ctx: PipelineContext) -> PipelineContext:
        """阶段6: 选择"""
        ctx.candidates = self.selector.select(ctx.candidates)
        return ctx

    def _stage7_post_selection_filter(self, ctx: PipelineContext) -> PipelineContext:
        """阶段7: 后选择过滤"""
        ctx.candidates = self.post_selection_filters.filter(ctx.candidates)

        # Apply moderation filter (if enabled via control_flags)
        import control_flags
        if control_flags.moderation_enabled:
            ctx.candidates = self.moderation_filter.filter(ctx.candidates)

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
