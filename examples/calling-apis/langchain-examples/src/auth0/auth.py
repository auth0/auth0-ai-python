import os

from auth0_fastapi.auth import AuthClient
from auth0_fastapi.config import Auth0Config
from dotenv import load_dotenv

load_dotenv()

config = Auth0Config(
    domain=os.getenv("AUTH0_DOMAIN"),
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    authorization_params={"scope": "openid profile email offline_access"},
    app_base_url=os.getenv("APP_BASE_URL", "http://localhost:3000"),
    secret=os.getenv("APP_SECRET_KEY", "SOME_RANDOM_SECRET_KEY"),
    mount_connected_account_routes=True
)

# Instantiate the AuthClient
auth_client = AuthClient(config)
