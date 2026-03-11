import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from src import config

log = logging.getLogger("polybot")

def is_in_cooldown() -> bool:
    """
    Check if the current time is within the configured cooldown window.
    Times are compared in the configured timezone (default US/Eastern).
    """
    try:
        tz = ZoneInfo(config.COOLDOWN_TIMEZONE)
        now = datetime.now(tz)
        current_time_str = now.strftime("%H:%M")
        
        # Simple string comparison works for HH:MM format
        is_cooldown = config.COOLDOWN_START_TIME <= current_time_str <= config.COOLDOWN_END_TIME
        
        return is_cooldown
    except Exception as e:
        log.error("Error checking cooldown status: %s", e)
        return False
