"""Webhook endpoint registration with SSRF protection."""
import uuid
from datetime import datetime, timezone

from auth import verify_api_key
from audit import log_webhook_created, log_webhook_deleted
from rate_limit import limiter, LIMIT_DEFAULT, LIMIT_REGISTER, LIMIT_FIRMWARE, LIMIT_PERSON, LIMIT_WEBHOOK
from validation import validate_webhook_url
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, field_validator

from db.postgres import WEBHOOKS, get_db

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    secret: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: str | HttpUrl) -> str:
        """Validate webhook URL for SSRF safety."""
        url_str = str(v)
        validate_webhook_url(url_str)  # Raises HTTPException if invalid
        return url_str


@router.get("")
@limiter.limit("100/minute")
async def list_webhooks(_: str = Depends(verify_api_key)):
    db = get_db()
    webhooks = []
    async for doc in db.collection(WEBHOOKS).stream():
        d = doc.to_dict()
        webhooks.append({"webhook_id": doc.id, "url": d.get("url"), "active": d.get("active", True)})
    return webhooks


@router.post("", status_code=201)
@limiter.limit("30/minute")
async def create_webhook(data: WebhookCreate, _: str = Depends(verify_api_key)):
    db = get_db()
    webhook_id = str(uuid.uuid4())
    url_str = str(data.url)
    await db.collection(WEBHOOKS).document(webhook_id).set({
        "url": url_str,
        "secret": data.secret,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    })
    await log_webhook_created(actor="api", webhook_id=webhook_id, url=url_str)
    return {"webhook_id": webhook_id, "url": url_str}


@router.delete("/{webhook_id}", status_code=204)
@limiter.limit("100/minute")
async def delete_webhook(webhook_id: str, _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(WEBHOOKS).document(webhook_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404)
    await doc_ref.delete()
    await log_webhook_deleted(actor="api", webhook_id=webhook_id)
