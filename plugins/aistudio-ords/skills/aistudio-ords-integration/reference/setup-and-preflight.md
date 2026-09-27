# Setup and preflight

Run this once per project, **before** choosing a path. Every failure listed here
was hit in practice, and each one is cheaper to find now than halfway through a
build.

## 1 · Install Oracle's base `aistudio` skill

This skill never creates artifacts itself. It hands every create, validate, save
and test command to Oracle's bundled `aistudio` skill and CLI, which are **not**
part of this plugin and are not in any Claude Code marketplace.

1. Get Oracle's repository: clone `https://github.com/oracle/fusion-ai-studio`
   or download its release zip.
2. Find the skill bundle for your release:
   `<repo>/<release>/aistudio/bin/aistudio-skill.zip`, for example
   `release-26C/aistudio/bin/aistudio-skill.zip`.
3. Verify it against the checksum shipped next to it:

   ```bash
   cat  <repo>/<release>/aistudio/bin/aistudio-skill.zip.sha256
   shasum -a 256 <repo>/<release>/aistudio/bin/aistudio-skill.zip
   ```

4. Unzip it into the **project** so that `SKILL.md` lands at
   `.claude/skills/aistudio/SKILL.md`:

   ```bash
   mkdir -p .claude/skills
   unzip -q -o <repo>/<release>/aistudio/bin/aistudio-skill.zip -d .claude/skills/
   ```

   Oracle's own guide says `.agents/skills/`. That is the Codex location.
   **Claude Code only discovers skills under `.claude/skills/`** (project) or
   `~/.claude/skills/` (user). If you install to `.agents/skills/`, the skill
   silently never loads.
5. The CLI is `scripts/aistudio.js` inside that folder. Always run it from the
   project root by path. Oracle's prompts write `aistudio <command>` as
   shorthand for this:

   ```bash
   node .claude/skills/aistudio/scripts/aistudio.js version
   node .claude/skills/aistudio/scripts/aistudio.js --help
   ```

   Oracle's prompt files print paths as `node .agents/skills/aistudio/...`.
   Substitute `.claude/skills/...`; the CLI works identically.
6. Reload skills (`/reload-plugins`, or restart the session) so `aistudio` shows
   up in the skill list.

Some later CLI commands write a `package.json` whose npm scripts point at
`.agents/skills/...`. Those scripts are for CI. Oracle's skill forbids running
workflow tests through npm, so leave them alone or fix the path. They do not
affect the CLI. The Node warning `MODULE_TYPELESS_PACKAGE_JSON` that appears
afterwards is harmless.

## 2 · Point the CLI at a Fusion pod

The CLI reads `env.properties` from the project root, from
`~/.config/aistudio-cli/env.properties`, or from `$AISTUDIO_ENV_PATH`. Without
one, every server command fails with `Missing env.properties`.

- **OAuth (recommended):** in AI Studio, open **Credentials → AI Studio CLI**,
  enable the CLI with your IDCS public client's **Client ID**, and copy the
  generated `env.properties` content into the project file. Then run
  `authenticate` once; it opens a browser.
- **Basic / dev mode:** set `aistudio.fa-host` and `aistudio.fa-user`, then use
  the CLI's `configure-basic-auth`. Never write the password into the file.

Verify:

```bash
node .claude/skills/aistudio/scripts/aistudio.js whoami      # prints your user
```

Add `env.properties`, `.env*.local`, `.debug/` and `test-reports/` to
`.gitignore` before the first commit.

## 3 · Probe what your user can actually reach

`whoami` succeeding does **not** mean every API works. Connector and Knowledge
Management endpoints sit behind a different resource scope and role from the
workflow and app APIs. Probe both **before** you pick a path:

| Probe (read-only) | Healthy result | If it fails |
|---|---|---|
| `list-workflow-families` | a family list | pod URL or auth is wrong |
| `list-bo-data-source-applications` | zero or more data sources | BO path unavailable |
| `search-connector-definitions --query <word>` | `ok: true`, 0–5 matches | **`401` → Connector path blocked** |
| `list-km-connectors` | a list | `401 Unauthorized` → same cause |

A `401` on the connector or KM probes while workflow calls succeed usually means
one of two things:

1. **The IDCS public client is missing a resource scope.** Oracle's CLI OAuth
   guide requires both **Oracle Fusion AI Cloud (Spectra)** and **Oracle Boss
   Cloud (Spectra)** under the client's token issuance policy. Add the missing
   one, then run `authenticate` again so the new token carries it.
2. **Your Fusion user lacks the connector role.** To tell which: open AI Studio
   → Connectors in the browser as the same user. If the UI fails too, it is the
   role; ask a pod admin.

Until the probe passes, the Connector path cannot be automated. Either fix
access first or take the External REST path and accept the UI step (see
[choosing-a-path.md](choosing-a-path.md)).

## 4 · Get ORDS credentials into the session safely

You need a working ORDS token to read live response shapes (step 1 of the
method) and to verify auth before creating tools.

- **Never paste a client secret into chat.** Put it in a git-ignored local file
  that only you can read, and read it from the shell:

  ```bash
  cat > .env.local <<'EOF'
  ORDS_CLIENT_ID=...
  ORDS_CLIENT_SECRET=...
  EOF
  chmod 600 .env.local
  ```

- **Use a dedicated OAuth client for AI Studio**, not the one your APEX or web
  app already uses. You can then revoke or rotate it without touching the other
  consumer. See [../assets/sql/create-oauth-client.sql](../assets/sql/create-oauth-client.sql).
- Test the exchange before building anything. See
  [ords-discovery.md](ords-discovery.md#get-a-token).

## Preflight checklist

- [ ] `aistudio` skill unzipped under `.claude/skills/aistudio/`, checksum verified
- [ ] `version` and `whoami` succeed from the project root
- [ ] Connector and KM probes checked. You know whether the Connector path is open
- [ ] ORDS catalog located and a token exchange works (see ords-discovery.md)
- [ ] Secrets are only in git-ignored files; a dedicated ORDS client exists for AI Studio
