ALTER TABLE documents DROP CONSTRAINT documents_source_type_check;

ALTER TABLE documents ADD CONSTRAINT documents_source_type_check
    CHECK (source_type IN ('md', 'txt', 'html', 'pdf', 'docx', 'slack'));