"""
AI conversation agent. Handles the OpenAI GPT-4 interaction, maintaining
the stylist persona and routing booking intents to the calendar service.
"""

from datetime import datetime, timedelta
import json
from openai import OpenAI
import config
import database as db
from calendar_service import get_available_slots, book_appointment_on_calendar

client = OpenAI(api_key=config.OPENAI_API_KEY)

SYSTEM_PROMPT_TEMPLATE = """You are {stylist_name}, a friendly hair stylist at {salon_name}.
You respond to customer text messages to schedule appointments.
Always respond as {stylist_name} in a warm, personal tone — never reveal you are an AI.

TODAY is {today}.

SALON INFO:
- Name: {salon_name}
- Address: {salon_address}
- Hours: {hours_start}AM - {hours_end}PM

CUSTOMER INFO:
{customer_info}

AVAILABLE APPOINTMENT SLOTS (next 14 days):
{available_slots}

INSTRUCTIONS:
1. Greet returning customers by name if you know them.
2. For new customers, ask for their name on first contact.
3. When a customer wants to book, offer 2-3 available time slots.
4. Confirm: date, time, service type, and estimated duration.
5. Once confirmed, output a JSON booking block EXACTLY like this (on its own line):
   BOOK_APPOINTMENT:{{"datetime":"YYYY-MM-DDTHH:MM:00","service":"<service name>","duration_minutes":<number>,"price":<number or null>}}
6. For cancellations, ask them to confirm, then output: CANCEL_APPOINTMENT:<appointment_id>
7. Keep responses SHORT — 1-4 sentences. This is SMS.
8. Use the customer's service history to estimate the correct duration (short trim ~20min, full cut ~40min, color ~90min).
9. If someone asks something you can't handle, say: "I'll have {stylist_name} follow up with you shortly!"

SERVICES & DEFAULT DURATIONS:
- Trim / bang trim: 20 min
- Haircut: 30-40 min
- Cut & style: 45-60 min
- Color / highlights: 90-120 min
- Blowout: 30-45 min
- Deep conditioning: 30 min
"""


def _build_customer_info(customer: dict | None) -> str:
    if not customer:
        return "New customer — no history yet."

    parts = [f"Name: {customer.get('name') or 'Unknown'}"]
    parts.append(f"Phone: {customer['phone']}")

    if customer.get("last_visit_date"):
        parts.append(f"Last visit: {customer['last_visit_date'][:10]}")

    if customer.get("service_duration_minutes"):
        parts.append(f"Typical service duration: {customer['service_duration_minutes']} min")

    if customer.get("notes"):
        parts.append(f"Notes: {customer['notes']}")

    appointments = db.get_customer_appointments(customer["id"])
    if appointments:
        recent = appointments[:3]
        history = ", ".join(
            f"{a['service']} on {a['datetime_utc'][:10]}"
            for a in recent if a.get("service")
        )
        if history:
            parts.append(f"Recent services: {history}")

    return "\n".join(parts)


def _format_slots(slots: list[datetime]) -> str:
    if not slots:
        return "No availability found in the next 14 days."
    lines = []
    for slot in slots[:12]:  # limit to avoid token overload
        lines.append(slot.strftime("- %A %b %-d at %-I:%M%p"))
    return "\n".join(lines)


def _extract_booking_command(text: str) -> dict | None:
    """Parse BOOK_APPOINTMENT JSON from AI response."""
    marker = "BOOK_APPOINTMENT:"
    if marker not in text:
        return None
    try:
        json_str = text.split(marker, 1)[1].strip().split("\n")[0]
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        return None


def _extract_cancel_command(text: str) -> int | None:
    """Parse CANCEL_APPOINTMENT:<id> from AI response."""
    marker = "CANCEL_APPOINTMENT:"
    if marker not in text:
        return None
    try:
        return int(text.split(marker, 1)[1].strip().split()[0])
    except (ValueError, IndexError):
        return None


def process_message(from_phone: str, incoming_text: str) -> str:
    """
    Main entry point. Takes an inbound SMS, runs it through the AI,
    handles any booking commands, and returns the reply text.
    """
    # Ensure customer record exists
    customer = db.upsert_customer(from_phone)

    # Append inbound message to history
    db.append_conversation(from_phone, "user", incoming_text)

    # Build conversation history for OpenAI (strip internal ts field)
    history = db.get_conversation_history(from_phone)
    messages_for_api = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    # Get availability
    try:
        slots = get_available_slots()
    except Exception:
        slots = []

    # Refresh customer after any upsert
    customer = db.get_customer_by_phone(from_phone)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        stylist_name=config.STYLIST_NAME,
        salon_name=config.SALON_NAME,
        salon_address=config.SALON_ADDRESS or "Contact us for address",
        today=datetime.now().strftime("%A, %B %-d %Y"),
        hours_start=config.BUSINESS_HOURS_START,
        hours_end=config.BUSINESS_HOURS_END,
        customer_info=_build_customer_info(customer),
        available_slots=_format_slots(slots),
    )

    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt}] + messages_for_api,
        max_tokens=300,
        temperature=0.7,
    )

    ai_reply = response.choices[0].message.content.strip()

    # Handle booking command embedded in reply
    booking_cmd = _extract_booking_command(ai_reply)
    if booking_cmd:
        ai_reply = _handle_booking(customer, booking_cmd, ai_reply)

    # Handle cancellation command
    cancel_id = _extract_cancel_command(ai_reply)
    if cancel_id:
        db.cancel_appointment(cancel_id)
        ai_reply = ai_reply.split("CANCEL_APPOINTMENT:")[0].strip()

    # Strip the raw command from what's sent to the customer
    if "BOOK_APPOINTMENT:" in ai_reply:
        ai_reply = ai_reply.split("BOOK_APPOINTMENT:")[0].strip()

    db.append_conversation(from_phone, "assistant", ai_reply)

    # Update customer name if AI learned it (heuristic: extract from context)
    _maybe_update_name(from_phone, history, incoming_text)

    return ai_reply


def _handle_booking(customer: dict, cmd: dict, original_reply: str) -> str:
    """Create DB record and Google Calendar event for a confirmed booking."""
    try:
        dt = datetime.fromisoformat(cmd["datetime"])
        service = cmd.get("service", "Appointment")
        duration = int(cmd.get("duration_minutes", config.BOOKING_SLOT_MINUTES))
        price = cmd.get("price")

        google_event_id = None
        try:
            google_event_id = book_appointment_on_calendar(
                customer_name=customer.get("name") or customer["phone"],
                customer_phone=customer["phone"],
                dt=dt,
                duration_minutes=duration,
                service=service,
            )
        except Exception as e:
            # Calendar failure shouldn't block the booking
            print(f"[calendar] Failed to create event: {e}")

        db.create_appointment(
            customer_id=customer["id"],
            dt=dt,
            service=service,
            duration_minutes=duration,
            price=price,
            google_event_id=google_event_id,
        )

        # Update customer's last visit tracking and typical duration
        db.update_customer(
            customer["phone"],
            service_duration_minutes=duration,
            last_visit_date=dt.isoformat(),
        )

    except Exception as e:
        print(f"[booking] Failed to create appointment: {e}")

    return original_reply


def _maybe_update_name(phone: str, history: list, latest_message: str):
    """Best-effort: persist customer name if we can extract it from context."""
    customer = db.get_customer_by_phone(phone)
    if customer and customer.get("name"):
        return  # already known

    # Look for name in recent assistant messages (AI may address customer by name)
    for msg in reversed(history[-6:]):
        if msg["role"] == "assistant":
            content = msg["content"]
            # Simple heuristic: "Hi <Name>!" patterns
            for prefix in ("Hi ", "Hello ", "Hey "):
                if prefix in content:
                    after = content.split(prefix, 1)[1]
                    candidate = after.split("!")[0].split(",")[0].strip()
                    if 2 <= len(candidate) <= 30 and candidate.replace(" ", "").isalpha():
                        db.update_customer(phone, name=candidate)
                        return
