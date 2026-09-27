#!/usr/bin/env python3
"""ORDS OpenAPI helper for AI Studio integrations. Python 3.8+, standard library only.

Subcommands
  catalog    List the modules published in an ORDS open-api-catalog index.
  inventory  Summarise every operation in a module spec and flag what the
             ORDS-generated spec gets wrong for an agent (placeholder bodies,
             missing operationIds, header-bound params, missing envelope fields).
  probe      Call each GET operation that needs no path parameter and report
             HTTP status, response shape (envelope with/without links, bare
             object) and the handler's real default page size.
  subset     Keep only the operations an agent needs, prune unreferenced
             component schemas, keep one security scheme, and validate that
             no $ref dangles. Produces an import-ready OpenAPI 3.0 file.

Credentials are read from environment variables only and are never printed.

Examples
  python3 ords_openapi.py catalog --host <adb-host> --alias <schema-alias>
  python3 ords_openapi.py inventory https://<adb-host>/ords/<alias>/open-api-catalog/<base-path>/
  ORDS_CLIENT_ID=... ORDS_CLIENT_SECRET=... python3 ords_openapi.py probe spec.json
  python3 ords_openapi.py subset spec.json --keep "GET /tickets" --keep "GET /summary" -o agent.json
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

METHODS = ("get", "post", "put", "patch", "delete")
ENVELOPE = ("hasMore", "count", "limit", "offset")


# --------------------------------------------------------------------- http
def http_get(url, token=None, accept="application/json"):
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def load_json(source, args=None):
    """Load a spec/catalog from a file or URL. URLs are fetched anonymously first
    (ORDS catalogs are usually public); on 401/403 a token is obtained and the
    request retried."""
    if not re.match(r"^https?://", source):
        with open(source, encoding="utf-8") as fh:
            return json.load(fh)
    status, body = http_get(source)
    if status in (401, 403) and args is not None:
        token = resolve_token(args, source=source)
        if token:
            status, body = http_get(source, token)
    if status != 200:
        sys.exit("GET %s -> HTTP %s. If the catalog is protected, set ORDS_TOKEN or "
                 "ORDS_CLIENT_ID/ORDS_CLIENT_SECRET (and --token-url if it cannot be derived)."
                 % (source, status))
    return json.loads(body)


def token_url_from_spec(spec):
    for scheme in (spec.get("components", {}).get("securitySchemes") or {}).values():
        flow = (scheme.get("flows") or {}).get("clientCredentials")
        if flow and flow.get("tokenUrl"):
            return flow["tokenUrl"]
    return None


def token_url_from_catalog_url(url):
    """https://<host>/ords/<alias>/open-api-catalog/... -> https://<host>/ords/<alias>/oauth/token"""
    if url and "/open-api-catalog/" in url:
        return url.split("/open-api-catalog/")[0] + "/oauth/token"
    return None


def resolve_token(args, spec=None, source=None):
    """Bearer token from ORDS_TOKEN, or a client-credentials exchange. Returns
    None when no credentials are configured."""
    if os.environ.get(args.token_env):
        return os.environ[args.token_env]
    cid, secret = os.environ.get(args.client_id_env), os.environ.get(args.client_secret_env)
    if not (cid and secret):
        return None
    url = (args.token_url or token_url_from_catalog_url(source)
           or (token_url_from_spec(spec) if spec else None))
    if not url:
        sys.exit("Client credentials are set but no token URL is known. Pass --token-url "
                 "https://<adb-host>/ords/<schema-alias>/oauth/token")
    basic = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
    req = urllib.request.Request(url, data=b"grant_type=client_credentials", headers={
        "Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as err:
        sys.exit("Token request to %s failed: HTTP %s (check the client id/secret and that the "
                 "client has the role mapped to the module privilege)." % (url, err.code))


# --------------------------------------------------------------- spec utils
def deref(spec, node, seen=None):
    """Follow a local #/components/... $ref chain (one level of objects)."""
    seen = seen or set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in seen or not ref.startswith("#/"):
            return node
        seen.add(ref)
        target = spec
        for part in ref[2:].split("/"):
            target = target.get(part, {}) if isinstance(target, dict) else {}
        node = target
    return node


def operations(spec):
    for path, item in (spec.get("paths") or {}).items():
        for method in METHODS:
            if method in item:
                yield path, method, item[method]


def body_properties(spec, op):
    content = ((op.get("requestBody") or {}).get("content") or {})
    for media in content.values():
        schema = deref(spec, media.get("schema") or {})
        return set((schema.get("properties") or {}).keys())
    return None


def response_properties(spec, op):
    for code in ("200", "201"):
        resp = (op.get("responses") or {}).get(code)
        if not resp:
            continue
        for media in (resp.get("content") or {}).values():
            schema = deref(spec, media.get("schema") or {})
            return set((schema.get("properties") or {}).keys())
    return None


def flags_for(spec, method, op):
    flags = []
    if not op.get("operationId"):
        flags.append("no-operationId")
    params = op.get("parameters") or []
    if any(p.get("in") == "header" for p in params):
        flags.append("header-params")
    if any("implicit" in (p.get("description") or "").lower() for p in params):
        flags.append("implicit-params")
    body = body_properties(spec, op)
    if body is not None and body <= {"body_text"} and "body_text" in body:
        flags.append("placeholder-body")
    if method == "get":
        props = response_properties(spec, op)
        if props and "items" in props and not set(ENVELOPE) & props:
            flags.append("envelope-undeclared")
    return flags


# ----------------------------------------------------------------- commands
def cmd_catalog(args):
    url = args.url or "https://%s/ords/%s/open-api-catalog/" % (args.host, args.alias.strip("/"))
    index = load_json(url, args)
    print("Catalog: %s" % url)
    print("%-32s %s" % ("MODULE", "SPEC URL (use this for inventory/subset/import)"))
    for item in index.get("items", []):
        href = next((l["href"] for l in item.get("links", []) if l.get("rel") == "canonical"), "")
        print("%-32s %s" % (item.get("name", ""), href))
    if index.get("hasMore"):
        print("(catalog index has more entries: add ?offset=%s)" % index.get("count"))


def cmd_inventory(args):
    spec = load_json(args.spec, args)
    dialect = spec.get("openapi") or ("swagger " + str(spec.get("swagger")))
    servers = [s.get("url") for s in spec.get("servers", [])]
    schemes = list((spec.get("components", {}).get("securitySchemes") or {}).keys())
    ops = list(operations(spec))
    print("Title:    %s" % spec.get("info", {}).get("title"))
    print("Dialect:  %s%s" % (dialect, "" if str(dialect).startswith("3.0") else
                              "   <-- AI Studio imports OpenAPI 3.0 only; convert first"))
    print("Server:   %s" % (", ".join(servers) or "(none)"))
    print("Security: %s" % (", ".join(schemes) or "(none declared)"))
    print("Ops:      %d%s\n" % (len(ops), "   <-- over ~15: subset before Connector import"
                                 if len(ops) > 15 else ""))
    counts = {}
    for path, method, op in ops:
        params = ", ".join("%s@%s" % (p.get("name"), p.get("in")) for p in op.get("parameters") or [])
        body = body_properties(spec, op)
        flags = flags_for(spec, method, op)
        for f in flags:
            counts[f] = counts.get(f, 0) + 1
        print("%-6s %s" % (method.upper(), path))
        if op.get("description"):
            print("       desc:   %s" % op["description"][:110])
        if params:
            print("       params: %s" % params)
        if body is not None:
            print("       body:   {%s}" % ", ".join(sorted(body)))
        if flags:
            print("       flags:  %s" % ", ".join(flags))
    if counts:
        print("\nWhat the generated spec gets wrong (see reference/ords-discovery.md):")
        notes = {
            "placeholder-body": "PL/SQL handler reads :body_text - the real JSON body is only in the handler source",
            "no-operationId": "generated names are unstable; add operationIds before Connector import",
            "implicit-params": "bind variables surfaced as untyped 'Implicit parameter' strings",
            "header-params": "handler binds HTTP headers - External REST endpoints must send them as headers",
            "envelope-undeclared": "response schema lists items but not hasMore/count/limit/offset, which ORDS still returns",
        }
        for flag, n in sorted(counts.items()):
            print("  %-20s x%-3d %s" % (flag, n, notes.get(flag, "")))


def classify(obj):
    if not isinstance(obj, dict):
        return "non-object"
    if "items" in obj and "hasMore" in obj:
        return "enveloped+links" if "links" in obj else "enveloped"
    return "bare-object"


def cmd_probe(args):
    spec = load_json(args.spec, args)
    token = resolve_token(args, spec=spec, source=args.spec if args.spec.startswith("http") else None)
    if not token:
        print("No credentials in env: probing anonymously (expect 401 on protected modules).")
    base = (spec.get("servers") or [{}])[0].get("url", "").rstrip("/")
    print("%-6s %-34s %-5s %-16s %-6s %-7s %-6s %s" % ("METHOD", "PATH", "HTTP", "SHAPE", "COUNT",
                                                        "HASMORE", "LIMIT", "TOP KEYS"))
    for path, method, op in operations(spec):
        if method != "get" or "{" in path:
            continue
        status, body = http_get(base + path, token)
        shape, count, more, limit, keys = "-", "", "", "", ""
        try:
            obj = json.loads(body)
            shape = classify(obj) if status == 200 else "error"
            if isinstance(obj, dict):
                count, more, limit = obj.get("count", ""), obj.get("hasMore", ""), obj.get("limit", "")
                keys = ",".join(list(obj.keys())[:6])
        except ValueError:
            shape = "html/non-json" if body.lstrip()[:1] == b"<" else "non-json"
        print("%-6s %-34s %-5s %-16s %-6s %-7s %-6s %s" % ("GET", path[:34], status, shape, count,
                                                            more, limit, keys))
    print("\nLIMIT is the handler's real default page size (p_items_per_page), not always 25.")


def collect_refs(node, out):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/"):
            out.add(ref)
        for value in node.values():
            collect_refs(value, out)
    elif isinstance(node, list):
        for value in node:
            collect_refs(value, out)


def cmd_subset(args):
    spec = load_json(args.spec, args)
    wanted = {}
    for keep in args.keep:
        m = re.match(r"^\s*(GET|POST|PUT|PATCH|DELETE)\s+(\S+)\s*$", keep, re.I)
        if not m:
            sys.exit("--keep must look like 'GET /tickets' (got %r)" % keep)
        wanted.setdefault(m.group(2), set()).add(m.group(1).lower())
    paths = {}
    for path, methods in wanted.items():
        item = (spec.get("paths") or {}).get(path)
        if item is None:
            sys.exit("Path %s is not in the spec. Paths: %s" % (path, ", ".join(spec.get("paths", {}))))
        missing = [m for m in methods if m not in item]
        if missing:
            sys.exit("%s has no %s operation" % (path, "/".join(missing).upper()))
        paths[path] = {k: v for k, v in item.items() if k in methods or k not in METHODS}
    out = {k: v for k, v in spec.items() if k not in ("paths", "components")}
    out["paths"] = paths
    comps = spec.get("components") or {}
    # Transitively keep referenced component entries.
    keep_refs, frontier = set(), set()
    collect_refs(paths, frontier)
    while frontier:
        ref = frontier.pop()
        if ref in keep_refs:
            continue
        keep_refs.add(ref)
        _, _, section, name = ref.split("/", 3)
        collect_refs((comps.get(section) or {}).get(name), frontier)
    new_comps = {}
    for ref in keep_refs:
        _, _, section, name = ref.split("/", 3)
        if name in (comps.get(section) or {}):
            new_comps.setdefault(section, {})[name] = comps[section][name]
    schemes = comps.get("securitySchemes") or {}
    if args.security:
        name, _, flow = args.security.partition(":")
        if name not in schemes:
            sys.exit("Security scheme %s not found. Available: %s" % (name, ", ".join(schemes)))
        scheme = json.loads(json.dumps(schemes[name]))
        if flow and "flows" in scheme:
            scheme["flows"] = {flow: scheme["flows"][flow]}
        new_comps["securitySchemes"] = {name: scheme}
        out["security"] = [{name: []}]
        for item in paths.values():
            for method in METHODS:
                if method in item:
                    item[method]["security"] = [{name: []}]
    elif schemes:
        new_comps["securitySchemes"] = schemes
    if new_comps:
        out["components"] = new_comps
    # Validate: dialect and dangling refs.
    problems = []
    if not str(out.get("openapi", "")).startswith("3.0"):
        problems.append("dialect is %s, AI Studio imports OpenAPI 3.0 only" % out.get("openapi") or out.get("swagger"))
    refs = set()
    collect_refs(out, refs)
    for ref in refs:
        _, _, section, name = ref.split("/", 3)
        if name not in (new_comps.get(section) or {}):
            problems.append("dangling $ref " + ref)
    for path, method, op in operations(out):
        for flag in flags_for(out, method, op):
            if flag in ("placeholder-body", "no-operationId"):
                problems.append("%s %s: %s (fix by hand before import)" % (method.upper(), path, flag))
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("Wrote %s: %d operations, %d component entries, %d bytes" % (
        args.output, sum(1 for _ in operations(out)),
        sum(len(v) for v in new_comps.values()), os.path.getsize(args.output)))
    for p in problems:
        print("  WARN " + p)
    if any(p.startswith("dangling") for p in problems):
        sys.exit(2)


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--token-env", default="ORDS_TOKEN", help="env var holding a bearer token (default ORDS_TOKEN)")
    common.add_argument("--client-id-env", default="ORDS_CLIENT_ID", help="env var with the OAuth client id")
    common.add_argument("--client-secret-env", default="ORDS_CLIENT_SECRET", help="env var with the OAuth client secret")
    common.add_argument("--token-url", help="https://<adb-host>/ords/<schema-alias>/oauth/token "
                        "(defaults to the spec's clientCredentials tokenUrl)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog", parents=[common], help="list modules in an open-api-catalog index")
    c.add_argument("url", nargs="?", help="https://<adb-host>/ords/<schema-alias>/open-api-catalog/")
    c.add_argument("--host", help="ADB host, e.g. <db-ocid-prefix>-<db-name>.adb.<region>.oraclecloudapps.com")
    c.add_argument("--alias", help="schema URL alias (ORDS.ENABLE_SCHEMA p_url_mapping_pattern)")
    i = sub.add_parser("inventory", parents=[common], help="summarise and flag a module spec")
    i.add_argument("spec", help="spec URL or local file")
    p = sub.add_parser("probe", parents=[common], help="call GET operations and classify response shapes")
    p.add_argument("spec", help="spec URL or local file")
    s = sub.add_parser("subset", parents=[common], help="write an agent-sized, validated spec")
    s.add_argument("spec", help="spec URL or local file")
    s.add_argument("--keep", action="append", required=True, help="'METHOD /path', repeatable")
    s.add_argument("--security", help="keep one scheme, optionally one flow: OAuth2:clientCredentials")
    s.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    if args.cmd == "catalog" and not args.url and not (args.host and args.alias):
        ap.error("catalog needs a URL or --host and --alias")
    {"catalog": cmd_catalog, "inventory": cmd_inventory, "probe": cmd_probe, "subset": cmd_subset}[args.cmd](args)


if __name__ == "__main__":
    main()
