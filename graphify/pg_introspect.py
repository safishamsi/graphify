from __future__ import annotations
from pathlib import Path
from graphify.extract import extract_sql


def _quote_ident(name: str) -> str:
    """Double-quote a PostgreSQL identifier, escaping embedded double-quotes."""
    return '"' + name.replace('"', '""') + '"'


def introspect_postgres(dsn: str | None = None) -> dict:
    """Connect to PostgreSQL, reconstruct DDL, and extract via extract_sql()."""
    try:
        import psycopg
    except ModuleNotFoundError:
        raise ImportError(
            "psycopg is required for --postgres. "
            "Install with: pip install 'graphify[postgres]'"
        )

    try:
        conn = psycopg.connect(dsn or "")  # empty string = PG* env vars
    except psycopg.OperationalError as exc:
        # Sanitize: strip the DSN/credentials that psycopg may embed in the
        # OperationalError message (e.g. "connection to server … failed: …\nDETAIL: …")
        msg = str(exc).split("\n")[0]
        raise ConnectionError(f"could not connect to PostgreSQL: {msg}") from None

    try:
        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE")

        # 1. Query tables
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """)
            tables = cur.fetchall()

            # 2. Query views
            cur.execute("""
                SELECT table_schema, table_name, view_definition
                FROM information_schema.views
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """)
            views = cur.fetchall()

            # 3. Query routines (functions/procedures), including language
            cur.execute("""
                SELECT routine_schema, routine_name, routine_type,
                       routine_definition, external_language
                FROM information_schema.routines
                WHERE routine_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY routine_schema, routine_name;
            """)
            routines = cur.fetchall()

            # 4. Query foreign keys — grouped by constraint to handle composites
            cur.execute("""
                SELECT
                    tc.constraint_name,
                    kcu1.table_schema,
                    kcu1.table_name,
                    ARRAY_AGG(kcu1.column_name ORDER BY kcu1.ordinal_position) AS columns,
                    kcu2.table_schema AS foreign_table_schema,
                    kcu2.table_name AS foreign_table_name,
                    ARRAY_AGG(kcu2.column_name ORDER BY kcu2.ordinal_position) AS foreign_columns
                FROM
                    information_schema.table_constraints AS tc
                    JOIN information_schema.referential_constraints AS rc
                      ON tc.constraint_name = rc.constraint_name
                      AND tc.table_schema = rc.constraint_schema
                    JOIN information_schema.key_column_usage AS kcu1
                      ON tc.constraint_name = kcu1.constraint_name
                      AND tc.table_schema = kcu1.table_schema
                    JOIN information_schema.key_column_usage AS kcu2
                      ON rc.unique_constraint_name = kcu2.constraint_name
                      AND rc.unique_constraint_schema = kcu2.table_schema
                      AND kcu1.position_in_unique_constraint = kcu2.ordinal_position
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                GROUP BY tc.constraint_name, kcu1.table_schema, kcu1.table_name,
                         kcu2.table_schema, kcu2.table_name
                ORDER BY kcu1.table_schema, kcu1.table_name;
            """)
            fks = cur.fetchall()
    finally:
        conn.close()

    ddl = []

    # Tables — quote identifiers to handle reserved words, hyphens, mixed-case
    for schema, name, ttype in tables:
        if ttype == "BASE TABLE":
            ddl.append(f"CREATE TABLE {_quote_ident(schema)}.{_quote_ident(name)} (id INT);")

    # Views — real body if available, stub if NULL (permission denied)
    for schema, name, body in views:
        if body:
            ddl.append(f"CREATE VIEW {_quote_ident(schema)}.{_quote_ident(name)} AS {body};")
        else:
            ddl.append(f"CREATE VIEW {_quote_ident(schema)}.{_quote_ident(name)} AS SELECT 1;")

    # Functions & Procedures — real body if available, stub if NULL
    # Use $gfx$ as the dollar-quote tag to avoid collision with $$ inside bodies.
    # Use external_language from the catalog; fall back to plpgsql if NULL/blank.
    for schema, name, rtype, body, ext_lang in routines:
        lang = (ext_lang or "plpgsql").lower()
        fn_sig = f"{_quote_ident(schema)}.{_quote_ident(name)}()"
        stub_body = "BEGIN SELECT 1; END;"
        if rtype in ("FUNCTION", "PROCEDURE"):
            actual_body = body if body else stub_body
            # Represent PROCEDUREs as FUNCTION so tree-sitter-sql can parse them
            ddl.append(
                f"CREATE FUNCTION {fn_sig} RETURNS void"
                f" AS $gfx$ {actual_body} $gfx$ LANGUAGE {lang};"
            )

    # FK edges — one ALTER TABLE per constraint (handles composite FKs correctly)
    for constraint_name, t_schema, t_name, cols, r_schema, r_name, r_cols in fks:
        col_list = ", ".join(_quote_ident(c) for c in cols)
        ref_col_list = ", ".join(_quote_ident(c) for c in r_cols)
        ddl.append(
            f"ALTER TABLE {_quote_ident(t_schema)}.{_quote_ident(t_name)} "
            f"ADD CONSTRAINT {_quote_ident(constraint_name)} "
            f"FOREIGN KEY ({col_list}) REFERENCES {_quote_ident(r_schema)}.{_quote_ident(r_name)}({ref_col_list});"
        )

    ddl_string = "\n".join(ddl)

    # Determine host/dbname for virtual path DSN sanitization
    info = psycopg.conninfo.conninfo_to_dict(dsn or "")
    host = info.get("host", "localhost")
    dbname = info.get("dbname", "db")
    virtual_path = Path(f"postgresql://{host}/{dbname}")

    # Pass virtual path and in-memory DDL content to extract_sql
    result = extract_sql(virtual_path, content=ddl_string)
    return result