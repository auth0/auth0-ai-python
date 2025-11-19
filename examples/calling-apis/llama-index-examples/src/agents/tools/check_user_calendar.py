from datetime import datetime, timedelta
from typing import Annotated

import requests
from auth0_ai_llamaindex.token_vault import (TokenVaultError,
                                             get_credentials_from_token_vault)
from llama_index.core.tools import FunctionTool

from ...auth0.auth0_ai import with_calendar_free_busy_access


def format_date(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "") + "Z"


def check_user_calendar_tool_function(
    date: Annotated[str, "Date and time in ISO 8601 format."]
):
    credentials = get_credentials_from_token_vault()
    if not credentials:
        raise ValueError(
            "Authorization required to access the Token Vault connection")

    parsed_date = datetime.fromisoformat(date)
    url = "https://www.googleapis.com/calendar/v3/freeBusy"
    body = {
        "timeMin": format_date(parsed_date),
        "timeMax": format_date(parsed_date + timedelta(hours=1)),
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


check_user_calendar_tool = with_calendar_free_busy_access(FunctionTool.from_defaults(
    name="check_user_calendar",
    description="Use this function to check if the user is available on a certain date and time",
    fn=check_user_calendar_tool_function,
))
