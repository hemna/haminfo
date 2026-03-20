# haminfo Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-09

## Active Technologies

- Python 3.10+ (supports 3.10-3.13) + Flask 1.1.4+, SQLAlchemy 2.0.41+, GeoAlchemy2 0.17.1+, aprsd 4.2.4 (001-aprs-position-reports)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.10+ (supports 3.10-3.13): Follow standard conventions

## Recent Changes

- 001-aprs-position-reports: Added Python 3.10+ (supports 3.10-3.13) + Flask 1.1.4+, SQLAlchemy 2.0.41+, GeoAlchemy2 0.17.1+, aprsd 4.2.4

<!-- MANUAL ADDITIONS START -->

## Required Skills and Tools

### Context Mode (MANDATORY)

**Always use context-mode tools** for any operation that may produce large output. This keeps context consumption low and enables efficient searching of results.

Prefer these context-mode tools over their standard equivalents:
- `ctx_execute` over `Bash` for commands with potentially large output (git log, test runs, API calls)
- `ctx_batch_execute` for running multiple commands and searching results in one call
- `ctx_execute_file` over `Read` for processing log files, large data files, or extracting specific information
- `ctx_fetch_and_index` over `WebFetch` for fetching and searching web content
- `ctx_search` to search previously indexed content

### Required Skills for This Project

Always invoke these skills when the situation applies:

| Skill | When to Use |
|-------|-------------|
| `postgres-pro` | Any PostgreSQL query optimization, EXPLAIN analysis, database schema changes, GeoAlchemy2/PostGIS operations |
| `database-optimizer` | Investigating slow queries, index design, query rewrites |
| `debugging-wizard` | Investigating errors, analyzing stack traces, troubleshooting |
| `systematic-debugging` | Any bug, test failure, or unexpected behavior before proposing fixes |
| `code-reviewer` | Before completing PRs or major changes |
| `test-driven-development` | When implementing new features or bugfixes |
| `verification-before-completion` | Before claiming work is complete or tests pass |

### Recommended Skills

| Skill | When to Use |
|-------|-------------|
| `fastapi-expert` | If migrating Flask endpoints to FastAPI or building async APIs |
| `mcp-developer` | Working on the MCP server integration (`haminfo/cmds/mcp.py`) |
| `spec-miner` | Understanding undocumented parts of the codebase |
| `brainstorming` | Before implementing new features or significant changes |
| `writing-plans` | For multi-step tasks before touching code |

## Production Environment

See private runbook for production deployment details (host, paths, credentials).

- **Database**: PostgreSQL with PostGIS (haminfo_db container)
- **Cron jobs**: Monthly RepeaterBook fetch (1st of month), weekly DB cleanup (Sundays)

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=haminfo

# Lint check
ruff check .
```

<!-- MANUAL ADDITIONS END -->
