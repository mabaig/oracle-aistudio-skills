# The ORDS response contract

AI Studio infers nothing about your API's responses. Every `EXTERNAL_REST` node
carries an `outputSpecification`, a JSON schema you write by hand, and
downstream expressions may only reference fields declared there:

> Do not invent response fields in downstream expressions unless they are
> declared in `outputSpecification`.

So the first real task in any ORDS integration is describing what ORDS returns.
That is more varied than people expect, and the generated OpenAPI spec is no
help: its response schemas usually list `items` and omit the envelope.

## ORDS returns three different shapes

Do not assume the envelope. Check each endpoint:
`scripts/ords_openapi.py probe <spec>` classifies every GET for you.

**1. Enveloped collection with links.** The AutoREST default, and what a
handler-based collection query returns unless you override it.

```json
{
  "items": [ { "status": "OPEN", "count": 12 } ],
  "hasMore": false,
  "limit": 25,
  "offset": 0,
  "count": 5,
  "links": [
    { "rel": "self",        "href": "https://<adb-host>/ords/<schema-alias>/<module-base-path>/<template>" },
    { "rel": "describedby", "href": "https://<adb-host>/ords/<schema-alias>/metadata-catalog/<module-base-path>/item" },
    { "rel": "first",       "href": "..." },
    { "rel": "next",        "href": "..." }
  ]
}
```

**2. Enveloped collection without links.** Seen on some handler modules with a
custom SQL source. Same pagination fields, no `links` array, so do not write a
schema that requires `links`.

**3. No envelope at all.** A `GET` handler returning a single composed object
(media or PL/SQL source) gives you exactly what the code produced:

```json
{ "byTotalOpenCase": 42, "byCaseType": [ ], "byTotalLPNHold": 7 }
```

Shape 3 is easy to miss because it appears alongside enveloped endpoints in the
same module. A KPI or dashboard-summary handler almost always returns shape 3.

A single-record template (`tickets/:reference`) backed by a collection query
still returns shape 1, with zero or one item. Guard `items?.[0]` before using it.

## Copy-paste output specifications

[assets/ords-output-specification.json](../assets/ords-output-specification.json)
contains ready schemas for shapes 1 to 3. Replace the `items` element with your
row shape and delete what you do not use.
[assets/example/08-workflow-node.json](../assets/example/08-workflow-node.json)
shows one in place on a node.

Declare only fields you actually consume downstream. An `outputSpecification`
listing 22 columns when the workflow reads 6 is 16 extra fields the LLM must
wade through, and it inflates every recorded test payload.

## Page size is per handler, not "25"

The module default (`p_items_per_page` on `DEFINE_MODULE`) is often 25, but
**each handler can override it**. One real module mixed handler page sizes of
25, 50, 100, 200, 500, 1000 and 5000. Find the real value from the `limit` in a
live response, from `probe`, or from `ITEMS_PER_PAGE` in
[../assets/sql/ords-introspection.sql](../assets/sql/ords-introspection.sql).

Whatever the default, if your workflow assumes it sees everything, it will
silently truncate the moment the table outgrows one page.

**The wrong fix, and it is the common one:**

```
resourcePath: /quality/case-audit?limit=200
```

We shipped that. It works until 201 rows exist, then fails silently and
invisibly, because `hasMore: true` is sitting right there in a response nobody
reads.

**Do this instead.** Make `limit` and `offset` **tokens** so the workflow sets
them and pagination is visible. Tokens are the only parameters an
`EXTERNAL_REST` node can bind; see
[external-rest-endpoints.md](external-rest-endpoints.md).

```json
{
  "name": "listTickets",
  "operationType": "GET",
  "resourcePath": "/tickets?status={status}&limit={limit}&offset={offset}"
}
```

Then declare `hasMore` in `outputSpecification` and act on it:

- Branch on it. A CONDITION node routing to an explicit "results truncated"
  path is honest; a hardcoded `?limit=200` is a hidden ceiling.
- Or, when a CODE node normalises the data, carry a `data_complete` flag and a
  list of truncated sources into every prompt, and instruct the model to say
  the list may be incomplete when the flag is false.

If a single page genuinely is the requirement, say so in the endpoint
description and assert `hasMore === false` in the test. Then growth past the
page size fails loudly instead of quietly returning partial data.

## Pagination and recorded test data

When you record test data for an ORDS node, the recorder may compact an
oversized collection (anything over about 3 KB per node). A compacted or
generated collection is no longer the complete server response, and the harness
enforces that:

> testData node &lt;NODE&gt; compacted/generated collection response must set
> hasMore to false.

This is correct behaviour, not an obstacle. A compacted fixture that claims
`hasMore: true` would assert a next page that does not exist in the fixture. So:

- Keep 2–5 representative rows, trimming **fields** before dropping rows.
- Set `hasMore: false`.
- Adjust `count`, `limit` and `offset` to match the compacted set. An envelope
  claiming `count: 5000` above 3 rows will confuse any LLM node reading it.
- Mark the node `capture.mode = "model-compacted"` and
  `capture.responseTruncated: true`.

## Grounding: shape the payload for the model, not the database

ORDS rows come straight from your table, which usually means audit columns,
surrogate keys and duplicated denormalised fields. Every one of them is
tokens spent and a chance for the model to cite something meaningless.

A real row we shipped carried 22 columns including `created_by`,
`last_updated_by`, `last_updated_date`, `source_application`, `error_msg`, both
`case_type_id` and `case_type_name`, and a `total_results` window-function
column repeated on every row.

Trim at the ORDS layer, not in the workflow. A handler module selecting the
eight columns the agent actually needs is cheaper, faster and easier to ground
than a `SELECT *` AutoREST endpoint plus a downstream transform. **The best
place to fix an agentic payload is the SQL.**

When you cannot change the SQL, put one CODE node after the shared fetches that:

- groups line-grain rows into the entity the user thinks in (order, ticket, pick
  slip), keeping the keys needed for write-backs
- drops audit columns and duplicates
- excludes non-person accounts (role or placeholder users synced into a users
  table) from anything the agent might recommend
- ranks by an explicit rule when the rule is mechanical (due date, then
  priority) and leaves judgement to the LLM

Unit-test that node locally against real responses with
[../scripts/code_node_harness.mjs](../scripts/code_node_harness.mjs) before
saving the workflow.

## Checklist

- [ ] Identified which of the three shapes each endpoint returns (`probe`)
- [ ] `outputSpecification` declares only consumed fields plus the envelope
- [ ] Real page size known per handler; `limit` / `offset` are tokens, not baked into `resourcePath`
- [ ] `hasMore` is declared and handled, or asserted false with a stated reason
- [ ] Compacted fixtures set `hasMore: false` with a consistent envelope
- [ ] Row shape trimmed in SQL, or in one tested CODE node, not across the workflow
