"""FastAPI 入口：启动时初始化数据库（可选种子数据），挂载 API 与静态前端。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import analysis, assertions, export, sources, transcripts
from .seed import seed_if_empty

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    yield


app = FastAPI(title="采访事实核查工作台", version="1.0.0", lifespan=lifespan)

app.include_router(assertions.router)
app.include_router(sources.router)
app.include_router(transcripts.router)
app.include_router(analysis.router)
app.include_router(export.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
