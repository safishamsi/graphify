"""Module 1 \u2014 semantic edge enrichment.

Submodules:
    url_normalize      Pure-function URL + route normalizer and matcher.
    http_probes        Local AST passes that lift route decorators and
                        fetch URL literals onto graph nodes.
    rls_resolver       Supabase / RLS pattern matching.
    migrations         Migration sequencer (timestamp-ordered).
    celery_payload     Producer / consumer payload matcher.
    semantic_edges     Orchestrator that runs all probes and emits the
                        semantic edges + StitcherCoverageReport.
"""
