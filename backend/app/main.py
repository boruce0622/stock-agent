from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.ai_config import router as ai_config_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.market_config import router as market_config_router
from app.api.v1.market_data import router as market_data_router
from app.api.v1.router import router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.services.chat_service import recover_incomplete_runs, shutdown_background_runs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if (
        settings.app_env not in {"development", "test"}
        and settings.app_encryption_key == "development-only-change-before-production"
    ):
        raise RuntimeError("生产环境必须配置独立的 APP_ENCRYPTION_KEY")
    # Development bootstrap only; production should run Alembic migrations.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await recover_incomplete_runs()
    try:
        yield
    finally:
        await shutdown_background_runs()
        await engine.dispose()


settings = get_settings()
app = FastAPI(title="Stock Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(ai_config_router)
app.include_router(market_config_router)
app.include_router(market_data_router)
app.include_router(knowledge_router)


@app.get("/")
async def root() -> dict:
    return {
        "name": "Stock Agent API",
        "docs": "/docs",
        "features": ["ai-provider-catalog"],
    }
