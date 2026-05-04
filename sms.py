"""SMS webhook for SignalWire — uses LaML response format."""
import os
import hmac
import hashlib
import base64
from fastapi import APIRouter, Request, Response

from agent import run_agent
from system_prompts import get_sms_system_prompt

router = APIRouter()


def validate_signalwire_signature(request_url: str, post_data: dict, signature: str, auth_token: str) -> bool:
    """SignalWire HMAC-SHA1 signature validation, same scheme as Twilio."""
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(post_data.items()))
    s = request_url + sorted_params
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@router.post("/incoming")
async def incoming_sms(request: Request):
    form = await request.form()
    data = dict(form)

    from_number = data.get("From", "")
    body = data.get("Body", "").strip()

    # Debug logging — print full payload so we can see what SignalWire sent
    print(f"[SMS In] From={from_number!r} Body={body!r}")
    print(f"[SMS Debug] All form keys: {list(data.keys())}")
    print(f"[SMS Debug] Headers: signalwire-sig={request.headers.get('X-Signalwire-Signature', 'MISSING')[:20]}...")

    # Signature validation — only enforce if explicitly enabled
    if os.getenv("VALIDATE_SIGNATURE", "false").lower() == "true":
        signature = request.headers.get("X-Signalwire-Signature", "")
        # Build the URL that SignalWire used to call us
        base_url = os.environ.get("BASE_URL", "").rstrip("/") + "/sms/incoming"
        token = os.environ.get("SIGNALWIRE_API_TOKEN", "")
        if not validate_signalwire_signature(base_url, data, signature, token):
            print(f"[SMS] Signature mismatch for url={base_url}")
            return Response(content="Forbidden", status_code=403)

    if not from_number or not body:
        print("[SMS] Skipping — empty From or Body")
        # Return empty LaML so SignalWire doesn't retry
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

    laml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{reply}</Message>
</Response>"""
    return Response(content=laml, media_type="text/xml")
