# Auth0 AI for Python

> ⚠️ **WARNING**: Auth0 AI for Python is currently **under heavy development**. We strictly follow [Semantic Versioning (SemVer)](https://semver.org/), meaning all **breaking changes will only occur in major versions**. However, please note that during this early phase, **major versions may be released frequently** as the API evolves. We recommend locking versions when using this in production.

[Auth0 AI](https://www.auth0.ai/) helps you build secure AI-powered applications.

Developers are using LLMs to build generative AI applications that deliver powerful new experiences for customers and employees. Maintaining security and privacy while allowing AI agents to assist people in their work and lives is a critical need. Auth0 AI helps you meet these requirements, ensuring that agents are properly authorized when taking actions or accessing resources on behalf of a person or organization. Common use cases include:

- **Authenticate users**: Easily implement login experiences tailored for AI agents and assistants.
- **Call APIs on users' behalf**: Use secure standards to call APIs from tools, integrating your app with other products.
- **Authorization for RAG**: Generate more relevant responses while ensuring that the agent incorporates only information the user has access to.
- **Async Authorization**: Enable agents to operate autonomously in the background while requiring human approval when necessary.

## Packages

- [`auth0-ai-llamaindex`](./packages/auth0-ai-llamaindex/) -
  Integration with [LlamaIndex](https://docs.llamaindex.ai/en/stable/) framework.

- [`auth0-ai-langchain`](./packages/auth0-ai-langchain/) -
  Integration with [LangChain](https://python.langchain.com/docs/tutorials/) framework.

## Examples

- [Authorization for RAG](/examples/authorization-for-rag/README.md): Examples of implementing secure document retrieval with strict access control using Okta FGA.
- [Authorization for Tools](/examples/authorization-for-tools/README.md): Examples of implementing secure tool calling with strict access control using Okta FGA.
- [Calling APIs](/examples/calling-apis/README.md): Examples of using secure standards to call third-party APIs from tools with Auth0.
- [Async Authorization](/examples/async-authorization/README.md): Examples of handling asynchronous user confirmation workflows.

## Recommendations for VSCode Users

To streamline development with Poetry and virtual environments in VSCode, follow these steps:

1. Configure Poetry to Use In-Project Virtual Environments  
   Run the following command to ensure the virtual environment is created within your project directory (e.g., `.venv`):

   ```bash
   poetry config virtualenvs.in-project true
   ```

2. Select the Correct Interpreter in VSCode

   - Open the Command Palette (Ctrl+Shift+P or Cmd+Shift+P).
   - Search for and select Python: Select Interpreter.
   - Choose the interpreter located in the .venv folder (e.g., .venv/bin/python).

## Feedback

### Contributing

We appreciate feedback and contribution to this repo! Before you get started, please see the following:

- [Auth0's general contribution guidelines](https://github.com/auth0/open-source-template/blob/master/GENERAL-CONTRIBUTING.md)
- [Auth0's code of conduct guidelines](https://github.com/auth0/open-source-template/blob/master/CODE-OF-CONDUCT.md)

### Raise an issue

To provide feedback or report a bug, please [raise an issue on our issue tracker](https://github.com/auth0/auth0-ai-python/issues).

### Vulnerability Reporting

Please do not report security vulnerabilities on the public GitHub issue tracker. The [Responsible Disclosure Program](https://auth0.com/responsible-disclosure-policy) details the procedure for disclosing security issues.

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
