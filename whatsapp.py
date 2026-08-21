"""WhatsApp Business Cloud API integration.

You still need to do this yourself before this code does anything (I can't
provision it for you):
1. Create a Meta developer account -> developers.facebook.com
2. Create an app -> add the "WhatsApp" product -> you get a test phone number,
   a temporary access token, and a Phone Number ID for free.
3. Set env vars: WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN
   (WHATSAPP_VERIFY_TOKEN is a string YOU make up, used only for the webhook
   handshake below — put the same value in the Meta app's webhook config).
4. Set your webhook URL in the Meta app to: https://<your-render-url>/webhook/whatsapp
5. The free test number can only message numbers you've added as testers in the
   Meta dashboard — fine for a hackathon demo, this is not a scope gap in this code.

Text messages are fully handled end to end. Image messages (screenshots) are
detected and the media ID is extracted, but downloading + OCR is left as a
clearly marked TODO — that's a real scope item (needs an OCR call, e.g. a
hosted Tesseract endpoint or a cloud OCR API) and shouldn't be silently faked.
"""
import os

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "vivek-dev-verify-token")
GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta calls this once when you save the webhook URL in the dashboard."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    return PlainTextResponse(content="Verification failed", status_code=403)


def extract_inbound_message(payload: dict) -> dict | None:
    """Pull the first text/image message out of a WhatsApp webhook payload.
    Returns None if this payload isn't a user message (e.g. a status update)."""
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages")
        if not messages:
            return None
        message = messages[0]
        from_number = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            return {"from": from_number, "type": "text", "text": message["text"]["body"]}
        if msg_type == "image":
            return {
                "from": from_number,
                "type": "image",
                "media_id": message["image"]["id"],
                # TODO(member2/backend): download via GET {GRAPH_API_BASE}/{media_id}
                # (returns a short-lived media URL), fetch the bytes, run OCR, then
                # pass the extracted text into AnalyzeRequest.screenshot_text.
            }
        return {"from": from_number, "type": msg_type}
    except (KeyError, IndexError, TypeError):
        return None


async def send_whatsapp_reply(to_number: str, body: str) -> None:
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        # Not configured yet (e.g. running locally without Meta credentials) — no-op.
        return
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, headers=headers, json=payload)


def format_reply(risk_score: int, action: str, reason: str) -> str:
    emoji = {"Safe": "\u2705", "Caution": "\u26a0\ufe0f", "High-Risk": "\U0001f6a8", "Block": "\u26d4"}.get(action, "")
    return (
        f"{emoji} VIVEK Risk Assessment\n"
        f"Score: {risk_score}/100 — {action}\n"
        f"Why: {reason}\n\n"
        f"This is an automated check. When unsure, verify directly with the official "
        f"source using a number/website you looked up yourself — never one sent to you."
    )
