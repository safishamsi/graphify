from __future__ import annotations
from pathlib import Path
from graphify.extract import extract_sql

def introspect_postgres(dsn: str | None = None) -> dict:
    """Connect to PostgreSQL, reconstruct DDL, and extract via extract_sql()."""
    try:
        import psycopg
    except ModuleNotFoundError:
        raise ImportError(
            "psycopg is required for --postgres. "
            "Install with: pip install 'graphify[postgres]'"
        )

    conn = psycopg.connect(dsn or "")  # empty string = PG* env vars
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

            # 3. Query routines (functions/procedures)
            cur.execute("""
                SELECT routine_schema, routine_name, routine_type, routine_definition
                FROM information_schema.routines
                WHERE routine_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY routine_schema, routine_name;
            """)
            routines = cur.fetchall()

            # 4. Query foreign keys
            cur.execute("""
                SELECT
                    kcu1.table_schema,
                    kcu1.table_name,
                    kcu1.column_name,
                    kcu2.table_schema AS foreign_table_schema,
                    kcu2.table_name AS foreign_table_name,
                    kcu2.column_name AS foreign_column_name
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
                ORDER BY kcu1.table_schema, kcu1.table_name, kcu1.ordinal_position;
            """)
            fks = cur.fetchall()
    finally:
        conn.close()

    ddl = []

    # Tables
    for schema, name, ttype in tables:
        if ttype == "BASE TABLE":
            ddl.append(f"CREATE TABLE {schema}.{name} (id INT);")

    # Views — real body if available, stub if NULL (permission denied)
    for schema, name, body in views:
        if body:
            ddl.append(f"CREATE VIEW {schema}.{name} AS {body};")
        else:
            ddl.append(f"CREATE VIEW {schema}.{name} AS SELECT 1;")

    # Functions & Procedures — real body if available, stub if NULL
    for schema, name, rtype, body in routines:
        if rtype == "FUNCTION":
            if body:
                ddl.append(f"CREATE FUNCTION {schema}.{name}() RETURNS void AS $$ {body} $$ LANGUAGE plpgsql;")
            else:
                ddl.append(f"CREATE FUNCTION {schema}.{name}() RETURNS void AS $$ BEGIN SELECT 1; END; $$ LANGUAGE plpgsql;")
        elif rtype == "PROCEDURE":
            if body:
                # To make procedures extractable by tree-sitter-sql (which does not support CREATE PROCEDURE),
                # we represent them as CREATE FUNCTION in the reconstructed DDL.
                ddl.append(f"CREATE FUNCTION {schema}.{name}() RETURNS void AS $$ {body} $$ LANGUAGE plpgsql;")
            else:
                ddl.append(f"CREATE FUNCTION {schema}.{name}() RETURNS void AS $$ BEGIN SELECT 1; END; $$ LANGUAGE plpgsql;")

    # FK edges
    for t_schema, t_name, col, r_schema, r_name, r_col in fks:
        ddl.append(
            f"ALTER TABLE {t_schema}.{t_name} "
            f"ADD CONSTRAINT fk_{t_schema}_{t_name}_{col} FOREIGN KEY ({col}) REFERENCES {r_schema}.{r_name}({r_col});"
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