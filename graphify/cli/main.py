"""graphify CLI - `graphify install` sets up the Claude Code skill."""
from __future__ import annotations
import json
import os
import platform
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"

# Output directory — override with GRAPHIFY_OUT env var for worktrees or shared-output setups.
# Accepts a relative name ("graphify-out-feature") or an absolute path ("/shared/graphify-out").
_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


from graphify.installers import (
    _PLATFORM_CONFIG,
    install,
    uninstall_all,
    _project_install,
    _project_uninstall,
    _project_uninstall_all,
    _print_install_usage,
    claude_install,
    claude_uninstall,
    gemini_install,
    gemini_uninstall,
    _cursor_install,
    _cursor_uninstall,
    vscode_install,
    vscode_uninstall,
    _kiro_install,
    _kiro_uninstall,
    _uninstall_codex_hook,
    _agents_install,
    _agents_uninstall,
    _antigravity_install,
    _antigravity_uninstall,
    _devin_rules_install,
    _devin_rules_uninstall,
)
from graphify.installers.core import _default_graph_path, _enforce_graph_size_cap_or_exit, _check_skill_version, _remove_skill_file

def _clone_repo(url: str, branch: str | None = None, out_dir: Path | None = None) -> Path:
    """Clone a GitHub repo to a local cache dir and return the path.

    Clones into ~/.graphify/repos/<owner>/<repo> by default so repeated
    runs on the same URL reuse the existing clone (git pull instead of clone).
    """
    import subprocess as _sp
    import re as _re

    # Normalise URL — strip trailing .git if present
    url = url.rstrip("/")
    if not url.endswith(".git"):
        git_url = url + ".git"
    else:
        git_url = url
        url = url[:-4]

    # Extract owner/repo from URL
    m = _re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        print(f"error: not a recognised GitHub URL: {url}", file=sys.stderr)
        sys.exit(1)
    owner, repo = m.group(1), m.group(2)

    if out_dir:
        dest = out_dir
    else:
        dest = Path.home() / ".graphify" / "repos" / owner / repo

    if branch and branch.startswith("-"):
        print(f"error: invalid branch name: {branch!r}", file=sys.stderr)
        sys.exit(1)

    if dest.exists():
        print(f"Repo already cloned at {dest} — pulling latest...", flush=True)
        cmd = ["git", "-C", str(dest), "pull"]
        if branch:
            cmd += ["origin", "--", branch]
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"warning: git pull failed:\n{result.stderr}", file=sys.stderr)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning {url} -> {dest} ...", flush=True)
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += ["--", git_url, str(dest)]
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"error: git clone failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

    print(f"Ready at: {dest}", flush=True)
    return dest


def main() -> None:
    # Check all known skill install locations for a stale version stamp.
    # Skip during install/uninstall (hook writes trigger a fresh check anyway).
    # Skip during hook-check — it runs on every editor tool use and must be silent.
    # Deduplicate paths so platforms sharing the same install dir don't warn twice.
    _silent_cmds = {"install", "uninstall", "hook-check"}
    if not any(arg in _silent_cmds for arg in sys.argv):
        for skill_dst in {Path.home() / cfg["skill_dst"] for cfg in _PLATFORM_CONFIG.values()}:
            _check_skill_version(skill_dst)

    if len(sys.argv) >= 2 and sys.argv[1] in ("-v", "--version", "version"):
        print(f"graphify {__version__}")
        return

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "-?"):
        print("Usage: graphify <command>")
        print()
        print("Commands:")
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codex|opencode|aider|claw|droid|trae|trae-cn|gemini|cursor|antigravity|hermes|kiro|pi|devin)")
        print("  uninstall               remove graphify from all detected platforms in one shot")
        print("    --purge                 also delete graphify-out/ directory")
        print("  path \"A\" \"B\"            shortest path between two nodes in graph.json")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  explain \"X\"             plain-language explanation of a node and its neighbors")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  diagnose multigraph    report same-endpoint edge collapse risk in graph.json")
        print("    --graph <path>          path to graph/extraction JSON")
        print("                            (default graphify-out/graph.json)")
        print("    --json                  emit machine-readable JSON")
        print("    --max-examples N        max same-endpoint examples to print (default 5)")
        print("    --directed              force directed post-build simulation")
        print("    --undirected            force undirected post-build simulation")
        print("                            (default follows JSON directed flag;")
        print("                             raw extraction with no flag defaults directed)")
        print("    --extract-path PATH     extractor source for suppression scan")
        print("  clone <github-url>      clone a GitHub repo locally and print its path for /graphify")
        print("  merge-driver <base> <current> <other>  git merge driver: union-merge two graph.json files (set up via hook install)")
        print("  merge-graphs <g1> <g2>  merge two or more graph.json files into one cross-repo graph")
        print("    --out <path>            output path (default: graphify-out/merged-graph.json)")
        print("    --branch <branch>       checkout a specific branch (default: repo default)")
        print("    --out <dir>             clone to a custom directory (default: ~/.graphify/repos/<owner>/<repo>)")
        print("  add <url>               fetch a URL and save it to ./raw, then update the graph")
        print("    --author \"Name\"         tag the author of the content")
        print("    --contributor \"Name\"    tag who added it to the corpus")
        print("    --dir <path>            target directory (default: ./raw)")
        print("  watch <path>            watch a folder and rebuild the graph on code changes")
        print("  update <path>           re-extract code files and update the graph (no LLM needed)")
        print("    --force                 overwrite graph.json even if the rebuild has fewer nodes")
        print("                            (also: GRAPHIFY_FORCE=1 env var; use after refactors that delete code)")
        print("    --no-cluster            skip clustering, write raw extraction only")
        print("  cluster-only <path>     rerun clustering on an existing graph.json and regenerate report")
        print("    --no-viz                skip graph.html generation (useful for >5000 node graphs / CI)")
        print("    --graph <path>          path to graph.json (default <path>/graphify-out/graph.json)")
        print("  query \"<question>\"       BFS traversal of graph.json for a question")
        print("    --dfs                   use depth-first instead of breadth-first")
        print("    --context C             explicit edge-context filter (repeatable)")
        print("    --budget N              cap output at N tokens (default 2000)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  affected \"X\"             reverse traversal to find nodes impacted by X")
        print("    --relation R            edge relation to traverse in reverse (repeatable)")
        print("    --depth N               reverse traversal depth (default 2)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  save-result             save a Q&A result to graphify-out/memory/ for graph feedback loop")
        print("    --question Q            the question asked")
        print("    --answer A              the answer to save")
        print("    --type T                query type: query|path_query|explain (default: query)")
        print("    --nodes N1 N2 ...       source node labels cited in the answer")
        print("    --memory-dir DIR        memory directory (default: graphify-out/memory)")
        print("  check-update <path>     check needs_update flag and notify if semantic re-extraction is pending (cron-safe)")
        print("  tree                    emit a D3 v7 collapsible-tree HTML for graph.json")
        print("    --graph PATH            path to graph.json (default graphify-out/graph.json)")
        print("    --output HTML           output path (default graphify-out/GRAPH_TREE.html)")
        print("    --root PATH             filesystem root for the hierarchy")
        print("    --max-children N        cap children per node (default 200)")
        print("    --top-k-edges N         per-symbol outbound edges in inspector (default 12)")
        print("    --label NAME            project label in header")
        print("  extract <path>          headless full extraction (AST + semantic LLM) for CI/scripts")
        print("    --backend B             gemini|kimi|claude|openai|deepseek|ollama (default: whichever API key is set)")
        print("    --model M               override backend default model")
        print("    --max-workers N         AST extraction subprocess count (default: cpu_count)")
        print("    --token-budget N        per-chunk token cap for semantic extraction (default: 60000)")
        print("    --max-concurrency N     parallel semantic chunks in flight (default: 4; set 1 for local LLMs)")
        print("    --api-timeout S         per-request timeout in seconds for the LLM client (default: 600)")
        print("    --out DIR               output dir (default: <path>); writes <DIR>/graphify-out/")
        print("    --google-workspace      export .gdoc/.gsheet/.gslides shortcuts via gws before extraction")
        print("    --no-cluster            skip clustering, write raw extraction only")
        print("    --global                also merge the resulting graph into the global graph")
        print("    --as <tag>              repo tag for --global (default: target directory name)")
        print("  global add <graph.json>  add/update a project graph in the global graph (~/.graphify/global-graph.json)")
        print("    --as <tag>               repo tag (default: parent directory name)")
        print("  global remove <tag>      remove a repo's nodes from the global graph")
        print("  global list              list repos in the global graph")
        print("  global path              print path to the global graph file")
        print("  benchmark [graph.json]  measure token reduction vs naive full-corpus approach")
        print("  export callflow-html    emit Mermaid-based architecture/call-flow HTML")
        print("  hook install            install post-commit/post-checkout git hooks (all platforms)")
        print("  hook uninstall          remove git hooks")
        print("  hook status             check if git hooks are installed")
        print("  gemini install          write GEMINI.md section + BeforeTool hook (Gemini CLI)")
        print("  gemini uninstall        remove GEMINI.md section + BeforeTool hook")
        print("  cursor install          write .cursor/rules/graphify.mdc (Cursor)")
        print("  cursor uninstall        remove .cursor/rules/graphify.mdc")
        print("  claude install          write graphify section to CLAUDE.md + PreToolUse hook (Claude Code)")
        print("  claude uninstall        remove graphify section from CLAUDE.md + PreToolUse hook")
        print("  codex install           write graphify section to AGENTS.md (Codex)")
        print("  codex uninstall         remove graphify section from AGENTS.md")
        print("  opencode install        write graphify section to AGENTS.md + tool.execute.before plugin (OpenCode)")
        print("  opencode uninstall      remove graphify section from AGENTS.md + plugin")
        print("  aider install           write graphify section to AGENTS.md (Aider)")
        print("  aider uninstall         remove graphify section from AGENTS.md")
        print("  copilot install         copy graphify skill to ~/.copilot/skills (GitHub Copilot CLI)")
        print("  copilot uninstall       remove graphify skill from ~/.copilot/skills")
        print("  vscode install          configure VS Code Copilot Chat (skill + .github/copilot-instructions.md)")
        print("  vscode uninstall        remove VS Code Copilot Chat configuration")
        print("  claw install            write graphify section to AGENTS.md (OpenClaw)")
        print("  claw uninstall          remove graphify section from AGENTS.md")
        print("  droid install           write graphify section to AGENTS.md (Factory Droid)")
        print("  droid uninstall        remove graphify section from AGENTS.md")
        print("  trae install            write graphify section to AGENTS.md (Trae)")
        print("  trae uninstall         remove graphify section from AGENTS.md")
        print("  trae-cn install         write graphify section to AGENTS.md (Trae CN)")
        print("  trae-cn uninstall      remove graphify section from AGENTS.md")
        print("  antigravity install     write .agents/rules + .agents/workflows + skill (Google Antigravity)")
        print("  antigravity uninstall   remove .agents/rules, .agents/workflows, and skill")
        print("  hermes install          write skill to ~/.hermes/skills/graphify/ (Hermes)")
        print("  hermes uninstall        remove skill from ~/.hermes/skills/graphify/")
        print("  kiro install            write skill to .kiro/skills/graphify/ + steering file (Kiro IDE/CLI)")
        print("  kiro uninstall          remove skill + steering file")
        print("  devin install           write skill to ~/.config/devin/skills/graphify/ (Devin CLI)")
        print("  devin uninstall         remove skill from ~/.config/devin/skills/graphify/")
        print("  pi install              write skill to ~/.pi/agent/skills/graphify/ (Pi coding agent)")
        print("  pi uninstall            remove skill from ~/.pi/agent/skills/graphify/")
        print()
        return

    cmd = sys.argv[1]

    # Universal help guard: -h/--help/-? anywhere after the command shows help
    # and stops — prevents flags from silently triggering destructive subcommands
    # (e.g. "cursor install --help" was silently installing into Cursor, #821).
    # Exempt: free-text commands (user string may contain these tokens), and
    # "install"/"uninstall" which have their own per-subcommand help handlers.
    _FREE_TEXT_CMDS = {"query", "explain", "path", "save-result", "install", "uninstall"}
    if cmd not in _FREE_TEXT_CMDS and any(a in {"-h", "--help", "-?"} for a in sys.argv[2:]):
        print(f"Run 'graphify --help' for full usage.")
        return

    if cmd == "install":
        # Default to windows platform on Windows, claude elsewhere
        default_platform = "windows" if platform.system() == "Windows" else "claude"
        selected_platform: str | None = None
        project_scope = False
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-h", "--help"):
                _print_install_usage()
                return
            if arg == "--project":
                project_scope = True
                i += 1
            elif arg.startswith("--platform="):
                candidate = arg.split("=", 1)[1]
                if selected_platform and selected_platform != candidate:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = candidate
                i += 1
            elif arg == "--platform":
                if i + 1 >= len(args):
                    print("error: --platform requires a value", file=sys.stderr)
                    sys.exit(1)
                candidate = args[i + 1]
                if selected_platform and selected_platform != candidate:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = candidate
                i += 2
            elif arg.startswith("-"):
                print(f"error: unknown install option '{arg}'", file=sys.stderr)
                sys.exit(1)
            else:
                if selected_platform and selected_platform != arg:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = arg
                i += 1
        chosen_platform = selected_platform or default_platform
        if project_scope:
            _project_install(chosen_platform, Path("."))
        else:
            install(platform_name=chosen_platform)
    elif cmd == "uninstall":
        args = sys.argv[2:]
        purge = "--purge" in args
        project_scope = "--project" in args
        selected_platform = None
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("--purge", "--project"):
                i += 1
            elif arg.startswith("--platform="):
                selected_platform = arg.split("=", 1)[1]
                i += 1
            elif arg == "--platform":
                if i + 1 >= len(args):
                    print("error: --platform requires a value", file=sys.stderr)
                    sys.exit(1)
                selected_platform = args[i + 1]
                i += 2
            elif arg.startswith("-"):
                print(f"error: unknown uninstall option '{arg}'", file=sys.stderr)
                sys.exit(1)
            else:
                selected_platform = arg
                i += 1
        if project_scope:
            if selected_platform:
                _project_uninstall(selected_platform, Path("."))
            else:
                _project_uninstall_all(Path("."))
        else:
            uninstall_all(purge=purge)
    elif cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("claude", Path("."))
            else:
                claude_install()
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("claude", Path("."))
            else:
                claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "gemini":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            gemini_install(project=("--project" in sys.argv[3:]))
        elif subcmd == "uninstall":
            gemini_uninstall(project=("--project" in sys.argv[3:]))
        else:
            print("Usage: graphify gemini [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "cursor":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _cursor_install(Path("."))
        elif subcmd == "uninstall":
            _cursor_uninstall(Path("."))
        else:
            print("Usage: graphify cursor [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "vscode":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            vscode_install()
        elif subcmd == "uninstall":
            vscode_uninstall()
        else:
            print("Usage: graphify vscode [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "copilot":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("copilot", Path("."))
            else:
                install(platform="copilot")
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("copilot", Path("."))
            else:
                removed = _remove_skill_file("copilot")
                print("skill removed" if removed else "nothing to remove")
        else:
            print("Usage: graphify copilot [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "kiro":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _kiro_install(Path("."))
        elif subcmd == "uninstall":
            _kiro_uninstall(Path("."))
        else:
            print("Usage: graphify kiro [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "pi":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("pi", Path("."))
            else:
                install("pi")
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("pi", Path("."))
            else:
                _remove_skill_file("pi")
        else:
            print("Usage: graphify pi [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "devin":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        project = "--project" in sys.argv
        if subcmd == "install":
            if project:
                _project_install("devin", Path("."))
                _devin_rules_install(Path("."))
            else:
                install(platform="devin")
        elif subcmd == "uninstall":
            if project:
                _project_uninstall("devin", Path("."))
                _devin_rules_uninstall(Path("."))
            else:
                removed = _remove_skill_file("devin")
                if removed:
                    print("  devin skill removed")
                else:
                    print("  devin skill not found")
        else:
            print("Usage: graphify devin [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd in ("aider", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install(cmd, Path("."))
            else:
                _agents_install(Path("."), cmd)
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall(cmd, Path("."))
            else:
                _agents_uninstall(Path("."), platform=cmd)
                if cmd == "codex":
                    _uninstall_codex_hook(Path("."))
        else:
            print(f"Usage: graphify {cmd} [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "antigravity":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("antigravity", Path("."))
            else:
                _antigravity_install(Path("."))
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("antigravity", Path("."))
            else:
                _antigravity_uninstall(Path("."))
        else:
            print("Usage: graphify antigravity [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "prs":
        from graphify.prs import cmd_prs
        cmd_prs(sys.argv[2:])
    elif cmd == "hook":
        from graphify.hooks import install as hook_install, uninstall as hook_uninstall, status as hook_status
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            print(hook_install(Path(".")))
        elif subcmd == "uninstall":
            print(hook_uninstall(Path(".")))
        elif subcmd == "status":
            print(hook_status(Path(".")))
        else:
            print("Usage: graphify hook [install|uninstall|status]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: graphify query \"<question>\" [--dfs] [--context C] [--budget N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve.search import _query_graph_text
        from networkx.readwrite import json_graph
        question = sys.argv[2]
        use_dfs = "--dfs" in sys.argv
        budget = 2000
        graph_path = _default_graph_path()
        context_filters: list[str] = []
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--budget" and i + 1 < len(args):
                try:
                    budget = int(args[i + 1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--budget="):
                try:
                    budget = int(args[i].split("=", 1)[1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--context" and i + 1 < len(args):
                context_filters.append(args[i + 1])
                i += 2
            elif args[i].startswith("--context="):
                context_filters.append(args[i].split("=", 1)[1])
                i += 1
            elif args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]; i += 2
            else:
                i += 1
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print(f"error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        try:
            import json as _json
            import networkx as _nx
            _raw = _json.loads(gp.read_text(encoding="utf-8"))
            if "links" not in _raw and "edges" in _raw:
                _raw = dict(_raw, links=_raw["edges"])
            try:
                G = json_graph.node_link_graph(_raw, edges="links")
            except TypeError:
                G = json_graph.node_link_graph(_raw)
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            _query_graph_text(
                G,
                question,
                mode="dfs" if use_dfs else "bfs",
                depth=2,
                token_budget=budget,
                context_filters=context_filters,
            )
        )
    elif cmd == "affected":
        if len(sys.argv) < 3:
            print("Usage: graphify affected \"<node-or-label>\" [--relation R] [--depth N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.affected import DEFAULT_AFFECTED_RELATIONS, format_affected, load_graph
        query = sys.argv[2]
        graph_path = "graphify-out/graph.json"
        depth = 2
        relations: list[str] = []
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
                i += 2
            elif args[i].startswith("--graph="):
                graph_path = args[i].split("=", 1)[1]
                i += 1
            elif args[i] == "--depth" and i + 1 < len(args):
                try:
                    depth = int(args[i + 1])
                except ValueError:
                    print("error: --depth must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--depth="):
                try:
                    depth = int(args[i].split("=", 1)[1])
                except ValueError:
                    print("error: --depth must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--relation" and i + 1 < len(args):
                relations.append(args[i + 1])
                i += 2
            elif args[i].startswith("--relation="):
                relations.append(args[i].split("=", 1)[1])
                i += 1
            else:
                i += 1
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print("error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        try:
            graph = load_graph(gp)
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            format_affected(
                graph,
                query,
                relations=relations or DEFAULT_AFFECTED_RELATIONS,
                depth=depth,
            )
        )
    elif cmd == "save-result":
        # graphify save-result --question Q --answer A --type T [--nodes N1 N2 ...]
        import argparse as _ap
        p = _ap.ArgumentParser(prog="graphify save-result")
        p.add_argument("--question", required=True)
        p.add_argument("--answer", required=True)
        p.add_argument("--type", dest="query_type", default="query")
        p.add_argument("--nodes", nargs="*", default=[])
        p.add_argument("--memory-dir", default="graphify-out/memory")
        opts = p.parse_args(sys.argv[2:])
        from graphify.ingest import save_query_result as _sqr
        out = _sqr(
            question=opts.question,
            answer=opts.answer,
            memory_dir=Path(opts.memory_dir),
            query_type=opts.query_type,
            source_nodes=opts.nodes or None,
        )
        print(f"Saved to {out}")
    elif cmd == "path":
        if len(sys.argv) < 4:
            print("Usage: graphify path \"<source>\" \"<target>\" [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve.search import _score_nodes
        from networkx.readwrite import json_graph
        import networkx as _nx
        source_label = sys.argv[2]
        target_label = sys.argv[3]
        graph_path = _default_graph_path()
        args = sys.argv[4:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        # Force directed so the renderer can recover stored caller→callee direction.
        _raw = {**_raw, "directed": True}
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        src_scored = _score_nodes(G, [t.lower() for t in source_label.split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in target_label.split()])
        if not src_scored:
            print(f"No node matching '{source_label}' found.", file=sys.stderr)
            sys.exit(1)
        if not tgt_scored:
            print(f"No node matching '{target_label}' found.", file=sys.stderr)
            sys.exit(1)
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        # Ambiguity guard: when both queries resolve to the same node, the
        # shortest path is trivially zero hops, which is almost never what the
        # caller wanted (see bug #828).
        if src_nid == tgt_nid:
            print(
                f"'{source_label}' and '{target_label}' both resolved to the same "
                f"node '{src_nid}'. Use a more specific label or the exact node ID.",
                file=sys.stderr,
            )
            sys.exit(1)
        for _name, _scored in (("source", src_scored), ("target", tgt_scored)):
            if len(_scored) >= 2:
                _top, _runner = _scored[0][0], _scored[1][0]
                if _top > 0 and (_top - _runner) / _top < 0.10:
                    print(
                        f"warning: {_name} match was ambiguous "
                        f"(top score {_top:g}, runner-up {_runner:g})",
                        file=sys.stderr,
                    )
        try:
            path_nodes = _nx.shortest_path(G.to_undirected(as_view=True), src_nid, tgt_nid)
        except (_nx.NetworkXNoPath, _nx.NodeNotFound):
            print(f"No path found between '{source_label}' and '{target_label}'.")
            sys.exit(0)
        hops = len(path_nodes) - 1
        segments = []
        from graphify.build import edge_data
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            # Check which direction the stored edge points.
            if G.has_edge(u, v):
                edata = edge_data(G, u, v)
                forward = True
            else:
                edata = edge_data(G, v, u)
                forward = False
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            if forward:
                segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
            else:
                segments.append(f"<--{rel}{conf_str}-- {G.nodes[v].get('label', v)}")
        print(f"Shortest path ({hops} hops):\n  " + " ".join(segments))

    elif cmd == "explain":
        if len(sys.argv) < 3:
            print("Usage: graphify explain \"<node>\" [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve.search import _find_node
        from networkx.readwrite import json_graph
        label = sys.argv[2]
        graph_path = _default_graph_path()
        args = sys.argv[3:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        # Force directed so the renderer can recover stored caller→callee direction.
        _raw = {**_raw, "directed": True}
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        matches = _find_node(G, label)
        if not matches:
            print(f"No node matching '{label}' found.")
            sys.exit(0)
        nid = matches[0]
        d = G.nodes[nid]
        print(f"Node: {d.get('label', nid)}")
        print(f"  ID:        {nid}")
        print(f"  Source:    {d.get('source_file', '')} {d.get('source_location', '')}".rstrip())
        print(f"  Type:      {d.get('file_type', '')}")
        print(f"  Community: {d.get('community', '')}")
        print(f"  Degree:    {G.degree(nid)}")
        from graphify.build import edge_data
        connections: list[tuple[str, str, dict]] = []  # (direction, neighbor_id, edge_data)
        for nb in G.successors(nid):
            connections.append(("out", nb, edge_data(G, nid, nb)))
        for nb in G.predecessors(nid):
            connections.append(("in", nb, edge_data(G, nb, nid)))
        if connections:
            print(f"\nConnections ({len(connections)}):")
            connections.sort(key=lambda c: G.degree(c[1]), reverse=True)
            for direction, nb, edata in connections[:20]:
                rel = edata.get("relation", "")
                conf = edata.get("confidence", "")
                arrow = "-->" if direction == "out" else "<--"
                print(f"  {arrow} {G.nodes[nb].get('label', nb)} [{rel}] [{conf}]")
            if len(connections) > 20:
                print(f"  ... and {len(connections) - 20} more")

    elif cmd == "diagnose":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd != "multigraph":
            print(
                "Usage: graphify diagnose multigraph "
                "[--graph path] [--json] [--max-examples N] "
                "[--directed] [--undirected] [--extract-path path]",
                file=sys.stderr,
            )
            sys.exit(1)

        graph_path = Path(_default_graph_path())
        max_examples = 5
        directed: bool | None = None
        direction_flag: str | None = None
        json_output = False
        extract_path: Path | None = None

        i = 3
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == "--graph":
                i += 1
                if i >= len(sys.argv):
                    print("error: --graph requires a path", file=sys.stderr)
                    sys.exit(1)
                graph_path = Path(sys.argv[i])
            elif arg == "--json":
                json_output = True
            elif arg == "--max-examples":
                i += 1
                if i >= len(sys.argv):
                    print("error: --max-examples requires an integer", file=sys.stderr)
                    sys.exit(1)
                try:
                    max_examples = int(sys.argv[i])
                except ValueError:
                    print("error: --max-examples requires an integer", file=sys.stderr)
                    sys.exit(1)
                if max_examples < 0:
                    print("error: --max-examples must be >= 0", file=sys.stderr)
                    sys.exit(1)
            elif arg == "--directed":
                if direction_flag == "undirected":
                    print(
                        "error: --directed and --undirected are mutually exclusive",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                direction_flag = "directed"
                directed = True
            elif arg == "--undirected":
                if direction_flag == "directed":
                    print(
                        "error: --directed and --undirected are mutually exclusive",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                direction_flag = "undirected"
                directed = False
            elif arg == "--extract-path":
                i += 1
                if i >= len(sys.argv):
                    print("error: --extract-path requires a path", file=sys.stderr)
                    sys.exit(1)
                extract_path = Path(sys.argv[i])
            else:
                print(f"error: unknown diagnose option {arg}", file=sys.stderr)
                sys.exit(1)
            i += 1

        from graphify.diagnostics import (
            diagnose_file,
            format_diagnostic_json,
            format_diagnostic_report,
        )

        try:
            summary = diagnose_file(
                graph_path,
                directed=directed,
                root=Path(".").resolve(),
                max_examples=max_examples,
                extract_path=extract_path,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

        if json_output:
            print(json.dumps(format_diagnostic_json(summary), indent=2))
        else:
            print(format_diagnostic_report(summary))

    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: graphify add <url> [--author Name] [--contributor Name] [--dir ./raw]", file=sys.stderr)
            sys.exit(1)
        from graphify.ingest import ingest as _ingest
        url = sys.argv[2]
        author: str | None = None
        contributor: str | None = None
        target_dir = Path("raw")
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--author" and i + 1 < len(args):
                author = args[i + 1]; i += 2
            elif args[i] == "--contributor" and i + 1 < len(args):
                contributor = args[i + 1]; i += 2
            elif args[i] == "--dir" and i + 1 < len(args):
                target_dir = Path(args[i + 1]); i += 2
            else:
                i += 1
        try:
            saved = _ingest(url, target_dir, author=author, contributor=contributor)
            print(f"Saved to {saved}")
            print("Run /graphify --update in your AI assistant to update the graph.")
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "watch":
        watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch.core import watch as _watch
        try:
            _watch(watch_path)
        except ImportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "cluster-only":
        # Mirror the tree/export arg-parsing pattern: walk argv so flags and
        # the optional positional path can appear in any order (#724).
        no_viz = "--no-viz" in sys.argv
        _min_cs_arg = next((a for a in sys.argv if a.startswith("--min-community-size=")), None)
        min_community_size = int(_min_cs_arg.split("=")[1]) if _min_cs_arg else 3
        args = sys.argv[2:]
        watch_path: Path | None = None
        graph_override: Path | None = None
        co_resolution: float = 1.0
        co_exclude_hubs: float | None = None
        i_arg = 0
        while i_arg < len(args):
            a = args[i_arg]
            if a == "--graph" and i_arg + 1 < len(args):
                graph_override = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--resolution" and i_arg + 1 < len(args):
                co_resolution = float(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--resolution="):
                co_resolution = float(a.split("=", 1)[1]); i_arg += 1
            elif a == "--exclude-hubs" and i_arg + 1 < len(args):
                co_exclude_hubs = float(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--exclude-hubs="):
                co_exclude_hubs = float(a.split("=", 1)[1]); i_arg += 1
            elif a == "--no-viz" or a.startswith("--min-community-size="):
                i_arg += 1
            elif a.startswith("--"):
                i_arg += 1
            elif watch_path is None:
                watch_path = Path(a); i_arg += 1
            else:
                i_arg += 1
        if watch_path is None:
            watch_path = Path(".")
        graph_json = graph_override if graph_override is not None else watch_path / "graphify-out" / "graph.json"
        if not graph_json.exists():
            print(f"error: no graph found at {graph_json} — run /graphify first", file=sys.stderr)
            sys.exit(1)
        from networkx.readwrite import json_graph as _jg
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export.markdown import to_json, to_html, _viz_node_limit
        print("Loading existing graph...")
        _enforce_graph_size_cap_or_exit(graph_json)
        _raw = json.loads(graph_json.read_text(encoding="utf-8"))
        _directed = bool(_raw.get("directed", False))
        G = build_from_json(_raw, directed=_directed)
        print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        print("Re-clustering...")
        communities = cluster(G, resolution=co_resolution, exclude_hubs_percentile=co_exclude_hubs)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        out = watch_path / "graphify-out"
        out.mkdir(parents=True, exist_ok=True)
        labels_path = out / ".graphify_labels.json"
        if labels_path.exists():
            try:
                labels = {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}
            except Exception:
                labels = {cid: f"Community {cid}" for cid in communities}
        else:
            labels = {cid: f"Community {cid}" for cid in communities}
        questions = suggest_questions(G, communities, labels)
        tokens = {"input": 0, "output": 0}
        from graphify.export.markdown import _git_head as _gh
        _commit = _gh()
        report = generate(G, communities, cohesion, labels, gods, surprises,
                          {"warning": "cluster-only mode — file stats not available"},
                          tokens, str(watch_path), suggested_questions=questions,
                          min_community_size=min_community_size, built_at_commit=_commit)
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        from graphify.export.markdown import backup_if_protected as _backup
        _backup(out)
        to_json(G, communities, str(out / "graph.json"))
        labels_path.write_text(json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False), encoding="utf-8")

        # Mirror watch.py pattern: gate to_html so core outputs (graph.json +
        # GRAPH_REPORT.md) always land. Honor --no-viz explicitly; otherwise
        # fall back to ValueError handling so an oversized graph doesn't crash
        # the CLI mid-write and leave a stale graph.html on disk.
        html_target = out / "graph.html"
        if no_viz:
            if html_target.exists():
                html_target.unlink()
            print(f"Done — {len(communities)} communities. GRAPH_REPORT.md and graph.json updated (--no-viz; graph.html removed).")
        else:
            try:
                to_html(G, communities, str(html_target), community_labels=labels or None, node_limit=_viz_node_limit())
                print(f"Done — {len(communities)} communities. GRAPH_REPORT.md, graph.json and graph.html updated.")
            except ValueError as viz_err:
                if html_target.exists():
                    html_target.unlink()
                print(f"Skipped graph.html: {viz_err}")
                print(f"Done — {len(communities)} communities. GRAPH_REPORT.md and graph.json updated.")

    elif cmd == "update":
        force = os.environ.get("GRAPHIFY_FORCE", "").lower() in ("1", "true", "yes")
        no_cluster = False
        args = sys.argv[2:]
        watch_arg: str | None = None
        for a in args:
            if a == "--force":
                force = True
                continue
            if a == "--no-cluster":
                no_cluster = True
                continue
            if a.startswith("-"):
                print(f"error: unknown update option: {a}", file=sys.stderr)
                sys.exit(2)
            if watch_arg is not None:
                print("error: update accepts at most one path argument", file=sys.stderr)
                sys.exit(2)
            watch_arg = a

        if watch_arg is not None:
            watch_path = Path(watch_arg)
        else:
            # Try to recover the scan root saved by the last full build
            saved = Path(_GRAPHIFY_OUT) / ".graphify_root"
            if saved.exists():
                watch_path = Path(saved.read_text(encoding="utf-8").strip())
            else:
                watch_path = Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch.core import _rebuild_code
        print(f"Re-extracting code files in {watch_path} (no LLM needed)...")
        # Interactive CLI: block on the per-repo lock rather than skip, so the
        # user sees their explicit `graphify update` complete instead of
        # exiting silently when a hook-driven rebuild happens to be running.
        ok = _rebuild_code(watch_path, force=force, no_cluster=no_cluster, block_on_lock=True)
        if ok:
            print("Code graph updated. For doc/paper/image changes run /graphify --update in your AI assistant.")
            if not (
                os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("MOONSHOT_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY")
                or os.environ.get("GRAPHIFY_NO_TIPS")
            ):
                print("Tip: set GEMINI_API_KEY or GOOGLE_API_KEY to use Gemini for semantic extraction.")
        else:
            print("Nothing to update or rebuild failed — check output above.", file=sys.stderr)
            sys.exit(1)

    elif cmd == "hook-check":
        # Codex Desktop rejects hookSpecificOutput.additionalContext on PreToolUse.
        # Keep this as a cross-platform no-op so installed hooks never break Bash
        # tool calls. Graph guidance reaches the agent via AGENTS.md / skill instead.
        sys.exit(0)
    elif cmd == "check-update":
        if len(sys.argv) < 3:
            print("Usage: graphify check-update <path>", file=sys.stderr)
            sys.exit(1)
        from graphify.watch.core import check_update
        check_update(Path(sys.argv[2]).resolve())
        sys.exit(0)
    elif cmd == "tree":
        # Emit a D3 v7 collapsible-tree HTML view of graph.json:
        # expand-all / collapse-all / reset-view buttons, multi-line
        # wrapText labels with separately-coloured name + count,
        # depth-based palette, click-to-toggle subtree, hover inspector
        # showing top-K outbound edges per symbol.
        from typing import Optional as _Opt
        from graphify.export.tree import write_tree_html, DEFAULT_MAX_CHILDREN
        graph_path = Path(_GRAPHIFY_OUT) / "graph.json"
        output_path: "_Opt[Path]" = None
        root: "_Opt[str]" = None
        max_children = DEFAULT_MAX_CHILDREN
        top_k_edges = 0
        project_label: "_Opt[str]" = None
        args = sys.argv[2:]
        i_arg = 0
        while i_arg < len(args):
            a = args[i_arg]
            if a == "--graph" and i_arg + 1 < len(args):
                graph_path = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--output" and i_arg + 1 < len(args):
                output_path = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--root" and i_arg + 1 < len(args):
                root = args[i_arg + 1]; i_arg += 2
            elif a == "--max-children" and i_arg + 1 < len(args):
                max_children = int(args[i_arg + 1]); i_arg += 2
            elif a == "--top-k-edges" and i_arg + 1 < len(args):
                top_k_edges = int(args[i_arg + 1]); i_arg += 2
            elif a == "--label" and i_arg + 1 < len(args):
                project_label = args[i_arg + 1]; i_arg += 2
            elif a in ("-h", "--help"):
                print("Usage: graphify tree [--graph PATH] [--output HTML]")
                print("  --graph PATH         path to graph.json (default graphify-out/graph.json)")
                print("  --output HTML        output path (default graphify-out/GRAPH_TREE.html)")
                print("  --root PATH          filesystem root (default: longest common dir of all source_files)")
                print("  --max-children N     cap visible children per node (default 200)")
                print("  --top-k-edges N      pre-compute top-K outbound edges per symbol (default 12)")
                print("  --label NAME         project label shown in the page header")
                return
            else:
                i_arg += 1
        if not graph_path.is_file():
            print(f"error: graph.json not found at {graph_path}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(graph_path)
        if output_path is None:
            output_path = graph_path.parent / "GRAPH_TREE.html"
        out = write_tree_html(
            graph_path=graph_path, output_path=output_path,
            root=root, max_children=max_children,
            top_k_edges=top_k_edges, project_label=project_label,
        )
        size_kb = out.stat().st_size / 1024
        print(f"wrote {out} ({size_kb:.1f} KB)")
        print(f"open with: xdg-open {out}  (or file://{out.resolve()})")
        sys.exit(0)

    elif cmd == "merge-driver":
        # git merge driver for graph.json — takes (base, current, other) and writes
        # the union of current+other nodes/edges back to current. Exits 1 on
        # corrupt input so git surfaces the conflict instead of silently
        # accepting a poisoned merge (see F-005).
        # Usage: graphify merge-driver %O %A %B  (set in .git/config merge driver)
        if len(sys.argv) < 5:
            print("Usage: graphify merge-driver <base> <current> <other>", file=sys.stderr)
            sys.exit(1)
        _base_path, _current_path, _other_path = sys.argv[2], sys.argv[3], sys.argv[4]
        # Hard caps so a malicious or corrupted graph.json cannot exhaust memory
        # at parse time. 50 MB / 100k nodes are well above any realistic graph
        # (typical graphs are <5 MB / <50k nodes); anything larger should fail
        # the merge so a human can investigate.
        _MERGE_MAX_BYTES = 50 * 1024 * 1024
        _MERGE_MAX_NODES = 100_000
        import networkx as _nx
        from networkx.readwrite import json_graph as _jg
        def _load_graph(p: str):
            path_obj = Path(p)
            try:
                size = path_obj.stat().st_size
            except OSError as exc:
                raise RuntimeError(f"cannot stat {p}: {exc}") from exc
            if size > _MERGE_MAX_BYTES:
                raise RuntimeError(
                    f"graph.json {p} is {size} bytes, exceeds {_MERGE_MAX_BYTES}-byte cap"
                )
            data = json.loads(path_obj.read_text(encoding="utf-8"))
            try:
                return _jg.node_link_graph(data, edges="links"), data
            except TypeError:
                return _jg.node_link_graph(data), data
        try:
            G_cur, _ = _load_graph(_current_path)
            G_oth, _ = _load_graph(_other_path)
        except Exception as exc:
            print(f"[graphify merge-driver] error loading graphs: {exc}", file=sys.stderr)
            sys.exit(1)  # surface the conflict so git doesn't accept a corrupt merge
        merged = _nx.compose(G_cur, G_oth)
        if merged.number_of_nodes() > _MERGE_MAX_NODES:
            print(
                f"[graphify merge-driver] merged graph has {merged.number_of_nodes()} nodes, "
                f"exceeds {_MERGE_MAX_NODES}-node cap; aborting merge.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            out_data = _jg.node_link_data(merged, edges="links")
        except TypeError:
            out_data = _jg.node_link_data(merged)
        Path(_current_path).write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        sys.exit(0)

    elif cmd == "merge-graphs":
        # graphify merge-graphs graph1.json graph2.json ... --out merged.json
        args = sys.argv[2:]
        graph_paths: list[Path] = []
        out_path = Path(_GRAPHIFY_OUT) / "merged-graph.json"
        i = 0
        while i < len(args):
            if args[i] == "--out" and i + 1 < len(args):
                out_path = Path(args[i + 1]); i += 2
            else:
                graph_paths.append(Path(args[i])); i += 1
        if len(graph_paths) < 2:
            print("Usage: graphify merge-graphs <graph1.json> <graph2.json> [...] [--out merged.json]", file=sys.stderr)
            sys.exit(1)
        import networkx as _nx
        from networkx.readwrite import json_graph as _jg
        from graphify.build import prefix_graph_for_global as _prefix
        graphs = []
        for gp in graph_paths:
            if not gp.exists():
                print(f"error: not found: {gp}", file=sys.stderr)
                sys.exit(1)
            _enforce_graph_size_cap_or_exit(gp)
            data = json.loads(gp.read_text(encoding="utf-8"))
            # Normalize edges/links key before loading — graphify writes "links"
            # via node_link_data but older runs may have used "edges" (#738).
            if "links" not in data and "edges" in data:
                data = dict(data, links=data["edges"])
            try:
                G = _jg.node_link_graph(data, edges="links")
            except TypeError:
                G = _jg.node_link_graph(data)
            graphs.append(G)
        merged = _nx.Graph()
        for G, gp in zip(graphs, graph_paths):
            repo_tag = gp.parent.parent.name  # graphify-out/../ → repo dir name
            prefixed = _prefix(G, repo_tag)
            merged = _nx.compose(merged, prefixed)
        try:
            out_data = _jg.node_link_data(merged, edges="links")
        except TypeError:
            out_data = _jg.node_link_data(merged)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        print(f"Merged {len(graphs)} graphs -> {merged.number_of_nodes()} nodes, {merged.number_of_edges()} edges")
        print(f"Written to: {out_path}")

    elif cmd == "clone":
        if len(sys.argv) < 3:
            print("Usage: graphify clone <github-url> [--branch <branch>] [--out <dir>]", file=sys.stderr)
            sys.exit(1)
        url = sys.argv[2]
        branch: str | None = None
        out_dir: Path | None = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--branch" and i + 1 < len(args):
                branch = args[i + 1]; i += 2
            elif args[i] == "--out" and i + 1 < len(args):
                out_dir = Path(args[i + 1]); i += 2
            else:
                i += 1
        local_path = _clone_repo(url, branch=branch, out_dir=out_dir)
        print(local_path)

    elif cmd == "export":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd not in ("html", "callflow-html", "obsidian", "wiki", "svg", "graphml", "neo4j"):
            print("Usage: graphify export <format>", file=sys.stderr)
            print("  html      [--graph PATH] [--labels PATH] [--node-limit N] [--no-viz]", file=sys.stderr)
            print("  callflow-html [GRAPH|DIR] [--graph PATH] [--labels PATH] [--report PATH] [--sections PATH] [--output HTML]", file=sys.stderr)
            print("            [--lang auto|zh-CN|en] [--max-sections N] [--diagram-scale N]", file=sys.stderr)
            print("  obsidian  [--graph PATH] [--labels PATH] [--dir PATH]", file=sys.stderr)
            print("  wiki      [--graph PATH] [--labels PATH]", file=sys.stderr)
            print("  svg       [--graph PATH] [--labels PATH]", file=sys.stderr)
            print("  graphml   [--graph PATH]", file=sys.stderr)
            print("  neo4j     [--graph PATH] [--push URI] [--user U] [--password P]", file=sys.stderr)
            print("            (or set NEO4J_PASSWORD instead of --password to keep it off argv)", file=sys.stderr)
            sys.exit(1)

        # Parse shared args
        args = sys.argv[3:]
        graph_path = Path(_GRAPHIFY_OUT) / "graph.json"
        graph_path_explicit = False
        labels_path = Path(_GRAPHIFY_OUT) / ".graphify_labels.json"
        labels_path_explicit = False
        report_path = Path(_GRAPHIFY_OUT) / "GRAPH_REPORT.md"
        report_path_explicit = False
        sections_path: Path | None = None
        callflow_output: Path | None = None
        callflow_lang = "auto"
        callflow_max_sections = 15
        callflow_diagram_scale = 1.0
        callflow_max_diagram_nodes = 18
        callflow_max_diagram_edges = 24
        analysis_path = Path(_GRAPHIFY_OUT) / ".graphify_analysis.json"
        node_limit = 5000
        no_viz = False
        obsidian_dir = Path(_GRAPHIFY_OUT) / "obsidian"
        neo4j_uri: str | None = None
        neo4j_user = "neo4j"
        # F-031: prefer the NEO4J_PASSWORD env var so the password never
        # appears on argv (visible in `ps` output / shell history). The
        # explicit --password flag still overrides it for compatibility.
        neo4j_password: str | None = os.environ.get("NEO4J_PASSWORD") or None
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--graph" and i + 1 < len(args):
                graph_path = Path(args[i + 1])
                graph_path_explicit = True
                i += 2
            elif a == "--labels" and i + 1 < len(args):
                labels_path = Path(args[i + 1])
                labels_path_explicit = True
                i += 2
            elif a == "--report" and i + 1 < len(args):
                report_path = Path(args[i + 1])
                report_path_explicit = True
                i += 2
            elif a == "--sections" and i + 1 < len(args):
                sections_path = Path(args[i + 1]); i += 2
            elif a == "--output" and i + 1 < len(args):
                callflow_output = Path(args[i + 1]).expanduser()
                if not callflow_output.is_absolute():
                    callflow_output = Path.cwd() / callflow_output
                i += 2
            elif a == "--lang" and i + 1 < len(args):
                callflow_lang = args[i + 1]; i += 2
            elif a == "--max-sections" and i + 1 < len(args):
                callflow_max_sections = int(args[i + 1]); i += 2
            elif a == "--diagram-scale" and i + 1 < len(args):
                callflow_diagram_scale = float(args[i + 1]); i += 2
            elif a == "--max-diagram-nodes" and i + 1 < len(args):
                callflow_max_diagram_nodes = int(args[i + 1]); i += 2
            elif a == "--max-diagram-edges" and i + 1 < len(args):
                callflow_max_diagram_edges = int(args[i + 1]); i += 2
            elif a in ("-h", "--help") and subcmd == "callflow-html":
                print("Usage: graphify export callflow-html [GRAPH|DIR] [--graph PATH] [--labels PATH]")
                print("  --report PATH          path to GRAPH_REPORT.md")
                print("  --sections PATH        JSON section definitions")
                print("  --output HTML          output path (default graphify-out/<project>-callflow.html)")
                print("  --lang LANG            auto, zh-CN, en, etc. (default auto)")
                print("  --max-sections N       maximum auto-derived sections (default 15)")
                print("  --diagram-scale N      Mermaid diagram scale (default 1.0)")
                print("  --max-diagram-nodes N  representative nodes per section (default 18)")
                print("  --max-diagram-edges N  representative edges per section (default 24)")
                sys.exit(0)
            elif a == "--node-limit" and i + 1 < len(args):
                node_limit = int(args[i + 1]); i += 2
            elif a == "--no-viz":
                no_viz = True; i += 1
            elif a == "--dir" and i + 1 < len(args):
                obsidian_dir = Path(args[i + 1]); i += 2
            elif a == "--push" and i + 1 < len(args):
                neo4j_uri = args[i + 1]; i += 2
            elif a == "--user" and i + 1 < len(args):
                neo4j_user = args[i + 1]; i += 2
            elif a == "--password" and i + 1 < len(args):
                neo4j_password = args[i + 1]; i += 2
            elif subcmd == "callflow-html" and not a.startswith("-") and not graph_path_explicit:
                candidate = Path(a)
                if candidate.name == "graph.json" or candidate.suffix.lower() == ".json":
                    graph_path = candidate
                elif (candidate / "graph.json").exists():
                    graph_path = candidate / "graph.json"
                else:
                    graph_path = candidate / _GRAPHIFY_OUT / "graph.json"
                graph_path_explicit = True
                i += 1
            else:
                i += 1

        graph_path = graph_path.expanduser()
        if graph_path_explicit:
            graph_out_dir = graph_path.parent
            if not labels_path_explicit:
                labels_path = graph_out_dir / ".graphify_labels.json"
            if not report_path_explicit:
                report_path = graph_out_dir / "GRAPH_REPORT.md"
        labels_path = labels_path.expanduser()
        report_path = report_path.expanduser()

        if not graph_path.exists():
            print(f"error: graph not found: {graph_path}. Run /graphify <path> first.", file=sys.stderr)
            sys.exit(1)

        if subcmd == "callflow-html":
            from graphify.export.callflow import write_callflow_html as _write_callflow_html
            out = _write_callflow_html(
                graph=graph_path,
                report=report_path,
                labels=labels_path,
                sections=sections_path,
                output=callflow_output,
                lang=callflow_lang,
                max_sections=callflow_max_sections,
                diagram_scale=callflow_diagram_scale,
                max_diagram_nodes=callflow_max_diagram_nodes,
                max_diagram_edges=callflow_max_diagram_edges,
                verbose=True,
            )
            print(f"callflow HTML written - open in any browser: {out}")
            sys.exit(0)

        from networkx.readwrite import json_graph as _jg

        _enforce_graph_size_cap_or_exit(graph_path)
        _raw = json.loads(graph_path.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        try:
            G = _jg.node_link_graph(_raw, edges="links")
        except TypeError:
            G = _jg.node_link_graph(_raw)

        # Load optional analysis/labels
        communities: dict[int, list[str]] = {}
        if analysis_path.exists():
            _an = json.loads(analysis_path.read_text(encoding="utf-8"))
            communities = {int(k): v for k, v in _an.get("communities", {}).items()}
            cohesion: dict[int, float] = {int(k): v for k, v in _an.get("cohesion", {}).items()}
            gods_data = _an.get("gods", [])
        else:
            cohesion = {}
            gods_data = []

        # Fallback: graph.json carries the per-node community as a node attribute
        # (`to_json` writes it on every node). The analysis sidecar is the
        # canonical source — but the post-commit / watch rebuild path doesn't
        # regenerate it, and `extract` may have its temp files cleaned up. When
        # that happens, `graphify export html` previously bailed with
        # "Single community - aggregated view not useful." even though the
        # per-node attribute had the right data all along. Reconstruct from
        # the graph itself so downstream subcommands (html, obsidian, wiki,
        # svg, graphml, neo4j) don't silently produce a degraded artifact.
        if not communities:
            reconstructed: dict[int, list[str]] = {}
            for node_id, data in G.nodes(data=True):
                cid_raw = data.get("community")
                if cid_raw is None:
                    continue
                try:
                    cid = int(cid_raw)
                except (TypeError, ValueError):
                    continue
                reconstructed.setdefault(cid, []).append(str(node_id))
            if reconstructed:
                communities = reconstructed

        labels: dict[int, str] = {}
        if labels_path.exists():
            labels = {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}

        out_dir = graph_path.parent

        if subcmd == "html":
            from graphify.export.markdown import to_html as _to_html
            if no_viz:
                html_target = out_dir / "graph.html"
                if html_target.exists():
                    html_target.unlink()
                print("--no-viz: skipped graph.html")
            else:
                _to_html(G, communities, str(out_dir / "graph.html"),
                         community_labels=labels or None, node_limit=node_limit)
                if G.number_of_nodes() <= node_limit:
                    print(f"graph.html written - open in any browser, no server needed")

        elif subcmd == "obsidian":
            from graphify.export.markdown import to_obsidian as _to_obsidian, to_canvas as _to_canvas
            n = _to_obsidian(G, communities, str(obsidian_dir),
                             community_labels=labels or None, cohesion=cohesion or None)
            print(f"Obsidian vault: {n} notes in {obsidian_dir}/")
            _to_canvas(G, communities, str(obsidian_dir / "graph.canvas"),
                       community_labels=labels or None)
            print(f"Canvas: {obsidian_dir}/graph.canvas")
            print(f"Open {obsidian_dir}/ as a vault in Obsidian.")

        elif subcmd == "wiki":
            from graphify.wiki import to_wiki as _to_wiki
            from graphify.analyze import god_nodes as _god_nodes
            if not communities:
                print(
                    "error: .graphify_analysis.json is missing or empty — refusing to export wiki to prevent data loss.\n"
                    "Run `graphify extract .` (or `graphify cluster-only .`) to regenerate community data first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not gods_data:
                gods_data = _god_nodes(G)
            n = _to_wiki(G, communities, str(out_dir / "wiki"),
                         community_labels=labels or None, cohesion=cohesion or None,
                         god_nodes_data=gods_data)
            print(f"Wiki: {n} articles written to {out_dir}/wiki/")
            print(f"  {out_dir}/wiki/index.md  ->  agent entry point")

        elif subcmd == "svg":
            from graphify.export.markdown import to_svg as _to_svg
            _to_svg(G, communities, str(out_dir / "graph.svg"),
                    community_labels=labels or None)
            print(f"graph.svg written - embeds in Obsidian, Notion, GitHub READMEs")

        elif subcmd == "graphml":
            from graphify.export.markdown import to_graphml as _to_graphml
            _to_graphml(G, communities, str(out_dir / "graph.graphml"))
            print(f"graph.graphml written - open in Gephi, yEd, or any GraphML tool")

        elif subcmd == "neo4j":
            if neo4j_uri:
                from graphify.export.markdown import push_to_neo4j as _push
                if neo4j_password is None:
                    print("error: --password required for --push", file=sys.stderr)
                    sys.exit(1)
                result = _push(G, uri=neo4j_uri, user=neo4j_user,
                               password=neo4j_password, communities=communities)
                print(f"Pushed to Neo4j: {result['nodes']} nodes, {result['edges']} edges")
            else:
                from graphify.export.markdown import to_cypher as _to_cypher
                _to_cypher(G, str(out_dir / "cypher.txt"))
                print(f"cypher.txt written - import with: cypher-shell < {out_dir}/cypher.txt")

    elif cmd == "benchmark":
        from graphify.benchmark import run_benchmark, print_benchmark
        graph_path = sys.argv[2] if len(sys.argv) > 2 else "graphify-out/graph.json"
        _enforce_graph_size_cap_or_exit(Path(graph_path))
        # Try to load corpus_words from detect output
        corpus_words = None
        detect_path = Path(".graphify_detect.json")
        if detect_path.exists():
            try:
                detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
                corpus_words = detect_data.get("total_words")
            except Exception:
                pass
        result = run_benchmark(graph_path, corpus_words=corpus_words)
        print_benchmark(result)

    elif cmd == "global":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        from graphify.global_graph import (
            global_add as _global_add,
            global_remove as _global_remove,
            global_list as _global_list,
            global_path as _global_path,
        )
        if subcmd == "add":
            # graphify global add <graph.json> [--as <tag>]
            args = sys.argv[3:]
            source = None
            tag = None
            i = 0
            while i < len(args):
                if args[i] == "--as" and i + 1 < len(args):
                    tag = args[i + 1]; i += 2
                elif not source:
                    source = Path(args[i]); i += 1
                else:
                    i += 1
            if not source:
                print("Usage: graphify global add <graph.json> [--as <repo-tag>]", file=sys.stderr)
                sys.exit(1)
            tag = tag or source.parent.parent.name
            try:
                result = _global_add(source, tag)
                if result["skipped"]:
                    print(f"'{tag}' unchanged since last add — global graph not modified.")
                else:
                    print(f"Added '{tag}' to global graph: +{result['nodes_added']} nodes, "
                          f"-{result['nodes_removed']} pruned. Global: {_global_path()}")
            except Exception as exc:
                print(f"error: {exc}", file=sys.stderr); sys.exit(1)
        elif subcmd == "remove":
            tag = sys.argv[3] if len(sys.argv) > 3 else ""
            if not tag:
                print("Usage: graphify global remove <repo-tag>", file=sys.stderr); sys.exit(1)
            try:
                removed = _global_remove(tag)
                print(f"Removed '{tag}' from global graph ({removed} nodes pruned).")
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr); sys.exit(1)
        elif subcmd == "list":
            repos = _global_list()
            if not repos:
                print("Global graph is empty. Use 'graphify global add' to add a project.")
            else:
                print(f"Global graph: {_global_path()}")
                for tag, info in repos.items():
                    print(f"  {tag}: {info.get('node_count', '?')} nodes, added {info.get('added_at', '?')[:10]}")
        elif subcmd == "path":
            print(_global_path())
        else:
            print("Usage: graphify global [add|remove|list|path]", file=sys.stderr); sys.exit(1)

    elif cmd == "extract":
        # Headless full-pipeline extraction for CI / scripts (#698).
        # Runs detect -> AST extraction on code -> semantic LLM extraction on
        # docs/papers/images -> merge -> build -> cluster -> write outputs.
        # Unlike the skill.md path (which runs through Claude Code subagents),
        # this calls extract_corpus_parallel directly using whichever backend
        # has an API key set.
        if len(sys.argv) < 3:
            print(
                "Usage: graphify extract <path> [--backend gemini|kimi|claude|openai|deepseek|ollama] "
                "[--model M] [--out DIR] [--google-workspace] [--no-cluster] "
                "[--max-workers N] [--token-budget N] [--max-concurrency N] "
                "[--api-timeout S]",
                file=sys.stderr,
            )
            sys.exit(1)

        target = Path(sys.argv[2]).resolve()
        if not target.exists():
            print(f"error: path not found: {target}", file=sys.stderr)
            sys.exit(1)

        backend: str | None = None
        model: str | None = None
        out_dir: Path | None = None
        no_cluster = False
        dedup_llm = False
        google_workspace = False
        global_merge = False
        global_repo_tag: str | None = None
        # Performance/tuning knobs (issue #792). None means "use library default".
        cli_max_workers: int | None = None
        cli_token_budget: int | None = None
        cli_max_concurrency: int | None = None
        cli_api_timeout: float | None = None
        # Clustering tuning knobs
        cli_resolution: float = 1.0
        cli_exclude_hubs: float | None = None
        cli_excludes: list[str] = []

        def _parse_int(name: str, raw: str) -> int:
            try:
                v = int(raw)
            except ValueError:
                print(f"error: {name} must be a positive integer (got {raw!r})", file=sys.stderr)
                sys.exit(2)
            if v <= 0:
                print(f"error: {name} must be > 0 (got {v})", file=sys.stderr)
                sys.exit(2)
            return v

        def _parse_float(name: str, raw: str) -> float:
            try:
                v = float(raw)
            except ValueError:
                print(f"error: {name} must be a positive number (got {raw!r})", file=sys.stderr)
                sys.exit(2)
            if v <= 0:
                print(f"error: {name} must be > 0 (got {v})", file=sys.stderr)
                sys.exit(2)
            return v

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--backend" and i + 1 < len(args):
                backend = args[i + 1]; i += 2
            elif a.startswith("--backend="):
                backend = a.split("=", 1)[1]; i += 1
            elif a == "--model" and i + 1 < len(args):
                model = args[i + 1]; i += 2
            elif a.startswith("--model="):
                model = a.split("=", 1)[1]; i += 1
            elif a == "--out" and i + 1 < len(args):
                out_dir = Path(args[i + 1]); i += 2
            elif a.startswith("--out="):
                out_dir = Path(a.split("=", 1)[1]); i += 1
            elif a == "--no-cluster":
                no_cluster = True; i += 1
            elif a == "--dedup-llm":
                dedup_llm = True; i += 1
            elif a == "--google-workspace":
                google_workspace = True; i += 1
            elif a == "--global":
                global_merge = True; i += 1
            elif a == "--as" and i + 1 < len(args):
                global_repo_tag = args[i + 1]; i += 2
            elif a == "--max-workers" and i + 1 < len(args):
                cli_max_workers = _parse_int("--max-workers", args[i + 1]); i += 2
            elif a.startswith("--max-workers="):
                cli_max_workers = _parse_int("--max-workers", a.split("=", 1)[1]); i += 1
            elif a == "--token-budget" and i + 1 < len(args):
                cli_token_budget = _parse_int("--token-budget", args[i + 1]); i += 2
            elif a.startswith("--token-budget="):
                cli_token_budget = _parse_int("--token-budget", a.split("=", 1)[1]); i += 1
            elif a == "--max-concurrency" and i + 1 < len(args):
                cli_max_concurrency = _parse_int("--max-concurrency", args[i + 1]); i += 2
            elif a.startswith("--max-concurrency="):
                cli_max_concurrency = _parse_int("--max-concurrency", a.split("=", 1)[1]); i += 1
            elif a == "--api-timeout" and i + 1 < len(args):
                cli_api_timeout = _parse_float("--api-timeout", args[i + 1]); i += 2
            elif a.startswith("--api-timeout="):
                cli_api_timeout = _parse_float("--api-timeout", a.split("=", 1)[1]); i += 1
            elif a == "--resolution" and i + 1 < len(args):
                cli_resolution = _parse_float("--resolution", args[i + 1]); i += 2
            elif a.startswith("--resolution="):
                cli_resolution = _parse_float("--resolution", a.split("=", 1)[1]); i += 1
            elif a == "--exclude-hubs" and i + 1 < len(args):
                cli_exclude_hubs = float(args[i + 1]); i += 2
            elif a.startswith("--exclude-hubs="):
                cli_exclude_hubs = float(a.split("=", 1)[1]); i += 1
            elif a == "--exclude" and i + 1 < len(args):
                cli_excludes.append(args[i + 1]); i += 2
            elif a.startswith("--exclude="):
                cli_excludes.append(a.split("=", 1)[1]); i += 1
            else:
                i += 1

        # CLI flag wins over env var. Setting GRAPHIFY_API_TIMEOUT here so
        # _call_openai_compat picks it up without needing a new kwarg path.
        if cli_api_timeout is not None:
            os.environ["GRAPHIFY_API_TIMEOUT"] = str(cli_api_timeout)
        if cli_max_workers is not None:
            os.environ["GRAPHIFY_MAX_WORKERS"] = str(cli_max_workers)

        # Backend resolution. If user did not pass --backend, sniff env.
        # If backend was explicitly requested, validate its key is present
        # and surface a clear error early — don't let extract_corpus_parallel
        # raise mid-run after we've spent time on AST extraction.
        from graphify.llm.core import (
            BACKENDS as _BACKENDS,
            detect_backend as _detect_backend,
            estimate_cost as _estimate_cost,
            extract_corpus_parallel as _extract_corpus_parallel,
            _format_backend_env_keys,
            _get_backend_api_key,
        )
        if backend is None:
            backend = _detect_backend()
            if backend is None:
                print(
                    "error: no LLM API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                    "(gemini), MOONSHOT_API_KEY (kimi), ANTHROPIC_API_KEY (claude), "
                    "OPENAI_API_KEY (openai), DEEPSEEK_API_KEY (deepseek), "
                    "or pass --backend.",
                    file=sys.stderr,
                )
                sys.exit(1)
        if backend not in _BACKENDS:
            print(
                f"error: unknown backend '{backend}'. "
                f"Available: {', '.join(sorted(_BACKENDS))}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not _get_backend_api_key(backend):
            # Ollama on a loopback URL ignores auth entirely; don't block
            # the run just because OLLAMA_API_KEY is unset (issue #792).
            # extract_files_direct already prints a warning and substitutes
            # a placeholder key in that case.
            allow_no_key = False
            if backend == "ollama":
                from urllib.parse import urlparse
                ollama_url = os.environ.get(
                    "OLLAMA_BASE_URL",
                    _BACKENDS["ollama"].get("base_url", ""),
                )
                try:
                    host = (urlparse(ollama_url).hostname or "").lower()
                except Exception:
                    host = ""
                allow_no_key = (
                    host in ("localhost", "127.0.0.1", "::1")
                    or host.startswith("127.")
                )
            elif backend == "bedrock":
                allow_no_key = bool(
                    os.environ.get("AWS_PROFILE")
                    or os.environ.get("AWS_REGION")
                    or os.environ.get("AWS_DEFAULT_REGION")
                    or os.environ.get("AWS_ACCESS_KEY_ID")
                )
            elif backend == "claude-cli":
                import shutil as _shutil
                allow_no_key = _shutil.which("claude") is not None
                if not allow_no_key:
                    print(
                        "error: backend 'claude-cli' requires the `claude` CLI on $PATH "
                        "(install Claude Code and run `claude` once to authenticate).",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            if not allow_no_key:
                print(
                    f"error: backend '{backend}' requires {_format_backend_env_keys(backend)} to be set.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Resolve output dir. The user-facing contract is "<out>/graphify-out/"
        # so a fresh checkout writes graphify-out/ at the project root, matching
        # the skill.md pipeline.
        out_root = (out_dir.resolve() if out_dir else target)
        graphify_out = out_root / "graphify-out"
        graphify_out.mkdir(parents=True, exist_ok=True)

        from graphify.detect.core import (
            detect as _detect,
            detect_incremental as _detect_incremental,
            save_manifest as _save_manifest,
        )
        manifest_path = graphify_out / "manifest.json"
        existing_graph_path = graphify_out / "graph.json"
        incremental_mode = manifest_path.exists() and existing_graph_path.exists()

        if incremental_mode:
            print(f"[graphify extract] incremental scan of {target}")
            detection = _detect_incremental(
                target,
                manifest_path=str(manifest_path),
                google_workspace=google_workspace or None,
                extra_excludes=cli_excludes or None,
            )
        else:
            print(f"[graphify extract] scanning {target}")
            detection = _detect(target, google_workspace=google_workspace or None, extra_excludes=cli_excludes or None)

        files_by_type = detection.get("files", {})
        if incremental_mode:
            new_by_type = detection.get("new_files", {})
            code_files = [Path(p) for p in new_by_type.get("code", [])]
            doc_files = [Path(p) for p in new_by_type.get("document", [])]
            paper_files = [Path(p) for p in new_by_type.get("paper", [])]
            image_files = [Path(p) for p in new_by_type.get("image", [])]
            deleted_files = list(detection.get("deleted_files", []))
            unchanged_total = sum(len(v) for v in detection.get("unchanged_files", {}).values())
        else:
            code_files = [Path(p) for p in files_by_type.get("code", [])]
            doc_files = [Path(p) for p in files_by_type.get("document", [])]
            paper_files = [Path(p) for p in files_by_type.get("paper", [])]
            image_files = [Path(p) for p in files_by_type.get("image", [])]
            deleted_files = []
            unchanged_total = 0

        semantic_files = doc_files + paper_files + image_files
        if incremental_mode:
            print(
                f"[graphify extract] {len(code_files)} code, {len(doc_files)} docs, "
                f"{len(paper_files)} papers, {len(image_files)} images changed; "
                f"{unchanged_total} unchanged; {len(deleted_files)} deleted"
            )
        else:
            print(
                f"[graphify extract] found {len(code_files)} code, "
                f"{len(doc_files)} docs, {len(paper_files)} papers, "
                f"{len(image_files)} images"
            )

        # AST extraction on code files. Empty code list (docs-only corpus) is
        # the issue #698 case — skip cleanly instead of crashing inside extract().
        ast_result: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        if code_files:
            from graphify.extract import extract as _ast_extract
            ast_kwargs: dict = {"cache_root": target}
            if cli_max_workers is not None:
                ast_kwargs["max_workers"] = cli_max_workers
            print(f"[graphify extract] AST extraction on {len(code_files)} code files...")
            try:
                ast_result = _ast_extract(code_files, **ast_kwargs)
            except Exception as exc:
                print(f"[graphify extract] AST extraction failed: {exc}", file=sys.stderr)
                ast_result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}

        # Semantic extraction on docs/papers/images. Check cache first.
        from graphify.cache import (
            check_semantic_cache as _check_semantic_cache,
            save_semantic_cache as _save_semantic_cache,
        )
        sem_result: dict = {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0,
        }
        sem_cache_hits = 0
        sem_cache_misses = 0
        if semantic_files:
            sem_paths_str = [str(p) for p in semantic_files]
            cached_nodes, cached_edges, cached_hyperedges, uncached_paths = (
                _check_semantic_cache(sem_paths_str, root=target)
            )
            sem_cache_hits = len(semantic_files) - len(uncached_paths)
            sem_cache_misses = len(uncached_paths)
            sem_result["nodes"].extend(cached_nodes)
            sem_result["edges"].extend(cached_edges)
            sem_result["hyperedges"].extend(cached_hyperedges)
            if sem_cache_hits:
                print(f"[graphify extract] semantic cache: {sem_cache_hits} hit / {sem_cache_misses} miss")

            if uncached_paths:
                print(f"[graphify extract] semantic extraction on {len(uncached_paths)} files via {backend}...")
                corpus_kwargs: dict = {
                    "backend": backend,
                    "model": model,
                    "root": target,
                }
                if cli_token_budget is not None:
                    corpus_kwargs["token_budget"] = cli_token_budget
                if cli_max_concurrency is not None:
                    corpus_kwargs["max_concurrency"] = cli_max_concurrency

                # Minimal progress callback so the CLI is no longer silent
                # during long local-inference runs (issue #792 addendum).
                # Also track per-chunk success so we can fail loudly when
                # every chunk errors (e.g. missing backend SDK package).
                _chunk_stats = {"total": 0, "succeeded": 0}
                def _progress(idx: int, total: int, _result: dict) -> None:
                    _chunk_stats["total"] = total
                    _chunk_stats["succeeded"] += 1
                    print(
                        f"[graphify extract] chunk {idx + 1}/{total} done",
                        flush=True,
                    )
                corpus_kwargs["on_chunk_done"] = _progress

                try:
                    fresh = _extract_corpus_parallel(
                        [Path(p) for p in uncached_paths],
                        **corpus_kwargs,
                    )
                except ImportError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    sys.exit(1)
                except Exception as exc:
                    print(
                        f"[graphify extract] semantic extraction failed: {exc}",
                        file=sys.stderr,
                    )
                    fresh = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

                # on_chunk_done only fires after a chunk succeeds. If fresh
                # semantic extraction was requested and no chunks completed,
                # fail instead of writing an AST-only graph with exit 0.
                if uncached_paths and _chunk_stats["succeeded"] == 0:
                    print(
                        f"[graphify extract] error: all semantic chunks failed "
                        f"for backend '{backend}' ({len(uncached_paths)} uncached files) - "
                        f"see per-chunk errors above. If you see 'requires the X package', "
                        f"run `pip install X` and retry.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                try:
                    _save_semantic_cache(
                        fresh.get("nodes", []),
                        fresh.get("edges", []),
                        fresh.get("hyperedges", []),
                        root=target,
                    )
                except Exception as exc:
                    print(f"[graphify extract] warning: could not write semantic cache: {exc}", file=sys.stderr)
                sem_result["nodes"].extend(fresh.get("nodes", []))
                sem_result["edges"].extend(fresh.get("edges", []))
                sem_result["hyperedges"].extend(fresh.get("hyperedges", []))
                sem_result["input_tokens"] += fresh.get("input_tokens", 0)
                sem_result["output_tokens"] += fresh.get("output_tokens", 0)

        # Merge AST + semantic. Order matters for deduplication: passing AST
        # first means semantic node attributes win on collision (richer labels
        # for symbols also referenced in docs). Hyperedges only come from the
        # semantic side.
        merged: dict = {
            "nodes": list(ast_result.get("nodes", [])) + list(sem_result.get("nodes", [])),
            "edges": list(ast_result.get("edges", [])) + list(sem_result.get("edges", [])),
            "hyperedges": list(sem_result.get("hyperedges", [])),
            "input_tokens": ast_result.get("input_tokens", 0) + sem_result.get("input_tokens", 0),
            "output_tokens": ast_result.get("output_tokens", 0) + sem_result.get("output_tokens", 0),
        }

        graph_json_path = graphify_out / "graph.json"
        analysis_path = graphify_out / ".graphify_analysis.json"

        # Build a manifest-safe files dict: only stamp semantic_hash for files
        # that actually produced output (cache hit or fresh extraction). Files
        # whose chunk failed have no source_file entry in sem_result — leaving
        # their semantic_hash empty so detect_incremental re-queues them (#933).
        _sem_extracted: set[str] = {
            n.get("source_file", "") for n in sem_result.get("nodes", [])
        } | {
            e.get("source_file", "") for e in sem_result.get("edges", [])
        }
        _sem_extracted.discard("")
        _sem_types = {"document", "paper", "image"}
        _manifest_files = {
            ftype: [f for f in flist if ftype not in _sem_types or f in _sem_extracted]
            for ftype, flist in files_by_type.items()
        }

        if no_cluster:
            # --no-cluster: dump the raw merged extraction as graph.json.
            # No NetworkX, no community detection, no analysis sidecar.
            from graphify.export.markdown import backup_if_protected as _backup
            _backup(graphify_out)
            graph_json_path.write_text(
                json.dumps(merged, indent=2), encoding="utf-8"
            )
            cost = _estimate_cost(
                backend, merged["input_tokens"], merged["output_tokens"]
            )
            print(
                f"[graphify extract] wrote {graph_json_path} — "
                f"{len(merged['nodes'])} nodes, {len(merged['edges'])} edges "
                f"(no clustering)"
            )
            if merged["input_tokens"] or merged["output_tokens"]:
                print(
                    f"[graphify extract] tokens: "
                    f"{merged['input_tokens']:,} in / "
                    f"{merged['output_tokens']:,} out, "
                    f"est. cost: ${cost:.4f}"
                )
            try:
                _save_manifest(_manifest_files, manifest_path=str(manifest_path), kind="both")
            except Exception as exc:
                print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)
            if global_merge:
                from graphify.global_graph import global_add as _global_add
                _tag = global_repo_tag or target.name
                try:
                    result = _global_add(graphify_out / "graph.json", _tag)
                    if result["skipped"]:
                        print(f"[graphify global] '{_tag}' unchanged since last add — skipped.")
                    else:
                        print(f"[graphify global] '{_tag}' merged into global graph "
                              f"(+{result['nodes_added']} nodes, -{result['nodes_removed']} pruned).")
                except Exception as exc:
                    print(f"[graphify global] warning: failed to merge into global graph: {exc}", file=sys.stderr)
            sys.exit(0)

        # Build graph + cluster + score + write.
        from graphify.build import (
            build as _build,
            build_merge as _build_merge,
        )
        from graphify.cluster import cluster as _cluster, score_all as _score_all
        from graphify.export.markdown import to_json as _to_json
        from graphify.analyze import god_nodes as _god_nodes, surprising_connections as _surprising
        dedup_backend = backend if dedup_llm else None
        if incremental_mode:
            G = _build_merge(
                [merged],
                graph_path=existing_graph_path,
                prune_sources=deleted_files or None,
                dedup=True,
                dedup_llm_backend=dedup_backend,
                root=target,
            )
        else:
            G = _build([merged], dedup=True, dedup_llm_backend=dedup_backend, root=target)
        if G.number_of_nodes() == 0:
            print(
                "[graphify extract] graph is empty — extraction produced no nodes. "
                "Possible causes: all files skipped, binary-only corpus, or LLM "
                "returned no edges.",
                file=sys.stderr,
            )
            sys.exit(1)

        communities = _cluster(G, resolution=cli_resolution, exclude_hubs_percentile=cli_exclude_hubs)
        cohesion = _score_all(G, communities)
        try:
            gods = _god_nodes(G)
        except Exception:
            gods = []
        try:
            surprises = _surprising(G, communities)
        except Exception:
            surprises = []

        from graphify.export.markdown import backup_if_protected as _backup
        _backup(graphify_out)
        _to_json(G, communities, str(graph_json_path), force=True)
        if merged.get("output_tokens", 0) > 0:
            (graphify_out / ".graphify_semantic_marker").write_text(
                json.dumps({"output_tokens": merged["output_tokens"]}), encoding="utf-8"
            )
        if global_merge:
            from graphify.global_graph import global_add as _global_add
            _tag = global_repo_tag or target.name
            try:
                result = _global_add(graphify_out / "graph.json", _tag)
                if result["skipped"]:
                    print(f"[graphify global] '{_tag}' unchanged since last add — skipped.")
                else:
                    print(f"[graphify global] '{_tag}' merged into global graph "
                          f"(+{result['nodes_added']} nodes, -{result['nodes_removed']} pruned).")
            except Exception as exc:
                print(f"[graphify global] warning: failed to merge into global graph: {exc}", file=sys.stderr)
        analysis = {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "tokens": {
                "input": merged["input_tokens"],
                "output": merged["output_tokens"],
            },
        }
        analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        try:
            _save_manifest(_manifest_files, manifest_path=str(manifest_path), kind="both")
        except Exception as exc:
            print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)

        cost = _estimate_cost(backend, merged["input_tokens"], merged["output_tokens"])
        print(
            f"[graphify extract] wrote {graph_json_path}: "
            f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
            f"{len(communities)} communities"
        )
        print(f"[graphify extract] wrote {analysis_path}")
        if incremental_mode:
            print(
                f"[graphify extract] incremental summary: "
                f"{sem_cache_hits + unchanged_total} files cached/unchanged, "
                f"{len(code_files) + sem_cache_misses} re-extracted, "
                f"{len(deleted_files)} deleted"
            )
        elif sem_cache_hits:
            print(f"[graphify extract] semantic cache: {sem_cache_hits} cached, {sem_cache_misses} re-extracted")
        if merged["input_tokens"] or merged["output_tokens"]:
            print(
                f"[graphify extract] tokens: "
                f"{merged['input_tokens']:,} in / "
                f"{merged['output_tokens']:,} out, "
                f"est. cost (~{backend}): ${cost:.4f}"
            )

    elif cmd == "cache-check":
        # graphify cache-check <files_from> [--root <dir>]
        # Reads file paths (one per line) from <files_from>, checks semantic cache.
        # Writes:
        #   graphify-out/.graphify_cached.json   — already-cached nodes/edges/hyperedges
        #   graphify-out/.graphify_uncached.txt  — paths that need extraction
        # Stdout: "Cache: N hit, M miss"
        from graphify.cache import check_semantic_cache
        if len(sys.argv) < 3:
            print("Usage: graphify cache-check <files_from> [--root <dir>]", file=sys.stderr)
            sys.exit(1)
        files_from = Path(sys.argv[2])
        root = Path(".")
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--root" and i + 1 < len(sys.argv):
                root = Path(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        files = [f for f in files_from.read_text(encoding="utf-8").splitlines() if f.strip()]
        cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(files, root)
        out = root / "graphify-out"
        out.mkdir(parents=True, exist_ok=True)
        if cached_nodes or cached_edges or cached_hyperedges:
            (out / ".graphify_cached.json").write_text(
                json.dumps({"nodes": cached_nodes, "edges": cached_edges, "hyperedges": cached_hyperedges},
                           ensure_ascii=False),
                encoding="utf-8",
            )
        (out / ".graphify_uncached.txt").write_text("\n".join(uncached), encoding="utf-8")
        print(f"Cache: {len(files) - len(uncached)} hit, {len(uncached)} miss")

    elif cmd == "merge-chunks":
        # graphify merge-chunks <chunk_glob_or_files...> --out <path>
        # Concatenates .graphify_chunk_*.json files written by semantic subagents.
        # Deduplicates nodes by id (first writer wins). Sums token counts.
        import glob as _glob
        if len(sys.argv) < 3:
            print("Usage: graphify merge-chunks <chunk_files...> --out <path>", file=sys.stderr)
            sys.exit(1)
        out_path: Path | None = None
        chunk_args: list[str] = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out_path = Path(sys.argv[i + 1])
                i += 2
            else:
                chunk_args.append(sys.argv[i])
                i += 1
        if not out_path:
            print("error: --out <path> required", file=sys.stderr)
            sys.exit(1)
        chunk_files: list[str] = []
        for arg in chunk_args:
            expanded = _glob.glob(arg)
            chunk_files.extend(sorted(expanded) if expanded else [arg])
        merged: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
        seen_ids: set[str] = set()
        for cf in chunk_files:
            try:
                chunk = json.loads(Path(cf).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[graphify merge-chunks] warning: skipping {cf}: {exc}", file=sys.stderr)
                continue
            for n in chunk.get("nodes", []):
                if n.get("id") not in seen_ids:
                    seen_ids.add(n["id"])
                    merged["nodes"].append(n)
            merged["edges"].extend(chunk.get("edges", []))
            merged["hyperedges"].extend(chunk.get("hyperedges", []))
            merged["input_tokens"] += chunk.get("input_tokens", 0)
            merged["output_tokens"] += chunk.get("output_tokens", 0)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        print(
            f"Merged {len(chunk_files)} chunks: {merged['nodes']} nodes, {len(merged['edges'])} edges, "
            f"{merged['input_tokens']:,} in / {merged['output_tokens']:,} out tokens"
        )

    elif cmd == "merge-semantic":
        # graphify merge-semantic --cached <path> --new <path> --out <path>
        # Merges cached semantic results with freshly-extracted chunk results.
        # Deduplicates nodes by id (cached entries take priority over new ones).
        if len(sys.argv) < 3:
            print("Usage: graphify merge-semantic --cached <path> --new <path> --out <path>", file=sys.stderr)
            sys.exit(1)
        cached_path: Path | None = None
        new_path: Path | None = None
        out_path2: Path | None = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--cached" and i + 1 < len(sys.argv):
                cached_path = Path(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--new" and i + 1 < len(sys.argv):
                new_path = Path(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out_path2 = Path(sys.argv[i + 1]); i += 2
            else:
                i += 1
        if not out_path2:
            print("error: --out <path> required", file=sys.stderr)
            sys.exit(1)
        empty: dict = {"nodes": [], "edges": [], "hyperedges": []}
        cached_data = json.loads(cached_path.read_text(encoding="utf-8")) if cached_path and cached_path.exists() else empty
        new_data = json.loads(new_path.read_text(encoding="utf-8")) if new_path and new_path.exists() else empty
        seen_ids2: set[str] = set()
        all_nodes: list[dict] = []
        for n in cached_data.get("nodes", []) + new_data.get("nodes", []):
            if n.get("id") not in seen_ids2:
                seen_ids2.add(n["id"])
                all_nodes.append(n)
        merged2 = {
            "nodes": all_nodes,
            "edges": cached_data.get("edges", []) + new_data.get("edges", []),
            "hyperedges": cached_data.get("hyperedges", []) + new_data.get("hyperedges", []),
        }
        out_path2.parent.mkdir(parents=True, exist_ok=True)
        out_path2.write_text(json.dumps(merged2, ensure_ascii=False), encoding="utf-8")
        print(f"Merged: {len(merged2['nodes'])} nodes, {len(merged2['edges'])} edges")

    elif Path(cmd).exists() or cmd in (".", "..") or cmd.startswith(("./", "../", "/", "~")):
        # User ran `graphify <path>` directly — treat as `graphify extract <path>`.
        # Common when following the PowerShell note in README (`graphify .`) or
        # copy-pasting skill invocations without the leading slash.
        sys.argv.insert(2, sys.argv[1])
        sys.argv[1] = "extract"
        main()
    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'graphify --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
