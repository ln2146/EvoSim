"""
用户数据仓库

封装用户相关的数据库查询
"""

import sys
import os
from typing import List, Dict, Any, Optional, Set

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.database_manager import fetch_all, fetch_one


class UserRepository:
    """
    用户数据仓库

    提供用户相关的数据库查询方法
    """

    def get_followed_ids(self, user_id: str) -> Set[str]:
        """
        获取用户关注列表

        Args:
            user_id: 用户 ID

        Returns:
            关注的用户 ID 集合
        """
        query = 'SELECT followed_id FROM follows WHERE follower_id = ?'
        try:
            rows = fetch_all(query, (user_id,)) or []
            return {str(r['followed_id']) for r in rows}
        except Exception as e:
            if "unable to open database file" in str(e):
                return set()
            raise

    def get_user_persona(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户画像

        Args:
            user_id: 用户 ID

        Returns:
            用户信息字典
        """
        query = '''
            SELECT user_id, persona, follower_count, influence_score
            FROM users
            WHERE user_id = ?
        '''
        try:
            return fetch_one(query, (user_id,))
        except Exception as e:
            if "unable to open database file" in str(e):
                return None
            raise

    def get_exposed_post_ids(self, user_id: str) -> Set[str]:
        """
        获取用户已曝光的帖子 ID

        Args:
            user_id: 用户 ID

        Returns:
            已曝光的帖子 ID 集合
        """
        query = 'SELECT DISTINCT post_id FROM feed_exposures WHERE user_id = ?'
        try:
            rows = fetch_all(query, (user_id,)) or []
            return {str(r['post_id']) for r in rows}
        except Exception as e:
            if "unable to open database file" in str(e):
                return set()
            raise

    def get_recent_interactions(self, user_id: str, limit: int = 50) -> List[str]:
        """
        获取用户最近交互的帖子 ID

        包括点赞、评论、转发等行为

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            帖子 ID 列表
        """
        # 从评论表获取交互
        query = '''
            SELECT DISTINCT post_id
            FROM comments
            WHERE author_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        '''
        try:
            rows = fetch_all(query, (user_id, limit)) or []
            return [str(r['post_id']) for r in rows]
        except Exception as e:
            if "unable to open database file" in str(e):
                return []
            raise

    def get_blocked_users(self, user_id: str) -> Set[str]:
        """
        获取用户屏蔽的用户列表

        注意: 当前数据库可能没有 blocked_users 表，返回空集合

        Args:
            user_id: 用户 ID

        Returns:
            屏蔽的用户 ID 集合
        """
        # 如果有 blocked_users 表，可以查询
        # 当前返回空集合
        return set()

    def get_muted_keywords(self, user_id: str) -> List[str]:
        """
        获取用户屏蔽的关键词列表

        注意: 当前数据库可能没有 muted_keywords 表，返回空列表

        Args:
            user_id: 用户 ID

        Returns:
            屏蔽的关键词列表
        """
        # 如果有 muted_keywords 表，可以查询
        # 当前返回空列表
        return []
