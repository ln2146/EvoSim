"""
LLM 审核提供者

使用与仿真主体相同的 LLM 端点（Gemini via OpenAI-compatible proxy）
进行语义级内容审核，能够识别阴谋论、隐晦假新闻等关键词无法覆盖的内容。
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from openai import OpenAI

from ..types import ModerationVerdict, ModerationSeverity, ModerationCategory
from ..config import ModerationProviderConfig


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a content moderation assistant for a social media simulation platform.
Analyze the given content and determine if it violates platform policies.

Categories:
- misinformation: fake news, conspiracy theories, unverified extreme claims, deliberately misleading content
- hate_speech: hate speech, discrimination, targeted harassment
- violence: violent content, threats of harm
- spam: spam, scam, unsolicited advertisement
- controversial: divisive but not clearly violating

Severity:
- low: minor issue, slightly problematic
- medium: moderate violation, should add a warning label
- high: serious violation, significantly reduce visibility
- critical: severe violation (incitement, explicit harmful misinformation)

Respond with valid JSON only — no markdown, no extra text.
If content is problematic:
{"flagged": true, "category": "misinformation", "severity": "high", "confidence": 0.85, "reason": "brief reason"}
If content is fine:
{"flagged": false}"""


class LLMProvider:
    """
    LLM 审核提供者

    通过 LLM 对内容进行语义级审核，准确率远高于关键词匹配。
    使用与仿真主体相同的 API 端点，无需额外密钥或服务。
    """

    def __init__(self, config: ModerationProviderConfig):
        self.config = config
        self.model = config.model or "gemini-2.0-flash"
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_endpoint,
            )
        return self._client

    def check(self, content: str, metadata: Dict[str, Any] = None) -> Optional[ModerationVerdict]:
        """
        使用 LLM 检查内容

        Args:
            content: 待检查的内容
            metadata: 额外元数据

        Returns:
            审核裁决，内容安全则返回 None
        """
        if not self.config.enabled:
            return None

        if not self.config.api_key:
            logger.warning("LLM moderation provider: api_key not configured")
            return None

        raw_text = self._call_llm(content)
        return self._parse_response(raw_text, content, metadata)

    def _call_llm(self, content: str) -> str:
        """调用 LLM 获取审核结果"""
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Moderate this content:\n\n{content[:2000]}"},
                ],
                max_tokens=150,
                temperature=0.1,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"LLM moderation API call failed: {e}") from e

    def _parse_response(
        self,
        raw_text: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[ModerationVerdict]:
        """解析 LLM 返回的 JSON 裁决"""
        # 剥离可能的 markdown 代码块
        text = raw_text
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"LLM moderation returned invalid JSON: '{raw_text[:120]}': {e}"
            ) from e

        if not result.get("flagged"):
            logger.debug("LLM moderation: content not flagged")
            return None

        # 解析分类
        category_str = result.get("category", "other")
        try:
            category = ModerationCategory(category_str)
        except ValueError:
            logger.warning(f"LLM returned unknown category '{category_str}', using OTHER")
            category = ModerationCategory.OTHER

        # 解析严重程度
        severity_str = result.get("severity", "medium")
        try:
            severity = ModerationSeverity(severity_str)
        except ValueError:
            logger.warning(f"LLM returned unknown severity '{severity_str}', using MEDIUM")
            severity = ModerationSeverity.MEDIUM

        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.7))))
        reason = result.get("reason", "LLM moderation flagged content")

        verdict = ModerationVerdict(
            post_id="",
            user_id="",
            content=content,
            category=category,
            severity=severity,
            confidence=confidence,
            reason=reason,
            provider="llm",
            checked_at=datetime.now(),
            metadata=metadata or {},
        )

        logger.info(f"LLM moderation flagged: [{severity_str}/{category_str}] {reason} (conf={confidence:.2f})")
        return verdict
