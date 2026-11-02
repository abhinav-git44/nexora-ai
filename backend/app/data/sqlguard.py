"""SQL safety for LLM-generated queries. Defence in depth:
1. Parse with sqlglot (Postgres dialect). Exactly one statement; must be a SELECT (CTEs allowed, all SELECT).
2. Every table reference must be the logical name `data` (rewritten to the dataset's physical table).
3. Deny-list of dangerous functions; no INTO, no locking clauses, no comments/semicolon chaining.
4. LIMIT enforced (clamped to MAX_ROWS).
5. Executed inside a READ ONLY transaction with statement_timeout, optionally with a read-only DB role.
"""
import sqlglot
from sqlglot import exp

MAX_ROWS = 1000
DENY_FUNCS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import", "lo_export", "dblink", "dblink_exec",
              "set_config", "current_setting", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "query_to_xml",
              "copy", "pg_stat_file", "txid_current", "nextval", "setval", "version", "inet_server_addr", "current_user", "session_user"}


class UnsafeSQL(ValueError):
    pass


def validate_and_rewrite(sql: str, physical_table: str, allowed_columns: set[str]) -> str:
    if not sql or len(sql) > 5000:
        raise UnsafeSQL("Query is empty or too long")
    if "--" in sql or "/*" in sql:
        raise UnsafeSQL("Comments are not allowed")
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"Could not parse SQL: {str(e).splitlines()[0][:200]}")
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeSQL("Exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeSQL("Only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Merge,
                             exp.TruncateTable, exp.Grant, exp.Into, exp.Lock, exp.Copy)):
            raise UnsafeSQL(f"{node.key.upper()} is not allowed")
        if isinstance(node, exp.Anonymous) and node.name.lower() in DENY_FUNCS:
            raise UnsafeSQL(f"Function {node.name} is not allowed")
        if isinstance(node, exp.Func) and getattr(node, "sql_name", lambda: "")().lower() in DENY_FUNCS:
            raise UnsafeSQL("Function not allowed")
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if t.args.get("db") or t.args.get("catalog"):
            raise UnsafeSQL("Schema-qualified tables are not allowed")
        if name in cte_names:
            continue
        if name != "data":
            raise UnsafeSQL(f"Unknown table '{t.name}'. Query the table named data")
        t.set("this", exp.to_identifier(physical_table))
        t.set("db", exp.to_identifier("datasets"))
        if not t.alias:
            t.set("alias", exp.TableAlias(this=exp.to_identifier("data")))
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}
    for c in tree.find_all(exp.Column):
        if c.name and c.name.lower() not in allowed_columns and c.name.lower() not in aliases and c.name != "*":
            raise UnsafeSQL(f"Unknown column '{c.name}'")
    limit = tree.args.get("limit")
    if isinstance(tree, exp.Select):
        if limit is None:
            tree = tree.limit(MAX_ROWS)
        else:
            try:
                n = int(limit.expression.name)
                if n > MAX_ROWS:
                    tree = tree.limit(MAX_ROWS)
            except (ValueError, AttributeError):
                tree = tree.limit(MAX_ROWS)
    else:
        tree = exp.select("*").from_(tree.subquery("u")).limit(MAX_ROWS)
    return tree.sql(dialect="postgres")
