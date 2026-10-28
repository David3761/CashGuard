"""`load_user_context`: the complete, immutable view of one user (B4).

STUB until B4: returns the hand-made Matei from `tests/builders.py` for any user, so the engine,
the context layer and the snapshot builder can integrate now. Real version: B4 step 1.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import UserContext


async def load_user_context(
    db: AsyncSession, user_id: int, today: date, history_days: int = 180
) -> UserContext:
    """Everything about `user_id` on `today`: profile, account, goal + goal pot, income, fixed
    costs, planned events, active pots, open receivables, confirmed facts active on `today`,
    hypotheses, active signatures and rules, plan preferences, baselines, resolved transactions
    of the last `history_days`, latest plan, latest + last weekly forecast, pending/asked events,
    and how many questions were asked today. A few batched queries, no N+1 (≤ 10 statements)."""
    from tests.builders import matei_ctx  # stub only; the real loader reads the DB

    return matei_ctx(today=today)
