import psycopg
import pytest

from bastion.config import get_settings
from bastion.db import Access, access_tx, get_pool

pytestmark = pytest.mark.integration

USER_ID = "11111111-1111-1111-1111-111111111111"
VISIBLE = "select text from chunks where text like 'chunkread-%' order by text"


@pytest.fixture
def chunks():
    settings = get_settings()

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from documents where title like 'chunkread-%'")
        rows = conn.execute(
            """
            insert into documents (title, source_type, department, min_level, status)
            values ('chunkread-handbook', 'md',  'ALL', 1, 'ready'),
                   ('chunkread-runbook',  'md',  'ENG', 2, 'ready'),
                   ('chunkread-design',   'md',  'ENG', 3, 'ready'),
                   ('chunkread-budget',   'pdf', 'FIN', 3, 'ready')
            returning title, id
            """
        ).fetchall()
        ids = dict(rows)

        for title, document_id in ids.items():
            conn.execute(
                "insert into chunks (document_id, ordinal, text, department, min_level)"
                " values (%s, 0, %s, 'ALL', 1)",
                (document_id, title),
            )

        conn.execute(
            "insert into chunks (document_id, ordinal, text, department, min_level, quarantined)"
            " values (%s, 1, 'chunkread-runbook-poisoned', 'ALL', 1, true)",
            (ids["chunkread-runbook"],),
        )
        conn.commit()

    yield

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from documents where title like 'chunkread-%'")
        conn.commit()


def visible_chunks(level, departments, is_admin=False):
    access = Access(user_id=USER_ID, level=level, departments=departments, is_admin=is_admin)

    with access_tx(access) as conn:
        return [row[0] for row in conn.execute(VISIBLE).fetchall()]


def test_no_context_sees_no_chunks(chunks):
    with get_pool().connection() as conn:
        rows = conn.execute(VISIBLE).fetchall()

    assert rows == []


def test_level_boundary_applies_to_chunks(chunks):
    assert visible_chunks(2, ("ENG",)) == ["chunkread-handbook", "chunkread-runbook"]


def test_department_boundary_applies_to_chunks(chunks):
    assert visible_chunks(2, ("FIN",)) == ["chunkread-handbook"]


def test_quarantined_chunks_are_hidden_even_from_an_executive_admin(chunks):
    assert visible_chunks(4, ("ENG", "HR", "FIN", "LEGAL"), is_admin=True) == [
        "chunkread-budget",
        "chunkread-design",
        "chunkread-handbook",
        "chunkread-runbook",
    ]


def test_the_worker_sees_every_chunk_including_quarantined(chunks):
    with psycopg.connect(get_settings().database_url_worker) as conn:
        rows = conn.execute(VISIBLE).fetchall()

    assert len(rows) == 5
