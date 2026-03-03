"""
社区发现与派系分析模块

基于网络拓扑结构进行社区发现，识别信息茧房中的派系：
- Louvain社区发现算法
- 派系命名与分类
- 模块度评估
- 跨派系连接分析
"""

import sqlite3
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import networkx as nx
from dataclasses import dataclass
import numpy as np


@dataclass
class CommunityInfo:
    """社区信息"""
    community_id: int
    members: List[str]  # 成员用户ID列表
    name: str  # 派系名称（如"吃瓜群众"、"支持者"、"反对者"）
    size: int  # 社区大小
    density: float  # 内部连接密度
    avg_position: float  # 平均立场倾向 [-1, 1], -1极左, 1极右
    key_topics: List[str]  # 主要讨论话题
    is_echo_chamber: bool  # 是否为回声室
    cross_community_links: int  # 跨社区连接数


@dataclass
class NetworkModularity:
    """网络模块度指标"""
    modularity: float  # 整体模块度 [0-1]
    num_communities: int  # 社区数量
    avg_community_size: float  # 平均社区大小
    max_community_size: int  # 最大社区大小
    partition_quality: str  # 分区质量评价


@dataclass
class PostFactionDistribution:
    """单个帖子的派系分布"""
    post_id: str
    total_comments: int
    support_count: int  # 赞成
    neutral_count: int  # 中立
    oppose_count: int  # 反对
    support_ratio: float
    neutral_ratio: float
    oppose_ratio: float
    top_commenters: List[Tuple[str, str]]  # (user_id, stance)
    like_count: int = 0  # 点赞数
    support_by_like: int = 0  # 通过点赞表达支持的人数
    oppose_by_like: int = 0  # 通过点赞表达反对的人数（通过后续行为推断）


@dataclass
class UserInfluenceMetrics:
    """用户受帖子影响的程度指标"""
    user_id: str
    post_id: str
    influence_score: float  # 影响程度 [0, 1]
    stance: str  # 'support', 'neutral', 'oppose'
    behavior_type: str  # 'like', 'comment', 'share', 'view_only'
    behavior_change: float  # 行为变化程度 [-1, 1], 正向表示更积极，负向表示更消极
    bubble_index: float  # 用户的信息茧房指数
    time_to_react: float  # 反应时间（小时），越小表示反应越快/越受影响


@dataclass
class FactionReport:
    """派系分析报告"""
    communities: List[CommunityInfo]
    modularity: NetworkModularity
    faction_map: Dict[str, str]  # 用户ID -> 派系名称
    network_stats: Dict


class CommunityDetector:
    """社区发现与派系分析器"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def build_social_network(self) -> nx.Graph:
        """构建社交网络图

        边的定义：
        - 强连接：互相关注（边权重=2）
        - 弱连接：单向关注（边权重=1）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        G = nx.Graph()

        try:
            # 获取所有用户
            cursor.execute("SELECT user_id FROM users")
            users = [row[0] for row in cursor.fetchall()]
            G.add_nodes_from(users)

            # 获取关注关系（双向）
            cursor.execute("""
                SELECT follower_id, followed_id FROM follows
            """)

            # 记录关注关系
            follows = defaultdict(set)
            for follower, followed in cursor.fetchall():
                follows[follower].add(followed)

            # 添加边
            for user1 in follows:
                for user2 in follows[user1]:
                    # 检查是否互相关注
                    if user2 in follows and user1 in follows[user2]:
                        # 强连接（互粉）
                        if G.has_edge(user1, user2):
                            G[user1][user2]['weight'] = 2
                        else:
                            G.add_edge(user1, user2, weight=2)
                    else:
                        # 弱连接（单向）
                        if not G.has_edge(user1, user2):
                            G.add_edge(user1, user2, weight=1)

            return G

        finally:
            conn.close()

    def build_interaction_network(self, limit: int = 1000) -> nx.Graph:
        """基于互动构建网络图

        边的定义：
        - 互动次数（评论、点赞、分享）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        G = nx.Graph()

        try:
            # 获取最近的互动
            cursor.execute("""
                SELECT l1.user_id as user1, l2.user_id as user2, COUNT(*) as weight
                FROM likes l1
                JOIN likes l2 ON l1.post_id = l2.post_id
                WHERE l1.user_id != l2.user_id
                GROUP BY l1.user_id, l2.user_id
                LIMIT ?
            """, (limit,))

            for user1, user2, weight in cursor.fetchall():
                if G.has_edge(user1, user2):
                    G[user1][user2]['weight'] += weight
                else:
                    G.add_edge(user1, user2, weight=weight)

            return G

        finally:
            conn.close()

    def detect_communities_louvain(self, graph: nx.Graph) -> List[Set[str]]:
        """使用Louvain算法检测社区

        Returns:
            社区列表，每个社区是一个用户ID集合
        """
        try:
            import networkx.algorithms.community as nx_comm
            # 使用Louvain算法
            communities = nx_comm.louvain_communities(graph, weight='weight')
            return list(communities)
        except ImportError:
            # 如果没有安装python-louvain，使用标签传播算法作为替代
            return self._detect_communities_label_propagation(graph)

    def _detect_communities_label_propagation(self, graph: nx.Graph) -> List[Set[str]]:
        """标签传播算法检测社区（备用方案）"""
        import networkx.algorithms.community as nx_comm
        communities = nx_comm.label_propagation_communities(graph)
        return list(communities)

    def calculate_modularity(self, graph: nx.Graph, communities: List[Set[str]]) -> float:
        """计算网络模块度

        模块度衡量社区划分的质量：
        - > 0.3: 有意义的社区结构
        - > 0.5: 强社区结构
        """
        try:
            import networkx.algorithms.community as nx_comm
            modularity = nx_comm.modularity(graph, communities)
            return modularity
        except:
            return 0.0

    def name_community(self, community_members: Set[str], graph: nx.Graph) -> str:
        """为社区命名（智能识别派系类型）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 分析社区特征
            members_list = list(community_members)

            # 1. 检查社区大小
            size = len(members_list)

            # 2. 检查内部连接密度
            if size < 2:
                return f"独立用户-{size}人"

            internal_edges = 0
            for i, user1 in enumerate(members_list):
                for user2 in members_list[i+1:]:
                    if graph.has_edge(user1, user2):
                        internal_edges += 1

            max_edges = size * (size - 1) / 2
            density = internal_edges / max_edges if max_edges > 0 else 0

            # 3. 分析讨论话题
            placeholders = ','.join(['?' for _ in members_list])
            cursor.execute(f"""
                SELECT DISTINCT p.news_type, COUNT(*) as count
                FROM posts p
                WHERE p.author_id IN ({placeholders})
                GROUP BY p.news_type
                ORDER BY count DESC
                LIMIT 3
            """, members_list)

            topics = [row[0] for row in cursor.fetchall() if row[0]]

            # 4. 分析情感倾向（基于评论内容）
            cursor.execute(f"""
                SELECT c.content
                FROM comments c
                WHERE c.author_id IN ({placeholders})
                LIMIT 50
            """, members_list)

            comments = [row[0] for row in cursor.fetchall()]

            # 简单情感分析（基于关键词）
            positive_words = ['支持', '赞同', '好', '优秀', '正确', '理性']
            negative_words = ['反对', '错误', '糟糕', '反对', '攻击', '坏']

            positive_count = sum(1 for c in comments if any(w in c for w in positive_words))
            negative_count = sum(1 for c in comments if any(w in c for w in negative_words))

            # 5. 命名规则
            if size > 50:
                base_name = "大众群体"
            elif size > 20:
                base_name = "活跃社群"
            elif size > 5:
                base_name = "核心圈层"
            else:
                base_name = "小团体"

            # 根据密度和情感倾向调整
            if density > 0.7:
                if positive_count > negative_count * 2:
                    return f"{base_name}-支持派"
                elif negative_count > positive_count * 2:
                    return f"{base_name}-反对派"
                else:
                    return f"{base_name}"
            elif density < 0.3:
                return f"吃瓜群众"
            else:
                if topics:
                    return f"{base_name}-{topics[0]}"
                else:
                    return f"{base_name}"

        finally:
            conn.close()

    def analyze_community_position(
        self,
        community_members: Set[str]
    ) -> Tuple[float, List[str]]:
        """分析社区的立场倾向和主要话题

        Returns:
            (平均立场, 主要话题列表)
            立场范围: [-1, 1], -1表示极左/反对, 1表示极右/支持
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            members_list = list(community_members)
            if not members_list:
                return 0.0, []

            placeholders = ','.join(['?' for _ in members_list])

            # 获取主要话题
            cursor.execute(f"""
                SELECT DISTINCT news_type FROM posts
                WHERE author_id IN ({placeholders})
                LIMIT 10
            """, members_list)
            topics = [row[0] for row in cursor.fetchall() if row[0]]

            # 简化的立场分析（基于帖子内容的情感关键词）
            cursor.execute(f"""
                SELECT content FROM posts
                WHERE author_id IN ({placeholders})
                LIMIT 100
            """, members_list)

            posts = [row[0] for row in cursor.fetchall()]

            # 简单的立场打分（实际项目中应该用更复杂的NLP）
            positive_keywords = ['支持', '赞同', '优秀', '正确', '应该', '必须']
            negative_keywords = ['反对', '错误', '糟糕', '不应该', '反对', '问题']

            position_scores = []
            for post in posts:
                score = 0
                for kw in positive_keywords:
                    score += post.count(kw)
                for kw in negative_keywords:
                    score -= post.count(kw)
                position_scores.append(score)

            avg_position = np.mean(position_scores) if position_scores else 0.0

            # 归一化到 [-1, 1]
            if avg_position > 0:
                avg_position = min(avg_position / 10.0, 1.0)
            else:
                avg_position = max(avg_position / 10.0, -1.0)

            return avg_position, topics

        finally:
            conn.close()

    def detect_factions(
        self,
        network_type: str = 'social',
        min_community_size: int = 3
    ) -> FactionReport:
        """检测并分析派系

        Args:
            network_type: 网络类型 ('social'社交网络, 'interaction'互动网络)
            min_community_size: 最小社区大小

        Returns:
            FactionReport: 派系分析报告
        """
        # 1. 构建网络
        if network_type == 'social':
            graph = self.build_social_network()
        else:
            graph = self.build_interaction_network()

        if graph.number_of_nodes() == 0:
            return FactionReport(
                communities=[],
                modularity=NetworkModularity(0, 0, 0, 0, "无数据"),
                faction_map={},
                network_stats={}
            )

        # 2. 检测社区
        communities = self.detect_communities_louvain(graph)

        # 3. 过滤小社区
        communities = [c for c in communities if len(c) >= min_community_size]

        # 4. 计算模块度
        modularity_score = self.calculate_modularity(graph, communities)

        # 5. 分析每个社区
        community_infos = []
        faction_map = {}

        for idx, community in enumerate(communities):
            # 命名社区
            name = self.name_community(community, graph)

            # 计算内部密度
            members_list = list(community)
            if len(members_list) >= 2:
                internal_edges = 0
                for i, u1 in enumerate(members_list):
                    for u2 in members_list[i+1:]:
                        if graph.has_edge(u1, u2):
                            internal_edges += 1
                max_edges = len(members_list) * (len(members_list) - 1) / 2
                density = internal_edges / max_edges if max_edges > 0 else 0
            else:
                density = 0

            # 分析立场和话题
            avg_position, key_topics = self.analyze_community_position(community)

            # 计算跨社区连接
            cross_links = 0
            for member in community:
                for neighbor in graph.neighbors(member):
                    if neighbor not in community:
                        cross_links += 1

            # 判断是否为回声室（高密度、低跨连接）
            is_echo_chamber = density > 0.6 and cross_links < len(community) * 2

            community_info = CommunityInfo(
                community_id=idx,
                members=members_list,
                name=name,
                size=len(community),
                density=density,
                avg_position=avg_position,
                key_topics=key_topics[:5],
                is_echo_chamber=is_echo_chamber,
                cross_community_links=cross_links
            )
            community_infos.append(community_info)

            # 建立用户到派系的映射
            for member in members_list:
                faction_map[member] = name

        # 6. 计算网络统计
        num_communities = len(communities)
        avg_size = np.mean([len(c) for c in communities]) if communities else 0
        max_size = max([len(c) for c in communities]) if communities else 0

        modularity_obj = NetworkModularity(
            modularity=modularity_score,
            num_communities=num_communities,
            avg_community_size=avg_size,
            max_community_size=max_size,
            partition_quality=self._evaluate_partition_quality(modularity_score)
        )

        # 7. 网络统计
        network_stats = {
            'total_nodes': graph.number_of_nodes(),
            'total_edges': graph.number_of_edges(),
            'avg_degree': np.mean([d for n, d in graph.degree()]) if graph.number_of_nodes() > 0 else 0,
            'network_density': nx.density(graph)
        }

        return FactionReport(
            communities=community_infos,
            modularity=modularity_obj,
            faction_map=faction_map,
            network_stats=network_stats
        )

    def _evaluate_partition_quality(self, modularity: float) -> str:
        """评估分区质量"""
        if modularity < 0.2:
            return "弱社区结构"
        elif modularity < 0.4:
            return "中等社区结构"
        elif modularity < 0.6:
            return "强社区结构"
        else:
            return "极强社区结构"

    def get_cross_faction_interactions(self) -> Dict[Tuple[str, str], int]:
        """获取跨派系互动矩阵

        Returns:
            {(派系A, 派系B): 互动次数}
        """
        report = self.detect_factions(network_type='interaction')

        cross_interactions = defaultdict(int)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 获取跨派系的评论互动
            for user1, faction1 in report.faction_map.items():
                for user2, faction2 in report.faction_map.items():
                    if faction1 != faction2:
                        # 检查user1是否评论过user2的帖子
                        cursor.execute("""
                            SELECT COUNT(*) FROM comments c
                            JOIN posts p ON c.post_id = p.post_id
                            WHERE c.author_id = ? AND p.author_id = ?
                        """, (user1, user2))

                        count = cursor.fetchone()[0]
                        if count > 0:
                            pair = tuple(sorted([faction1, faction2]))
                            cross_interactions[pair] += count

            return dict(cross_interactions)

        finally:
            conn.close()

    def get_echo_chamber_users(self, threshold: float = 0.7) -> List[str]:
        """获取处于回声室中的用户列表

        Args:
            threshold: 回声室判定阈值（社区密度）

        Returns:
            处于回声室的用户ID列表
        """
        report = self.detect_factions()

        echo_users = []
        for community in report.communities:
            if community.is_echo_chamber:
                echo_users.extend(community.members)

        return echo_users

    def _analyze_comment_stance(self, content: str) -> str:
        """分析评论的立场（优化版）

        Args:
            content: 评论内容

        Returns:
            'support'（赞成）, 'neutral'（中立）, 或 'oppose'（反对）
        """
        if not content or not content.strip():
            return 'neutral'

        content_lower = content.lower()

        # 1. 强烈支持指标（权重2.0）
        strong_support_keywords = [
            # 中文
            '支持', '赞同', '赞成', '同意', '认可', '肯定', '确实', '对的', '有道理',
            '完全正确', '绝对正确', '必须', '一定要', '太对了', '说得好', '讲得对',
            '非常好', '很棒', '优秀', '完美', '坚决支持', '全力支持', '强烈支持',
            '一百个赞同', '一万个同意',
            # 英文
            'absolutely', 'definitely', 'completely agree', 'totally agree',
            'strongly support', 'fully support', '100% agree', 'exactly',
            'perfectly', 'absolutely right', 'spot on', 'you\'re right',
            'must', 'essential', 'crucial', 'vital',
            # Emoji
            '👍', '👏', '🎉'
        ]

        # 2. 支持指标（权重1.0）
        support_keywords = [
            # 中文
            '好', '很好', '不错', '可以', '行', '赞', '应该', '认为对', '觉得对',
            '有道理', '说得对', '你说得对', '同意这点', '认可这点', '确实如此',
            '是对的', '没错', '正确', '很对', '挺好', '甚好', '赞同这个', '接受',
            '表示同意', '大力支持', '支持这个观点',
            # 英文
            'agree', 'support', 'good', 'great', 'excellent', 'nice', 'right',
            'correct', 'yes', 'true', 'makes sense', 'valid point', 'well said',
            'i agree', 'totally', 'exactly', 'absolutely', 'sure', 'okay',
            'approve', 'endorse', 'favor', 'like', 'love', 'appreciate',
            'thumbs up', '+1', 'well done', 'keep it up'
        ]

        # 3. 强烈反对指标（权重2.0）
        strong_oppose_keywords = [
            # 中文
            '反对', '强烈反对', '坚决反对', '绝对反对', '完全不同意', '坚决不',
            '错', '大错特错', '不可接受', '荒谬', '无稽之谈', '胡说八道', '胡说',
            '瞎扯', '乱说', '错误', '不对劲', '有问题', '质疑', '怀疑', '不', '别',
            '勿', '否', '差', '糟糕', '太差', '不行', '不可以', '不应该', '反对这个',
            '拒绝',
            # 英文
            'strongly disagree', 'totally disagree', 'completely disagree',
            'absolutely not', 'no way', 'never', 'oppose', 'against',
            'wrong', 'terrible', 'horrible', 'awful', 'disgusting',
            'reject', 'refuse', 'deny', 'impossible', 'ridiculous',
            'nonsense', 'garbage', 'crap',
            # Emoji
            '❌', '👎', '👎🏻'
        ]

        # 4. 反对指标（权重1.0）
        oppose_keywords = [
            # 中文
            '不同意', '不赞同', '不赞成', '觉得不对', '认为不对', '有问题',
            '不对劲', '不太对', '感觉不对', '似乎错了', '可能错了', '怀疑',
            '质疑这点', '不认可', '无法接受', '难以接受', '不妥', '欠妥',
            '反驳', '反对意见', '不同意见', '保留意见', '持保留态度',
            # 英文
            'disagree', 'don\'t agree', 'not agree', 'wrong', 'incorrect',
            'problem', 'issue', 'concern', 'doubt', 'suspect', 'question',
            'skeptical', 'suspicious', 'not sure', 'not convinced',
            'bad', 'poor', 'fail', 'failure', 'reject', 'decline',
            'disapprove', 'against this', 'oppose this', 'no', 'not',
            'can\'t accept', 'unacceptable'
        ]

        # 5. 中立/探讨指标（权重0.5，但会抵消部分支持/反对分数）
        neutral_keywords = [
            # 中文
            '觉得', '可能', '也许', '大概', '好像', '似乎', '据说', '听说',
            '个人认为', '个人觉得', '我的看法', '我理解', '我想', '我的观点',
            '分析一下', '讨论一下', '探讨', '研究', '思考', '观察',
            '如何看待', '怎么看', '怎么说', '谈谈', '聊聊', '分享',
            # 英文
            'maybe', 'perhaps', 'possibly', 'might', 'could', 'seems',
            'appears', 'supposedly', 'reportedly', 'heard', 'i think',
            'i feel', 'i believe', 'my opinion', 'my view', 'perspective',
            'analyze', 'discuss', 'explore', 'consider', 'think about',
            'how do you see', 'what do you think', 'thoughts', 'views',
            'interesting', 'curious', 'wonder', 'unclear', 'not sure',
            # 标点
            '?', '？', '吗', '呢', '吧', '啊'
        ]

        # 计算得分（加权）
        support_score = 0
        oppose_score = 0
        neutral_score = 0

        # 强关键词（权重2.0）
        for kw in strong_support_keywords:
            if kw in content:
                support_score += 2.0

        for kw in strong_oppose_keywords:
            if kw in content:
                oppose_score += 2.0

        # 普通关键词（权重1.0）
        for kw in support_keywords:
            if kw in content:
                support_score += 1.0

        for kw in oppose_keywords:
            if kw in content:
                oppose_score += 1.0

        # 中立关键词（权重0.5）
        for kw in neutral_keywords:
            if kw in content:
                neutral_score += 0.5

        # 6. 基于情感符号调整
        # 积极表情符号
        positive_emojis = ['😊', '😄', '👍', '👏', '🎉', '💪', '👌', '✅', '✔️', '🌟']
        for emoji in positive_emojis:
            if emoji in content:
                support_score += 1.5

        # 消极表情符号
        negative_emojis = ['😞', '😠', '👎', '❌', '⛔', '🚫', '💔', '😔']
        for emoji in negative_emojis:
            if emoji in content:
                oppose_score += 1.5

        # 7. 基于评论长度调整
        # 简短评论（<10字符）更可能是中立或情绪化表达
        # 中等长度（10-50字符）可能包含明确观点
        # 长评论（>50字符）更可能是理性分析
        length = len(content.strip())
        if length < 10:
            # 简短评论，降低支持/反对分数的权重
            support_score *= 0.7
            oppose_score *= 0.7
            # 如果完全没有关键词，倾向于中立
            if support_score == 0 and oppose_score == 0:
                return 'neutral'
        elif length > 50:
            # 长评论，提高权重
            support_score *= 1.2
            oppose_score *= 1.2

        # 8. 判断立场
        # 设置阈值，需要有明显的倾向才会判定为支持或反对
        threshold = 0.5  # 最低得分阈值

        if support_score >= threshold and support_score > oppose_score * 1.2:
            return 'support'
        elif oppose_score >= threshold and oppose_score > support_score * 1.2:
            return 'oppose'
        elif neutral_score > 0 and (support_score + oppose_score) < threshold:
            return 'neutral'
        elif support_score == oppose_score and support_score > threshold:
            # 支持和反对分数相等但都有，根据绝对值决定
            if support_score > 1.0:
                return 'neutral'  # 势均力敌算中立
            else:
                return 'neutral'
        else:
            return 'neutral'  # 默认中立

    def analyze_post_factions(
        self,
        limit: int = 50,
        min_comments: int = 3
    ) -> List[PostFactionDistribution]:
        """分析每个帖子的派系分布（赞成、中立、反对）

        Args:
            limit: 分析的最大帖子数
            min_comments: 最少评论数，低于此数的帖子不分析

        Returns:
            帖子派系分布列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 获取有足够评论的帖子
            cursor.execute("""
                SELECT post_id FROM posts
                WHERE num_comments >= ?
                ORDER BY num_comments DESC
                LIMIT ?
            """, (min_comments, limit))

            post_ids = [row[0] for row in cursor.fetchall()]

            results = []

            for post_id in post_ids:
                # 获取该帖子的所有评论
                cursor.execute("""
                    SELECT comment_id, author_id, content
                    FROM comments
                    WHERE post_id = ?
                    ORDER BY created_at
                """, (post_id,))

                comments = cursor.fetchall()

                if not comments:
                    continue

                # 分析每条评论的立场
                stance_distribution = {'support': 0, 'neutral': 0, 'oppose': 0}
                commenter_stances = []

                for comment_id, author_id, content in comments:
                    stance = self._analyze_comment_stance(content)
                    stance_distribution[stance] += 1
                    commenter_stances.append((author_id, stance))

                total = len(comments)
                support_ratio = stance_distribution['support'] / total
                neutral_ratio = stance_distribution['neutral'] / total
                oppose_ratio = stance_distribution['oppose'] / total

                # 获取每个立场的代表性评论者
                top_commenters = commenter_stances[:10]  # 前10个评论者

                result = PostFactionDistribution(
                    post_id=post_id,
                    total_comments=total,
                    support_count=stance_distribution['support'],
                    neutral_count=stance_distribution['neutral'],
                    oppose_count=stance_distribution['oppose'],
                    support_ratio=support_ratio,
                    neutral_ratio=neutral_ratio,
                    oppose_ratio=oppose_ratio,
                    top_commenters=top_commenters
                )

                results.append(result)

            return results

        finally:
            conn.close()

    def _get_user_bubble_index(self, user_id: str) -> float:
        """获取用户的信息茧房指数

        Args:
            user_id: 用户ID

        Returns:
            信息茧房指数 [0, 1]
        """
        try:
            from src.filter_bubble_analyzer import FilterBubbleAnalyzer
            analyzer = FilterBubbleAnalyzer(self.db_path)
            metrics = analyzer.analyze_user_bubble(user_id)
            return metrics.echo_chamber_index
        except:
            return 0.5  # 默认值

    def _calculate_user_influence(
        self,
        user_id: str,
        post_id: str,
        post_created_at: str,
        conn: sqlite3.Connection,
        has_liked: bool = False,
        has_shared: bool = False
    ) -> UserInfluenceMetrics:
        """计算用户受帖子影响的程度

        综合考虑：
        1. 点赞行为（直接支持）
        2. 评论内容（立场分析）
        3. 行为变化（帖子前后的活跃度变化）
        4. 反应时间（多快做出反应）
        5. 信息茧房指数（高茧房用户更容易被影响）

        Args:
            user_id: 用户ID
            post_id: 帖子ID
            post_created_at: 帖子创建时间
            conn: 数据库连接
            has_liked: 是否点赞（外部提供，避免依赖likes表）
            has_shared: 是否分享（外部提供，避免依赖shares表）

        Returns:
            UserInfluenceMetrics: 影响程度指标
        """
        cursor = conn.cursor()

        # 1. 获取用户的茧房指数
        bubble_index = self._get_user_bubble_index(user_id)

        # 2. 检查评论行为
        cursor.execute("""
            SELECT comment_id, content, created_at FROM comments
            WHERE author_id = ? AND post_id = ?
            ORDER BY created_at
            LIMIT 1
        """, (user_id, post_id))

        comment_result = cursor.fetchone()
        has_commented = comment_result is not None
        comment_content = comment_result[1] if comment_result else None
        comment_time = comment_result[2] if comment_result else None

        # 3. 判断行为类型
        if has_shared:
            behavior_type = 'share'
            base_influence = 0.9
        elif has_commented:
            behavior_type = 'comment'
            base_influence = 0.7
        elif has_liked:
            behavior_type = 'like'
            base_influence = 0.5
        else:
            behavior_type = 'view_only'
            base_influence = 0.1

        # 4. 计算反应时间（小时）
        from datetime import datetime

        reaction_time_hours = float('inf')
        if comment_time:
            try:
                comment_dt = datetime.fromisoformat(comment_time.replace('Z', '+00:00'))
                post_dt = datetime.fromisoformat(post_created_at.replace('Z', '+00:00'))
                reaction_time_hours = (comment_dt - post_dt).total_seconds() / 3600
            except:
                reaction_time_hours = float('inf')

        # 反应时间越短，影响越大（24小时内线性衰减）
        if reaction_time_hours < float('inf'):
            time_factor = max(0, 1 - reaction_time_hours / 24)
        else:
            time_factor = 0

        # 5. 分析评论立场
        if comment_content:
            stance = self._analyze_comment_stance(comment_content)
        elif has_liked:
            stance = 'support'  # 点赞默认为支持
        else:
            stance = 'neutral'

        # 6. 分析行为变化（比较用户在帖子前后1周内的活跃度）
        cursor.execute("""
            SELECT
                COUNT(CASE WHEN created_at < ? THEN 1 END) as before_count,
                COUNT(CASE WHEN created_at >= ? THEN 1 END) as after_count
            FROM posts
            WHERE author_id = ?
            AND created_at >= datetime(?, '-7 days')
            AND created_at <= datetime(?, '+7 days')
        """, (post_created_at, post_created_at, user_id, post_created_at, post_created_at))

        before_after = cursor.fetchone()
        posts_before = before_after[0] if before_after else 0
        posts_after = before_after[1] if before_after else 0

        # 计算活跃度变化 [-1, 1]
        if posts_before + posts_after > 0:
            behavior_change = (posts_after - posts_before) / max(posts_before + posts_after, 1)
        else:
            behavior_change = 0

        # 7. 计算综合影响分数
        # 基础影响 + 时间因子 + 茧房指数加成 + 行为变化加成
        influence_score = (
            base_influence * 0.4 +
            time_factor * 0.2 +
            bubble_index * 0.2 +  # 高茧房用户更容易被影响
            abs(behavior_change) * 0.2
        )

        # 限制在 [0, 1]
        influence_score = max(0, min(1, influence_score))

        return UserInfluenceMetrics(
            user_id=user_id,
            post_id=post_id,
            influence_score=influence_score,
            stance=stance,
            behavior_type=behavior_type,
            behavior_change=behavior_change,
            bubble_index=bubble_index,
            time_to_react=reaction_time_hours if reaction_time_hours < float('inf') else -1
        )

    def _check_table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """检查表是否存在"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table_name,))
        return cursor.fetchone() is not None

    def analyze_post_factions_enhanced(
        self,
        limit: int = 50,
        min_comments: int = 3
    ) -> List[Dict]:
        """增强版帖子派系分析（加入点赞行为和影响程度）

        Args:
            limit: 分析的最大帖子数
            min_comments: 最少评论数

        Returns:
            增强的帖子派系分布列表，包含影响程度数据
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 检查是否有likes表
            has_likes_table = self._check_table_exists(conn, 'likes')
            has_shares_table = self._check_table_exists(conn, 'shares')

            # 获取有足够互动的帖子（评论+点赞）
            cursor.execute("""
                SELECT p.post_id, p.created_at, p.num_comments, p.num_likes
                FROM posts p
                WHERE p.num_comments >= ?
                ORDER BY (p.num_comments + p.num_likes) DESC
                LIMIT ?
            """, (min_comments, limit))

            posts = cursor.fetchall()
            results = []

            for post_id, post_created_at, num_comments, num_likes in posts:
                # 1. 获取所有点赞用户（如果有likes表）
                like_users = set()
                if has_likes_table:
                    try:
                        cursor.execute("""
                            SELECT user_id, created_at FROM likes
                            WHERE post_id = ?
                        """, (post_id,))
                        likes = cursor.fetchall()
                        like_users = set(user_id for user_id, _ in likes)
                    except:
                        pass  # 表可能存在但查询失败

                # 2. 获取所有评论
                cursor.execute("""
                    SELECT comment_id, author_id, content, created_at
                    FROM comments
                    WHERE post_id = ?
                    ORDER BY created_at
                """, (post_id,))

                comments = cursor.fetchall()

                if not comments:
                    continue

                # 3. 分析每条评论的立场
                stance_distribution = {'support': 0, 'neutral': 0, 'oppose': 0}
                commenter_stances = []
                user_influences = []

                # 分析评论者
                for comment_id, author_id, content, comment_time in comments:
                    stance = self._analyze_comment_stance(content)
                    stance_distribution[stance] += 1
                    commenter_stances.append((author_id, stance))

                    # 计算影响程度
                    influence = self._calculate_user_influence(
                        author_id, post_id, post_created_at, conn,
                        has_liked=(author_id in like_users),
                        has_shared=False  # 需要shares表时检查
                    )
                    user_influences.append(influence)

                # 分析仅点赞未评论的用户（如果有likes表）
                if has_likes_table:
                    for like_user_id in like_users:
                        if like_user_id not in [c[0] for c in comments]:
                            stance_distribution['support'] += 1  # 点赞视为支持

                            # 计算影响程度
                            influence = self._calculate_user_influence(
                                like_user_id, post_id, post_created_at, conn,
                                has_liked=True,
                                has_shared=False
                            )
                            user_influences.append(influence)

                total_interactions = len(comments) + len(like_users)
                support_ratio = stance_distribution['support'] / total_interactions
                neutral_ratio = stance_distribution['neutral'] / total_interactions
                oppose_ratio = stance_distribution['oppose'] / total_interactions

                # 4. 计算影响程度统计
                high_influence_users = [u for u in user_influences if u.influence_score > 0.7]
                avg_influence = sum(u.influence_score for u in user_influences) / len(user_influences) if user_influences else 0

                # 5. 分析高茧房用户的立场倾向
                high_bubble_users = [u for u in user_influences if u.bubble_index > 0.6]
                high_bubble_support_ratio = (
                    sum(1 for u in high_bubble_users if u.stance == 'support') / len(high_bubble_users)
                    if high_bubble_users else 0
                )

                result = {
                    'post_id': post_id,
                    'total_comments': len(comments),
                    'total_likes': len(like_users) if has_likes_table else num_likes,
                    'total_interactions': total_interactions,
                    'support_count': stance_distribution['support'],
                    'neutral_count': stance_distribution['neutral'],
                    'oppose_count': stance_distribution['oppose'],
                    'support_ratio': support_ratio,
                    'neutral_ratio': neutral_ratio,
                    'oppose_ratio': oppose_ratio,
                    'top_commenters': commenter_stances[:10],
                    'like_count': len(like_users) if has_likes_table else num_likes,
                    'support_by_like': len(like_users - set(c[0] for c in comments)) if has_likes_table else 0,
                    'avg_influence_score': avg_influence,
                    'high_influence_count': len(high_influence_users),
                    'high_influence_users': [
                        {'user_id': u.user_id, 'score': u.influence_score, 'stance': u.stance}
                        for u in sorted(high_influence_users, key=lambda x: x.influence_score, reverse=True)[:5]
                    ],
                    'high_bubble_users_count': len(high_bubble_users),
                    'high_bubble_support_ratio': high_bubble_support_ratio
                }

                results.append(result)

            return results

        finally:
            conn.close()

    def get_post_factions_summary(
        self,
        limit: int = 50,
        min_comments: int = 3,
        use_enhanced: bool = True
    ) -> Dict:
        """获取帖子派系分析的汇总信息

        Args:
            limit: 分析的最大帖子数
            min_comments: 最少评论数
            use_enhanced: 是否使用增强版分析（包含点赞和影响程度）

        Returns:
            汇总信息字典
        """
        if use_enhanced:
            post_factions = self.analyze_post_factions_enhanced(limit, min_comments)
        else:
            # 转换旧格式为新格式
            old_factions = self.analyze_post_factions(limit, min_comments)
            post_factions = [
                {
                    'post_id': p.post_id,
                    'total_comments': p.total_comments,
                    'total_likes': getattr(p, 'like_count', 0),
                    'total_interactions': p.total_comments + getattr(p, 'like_count', 0),
                    'support_count': p.support_count,
                    'neutral_count': p.neutral_count,
                    'oppose_count': p.oppose_count,
                    'support_ratio': p.support_ratio,
                    'neutral_ratio': p.neutral_ratio,
                    'oppose_ratio': p.oppose_ratio,
                    'top_commenters': p.top_commenters,
                    'like_count': getattr(p, 'like_count', 0),
                    'support_by_like': getattr(p, 'support_by_like', 0),
                    'avg_influence_score': 0,
                    'high_influence_count': 0,
                    'high_influence_users': [],
                    'high_bubble_users_count': 0,
                    'high_bubble_support_ratio': 0
                }
                for p in old_factions
            ]

        if not post_factions:
            return {
                'total_posts_analyzed': 0,
                'avg_support_ratio': 0.0,
                'avg_neutral_ratio': 0.0,
                'avg_oppose_ratio': 0.0,
                'most_divisive_post': None,
                'most_consensus_post': None,
                'avg_influence_score': 0.0,
                'high_bubble_support_ratio': 0.0,
                'post_factions': [],
                'analysis_type': 'enhanced' if use_enhanced else 'basic'
            }

        # 计算平均值
        avg_support = sum(p['support_ratio'] for p in post_factions) / len(post_factions)
        avg_neutral = sum(p['neutral_ratio'] for p in post_factions) / len(post_factions)
        avg_oppose = sum(p['oppose_ratio'] for p in post_factions) / len(post_factions)
        avg_influence = sum(p.get('avg_influence_score', 0) for p in post_factions) / len(post_factions)
        avg_high_bubble_support = sum(p.get('high_bubble_support_ratio', 0) for p in post_factions) / len(post_factions)

        # 找出最具分歧的帖子（赞成和反对比例接近且都较高）
        most_divisive = max(
            post_factions,
            key=lambda p: min(p['support_ratio'], p['oppose_ratio'])
        )

        # 找出最具共识的帖子（某一立场占绝对优势）
        most_consensus = max(
            post_factions,
            key=lambda p: max(p['support_ratio'], p['neutral_ratio'], p['oppose_ratio'])
        )

        # 找出影响最大的帖子
        if use_enhanced:
            most_influential = max(
                post_factions,
                key=lambda p: p.get('avg_influence_score', 0)
            )
        else:
            most_influential = None

        return {
            'total_posts_analyzed': len(post_factions),
            'avg_support_ratio': avg_support,
            'avg_neutral_ratio': avg_neutral,
            'avg_oppose_ratio': avg_oppose,
            'avg_influence_score': avg_influence,
            'high_bubble_support_ratio': avg_high_bubble_support,
            'most_divisive_post': {
                'post_id': most_divisive['post_id'],
                'support_ratio': most_divisive['support_ratio'],
                'oppose_ratio': most_divisive['oppose_ratio'],
                'total_interactions': most_divisive['total_interactions']
            },
            'most_consensus_post': {
                'post_id': most_consensus['post_id'],
                'dominant_stance': 'support' if most_consensus['support_ratio'] > 0.5 else
                                   'neutral' if most_consensus['neutral_ratio'] > 0.5 else 'oppose',
                'ratio': max(most_consensus['support_ratio'], most_consensus['neutral_ratio'], most_consensus['oppose_ratio']),
                'total_interactions': most_consensus['total_interactions']
            },
            'most_influential_post': {
                'post_id': most_influential['post_id'],
                'avg_influence_score': most_influential.get('avg_influence_score', 0),
                'total_interactions': most_influential['total_interactions']
            } if most_influential else None,
            'post_factions': post_factions,
            'analysis_type': 'enhanced' if use_enhanced else 'basic'
        }
