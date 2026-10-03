CREATE FUNCTION app_can_read(p_min_level int, p_department text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT coalesce(
        p_min_level <= app_level()
        AND (p_department = 'ALL' OR p_department = ANY (app_departments())),
        false
    )
$$;

REVOKE SELECT ON users FROM bastion_worker;

CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));

-- Postgres applies the read policy to an UPDATE or DELETE only when the statement
-- has to read rows (a WHERE or RETURNING). Without one, only the write policy runs,
-- so every write policy must repeat the read test itself.
DROP POLICY documents_insert ON documents;
DROP POLICY documents_update ON documents;
DROP POLICY documents_delete ON documents;

CREATE POLICY documents_insert ON documents FOR INSERT
WITH CHECK (
    current_user = 'bastion_worker'
    OR (app_is_admin() AND app_can_read(min_level, department))
);

CREATE POLICY documents_update ON documents FOR UPDATE
USING (
    current_user = 'bastion_worker'
    OR (app_is_admin() AND app_can_read(min_level, department))
)
WITH CHECK (
    current_user = 'bastion_worker'
    OR (app_is_admin() AND app_can_read(min_level, department))
);

CREATE POLICY documents_delete ON documents FOR DELETE
USING (app_is_admin() AND app_can_read(min_level, department));

DROP POLICY blobs_admin_insert ON document_blobs;
DROP POLICY blobs_admin_delete ON document_blobs;

CREATE POLICY blobs_admin_insert ON document_blobs FOR INSERT
WITH CHECK (
    app_is_admin()
    AND EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id)
);

CREATE POLICY blobs_admin_delete ON document_blobs FOR DELETE
USING (
    app_is_admin()
    AND EXISTS (SELECT 1 FROM documents d WHERE d.id = document_blobs.document_id)
);

DROP POLICY chunks_admin_update ON chunks;
REVOKE UPDATE ON chunks FROM bastion_app;

-- Every refusal returns the same false, so the result cannot be used to find out
-- whether a chunk exists. A release with no user is refused so that every release
-- in the audit log has an actor.
CREATE FUNCTION release_chunk(p_chunk_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    released boolean;
BEGIN
    IF NOT app_is_admin() OR app_user() IS NULL THEN
        RETURN false;
    END IF;

    UPDATE chunks c
       SET quarantined = false
     WHERE c.id = p_chunk_id
       AND c.quarantined
       AND app_can_read(c.min_level, c.department)
    RETURNING true INTO released;

    IF released IS NOT TRUE THEN
        RETURN false;
    END IF;

    INSERT INTO audit_log (user_id, action, detail)
    VALUES (app_user(), 'chunk.release', jsonb_build_object('chunk_id', p_chunk_id));

    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION release_chunk(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION release_chunk(uuid) TO bastion_app;
