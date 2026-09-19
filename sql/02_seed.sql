SET search_path TO maritime_sql_agent, public;

TRUNCATE TABLE
    crew_training_records,
    checklist_items,
    certificates,
    compliance_documents,
    vessels
RESTART IDENTITY CASCADE;

INSERT INTO vessels (
    vessel_id, vessel_name, imo_number, vessel_type, gross_tonnage,
    build_year, flag_state, class_society, operating_status
) VALUES
    (1, 'M/V Ocean Aurora', '9876543', 'LNG Carrier', 116000, 2018, 'Marshall Islands', 'DNV', 'active'),
    (2, 'M/V Pacific Trader', '9765432', 'Bulk Carrier', 45200, 2012, 'Panama', 'KR', 'active'),
    (3, 'M/V Hanseatic Star', '9654321', 'Container Ship', 74000, 2020, 'Liberia', 'ABS', 'active'),
    (4, 'M/T Blue Horizon', '9543210', 'Oil Tanker', 58000, 2015, 'Singapore', 'LR', 'active'),
    (5, 'M/V Coastal Hope', '9432109', 'General Cargo', 8500, 2008, 'Republic of Korea', 'KR', 'drydock');

INSERT INTO vessels (
    vessel_id, vessel_name, imo_number, vessel_type, gross_tonnage,
    build_year, flag_state, class_society, operating_status
)
SELECT
    gs AS vessel_id,
    'M/V Training Vessel ' || LPAD((gs - 5)::TEXT, 2, '0') AS vessel_name,
    (9300000 + gs)::TEXT AS imo_number,
    CASE gs % 5
        WHEN 0 THEN 'General Cargo'
        WHEN 1 THEN 'Bulk Carrier'
        WHEN 2 THEN 'Container Ship'
        WHEN 3 THEN 'Offshore Support Vessel'
        ELSE 'Training Vessel'
    END AS vessel_type,
    9000 + (gs * 850) AS gross_tonnage,
    2000 + (gs % 24) AS build_year,
    CASE gs % 5
        WHEN 0 THEN 'Panama'
        WHEN 1 THEN 'Liberia'
        WHEN 2 THEN 'Marshall Islands'
        WHEN 3 THEN 'Singapore'
        ELSE 'Republic of Korea'
    END AS flag_state,
    CASE gs % 4
        WHEN 0 THEN 'KR'
        WHEN 1 THEN 'DNV'
        WHEN 2 THEN 'ABS'
        ELSE 'LR'
    END AS class_society,
    CASE
        WHEN gs % 11 = 0 THEN 'drydock'
        WHEN gs % 17 = 0 THEN 'inactive'
        ELSE 'active'
    END AS operating_status
FROM generate_series(6, 50) AS gs;

SELECT setval(pg_get_serial_sequence('vessels', 'vessel_id'), (SELECT MAX(vessel_id) FROM vessels));

INSERT INTO certificates (
    vessel_id, certificate_name, certificate_number, issuing_authority,
    issue_date, expiry_date, document_url, remarks
) VALUES
    (1, 'Cargo Ship Safety Equipment Certificate', 'SE-2025-001', 'DNV', '2025-05-26', '2026-05-25', 'https://docs.example.com/cert/se-2025-001.pdf', 'renewal survey booked'),
    (1, 'International Oil Pollution Prevention Certificate', 'IOPP-2025-011', 'DNV', '2025-01-15', '2027-01-15', 'https://docs.example.com/cert/iopp-2025-011.pdf', 'valid'),
    (2, 'Cargo Ship Safety Construction Certificate', 'SC-2021-009', 'KR', '2021-04-20', '2026-04-20', 'https://docs.example.com/cert/sc-2021-009.pdf', 'expired, urgent renewal'),
    (2, 'International Load Line Certificate', 'LL-2021-009', 'KR', '2021-07-15', '2026-07-15', 'https://docs.example.com/cert/ll-2021-009.pdf', 'renewal window open'),
    (3, 'Cargo Ship Safety Radio Certificate', 'SR-2025-077', 'ABS', '2025-06-21', '2026-06-20', 'https://docs.example.com/cert/sr-2025-077.pdf', 'GMDSS inspection required'),
    (3, 'International Tonnage Certificate', 'ITC-2020-014', 'ABS', '2020-03-01', '2030-03-01', 'https://docs.example.com/cert/itc-2020-014.pdf', 'valid'),
    (4, 'International Oil Pollution Prevention Certificate', 'IOPP-2021-041', 'LR', '2021-05-30', '2026-05-30', 'https://docs.example.com/cert/iopp-2021-041.pdf', 'annual survey pending'),
    (4, 'Classification Certificate', 'CLASS-2021-041', 'LR', '2021-10-01', '2026-10-01', 'https://docs.example.com/cert/class-2021-041.pdf', 'valid'),
    (5, 'Cargo Ship Safety Equipment Certificate', 'SE-2021-088', 'KR', '2021-05-10', '2026-05-10', 'https://docs.example.com/cert/se-2021-088.pdf', 'drydock renewal planned'),
    (5, 'Certificate of Registry', 'REG-2023-088', 'Korea Register', '2023-01-01', '2028-01-01', 'https://docs.example.com/cert/reg-2023-088.pdf', 'valid');

INSERT INTO certificates (
    vessel_id, certificate_name, certificate_number, issuing_authority,
    issue_date, expiry_date, document_url, remarks
)
SELECT
    v.vessel_id,
    cert_def.certificate_name,
    cert_def.prefix || '-' || v.vessel_id::TEXT || '-' || cert_def.seq::TEXT AS certificate_number,
    v.class_society,
    DATE '2025-01-01' + ((v.vessel_id + cert_def.seq) % 180) * INTERVAL '1 day' AS issue_date,
    DATE '2027-07-01' + ((v.vessel_id + cert_def.seq) % 365) * INTERVAL '1 day' AS expiry_date,
    'https://docs.example.com/cert/generated-' || v.vessel_id::TEXT || '-' || cert_def.seq::TEXT || '.pdf' AS document_url,
    'generated valid certificate for seed dataset' AS remarks
FROM vessels v
CROSS JOIN (
    VALUES
        (1, 'Cargo Ship Safety Certificate', 'CSS'),
        (2, 'Maritime Labour Certificate', 'MLC')
) AS cert_def(seq, certificate_name, prefix)
WHERE v.vessel_id BETWEEN 6 AND 50;

INSERT INTO compliance_documents (
    document_code, document_title, document_type, document_domain,
    applies_vessel_type, tonnage_min, tonnage_max, build_year_min, build_year_max,
    issuer, is_mandatory
) VALUES
    ('SOLAS-III', 'SOLAS Chapter III Life-Saving Appliances', 'Regulation', 'Safety', NULL, NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('SOLAS-V', 'SOLAS Chapter V Safety of Navigation', 'Regulation', 'Navigation', NULL, NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('MARPOL-I', 'MARPOL Annex I Oil Pollution Prevention', 'Regulation', 'Environment', 'Oil Tanker', NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('MARPOL-I-LNG', 'MARPOL Annex I Machinery Space Bilge Requirements', 'Regulation', 'Environment', 'LNG Carrier', NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('ISM-CODE', 'International Safety Management Code', 'Regulation', 'Management', NULL, NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('STCW-A-II', 'STCW Deck Officer Competence Standards', 'Regulation', 'Crew', NULL, NULL, NULL, NULL, NULL, 'IMO', TRUE),
    ('PSC-GENERAL', 'PSC Pre-Inspection Checklist', 'Checklist', 'Inspection', NULL, 500, NULL, NULL, NULL, 'Shipping Company', TRUE),
    ('LNG-CARGO-MANUAL', 'LNG Carrier Cargo Operation Manual', 'Manual', 'Cargo', 'LNG Carrier', NULL, NULL, NULL, NULL, 'Shipping Company', TRUE),
    ('CARGO-SYSTEM-DOC', 'LNG Cargo Handling System Doc', 'System Doc', 'Cargo', 'LNG Carrier', NULL, NULL, 2010, NULL, 'Shipyard', FALSE),
    ('PMS-ENGINE-MANUAL', 'Engine PMS Manufacturer Manual', 'Manufacturer Manual', 'Engineering', NULL, NULL, NULL, NULL, NULL, 'Equipment Maker', FALSE);

INSERT INTO compliance_documents (
    document_code, document_title, document_type, document_domain,
    applies_vessel_type, tonnage_min, tonnage_max, build_year_min, build_year_max,
    issuer, is_mandatory
)
SELECT
    'DOC-' || LPAD(gs::TEXT, 3, '0') AS document_code,
    'Generated Fleet Procedure ' || gs::TEXT AS document_title,
    CASE gs % 5
        WHEN 0 THEN 'Regulation'
        WHEN 1 THEN 'Manual'
        WHEN 2 THEN 'Checklist'
        WHEN 3 THEN 'System Doc'
        ELSE 'Manufacturer Manual'
    END AS document_type,
    CASE gs % 6
        WHEN 0 THEN 'Safety'
        WHEN 1 THEN 'Navigation'
        WHEN 2 THEN 'Cargo'
        WHEN 3 THEN 'Environment'
        WHEN 4 THEN 'Engineering'
        ELSE 'Inspection'
    END AS document_domain,
    CASE gs % 4
        WHEN 0 THEN 'Training Vessel'
        WHEN 1 THEN 'Offshore Support Vessel'
        WHEN 2 THEN 'General Cargo'
        ELSE 'Container Ship'
    END AS applies_vessel_type,
    CASE WHEN gs % 3 = 0 THEN 5000 ELSE NULL END AS tonnage_min,
    CASE WHEN gs % 7 = 0 THEN 80000 ELSE NULL END AS tonnage_max,
    CASE WHEN gs % 4 = 0 THEN 2005 ELSE NULL END AS build_year_min,
    NULL AS build_year_max,
    CASE gs % 3
        WHEN 0 THEN 'Shipping Company'
        WHEN 1 THEN 'Class Society'
        ELSE 'Equipment Maker'
    END AS issuer,
    (gs % 5 <> 0) AS is_mandatory
FROM generate_series(11, 50) AS gs;

INSERT INTO checklist_items (
    vessel_id, checklist_type, item_category, item_text,
    status, severity, due_date, completed_at, remarks
) VALUES
    (1, 'PSC', 'Safety', 'Lifeboat weekly test record verified', 'completed', 'high', '2026-05-01', '2026-05-01', 'evidence uploaded'),
    (1, 'PSC', 'Cargo', 'Cargo ESD trip test evidence prepared', 'open', 'high', '2026-05-08', NULL, 'pending cargo team confirmation'),
    (1, 'PSC', 'Safety', 'Fire door inspection log updated', 'in_progress', 'medium', '2026-05-06', NULL, 'engine team updating log'),
    (2, 'PSC', 'Deck', 'Hatch cover condition verified', 'open', 'critical', '2026-05-05', NULL, 'repair estimate requested'),
    (2, 'PSC', 'Navigation', 'Charts and publications corrected', 'completed', 'medium', '2026-05-02', '2026-05-02', 'checked by Chief Officer'),
    (3, 'PSC', 'Radio', 'GMDSS logbook checked', 'completed', 'medium', '2026-05-02', '2026-05-02', 'radio officer confirmed'),
    (3, 'PSC', 'Safety', 'Fire drill record signed by Master', 'open', 'high', '2026-05-12', NULL, 'Master signature pending'),
    (4, 'PSC', 'Environment', 'SOPEP drill evidence prepared', 'open', 'medium', '2026-05-07', NULL, 'drill photo pending'),
    (4, 'PSC', 'Environment', 'Oil Record Book entries reviewed', 'completed', 'high', '2026-05-01', '2026-05-01', 'reviewed by Chief Engineer'),
    (5, 'PSC', 'Safety', 'Muster list updated after crew change', 'open', 'high', '2026-05-03', NULL, 'update required before undocking');

INSERT INTO checklist_items (
    vessel_id, checklist_type, item_category, item_text,
    status, severity, due_date, completed_at, remarks
)
SELECT
    v.vessel_id,
    'PSC' AS checklist_type,
    CASE v.vessel_id % 5
        WHEN 0 THEN 'Documentation'
        WHEN 1 THEN 'Bridge'
        WHEN 2 THEN 'Lifesaving'
        WHEN 3 THEN 'Fire Safety'
        ELSE 'Pollution'
    END AS item_category,
    CASE v.vessel_id % 15
        WHEN 0 THEN 'Certificates validity checked'
        WHEN 1 THEN 'Crew lists and licenses verified'
        WHEN 2 THEN 'Oil Record Book updated'
        WHEN 3 THEN 'Garbage Record Book updated'
        WHEN 4 THEN 'Hours of Work and Rest records reviewed'
        WHEN 5 THEN 'Nautical publications updated with latest NtM'
        WHEN 6 THEN 'Charts corrected for intended voyage'
        WHEN 7 THEN 'Voyage plan prepared berth-to-berth'
        WHEN 8 THEN 'GMDSS daily and weekly test records available'
        WHEN 9 THEN 'Steering gear test record verified'
        WHEN 10 THEN 'Lifeboat engine start test completed within three minutes'
        WHEN 11 THEN 'Lifebuoys lights and smoke signals checked'
        WHEN 12 THEN 'Emergency Fire Pump pressure test completed'
        WHEN 13 THEN 'Fire detection panel checked with no active faults'
        ELSE 'OWS 15ppm alarm test evidence available'
    END AS item_text,
    'completed' AS status,
    CASE v.vessel_id % 3
        WHEN 0 THEN 'low'
        WHEN 1 THEN 'medium'
        ELSE 'low'
    END AS severity,
    DATE '2026-04-01' + (v.vessel_id % 30) * INTERVAL '1 day' AS due_date,
    DATE '2026-04-02' + (v.vessel_id % 30) * INTERVAL '1 day' AS completed_at,
    'PSC template item adapted from maritime operations reference pattern' AS remarks
FROM vessels v
WHERE v.vessel_id BETWEEN 6 AND 50;

INSERT INTO crew_training_records (
    vessel_id, crew_name, rank, training_name, certificate_number,
    issuing_authority, issue_date, expiry_date, is_required
) VALUES
    (1, 'Kim Minjun', 'Captain', 'Advanced Fire Fighting', 'AFF-2024-001', 'Korea Maritime Training Center', '2024-02-01', '2027-02-01', TRUE),
    (1, 'Maria Santos', 'Chief Officer', 'Advanced Cargo Operations', 'ACO-2021-014', 'SIGTTO Training Center', '2021-05-20', '2026-05-20', TRUE),
    (1, 'Lee Jisoo', '2/O', 'ECDIS Generic Training', 'ECDIS-2021-019', 'KR Academy', '2021-04-30', '2026-04-30', TRUE),
    (2, 'Ahmed Khan', 'Chief Engineer', 'Basic Safety Training', 'BST-2021-055', 'Maritime Academy', '2021-09-01', '2026-09-01', TRUE),
    (2, 'Ravi Singh', 'Bosun', 'Enclosed Space Entry', 'ESE-2021-078', 'Maritime Academy', '2021-05-15', '2026-05-15', TRUE),
    (3, 'Zhang Wei', '2/O', 'GMDSS GOC', 'GMDSS-2021-120', 'Radio School', '2021-06-10', '2026-06-10', TRUE),
    (3, 'Jose Santos', 'AB', 'Basic Safety Training', 'BST-2020-099', 'Maritime Academy', '2020-12-31', '2025-12-31', TRUE),
    (4, 'Park Hyun', 'Chief Officer', 'Oil Tanker Advanced Training', 'OTA-2021-041', 'Tanker Training Center', '2021-05-28', '2026-05-28', TRUE),
    (4, 'Chen Li', '3/E', 'Advanced Fire Fighting', 'AFF-2025-022', 'Maritime Academy', '2025-03-01', '2028-03-01', TRUE),
    (5, 'Choi Ara', 'Master', 'Medical Care', 'MED-2021-033', 'Maritime Medical Institute', '2021-05-05', '2026-05-05', TRUE);

INSERT INTO crew_training_records (
    vessel_id, crew_name, rank, training_name, certificate_number,
    issuing_authority, issue_date, expiry_date, is_required
)
SELECT
    v.vessel_id,
    'Crew Member ' || LPAD(v.vessel_id::TEXT, 3, '0') AS crew_name,
    CASE v.vessel_id % 6
        WHEN 0 THEN 'Captain'
        WHEN 1 THEN 'Chief Officer'
        WHEN 2 THEN 'Chief Engineer'
        WHEN 3 THEN '2/O'
        WHEN 4 THEN '3/E'
        ELSE 'AB'
    END AS rank,
    CASE v.vessel_id % 5
        WHEN 0 THEN 'Basic Safety Training'
        WHEN 1 THEN 'Advanced Fire Fighting'
        WHEN 2 THEN 'ECDIS Generic Training'
        WHEN 3 THEN 'Medical First Aid'
        ELSE 'Bridge Resource Management'
    END AS training_name,
    'TRN-' || v.vessel_id::TEXT || '-001' AS certificate_number,
    CASE v.vessel_id % 3
        WHEN 0 THEN 'Maritime Academy'
        WHEN 1 THEN 'KR Academy'
        ELSE 'Korea Maritime Training Center'
    END AS issuing_authority,
    DATE '2025-01-01' + (v.vessel_id % 120) * INTERVAL '1 day' AS issue_date,
    DATE '2027-01-01' + (v.vessel_id % 240) * INTERVAL '1 day' AS expiry_date,
    TRUE AS is_required
FROM vessels v
WHERE v.vessel_id BETWEEN 6 AND 50;
