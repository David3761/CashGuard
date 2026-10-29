"""Shared FastAPI dependency aliases for the routers."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db.session import get_db
from app.domain.models import UserProfile

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[UserProfile, Depends(current_user)]
