from fastapi import FastAPI

from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router
from app.api.cases import router as cases_router
from app.api.risk import router as risk_router
from app.api.transactions import router as transactions_router
from app.core.config import API_PREFIX, APP_NAME
from app.core.errors import register_error_handlers

app = FastAPI(title=APP_NAME, version="0.6.0")
register_error_handlers(app)
for api_router in (
    transactions_router,
    alerts_router,
    cases_router,
    risk_router,
    analytics_router,
):
    app.include_router(api_router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "application": APP_NAME}
