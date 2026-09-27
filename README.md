# Oracle AI Studio skills for Claude Code

Skills for building on the Oracle Fusion AI Studio ecosystem.

## `aistudio-ords`: ORDS → Fusion agentic apps

Oracle partners and SIs have spent years building ORDS modules on ATP to feed
APEX and VBCS. Fusion AI Studio is new, and there is no documented path from
that existing estate to an agentic app.

This skill supplies what AI Studio does not ship:

- how to find and read an ORDS API through its OpenAPI catalog
- which of three REST paths to take
- how authentication actually works against ORDS on ATP
- how to author endpoints and model the `items` / `hasMore` / `count` / `links` envelope
- how to write back to ORDS safely from app actions
- how to regression-test the result

It performs no artifact operations. Every create, validate, save and test is
delegated to Oracle's own bundled `aistudio` skill, which stays the authority
on commands and schemas.

### Prerequisites

1. **Oracle's base `aistudio` skill**, which is not in any Claude Code
   marketplace. Get `aistudio-skill.zip` from
   [`oracle/fusion-ai-studio`](https://github.com/oracle/fusion-ai-studio)
   (`<release>/aistudio/bin/`), verify its `.sha256`, and unzip it into your
   project's **`.claude/skills/`**. Claude Code does not read Oracle's
   documented `.agents/skills/` location.
2. An `env.properties` for your Fusion pod, from AI Studio → Credentials → AI
   Studio CLI, and a successful `authenticate` / `whoami`.
3. Python 3.8+ and Node 18+ for the bundled helper scripts. They use only the
   standard library.

Full steps and the preflight probes are in
[`reference/setup-and-preflight.md`](plugins/aistudio-ords/skills/aistudio-ords-integration/reference/setup-and-preflight.md).

### Install

```
/plugin marketplace add mabaig/oracle-aistudio-skills
/plugin install aistudio-ords@oracle-aistudio
```

Then describe what you want, for example "build an agentic app on my ORDS
module at `https://<adb-host>/ords/<schema-alias>/open-api-catalog/`", and the
skill loads.

### Quick start: find your ORDS API

Every ORDS URL on Autonomous Database has the same anatomy:

```
https://<adb-host>/ords/<schema-alias>/<module-base-path>/<template-pattern>
https://<adb-host>/ords/<schema-alias>/open-api-catalog/                     ← index of modules
https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/  ← one module's OpenAPI 3.0 spec
https://<adb-host>/ords/<schema-alias>/oauth/token                           ← OAuth2 client credentials
```

The schema alias is `ORDS.ENABLE_SCHEMA`'s `p_url_mapping_pattern`, and the base
path is `ORDS.DEFINE_MODULE`'s `p_base_path`. Neither is necessarily the schema
or module name. The bundled helper does the rest:

```bash
S=<skill-dir>/scripts
python3 $S/ords_openapi.py catalog   --host <adb-host> --alias <schema-alias>
python3 $S/ords_openapi.py inventory https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/
ORDS_CLIENT_ID=... ORDS_CLIENT_SECRET=... \
python3 $S/ords_openapi.py probe     https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/
python3 $S/ords_openapi.py subset    module-spec.json --keep "GET /tickets" --keep "POST /tickets/assign" \
                                     --security OAuth2:clientCredentials -o agent-spec.json
```

### What it covers

| | |
|---|---|
| **Setup & preflight** | Installing the base skill for Claude Code, pod config, and probing connector/KM access before choosing a path |
| **ORDS discovery** | URL anatomy, the OpenAPI catalog, token exchange, handler-source introspection, and what the generated spec gets wrong |
| **Choosing a path** | External REST vs Connector vs `NonFusionOracleSource`, decided by credentials and connector access |
| **Auth on ATP** | The CLI cannot write auth into an External REST tool; both routes around it, dedicated OAuth clients, secret hygiene |
| **External REST endpoints** | Tokens as the workflow contract, empty-means-NULL filters, PL/SQL bodies, header params, save-before-UI-auth |
| **Spec handling** | OpenAPI 3.0 only, subset and enrich before Connector import |
| **Response contract** | Three response shapes, per-handler page sizes, `hasMore`, trimming for grounding |
| **Write-back actions** | App action → re-validate → write → report, and handlers that return real counts |
| **Testing** | Recording preconditions, reading recorder failures, InitDisplay baseline, empty collections, live writes |

### Things you will hit

- **Authentication cannot be scripted on the External REST path.** The CLI
  forces `authInfo.type = "none"`. An authenticated tool needs a human in the
  UI, after the tool is saved, on every environment. Until then, calls get
  ORDS's HTML 401 page, which the test recorder reports as a "truncated
  preview".
- **Connector access is a separate permission.** Workflow commands can work
  while connector APIs return `401`, because of a missing IDCS scope or role.
  Probe first.
- **The generated spec lies about PL/SQL bodies.** `{ "body_text": string }` is
  a placeholder; the real contract is in the handler source.
- **Page size is per handler, not 25.** Baking `?limit=200` into the path fails
  silently at row 201. Make `limit` / `offset` tokens and handle `hasMore`.
- **Not every ORDS response is enveloped.** Summary and KPI handlers return a
  bare object, often beside enveloped endpoints in the same module.

### Worked example

A service-desk module small enough to run from zero on a clean pod:

- DDL and ORDS handlers covering all three response shapes, plus sample responses
- SQL to protect the module with OAuth2
- a write handler that reports honestly
- the enriched agent OpenAPI spec
- token-based External REST endpoints
- a normalised workflow node

## Tested against

| | |
|---|---|
| AI Studio CLI | `1.0.1785996600989` |
| Repo | [`oracle/fusion-ai-studio`](https://github.com/oracle/fusion-ai-studio) branch `release-26C` |
| Verified | September 2026 |

Oracle ships monthly. This skill deliberately avoids restating command
signatures and delegates those to the bundled `aistudio` skill, so it should
survive routine drops. If something has moved, open an issue with the CLI
version from `aistudio version`.

See [CHANGELOG.md](CHANGELOG.md) for what changed between versions.

## Contributing

Issues and PRs welcome. Two rules: no credentials, hostnames or customer data in
any example, and never restate an `aistudio` command signature this skill can
delegate instead.

## License

Universal Permissive License v1.0. See [LICENSE](LICENSE).
