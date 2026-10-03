import psycopg
import pytest

from bastion.config import get_settings
from bastion.db import Access, access_tx

pytestmark = pytest.mark.integration

DENIED = psycopg.errors.InsufficientPrivilege


@pytest.fixture
def world():
    settings = get_settings()

    with psycopg.connect(settings.database_url_owner) as conn:
        delete_test_data(conn)
        admin_id = conn.execute(
            "insert into users (email, password_hash, level, departments, is_admin)"
            " values ('scope-admin@nimbus.test', 'x', 2, '{HR}', true) returning id"
        ).fetchone()[0]
        rows = conn.execute(
            """
            insert into documents (title, source_type, department, min_level, status)
            values ('scope-hr',       'md',  'HR',  2, 'ready'),
                   ('scope-hr-empty', 'md',  'HR',  2, 'ready'),
                   ('scope-fin',      'pdf', 'FIN', 4, 'ready')
            returning title, id
            """
        ).fetchall()
        documents = dict(rows)
        conn.execute(
            "insert into document_blobs (document_id, content, media_type, byte_size, sha256)"
            " values (%(hr)s, %(content)s, 'text/plain', 1, 'a'),"
            "        (%(fin)s, %(content)s, 'text/plain', 1, 'a')",
            {"hr": documents["scope-hr"], "fin": documents["scope-fin"], "content": b"x"},
        )
        chunk_rows = conn.execute(
            """
            insert into chunks (document_id, ordinal, text, department, min_level, quarantined)
            values (%(hr)s,  0, 'scope-hr-normal',    'ALL', 1, false),
                   (%(hr)s,  1, 'scope-hr-poisoned',  'ALL', 1, true),
                   (%(fin)s, 0, 'scope-fin-poisoned', 'ALL', 1, true)
            returning text, id
            """,
            {"hr": documents["scope-hr"], "fin": documents["scope-fin"]},
        ).fetchall()
        conn.commit()

    yield {"admin": admin_id, "documents": documents, "chunks": dict(chunk_rows)}

    with psycopg.connect(settings.database_url_owner) as conn:
        delete_test_data(conn)
        conn.commit()


def delete_test_data(conn):
    conn.execute(
        "delete from audit_log where user_id in"
        " (select id from users where email = 'scope-admin@nimbus.test')"
    )
    conn.execute("delete from documents where title like 'scope-%'")
    conn.execute("delete from users where email = 'scope-admin@nimbus.test'")


def hr_admin(world, is_admin=True):
    return Access(user_id=world["admin"], level=2, departments=("HR",), is_admin=is_admin)


def is_quarantined(chunk_id):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        row = conn.execute("select quarantined from chunks where id = %s", (chunk_id,)).fetchone()

    return row[0]


# The destructive statements below run against whatever is in the database, so each
# one ends with psycopg.Rollback: the effect is measured, then undone.
def test_an_update_without_where_touches_only_readable_documents(world):
    with access_tx(hr_admin(world)) as conn:
        readable = conn.execute("select count(*) from documents").fetchone()[0]
        changed = conn.execute("update documents set department = 'ALL', min_level = 1").rowcount
        finance_now_visible = conn.execute(
            "select count(*) from documents where title = 'scope-fin'"
        ).fetchone()[0]
        raise psycopg.Rollback

    assert changed == readable
    assert finance_now_visible == 0


def test_a_delete_without_where_removes_only_readable_documents(world):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        total = conn.execute("select count(*) from documents").fetchone()[0]

    with access_tx(hr_admin(world)) as conn:
        readable = conn.execute("select count(*) from documents").fetchone()[0]
        deleted = conn.execute("delete from documents").rowcount
        raise psycopg.Rollback

    assert deleted == readable
    assert deleted < total


def test_an_admin_cannot_raise_a_document_above_their_own_access(world):
    with pytest.raises(DENIED), access_tx(hr_admin(world)) as conn:
        conn.execute("update documents set min_level = 4 where title = 'scope-hr'")


def test_an_admin_cannot_create_a_document_they_could_not_read(world):
    with pytest.raises(DENIED), access_tx(hr_admin(world)) as conn:
        conn.execute(
            "insert into documents (title, source_type, department, min_level)"
            " values ('scope-planted', 'md', 'FIN', 4)"
        )


def test_an_admin_can_create_a_document_in_their_own_scope(world):
    with access_tx(hr_admin(world)) as conn:
        conn.execute(
            "insert into documents (title, source_type, department, min_level)"
            " values ('scope-own', 'md', 'HR', 2)"
        )
        created = conn.execute(
            "select count(*) from documents where title = 'scope-own'"
        ).fetchone()[0]
        raise psycopg.Rollback

    assert created == 1


def test_an_admin_cannot_attach_a_file_to_an_unreadable_document(world):
    with pytest.raises(DENIED), access_tx(hr_admin(world)) as conn:
        conn.execute(
            "insert into document_blobs (document_id, content, media_type, byte_size, sha256)"
            " values (%s, %s, 'text/plain', 1, 'x')",
            (world["documents"]["scope-fin"], b"x"),
        )


def test_an_admin_can_attach_a_file_to_a_readable_document(world):
    with access_tx(hr_admin(world)) as conn:
        attached = conn.execute(
            "insert into document_blobs (document_id, content, media_type, byte_size, sha256)"
            " values (%s, %s, 'text/plain', 1, 'x')",
            (world["documents"]["scope-hr-empty"], b"x"),
        ).rowcount
        raise psycopg.Rollback

    assert attached == 1


def test_a_blob_delete_without_where_leaves_unreadable_files_alone(world):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        total, readable = conn.execute(
            """
            select count(*),
                   count(*) filter (where d.min_level <= 2 and d.department in ('ALL', 'HR'))
              from document_blobs b
              join documents d on d.id = b.document_id
            """
        ).fetchone()

    with access_tx(hr_admin(world)) as conn:
        deleted = conn.execute("delete from document_blobs").rowcount
        raise psycopg.Rollback

    assert deleted == readable
    assert deleted < total


def test_an_admin_cannot_rewrite_chunk_text(world):
    with pytest.raises(DENIED), access_tx(hr_admin(world)) as conn:
        conn.execute("update chunks set text = 'tampered' where text = 'scope-hr-normal'")


def test_an_admin_can_release_a_quarantined_chunk_in_their_scope(world):
    chunk_id = world["chunks"]["scope-hr-poisoned"]

    with access_tx(hr_admin(world)) as conn:
        released = conn.execute("select release_chunk(%s)", (chunk_id,)).fetchone()[0]
        visible = conn.execute(
            "select count(*) from chunks where text = 'scope-hr-poisoned'"
        ).fetchone()[0]

    with psycopg.connect(get_settings().database_url_owner) as conn:
        logged = conn.execute(
            "select count(*) from audit_log where action = 'chunk.release'"
            " and user_id = %s and detail ->> 'chunk_id' = %s",
            (world["admin"], str(chunk_id)),
        ).fetchone()[0]

    assert released is True
    assert visible == 1
    assert logged == 1


def test_releasing_a_chunk_outside_the_admins_scope_does_nothing(world):
    chunk_id = world["chunks"]["scope-fin-poisoned"]

    with access_tx(hr_admin(world)) as conn:
        released = conn.execute("select release_chunk(%s)", (chunk_id,)).fetchone()[0]

    assert released is False
    assert is_quarantined(chunk_id) is True


def test_a_release_with_no_user_is_refused(world):
    chunk_id = world["chunks"]["scope-hr-poisoned"]
    nobody = Access(user_id="", level=2, departments=("HR",), is_admin=True)

    with access_tx(nobody) as conn:
        released = conn.execute("select release_chunk(%s)", (chunk_id,)).fetchone()[0]

    assert released is False
    assert is_quarantined(chunk_id) is True


def test_a_non_admin_cannot_release_a_chunk(world):
    chunk_id = world["chunks"]["scope-hr-poisoned"]

    with access_tx(hr_admin(world, is_admin=False)) as conn:
        released = conn.execute("select release_chunk(%s)", (chunk_id,)).fetchone()[0]

    assert released is False
    assert is_quarantined(chunk_id) is True
