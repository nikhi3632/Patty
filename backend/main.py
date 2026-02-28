import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import get
from src.api.routes import router

app = FastAPI(title="Patty API")

cors_origins = get("CORS_ORIGINS")
allowed_origins = cors_origins.split(",") if cors_origins else ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
