from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, server_message
from services.auth_service import get_current_active_user
from services.stats_service import get_overview_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _require_admin(current_user=Depends(get_current_active_user)):
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)
    return current_user


@router.get("/overview")
def stats_overview(db: Session = Depends(get_db), _admin=Depends(_require_admin)):
    data = get_overview_stats(db)
    return server_message("SUCCESS", data=data)
