from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.database import init_db
from routers import auth, onboarding, clients, remote_write
from core.cert_authority import bootstrap_ca, CA_CERT_PATH
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if not CA_CERT_PATH.exists():
        bootstrap_ca()
    yield


app = FastAPI(title="MaaS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(clients.router)
app.include_router(remote_write.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
