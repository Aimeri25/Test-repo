"""
Main Flask application.
- POST /sms     — Twilio webhook for inbound SMS
- POST /cancel  — Customer-facing cancellation link (optional)
- GET  /health  — Health check
"""

from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

import config
import database as db
from ai_agent import process_message
from reminders import start_scheduler

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

_validator = RequestValidator(config.TWILIO_AUTH_TOKEN)


def _validate_twilio_request() -> bool:
    """Verify the request genuinely came from Twilio."""
    signature = request.headers.get("X-Twilio-Signature", "")
    url = request.url
    params = request.form.to_dict()
    return _validator.validate(url, params, signature)


@app.route("/sms", methods=["POST"])
def sms_webhook():
    if config.TWILIO_AUTH_TOKEN and not _validate_twilio_request():
        return Response("Forbidden", status=403)

    from_phone = request.form.get("From", "").strip()
    body = request.form.get("Body", "").strip()

    if not from_phone or not body:
        return Response("Bad Request", status=400)

    # Check for CANCEL keyword
    if body.upper() in ("CANCEL", "STOP", "UNSUBSCRIBE"):
        _handle_cancellation_keyword(from_phone)
        reply_text = (
            f"Your appointment has been cancelled. "
            f"Text us anytime to rebook! — {config.STYLIST_NAME}"
        )
    else:
        try:
            reply_text = process_message(from_phone, body)
        except Exception as e:
            print(f"[sms] Error processing message from {from_phone}: {e}")
            reply_text = (
                f"Sorry, I ran into a hiccup! {config.STYLIST_NAME} will "
                f"follow up with you shortly."
            )

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(str(twiml), mimetype="text/xml")


def _handle_cancellation_keyword(phone: str):
    """Cancel the next upcoming appointment for this customer."""
    customer = db.get_customer_by_phone(phone)
    if not customer:
        return
    appointments = db.get_customer_appointments(customer["id"])
    upcoming = [
        a for a in appointments
        if a["status"] == "confirmed" and a["datetime_utc"] > __import__("datetime").datetime.utcnow().isoformat()
    ]
    if upcoming:
        db.cancel_appointment(upcoming[0]["id"])


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "stylist": config.STYLIST_NAME, "salon": config.SALON_NAME}


if __name__ == "__main__":
    db.init_db()
    scheduler = start_scheduler()
    try:
        app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
    finally:
        scheduler.shutdown()
