"""
Automated SMS reminder system using APScheduler.
Runs two checks per minute; sends 24h and 2h reminders for confirmed appointments.
"""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client

import config
import database as db

_twilio = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def _send_sms(to: str, body: str):
    _twilio.messages.create(
        body=body,
        from_=config.TWILIO_PHONE_NUMBER,
        to=to,
    )


def _check_and_send_reminders():
    now = datetime.now(timezone.utc)
    appointments = db.get_upcoming_appointments_for_reminders()

    for appt in appointments:
        try:
            appt_dt = datetime.fromisoformat(appt["datetime_utc"]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        time_until = appt_dt - now
        phone = appt["phone"]
        name = appt.get("name") or "there"
        service = appt.get("service") or "appointment"
        time_str = appt_dt.strftime("%-I:%M%p").lower()
        date_str = appt_dt.strftime("%A, %b %-d")

        # 24-hour reminder (window: 23h to 25h before)
        if not appt["reminder_24h_sent"]:
            if timedelta(hours=23) <= time_until <= timedelta(hours=25):
                msg = (
                    f"Hi {name}! Just confirming your {service} tomorrow "
                    f"at {time_str} with {config.STYLIST_NAME} at {config.SALON_NAME}. "
                    f"Reply CANCEL to cancel. See you then!"
                )
                _send_sms(phone, msg)
                db.mark_reminder_sent(appt["id"], "24h")

        # 2-hour reminder (window: 1h50m to 2h10m before)
        if not appt["reminder_2h_sent"]:
            if timedelta(hours=1, minutes=50) <= time_until <= timedelta(hours=2, minutes=10):
                msg = (
                    f"Hey {name}! Your {service} with {config.STYLIST_NAME} "
                    f"is in 2 hours at {time_str}. "
                    f"{config.SALON_ADDRESS or config.SALON_NAME} — see you soon!"
                )
                _send_sms(phone, msg)
                db.mark_reminder_sent(appt["id"], "2h")


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _check_and_send_reminders,
        trigger="interval",
        minutes=5,
        id="reminder_check",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
