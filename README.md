# Oracle AI Studio skills for Claude Code

Skills for building on the Oracle Fusion AI Studio ecosystem.

## `aistudio-ords` — ORDS → Fusion agentic apps

Oracle partners and SIs have spent years building ORDS modules on ATP to feed
APEX and VBCS. Fusion AI Studio is new, and there is no documented path from
that existing estate to an agentic app.

This skill supplies what AI Studio does not ship: which of three REST paths to
take, how authentication actually works against ORDS on ATP, how to model the
`items` / `hasMore` / `count` / `links` envelope into a workflow node, and how
to regression-test the result.

It performs no artifact operations. Every create, validate and save is delegated
to Oracle's own bundled `aistudio` skill, which stays the authority on commands
and schemas.

### Install

```
/plugin marketplace add mabaig/oracle-aistudio-skills
/plugin install aistudio-ords@oracle-aistudio
```

Then just describe what you want — "connect my ORDS tickets module to a
workflow" — and the skill loads.

### What it covers

| | |
|---|---|
| **Choosing a path** | External REST vs Connector vs `NonFusionOracleSource`, and why the deciding factor is almost always credentials |
| **Auth on ATP** | The CLI cannot write auth into an External REST tool. What that means and both routes around it |
| **Response contract** | ORDS returns three different shapes. Assuming the envelope is a real bug |
| **Spec handling** | The hardcoded OpenAPI 3.0 constraint, and why to import a module spec rather than a whole AutoREST schema |
| **URLs and catalogs** | URL anatomy, splitting instance URL from resource path, `:name` → `{name}`, fetching a module's OpenAPI document (with or without a token), filters and paging |
| **Diagnosing** | A curl-first triage ladder, what `401`/`403`/`404`/`405`/`503`/`555` mean from ORDS, and why the `.tool` file can't prove auth |
| **Agent safety** | Read/write tool split, confirmation gates in the workflow graph, safe write handlers, failure isolation |
| **ORDS setup SQL** | Inventory queries on `USER_ORDS_*`, privileges, roles and OAuth client samples |
| **Testing** | Record at the ORDS boundary, replay from file, assert the path, cover the empty collection, keep a live smoke run |
| **Walkthrough** | Every step, end to end, on the sample service-desk module |

### Helper script

`scripts/ords_catalog.py` (Python 3, standard library only, never prints secrets)
lists the modules in an ORDS OpenAPI catalog, downloads a module's spec, turns it
into draft AI Studio endpoint blocks, subsets it for Connector import, and checks
any endpoint's status and envelope shape:

```bash
S=plugins/aistudio-ords/skills/aistudio-ords-integration/scripts/ords_catalog.py
BASE="https://<host>/ords/<schema-alias>"
python3 $S modules   --base "$BASE"
python3 $S spec      --base "$BASE" --module <module> -o module-openapi.json
python3 $S endpoints module-openapi.json -o endpoints.json
python3 $S check     --base "$BASE" --path /<module>/<template> --auth client-credentials
```

### Things you will hit

- **Authentication cannot be scripted on the External REST path.** The CLI
  forces `authInfo.type = "none"` and rejects credential fields. Sound secret
  hygiene — but an authenticated External REST tool always needs a human in the
  UI, on every environment.
- **ORDS pages at 25 rows.** Baking `?limit=200` into the resource path is the
  popular fix and it fails silently at row 201.
- **Not every ORDS response is enveloped.** Summary and KPI handlers return a
  bare object, often beside enveloped endpoints in the same module.
- **The `.tool` file can't prove auth works.** A tool authenticated in the UI can
  still read `authInfo.type: "none"`; only a live call proves it.
- **An agent is offered every endpoint of an attached tool** — including the
  writes. Split read and write tools and gate writes in the workflow graph.
- **Green replayed tests, empty app.** Keep one live smoke run per deploy.

### Worked example

A service-desk module — DDL, ORDS handlers, sample responses, a sample OpenAPI
document, tool endpoints — small enough to run from zero on a clean pod, and
deliberately exercising all three response shapes. The walkthrough reference
takes it through every step.

## Tested against

| | |
|---|---|
| AI Studio CLI | `1.0.1785996600989` |
| Repo | [`oracle/fusion-ai-studio`](https://github.com/oracle/fusion-ai-studio) branch `release-26C` |
| Verified | September 2026 |

Oracle ships monthly. This skill deliberately avoids restating command
signatures — it delegates those to the bundled `aistudio` skill — so it should
survive routine drops. If something has moved, open an issue with the CLI
version from `aistudio version`.

## Contributing

Issues and PRs welcome. Two rules: no credentials, hostnames or customer data in
any example, and never restate an `aistudio` command signature this skill can
delegate instead.

## License

Universal Permissive License v1.0. See [LICENSE](LICENSE).
