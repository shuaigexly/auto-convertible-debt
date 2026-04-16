from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.shared.db import get_db
from app.shared.models import Subscription, BondSnapshot
from app.shared.schemas import SubscriptionOut, BondSnapshotOut

router = APIRouter()


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    trade_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Subscription)
    if trade_date:
        stmt = stmt.where(Subscription.trade_date == trade_date)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/snapshots", response_model=list[BondSnapshotOut])
async def list_snapshots(
    trade_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(BondSnapshot)
    if trade_date:
        stmt = stmt.where(BondSnapshot.trade_date == trade_date)
    result = await session.execute(stmt)
    return result.scalars().all()
