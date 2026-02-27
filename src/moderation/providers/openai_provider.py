"""
OpenAI Moderation API 提供者

使用 OpenAI 的 Moderation API 进行内容审核
"""

import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any

from ..types import ModerationVerdict, ModerationSeverity, ModerationCategory
from ..config import ModerationProviderConfig


logger = logging.getLogger(__name__)


class OpenAIProvider:
    """
    OpenAI Moderation API 提供者

    使用 OpenAI 的 /v1/moderations 端点进行内容审核
    支持检测: hate, hate/threatening, self-harm, sexual, sexual/minors, violence, violence/graphic
    """

    # OpenAI 分类到我们分类的映射
    CATEGORY_MAPPING = {
        "hate": ModerationCategory.HATE_SPEECH,
        "hate/threatening": ModerationCategory.HATE_SPEECH,
        "self-harm": ModerationCategory.OTHER,
        "sexual": ModerationCategory.SEXUAL,
        "sexual/minors": ModerationCategory.SEXUAL,
        "violence": ModerationCategory.VIOLENCE,
        "violence/graphic": ModerationCategory.VIOLENCE,
    }

    # OpenAI 分类到严重程度的默认映射
    SEVERITY_MAPPING = {
        "hate": ModerationSeverity.HIGH,
        "hate/threatening": ModerationSeverity.CRITICAL,
        "self-harm": ModerationSeverity.CRITICAL,
        "sexual": ModerationSeverity.HIGH,
        "sexual/minors": ModerationSeverity.CRITICAL,
        "violence": ModerationSeverity.HIGH,
        "violence/graphic": ModerationSeverity.CRITICAL,
    }

    def __init__(self, config: ModerationProviderConfig):
        """
        初始化 OpenAI 提供者

        Args:
            config: 提供者配置
        """
        self.config = config
        self.api_key = config.api_key
        self.endpoint = config.api_endpoint or "https://api.openai.com/v1/moderations"
        self.timeout = 10

    def check(self, content: str, metadata: Dict[str, Any] = None) -> Optional[ModerationVerdict]:
        """
        检查内容

        Args:
            content: 待检查的内容
            metadata: 额外元数据

        Returns:
            审核裁决，如果内容安全则返回 None
        """
        if not self.config.enabled:
            logger.debug("OpenAI moderation provider is disabled")
            return None

        if not self.api_key:
            logger.warning("OpenAI API key not configured")
            return None

        response = self._call_api(content)

        if not response or not response.get("results"):
            raise RuntimeError(f"Invalid API response from OpenAI moderation: {response}")

        return self._parse_response(response, content, metadata)

    def _call_api(self, content: str) -> Optional[Dict[str, Any]]:
        """调用 OpenAI Moderation API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {"input": content}

        # 如果配置了自定义 endpoint，可能需要不同的请求格式
        if self.config.api_endpoint and "openai" not in self.config.api_endpoint.lower():
            # 第三方兼容 API 可能需要 model 参数
            data["model"] = self.config.model

        response = requests.post(
            self.endpoint,
            headers=headers,
            json=data,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI Moderation API returned status {response.status_code}: {response.text}")

        return response.json()

    def _parse_response(
        self,
        response: Dict[str, Any],
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """
        解析 API 响应

        OpenAI Moderation API 响应格式:
        {
            "results": [{
                "flagged": true,
                "categories": {"hate": false, "violence": true, ...},
                "category_scores": {"hate": 0.1, "violence": 0.95, ...}
            }]
        }
        """
        result = response["results"][0]
        flagged = result.get("flagged", False)

        if not flagged:
            logger.debug("Content not flagged by OpenAI moderation")
            return None

        categories = result.get("categories", {})
        category_scores = result.get("category_scores", {})

        # 找到所有被标记的分类
        flagged_categories = [
            (cat, score)
            for cat, score in category_scores.items()
            if categories.get(cat, False)
        ]

        if not flagged_categories:
            return None

        # 选择分数最高的分类
        top_category, top_score = max(flagged_categories, key=lambda x: x[1])

        # 映射到我们的分类和严重程度
        our_category = self.CATEGORY_MAPPING.get(top_category, ModerationCategory.OTHER)
        severity = self.SEVERITY_MAPPING.get(top_category, ModerationSeverity.MEDIUM)

        # 根据分数调整严重程度
        if top_score > 0.9 and severity != ModerationSeverity.CRITICAL:
            severity = ModerationSeverity(
                list(ModerationSeverity)[
                    max(0, list(ModerationSeverity).index(severity) - 1)
                ]
            )

        # 生成原因说明
        category_names = {
            "hate": "仇恨言论",
            "hate/threatening": "仇恨威胁",
            "self-harm": "自残内容",
            "sexual": "色情内容",
            "sexual/minors": "涉及未成年人的色情内容",
            "violence": "暴力内容",
            "violence/graphic": "血腥暴力",
        }

        reason = f"检测到{category_names.get(top_category, top_category)} (置信度: {top_score:.2%})"

        verdict = ModerationVerdict(
            post_id="",
            user_id="",
            content=content,
            category=our_category,
            severity=severity,
            confidence=float(top_score),
            reason=reason,
            provider="openai_moderation",
            checked_at=datetime.now(),
            metadata=metadata or {},
        )

        logger.info(f"OpenAI moderation flagged content: {reason}")
        return verdict

    def check_batch(self, contents: list, metadata: Dict[str, Any] = None) -> list:
        """
        批量检查内容

        OpenAI Moderation API 支持批量请求 (最多 20 条)

        Args:
            contents: 内容列表
            metadata: 额外元数据

        Returns:
            裁决列表
        """
        if not self.config.enabled or not self.api_key:
            return [None] * len(contents)

        # OpenAI API 限制每次最多 20 条
        batch_size = 20
        verdicts = []

        for i in range(0, len(contents), batch_size):
            batch = contents[i:i + batch_size]

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            data = {"input": batch}
            if self.config.api_endpoint and "openai" not in self.config.api_endpoint.lower():
                data["model"] = self.config.model

            response = requests.post(
                self.endpoint,
                headers=headers,
                json=data,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                raise RuntimeError(f"Batch OpenAI Moderation API returned status {response.status_code}: {response.text}")

            response_data = response.json()
            results = response_data.get("results", [])

            for j, result in enumerate(results):
                flagged = result.get("flagged", False)
                if flagged:
                    # 构造单个内容的响应格式
                    single_response = {"results": [result]}
                    verdicts.append(
                        self._parse_response(single_response, batch[j], metadata)
                    )
                else:
                    verdicts.append(None)

        return verdicts
