# Calling APIs On User's Behalf with LangChain

## Getting Started

### Prerequisites

- An OpenAI account and API key. You can create one [here](https://platform.openai.com).
  - [Use this page for instructions on how to find your OpenAI API key](https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key)
- [LangGraph CLI](https://langchain-ai.github.io/langgraph/cloud/reference/cli/)
- An **[Auth0](https://auth0.com)** account and the following settings and resources configured:
  - An application to initiate the authorization flow:
    - **Application Type**: `Regular Web Application`
    - **Allowed Callback URLs**: `http://localhost:3000/auth/callback`
    - **Allowed Logout URLs**: `http://localhost:3000`
    - **Advanced Settings -> Grant Types**: `Refresh Token` and `Token Vault` (or `urn:auth0:params:oauth:grant-type:token-exchange:federated-connection-access-token`)
    - **Allow Refresh Token Rotation**: currently you should disable this setting if you are using Token Vault for token exchanges with a refresh token.
  - Either **Google**, **Slack** or **Github** social connections enabled for the application:
    - **Google connection** set up instructions:
      - Create a [Google OAuth 2.0 Client](https://console.cloud.google.com/apis/credentials) configured with access to the `https://www.googleapis.com/auth/calendar.freebusy` scope (Google Calendar API).
      - On Auth0 Dashboard, set up the client ID and secret from the previously created Google client.
      - Enable following settings:
        - **Use for Connected Accounts with Token Vault** enabled.
        - **Offline access** enabled.
        - **https://www.googleapis.com/auth/calendar.freebusy** scope granted.
    - **Slack connection** set up instructions:
      - Create a [Slack App](https://api.slack.com/apps) and follow the [Auth0's Signin with Slack](https://marketplace.auth0.com/integrations/sign-in-with-slack) `installation` instructions to set up the connection.
      - Enable following settings:
        - **Use for Connected Accounts with Token Vault** enabled.
        - On Slack's OAuth & Permission settings, make sure to add the `channels:read` scope to the User Token scopes.
    - **Github connection** set up instructions:
      - Register a new app in [GitHub Developer Settings: OAuth Apps](https://github.com/settings/developers#oauth-apps) and follow the [Auth0's Github social connection](https://marketplace.auth0.com/integrations/github-social-connection) `installation` instructions to set up the connection.
      - On Auth0 Dashboard, set up the client ID and secret from the previously created Github App.
      - Enable following settings:
        - **Use for Connected Accounts with Token Vault** enabled.

### Setup

Copy the file `.env.example` to `.env` and fill in the required values:

```sh
# Auth0
AUTH0_DOMAIN="<auth0-domain>"
AUTH0_CLIENT_ID="<auth0-client-id>"
AUTH0_CLIENT_SECRET="<auth0-client-secret>"

# OpenAI
OPENAI_API_KEY="<openai-api-key>"
```

### How to run it

1.  **Install Dependencies**

    Use [Poetry](https://python-poetry.org/) to install the required dependencies:

    ```sh
    poetry install
    ```

2.  **Run LangGraph (dev mode)**

    ```sh
    poetry run langgraph_up
    ```

3.  **Run chat client**

    ```sh
    poetry run start
    ```

    > And navigate to `http://localhost:3000/`

4.  **Login with your Google account and ask the assistant about your availability**

    ```sh
    Am I available on September 25th at 9:15 AM?
    ```

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png"   width="150">
    <source media="(prefers-color-scheme: dark)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_dark_mode.png" width="150">
    <img alt="Auth0 Logo" src="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png" width="150">
  </picture>
</p>
<p align="center">Auth0 is an easy to implement, adaptable authentication and authorization platform. To learn more checkout <a href="https://auth0.com/why-auth0">Why Auth0?</a></p>
<p align="center">
This project is licensed under the Apache 2.0 license. See the <a href="/LICENSE"> LICENSE</a> file for more info.</p>
