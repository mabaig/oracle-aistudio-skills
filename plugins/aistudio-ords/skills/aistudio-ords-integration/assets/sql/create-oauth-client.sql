-- A dedicated ORDS OAuth2 client for Fusion AI Studio (client credentials).
--
-- Give AI Studio its own client instead of reusing the one an APEX, VBCS or web
-- app already uses. You can then rotate or revoke it without breaking the
-- other consumer, and ORDS logs show which consumer made a call.
--
-- Prerequisites: the module is protected by a privilege that requires a role
-- (see ../example/05-protect-module.sql). Replace the placeholders below.
-- Run as the REST-enabled schema.

BEGIN
  OAUTH.CREATE_CLIENT(
    p_name            => 'aistudio_client',                -- one per consumer
    p_grant_type      => 'client_credentials',
    p_owner           => 'Fusion AI Studio',
    p_description     => 'Fusion AI Studio agentic apps and workflows',
    p_support_email   => 'ops@example.com',
    p_privilege_names => '<privilege_name>');              -- e.g. servicedesk_priv

  OAUTH.GRANT_CLIENT_ROLE(
    p_client_name => 'aistudio_client',
    p_role_name   => '<role_name>');                       -- e.g. servicedesk_role
  COMMIT;
END;
/

-- The client id is safe to read and share with the person configuring AI Studio.
SELECT name, client_id, grant_type FROM user_ords_clients WHERE name = 'aistudio_client';

-- The client secret is not. Retrieve it once, in your own SQL tool, and type it
-- straight into the AI Studio UI (External REST tool auth) or the connector
-- instance's secret field. Never paste it into chat, tickets or source control.
--   * Releases that store it readably expose it as USER_ORDS_CLIENTS.CLIENT_SECRET.
--   * On ORDS 23.3 and later, prefer the ORDS_SECURITY package's client
--     registration API, which returns the secret at registration time; OAUTH.*
--     still works there but is deprecated.

-- Verify from a shell (reads the secret from a git-ignored .env.local):
--   curl -s -u "$ORDS_CLIENT_ID:$ORDS_CLIENT_SECRET" -d grant_type=client_credentials \
--        "https://<adb-host>/ords/<schema-alias>/oauth/token"
--   -> {"access_token":"...","token_type":"bearer","expires_in":3600}

-- Revoke when AI Studio no longer needs access:
--   BEGIN OAUTH.DELETE_CLIENT(p_name => 'aistudio_client'); COMMIT; END;
--   /
