from app.core.config import get_settings
from app.models.user import PlanType

settings = get_settings()


def get_limit_for_plan(plan: PlanType) -> int:
    if plan == PlanType.ELITE:
        return settings.ELITE_MESSAGES_LIMIT
    if plan == PlanType.PRO:
        return settings.PRO_MESSAGES_LIMIT
    return settings.FREE_MESSAGES_LIMIT


def can_send_message(messages_used: int, plan: PlanType) -> bool:
    limit = get_limit_for_plan(plan)
    return messages_used < limit


def remaining_messages(messages_used: int, plan: PlanType) -> int:
    limit = get_limit_for_plan(plan)
    return max(0, limit - messages_used)
