import os
from dotenv import load_dotenv

load_dotenv()

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Google Calendar
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

# Stylist profile (one stylist per deployment)
STYLIST_NAME = os.getenv("STYLIST_NAME", "Sarah")
SALON_NAME = os.getenv("SALON_NAME", "Sarah's Salon")
SALON_ADDRESS = os.getenv("SALON_ADDRESS", "")
STYLIST_PHONE = os.getenv("STYLIST_PHONE", TWILIO_PHONE_NUMBER)

# Booking settings
BOOKING_SLOT_MINUTES = int(os.getenv("BOOKING_SLOT_MINUTES", "30"))
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "9"))   # 9 AM
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "18"))      # 6 PM
BOOKING_DAYS_AHEAD = int(os.getenv("BOOKING_DAYS_AHEAD", "14"))      # 2 weeks

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "hair_stylist.db")

# Flask
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
