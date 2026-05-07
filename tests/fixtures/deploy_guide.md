# Deploy Guide

How to deploy the QuranicWords backend.

## Prerequisites

- Docker installed
- SSH access to VPS

## Full Deploy

Run this one-liner on your VPS:

```bash
cd /opt/QuranicWords && git pull origin main && docker compose build --no-cache api
```

### Database Migration

If you changed the Prisma schema:

```sql
ALTER TABLE users ADD COLUMN points INT DEFAULT 0;
```

## Rollback

Use `git revert` to undo bad deploys.

```python
def rollback(version):
    subprocess.run(["git", "checkout", version])
```
