# Unified Session Management Implementation Plan

## Overview

Unify session management between Auggie and Codex providers so both use the common `TerminalSession` infrastructure from `backend/services/terminal_agent/`, differing only in provider-specific parameters (patterns, markers, commands).

### Goals
- Make Codex use interactive session mode (like Auggie) instead of one-shot exec mode
- Have both providers use `TerminalAgentStreamGenerator` in `chat.py`
- Remove special-case handling for Auggie in routes
- (Optional) Deprecate legacy `backend/session.py` in favor of common session infrastructure

### Success Criteria
- Codex maintains session state across messages (conversation context preserved)
- Both Auggie and Codex use `TerminalAgentStreamGenerator`
- Reduced code duplication in `chat.py`
- No regression in Auggie functionality

### Scope Boundaries
- **Included**: Codex session mode migration, route unification, deprecation of Auggie-specific code path
- **Excluded**: OpenAI provider (already different architecture), new features

---

## Prerequisites

1. Verify Codex CLI supports interactive mode (not just `codex exec`)
2. Identify Codex interactive mode prompt patterns and response markers
3. Test Codex interactive CLI manually to understand behavior

---

## Implementation Steps

### Step 1: Update CodexProvider to Support Interactive Mode

**File**: `backend/services/codex/provider.py`

**Changes**:
1. Change `is_exec_mode` property to return `False`
2. Update `get_command()` signature to match base class: `get_command(workspace, model)` - remove `message` param
3. Change command from `codex exec` to interactive `codex` command
4. Review/update prompt patterns and end patterns for interactive mode

**Key Implementation Details**:
```python
# Before:
def get_command(self, workspace: str, model: Optional[str] = None, message: str = None) -> List[str]:
    cmd = [codex_cmd, 'exec']
    if message:
        cmd.append(message)
    return cmd

@property
def is_exec_mode(self) -> bool:
    return True

# After:
def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
    cmd = [codex_cmd]  # Interactive mode, no 'exec'
    if model:
        cmd.extend(['--model', model])
    return cmd

@property
def is_exec_mode(self) -> bool:
    return False  # Use session mode
```

**Testing**: Manually test Codex interactive CLI to verify prompt patterns

---

### Step 2: Update Routes to Use Unified Handler for Auggie

**File**: `backend/routes/chat.py`

**Changes**:
1. Remove the special `provider != 'auggie'` check on line 1341
2. Route Auggie through `TerminalAgentStreamGenerator` (same as Codex)
3. Remove the fallback `StreamGenerator` class usage for Auggie
4. Keep `StreamGenerator` class temporarily for potential rollback

**Before** (line 1341):
```python
if provider in TERMINAL_AGENT_PROVIDERS and provider != 'auggie':
    # Use TerminalAgentStreamGenerator
    ...

# Fallback uses StreamGenerator (Auggie-specific)
generator = StreamGenerator(message, ...)
```

**After**:
```python
if provider in TERMINAL_AGENT_PROVIDERS:
    # Use TerminalAgentStreamGenerator for ALL terminal agents (including auggie)
    ...
```

**Testing**: Verify Auggie still works correctly through new code path

---

### Step 3: Remove Exec Mode Code Path

**File**: `backend/routes/chat.py`

**Changes**:
1. Remove `_generate_exec_mode()` method from `TerminalAgentStreamGenerator` (lines 1165-1280)
2. Remove `_extract_exec_response()` method (lines 1259-1280)
3. Remove the exec mode branch in `generate()` (lines 961-963)

**Before**:
```python
def generate(self):
    ...
    if self.provider.is_exec_mode:
        yield from self._generate_exec_mode()
        return
```

**After**:
```python
def generate(self):
    # All providers use session mode - no exec mode branch
    ...
```

---

### Step 4: Update Session Management in chat.py

**File**: `backend/routes/chat.py`

**Changes**:
1. Update imports to use only `terminal_agent` SessionManager
2. Update `/api/chat/reset` endpoint to use unified session manager
3. Remove legacy `SessionManager` import from `backend.session`

**Current imports**:
```python
from backend.session import SessionManager  # Legacy Auggie-specific
```

**New imports**:
```python
from backend.services.terminal_agent.executor import SessionManager as TerminalSessionManager
```

---

### Step 5: Deprecate Legacy Session Module (Optional)

**File**: `backend/session.py`

**Options**:
1. **Full removal**: Delete file, ensure no imports remain
2. **Soft deprecation**: Add deprecation warnings, keep for backward compatibility

**Recommended**: Start with soft deprecation, add `# DEPRECATED` comments and logging warnings

**Dependencies to check**:
- `backend/routes/chat.py` - Update to use new SessionManager
- Any other files importing from `backend.session`

---


## File Changes Summary

### Files to Modify

| File | Changes |
|------|---------|
| `backend/services/codex/provider.py` | Remove `is_exec_mode=True`, update `get_command()` signature, change to interactive mode |
| `backend/routes/chat.py` | Remove `provider != 'auggie'` check, remove exec mode methods, update SessionManager import |
| `backend/routes/settings.py` | Update SessionManager import to use terminal_agent version |
| `backend/services/terminal_agent/executor.py` | Add `reset()` method to SessionManager for reset endpoint |

### Files to Deprecate (Phase 2)

| File | Status |
|------|--------|
| `backend/session.py` | Mark as deprecated, keep for rollback |
| `backend/services/auggie/executor.py` | Mark as deprecated (uses legacy SessionManager) |

### Test Files to Update

| File | Changes |
|------|---------|
| `tests/test_session_in_use.py` | Update imports to use new SessionManager or mark for migration |
| `tests/test_auggie_streaming.py` | Update imports to use new SessionManager or mark for migration |

---

## Detailed File Change Analysis

### `backend/routes/chat.py` Changes

**Lines to modify:**
- Line 15: Change `from backend.session import SessionManager` to `from backend.services.terminal_agent.executor import SessionManager as TerminalSessionManager`
- Line 1341: Change `if provider in TERMINAL_AGENT_PROVIDERS and provider != 'auggie':` to `if provider in TERMINAL_AGENT_PROVIDERS:`
- Lines 961-963: Remove exec mode branch
- Lines 1165-1280: Remove `_generate_exec_mode()` and `_extract_exec_response()` methods
- Lines 1369-1399: Remove fallback `StreamGenerator` usage (now handled by TerminalAgentStreamGenerator)
- Line 1418: Update to use new SessionManager reset

**Code changes for reset endpoint (line 1418):**
```python
# Before:
reset_success = SessionManager.reset(workspace)

# After - need to reset all terminal agent sessions for the workspace:
reset_success = TerminalSessionManager.reset(workspace)  # Need to add reset() method
```

### `backend/services/terminal_agent/executor.py` Changes

**Add `reset()` and `cleanup_old()` methods to SessionManager:**
```python
@classmethod
def reset(cls, workspace: str) -> bool:
    """Reset all sessions for a workspace."""
    keys_to_remove = [k for k in cls._sessions if workspace in k]
    for key in keys_to_remove:
        session = cls._sessions.get(key)
        if session:
            if session.in_use:
                return False
            session.cleanup()
            del cls._sessions[key]
    return True

@classmethod
def cleanup_old(cls, max_age_seconds: float = 600) -> None:
    """Clean up sessions older than max_age_seconds."""
    import time
    now = time.time()
    keys_to_remove = []
    for key, session in cls._sessions.items():
        if not session.in_use and (now - session._created_at) > max_age_seconds:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        cls._sessions[key].cleanup()
        del cls._sessions[key]
```

---

## Testing Strategy

### Unit Tests

1. **Test Codex interactive session**
   - Verify session starts correctly
   - Verify message sending works
   - Verify response extraction works
   - Verify session reuse across messages

2. **Test Auggie through new path**
   - Verify no regression in Auggie functionality
   - Verify session management works correctly
   - Verify streaming works correctly

3. **Test session reset**
   - Verify reset works for both providers
   - Verify in-use protection works

### Integration Tests

1. **Multi-message conversation test**
   - Send multiple messages to same session
   - Verify context is maintained

2. **Provider switching test**
   - Switch between Auggie and Codex
   - Verify each maintains separate sessions

### Manual Testing Steps

1. Start app, send message to Codex
2. Verify response received
3. Send follow-up message
4. Verify context maintained (Codex remembers previous message)
5. Reset session
6. Verify new session starts fresh
7. Repeat for Auggie to ensure no regression

---

## Rollback Plan

### Immediate Rollback (Code Level)

1. Revert changes to `backend/services/codex/provider.py`:
   - Restore `is_exec_mode = True`
   - Restore `get_command()` with message parameter

2. Revert changes to `backend/routes/chat.py`:
   - Restore `provider != 'auggie'` check
   - Restore exec mode methods

### Data/Session Rollback

- No persistent data changes - sessions are ephemeral
- Kill any running Codex/Auggie processes if needed

### Feature Flag Option (Alternative)

Add configuration flag to enable/disable unified session mode:
```python
# backend/config.py
UNIFIED_SESSION_MODE = os.environ.get('UNIFIED_SESSION_MODE', 'true').lower() == 'true'
```

---

## Estimated Effort

| Task | Estimated Time | Complexity |
|------|---------------|------------|
| Step 1: Update CodexProvider | 30 min | Low |
| Step 2: Update routes (remove auggie check) | 15 min | Low |
| Step 3: Remove exec mode code | 30 min | Medium |
| Step 4: Update SessionManager imports | 30 min | Medium |
| Step 5: Add reset/cleanup methods | 30 min | Low |
| Testing & debugging | 2-3 hours | Medium |
| **Total** | **4-5 hours** | **Medium** |

---

## Implementation Order

1. **Phase 1: Codex Migration** (can be done independently)
   - Update CodexProvider to interactive mode
   - Test Codex thoroughly

2. **Phase 2: Auggie Migration** (depends on Phase 1 success)
   - Route Auggie through TerminalAgentStreamGenerator
   - Test Auggie thoroughly

3. **Phase 3: Cleanup** (after both phases validated)
   - Remove exec mode code
   - Update imports
   - Deprecate legacy session.py

---

## Open Questions

1. **Codex interactive mode support**: Does Codex CLI support interactive mode similar to Auggie? Need to verify before implementation.

2. **Prompt patterns**: What are the correct prompt/end patterns for Codex interactive mode? May need adjustment.

3. **Session key strategy**: Current key is `{provider}:{workspace}:{model}`. Should model changes create new sessions or reuse existing?

4. **Cleanup thread**: Legacy `session.py` has cleanup thread for stale processes. Should this be added to terminal_agent SessionManager?
