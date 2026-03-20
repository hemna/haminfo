"""SQL query validation for MCP server.

Provides SQL AST-based validation to prevent dangerous operations
while allowing safe SELECT queries against the haminfo database.
"""

from __future__ import annotations

import re


# Tables that are allowed to be queried
ALLOWED_TABLES = frozenset(
    {
        'station',
        'weather_station',
        'weather_report',
        'aprs_packet',
        'request',
        'wx_request',
    }
)

# SQL statements that are explicitly forbidden
FORBIDDEN_KEYWORDS = frozenset(
    {
        'DROP',
        'DELETE',
        'TRUNCATE',
        'ALTER',
        'INSERT',
        'UPDATE',
        'CREATE',
        'GRANT',
        'REVOKE',
        'EXEC',
        'EXECUTE',
        'MERGE',
        'CALL',
        'COPY',
        'LOAD',
        'REPLACE',
    }
)

# Maximum query complexity limits
MAX_QUERY_LENGTH = 2000
MAX_RESULT_LIMIT = 1000


class SQLValidationError(Exception):
    """Raised when a SQL query fails validation."""

    def __init__(self, message: str, query: str = ''):
        self.query = query
        super().__init__(message)


def validate_query(sql: str) -> str:
    """Validate a SQL query for safety.

    Only allows SELECT queries against known tables with
    complexity limits.

    Args:
        sql: The SQL query string to validate.

    Returns:
        The validated (and possibly modified) SQL query string.

    Raises:
        SQLValidationError: If the query is not safe to execute.
    """
    if not sql or not sql.strip():
        raise SQLValidationError('Empty query provided', sql)

    # Normalize whitespace for analysis
    normalized = ' '.join(sql.split()).strip()

    # Check query length
    if len(normalized) > MAX_QUERY_LENGTH:
        raise SQLValidationError(
            f'Query exceeds maximum length of {MAX_QUERY_LENGTH} characters',
            sql,
        )

    # Check for forbidden keywords (case-insensitive, word-boundary)
    upper = normalized.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary matching to avoid false positives
        # e.g., "UPDATED_AT" should not match "UPDATE"
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, upper):
            raise SQLValidationError(
                f'Forbidden SQL operation: {keyword}. Only SELECT queries are allowed.',
                sql,
            )

    # Must start with SELECT (after optional whitespace/comments)
    # Strip leading comments (use original sql to preserve newlines)
    stripped = _strip_sql_comments(sql.strip())
    if not stripped.upper().startswith('SELECT'):
        raise SQLValidationError(
            f'Only SELECT queries are allowed. Query starts with: {stripped[:20]}...',
            sql,
        )

    # Check for multiple statements (SQL injection via semicolon)
    if _contains_multiple_statements(normalized):
        raise SQLValidationError(
            'Multiple SQL statements are not allowed',
            sql,
        )

    # Check for subqueries that might contain dangerous operations
    # This is a safety net - the keyword check above should catch most cases
    _validate_subqueries(normalized)

    # Ensure LIMIT is present (add default if missing)
    if 'LIMIT' not in upper:
        normalized = f'{normalized.rstrip(";")} LIMIT {MAX_RESULT_LIMIT}'

    return normalized


def validate_table_name(table: str) -> bool:
    """Check if a table name is in the allowed list.

    Args:
        table: The table name to validate.

    Returns:
        True if the table is allowed.

    Raises:
        SQLValidationError: If the table is not allowed.
    """
    if table.lower() not in ALLOWED_TABLES:
        raise SQLValidationError(
            f"Table '{table}' is not in the allowed list. "
            f'Allowed tables: {", ".join(sorted(ALLOWED_TABLES))}',
        )
    return True


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments from the beginning of a query."""
    result = sql.strip()
    while result:
        if result.startswith('--'):
            # Single-line comment
            newline = result.find('\n')
            if newline == -1:
                return ''
            result = result[newline + 1 :].strip()
        elif result.startswith('/*'):
            # Block comment
            end = result.find('*/')
            if end == -1:
                return ''
            result = result[end + 2 :].strip()
        else:
            break
    return result


def _contains_multiple_statements(sql: str) -> bool:
    """Check if SQL contains multiple statements.

    Accounts for semicolons within string literals.
    """
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(sql):
        char = sql[i]
        # Handle escape sequences inside quotes
        if char == '\\' and (in_single_quote or in_double_quote):
            i += 2  # Skip escaped character
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == ';' and not in_single_quote and not in_double_quote:
            # Check if there's meaningful content after the semicolon
            remaining = sql[i + 1 :].strip()
            if remaining:
                return True
        i += 1
    return False


def _validate_subqueries(sql: str) -> None:
    """Validate that subqueries don't contain dangerous operations."""
    upper = sql.upper()

    # Check for dangerous patterns in subqueries
    dangerous_patterns = [
        r'INTO\s+(?:OUTFILE|DUMPFILE)',
        r'LOAD_FILE\s*\(',
        r'pg_sleep\s*\(',
        r'pg_read_file\s*\(',
        r'dblink\s*\(',
        r'COPY\s+',
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, upper, re.IGNORECASE):
            raise SQLValidationError(
                'Potentially dangerous SQL pattern detected',
                sql,
            )
