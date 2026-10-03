import psycopg
import pytest

from bastion.config import get_settings

pytestmark = pytest.mark.integration

ENG_DOC = "ing-eng-doc"
FIN_DOC = "ing-fin-doc"


@pytest.fixture
def documents():
    settings = get_settings()

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from documents where title like 'ing-%'")
        rows = conn.execute(
            """
            insert into documents (title, source_type, department, min_level, status)
            values (%s, 'md', 'ENG', 2, 'queued'), (%s, 'pdf', 'FIN', 3, 'queued')
            returning title, id
            """,
            (ENG_DOC, FIN_DOC),
        ).fetchall()
        ids = dict(rows)
        conn.execute(
            "insert into document_blobs (document_id, content, media_type, byte_size, sha256)"
            " values (%s, %s, 'text/markdown', 5, 'abc')",
            (ids[ENG_DOC], b"# Hi!"),
        )
        conn.execute(
            "insert into jobs (document_id) values (%s), (%s)", (ids[ENG_DOC], ids[FIN_DOC])
        )
        conn.commit()

    yield ids

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from documents where title like 'ing-%'")
        conn.commit()


def app_context(conn, level, departments, is_admin):
    conn.execute(
        "select set_config('app.user_level', %s, true),"
        " set_config('app.departments', %s, true),"
        " set_config('app.is_admin', %s, true)",
        (str(level), ",".join(departments), str(is_admin).lower()),
    )


def test_the_worker_can_read_file_bytes(documents):
    with psycopg.connect(get_settings().database_url_worker) as conn:
        content = conn.execute(
            "select content from document_blobs where document_id = %s", (documents[ENG_DOC],)
        ).fetchone()[0]

    assert bytes(content) == b"# Hi!"


def test_the_web_app_cannot_read_file_bytes(documents):
    with psycopg.connect(get_settings().database_url_app) as conn:
        app_context(conn, 4, ["ENG", "HR", "FIN", "LEGAL"], is_admin=True)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select content from document_blobs")


def test_jobs_are_visible_only_for_readable_documents(documents):
    with psycopg.connect(get_settings().database_url_app) as conn:
        app_context(conn, 2, ["ENG"], is_admin=False)
        engineer_sees = conn.execute("select count(*) from jobs").fetchone()[0]

    with psycopg.connect(get_settings().database_url_app) as conn:
        app_context(conn, 4, ["ENG", "HR", "FIN", "LEGAL"], is_admin=True)
        admin_sees = conn.execute("select count(*) from jobs").fetchone()[0]

    assert engineer_sees == 1
    assert admin_sees == 2


def test_only_admins_can_queue_a_job(documents):
    with psycopg.connect(get_settings().database_url_app) as conn:
        app_context(conn, 2, ["ENG"], is_admin=False)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("insert into jobs (document_id) values (%s)", (documents[ENG_DOC],))


def test_an_oversized_file_is_rejected(documents):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into document_blobs (document_id, content, media_type, byte_size, sha256)"
                " values (%s, %s, 'text/plain', 20000000, 'x')",
                (documents[FIN_DOC], b"\x00"),
            )


def test_deleting_a_document_removes_its_blob_and_jobs(documents):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        conn.execute("delete from documents where title = %s", (ENG_DOC,))
        conn.commit()
        blobs = conn.execute(
            "select count(*) from document_blobs where document_id = %s", (documents[ENG_DOC],)
        ).fetchone()[0]
        jobs = conn.execute(
            "select count(*) from jobs where document_id = %s", (documents[ENG_DOC],)
        ).fetchone()[0]

    assert blobs == 0
    assert jobs == 0