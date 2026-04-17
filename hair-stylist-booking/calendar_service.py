"""
Google Calendar integration.
- Fetches busy blocks to compute available slots.
- Creates/deletes calendar events for bookings.
"""

from datetime import datetime, timedelta, timezone
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = None
    token_path = config.GOOGLE_TOKEN_FILE
    creds_path = config.GOOGLE_CREDENTIALS_FILE

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_available_slots(slot_duration_minutes: int = None) -> list[datetime]:
    """
    Returns available datetime slots within business hours for the next
    BOOKING_DAYS_AHEAD days, excluding times already blocked in Google Calendar.
    """
    slot_duration = slot_duration_minutes or config.BOOKING_SLOT_MINUTES

    now = datetime.now(timezone.utc)
    end_range = now + timedelta(days=config.BOOKING_DAYS_AHEAD)

    try:
        service = _get_service()
        busy_response = service.freebusy().query(body={
            "timeMin": now.isoformat(),
            "timeMax": end_range.isoformat(),
            "items": [{"id": config.GOOGLE_CALENDAR_ID}],
        }).execute()
        busy_blocks = busy_response["calendars"][config.GOOGLE_CALENDAR_ID]["busy"]
    except Exception as e:
        print(f"[calendar] Could not fetch busy times: {e}")
        busy_blocks = []

    busy_intervals = [
        (
            datetime.fromisoformat(b["start"]).replace(tzinfo=timezone.utc),
            datetime.fromisoformat(b["end"]).replace(tzinfo=timezone.utc),
        )
        for b in busy_blocks
    ]

    available = []
    cursor = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    while cursor < end_range:
        weekday = cursor.weekday()  # 0=Monday, 6=Sunday
        if weekday < 6:  # skip Sundays
            local_hour = cursor.hour  # simplified: assumes server in stylist timezone
            if config.BUSINESS_HOURS_START <= local_hour < config.BUSINESS_HOURS_END:
                slot_end = cursor + timedelta(minutes=slot_duration)
                if not _overlaps(cursor, slot_end, busy_intervals):
                    available.append(cursor)

        cursor += timedelta(minutes=slot_duration)

    return available


def _overlaps(start: datetime, end: datetime, busy: list) -> bool:
    for b_start, b_end in busy:
        if start < b_end and end > b_start:
            return True
    return False


def book_appointment_on_calendar(
    customer_name: str,
    customer_phone: str,
    dt: datetime,
    duration_minutes: int,
    service: str,
) -> str:
    """Creates a Google Calendar event and returns the event ID."""
    service_obj = _get_service()
    end_dt = dt + timedelta(minutes=duration_minutes)

    event = {
        "summary": f"{service} — {customer_name}",
        "description": f"Customer: {customer_name}\nPhone: {customer_phone}\nService: {service}",
        "start": {"dateTime": dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    created = service_obj.events().insert(
        calendarId=config.GOOGLE_CALENDAR_ID, body=event
    ).execute()

    return created["id"]


def delete_calendar_event(event_id: str):
    service = _get_service()
    service.events().delete(
        calendarId=config.GOOGLE_CALENDAR_ID, eventId=event_id
    ).execute()
