-- ORDS introspection: what is actually deployed, as opposed to what the
-- generated OpenAPI spec or your repo scripts say.
--
-- Run as the REST-enabled schema (the parsing schema of the modules).
-- Column names are from ORDS 22-24. If a column is missing on your release,
-- DESCRIBE the view; the view names have been stable for years.
-- Never select or share CLIENT_SECRET.

-- 1. The schema alias used in every URL: https://<adb-host>/ords/<PATTERN>/...
SELECT parsing_schema, pattern AS schema_alias, type, status
  FROM user_ords_schemas;

-- 2. Modules: base path (URL segment 3) and default page size.
SELECT m.name            AS module_name,
       m.uri_prefix      AS base_path,
       m.items_per_page  AS module_page_size,
       m.status
  FROM user_ords_modules m
 ORDER BY m.name;

-- 3. Every template and handler, with the effective page size and source.
--    Use this to recover the real JSON body a PL/SQL handler expects when the
--    generated spec shows only { "body_text": string }.
SELECT m.name                                     AS module_name,
       m.uri_prefix || t.uri_template             AS path,
       h.method,
       h.source_type,
       NVL(h.items_per_page, m.items_per_page)    AS page_size,
       h.mimes_allowed,
       DBMS_LOB.SUBSTR(h.source, 4000, 1)         AS source_first_4000
  FROM user_ords_modules   m
  JOIN user_ords_templates t ON t.module_id   = m.id
  JOIN user_ords_handlers  h ON h.template_id = t.id
 WHERE m.name = :module_name            -- or remove to list everything
 ORDER BY t.uri_template, h.method;

-- 4. Explicit handler parameters: header binds, URI binds, response params.
SELECT m.name || ' ' || h.method || ' ' || m.uri_prefix || t.uri_template AS handler,
       p.name, p.bind_variable_name, p.source_type, p.param_type, p.access_method
  FROM user_ords_modules    m
  JOIN user_ords_templates  t ON t.module_id   = m.id
  JOIN user_ords_handlers   h ON h.template_id = t.id
  JOIN user_ords_parameters p ON p.handler_id  = h.id
 ORDER BY handler, p.name;

-- 5. What protects a module: privilege -> URL patterns / modules -> roles.
SELECT privilege_name, pattern          FROM user_ords_privilege_mappings ORDER BY 1, 2;
SELECT privilege_name, module_name      FROM user_ords_privilege_modules  ORDER BY 1, 2;
SELECT privilege_name, role_name        FROM user_ords_privilege_roles    ORDER BY 1, 2;

-- 6. OAuth clients and what they are granted (no secrets).
SELECT name, client_id, grant_type, description FROM user_ords_clients ORDER BY name;
SELECT client_name, role_name                   FROM user_ords_client_roles ORDER BY 1, 2;
SELECT client_name, privilege_name              FROM user_ords_client_privileges ORDER BY 1, 2;

-- A client that gets a token but receives 401/403 on a handler is almost always
-- missing the role that the handler's privilege requires: compare (5) with (6).
