## For /graphify query

```powershell
aag query "QUESTION"
```

## For /graphify path

```powershell
aag path "NODE_A" "NODE_B"
```

## For --update (incremental)

```powershell
@'
import sys, json
from graphify.detect import detect_incremental
from pathlib import Path
result = detect_incremental(Path('INPUT_PATH'))
print(json.dumps(result))
'@ | Out-File -FilePath .graphify_update.py -Encoding utf8
python .graphify_update.py
Remove-Item -ErrorAction SilentlyContinue .graphify_update.py
```
