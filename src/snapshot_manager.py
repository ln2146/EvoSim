"""
时间步快照管理器

功能：
1. 在每个tick结束时保存数据库快照
2. 从任意tick恢复状态
3. 管理快照存储空间
"""

import os
import shutil
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class SnapshotManager:
    """时间步快照管理器"""

    def __init__(self, project_root: str, simulation_db_path: str):
        """
        初始化快照管理器

        Args:
            project_root: 项目根目录
            simulation_db_path: 当前模拟数据库路径
        """
        self.project_root = project_root
        self.simulation_db_path = simulation_db_path

        # 快照存储目录
        self.snapshots_dir = os.path.join(project_root, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)

        # 元数据文件
        self.metadata_file = os.path.join(self.snapshots_dir, "metadata.json")

        # 当前会话ID
        self.session_id = None

    def create_session(self) -> str:
        """
        创建新的快照会话

        Returns:
            session_id: 会话ID
        """
        # 清理旧会话的快照
        self.cleanup_old_snapshots()

        # 创建新会话ID
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 创建会话目录
        session_dir = os.path.join(self.snapshots_dir, self.session_id)
        os.makedirs(session_dir, exist_ok=True)

        # 初始化元数据
        metadata = {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "ticks": {}
        }

        self._save_metadata(metadata)

        logger.info(f"📦 创建新快照会话: {self.session_id}")
        return self.session_id

    def save_tick_snapshot(self, tick: int, additional_info: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存指定tick的快照

        Args:
            tick: 时间步编号
            additional_info: 额外信息（如配置、状态等）

        Returns:
            是否保存成功
        """
        if not self.session_id:
            logger.error("❌ 快照会话未初始化，请先调用 create_session()")
            return False

        try:
            # 创建tick快照目录
            tick_dir = os.path.join(self.snapshots_dir, self.session_id, f"tick_{tick}")
            os.makedirs(tick_dir, exist_ok=True)

            # 复制数据库文件
            snapshot_db_path = os.path.join(tick_dir, "simulation.db")

            # 确保源文件存在
            if not os.path.exists(self.simulation_db_path):
                logger.error(f"❌ 源数据库不存在: {self.simulation_db_path}")
                return False

            # 复制数据库
            shutil.copy2(self.simulation_db_path, snapshot_db_path)

            # 保存额外信息
            if additional_info:
                info_file = os.path.join(tick_dir, "info.json")
                with open(info_file, 'w', encoding='utf-8') as f:
                    json.dump(additional_info, f, ensure_ascii=False, indent=2)

            # 更新全局元数据
            metadata = self._load_metadata()
            metadata["ticks"][str(tick)] = {
                "tick": tick,
                "timestamp": datetime.now().isoformat(),
                "db_path": snapshot_db_path,
                "info_file": info_file if additional_info else None
            }
            self._save_metadata(metadata)

            # 同时更新会话目录下的元数据（用于list_sessions读取）
            session_metadata_path = os.path.join(self.snapshots_dir, self.session_id, "metadata.json")
            session_metadata = self._load_session_metadata(self.session_id)
            session_metadata["ticks"][str(tick)] = {
                "tick": tick,
                "timestamp": datetime.now().isoformat(),
                "db_path": snapshot_db_path,
                "info_file": info_file if additional_info else None
            }
            with open(session_metadata_path, 'w', encoding='utf-8') as f:
                json.dump(session_metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 已保存 tick {tick} 的快照")
            return True

        except Exception as e:
            logger.error(f"❌ 保存 tick {tick} 快照失败: {e}")
            return False

    def restore_from_tick(self, tick: int, session_id: Optional[str] = None) -> Optional[str]:
        """
        从指定tick恢复数据库

        Args:
            tick: 要恢复到的tick
            session_id: 会话ID（如果不指定则使用当前会话）

        Returns:
            恢复的数据库路径，失败返回None
        """
        try:
            # 确定使用的会话
            target_session = session_id or self.session_id
            if not target_session:
                logger.error("❌ 未指定会话ID且当前没有活动会话")
                return None

            # 查找快照路径
            snapshot_db_path = os.path.join(
                self.snapshots_dir,
                target_session,
                f"tick_{tick}",
                "simulation.db"
            )

            if not os.path.exists(snapshot_db_path):
                logger.error(f"❌ 快照不存在: {snapshot_db_path}")
                return None

            # 关闭当前数据库连接（如果需要）
            # 注意：调用者需要确保没有打开的数据库连接

            # 备份当前数据库
            if os.path.exists(self.simulation_db_path):
                backup_path = f"{self.simulation_db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.simulation_db_path, backup_path)
                logger.info(f"📋 已备份当前数据库到: {backup_path}")

            # 恢复快照
            shutil.copy2(snapshot_db_path, self.simulation_db_path)

            logger.info(f"✅ 成功从 tick {tick} 恢复数据库")
            return self.simulation_db_path

        except Exception as e:
            logger.error(f"❌ 恢复 tick {tick} 失败: {e}")
            return None

    def list_available_ticks(self, session_id: Optional[str] = None) -> List[int]:
        """
        列出可用的tick

        Args:
            session_id: 会话ID（如果不指定则列出所有会话）

        Returns:
            可用的tick列表
        """
        try:
            if session_id:
                # 列出特定会话的tick
                session_dir = os.path.join(self.snapshots_dir, session_id)
                if not os.path.exists(session_dir):
                    return []

                ticks = []
                for item in os.listdir(session_dir):
                    if item.startswith("tick_"):
                        tick_num = int(item.split("_")[1])
                        ticks.append(tick_num)
                return sorted(ticks)
            else:
                # 列出所有会话的tick
                metadata = self._load_metadata()
                ticks = []
                for tick_str in metadata.get("ticks", {}).keys():
                    ticks.append(int(tick_str))
                return sorted(ticks)

        except Exception as e:
            logger.error(f"❌ 列出可用tick失败: {e}")
            return []

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有快照会话

        Returns:
            会话信息列表
        """
        try:
            sessions = []
            if not os.path.exists(self.snapshots_dir):
                return sessions

            for session_id in os.listdir(self.snapshots_dir):
                session_dir = os.path.join(self.snapshots_dir, session_id)
                if not os.path.isdir(session_dir):
                    continue

                # 读取会话元数据
                metadata_path = os.path.join(session_dir, "metadata.json")
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        session_metadata = json.load(f)
                        sessions.append(session_metadata)
                else:
                    # 如果没有元数据文件，创建基本信息
                    tick_count = len([d for d in os.listdir(session_dir) if d.startswith("tick_")])
                    sessions.append({
                        "session_id": session_id,
                        "created_at": "Unknown",
                        "tick_count": tick_count
                    })

            # 按创建时间排序
            sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return sessions

        except Exception as e:
            logger.error(f"❌ 列出会话失败: {e}")
            return []

    def cleanup_old_snapshots(self, keep_sessions: int = 5) -> None:
        """
        清理旧的快照会话，保留最近的几个

        Args:
            keep_sessions: 保留的会话数量
        """
        try:
            sessions = self.list_sessions()

            if len(sessions) <= keep_sessions:
                return

            # 删除旧的会话
            sessions_to_delete = sessions[keep_sessions:]
            for session in sessions_to_delete:
                session_id = session.get("session_id")
                session_dir = os.path.join(self.snapshots_dir, session_id)

                if os.path.exists(session_dir):
                    shutil.rmtree(session_dir)
                    logger.info(f"🗑️  已删除旧快照会话: {session_id}")

        except Exception as e:
            logger.error(f"❌ 清理旧快照失败: {e}")

    def cleanup_all_snapshots(self) -> None:
        """
        清理所有快照（在启动main.py时调用）
        """
        try:
            if os.path.exists(self.snapshots_dir):
                shutil.rmtree(self.snapshots_dir)
                os.makedirs(self.snapshots_dir, exist_ok=True)
                logger.info("🗑️  已清理所有快照数据")

        except Exception as e:
            logger.error(f"❌ 清理所有快照失败: {e}")

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            会话信息字典
        """
        try:
            metadata_file = os.path.join(self.snapshots_dir, session_id, "metadata.json")
            if not os.path.exists(metadata_file):
                return None

            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"❌ 获取会话信息失败: {e}")
            return None

    def _load_metadata(self) -> Dict[str, Any]:
        """加载元数据"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"❌ 加载元数据失败: {e}")

        # 返回默认元数据
        return {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "ticks": {}
        }

    def _save_metadata(self, metadata: Dict[str, Any]) -> None:
        """保存元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存元数据失败: {e}")


def create_snapshot_manager(project_root: str, simulation_db_path: str) -> SnapshotManager:
    """
    创建快照管理器实例

    Args:
        project_root: 项目根目录
        simulation_db_path: 模拟数据库路径

    Returns:
        SnapshotManager实例
    """
    return SnapshotManager(project_root, simulation_db_path)
