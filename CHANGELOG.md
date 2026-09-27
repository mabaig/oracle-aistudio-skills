# Changelog

## 0.2.0 — 2026-09-27

### Added
- `reference/ords-url-and-catalog.md` — ORDS URL anatomy, mapping to an External REST
  tool's instance URL and resource paths (`:name` → `{name}`), the OpenAPI and
  metadata catalogs, fetching a protected module's spec with a token, filtering
  and paging.
- `reference/diagnosing-ords.md` — curl-first triage ladder, ORDS status codes
  (including `555`), proving tool auth with a live call, the green-tests-empty-app
  trap, failure isolation, per-environment differences.
- `reference/agent-safety-and-resilience.md` — read/write tool split, confirmation
  gates in the workflow graph, safe write handlers, containing failures.
- `reference/ords-setup-sql.md` — `USER_ORDS_*` inventory queries, role and
  privilege samples, OAuth2 client registration, rotation.
- `reference/end-to-end-walkthrough.md` — every step on the sample module.
- `scripts/ords_catalog.py` — stdlib-only helper: `modules`, `spec`, `endpoints`,
  `subset`, `check`, with client-credentials or bearer-token auth from the environment.
- `assets/example/05-openapi-module.json` — sample module OpenAPI document.

### Changed
- `SKILL.md` — "Where to start" table, step 0, inventory and URL guidance, four new
  pitfalls, helper script section.
- `auth-on-atp.md`, `spec-handling.md`, `choosing-a-path.md`,
  `testing-ords-workflows.md` — cross-links, live verification, read/write split,
  live smoke run.
- `ords-response-contract.md` — examples made generic.

### Fixed
- Endpoint blocks in `assets/ords-endpoint-template.json` and
  `assets/example/04-tool-endpoints.json` now include the module base path
  (`/servicedesk/...`) and use the module's real path parameter (`{reference}`);
  added the `getSummary` bare-object endpoint.

## 0.1.0

- Initial release: path selection, ATP authentication, response envelope, spec
  handling, testing, service-desk worked example.
