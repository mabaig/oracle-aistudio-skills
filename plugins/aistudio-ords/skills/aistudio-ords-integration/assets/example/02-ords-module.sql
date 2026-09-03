-- Handler-based ORDS module.
--
-- Deliberately NOT AutoREST: handlers let us select only the columns the agent
-- needs, which is the single most effective thing you can do for grounding and
-- token cost. See reference/ords-response-contract.md

BEGIN
  ORDS.ENABLE_SCHEMA(
    p_enabled             => TRUE,
    p_schema              => USER,
    p_url_mapping_type    => 'BASE_PATH',
    p_url_mapping_pattern => LOWER(USER),
    p_auto_rest_auth      => FALSE);

  ORDS.DEFINE_MODULE(
    p_module_name => 'servicedesk',
    p_base_path   => '/servicedesk/',
    p_items_per_page => 25);

  ---------------------------------------------------------------- collection
  ORDS.DEFINE_TEMPLATE(
    p_module_name => 'servicedesk',
    p_pattern     => 'tickets');

  ORDS.DEFINE_HANDLER(
    p_module_name => 'servicedesk',
    p_pattern     => 'tickets',
    p_method      => 'GET',
    p_source_type => ORDS.source_type_collection_feed,
    p_source      => q'[
      SELECT t.reference, t.subject, t.status, t.priority,
             q.code AS queue_code, t.assigned_to, t.created_date
        FROM tickets t
        JOIN queues  q ON q.id = t.queue_id
       WHERE (:status IS NULL OR t.status = :status)
       ORDER BY t.created_date DESC
    ]');

  ------------------------------------------------------------- single record
  ORDS.DEFINE_TEMPLATE(
    p_module_name => 'servicedesk',
    p_pattern     => 'tickets/:reference');

  ORDS.DEFINE_HANDLER(
    p_module_name => 'servicedesk',
    p_pattern     => 'tickets/:reference',
    p_method      => 'GET',
    p_source_type => ORDS.source_type_collection_feed,
    p_source      => q'[
      SELECT t.reference, t.subject, t.status, t.priority,
             q.code AS queue_code, t.assigned_to, t.created_date
        FROM tickets t
        JOIN queues  q ON q.id = t.queue_id
       WHERE t.reference = :reference
    ]');

  ------------------------------------------- summary: NO envelope, bare object
  ORDS.DEFINE_TEMPLATE(
    p_module_name => 'servicedesk',
    p_pattern     => 'summary');

  ORDS.DEFINE_HANDLER(
    p_module_name => 'servicedesk',
    p_pattern     => 'summary',
    p_method      => 'GET',
    p_source_type => ORDS.source_type_media,
    p_source      => q'[
      SELECT 'application/json', JSON_OBJECT(
               'openCount'  VALUE (SELECT COUNT(*) FROM tickets WHERE status = 'OPEN'),
               'highCount'  VALUE (SELECT COUNT(*) FROM tickets WHERE priority = 'HIGH'),
               'unassigned' VALUE (SELECT COUNT(*) FROM tickets WHERE assigned_to IS NULL))
        FROM dual
    ]');

  COMMIT;
END;
/
