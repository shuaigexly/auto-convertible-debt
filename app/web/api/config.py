from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.shared.db import get_db
from app.shared.models import ConfigEntry
from app.shared.schemas import ConfigEntryOut, ConfigEntryCreate

router = APIRouter()


@router.get("/", response_model=list[ConfigEntryOut])
async def list_config(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(ConfigEntry))
    return result.scalars().all()


@router.put("/{key}", response_model=ConfigEntryOut)
async def upsert_config(
    key: Annotated[str, Path(max_length=100)],
    body: ConfigEntryCreate,
    session: AsyncSession = Depends(get_db),
):
    entry = await session.get(ConfigEntry, key)
    if entry:
        entry.value = body.value
    else:
        entry = ConfigEntry(key=key, value=body.value)
        session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry
