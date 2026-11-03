"""Database package.

    connection.py      client + collections + indexes
    users.py           registration, lookup, rank role, streak, engage cache
    xp.py              direct XP changes + daily message-XP cap
    missions.py        mission completion (pause-aware, atomic)
    pause.py           GLOBAL pause / resume of mission XP
    games.py           mini-game betting (daily limit, settle, history)
    leaderboard.py     leaderboard + rank positions
    platform_stats.py  Discord / Telegram daily stats
    resets.py          weekly / monthly resets + CSV snapshots

Cogs should normally go through `services/` (which adds announcements and the
central rank check) rather than calling the XP functions here directly.
"""
from .connection import (
    setup_indexes, users_col, platform_stats_col, daily_xp_col, settings_col, game_history_col,
)
from .bets import (
    get_bet_status, get_game_stats, payout_multiplier, place_bet, refund_bet, settle_bet, settle_push,
)
from .game_stats import get_game_overview, period_range
from .leaderboard import get_leaderboard, get_user_rank_position
from .missions import complete_mission
from .pause import (
    flush_user_pending, get_pause_state, get_pause_summary, get_user_held, is_paused,
    pause_all, resume_all,
)
from .platform_stats import get_stats_range, record_stat_event
from .resets import generate_snapshot_csv, monthly_reset, weekly_reset
from .users import (
    get_current_rank, update_engage_cache, update_streak, update_user_rank,
    user_details, user_register,
)
from .xp import add_daily_xp, get_daily_xp_progress, xp_update

__all__ = [
    "setup_indexes", "users_col", "platform_stats_col", "daily_xp_col", "settings_col", "game_history_col",
    "get_bet_status", "get_game_stats", "payout_multiplier", "place_bet", "refund_bet", "settle_bet",
    "settle_push", "get_game_overview", "period_range",
    "get_leaderboard", "get_user_rank_position", "complete_mission",
    "flush_user_pending", "get_pause_state", "get_pause_summary", "get_user_held", "is_paused",
    "pause_all", "resume_all",
    "get_stats_range", "record_stat_event",
    "generate_snapshot_csv", "monthly_reset", "weekly_reset",
    "get_current_rank", "update_engage_cache", "update_streak", "update_user_rank",
    "user_details", "user_register",
    "add_daily_xp", "get_daily_xp_progress", "xp_update",
]
