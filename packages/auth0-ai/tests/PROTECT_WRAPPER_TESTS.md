# TokenVaultAuthorizer.protect() Test Suite

This document explains the comprehensive test suite for the `protect()` wrapper method in `token_vault_authorizer.py:276-321`.

## Critical Bug Fix Coverage

### The Bug
There was a bug where credential deletion wasn't being **awaited** when errors occurred. This meant that failed credentials could remain in the store, causing subsequent requests to use invalid tokens.

### Tests Verifying the Fix

#### 1. `test_protect_deletes_credentials_on_token_vault_error` (Lines 151-184)
**MOST CRITICAL TEST** - Verifies that credentials are properly deleted when a `TokenVaultError` occurs.

```python
# Key Assertions:
authorizer.credentials_store.delete.assert_called_once()
assert authorizer.credentials_store.delete.await_count == 1  # ✅ Verifies await was called
```

This test specifically checks that:
- `delete()` was called
- `delete()` was **awaited** (the bug was not awaiting it)
- The correct namespace was used for deletion

#### 2. `test_protect_deletes_credentials_on_auth0_interrupt` (Lines 186-225)
Similar to above, but tests deletion when `Auth0Interrupt` is raised instead of `TokenVaultError`.

#### 3. `test_protect_credential_deletion_with_correct_namespace` (Lines 398-441)
Verifies that credentials are deleted from the **correct namespace**, which is critical for multi-tenant scenarios.

```python
# Verifies the namespace used for deletion matches what was used for get
get_namespace = authorizer.credentials_store.get.call_args[0][0]
delete_namespace = authorizer.credentials_store.delete.call_args[0][0]
assert get_namespace == delete_namespace
```

## Complete Test Coverage

### 1. Success Path Tests

#### `test_protect_executes_function_successfully`
- Tests normal execution with existing credentials
- Verifies credentials are retrieved from store
- Confirms wrapped function executes

#### `test_protect_fetches_and_stores_new_credentials`
- Tests fetching new credentials when none exist
- Verifies `get_access_token_impl` is called
- Confirms credentials are validated and stored

### 2. Error Handling Tests

#### `test_protect_deletes_credentials_on_token_vault_error` ⭐
- **Critical**: Verifies async deletion is awaited
- Tests cleanup on TokenVaultError

#### `test_protect_deletes_credentials_on_auth0_interrupt` ⭐
- Verifies deletion on Auth0Interrupt
- Confirms interrupt handler is called

### 3. Namespace & Context Tests

#### `test_protect_uses_correct_namespace_for_credentials`
- Verifies namespace is correctly derived from context
- Ensures get/put use same namespace

#### `test_protect_credential_deletion_with_correct_namespace` ⭐
- Critical for multi-tenant scenarios
- Ensures deletion uses correct namespace

#### `test_protect_with_different_contexts[thread|agent|tool|tool-call]`
- Parametrized test for all credential_context types
- Verifies each context mode works correctly

### 4. Functionality Tests

#### `test_protect_wraps_sync_functions`
- Tests wrapping synchronous functions
- Verifies wrapper handles both sync and async functions

#### `test_protect_passes_args_and_kwargs_to_wrapped_function`
- Ensures arguments are passed through correctly
- Tests both positional and keyword arguments

#### `test_protect_local_storage_cleanup_after_execution`
- Verifies local storage is cleaned up
- Tests context manager properly resets state

#### `test_protect_prevents_nested_tool_calls`
- Ensures nested protect calls are blocked
- Prevents corruption of local storage

## Mocking Strategy

All tests use comprehensive mocking to isolate the `protect()` wrapper:

```python
# Mock the credential store
authorizer.credentials_store.get = AsyncMock(return_value=mock_credentials)
authorizer.credentials_store.put = AsyncMock()
authorizer.credentials_store.delete = AsyncMock()  # AsyncMock tracks await calls!

# Mock Auth0 token fetching
authorizer.get_access_token_impl = AsyncMock(return_value=mock_credentials)

# Mock validation
authorizer.validate_token = MagicMock()

# Mock the interrupt handler
authorizer._handle_authorization_interrupts = MagicMock()
```

### Why AsyncMock for Store Methods?
`AsyncMock` is crucial because it tracks:
- Whether the async function was called
- Whether it was **awaited** (via `.await_count`)
- Call arguments

This is how we catch the bug where `delete()` wasn't being awaited!

## Key Testing Patterns

### 1. Testing Async Functions
```python
@pytest.mark.asyncio
async def test_something():
    result = await async_function()
    assert result == expected
```

### 2. Verifying Async Calls Were Awaited
```python
mock_async_fn = AsyncMock()
await code_under_test()
assert mock_async_fn.await_count == 1  # ✅ Verifies await
```

### 3. Testing Exception Handling
```python
mock_execute = AsyncMock(side_effect=TokenVaultError("error"))
await wrapped()  # Should handle error gracefully
authorizer.credentials_store.delete.assert_called_once()
```

### 4. Context Requirements
All context getters must provide:
```python
def get_context():
    return {
        "thread_id": "...",      # Required
        "tool_call_id": "...",   # Required
        "tool_name": "...",      # Required
    }
```

## Running the Tests

```bash
# Run all protect wrapper tests
poetry run pytest tests/test_token_vault_authorizer_protect.py -v

# Run just the critical deletion tests
poetry run pytest tests/test_token_vault_authorizer_protect.py -k "delete" -v

# Run with coverage
poetry run pytest tests/test_token_vault_authorizer_protect.py --cov=auth0_ai.authorizers.token_vault_authorizer
```

## Test Results

```
14 tests in test_token_vault_authorizer_protect.py - ALL PASSING ✅
- 10 comprehensive wrapper behavior tests
- 4 parametrized tests for different credential contexts
```

## Files

- `tests/test_token_vault_authorizer_protect.py` - All protect wrapper tests
- `tests/test_token_vault_authorizer.py` - Basic authorizer initialization tests
- `auth0_ai/authorizers/token_vault_authorizer.py:276-321` - Code under test

## What Makes These Tests Effective

1. **Complete mocking** - No external dependencies
2. **AsyncMock usage** - Catches await bugs
3. **Namespace verification** - Ensures multi-tenant safety
4. **Error path coverage** - Tests both success and failure
5. **Context flexibility** - Tests all credential_context modes
6. **Clear documentation** - Each test explains what it verifies

## Future Test Additions

Consider adding tests for:
- Race conditions in concurrent tool calls
- Store failures (network errors, etc.)
- Token expiration scenarios
- Malformed credentials
- Very long-running wrapped functions
