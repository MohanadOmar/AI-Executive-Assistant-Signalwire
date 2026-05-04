"""SMS webhook for SignalWire — handles both LaML (form) and JSON webhooks."""
import os
import hmac
import hashlib
import base64
import json
from fastapi import APIRouter, Request, Response

from agent import run_agent
from system_prompts import get_sms_system_prompt

router = APIRouter()


async def parse_signalwire_payload(request: Request) -> dict:
    """Parse SignalWire payload — handles both form-encoded (LaML) and JSON."""
    content_type = request.headers.get("content-type", "")
    print(f"[SMS Debug] Content-Type: {content_type}")

    # Read raw body for logging + JSON parsing
    raw = await request.body()
    print(f"[SMS Debug] Raw body length: {len(raw)} bytes")
    if raw:
        print(f"[SMS Debug] Raw body preview: {raw[:300]!r}")

    # Try JSON first
    if "application/json" in content_type:
        try:
            payload = json.loads(raw)
            # SignalWire JSON webhook nests message info — flatten it
            # Common shapes: { "From": "...", "Body": "..." } or { "params": { "from": ..., "body": ... } }
            if "params" in payload and isinstance(payload["params"], dict):
                p = payload["params"]
                return {
                    "From": p.get("from") or p.get("From", ""),
                    "Body": p.get("body") or p.get("Body", ""),
                    "To": p.get("to") or p.get("To", ""),
                    **payload,
                }
            return payload
        except Exception as e:
            print(f"[SMS] JSON parse failed: {e}")

    # Fall back to form-encoded
    try:
        form = await request.form()
        return dict(form)
    except Exception as e:
        print(f"[SMS] Form parse failed: {e}")

    # Last resort — try parsing raw as form
    try:
        from urllib.parse import parse_qs
        parsed = parse_qs(raw.decode())
        return {k: v[0] if v else "" for k, v in parsed.items()}
    except Exception:
        return {}


@router.post("/incoming")
async def incoming_sms(request: Request):
    data = await parse_signalwire_payload(request)

    from_number = data.get("From", "") or data.get("from", "")
    body = (data.get("Body", "") or data.get("body", "")).strip()

    print(f"[SMS In] From={from_number!r} Body={body!r}")
    print(f"[SMS Debug] All keys: {list(data.keys())}")

    if not from_number or not body:
        print("[SMS] Skipping — empty From or Body")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="text/xml",
        )

    try:
        reply = run_agent(
            user_message=body,
            system_prompt=get_sms_system_prompt(),
            phone_number=from_number,
        )
        print(f"[SMS Out] To {from_number}: {reply}")
    except Exception as e:
        print(f"[SMS Error] {e}")
        reply = "Dodo hit an error. Try again in a moment."

    # Always return LaML — works for both LaML and JSON webhook configs
    laml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{reply}</Message>
</Response>"""
    return Response(content=laml, media_type="text/xml")
