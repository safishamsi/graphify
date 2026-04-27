---
description: Build or query a graphify knowledge graph
---

Invoke the `graphify` skill immediately.

Pass the full `/graphify` argument string through unchanged.
If no arguments were supplied, treat the target path as `.`.

Examples:
- `/graphify`
- `/graphify src --update`
- `/graphify query "what connects auth to billing?"`

Do not answer from raw files before handing off to the `graphify` skill.
