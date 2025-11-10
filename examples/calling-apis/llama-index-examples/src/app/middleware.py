import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class HostRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware to redirect requests to the correct host.
    This prevents issues when accessing via 0.0.0.0 or 127.0.0.1 when Auth0 is configured for localhost.
    """

    async def dispatch(self, request: Request, call_next):
        app_base_url = os.getenv("APP_BASE_URL", "http://localhost:3000")
        expected_host = urlparse(app_base_url).netloc
        request_host = request.headers.get("host", "")

        # If the request host doesn't match the expected host, redirect
        if request_host and request_host != expected_host:
            # Build the correct URL with the expected host
            correct_url = f"{urlparse(app_base_url).scheme}://{expected_host}{request.url.path}"
            if request.url.query:
                correct_url += f"?{request.url.query}"
            return RedirectResponse(url=correct_url, status_code=307)

        return await call_next(request)
