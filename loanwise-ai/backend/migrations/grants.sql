-- Run once against the production Postgres database, as a superuser/owner,
-- AFTER the app has created its tables (Base.metadata.create_all or a
-- proper Alembic migration). This is what makes "append-only audit log" a
-- fact enforced by the database, not a convention the application code
-- promises to follow (PRD Section 8.4).
--
-- SQLite (used for local dev in this reference implementation) has no
-- row/table-level GRANT model, so this file only takes effect in the
-- Postgres deployment target described in Section 13.

-- 1. Dedicated least-privilege role for the running application.
--    (Do not use the Postgres superuser / table owner as the app's
--    connection role in production.)
CREATE ROLE loanwise_app WITH LOGIN PASSWORD :'app_password';

-- 2. Default: no access. Grant table-by-table, deliberately.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM loanwise_app;

-- 3. Normal read/write tables the app needs full CRUD on.
GRANT SELECT, INSERT, UPDATE ON applications, predictions, model_versions,
    fairness_reports, drift_reports, users TO loanwise_app;

-- 4. The applicant_protected table is intentionally NOT granted to
--    loanwise_app at all. Only the offline fairness-audit job (running
--    under a separate `loanwise_fairness_job` role, below) can read it.
--    This is what makes "the prediction service can't join protected
--    attributes" true at the infrastructure layer, not just in application
--    code (Section 9, point 3).
CREATE ROLE loanwise_fairness_job WITH LOGIN PASSWORD :'fairness_job_password';
GRANT SELECT ON applicant_protected, applications, predictions, model_versions
    TO loanwise_fairness_job;
GRANT INSERT, SELECT ON fairness_reports TO loanwise_fairness_job;

-- 5. audit_logs: append-only. INSERT + SELECT only — explicitly no UPDATE,
--    no DELETE. Even a fully compromised application server (RCE, leaked
--    credentials, whatever) cannot rewrite or erase history through this
--    connection. Only a superuser with a direct, separately-audited
--    connection could, and Postgres logs that connection at the
--    infrastructure level (pgaudit / cloud provider audit log).
GRANT SELECT, INSERT ON audit_logs TO loanwise_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM loanwise_app;

-- 6. Sequence usage for the audit_logs BIGSERIAL id.
GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO loanwise_app;
