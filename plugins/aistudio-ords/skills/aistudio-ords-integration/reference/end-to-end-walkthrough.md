# End-to-end walkthrough (sample)

A worked run of the six steps in `SKILL.md`, using the service-desk example in
[assets/example/](../assets/example/). Every host, schema, module and client
name is a placeholder — substitute your own.

AI Studio command names appear as signposts only. Before running any of them,
read the current base `aistudio` skill for the exact flags and file layout; it
is the authority and it changes monthly.

```bash
# Placeholders used throughout
export BASE="https://<host>/ords/<schema-alias>"     # instance URL: host + /ords + schema alias
export H=plugins/aistudio-ords/skills/aistudio-ords-integration
```

---

## Step 0 · Prerequisites

- An ORDS-enabled schema on your database, and its **schema alias** (see
  [ords-url-and-catalog.md](ords-url-and-catalog.md)).
- Network reachability from your machine to `$BASE` (for testing) and from the
  Fusion environment to `$BASE` (for runtime).
- The AI Studio CLI authenticated against the Fusion environment you intend to
  change. Confirm the user and environment first — artifacts and ids are
  per environment.
- Python 3 for `scripts/ords_catalog.py`.

## Step 1 · Build the ORDS side and inventory it

Run [01-schema.sql](../assets/example/01-schema.sql) and
[02-ords-module.sql](../assets/example/02-ords-module.sql) as the schema owner.
On an existing estate, skip creation and run the inventory queries in
[ords-setup-sql.md](ords-setup-sql.md) instead.

Prove each endpoint from a shell before touching AI Studio:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/metadata-catalog/"          # 200 = schema reachable
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets/TKT-1001
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/summary
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path "/servicedesk/tickets?status=ARCHIVED"
```

Record the result as an inventory table:

| Endpoint | Method | Auth | Shape | Rows | Agent may call? |
|---|---|---|---|---|---|
| `/servicedesk/tickets` | GET | none | enveloped, with links | paged, 25 per page | yes |
| `/servicedesk/tickets/{reference}` | GET | none | enveloped, one item | 0–1 | yes |
| `/servicedesk/summary` | GET | none | **bare object** | 1 | yes |

## Step 2 · Choose the path

All three endpoints are read-only and open, and there are fewer than 15 of
them, so **External REST** is the least work
([choosing-a-path.md](choosing-a-path.md)). If you protect the module (step 3),
the choice is still External REST plus a UI step, or Connector if you want the
setup reproducible from source.

## Step 3 · Settle authentication (optional for the sample)

To practise the credentialed flow, protect the module and register a client
with the samples in [ords-setup-sql.md](ords-setup-sql.md) (sections 2 and 3),
then prove it:

```bash
# export ORDS_CLIENT_ID / ORDS_CLIENT_SECRET from your secret manager first
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets                         # expect 401
python3 $H/scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets --auth client-credentials # expect 200
```

Decide now how AI Studio will authenticate: [auth-on-atp.md](auth-on-atp.md).

## Step 4 · Get the spec and create the tool

Fetch the module's OpenAPI document and generate endpoint blocks:

```bash
python3 $H/scripts/ords_catalog.py modules   --base "$BASE"            # add --auth client-credentials if protected
python3 $H/scripts/ords_catalog.py spec      --base "$BASE" --module servicedesk -o servicedesk-openapi.json
python3 $H/scripts/ords_catalog.py endpoints servicedesk-openapi.json -o endpoints.json
```

Review `endpoints.json` against the curated
[04-tool-endpoints.json](../assets/example/04-tool-endpoints.json):

- descriptions written for the agent (what the endpoint returns and when to use it)
- resource paths start with the module base path, with `{name}` tokens
- `limit` and `offset` on collection endpoints only
- write endpoints (none in the sample) moved to a separate tool

Then hand off to the base `aistudio` skill:

1. `do-create-tool` with the External REST tool type, the instance URL `$BASE`,
   the endpoint blocks, and a family and product.
2. `validate-tool` — fix everything it reports.
3. `do-save-tool` — only when you intend to persist to the environment.
4. **If the module is protected:** add OAuth2 client credentials to the tool in
   the AI Studio UI, with token URL `$BASE/oauth/token`.

On the **Connector** path instead: `subset` the spec to the paths you need,
then follow Route B in [auth-on-atp.md](auth-on-atp.md).

## Step 5 · Wire the workflow

Hand off to `aistudio` for workflow creation. Design:

```
START
 ├─ FETCH_TICKETS  (EXTERNAL_REST → listTickets, limit 25, offset 0)
 ├─ FETCH_SUMMARY  (EXTERNAL_REST → getSummary)
 ├─ HAS_TICKETS    (CONDITION on the tickets items) ──false──▶ NO_TICKETS (RETURN)
 └─ STAGE_ROUTER   (SWITCH on the app message hint)
       ├─ InitDisplay ─▶ LLM   (card from summary + list from tickets)
       ├─ Query       ─▶ AGENT (read tool attached, for lookups by reference)
       └─ Summary     ─▶ LLM
```

For each `EXTERNAL_REST` node, write the `outputSpecification` by hand from
[assets/ords-output-specification.json](../assets/ords-output-specification.json):

- `FETCH_TICKETS` → **enveloped collection**, declare `items`, `hasMore`, `count`
  and only the row fields the prompts use.
- `FETCH_SUMMARY` → **bare object**, declare `openCount`, `highCount`,
  `unassigned` directly. No `items`.

Wrap the injected ORDS data in a labelled DATA section and mark it as untrusted
data in the system prompt ([agent-safety-and-resilience.md](agent-safety-and-resilience.md)).
Run `validate-workflow` before saving.

## Step 6 · Test, then prove it live

1. **Record and replay** ([testing-ords-workflows.md](testing-ords-workflows.md)):
   record the ORDS nodes once, compact to a few rows with `hasMore: false`,
   replay from file, and assert the path.
2. **Cover the empty collection:** the `status=ARCHIVED` response drives the
   `NO_TICKETS` branch.
3. **Live smoke run:** run the workflow once against live data and read each
   ORDS node's status in the trace. A `401` here with green replayed tests means
   authentication is missing on this environment
   ([diagnosing-ords.md](diagnosing-ords.md)).

## Step 7 · Put it in an app (optional)

Hand off to `aistudio` for the app. Point one panel at the workflow, keep the
display prompt aligned with the `InitDisplay` stage, and add priority actions
only if a real next step exists. If the app runs published workflows, publish
after every workflow change; otherwise use the app's draft-while-developing
option during development.

## Step 8 · Promote to another environment

- Re-create or import the tool, workflow and app; ids do not carry over.
- Repeat the UI authentication step on the new environment.
- Run the live smoke run on the new environment before telling anyone it works.

## Done when

- [ ] Every endpoint proved from a shell with the same credentials AI Studio uses
- [ ] Tool validated; UI auth (if any) proved by a live call
- [ ] Each ORDS node's `outputSpecification` matches its real shape
- [ ] Replay tests pass, the empty-collection branch is covered, and a live smoke run is clean
- [ ] Promotion steps, including manual auth steps, written down per environment
