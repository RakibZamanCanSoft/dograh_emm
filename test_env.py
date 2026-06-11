from dotenv import load_dotenv
import os

load_dotenv("api/.env")
val = os.getenv("DISABLE_NEW_REGISTRATIONS", "false")
print("ENV VAL:", val)
print("COMPARED:", val.lower() == "true")

from api.constants import DISABLE_NEW_REGISTRATIONS
print("FROM CONSTANTS:", DISABLE_NEW_REGISTRATIONS)
