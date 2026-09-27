-- A write handler an agent can report on truthfully.
--
-- POST /servicedesk/tickets/assign
--   body: {"references":["TKT-1001","TKT-1003"],"assignee":"j.rivera","assigned_by":"supervisor@example.com"}
--
-- The generated OpenAPI spec will show this handler's body as
-- { "body_text": string }. That is the placeholder for :body_text, not the
-- contract. Document the real body above and in your agent spec
-- (07-agent-openapi.json).
--
-- Design points (see reference/write-back-actions.md):
--   * counts come from SQL%ROWCOUNT, never from a loop counter
--   * each key is reported as updated or skipped, with a reason
--   * validation failures return 400 with a short message, not ORA- text

BEGIN
  ORDS.DEFINE_TEMPLATE(
    p_module_name => 'servicedesk',
    p_pattern     => 'tickets/assign');

  ORDS.DEFINE_HANDLER(
    p_module_name   => 'servicedesk',
    p_pattern       => 'tickets/assign',
    p_method        => 'POST',
    p_source_type   => ORDS.source_type_plsql,
    p_mimes_allowed => 'application/json',
    p_source        => q'[
DECLARE
  l_body     CLOB          := :body_text;
  l_assignee VARCHAR2(60)  := JSON_VALUE(l_body, '$.assignee');
  l_refs     JSON_ARRAY_T;
  l_ref      VARCHAR2(20);
  l_updated  JSON_ARRAY_T  := JSON_ARRAY_T();
  l_skipped  JSON_ARRAY_T  := JSON_ARRAY_T();
  l_count    PLS_INTEGER   := 0;
BEGIN
  IF l_assignee IS NULL OR JSON_QUERY(l_body, '$.references') IS NULL THEN
    :status_code := 400;
    OWA_UTIL.MIME_HEADER('application/json', TRUE);
    HTP.P('{"success":false,"error":"assignee and references are required"}');
    RETURN;
  END IF;

  l_refs := JSON_ARRAY_T(JSON_QUERY(l_body, '$.references'));
  FOR i IN 0 .. l_refs.get_size - 1 LOOP
    l_ref := l_refs.get_string(i);
    UPDATE tickets
       SET assigned_to = l_assignee
     WHERE reference = l_ref
       AND status   <> 'RESOLVED';
    IF SQL%ROWCOUNT = 1 THEN
      l_count := l_count + 1;
      l_updated.append(l_ref);
    ELSE
      l_skipped.append(l_ref);           -- unknown or already resolved
    END IF;
  END LOOP;
  COMMIT;

  :status_code := 200;
  OWA_UTIL.MIME_HEADER('application/json', TRUE);
  HTP.P('{"success":true,"updated_count":' || l_count
        || ',"updated":' || l_updated.to_string
        || ',"skipped":' || l_skipped.to_string
        || ',"message":"' || l_count || ' ticket(s) assigned to ' || l_assignee || '"}');
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    :status_code := 500;
    OWA_UTIL.MIME_HEADER('application/json', TRUE);
    HTP.P('{"success":false,"error":"assignment failed; see server log"}');
END;
]');
  COMMIT;
END;
/
