"""
Embedding 管理器

双层 Embedding 支持:
1. 本地 sentence-transformers 轻量模型 (默认，CPU 友好)
2. OpenAI Embedding API (可选，通过 use_openai_embedding=True 启用)

替代 X 算法的 Grok Transformer
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """
    Embedding 管理器

    双层架构:
    - 本地层: sentence-transformers 轻量模型，CPU 友好
    - 云端层: OpenAI Embedding API，精度更高

    支持:
    - 帖子 embedding 预计算和缓存
    - 用户 persona embedding 计算
    - 个人电脑可跑 (本地模式)
    """

    def __init__(
        self,
        model_name: str = "paraphrase-MiniLM-L6-v2",
        cache_embeddings: bool = True,
        max_cache_size: int = 10000,
        use_openai_embedding: bool = False,
        openai_model_name: str = None
    ):
        """
        初始化 EmbeddingManager

        Args:
            model_name: sentence-transformers 模型名称 (本地模式)
            cache_embeddings: 是否缓存 embedding
            max_cache_size: 最大缓存条目数
            use_openai_embedding: 是否使用 OpenAI Embedding API
            openai_model_name: OpenAI embedding 模型名称 (None 则使用默认)
        """
        self.model_name = model_name
        self.cache_embeddings = cache_embeddings
        self.max_cache_size = max_cache_size
        self.use_openai_embedding = use_openai_embedding
        self.openai_model_name = openai_model_name

        self._local_model = None
        self._openai_client = None
        self._openai_model = None
        self._cache: Dict[str, List[float]] = {}
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化模型"""
        if self._initialized:
            return

        if self.use_openai_embedding:
            self._init_openai_embedding()
        else:
            self._init_local_embedding()

        self._initialized = True

    def _init_local_embedding(self):
        """初始化本地 sentence-transformers 模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.model_name)
            logger.info(f"EmbeddingManager initialized with local model: {self.model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        except Exception as e:
            logger.error(f"Failed to initialize local embedding model: {e}")

    def _init_openai_embedding(self):
        """初始化 OpenAI Embedding 客户端"""
        try:
            from multi_model_selector import multi_model_selector
            self._openai_client, self._openai_model = multi_model_selector.create_embedding_client(
                model_name=self.openai_model_name
            )
            logger.info(f"EmbeddingManager initialized with OpenAI model: {self._openai_model}")
        except ImportError:
            logger.warning(
                "multi_model_selector not available. "
                "Falling back to local embedding."
            )
            self.use_openai_embedding = False
            self._init_local_embedding()
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI embedding: {e}")
            logger.info("Falling back to local embedding.")
            self.use_openai_embedding = False
            self._init_local_embedding()

    def encode_text(self, text: str) -> Optional[List[float]]:
        """
        编码文本为 embedding

        Args:
            text: 输入文本

        Returns:
            embedding 向量，失败返回 None
        """
        self._ensure_initialized()

        if not text:
            return None

        if self.use_openai_embedding:
            return self._encode_with_openai(text)
        else:
            return self._encode_with_local(text)

    def _encode_with_local(self, text: str) -> Optional[List[float]]:
        """使用本地模型编码"""
        if not self._local_model:
            return None

        try:
            embedding = self._local_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to encode text with local model: {e}")
            return None

    def _encode_with_openai(self, text: str) -> Optional[List[float]]:
        """使用 OpenAI API 编码"""
        if not self._openai_client:
            return None

        try:
            response = self._openai_client.embeddings.create(
                input=text,
                model=self._openai_model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to encode text with OpenAI: {e}")
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
        if self.use_openai_embedding:
            return self._openai_client is not None
        return self._local_model is not None

    @property
    def embedding_mode(self) -> str:
        """返回当前 embedding 模式"""
        if self.use_openai_embedding:
            return f"openai:{self._openai_model}"
        return f"local:{self.model_name}"
