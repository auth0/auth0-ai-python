from datetime import datetime, timedelta

import requests
from auth0_ai_langchain.token_vault import (
    TokenVaultError,
    get_credentials_from_token_vault,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from src.auth0.auth0_ai import with_calendar_free_busy_access


class CheckUserCalendarSchema(BaseModel):
    date: datetime


def add_hours(dt: datetime, hours: int) -> str:
    return (dt + timedelta(hours=hours)).isoformat()


def check_user_calendar_tool_function(date: datetime):
    credentials = get_credentials_from_token_vault()
    if not credentials:
        raise ValueError(
            "Authorization required to access the Token Vault connection")

    url = "https://www.googleapis.com/calendar/v3/freeBusy"
    body = {
        "timeMin": date.isoformat() + "Z",
        "timeMax": add_hours(date, 1) + "Z",
        "timeZone": "UTC",
        "items": [{"id": "primary"}]
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"{credentials['token_type']} {credentials['access_token']}"},
        json=body
    )

    if response.status_code != 200:
        if response.status_code == 401:
            raise TokenVaultError(
                "Authorization required to access the Token Vault connection")
        raise ValueError(
            f"Invalid response from Google Calendar API: {response.status_code} - {response.text}")

    busy_resp = response.json()
    return {"available": len(busy_resp["calendars"]["primary"]["busy"]) == 0}


check_user_calendar_tool = with_calendar_free_busy_access(StructuredTool(
    name="check_user_calendar",
    description="Use this function to check if the user is available on a certain date and time",
    args_schema=CheckUserCalendarSchema,
    func=check_user_calendar_tool_function,
))
