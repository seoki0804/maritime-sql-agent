# Neon DB Verification Summary

Verification date: 2026-05-10

Schema: `maritime_sql_agent`

## Row Counts

| table_name | row_count |
|---|---:|
| vessels | 50 |
| certificates | 100 |
| compliance_documents | 50 |
| checklist_items | 55 |
| crew_training_records | 55 |

## Integrity Checks

| check | result |
|---|---:|
| Missing column comments | 0 |
| Certificates without vessel FK match | 0 |
| Checklist items without vessel FK match | 0 |
| Crew training records without vessel FK match | 0 |

## Briefing Sample Checks

| check_name | expected_sample_count |
|---|---:|
| sample_expiring_certificates_q2 | 5 |
| sample_open_high_critical_psc_q3 | 4 |
| sample_required_training_at_risk_q9 | 6 |

## Expected SQL Row Counts

| question | rows |
|---|---:|
| Q1 Easy | 1 |
| Q2 Easy | 5 |
| Q3 Easy | 4 |
| Q4 Medium | 2 |
| Q5 Medium | 50 |
| Q6 Medium | 50 |
| Q7 Medium | 9 |
| Q8 Hard | 50 |
| Q9 Hard | 6 |
| Q10 Hard | 5 |
