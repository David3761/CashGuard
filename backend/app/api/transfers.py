from fastapi import APIRouter

from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.services import accounts, pots, transfers

router = APIRouter(tags=["transfers"])


@router.post("/transfers/{transfer_id}/undo")
async def undo_transfer(transfer_id: int, user: CurrentUser, db: Db) -> s.TransferOut:
    """Undo once: the money goes back from the pot to the balance."""
    t = await transfers.undo(db, user.id, transfer_id)
    if t.pot_id is not None:
        await pots.add_saved(db, user.id, t.pot_id, -t.amount)
    await accounts.adjust_balance(db, user.id, t.amount)
    await db.commit()
    return s.TransferOut(**t.model_dump(include=set(s.TransferOut.model_fields)))
