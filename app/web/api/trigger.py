from fastapi import APIRouter, BackgroundTasks
from app.worker.main import job_snapshot, job_subscribe, job_reconcile

router = APIRouter()


@router.post("/snapshot")
async def trigger_snapshot(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_snapshot)
    return {"status": "triggered", "job": "snapshot"}


@router.post("/subscribe")
async def trigger_subscribe(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_subscribe)
    return {"status": "triggered", "job": "subscribe"}


@router.post("/reconcile")
async def trigger_reconcile(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_reconcile)
    return {"status": "triggered", "job": "reconcile"}
