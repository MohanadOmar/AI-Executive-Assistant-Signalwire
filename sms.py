"""SMS webhook for SignalWire JSON Messaging Handler.

SignalWire's JSON webhook does NOT use LaML responses. Replies must be sent
via a separate API call (handled by send_sms in tools.py).
"""
import os
import json
from fastapi import APIRouter, Request, Response

from agent import run_agent
from system_prompts import get_sms_system_prompt
from tools import send_sms

router = APIRouter()


async def parse_signalwire_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    raw = await request.body()

    print(f"[SMS Debug] Content-Type: {content_type}")
    print(f"[SMS Debug] Raw body length: {len(raw)} bytes")

    payload = {}
    if "application/json" in content_type:
        try:
            payload = json.loads(raw)
        except Exception as e:
            print(f"[SMS] JSON parse failed: {e}")
            return {}
    else:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception as e:
            print(f"[SMS] Form parse failed: {e}")
            return {}

    # SignalWire nests: { "message": { "from": ..., "body": ..., ... } }
    msg = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(msg, dict):
        return {
            "From": msg.get("from", ""),
            "Body": msg.get("body", ""),
            "To": msg.get("to", ""),
            "MessageId": msg.get("message_id", ""),
        }

    # LaML fallback
    return {
        "From": payload.get("From", "") or payload.get("from", ""),
        "Body": payload.get("Body", "") or payload.get("body", ""),
        "To": payload.get("To", "") or payload.get("to", ""),
    }


@router.post("/incoming")
async def incoming_sms(request: Request):
    data = await parse_signalwire_payload(request)

    from_number = data.get("From", "")
    body = data.get("Body", "").strip()

    print(f"[SMS In] From={from_number!r} Body={body!r}")

    if not from_number or not body:
        print("[SMS] Skipping — empty From or Body")
        return Response(status_code=200)

    # Inbound webhook only delivers — we send the reply via API
    try:
        reply = run_agent(
            user_message=body,
            system_prompt=get_sms_system_prompt(),
            phone_number=from_number,
        )
        print(f"[SMS Out] Replying to {from_number}: {reply}")

        # Actually send the reply via SignalWire API
        if reply:
            send_result = send_sms(to=from_number, message=reply)
            print(f"[SMS Sent] sid={send_result.get('sid')} status={send_result.get('status')}")

    except Exception as e:
        print(f"[SMS Error] {e}")
        try:
            send_sms(to=from_number, message="Dodo hit an error. Try again in a moment.")
        except Exception as e2:
            print(f"[SMS] Failed to send error reply too: {e2}")

    return Response(status_code=200)
