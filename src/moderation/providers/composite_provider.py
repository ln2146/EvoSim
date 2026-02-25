"""
组合审核提供者

协调多个审核提供者，综合结果
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

from ..types import ModerationVerdict, ModerationSeverity
from ..config import ModerationConfig
from .openai_provider import OpenAIProvider
from .keyword_provider import KeywordProvider


logger = logging.getLogger(__name__)


class CompositeProvider:
    """
    组合审核提供者

    协调多个提供者进行审核，综合结果得出最终裁决
    支持的策略:
    1. 优先级策略: 按提供者优先级顺序，返回第一个有结果的
    2. 投票策略: 多个提供者投票决定
    3. 置信度策略: 返回置信度最高的结果
    """

    def __init__(self, config: ModerationConfig):
        """
        初始化组合提供者

        Args:
            config: 审核配置
        """
        self.config = config
        self.providers: List[Tuple[str, float, Any]] = []  # (name, weight, provider)

        # 初始化子提供者
        self._init_providers()

    def _init_providers(self):
        """初始化所有配置的提供者"""
        # OpenAI Provider
        if self.config.openai_provider.enabled:
            try:
                provider = OpenAIProvider(self.config.openai_provider)
                weight = self.config.openai_provider.weight
                self.providers.append(("openai", weight, provider))
                logger.info("Initialized OpenAI moderation provider")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI provider: {e}")

        # Keyword Provider
        if self.config.keyword_provider.enabled:
            try:
                provider = KeywordProvider(self.config.keyword_provider)
                weight = self.config.keyword_provider.weight
                self.providers.append(("keyword", weight, provider))
                logger.info("Initialized keyword moderation provider")
            except Exception as e:
                logger.error(f"Failed to initialize keyword provider: {e}")

        if not self.providers:
            logger.warning("No moderation providers enabled")

    def check(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        strategy: str = "confidence"
    ) -> Optional[ModerationVerdict]:
        """
        综合检查内容

        Args:
            content: 待检查的内容
            metadata: 额外元数据
            strategy: 综合策略 ("priority", "vote", "confidence")

        Returns:
            审核裁决，如果所有提供者都认为内容安全则返回 None
        """
        if not self.providers:
            return None

        if strategy == "priority":
            return self._check_priority(content, metadata)
        elif strategy == "vote":
            return self._check_vote(content, metadata)
        else:  # confidence
            return self._check_confidence(content, metadata)

    def _check_priority(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """
        优先级策略: 按顺序返回第一个有结果的裁决
        """
        for name, weight, provider in self.providers:
            try:
                verdict = provider.check(content, metadata)
                if verdict:
                    logger.debug(f"Provider '{name}' returned a verdict")
                    return verdict
            except Exception as e:
                logger.error(f"Provider '{name}' error: {e}")

        return None

    def _check_confidence(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """
        置信度策略: 返回置信度最高的裁决
        """
        verdicts = []

        for name, weight, provider in self.providers:
            try:
                verdict = provider.check(content, metadata)
                if verdict:
                    # 加权置信度
                    weighted_confidence = verdict.confidence * weight
                    verdicts.append((name, verdict, weighted_confidence))
            except Exception as e:
                logger.error(f"Provider '{name}' error: {e}")

        if not verdicts:
            return None

        # 返回置信度最高的
        verdicts.sort(key=lambda x: x[2], reverse=True)
        name, verdict, confidence = verdicts[0]
        logger.debug(f"Highest confidence verdict from '{name}': {confidence:.2f}")

        return verdict

    def _check_vote(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """
        投票策略: 多数提供者认为需要审核才返回裁决
        """
        verdicts = []

        for name, weight, provider in self.providers:
            try:
                verdict = provider.check(content, metadata)
                if verdict:
                    verdicts.append((name, verdict, weight))
            except Exception as e:
                logger.error(f"Provider '{name}' error: {e}")

        if not verdicts:
            return None

        # 如果只有一个提供者返回结果，直接返回
        if len(verdicts) == 1:
            return verdicts[0][1]

        # 计算投票权重
        total_weight = sum(w for _, _, w in self.providers)
        flagged_weight = sum(w for _, _, w in verdicts)

        # 如果超过半数的权重认为需要审核
        if flagged_weight > total_weight / 2:
            # 选择严重程度最高的裁决
            verdicts.sort(
                key=lambda x: list(ModerationSeverity).index(x[1].severity),
                reverse=True
            )
            return verdicts[0][1]

        return None

    def check_batch(
        self,
        contents: List[str],
        metadata: Dict[str, Any] = None,
        strategy: str = "confidence"
    ) -> List[Optional[ModerationVerdict]]:
        """
        批量检查内容

        Args:
            contents: 内容列表
            metadata: 额外元数据
            strategy: 综合策略

        Returns:
            裁决列表
        """
        results = []

        for content in contents:
            verdict = self.check(content, metadata, strategy)
            results.append(verdict)

        return results

    def get_provider_names(self) -> List[str]:
        """获取已初始化的提供者名称列表"""
        return [name for name, _, _ in self.providers]

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """获取各提供者状态"""
        status = {}

        for name, weight, provider in self.providers:
            status[name] = {
                "weight": weight,
                "type": type(provider).__name__,
                "enabled": True,
            }

        return status
