import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import get
from src.api.routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Renew Gmail watch on startup
    try:
        topic = get("GMAIL_PUBSUB_TOPIC")
        if topic:
            from src.core.email.gmail_client import get_gmail_service

            service = get_gmail_service()
            if service:
                result = (
                    service.users()
                    .watch(
                        userId="me",
                        body={"topicName": topic, "labelIds": ["INBOX"]},
                    )
                    .execute()
                )
                logger.info(
                    "Gmail watch renewed: expiration=%s", result.get("expiration")
                )
    except Exception as exc:
        logger.warning("Gmail watch renewal failed: %s", exc)
    yield


app = FastAPI(title="Patty API", lifespan=lifespan)

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
