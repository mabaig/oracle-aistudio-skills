# Changelog

## 0.2.0: robustness pass from a full end-to-end build

Everything below came from building an agentic app on a real, OAuth-protected
ORDS module, from an empty folder to drafts on a pod, and writing down each
place the 0.1.0 skill left the builder stuck or wrong.

### Added

- **`reference/setup-and-preflight.md`**
  - How to obtain, checksum and install Oracle's base `aistudio` skill for
    Claude Code (`.claude/skills/`, not `.agents/skills/`)
  - `env.properties` and `whoami`
  - Read-only probes that catch a connector/KM `401` (missing IDCS Boss Cloud
    scope or connector role) before a path is chosen
- **`reference/ords-discovery.md`**
  - ORDS URL anatomy (ADB host, schema alias, module base path, template)
  - The `open-api-catalog` index and per-module spec URLs, and token exchange
  - Handler-source introspection
  - A table of what the ORDS-generated spec gets wrong
- **`reference/external-rest-endpoints.md`**
  - Tokens are the only values a workflow node can bind
  - Query filters as tokens; empty values bind as NULL
  - PL/SQL `bodyTemplate`s, array tokens, header-bound params, `DELETE` bodies
  - Save the tool before adding UI auth
- **`reference/write-back-actions.md`**
  - The app action → InvokeAction → re-validate → write → merge → report pattern
  - Handler patterns that make agents misreport results
  - Live write recordings
- **`scripts/ords_openapi.py`**: `catalog`, `inventory` (flags placeholder
  bodies, missing operationIds, implicit/header params, undeclared envelopes),
  `probe` (real shapes and per-handler page sizes) and `subset` (agent-sized,
  `$ref`-validated spec, one security scheme). Standard library only;
  credentials from env vars only.
- **`scripts/code_node_harness.mjs`**: run a workflow's CODE nodes locally
  against recorded ORDS JSON.
- **`assets/sql/ords-introspection.sql`** and
  **`assets/sql/create-oauth-client.sql`** (dedicated AI Studio client).
- **Example files `05`–`08`**: module protection, a truthful write handler, the
  enriched agent OpenAPI spec, and a normalised `EXTERNAL_REST` node.
- A generic **sample session** in `SKILL.md`.

### Changed

- **Catalog URL corrected.** Per-module specs live at
  `open-api-catalog/<module-base-path>/`, not `<module>/`.
- **"ORDS pages at 25" replaced.** Page size is per handler; one real module
  ranged from 25 to 5000.
- **Endpoint template and example endpoints** now use `{tokens}` in
  `resourcePath` instead of `isToken: false` parameter definitions, which a
  workflow node cannot bind. `04-tool-endpoints.json` is verified to be
  accepted by the CLI unchanged.
- **Auth reference.** Adds curl verification, the HTML-401 recording symptom,
  connector-scope troubleshooting, dedicated clients and secret hygiene.
- **Testing reference.** Adds recording preconditions, a table for reading
  recorder failures, the InitDisplay-baseline and panel-discriminator
  behaviour, and a warning that write recordings are real.
- **`SKILL.md`** now has a seven-step method (with a preflight step 0), links
  to every new reference and script, and an expanded list of catch-outs. The
  claim that the example contained a trimmed spec and workflow node is now true.

## 0.1.0

Initial release: path choice, auth on ATP, response contract, spec handling,
testing, and the service-desk example.
