# Authentication

Users MUST authenticate via SSO.

## Passwords

NEVER store passwords in plain text.

Example (not production):

```python
password = "example"
```

The system SHALL reject weak tokens.
