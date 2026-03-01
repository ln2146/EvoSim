"""
帖子数据仓库

封装帖子相关的数据库查询
"""

import sys
import os
from typing import List, Dict, Any, Optional

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.database_manager import fetch_all, fetch_one


class PostRepository:
    """
    帖子数据仓库

    提供帖子相关的数据库查询方法
    """

    BASE_SELECT = '''
        SELECT p.post_id, p.content, p.summary, p.author_id, p.created_at,
               p.num_likes, p.num_shares, p.num_flags, p.num_comments,
               p.original_post_id, p.is_news, p.news_type, p.status,
               p.is_agent_response, p.agent_role, p.agent_response_type,
               p.intervention_id,
               p.moderation_degradation_factor, p.moderation_label
        FROM posts p
    '''

    def get_active_news_posts(self) -> List[Dict[str, Any]]:
        """获取所有活跃新闻帖子"""
        query = f'''
            {self.BASE_SELECT}
            WHERE p.is_news = TRUE
            AND (p.status IS NULL OR p.status != 'taken_down')
        '''
        # NO FALLBACK: Propagate database errors instead of returning empty list
        result = fetch_all(query)
        return result if result else []

    def get_active_non_news_posts(self) -> List[Dict[str, Any]]:
        """获取所有活跃非新闻帖子"""
        query = f'''
            {self.BASE_SELECT}
            WHERE (p.is_news IS NULL OR p.is_news != TRUE)
            AND (p.status IS NULL OR p.status != 'taken_down')
        '''
        # NO FALLBACK: Propagate database errors instead of returning empty list
        result = fetch_all(query)
        return result if result else []

    def get_posts_by_authors(self, author_ids: List[str]) -> List[Dict[str, Any]]:
        """
        获取指定作者的帖子 (In-Network 召回)

        Args:
            author_ids: 作者 ID 列表

        Returns:
            帖子列表
        """
        if not author_ids:
            return []

        placeholders = ','.join(['?' for _ in author_ids])
        query = f'''
            {self.BASE_SELECT}
            WHERE p.author_id IN ({placeholders})
            AND (p.status IS NULL OR p.status != 'taken_down')
        '''
        # NO FALLBACK: Propagate database errors instead of returning empty list
        result = fetch_all(query, tuple(author_ids))
        return result if result else []

    def get_all_active_posts(self) -> List[Dict[str, Any]]:
        """获取所有活跃帖子"""
        query = f'''
            {self.BASE_SELECT}
            WHERE (p.status IS NULL OR p.status != 'taken_down')
        '''
        # NO FALLBACK: Propagate database errors instead of returning empty list
        result = fetch_all(query)
        return result if result else []

    def get_post_timesteps(self) -> Dict[str, int]:
        """
        获取帖子时间步映射

        Returns:
            {post_id: time_step} 字典
        """
        # NO FALLBACK: Propagate database errors instead of returning empty dict
        rows = fetch_all('SELECT post_id, time_step FROM post_timesteps')
        return {str(r['post_id']): r['time_step'] for r in rows if r}

    def get_post_by_id(self, post_id: str) -> Optional[Dict[str, Any]]:
        """获取单个帖子"""
        query = f'''
            {self.BASE_SELECT}
            WHERE p.post_id = ?
        '''
        # NO FALLBACK: Propagate database errors instead of returning None
        return fetch_one(query, (post_id,))
