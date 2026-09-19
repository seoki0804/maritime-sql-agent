CREATE SCHEMA IF NOT EXISTS maritime_sql_agent;

SET search_path TO maritime_sql_agent, public;

DROP TABLE IF EXISTS crew_training_records CASCADE;
DROP TABLE IF EXISTS checklist_items CASCADE;
DROP TABLE IF EXISTS certificates CASCADE;
DROP TABLE IF EXISTS compliance_documents CASCADE;
DROP TABLE IF EXISTS vessels CASCADE;

CREATE TABLE vessels (
    vessel_id        SERIAL PRIMARY KEY,
    vessel_name      VARCHAR(120) NOT NULL,
    imo_number       VARCHAR(20) NOT NULL UNIQUE,
    vessel_type      VARCHAR(80) NOT NULL,
    gross_tonnage    INT NOT NULL CHECK (gross_tonnage > 0),
    build_year       INT NOT NULL CHECK (build_year >= 1900),
    flag_state       VARCHAR(80) NOT NULL,
    class_society    VARCHAR(40),
    operating_status VARCHAR(20) NOT NULL CHECK (operating_status IN ('active', 'drydock', 'inactive'))
);

COMMENT ON TABLE vessels IS '관리 대상 선박의 기본 제원과 운항 상태';
COMMENT ON COLUMN vessels.vessel_id IS '선박 고유 식별자';
COMMENT ON COLUMN vessels.vessel_name IS '선박명';
COMMENT ON COLUMN vessels.imo_number IS 'IMO Number';
COMMENT ON COLUMN vessels.vessel_type IS '선종: LNG Carrier, Bulk Carrier, Oil Tanker 등';
COMMENT ON COLUMN vessels.gross_tonnage IS '총톤수 GT';
COMMENT ON COLUMN vessels.build_year IS '선박 건조 연도';
COMMENT ON COLUMN vessels.flag_state IS '기국';
COMMENT ON COLUMN vessels.class_society IS '선급: KR, DNV, ABS, LR 등';
COMMENT ON COLUMN vessels.operating_status IS '운항 상태: active, drydock, inactive';

CREATE TABLE certificates (
    certificate_id     SERIAL PRIMARY KEY,
    vessel_id          INT NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    certificate_name   VARCHAR(160) NOT NULL,
    certificate_number VARCHAR(80),
    issuing_authority  VARCHAR(120),
    issue_date         DATE,
    expiry_date        DATE NOT NULL,
    document_url       TEXT,
    remarks            TEXT
);

COMMENT ON TABLE certificates IS '선박별 certificate와 만료일 관리 정보';
COMMENT ON COLUMN certificates.certificate_id IS 'Certificate 고유 식별자';
COMMENT ON COLUMN certificates.vessel_id IS 'Certificate가 연결된 선박 ID';
COMMENT ON COLUMN certificates.certificate_name IS 'Certificate 이름';
COMMENT ON COLUMN certificates.certificate_number IS 'Certificate 번호';
COMMENT ON COLUMN certificates.issuing_authority IS '발급 기관 또는 선급';
COMMENT ON COLUMN certificates.issue_date IS '발급일';
COMMENT ON COLUMN certificates.expiry_date IS '만료일';
COMMENT ON COLUMN certificates.document_url IS '스캔 PDF 또는 전자 문서 링크';
COMMENT ON COLUMN certificates.remarks IS '비고 또는 OCR 확인 메모';

CREATE TABLE compliance_documents (
    document_id         SERIAL PRIMARY KEY,
    document_code       VARCHAR(80) NOT NULL UNIQUE,
    document_title      VARCHAR(220) NOT NULL,
    document_type       VARCHAR(40) NOT NULL CHECK (document_type IN ('Regulation', 'Manual', 'Checklist', 'System Doc', 'Manufacturer Manual')),
    document_domain     VARCHAR(50) NOT NULL,
    applies_vessel_type VARCHAR(80),
    tonnage_min         INT CHECK (tonnage_min IS NULL OR tonnage_min >= 0),
    tonnage_max         INT CHECK (tonnage_max IS NULL OR tonnage_max >= 0),
    build_year_min      INT CHECK (build_year_min IS NULL OR build_year_min >= 1900),
    build_year_max      INT CHECK (build_year_max IS NULL OR build_year_max >= 1900),
    issuer              VARCHAR(120),
    is_mandatory        BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (tonnage_min IS NULL OR tonnage_max IS NULL OR tonnage_min <= tonnage_max),
    CHECK (build_year_min IS NULL OR build_year_max IS NULL OR build_year_min <= build_year_max)
);

COMMENT ON TABLE compliance_documents IS '선박별 적용 가능성을 판단할 Regulation, Manual, Checklist, System Doc 목록';
COMMENT ON COLUMN compliance_documents.document_id IS '근거 문서 고유 식별자';
COMMENT ON COLUMN compliance_documents.document_code IS '문서 코드 또는 약어';
COMMENT ON COLUMN compliance_documents.document_title IS '문서 제목';
COMMENT ON COLUMN compliance_documents.document_type IS '문서 유형: Regulation, Manual, Checklist, System Doc, Manufacturer Manual';
COMMENT ON COLUMN compliance_documents.document_domain IS '문서 업무 영역: Safety, Navigation, Cargo, Environment 등';
COMMENT ON COLUMN compliance_documents.applies_vessel_type IS '적용 선종. NULL이면 모든 선종에 적용';
COMMENT ON COLUMN compliance_documents.tonnage_min IS '적용 최소 GT. NULL이면 하한 없음';
COMMENT ON COLUMN compliance_documents.tonnage_max IS '적용 최대 GT. NULL이면 상한 없음';
COMMENT ON COLUMN compliance_documents.build_year_min IS '적용 최소 건조 연도. NULL이면 하한 없음';
COMMENT ON COLUMN compliance_documents.build_year_max IS '적용 최대 건조 연도. NULL이면 상한 없음';
COMMENT ON COLUMN compliance_documents.issuer IS '발행 기관, 회사, 제조사';
COMMENT ON COLUMN compliance_documents.is_mandatory IS '필수 적용 문서 여부';

CREATE TABLE checklist_items (
    item_id        SERIAL PRIMARY KEY,
    vessel_id      INT NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    checklist_type VARCHAR(30) NOT NULL CHECK (checklist_type IN ('PSC', 'FSC', 'Vetting', 'Audit')),
    item_category  VARCHAR(60) NOT NULL,
    item_text      TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL CHECK (status IN ('open', 'in_progress', 'completed', 'deferred')),
    severity       VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    due_date       DATE,
    completed_at   DATE,
    remarks        TEXT,
    CHECK (completed_at IS NULL OR due_date IS NULL OR completed_at >= due_date - INTERVAL '365 days')
);

COMMENT ON TABLE checklist_items IS 'PSC, FSC, Vetting, Audit 준비를 위한 선박별 체크리스트 항목';
COMMENT ON COLUMN checklist_items.item_id IS '체크리스트 항목 고유 식별자';
COMMENT ON COLUMN checklist_items.vessel_id IS '체크리스트가 연결된 선박 ID';
COMMENT ON COLUMN checklist_items.checklist_type IS '점검 유형: PSC, FSC, Vetting, Audit';
COMMENT ON COLUMN checklist_items.item_category IS '점검 카테고리: Bridge, Deck, Engine, Safety 등';
COMMENT ON COLUMN checklist_items.item_text IS '점검 항목 내용';
COMMENT ON COLUMN checklist_items.status IS '항목 처리 상태';
COMMENT ON COLUMN checklist_items.severity IS '미완료 시 중요도';
COMMENT ON COLUMN checklist_items.due_date IS '조치 기한';
COMMENT ON COLUMN checklist_items.completed_at IS '완료일';
COMMENT ON COLUMN checklist_items.remarks IS '점검 비고';

CREATE TABLE crew_training_records (
    training_id        SERIAL PRIMARY KEY,
    vessel_id          INT NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    crew_name          VARCHAR(120) NOT NULL,
    rank               VARCHAR(80) NOT NULL,
    training_name      VARCHAR(160) NOT NULL,
    certificate_number VARCHAR(80),
    issuing_authority  VARCHAR(120),
    issue_date         DATE NOT NULL,
    expiry_date        DATE,
    is_required        BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (expiry_date IS NULL OR expiry_date >= issue_date)
);

COMMENT ON TABLE crew_training_records IS '선원별 STCW 및 직무 교육 certificate 이력';
COMMENT ON COLUMN crew_training_records.training_id IS '교육 이력 고유 식별자';
COMMENT ON COLUMN crew_training_records.vessel_id IS '선원이 배정된 선박 ID';
COMMENT ON COLUMN crew_training_records.crew_name IS '선원 이름';
COMMENT ON COLUMN crew_training_records.rank IS '직급: Captain, Chief Officer, 2/O, Chief Engineer 등';
COMMENT ON COLUMN crew_training_records.training_name IS '교육 또는 certificate 이름';
COMMENT ON COLUMN crew_training_records.certificate_number IS '교육 certificate 번호';
COMMENT ON COLUMN crew_training_records.issuing_authority IS '교육 발급 기관';
COMMENT ON COLUMN crew_training_records.issue_date IS '교육 certificate 발급일';
COMMENT ON COLUMN crew_training_records.expiry_date IS '교육 certificate 만료일. NULL이면 만료 없음';
COMMENT ON COLUMN crew_training_records.is_required IS '승선 또는 직무 수행에 필수인 교육 여부';

CREATE INDEX idx_certificates_vessel_expiry
    ON certificates (vessel_id, expiry_date);

CREATE INDEX idx_checklist_vessel_type_status
    ON checklist_items (vessel_id, checklist_type, status, severity);

CREATE INDEX idx_training_vessel_expiry
    ON crew_training_records (vessel_id, expiry_date);

CREATE INDEX idx_documents_matching_rules
    ON compliance_documents (applies_vessel_type, tonnage_min, tonnage_max, build_year_min, build_year_max);

