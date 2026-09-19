SET search_path TO maritime_sql_agent, public;

-- 1. Row count check: every table should have at least 50 rows.
SELECT 'vessels' AS table_name, COUNT(*) AS row_count FROM vessels
UNION ALL
SELECT 'certificates', COUNT(*) FROM certificates
UNION ALL
SELECT 'compliance_documents', COUNT(*) FROM compliance_documents
UNION ALL
SELECT 'checklist_items', COUNT(*) FROM checklist_items
UNION ALL
SELECT 'crew_training_records', COUNT(*) FROM crew_training_records
ORDER BY table_name;

-- 2. Column comment check: missing_comment_count should be 0.
SELECT
    c.table_name,
    COUNT(*) FILTER (
        WHERE pg_catalog.col_description(format('%I.%I', c.table_schema, c.table_name)::REGCLASS::OID, c.ordinal_position) IS NULL
    ) AS missing_comment_count
FROM information_schema.columns c
WHERE c.table_schema = 'maritime_sql_agent'
  AND c.table_name IN ('vessels', 'certificates', 'compliance_documents', 'checklist_items', 'crew_training_records')
GROUP BY c.table_name
ORDER BY c.table_name;

-- 3. FK orphan check: every count should be 0.
SELECT 'certificates_without_vessel' AS check_name, COUNT(*) AS invalid_count
FROM certificates c
LEFT JOIN vessels v ON v.vessel_id = c.vessel_id
WHERE v.vessel_id IS NULL
UNION ALL
SELECT 'checklist_items_without_vessel', COUNT(*)
FROM checklist_items ci
LEFT JOIN vessels v ON v.vessel_id = ci.vessel_id
WHERE v.vessel_id IS NULL
UNION ALL
SELECT 'crew_training_without_vessel', COUNT(*)
FROM crew_training_records ctr
LEFT JOIN vessels v ON v.vessel_id = ctr.vessel_id
WHERE v.vessel_id IS NULL;

-- 4. Key expected rows for the 5-vessel briefing sample.
SELECT
    'sample_expiring_certificates_q2' AS check_name,
    COUNT(*) AS expected_sample_count
FROM certificates c
JOIN vessels v ON v.vessel_id = c.vessel_id
WHERE v.vessel_id BETWEEN 1 AND 5
  AND c.expiry_date <= DATE '2026-05-02' + INTERVAL '60 days'
UNION ALL
SELECT
    'sample_open_high_critical_psc_q3',
    COUNT(*)
FROM checklist_items ci
JOIN vessels v ON v.vessel_id = ci.vessel_id
WHERE v.vessel_id BETWEEN 1 AND 5
  AND ci.checklist_type = 'PSC'
  AND ci.status <> 'completed'
  AND ci.severity IN ('high', 'critical')
UNION ALL
SELECT
    'sample_required_training_at_risk_q9',
    COUNT(*)
FROM crew_training_records ctr
JOIN vessels v ON v.vessel_id = ctr.vessel_id
WHERE v.vessel_id BETWEEN 1 AND 5
  AND ctr.is_required = TRUE
  AND ctr.expiry_date <= DATE '2026-05-02' + INTERVAL '30 days';

