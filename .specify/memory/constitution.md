<!--
================================================================================
SYNC IMPACT REPORT
================================================================================
Version Change: N/A → 1.0.0 (Initial ratification)

Modified Principles: N/A (Initial creation)

Added Sections:
  - Core Principles (4 principles)
  - Quality Gates
  - Development Workflow
  - Governance

Removed Sections: N/A (Initial creation)

Templates Requiring Updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (Success Criteria supports testing)
  - .specify/templates/tasks-template.md: ✅ Compatible (Test phases align with Testing principle)

Follow-up TODOs: None
================================================================================
-->

# Haminfo Constitution

## Core Principles

### I. Code Quality

All code contributions MUST adhere to established quality standards to maintain
a consistent, maintainable, and secure codebase.

**Non-Negotiable Rules:**
- All Python code MUST pass `ruff` linting with zero errors before merge
- Code MUST follow PEP 8 style guidelines (enforced via tooling)
- All functions and classes MUST include docstrings explaining purpose and usage
- Type hints MUST be used for all function signatures and public APIs
- No commented-out code or debug statements in production code
- Database queries MUST use parameterized statements (no string concatenation)
- All dependencies MUST be pinned to specific versions in `pyproject.toml`

**Rationale**: Consistent code quality reduces cognitive load during reviews,
prevents security vulnerabilities, and ensures long-term maintainability of the
ham radio information platform.

### II. Testing Standards

Testing is mandatory for all new features and bug fixes. Test coverage ensures
reliability of the ham radio data services.

**Non-Negotiable Rules:**
- All new features MUST include corresponding tests before merge
- Bug fixes MUST include a regression test proving the fix
- Test coverage for new code MUST be at minimum 80%
- Tests MUST be isolated and not depend on external network services
- Database tests MUST use test fixtures, not production data
- Integration tests MUST verify API contract compliance
- Tests MUST run in under 5 minutes for the full suite

**Test Categories Required:**
- Unit tests: For individual functions and methods
- Integration tests: For API endpoints and database operations
- Contract tests: For external API boundaries (APRS, OpenCage, etc.)

**Rationale**: Ham radio operators depend on accurate, reliable data. Testing
ensures data integrity and service availability.

### III. User Experience Consistency

All user-facing interfaces (CLI, API, web) MUST provide a consistent,
predictable experience aligned with ham radio community expectations.

**Non-Negotiable Rules:**
- CLI commands MUST follow the pattern: `haminfo <command> [options]`
- All CLI output MUST support both human-readable and JSON formats (`--format`)
- API responses MUST use consistent JSON structure with `data`, `error`, `meta` fields
- Error messages MUST be actionable and include error codes
- All timestamps MUST use ISO 8601 format (UTC)
- Geographic coordinates MUST use standard lat/lon decimal degrees
- Callsign handling MUST be case-insensitive for input, uppercase for output
- API versioning MUST follow `/api/v{N}/` URL prefix pattern

**Rationale**: Ham radio operators expect standardized interfaces. Consistency
reduces learning curve and enables automation of ham radio workflows.

### IV. Performance Requirements

The system MUST meet performance targets to ensure responsive service for real-time
ham radio data queries.

**Non-Negotiable Rules:**
- API response time MUST be under 200ms for p95 of read operations
- Database queries MUST complete in under 100ms for indexed lookups
- Bulk import operations MUST process at minimum 1000 records/second
- Memory usage MUST stay under 512MB for the API service under normal load
- Geographic queries (PostGIS) MUST use spatial indexes
- Caching MUST be implemented for frequently accessed static data
- No N+1 query patterns in ORM usage

**Monitoring Requirements:**
- All API endpoints MUST log response times
- Database query times MUST be captured via SQLAlchemy events
- Memory and CPU metrics MUST be available via observability tooling

**Rationale**: Ham radio operations often require real-time data access.
Performance ensures the platform supports time-sensitive amateur radio activities.

## Quality Gates

All changes MUST pass through these quality gates before merge:

**Automated Gates:**
1. `ruff check .` - Linting passes with zero errors
2. `pytest` - All tests pass
3. `pytest --cov` - Coverage meets 80% threshold for changed files
4. Type checking via IDE or mypy (advisory, not blocking)

**Manual Review Gates:**
1. Code review by at least one maintainer
2. Documentation updated if public API changes
3. Database migration tested if schema changes
4. Performance impact assessed for data-intensive changes

**Pre-Deployment Gates:**
1. Integration tests pass against staging database
2. API contract tests verify backward compatibility
3. Load test validates performance requirements (for major releases)

## Development Workflow

**Branch Strategy:**
- `main`: Production-ready code only
- `feature/*`: New features branch from main
- `fix/*`: Bug fixes branch from main
- `release/*`: Release preparation branches

**Commit Standards:**
- Commit messages MUST follow Conventional Commits format
- Format: `type(scope): description`
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`
- Example: `feat(api): add repeater search by frequency endpoint`

**Pull Request Requirements:**
- PRs MUST reference related issue (if applicable)
- PRs MUST include description of changes and testing performed
- PRs MUST pass all automated quality gates
- PRs MUST be reviewed before merge (no self-merge to main)

## Governance

This constitution supersedes all other development practices for the Haminfo
project. All contributors MUST comply with these principles.

**Amendment Process:**
1. Propose amendment via GitHub issue with `constitution` label
2. Discussion period of minimum 7 days
3. Amendment requires maintainer approval
4. Update constitution version following semantic versioning:
   - MAJOR: Principle removal or fundamental redefinition
   - MINOR: New principle added or significant expansion
   - PATCH: Clarification, wording, or non-semantic changes

**Compliance Review:**
- All PRs and code reviews MUST verify compliance with this constitution
- Violations MUST be addressed before merge
- Complexity exceeding these guidelines MUST be justified in PR description

**Exception Process:**
- Exceptions to any rule MUST be documented in PR description
- Exceptions MUST include rationale and mitigation plan
- Exceptions MUST be approved by maintainer

**Version**: 1.0.0 | **Ratified**: 2026-03-09 | **Last Amended**: 2026-03-09
