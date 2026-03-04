import inspect
import uuid
from typing import Any, Callable
from agent_framework import FunctionTool
from auth0_ai.interrupts.token_vault_interrupt import TokenVaultInterrupt

# Framework-injected runtime kwargs forwarded by the agent to tool functions.
# These must be stripped before invoking the original user-defined function.
# Reference: https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_tools.py#L514-L529
_FRAMEWORK_KWARGS = frozenset({
    "chat_options", "tools", "tool_choice", "options", "response_format", "conversation_id",
})


def _build_function_tool_kwargs(tool: FunctionTool) -> dict[str, Any]:
    """Build constructor kwargs by copying configuration from an existing FunctionTool.

    Introspects FunctionTool.__init__ to forward all named parameters except func,
    name, description, and input_model (handled separately by the caller). None values
    are omitted for optional parameters to avoid overriding framework defaults.

    Args:
        tool: The source FunctionTool to copy configuration from.

    Returns:
        A dict of kwargs suitable for unpacking into the FunctionTool constructor.
    """
    init_signature = inspect.signature(FunctionTool)
    init_kwargs: dict[str, Any] = {}
    for param_name, param in init_signature.parameters.items():
        if param_name in {"self", "func", "name", "description", "input_model"}:
            continue
        if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
            continue
        if hasattr(tool, param_name):
            value = getattr(tool, param_name)
            if value is not None or param.default is inspect.Parameter.empty:
                init_kwargs[param_name] = value
    return init_kwargs


def tool_wrapper(tool: FunctionTool, protect_fn: Callable) -> FunctionTool:
    """Wrap an MS Agent FunctionTool with an Auth0 authorization protect function.

    The returned FunctionTool preserves the original tool's name, description, input
    schema, and all framework configuration (approval_mode, max_invocations, etc.).
    At runtime the wrapped function:
    - Extracts and validates the session injected by the agent framework
    - Strips framework-injected kwargs before forwarding to the original function
    - Builds the authorization context (thread_id, tool_call_id, tool_name)
    - Delegates to protect_fn for credential acquisition and validation
    - Stores any TokenVaultInterrupt in session.state["pending_interrupt"] before re-raising

    Args:
        tool: The FunctionTool to wrap.
        protect_fn: The bound protect method from a TokenVaultAuthorizerBase instance.

    Returns:
        A new FunctionTool with authorization applied, preserving all original configuration.
    """
    original_func = tool.func
    tool_name = tool.name
    tool_description = tool.description
    input_model = tool.input_model

    async def wrapped_func(**kwargs: Any):
        # The agent framework injects `session` (AgentSession) into runtime kwargs
        # for tools that accept **kwargs. session.session_id is used as thread_id
        # for credential namespace resolution in the token vault authorizer.
        session = kwargs.pop("session", None)
        for key in _FRAMEWORK_KWARGS:
            kwargs.pop(key, None)

        if session is None:
            raise RuntimeError(
                f"[{tool_name}] A session is required to record tool state. "
                "Pass session via options={'additional_function_arguments': {'session': session}}."
            )

        thread_id = session.session_id

        # tool_call_id is consumed by FunctionTool.invoke() before reaching this
        # function, so a unique ID is generated per invocation instead.
        # Reference: https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_tools.py#L466-L470
        tool_call_id = str(uuid.uuid4())

        def get_context(*_, **__):
            return {
                "thread_id": thread_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
            }

        async def execute_fn(*_, **__):
            # original_func is called directly rather than through FunctionTool.__call__
            # to avoid double-counting framework metrics (invocation_count,
            # invocation_exception_count) already tracked at the wrapped tool boundary.
            if inspect.iscoroutinefunction(original_func):
                return await original_func(**kwargs)
            else:
                return original_func(**kwargs)

        try:
            result = await protect_fn(get_context, execute_fn)(**kwargs)
            session.state.pop("pending_interrupt", None)
            return result
        except TokenVaultInterrupt as e:
            session.state["pending_interrupt"] = e
            raise

    schema_or_model = tool.parameters() if getattr(tool, "_schema_supplied", False) else input_model

    init_kwargs = _build_function_tool_kwargs(tool)

    return FunctionTool(
        func=wrapped_func,
        name=tool_name,
        description=tool_description,
        input_model=schema_or_model,
        **init_kwargs,
    )
