SET search_path TO maritime_sql_agent, public;

-- Q1 Easy: IMO 번호 9876543인 선박의 기본 제원
SELECT
    vessel_name,
    vessel_type,
    gross_tonnage,
    build_year,
    flag_state,
    class_society,
    operating_status
FROM vessels
WHERE imo_number = '9876543';

-- Q2 Easy: 2026-05-02 기준 만료 또는 60일 이내 만료 certificate
SELECT
    v.vessel_name,
    c.certificate_name,
    c.expiry_date,
    c.expiry_date - DATE '2026-05-02' AS days_remaining,
    CASE
        WHEN c.expiry_date < DATE '2026-05-02' THEN 'expired'
        ELSE 'expiring'
    END AS cert_status
FROM certificates c
JOIN vessels v ON v.vessel_id = c.vessel_id
WHERE c.expiry_date <= DATE '2026-05-02' + INTERVAL '60 days'
ORDER BY c.expiry_date;

-- Q3 Easy: 미완료 high/critical PSC checklist item
SELECT
    v.vessel_name,
    ci.item_category,
    ci.item_text,
    ci.severity,
    ci.due_date
FROM checklist_items ci
JOIN vessels v ON v.vessel_id = ci.vessel_id
WHERE ci.checklist_type = 'PSC'
  AND ci.status <> 'completed'
  AND ci.severity IN ('high', 'critical')
ORDER BY
    CASE ci.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
    ci.due_date;

-- Q4 Medium: 이미 만료된 required crew training certificate
SELECT
    v.vessel_name,
    ctr.crew_name,
    ctr.rank,
    ctr.training_name,
    ctr.expiry_date
FROM crew_training_records ctr
JOIN vessels v ON v.vessel_id = ctr.vessel_id
WHERE ctr.is_required = TRUE
  AND ctr.expiry_date < DATE '2026-05-02'
ORDER BY ctr.expiry_date;

-- Q5 Medium: 선박별 expired/90일 이내 만료 certificate count
SELECT
    v.vessel_name,
    COUNT(*) FILTER (WHERE c.expiry_date < DATE '2026-05-02') AS expired_count,
    COUNT(*) FILTER (
        WHERE c.expiry_date >= DATE '2026-05-02'
          AND c.expiry_date <= DATE '2026-05-02' + INTERVAL '90 days'
    ) AS expiring_90d_count
FROM vessels v
LEFT JOIN certificates c ON c.vessel_id = v.vessel_id
GROUP BY v.vessel_id, v.vessel_name
ORDER BY expired_count DESC, expiring_90d_count DESC, v.vessel_name;

-- Q6 Medium: 선박별 PSC checklist completion rate
SELECT
    v.vessel_name,
    COUNT(ci.item_id) AS total_items,
    COUNT(ci.item_id) FILTER (WHERE ci.status = 'completed') AS completed_items,
    ROUND(
        100.0 * COUNT(ci.item_id) FILTER (WHERE ci.status = 'completed')
        / NULLIF(COUNT(ci.item_id), 0),
        2
    ) AS completion_pct
FROM vessels v
JOIN checklist_items ci ON ci.vessel_id = v.vessel_id
WHERE ci.checklist_type = 'PSC'
GROUP BY v.vessel_id, v.vessel_name
ORDER BY completion_pct ASC, v.vessel_name;

-- Q7 Medium: M/V Ocean Aurora에 적용되는 Regulation, Manual, System Doc
SELECT
    v.vessel_name,
    d.document_code,
    d.document_title,
    d.document_type,
    d.document_domain,
    d.is_mandatory
FROM vessels v
JOIN compliance_documents d
    ON (d.applies_vessel_type IS NULL OR d.applies_vessel_type = v.vessel_type)
   AND (d.tonnage_min IS NULL OR d.tonnage_min <= v.gross_tonnage)
   AND (d.tonnage_max IS NULL OR d.tonnage_max >= v.gross_tonnage)
   AND (d.build_year_min IS NULL OR d.build_year_min <= v.build_year)
   AND (d.build_year_max IS NULL OR d.build_year_max >= v.build_year)
WHERE v.vessel_name = 'M/V Ocean Aurora'
ORDER BY d.document_domain, d.document_type, d.document_code;

-- Q8 Hard: fleet compliance risk ranking
WITH cert_risk AS (
    SELECT
        vessel_id,
        COUNT(*) FILTER (WHERE expiry_date < DATE '2026-05-02') AS expired_cert_count,
        COUNT(*) FILTER (
            WHERE expiry_date >= DATE '2026-05-02'
              AND expiry_date <= DATE '2026-05-02' + INTERVAL '90 days'
        ) AS expiring_cert_count
    FROM certificates
    GROUP BY vessel_id
),
checklist_risk AS (
    SELECT
        vessel_id,
        COUNT(*) FILTER (WHERE status <> 'completed' AND severity = 'critical') AS open_critical_count,
        COUNT(*) FILTER (WHERE status <> 'completed' AND severity = 'high') AS open_high_count
    FROM checklist_items
    WHERE checklist_type = 'PSC'
    GROUP BY vessel_id
),
scored AS (
    SELECT
        v.vessel_name,
        COALESCE(cr.expired_cert_count, 0) AS expired_cert_count,
        COALESCE(cr.expiring_cert_count, 0) AS expiring_cert_count,
        COALESCE(ch.open_critical_count, 0) AS open_critical_count,
        COALESCE(ch.open_high_count, 0) AS open_high_count,
        COALESCE(cr.expired_cert_count, 0) * 3
          + COALESCE(cr.expiring_cert_count, 0) * 2
          + COALESCE(ch.open_critical_count, 0) * 3
          + COALESCE(ch.open_high_count, 0) * 2 AS risk_score
    FROM vessels v
    LEFT JOIN cert_risk cr ON cr.vessel_id = v.vessel_id
    LEFT JOIN checklist_risk ch ON ch.vessel_id = v.vessel_id
)
SELECT
    vessel_name,
    expired_cert_count,
    expiring_cert_count,
    open_critical_count,
    open_high_count,
    risk_score,
    RANK() OVER (ORDER BY risk_score DESC) AS risk_rank
FROM scored
ORDER BY risk_rank, vessel_name;

-- Q9 Hard: required training 만료 또는 30일 이내 만료 crew
WITH training_status AS (
    SELECT
        v.vessel_name,
        ctr.crew_name,
        ctr.rank,
        ctr.training_name,
        ctr.expiry_date,
        CASE
            WHEN ctr.expiry_date < DATE '2026-05-02' THEN 'expired'
            WHEN ctr.expiry_date <= DATE '2026-05-02' + INTERVAL '30 days' THEN 'expiring_30d'
            ELSE 'valid'
        END AS training_status
    FROM crew_training_records ctr
    JOIN vessels v ON v.vessel_id = ctr.vessel_id
    WHERE ctr.is_required = TRUE
      AND ctr.expiry_date IS NOT NULL
),
at_risk AS (
    SELECT *
    FROM training_status
    WHERE training_status IN ('expired', 'expiring_30d')
)
SELECT
    vessel_name,
    crew_name,
    rank,
    training_name,
    expiry_date,
    training_status,
    RANK() OVER (
        PARTITION BY vessel_name
        ORDER BY
            CASE training_status WHEN 'expired' THEN 1 ELSE 2 END,
            expiry_date
    ) AS vessel_risk_rank
FROM at_risk
ORDER BY
    CASE training_status WHEN 'expired' THEN 1 ELSE 2 END,
    expiry_date,
    vessel_name,
    crew_name;

-- Q10 Hard: 선박별 지금 당장 조치해야 할 action item 1개
WITH action_items AS (
    SELECT
        v.vessel_id,
        v.vessel_name,
        'expired_certificate' AS action_type,
        c.certificate_name AS action_detail,
        c.expiry_date AS due_date,
        4 AS priority_score
    FROM certificates c
    JOIN vessels v ON v.vessel_id = c.vessel_id
    WHERE c.expiry_date < DATE '2026-05-02'

    UNION ALL

    SELECT
        v.vessel_id,
        v.vessel_name,
        'critical_psc_item' AS action_type,
        ci.item_text AS action_detail,
        ci.due_date,
        CASE ci.severity WHEN 'critical' THEN 4 WHEN 'high' THEN 3 ELSE 2 END AS priority_score
    FROM checklist_items ci
    JOIN vessels v ON v.vessel_id = ci.vessel_id
    WHERE ci.checklist_type = 'PSC'
      AND ci.status <> 'completed'
      AND ci.severity IN ('critical', 'high')

    UNION ALL

    SELECT
        v.vessel_id,
        v.vessel_name,
        'crew_training_expiry' AS action_type,
        ctr.crew_name || ' - ' || ctr.training_name AS action_detail,
        ctr.expiry_date AS due_date,
        CASE
            WHEN ctr.expiry_date < DATE '2026-05-02' THEN 4
            ELSE 2
        END AS priority_score
    FROM crew_training_records ctr
    JOIN vessels v ON v.vessel_id = ctr.vessel_id
    WHERE ctr.is_required = TRUE
      AND ctr.expiry_date <= DATE '2026-05-02' + INTERVAL '30 days'
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY vessel_id
            ORDER BY priority_score DESC, due_date ASC
        ) AS rn
    FROM action_items
)
SELECT
    vessel_name,
    action_type,
    action_detail,
    due_date,
    priority_score
FROM ranked
WHERE rn = 1
ORDER BY priority_score DESC, due_date ASC, vessel_name;

