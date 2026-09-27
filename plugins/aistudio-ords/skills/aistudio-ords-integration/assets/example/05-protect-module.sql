-- Protect the servicedesk module with OAuth2 so you can practise the
-- authenticated paths (Connector, or External REST + UI hand-off).
--
-- After this runs, every /servicedesk/* call without a valid bearer token
-- returns 401. Then create a client with ../sql/create-oauth-client.sql using
-- p_privilege_names => 'servicedesk_priv' and p_role_name => 'servicedesk_role'.

BEGIN
  ORDS.CREATE_ROLE(p_role_name => 'servicedesk_role');
  COMMIT;
END;
/

DECLARE
  l_roles    OWA.vc_arr;
  l_patterns OWA.vc_arr;
BEGIN
  l_roles(1)    := 'servicedesk_role';
  l_patterns(1) := '/servicedesk/*';
  -- Optional: also hide the API description from anonymous callers.
  -- l_patterns(2) := '/open-api-catalog/*';

  ORDS.DEFINE_PRIVILEGE(
    p_privilege_name => 'servicedesk_priv',
    p_roles          => l_roles,
    p_patterns       => l_patterns,
    p_label          => 'Service desk API',
    p_description    => 'Access to the servicedesk ORDS module');
  COMMIT;
END;
/

-- Check: https://<adb-host>/ords/<schema-alias>/servicedesk/tickets now returns 401,
-- while /open-api-catalog/servicedesk/ stays readable unless you added pattern (2).
