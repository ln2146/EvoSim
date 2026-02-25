"""
审核系统配置定义

遵循 AGENT_ENVIRONMENT_SPEC.md: Config 层定义所有可配置参数
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from .types import ModerationAction, ModerationSeverity


@dataclass
class ModerationProviderConfig:
    """
    审核提供者配置

    每个审核提供者（OpenAI、关键词等）的配置
    """
    # 开关
    enabled: bool = False
    weight: float = 1.0  # 多提供者时的权重

    # 触发阈值
    threshold: float = 0.7  # 触发审核的最小置信度

    # OpenAI API 配置
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: str = "gpt-4o-mini"

    # 关键词配置
    keywords: Dict[str, List[str]] = field(default_factory=dict)
    # 格式: {"category_name": ["keyword1", "keyword2", ...]}


@dataclass
class ModerationActionConfig:
    """
    干预动作配置

    定义不同严重程度对应的干预方式和参数
    """
    # 可见性降级系数 - 严重程度 -> 推荐权重系数
    visibility_degradation_factors: Dict[ModerationSeverity, float] = field(
        default_factory=lambda: {
            ModerationSeverity.LOW: 0.8,       # 轻微: 降低 20%
            ModerationSeverity.MEDIUM: 0.5,     # 中等: 降低 50%
            ModerationSeverity.HIGH: 0.2,       # 严重: 降低 80%
            ModerationSeverity.CRITICAL: 0.0,    # 极其严重: 完全隐藏
        }
    )

    # 警告标签文字 - 分类 -> 标签文字
    warning_labels: Dict[str, str] = field(
        default_factory=lambda: {
            "misinformation": "⚠️ 此内容可能包含不实信息，请谨慎参考",
            "hate_speech": "⚠️ 此内容包含敏感信息",
            "violence": "⚠️ 此内容涉及暴力内容",
            "spam": "⚠️ 此内容被标记为广告或垃圾信息",
            "controversial": "ℹ️ 此内容存在争议，建议多方核实",
            "other": "⚠️ 此内容需谨慎参考",
        }
    )

    # 硬性打击阈值 - 严重程度 -> 触发删帖的最小置信度
    takedown_thresholds: Dict[ModerationSeverity, float] = field(
        default_factory=lambda: {
            ModerationSeverity.HIGH: 0.8,      # 严重且置信度 > 0.8 删帖
            ModerationSeverity.CRITICAL: 0.6,   # 极其严重且置信度 > 0.6 删帖
        }
    )

    # 封号阈值
    ban_thresholds: Dict[ModerationSeverity, float] = field(
        default_factory=lambda: {
            ModerationSeverity.CRITICAL: 0.8,   # 极其严重且置信度 > 0.8 封号
        }
    )

    # 严重程度到默认动作的映射
    severity_to_action: Dict[ModerationSeverity, ModerationAction] = field(
        default_factory=lambda: {
            ModerationSeverity.LOW: ModerationAction.VISIBILITY_DEGRADATION,
            ModerationSeverity.MEDIUM: ModerationAction.WARNING_LABEL,
            ModerationSeverity.HIGH: ModerationAction.WARNING_LABEL,
            ModerationSeverity.CRITICAL: ModerationAction.HARD_TAKEDOWN,
        }
    )


@dataclass
class ModerationConfig:
    """
    审核系统总配置

    整合所有子配置，作为单一配置入口
    """
    # 全局开关
    enabled: bool = False

    # 审核提供者配置
    openai_provider: ModerationProviderConfig = field(
        default_factory=lambda: ModerationProviderConfig(
            enabled=True,
            threshold=0.7,
        )
    )
    keyword_provider: ModerationProviderConfig = field(
        default_factory=lambda: ModerationProviderConfig(
            enabled=False,
            threshold=0.6,
            keywords={
                "misinformation": ["谣言", "假新闻", "虚假"],
                "hate_speech": ["仇恨", "歧视"],
            }
        )
    )

    # 干预动作配置
    actions: ModerationActionConfig = field(
        default_factory=ModerationActionConfig
    )

    # 审核触发条件
    check_news_only: bool = True  # 是否只检查新闻
    check_threshold_engagement: int = 5  # 互动数阈值

    # 异步批处理配置
    batch_size: int = 10
    batch_interval_seconds: int = 60

    # 统计保留
    keep_stats: bool = True
    max_stats_entries: int = 10000

    @classmethod
    def from_dict(cls, config_dict: Optional[Dict[str, Any]] = None) -> "ModerationConfig":
        """
        从字典创建配置

        支持部分配置覆盖，未指定的使用默认值
        """
        if not config_dict:
            return cls()

        def parse_dataclass(dc_cls, data: Optional[Dict] = None):
            if not data:
                return dc_cls()
            # 只取 dataclass 定义的字段
            valid_fields = {f.name for f in dc_cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            return dc_cls(**filtered)

        # 解析 severity 字符串到枚举
        action_config_data = config_dict.get('actions', {})
        if 'severity_to_action' in action_config_data:
            severity_map = {}
            for severity_str, action_str in action_config_data['severity_to_action'].items():
                severity = ModerationSeverity(severity_str)
                action = ModerationAction(action_str)
                severity_map[severity] = action
            action_config_data['severity_to_action'] = severity_map

        return cls(
            enabled=config_dict.get('enabled', False),
            openai_provider=parse_dataclass(
                ModerationProviderConfig,
                config_dict.get('openai_provider')
            ),
            keyword_provider=parse_dataclass(
                ModerationProviderConfig,
                config_dict.get('keyword_provider')
            ),
            actions=parse_dataclass(
                ModerationActionConfig,
                action_config_data
            ) if action_config_data else ModerationActionConfig(),
            check_news_only=config_dict.get('check_news_only', True),
            check_threshold_engagement=config_dict.get('check_threshold_engagement', 5),
            batch_size=config_dict.get('batch_size', 10),
            batch_interval_seconds=config_dict.get('batch_interval_seconds', 60),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化和 API 响应"""
        from dataclasses import asdict
        return {
            'enabled': self.enabled,
            'openai_provider': asdict(self.openai_provider),
            'keyword_provider': asdict(self.keyword_provider),
            'actions': asdict(self.actions),
            'check_news_only': self.check_news_only,
            'check_threshold_engagement': self.check_threshold_engagement,
            'batch_size': self.batch_size,
            'batch_interval_seconds': self.batch_interval_seconds,
        }


# 默认配置实例
DEFAULT_CONFIG = ModerationConfig()


def load_config_from_env() -> ModerationConfig:
    """
    从环境变量加载配置

    支持通过环境变量覆盖配置
    """
    config = ModerationConfig()

    # OpenAI API Key
    import os
    if 'OPENAI_API_KEY' in os.environ:
        config.openai_provider.api_key = os.environ['OPENAI_API_KEY']

    # OpenAI Base URL (可选)
    if 'OPENAI_BASE_URL' in os.environ:
        config.openai_provider.api_endpoint = f"{os.environ['OPENAI_BASE_URL']}/v1/moderations"

    # 启用状态
    if 'MODERATION_ENABLED' in os.environ:
        config.enabled = os.environ['MODERATION_ENABLED'].lower() in ('true', '1', 'yes')

    return config
