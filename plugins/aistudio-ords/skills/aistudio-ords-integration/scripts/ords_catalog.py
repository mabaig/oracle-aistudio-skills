#!/usr/bin/env python3
"""ORDS catalog helper for Fusion AI Studio integrations.

Standard library only. Never prints credentials or tokens.

Commands
  modules    List modules and objects published in <base>/open-api-catalog/
  spec       Download one module's OpenAPI document and report its dialect
  endpoints  Turn an OpenAPI document into AI Studio External REST endpoint blocks
  subset     Keep only selected paths (plus the components they reference)
  check      Call one endpoint and report status, envelope shape and paging

<base> is https://<host>/ords/<schema-alias>  (no trailing slash)

Authentication for network commands (optional)
  --auth client-credentials   token from <base>/oauth/token using the
                              ORDS_CLIENT_ID and ORDS_CLIENT_SECRET env vars
  --bearer-env NAME           read an existing bearer token from env var NAME

Examples
  python3 ords_catalog.py modules   --base "$BASE"
  python3 ords_catalog.py spec      --base "$BASE" --module servicedesk -o servicedesk-openapi.json
  python3 ords_catalog.py endpoints servicedesk-openapi.json -o endpoints.json
  python3 ords_catalog.py subset    servicedesk-openapi.json --paths /servicedesk/tickets -o trimmed.json
  python3 ords_catalog.py check     --base "$BASE" --path /servicedesk/tickets --auth client-credentials
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


# --------------------------------------------------------------------------- http
def _die(msg, code=1):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def _token(args):
    """Return a bearer token or None. The token is never printed."""
    if getattr(args, "bearer_env", None):
        tok = os.environ.get(args.bearer_env)
        if not tok:
            _die("environment variable %s is empty or not set" % args.bearer_env)
        return tok
    if getattr(args, "auth", None) == "client-credentials":
        cid, secret = os.environ.get("ORDS_CLIENT_ID"), os.environ.get("ORDS_CLIENT_SECRET")
        if not cid or not secret:
            _die("set ORDS_CLIENT_ID and ORDS_CLIENT_SECRET in the environment")
        basic = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
        req = urllib.request.Request(
            args.base.rstrip("/") + "/oauth/token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": "Basic " + basic,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            _die("token request returned HTTP %s (check the client id and secret, and the schema alias)" % e.code)
        except urllib.error.URLError as e:
            _die("token request failed: %s" % e.reason)
        tok = body.get("access_token")
        if not tok:
            _die("token response did not contain access_token")
        print("token acquired (expires_in=%s)" % body.get("expires_in"), file=sys.stderr)
        return tok
    return None


def _get(url, token=None):
    """GET url; return (status, parsed_json_or_text)."""
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            status, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        _die("request failed: %s" % e.reason)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def _explain(status):
    return {
        400: "bad request - malformed filter, bind or body",
        401: "unauthorised - missing or rejected credentials (see reference/diagnosing-ords.md)",
        403: "forbidden - authenticated but lacks the privilege for this pattern",
        404: "not found - wrong schema alias, module base path or template, or unpublished",
        405: "method not allowed - no handler for this method",
        503: "service unavailable - database stopped or connection pool exhausted",
        555: "user-defined resource error - the handler SQL/PL/SQL raised an exception",
    }.get(status, "")


# ----------------------------------------------------------------------- commands
def cmd_modules(args):
    status, body = _get(args.base.rstrip("/") + "/open-api-catalog/", _token(args))
    if status != 200:
        _die("HTTP %s %s" % (status, _explain(status)))
    items = body.get("items", []) if isinstance(body, dict) else []
    if not items:
        print("catalog returned no items (nothing published, or protected modules hidden from this caller)")
        return
    for it in items:
        name = it.get("name") or it.get("title") or "?"
        hrefs = [l.get("href") for l in it.get("links", []) if l.get("href")]
        print("%-40s %s" % (name, hrefs[0] if hrefs else ""))


def cmd_spec(args):
    url = "%s/open-api-catalog/%s/" % (args.base.rstrip("/"), args.module.strip("/"))
    status, body = _get(url, _token(args))
    if status != 200 or not isinstance(body, dict):
        _die("HTTP %s %s" % (status, _explain(status)))
    dialect = body.get("openapi") or ("swagger " + str(body.get("swagger")) if body.get("swagger") else "unknown")
    with open(args.output, "w") as f:
        json.dump(body, f, indent=2)
    print("saved %s  dialect=%s  paths=%d" % (args.output, dialect, len(body.get("paths", {}))))
    if not str(dialect).startswith("3.0"):
        print("warning: AI Studio connector import expects OpenAPI 3.0.x; convert before importing", file=sys.stderr)


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        _die("cannot read %s: %s" % (path, e))


def _server_path_prefix(spec):
    """Path part of servers[0].url, e.g. '/ords/sdesk/servicedesk'."""
    servers = spec.get("servers") or []
    if not servers:
        return ""
    return urllib.parse.urlparse(servers[0].get("url", "")).path.rstrip("/")


def _to_resource_path(prefix, path, schema_alias_path):
    """Build an AI Studio resourcePath relative to the instance URL (<host>/ords/<alias>)."""
    full = (prefix + "/" + path.lstrip("/")) if prefix else path
    if schema_alias_path and full.startswith(schema_alias_path):
        full = full[len(schema_alias_path):]
    full = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", full)   # ORDS :name -> {name}
    return "/" + full.lstrip("/")


def _is_collection(spec, op):
    """True when the 200 response schema is an ORDS enveloped collection (has an items array)."""
    resp = (op.get("responses") or {}).get("200") or {}
    schema = (((resp.get("content") or {}).get("application/json") or {}).get("schema")) or {}
    for _ in range(5):
        if "$ref" in schema:
            schema = _resolve(spec, schema["$ref"]) or {}
        else:
            break
    items = (schema.get("properties") or {}).get("items") or {}
    return items.get("type") == "array" or "$ref" in items


def cmd_endpoints(args):
    spec = _load(args.spec)
    prefix = _server_path_prefix(spec)
    alias = None
    m = re.match(r"(/ords/[^/]+)", prefix)
    if m:
        alias = m.group(1)
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        for method in HTTP_METHODS:
            op = ops.get(method)
            if not op:
                continue
            params = list(ops.get("parameters", [])) + list(op.get("parameters", []))
            rp = _to_resource_path(prefix, path, alias)
            pdefs, query = [], []
            for p in params:
                if "$ref" in p:
                    continue
                name, loc = p.get("name"), p.get("in")
                typ = (p.get("schema") or {}).get("type", "string")
                if loc == "path":
                    pdefs.append({"name": name, "dataType": typ, "isToken": True})
                elif loc == "query":
                    query.append({"name": name, "dataType": typ, "isToken": False})
            if (method == "get" and _is_collection(spec, op) and not re.search(r"\{[^}]+\}$", rp)
                    and not any(q["name"] == "limit" for q in query)):
                query += [{"name": "limit", "dataType": "number", "isToken": False},
                          {"name": "offset", "dataType": "number", "isToken": False}]
            op_id = op.get("operationId") or re.sub(r"[^A-Za-z0-9]+", "_", method + path).strip("_")
            out.append({
                "name": op_id,
                "description": (op.get("summary") or op.get("description") or
                                "%s %s - review and describe for the agent" % (method.upper(), rp)).strip(),
                "operationType": method.upper(),
                "resourcePath": rp,
                "parameterDefinitions": pdefs + query,
                "headers": [],
                "_review": "Confirm field names against the base aistudio skill; remove endpoints the agent must not call; write endpoints belong in a separate tool.",
            })
    if alias:
        print("instance URL should end with: %s" % alias, file=sys.stderr)
    writes = [e["name"] for e in out if e["operationType"] != "GET"]
    if writes:
        print("note: %d write endpoint(s) found (%s) - put them in a separate tool (reference/agent-safety-and-resilience.md)"
              % (len(writes), ", ".join(writes)), file=sys.stderr)
    text = json.dumps(out, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text + "\n")
        print("wrote %d endpoint block(s) to %s" % (len(out), args.output))
    else:
        print(text)


def _refs(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/"):
                acc.add(v)
            else:
                _refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            _refs(v, acc)


def _resolve(spec, ref):
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def cmd_subset(args):
    spec = _load(args.spec)
    paths = spec.get("paths") or {}
    wanted = {}
    for p in args.paths:
        matches = [k for k in paths if k == p or k.rstrip("/") == p.rstrip("/")]
        if not matches:
            _die("path %s not in spec. Available: %s" % (p, ", ".join(sorted(paths))))
        for k in matches:
            wanted[k] = paths[k]
    out = {k: v for k, v in spec.items() if k not in ("paths", "components")}
    out["paths"] = wanted
    # transitive $ref closure over components
    seen, frontier = set(), set()
    _refs(wanted, frontier)
    components = {}
    while frontier:
        ref = frontier.pop()
        if ref in seen:
            continue
        seen.add(ref)
        target = _resolve(spec, ref)
        if target is None:
            _die("dangling $ref %s in the source spec" % ref)
        parts = ref[2:].split("/")
        if parts[0] == "components" and len(parts) == 3:
            components.setdefault(parts[1], {})[parts[2]] = target
        _refs(target, frontier)
    if components:
        out["components"] = components
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print("wrote %s: %d path(s), %d component ref(s)" % (args.output, len(wanted), len(seen)))


def cmd_check(args):
    url = args.base.rstrip("/") + "/" + args.path.lstrip("/")
    status, body = _get(url, _token(args))
    print("HTTP %s %s" % (status, _explain(status)))
    if not isinstance(body, dict):
        print("body is not JSON" if body else "empty body")
        return
    if "items" in body:
        shape = "enveloped collection" + (" with links" if "links" in body else " without links")
        print("shape: %s | rows on page: %d | hasMore: %s | count: %s | limit: %s | offset: %s" % (
            shape, len(body.get("items") or []), body.get("hasMore"), body.get("count"),
            body.get("limit"), body.get("offset")))
        if body.get("hasMore"):
            print("warning: hasMore is true - the workflow must page or state that results are truncated")
        first = (body.get("items") or [{}])[0]
        if first:
            print("row fields (%d): %s" % (len(first), ", ".join(sorted(first))))
            if len(first) > 12:
                print("hint: %d fields per row - trim columns in the handler SQL" % len(first))
    elif status == 200:
        print("shape: bare object (no envelope) | top-level fields: %s" % ", ".join(sorted(body)))
    else:
        detail = body.get("message") or body.get("title") or ""
        if detail:
            print("detail: %s" % str(detail)[:300])


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def net(p):
        p.add_argument("--base", required=True, help="https://<host>/ords/<schema-alias>")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--auth", choices=["client-credentials"])
        g.add_argument("--bearer-env", metavar="NAME")

    p = sub.add_parser("modules", help="list modules in the OpenAPI catalog"); net(p); p.set_defaults(fn=cmd_modules)
    p = sub.add_parser("spec", help="download a module OpenAPI document"); net(p)
    p.add_argument("--module", required=True, help="module base path, e.g. servicedesk")
    p.add_argument("-o", "--output", required=True); p.set_defaults(fn=cmd_spec)
    p = sub.add_parser("endpoints", help="OpenAPI -> AI Studio External REST endpoint blocks")
    p.add_argument("spec"); p.add_argument("-o", "--output"); p.set_defaults(fn=cmd_endpoints)
    p = sub.add_parser("subset", help="keep selected paths and the components they reference")
    p.add_argument("spec"); p.add_argument("--paths", nargs="+", required=True)
    p.add_argument("-o", "--output", required=True); p.set_defaults(fn=cmd_subset)
    p = sub.add_parser("check", help="call one endpoint and classify the response"); net(p)
    p.add_argument("--path", required=True, help="path after the schema alias, e.g. /servicedesk/tickets")
    p.set_defaults(fn=cmd_check)

    args = ap.parse_args()
    if getattr(args, "base", None) and not args.base.startswith("https://") and not args.base.startswith("http://localhost"):
        print("warning: base URL is not https", file=sys.stderr)
    args.fn(args)


if __name__ == "__main__":
    main()
