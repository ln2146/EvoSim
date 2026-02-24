"""
Embedding 管理器

使用 sentence-transformers 轻量模型管理文本 embedding
替代 X 算法的 Grok Transformer
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """
    Embedding 管理器

    使用 sentence-transformers 轻量模型:
    - 支持帖子 embedding 预计算和缓存
    - 支持用户 persona embedding 计算
    - CPU 友好，个人电脑可跑
    """

    def __init__(
        self,
        model_name: str = "paraphrase-MiniLM-L6-v2",
        cache_embeddings: bool = True,
        max_cache_size: int = 10000
    ):
        """
        初始化 EmbeddingManager

        Args:
            model_name: sentence-transformers 模型名称
            cache_embeddings: 是否缓存 embedding
            max_cache_size: 最大缓存条目数
        """
        self.model_name = model_name
        self.cache_embeddings = cache_embeddings
        self.max_cache_size = max_cache_size

        self._model = None
        self._cache: Dict[str, List[float]] = {}
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化模型"""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._initialized = True
            logger.info(f"EmbeddingManager initialized with model: {self.model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            self._initialized = True  # 标记为已初始化，避免重复尝试
        except Exception as e:
            logger.error(f"Failed to initialize EmbeddingManager: {e}")
            self._initialized = True

    def encode_text(self, text: str) -> Optional[List[float]]:
        """
        编码文本为 embedding

        Args:
            text: 输入文本

        Returns:
            embedding 向量，失败返回 None
        """
        self._ensure_initialized()

        if not self._model or not text:
            return None

        try:
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            return None

    def get_or_compute_embedding(
        self,
        post_id: str,
        content: str
    ) -> Optional[List[float]]:
        """
        获取或计算帖子 embedding

        优先从缓存获取，缓存未命中则计算并缓存

        Args:
            post_id: 帖子 ID
            content: 帖子内容

        Returns:
            embedding 向量
        """
        # 检查缓存
        if self.cache_embeddings and post_id in self._cache:
            return self._cache[post_id]

        # 计算 embedding
        embedding = self.encode_text(content)

        # 缓存结果
        if embedding and self.cache_embeddings:
            self._add_to_cache(post_id, embedding)

        return embedding

    def _add_to_cache(self, key: str, embedding: List[float]):
        """添加到缓存，超出限制时清理旧条目"""
        if len(self._cache) >= self.max_cache_size:
            # 简单策略: 删除一半旧条目
            keys_to_remove = list(self._cache.keys())[:self.max_cache_size // 2]
            for k in keys_to_remove:
                del self._cache[k]

        self._cache[key] = embedding

    def precompute_embeddings(self, posts: List[Dict]) -> int:
        """
        批量预计算帖子 embedding

        Args:
            posts: 帖子列表，每个帖子需要有 post_id 和 content 字段

        Returns:
            成功计算的数量
        """
        self._ensure_initialized()

        if not self._model:
            return 0

        count = 0
        for post in posts:
            post_id = str(post.get('post_id', ''))
            content = post.get('content', '')

            if post_id and content and post_id not in self._cache:
                embedding = self.encode_text(content)
                if embedding:
                    self._add_to_cache(post_id, embedding)
                    count += 1

        logger.info(f"Precomputed {count} embeddings")
        return count

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)

    @property
    def is_available(self) -> bool:
        """检查 embedding 功能是否可用"""
        self._ensure_initialized()
        return self._model is not None
