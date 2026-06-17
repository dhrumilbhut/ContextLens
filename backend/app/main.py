import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import database, redis
from app.config import VERSION
from app.routers import api_keys, health, ingest, projects, traces

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.create_pool()
    logger.info("database pool created")
    await redis.create_connection()
    logger.info("redis connection created")
    yield
    await database.close_pool()
    await redis.close_connection()


app = FastAPI(title="ContextLens API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(projects.router)
app.include_router(api_keys.router)
app.include_router(traces.router)
app.include_router(health.router)
