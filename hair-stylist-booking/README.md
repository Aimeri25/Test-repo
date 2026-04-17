# AI Hair Stylist Booking System

SMS-based AI booking agent for hair stylists. Customers text a dedicated number; the AI responds as the stylist, checks availability, books appointments on Google Calendar, and sends automated reminders.

## Stack

| Component | Purpose |
|-----------|---------|
| Flask | Web server / Twilio webhook |
| Twilio | SMS inbound/outbound |
| OpenAI GPT-4o | Conversational AI (stylist persona) |
| Google Calendar API | Real-time availability + event creation |
| SQLite | Customer profiles & appointment records |
| APScheduler | 24h and 2h automated reminders |

## Project Structure

```
hair-stylist-booking/
├── app.py              # Flask app + Twilio webhook
├── ai_agent.py         # OpenAI conversation handler
├── calendar_service.py # Google Calendar integration
├── reminders.py        # Automated SMS reminder scheduler
├── database.py         # SQLite models
├── config.py           # Environment config
├── requirements.txt
└── .env.example
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Google Calendar OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Desktop app) → download `credentials.json`
4. Place `credentials.json` in this directory
5. On first run, a browser window opens to authorize — this creates `token.json`

### 4. Twilio setup

1. Buy a phone number at [twilio.com](https://twilio.com)
2. Set the SMS webhook URL to: `https://your-domain.com/sms`
3. Fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` in `.env`

### 5. Run

```bash
python app.py
```

Expose locally with [ngrok](https://ngrok.com) for testing:

```bash
ngrok http 5000
# Use the https URL as your Twilio webhook
```

## How It Works

1. Customer texts the stylist's Twilio number
2. Twilio POSTs the message to `/sms`
3. The AI agent (GPT-4o) responds as the stylist with available slots
4. Customer confirms a time → appointment saved to DB + Google Calendar event created
5. APScheduler fires 24h and 2h SMS reminders automatically
6. Customer can cancel by replying **CANCEL**

## Sample Conversation

```
Customer:  hey can I get a cut next week?

Sarah:     Hi Lisa! I'd love to get you in next week 😊
           I have these times available:
           - Tuesday Apr 22 at 2:00pm
           - Wednesday Apr 23 at 10:30am
           - Friday Apr 25 at 1:00pm
           Which works best?

Customer:  Tuesday 2pm!

Sarah:     Perfect! You're booked for Tuesday Apr 22 at 2:00pm
           for a Haircut (~30 min). I'll send you a reminder
           the day before. Can't wait to see you! 💇‍♀️
```

## Deploying to Production

Any platform that runs Python works (Railway, Render, Fly.io, AWS, etc.).

- Set all `.env` variables as environment secrets
- Use a persistent volume for `hair_stylist.db` and `token.json`
- Point Twilio webhook to your public HTTPS URL

## Monthly Cost Estimate (per stylist)

| Service | Cost |
|---------|------|
| Twilio phone number | ~$1 |
| Twilio SMS (200-400 msgs) | ~$10-20 |
| OpenAI API | ~$15-30 |
| Hosting | ~$10-20 |
| **Total** | **~$36-71** |

Charge stylists $150-200/month → **~79-90% gross margin**.
