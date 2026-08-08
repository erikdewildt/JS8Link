# JS8Link contribution rules

These instructions apply to the entire repository.

## Versioning

- JS8Link uses Semantic Versioning (`MAJOR.MINOR.PATCH`). The canonical version is stored in
  `VERSION`.
- Keep `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, and the root package
  entries in `frontend/package-lock.json` synchronized with `VERSION`.
- Use `just version-set <version>` to change the project version; do not edit individual version
  fields independently.
- Increment `PATCH` for backward-compatible bug fixes and `MINOR` for backward-compatible
  features. Increment `MAJOR` for incompatible public API, configuration, protocol, or database
  behavior after version 1.0. Before 1.0, use a minor increment for incompatible changes and a
  patch increment for compatible fixes.
- Do not bump the version for documentation-only, test-only, formatting, or internal refactoring
  changes unless they are part of a release.
- Git release tags use the form `vMAJOR.MINOR.PATCH` and must match `VERSION` exactly.

## Changelog

- Every user-visible feature and every bug fix must update `CHANGELOG.md` in the same change.
- Add new entries under `## [Unreleased]` using the categories `Added`, `Changed`, `Deprecated`,
  `Removed`, `Fixed`, or `Security`.
- Describe user impact in concise language; do not use commit hashes or implementation-only detail.
- Mention database migrations, API changes, configuration changes, installer changes, and protocol
  changes only when they have a user-visible effect. Do not include test changes, refactors,
  maintenance tooling, formatting, or other implementation details.
- When releasing, move the relevant Unreleased entries into a new
  `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD` section, update comparison links, and restore an empty
  `Unreleased` section.

## Pydantic

- Every API endpoint that accepts a request body **must** use a Pydantic `BaseModel` for
  validation. Raw `dict[str, Any]` or `dict[str, str]` parameters are not allowed for request
  bodies.
- Every API endpoint that returns data to the frontend **should** declare a `response_model`
  for automatic OpenAPI schema generation and response validation.
- All Pydantic models live in `backend/src/js8link/schemas.py`. Do not define models inline
  in endpoint functions.
- Domain-logic modules (`backend/src/js8link/domain/`) may use `@dataclass` for internal data
  structures; Pydantic is only required at the API boundary.
- External message formats (JS8Call TCP JSON) are parsed as raw `dict[str, Any]` — Pydantic
  is not required for these, but the parsed data should be converted to a Pydantic model
  before passing it to other parts of the application.
- The `EventEnvelope` model must be used for all WebSocket event payloads. Manual
  construction of `{"event": ..., "data": ..., "timestamp": ...}` dicts is not allowed.

## JS8Call protocol

- Before implementing or changing any behavior involving JS8Call messages, events, API calls,
  parsing, interpretation, persistence, transmission, or related UI, consult and follow
  `docs/design/js8call-protocol.md`.
- Treat `docs/design/js8call-protocol.md` as the repository's protocol reference. If the
  implementation or external JS8Call documentation reveals a discrepancy, update the protocol
  document and add or update tests before changing dependent behavior.
- Keep the distinction between raw JS8Call data, protocol interpretation, and application-level
  meaning explicit. Do not infer sender, recipient, heartbeat direction, SNR direction, or message
  type from UI assumptions alone.

## Verification

- Run `just test` after every code or configuration change.
- `just test` runs `just version-check`, backend pytest, frontend Vitest unit tests, and Playwright
  E2E tests. `just check` runs the complete lint, format, typecheck, and version validation layer.
  Resolve failures in both before considering a change complete.

## Help and tooltips

- Every new or changed user-facing feature must add or update the matching topic in both
  `backend/src/js8link/help/nl.json` and `backend/src/js8link/help/en.json`.
- New icon-only or compact controls must have a short keyboard-accessible tooltip and a context
  help entry when the control needs more than one sentence of explanation.
- When a screen changes materially, review its help context and regenerate or update its local
  screenshot asset.
- Help content must remain available offline; use local screenshots and local documentation links
  where possible, while keeping official external references clearly marked.
- New help content requires backend contract tests, Vitest coverage for context or rendering logic,
  and a Playwright flow covering opening, navigation, language behavior, and closing the drawer.

## Testing requirements

- Every backend behavior change must add or update pytest coverage for the affected domain logic,
  API validation, response contract, persistence behavior, or integration boundary.
- Every frontend behavior change must add or update a Vitest test for affected pure logic or
  component behavior. Keep reusable display, parsing, filtering, and validation logic in modules
  that can be tested without a browser.
- Every user-visible workflow change must add or update a Playwright E2E scenario. E2E tests live
  in `frontend/e2e/` and must cover the workflow through the rendered UI, including the relevant
  API interaction and resulting state.
- Maintain the core E2E smoke coverage for setup completion, navigation, chat creation, offset
  Auto/Vast selection, settings tabs, monitor filters, theme/language changes, and message
  sending. Add regression coverage for every reported browser bug.
- E2E tests must mock external JS8Call/API state at the network boundary and must not require a
  running radio or access to an external service. Use the local Vite web server and Playwright's
  trace/screenshot artifacts for failures.
- Install the browser locally with `cd frontend && npx playwright install chromium` when setting up
  a new development environment. Run focused layers with `just frontend-unit` or `just frontend-e2e`,
  but use `just test` before handoff.
