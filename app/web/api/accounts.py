from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.shared.db import get_db
from app.shared.models import Account
from app.shared.schemas import AccountCreate, AccountOut
from app.shared.crypto import encrypt, get_keys_from_env

router = APIRouter()


@router.get("/", response_model=list[AccountOut])
async def list_accounts(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Account))
    return result.scalars().all()


@router.post("/", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, session: AsyncSession = Depends(get_db)):
    primary_key, old_key = get_keys_from_env()
    encrypted = encrypt(body.credentials_plain, primary_key, old_key)
    account = Account(
        name=body.name,
        broker=body.broker,
        credentials_enc=encrypted,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@router.patch("/{account_id}/enable", response_model=AccountOut)
async def enable_account(account_id: int, session: AsyncSession = Depends(get_db)):
    account = await session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.enabled = True
    await session.commit()
    await session.refresh(account)
    return account


@router.patch("/{account_id}/disable", response_model=AccountOut)
async def disable_account(account_id: int, session: AsyncSession = Depends(get_db)):
    account = await session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.enabled = False
    await session.commit()
    await session.refresh(account)
    return account


@router.patch("/{account_id}/reset-circuit", response_model=AccountOut)
async def reset_circuit(account_id: int, session: AsyncSession = Depends(get_db)):
    account = await session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.circuit_broken = False
    account.consecutive_failures = 0
    await session.commit()
    await session.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
async def delete_account(account_id: int, session: AsyncSession = Depends(get_db)):
    account = await session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete account with existing subscription records",
        ) from None
