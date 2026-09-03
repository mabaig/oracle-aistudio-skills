# The ORDS response contract

AI Studio infers nothing about your API's responses. Every `EXTERNAL_REST` node
carries an `outputSpecification` — a JSON schema you write by hand — and
downstream expressions may only reference fields declared there:

> Do not invent response fields in downstream expressions unless they are
> declared in `outputSpecification`.

So the first real task in any ORDS integration is describing what ORDS returns.
That is more varied than people expect.

## ORDS returns three different shapes

Do not assume the envelope. Check each endpoint.

**1. Enveloped collection with links** — the AutoREST default, and what a
handler-based module returns unless you override it.

```json
{
  "items": [ { "status": "OPEN", "count": 12 } ],
  "hasMore": false,
  "limit": 25,
  "offset": 0,
  "count": 5,
  "links": [
    { "rel": "self",        "href": "https://<host>/ords/<schema>/<module>/<template>" },
    { "rel": "describedby", "href": "https://<host>/ords/<schema>/metadata-catalog/<module>/item" },
    { "rel": "first",       "href": "..." },
    { "rel": "next",        "href": "..." }
  ]
}
```

**2. Enveloped collection without links.** Common on handler modules with a
custom SQL source. Same pagination fields, no `links` array — so do not write a
schema that requires `links`.

**3. No envelope at all.** A `GET` handler returning a single composed object
gives you exactly what the SQL produced:

```json
{ "byTotalOpenCase": 42, "byCaseType": [ ], "byTotalLPNHold": 7 }
```

Shape 3 is easy to miss because it appears alongside enveloped endpoints in the
same module. A KPI or dashboard-summary handler almost always returns shape 3.

## Copy-paste output specifications

[assets/ords-output-specification.json](../assets/ords-output-specification.json)
contains ready schemas for shapes 1 and 2. Replace the `items` element with
your row shape and delete what you do not use.

Declare only fields you actually consume downstream. An `outputSpecification`
listing 22 columns when the workflow reads 6 is 16 extra fields the LLM must
wade through, and it inflates every recorded test payload.

## `limit` is 25 until you say otherwise

ORDS defaults to **25 rows**. If your workflow assumes it sees everything, it
will silently truncate at 25 the moment the table grows.

**The wrong fix — and it is the common one:**

```
resourcePath: /quality/case-audit?limit=200
```

We shipped that. It works until 201 rows exist, then fails silently and
invisibly, because `hasMore: true` is sitting right there in a response nobody
reads.

**Do this instead.** Expose `limit` and `offset` as real parameter definitions
so pagination is visible in the workflow:

```json
{
  "name": "listTickets",
  "operationType": "GET",
  "resourcePath": "/tickets",
  "parameterDefinitions": [
    { "name": "limit",  "dataType": "number", "isToken": false },
    { "name": "offset", "dataType": "number", "isToken": false }
  ]
}
```

Then declare `hasMore` in `outputSpecification` and branch on it — a CONDITION
node routing to an explicit "results truncated" path is honest; a hardcoded
`?limit=200` is a hidden ceiling.

If a single page genuinely is the requirement, say so in the endpoint
description and assert `hasMore === false` in the test. Then a future growth
past the page size fails loudly instead of quietly returning partial data.

## Pagination and recorded test data

When you record test data for an ORDS node, the recorder may compact an
oversized collection. A compacted or generated collection is no longer the
complete server response, and the harness enforces that:

> testData node &lt;NODE&gt; compacted/generated collection response must set
> hasMore to false.

This is correct behaviour, not an obstacle. A compacted fixture that claims
`hasMore: true` would assert a next page that does not exist in the fixture. So:

- Keep 2–5 representative rows, trimming **fields** before dropping rows.
- Set `hasMore: false`.
- Adjust `count`, `limit` and `offset` to match the compacted set — an envelope
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

## Checklist

- [ ] Identified which of the three shapes each endpoint returns
- [ ] `outputSpecification` declares only consumed fields
- [ ] `limit` / `offset` are parameters, not baked into `resourcePath`
- [ ] `hasMore` is declared and handled, or asserted false with a stated reason
- [ ] Compacted fixtures set `hasMore: false` with a consistent envelope
- [ ] Row shape trimmed in SQL, not in the workflow
