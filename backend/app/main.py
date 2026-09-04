from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.documents import seed_sample_documents
from app.services.users import seed_users
from app.storage.database import ensure_data_dirs, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    init_db()
    seed_users()
    seed_sample_documents()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Enterprise Knowledge Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    return app


app = create_app()
