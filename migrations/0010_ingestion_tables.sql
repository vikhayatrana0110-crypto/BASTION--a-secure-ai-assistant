CREATE TABLE document_blobs (
    document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    content     bytea NOT NULL,
    media_type  text NOT NULL,
    byte_size   int  NOT NULL CHECK (byte_size > 0 AND byte_size <= 10485760),
    sha256      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version     int  NOT NULL DEFAULT 1,
    status      text NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts    int  NOT NULL DEFAULT 0,
    last_error  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz
);

CREATE INDEX jobs_queued_idx ON jobs (status, created_at) WHERE status = 'queued';

GRANT INSERT, DELETE ON document_blobs TO bastion_app;
GRANT SELECT, DELETE ON document_blobs TO bastion_worker;
GRANT SELECT, INSERT ON jobs TO bastion_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO bastion_worker;

ALTER TABLE document_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_blobs FORCE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY blobs_worker_all ON document_blobs FOR ALL TO bastion_worker
USING (true) WITH CHECK (true);

CREATE POLICY blobs_admin_insert ON document_blobs FOR INSERT
WITH CHECK (app_is_admin());

CREATE POLICY blobs_admin_delete ON document_blobs FOR DELETE
USING (app_is_admin());

CREATE POLICY jobs_worker_all ON jobs FOR ALL TO bastion_worker
USING (true) WITH CHECK (true);

CREATE POLICY jobs_read ON jobs FOR SELECT
USING (EXISTS (SELECT 1 FROM documents d WHERE d.id = jobs.document_id));

CREATE POLICY jobs_admin_insert ON jobs FOR INSERT
WITH CHECK (app_is_admin() AND EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id));