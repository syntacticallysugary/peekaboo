"""Webhook endpoint registration."""
import uuid
from datetime import datetime, timezone

from auth import verify_api_key
from rate_limit import limiter, LIMIT_DEFAULT, LIMIT_REGISTER, LIMIT_FIRMWARE, LIMIT_PERSON, LIMIT_WEBHOOK
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from db.firestore import WEBHOOKS, get_db

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    secret: str | None = None


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
    await db.collection(WEBHOOKS).document(webhook_id).set({
        "url": str(data.url),
        "secret": data.secret,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    })
    return {"webhook_id": webhook_id, "url": str(data.url)}


@router.delete("/{webhook_id}", status_code=204)
@limiter.limit("100/minute")
async def delete_webhook(webhook_id: str, _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(WEBHOOKS).document(webhook_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404)
    await doc_ref.delete()
