# LSP Hook Enrichment

Graphify can hand unresolved AST callsites to external LSP resolvers through a
config file. The hook output is evidence; graphify decides which evidence is
safe to promote into graph edges.

## Contract

When LSP hooks are configured and enabled, graphify writes:

```text
graphify-out/unresolved_calls.json
```

External hooks read that file and write JSON fragments to:

```text
graphify-out/enrichment/lsp/
```

The preferred fragment shape is resolver evidence:

```json
{
  "generated_by": "graphify-lsp-definition-hook",
  "language": "ruby",
  "lsp_server": "ruby-lsp",
  "lsp_evidence": [
    {
      "call_id": "call_...",
      "caller": "src_worker_run",
      "callee": "prepare",
      "receiver": "self",
      "source_file": "src/worker.rb",
      "source_location": "L74",
      "definitions": [
        {
          "definition_file": "src/worker.rb",
          "range": {"start": {"line": 12, "character": 6}},
          "target_id": "src_worker_prepare"
        }
      ]
    }
  ]
}
```

Graphify promotes evidence into graph edges conservatively:

- exactly one local target is required;
- receiver-bearing calls require `receiver_type` or `receiver_type_confidence`
  unless the sidecar policy explicitly allows receiver calls without type proof;
- promoted LSP edges are `INFERRED`, not `EXTRACTED`;
- multiple resolvers that agree on the same callsite raise the inferred
  confidence and record the confirming resolvers;
- multiple resolvers that disagree on the same callsite produce `AMBIGUOUS`
  candidate edges;
- external, stdlib, or gem definitions stay sidecar evidence.

## Config Example

Graphify loads hook settings from `.graphify/config.json`. Set `GRAPHIFY_CONFIG`
to use another JSON file. Hook commands are disabled unless
`GRAPHIFY_ENABLE_HOOKS=1` or `GRAPHIFY_ALLOW_HOOKS=1` is set in the process
environment; `GRAPHIFY_NO_HOOKS=1` forces them off. The config can be committed
when a project wants shared resolver settings.

The `{python}` placeholder resolves to `.graphify_python`, then
`graphify-out/.graphify_python`, then the current graphify interpreter. The
Graphify skill bootstrap writes `graphify-out/.graphify_python`, so the examples
below run the hook module from the same environment as graphify. Hooks are
optional by default; set `"required": true` when a resolver failure should stop
the enrichment stage.

```json
{
  "lsp": {
    "parallel_hooks": true,
    "max_parallel_hooks": 4,
    "cache": true,
    "chains": [
      {
        "name": "python",
        "languages": ["python"],
        "required": false,
        "hooks": [
          {
            "name": "pyright",
            "command": [
              "{python}",
              "-m",
              "graphify.lsp_definition_hook",
              "python",
              "--request-concurrency",
              "8",
              "--",
              "pyright-langserver",
              "--stdio"
            ]
          }
        ]
      },
      {
        "name": "typescript",
        "languages": ["typescript"],
        "required": false,
        "hooks": [
          {
            "name": "typescript-language-server",
            "command": [
              "{python}",
              "-m",
              "graphify.lsp_definition_hook",
              "typescript",
              "--request-concurrency",
              "8",
              "--",
              "typescript-language-server",
              "--stdio"
            ]
          }
        ]
      },
      {
        "name": "javascript",
        "languages": ["javascript"],
        "required": false,
        "hooks": [
          {
            "name": "typescript-language-server",
            "command": [
              "{python}",
              "-m",
              "graphify.lsp_definition_hook",
              "javascript",
              "--request-concurrency",
              "8",
              "--",
              "typescript-language-server",
              "--stdio"
            ]
          }
        ]
      },
      {
        "name": "ruby",
        "languages": ["ruby"],
        "required": false,
        "hooks": [
          {
            "name": "ruby-lsp",
            "command": [
              "{python}",
              "-m",
              "graphify.lsp_definition_hook",
              "ruby",
              "--request-concurrency",
              "8",
              "--",
              "ruby-lsp"
            ]
          },
          {
            "name": "solargraph",
            "command": [
              "{python}",
              "-m",
              "graphify.lsp_definition_hook",
              "ruby",
              "--request-concurrency",
              "4",
              "--",
              "solargraph",
              "stdio"
            ]
          }
        ]
      }
    ]
  }
}
```

```bash
GRAPHIFY_ENABLE_HOOKS=1 graphify update .
```

The packaged hook wrapper uses LSP over stdio.

The built-in hook keeps small debug samples by default. Use
`--debug-unmapped 0` and `--debug-errors 0` to suppress debug samples, or `-1`
to keep all samples for local investigation.

## Cache

The LSP cache is strict and whole-workspace by default. A cache hit requires:

- same LSP config;
- same unresolved-call exchange;
- same source file contents for the full run;
- same known language workspace config/lock files, such as `Gemfile.lock`,
  `.solargraph.yml`, `tsconfig.json`, `pyproject.toml`, and lockfiles.

Graphify skips LSP cache reuse for incremental/watch rebuilds that evict only
some files, because LSP definitions can depend on unchanged files.
