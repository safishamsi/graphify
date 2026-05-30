### Step 1 - Ensure graphify is installed

```powershell
# Detect Python and install graphify if needed
@'
import graphify
'@ | Out-File -FilePath .graphify_step_1_ensure_graphify_is_installed_1.py -Encoding utf8
python .graphify_step_1_ensure_graphify_is_installed_1.py 2>$null
Remove-Item -ErrorAction SilentlyContinue .graphify_step_1_ensure_graphify_is_installed_1.py
if ($LASTEXITCODE -ne 0) { pip install graphifyy -q 2>&1 | Select-Object -Last 3 }
# Write interpreter path for all subsequent steps
@'
import sys; open('.graphify_python', 'w').write(sys.executable)
'@ | Out-File -FilePath .graphify_step_1_ensure_graphify_is_installed_2.py -Encoding utf8
python .graphify_step_1_ensure_graphify_is_installed_2.py
Remove-Item -ErrorAction SilentlyContinue .graphify_step_1_ensure_graphify_is_installed_2.py
```

### Step 2 - Detect files

```powershell
@'
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
print(json.dumps(result))
'@ | Out-File -FilePath .graphify_step_2_detect_files_3.py -Encoding utf8
python .graphify_step_2_detect_files_3.py > .graphify_detect.json
Remove-Item -ErrorAction SilentlyContinue .graphify_step_2_detect_files_3.py
```

### Step 3 - Extract entities and relationships

#### Part A - Structural extraction for code files

```powershell
@'
import json
from graphify.extract import collect_files, extract
from pathlib import Path

def main():
    code_files = []
    detect = json.loads(Path('.graphify_detect.json').read_text())
    for f in detect.get('files', {}).get('code', []):
        code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

    if code_files:
        result = extract(code_files)
        Path('.graphify_ast.json').write_text(json.dumps(result, indent=2))
    else:
        Path('.graphify_ast.json').write_text(json.dumps({'nodes':[],'edges':[]}))

if __name__ == "__main__":
    main()
'@ | Out-File -FilePath .graphify_step_3_ast.py -Encoding utf8
python .graphify_step_3_ast.py
Remove-Item -ErrorAction SilentlyContinue .graphify_step_3_ast.py
```

### Step 4 - Build graph, cluster, analyze

```powershell
@'
import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections
from graphify.report import generate
from graphify.store import save
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)
# ... (rest of Step 4 logic)
save('.', G, communities)
'@ | Out-File -FilePath .graphify_step_4.py -Encoding utf8
python .graphify_step_4.py
Remove-Item -ErrorAction SilentlyContinue .graphify_step_4.py
```
