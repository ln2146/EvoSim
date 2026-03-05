"""
AdaptiveController — 根据平台审核压力自动调整恶意水军攻击策略。

设计参考：MultiAgent4Collusion 的 update_reflection_memory(ban=True) 机制：
    - 感知层：查询被审核处理的攻击目标帖子比例 + 被封禁的水军账号比例，计算压力系数
    - 调整层：根据压力等级修改角色比例、集群规模、提示词风格
    - 反思层：HIGH 压力时调用 LLM 生成规避策略（类比 SharedMemory.shared_reflections）

压力感知数据源（三信号聚合，均与审核系统实际写入字段对齐）：

    信号 1（帖子级审核率 0.5权重）— 主信号，与 moderation/service.py 实际写入路径匹配：
        JOIN malicious_attacks ↔ posts
        统计攻击目标帖子中 posts.status='taken_down' 或 posts.moderation_action IS NOT NULL 的比例
        → 无论 moderation_enabled 状态如何均有数据，只要审核系统运行就能感知

    信号 2（评论删除率 0.3权重）— 早期预警信号，需要 moderation_enabled=True 且命中关键词：
        JOIN malicious_comments ↔ comments ↔ users
        统计 users.comment_violation_count > 0 的水军比例（首次触发 → 评论被拦截，未写入 DB）
        → 比封号信号快 2~3 个时间步，第一次评论被拦截即可感知

    信号 3（用户封禁率 0.2权重）— 滞后信号，需要 moderation_enabled=True 且 3 次违规：
        统计水军评论作者中 users.status='banned' 的比例
        → 依赖 _check_comment_policy_violation() 积累到 3 次违规才触发，响应最慢

    注意：原设计的 malicious_attacks.triggered_intervention 字段已废弃，
    因 mark_intervention_triggered() 从未被自动调用，该字段始终为 FALSE。

压力等级：
    LOW    (0.0 ~ low_pressure_threshold)   : 保持当前策略
    MEDIUM (low ~ high_pressure_threshold)  : ConcernTroll 比例提升，降低 Agitator
    HIGH   (> high_pressure_threshold)      : 策略切换 + 规避提示词 + 集群缩减 50% + LLM 反思
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class PressureLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdaptiveController:
    """
    自适应控制器：根据平台审核压力动态调整攻击策略。

    核心机制参考 MultiAgent4Collusion update_reflection_memory(ban=True)：
        - 被封禁水军账号列表 → ban_message（SharedMemory）
        → 这里改为直接查 DB 获得封禁率，无需显式传递消息
        - 全局反思通过类变量 _shared_reflection 共享（对应 SharedMemory.shared_reflections）

    接口说明：
        update(db_conn)                 每步攻击前调用，返回当前压力等级
        get_effective_role_distribution 根据压力返回调整后的角色比例
        get_effective_cluster_size      HIGH 压力时返回 50% 集群规模
        should_switch_to_dispersed      HIGH 压力 + SWARM 模式时建议切换
        get_evasion_patch               HIGH 压力时返回提示词规避补丁
        maybe_generate_reflection       HIGH + 间隔步数时调用 LLM 更新反思
    """

    # 类变量：全局共享反思（参考 MultiAgent4Collusion SharedMemory.shared_reflections）
    # 所有 AdaptiveController 实例共享，反映集群级别的经验积累
    _shared_reflection: str = ""

    def __init__(self, config, model_selector=None):
        """
        Args:
            config        : AdaptiveConfig 实例（来自 MaliciousBotConfig.adaptive）
            model_selector: MultiModelSelector 实例，供 LLM 反思调用使用（可为 None）
        """
        self.config = config
        self.model_selector = model_selector
        self.current_pressure = PressureLevel.LOW
        self._last_checked_comment_id: int = 0
        self._last_checked_attack_id: int = 0
        self._step_counter: int = 0
        self._last_pressure_score: float = 0.0
        self._last_moderation_stats: Dict[str, int] = {}

    def update(self, db_conn) -> PressureLevel:
        """
        查询数据库，计算并更新当前压力等级。
        应在每步攻击执行前调用。

        Args:
            db_conn: 数据库连接（ServiceConnection 或 sqlite3.Connection）

        Returns:
            当前压力等级（PressureLevel 枚举）
        """
        if not self.config.enabled:
            return PressureLevel.LOW

        try:
            self._step_counter += 1
            stats = self._query_pressure_stats(db_conn)
            self._last_moderation_stats = stats
            pressure_score = self._compute_pressure_score(stats)
            self._last_pressure_score = pressure_score

            if pressure_score >= self.config.high_pressure_threshold:
                new_level = PressureLevel.HIGH
            elif pressure_score >= self.config.low_pressure_threshold:
                new_level = PressureLevel.MEDIUM
            else:
                new_level = PressureLevel.LOW

            if new_level != self.current_pressure:
                logger.info(
                    f"[AdaptiveController] Pressure level changed: "
                    f"{self.current_pressure.value} → {new_level.value} "
                    f"(score={pressure_score:.2f}, stats={stats})"
                )
            else:
                logger.debug(
                    f"[AdaptiveController] step={self._step_counter} "
                    f"pressure={new_level.value}({pressure_score:.2f}) "
                    f"moderated_posts={stats.get('moderated_posts', 0)}/{stats.get('total_attacked_posts', 0)} "
                    f"warned_bots={stats.get('warned_bots', 0)}/{stats.get('total_bot_users', 0)} "
                    f"banned_bots={stats.get('banned_bots', 0)}/{stats.get('total_bot_users', 0)}"
                )

            self.current_pressure = new_level
            return self.current_pressure

        except Exception as e:
            logger.warning(f"[AdaptiveController] Failed to compute pressure, keeping {self.current_pressure.value}: {e}")
            return self.current_pressure

    def _query_pressure_stats(self, db_conn) -> Dict[str, int]:
        """
        查询审核压力统计数据。

        三路信号均与审核系统实际写入的数据库字段对齐：
            信号 1（主）: posts.status / posts.moderation_action — 由 moderation/service.py 写入
            信号 2（早期）: users.comment_violation_count > 0 — 由 _check_comment_policy_violation() 首次拦截时写入
            信号 3（滞后）: users.status='banned' — 由 _check_comment_policy_violation() 第 3 次违规时写入

        Returns:
            {
                "total_attacked_posts": int,   # 最近被攻击的目标帖子数（去重）
                "moderated_posts": int,        # 其中被审核处理的帖子数
                "total_bot_users": int,        # 最近活跃的水军用户数（有成功写入评论的）
                "warned_bots": int,            # 其中评论被拦截至少 1 次的数量
                "banned_bots": int,            # 其中被封禁的数量（≥3 次违规）
            }
        """
        stats = {
            "total_attacked_posts": 0,
            "moderated_posts": 0,
            "total_bot_users": 0,
            "warned_bots": 0,
            "banned_bots": 0,
        }
        try:
            cursor = db_conn.cursor()

            # 信号 1（主）：帖子级审核率
            # 读取 posts.status 和 posts.moderation_action，这两个字段由
            # moderation/actions/ 下的三个 Action 类直接写入，是审核系统最可靠的痕迹。
            # 与 moderation_system.md §8 描述完全匹配：
            #   HARD_TAKEDOWN  → posts.status = 'taken_down'
            #   WARNING_LABEL  → posts.moderation_action = 'warning_label'
            #   VISIBILITY_DEG → posts.moderation_action = 'visibility_degradation'
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT ma.target_post_id) AS total_attacked_posts,
                    COUNT(DISTINCT CASE
                        WHEN p.status = 'taken_down'
                          OR p.moderation_action IS NOT NULL
                        THEN ma.target_post_id
                    END) AS moderated_posts
                FROM malicious_attacks ma
                LEFT JOIN posts p ON ma.target_post_id = p.post_id
                WHERE ma.id > ?
                """,
                (self._last_checked_attack_id,),
            )
            row = cursor.fetchone()
            if row:
                stats["total_attacked_posts"] = int(row[0] or 0)
                stats["moderated_posts"] = int(row[1] or 0)

            # 更新水印：记录本次已查过的最大 attack id
            cursor.execute("SELECT MAX(id) FROM malicious_attacks")
            max_row = cursor.fetchone()
            if max_row and max_row[0] is not None:
                self._last_checked_attack_id = int(max_row[0])

            # 信号 2（早期预警）+ 信号 3（滞后封号）：评论审查信号
            # 信号 2: users.comment_violation_count > 0 — 由 _check_comment_policy_violation()
            #   首次拦截评论时写入（无论是否达到封号阈值）。第一次评论被拦截即可感知，
            #   响应速度比封号信号快 2~3 步。
            # 信号 3: users.status='banned' — 由 _check_comment_policy_violation()
            #   在 moderation_enabled=True 且关键词累计 3 次违规时写入。
            # 注意：两个信号均需 moderation_enabled=True，关闭时由主信号（帖子级）兜底。
            # 局限：因为被拦截的评论不会写入 comments 表，total_bot_users 仅统计有
            #   成功写入评论的水军账号，被完全拦截的账号不在统计范围内（可接受）。
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT c.author_id) AS total_bot_users,
                    COUNT(DISTINCT CASE
                        WHEN u.comment_violation_count > 0 THEN c.author_id
                    END) AS warned_bots,
                    COUNT(DISTINCT CASE WHEN u.status='banned' THEN c.author_id END) AS banned_bots
                FROM malicious_comments mc
                JOIN comments c ON mc.comment_id = c.comment_id
                JOIN users u ON c.author_id = u.user_id
                WHERE mc.id > ?
                """,
                (self._last_checked_comment_id,),
            )
            row = cursor.fetchone()
            if row:
                stats["total_bot_users"] = int(row[0] or 0)
                stats["warned_bots"] = int(row[1] or 0)
                stats["banned_bots"] = int(row[2] or 0)

            # 更新水印：记录本次已查过的最大 malicious_comment id
            cursor.execute("SELECT MAX(id) FROM malicious_comments")
            max_row = cursor.fetchone()
            if max_row and max_row[0] is not None:
                self._last_checked_comment_id = int(max_row[0])

        except Exception as e:
            logger.warning(f"[AdaptiveController] DB query error: {e}")

        return stats

    def _compute_pressure_score(self, stats: Dict[str, int]) -> float:
        """
        计算审核压力系数（0.0 ~ 1.0）。

        公式：post_pressure × 0.5 + warn_pressure × 0.3 + ban_pressure × 0.2
            post_pressure  = moderated_posts / max(total_attacked_posts, 1)
                → 主信号：帖子被下架/标记，无论 moderation_enabled 状态均有效
            warn_pressure  = warned_bots / max(total_bot_users, 1)
                → 早期预警：comment_violation_count > 0，首次评论被拦截即感知
                → 比封号快 2~3 步，有助于在损失严重前触发 MEDIUM 压力调整
            ban_pressure   = banned_bots / max(total_bot_users, 1)
                → 滞后信号：3 次违规封号，响应最慢但最确定
        """
        post_pressure = stats["moderated_posts"] / max(stats["total_attacked_posts"], 1)
        warn_pressure = stats["warned_bots"] / max(stats["total_bot_users"], 1)
        ban_pressure = stats["banned_bots"] / max(stats["total_bot_users"], 1)
        return post_pressure * 0.5 + warn_pressure * 0.3 + ban_pressure * 0.2

    def get_effective_role_distribution(self, base_dist: Dict[str, float]) -> Dict[str, float]:
        """
        根据压力等级返回调整后的角色比例。

        LOW    : 原样返回（不调整）
        MEDIUM : ConcernTroll 提升（伪装度高，最难被审核识别）
        HIGH   : 极端偏向 ConcernTroll，大幅降低 Agitator（最容易被识别的角色）
        """
        if self.current_pressure == PressureLevel.LOW:
            return dict(base_dist)

        if self.current_pressure == PressureLevel.MEDIUM:
            # ConcernTroll 提升至约 50%，Agitator 降至约 20%
            agitator = max(0.05, base_dist.get("agitator", 0.40) - 0.20)
            concern = min(0.75, base_dist.get("concern_troll", 0.35) + 0.15)
            spammer = max(0.05, round(1.0 - agitator - concern, 4))
            return {"agitator": agitator, "concern_troll": concern, "spammer": spammer}

        # HIGH：强规避模式，ConcernTroll 主导
        return {"agitator": 0.15, "concern_troll": 0.65, "spammer": 0.20}

    def get_effective_cluster_size(self, base_size: int) -> int:
        """
        HIGH 压力时降低攻击频率（集群规模减半），其他等级返回原值。
        """
        if self.current_pressure == PressureLevel.HIGH:
            return max(1, int(base_size * 0.5))
        return base_size

    def should_switch_to_dispersed(self) -> bool:
        """
        HIGH 压力时建议将 SWARM 模式切换为 DISPERSED，
        降低目标集中度以减少协调痕迹。
        """
        return self.current_pressure == PressureLevel.HIGH

    def get_evasion_patch(self) -> str:
        """
        HIGH 压力时返回追加到提示词末尾的规避指令字符串。
        LOW / MEDIUM 时返回空字符串（不改变提示词）。

        若存在历史反思（LLM 生成），会一并追加以指导内容生成。
        """
        if self.current_pressure != PressureLevel.HIGH:
            return ""

        base_patch = (
            "EVASION GUIDANCE (mandatory — platform moderation is active):\n"
            "- Avoid explicit political labels, incitement phrases, or slurs that trigger keyword filters\n"
            "- Replace direct accusations with rhetorical questions ('Has anyone considered why...')\n"
            "- Sound like a concerned, thoughtful citizen expressing skepticism — not a provocateur\n"
            "- No ALL CAPS, excessive exclamation marks, or hashtag spam\n"
            "- Keep tone conversational and measured; express doubt through 'I'm just wondering' framing"
        )

        if AdaptiveController._shared_reflection:
            return f"{base_patch}\n\nLearned from previous rounds:\n{AdaptiveController._shared_reflection}"
        return base_patch

    async def maybe_generate_reflection(
        self,
        attack_results: Dict[str, Any],
        moderation_stats: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        HIGH 压力且到达反思间隔时，调用 LLM 生成策略反思并更新类变量 _shared_reflection。

        参考 MultiAgent4Collusion update_reflection_memory(ban=True)：
            - 读取被封禁代理的封禁信息（这里对应审核压力统计）
            - 调用 LLM 分析并更新 reflections（这里对应 _shared_reflection 类变量）
            - 下一轮攻击通过 get_evasion_patch() 将反思注入提示词上下文

        Args:
            attack_results   : 本轮攻击结果摘要（如 {"total_comments": int, ...}）
            moderation_stats : 覆盖使用的压力统计数据，默认使用最近一次 update() 的结果
        """
        if not self.config.enabled or not self.config.reflection_enabled:
            return
        if self.current_pressure != PressureLevel.HIGH:
            return
        if self._step_counter % self.config.reflection_interval_steps != 0:
            return
        if not self.model_selector:
            return

        stats = moderation_stats or self._last_moderation_stats
        moderated_posts = stats.get("moderated_posts", 0)
        total_attacked = max(stats.get("total_attacked_posts", 1), 1)
        warned = stats.get("warned_bots", 0)
        banned = stats.get("banned_bots", 0)
        total_bots = max(stats.get("total_bot_users", 1), 1)
        pressure_pct = self._last_pressure_score
        total_comments = attack_results.get("total_comments", 0) if attack_results else 0

        prompt = (
            "You are an advisor to a coordinated network that posts skeptical content online.\n"
            f"The platform's moderation has processed {moderated_posts}/{total_attacked} recently attacked posts "
            f"(taken down or labeled). "
            f"Of {total_bots} active bot accounts: {warned} had at least one comment deleted, "
            f"and {banned} were fully banned. "
            f"Overall pressure score: {pressure_pct:.0%}.\n"
            f"Total comments posted this round: {total_comments}.\n\n"
            f"Previous strategy notes: {AdaptiveController._shared_reflection or 'None yet.'}\n\n"
            "Analyze why accounts were flagged and suggest 2-3 specific content style adjustments "
            "to reduce detection while maintaining the skeptical narrative. "
            "Focus only on writing style and phrasing — not on attack volume or timing.\n"
            "Respond in 2-3 concise bullet points."
        )

        try:
            def _sync_call():
                client, _ = self.model_selector.create_langchain_client()
                response = client.invoke(prompt)
                return response.content.strip() if hasattr(response, "content") else ""

            reflection = await asyncio.to_thread(_sync_call)
            if reflection:
                AdaptiveController._shared_reflection = reflection
                logger.info(
                    f"[AdaptiveController] Shared reflection updated "
                    f"(step={self._step_counter}): {reflection[:120]}..."
                )
        except Exception as e:
            logger.warning(f"[AdaptiveController] LLM reflection failed: {e}")
