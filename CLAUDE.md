# AI Coding Instructions

## Code Style
- Do NOT write docstrings or comments unless explicitly requested
- Organize and refactor code for clarity when possible
- Keep code concise and readable
- DRY principle: Avoid code duplication, extract reusable functions
- Single responsibility: Keep functions focused on one task
- Consistent naming: Follow existing naming conventions in the codebase

## Error Handling
- Always add proper error handling and edge cases
- Handle exceptions gracefully

## Debugging/Logging
- Add meaningful log messages for debugging
- Use appropriate log levels (debug, info, warning, error)
- Log network call requests and responses (skip if payload is large)

## Testing
- Write test cases for important/critical functions
- Add tests when implementing new features
- Be mindful of API costs (OpenAI, etc.) - use minimal test runs for paid APIs
- Prefer mocking external paid APIs in unit tests

## Security
- Never hardcode secrets, API keys, or credentials
- Sanitize user inputs
- Use environment variables for sensitive config

## Performance
- Avoid unnecessary loops or redundant operations
- Use async/await properly for I/O operations
- Consider memory usage for large data processing

## Project-Specific
- Prefer existing utility functions over writing new ones
- Match the logging style already in use (structlog)
- Use Pydantic models for data validation
- Use dataclasses or Pydantic for data structures
- Follow existing import ordering

## Git/Workflow
- Don't commit or push without explicit permission
- Don't modify unrelated files

## Frontend
- Keep JavaScript/CSS organized and modular
- Use meaningful class names and IDs
- Minimize DOM manipulations, batch when possible
- Use event delegation where appropriate
- Ensure responsive design works across screen sizes
- Keep bundle size small, avoid unnecessary dependencies
- Handle loading and error states in UI
- Sanitize any user-generated content before rendering
- Use async/await for API calls with proper error handling
- Follow existing styling patterns in the project
- Match existing design (colors, spacing, fonts, UI components) - maintain visual consistency

## General
- Follow existing patterns in the codebase
- Prefer small, focused functions

## Slack Bot Responses
When responding to messages from the Slack bot (identified by short, direct questions typically without code context):
- At the END of your response, always include a summary section
- Use this exact format:
```
---SUMMARY---
Your casual, human-friendly summary here (1-3 short points max)
---END_SUMMARY---
```
- Keep the summary conversational, like talking to a coworker
- For simple actions (commits, file changes): "Done! Committed with message 'xyz'"
- For multiple items: use bullet points (max 3)
- No formal language - be direct and friendly
