from fastapi import FastAPI
from app.web.api import accounts, config, history, trigger

app = FastAPI(title="CB Auto Subscribe")

app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(trigger.router, prefix="/api/trigger", tags=["trigger"])
