import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
import config


@contextmanager
def get_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                name TEXT,
                notes TEXT,
                preferred_days TEXT DEFAULT '[]',
                preferred_times TEXT DEFAULT '[]',
                service_duration_minutes INTEGER DEFAULT 30,
                last_visit_date TEXT,
                conversation_history TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                datetime_utc TEXT NOT NULL,
                service TEXT,
                duration_minutes INTEGER NOT NULL,
                price REAL,
                status TEXT DEFAULT 'confirmed',
                google_event_id TEXT,
                reminder_24h_sent INTEGER DEFAULT 0,
                reminder_2h_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)


# --- Customer operations ---

def get_customer_by_phone(phone: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE phone = ?", (phone,)
        ).fetchone()
        return _row_to_customer(row) if row else None


def upsert_customer(phone: str, **kwargs) -> dict:
    customer = get_customer_by_phone(phone)
    if customer:
        if kwargs:
            fields = ", ".join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [phone]
            with get_db() as conn:
                conn.execute(
                    f"UPDATE customers SET {fields} WHERE phone = ?", values
                )
        return get_customer_by_phone(phone)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO customers (phone) VALUES (?)", (phone,)
        )
    if kwargs:
        with get_db() as conn:
            fields = ", ".join(f"{k} = ?" for k in kwargs)
            values = list(kwargs.values()) + [phone]
            conn.execute(
                f"UPDATE customers SET {fields} WHERE phone = ?", values
            )
    return get_customer_by_phone(phone)


def update_customer(phone: str, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [phone]
    with get_db() as conn:
        conn.execute(
            f"UPDATE customers SET {fields} WHERE phone = ?", values
        )


def get_conversation_history(phone: str) -> list:
    customer = get_customer_by_phone(phone)
    if not customer:
        return []
    return json.loads(customer.get("conversation_history") or "[]")


def append_conversation(phone: str, role: str, content: str):
    history = get_conversation_history(phone)
    history.append({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
    # Keep last 20 messages to avoid token bloat
    history = history[-20:]
    update_customer(phone, conversation_history=json.dumps(history))


def clear_conversation(phone: str):
    update_customer(phone, conversation_history="[]")


# --- Appointment operations ---

def create_appointment(customer_id: int, dt: datetime, service: str,
                       duration_minutes: int, price: float = None,
                       google_event_id: str = None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO appointments
               (customer_id, datetime_utc, service, duration_minutes, price, google_event_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (customer_id, dt.isoformat(), service, duration_minutes, price, google_event_id)
        )
        return cur.lastrowid


def get_appointment(appointment_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        return dict(row) if row else None


def get_upcoming_appointments_for_reminders() -> list[dict]:
    """Returns confirmed appointments that need reminders sent."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.*, c.phone, c.name
               FROM appointments a
               JOIN customers c ON a.customer_id = c.id
               WHERE a.status = 'confirmed'
               AND a.datetime_utc > datetime('now')
               ORDER BY a.datetime_utc ASC"""
        ).fetchall()
        return [dict(r) for r in rows]


def mark_reminder_sent(appointment_id: int, reminder_type: str):
    field = f"reminder_{reminder_type}_sent"
    with get_db() as conn:
        conn.execute(
            f"UPDATE appointments SET {field} = 1 WHERE id = ?", (appointment_id,)
        )


def cancel_appointment(appointment_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ?",
            (appointment_id,)
        )


def get_customer_appointments(customer_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM appointments
               WHERE customer_id = ? AND status != 'cancelled'
               ORDER BY datetime_utc DESC""",
            (customer_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_customer(row) -> dict:
    d = dict(row)
    for field in ("preferred_days", "preferred_times", "conversation_history"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    return d
