import psycopg
import pytest

from bastion.auth.login import authenticate
from bastion.config import get_settings
from bastion.db import access_tx
from bastion.seed import PERSONAS, seed_personas

pytestmark = pytest.mark.integration

PASSWORD = "matrix-test-password"

DOCUMENTS = [
    ("matrix-handbook", "ALL", 1),
    ("matrix-runbook", "ENG", 2),
    ("matrix-design", "ENG", 3),
    ("matrix-leave", "HR", 2),
    ("matrix-salaries", "HR", 3),
    ("matrix-expenses", "FIN", 2),
    ("matrix-budget", "FIN", 3),
    ("matrix-contracts", "LEGAL", 3),
    ("matrix-board", "ALL", 4),
]

# Written out by hand rather than computed, so the test does not repeat the rule it checks.
EXPECTED = {
    "intern@nimbus.test": ["matrix-handbook"],
    "engineer@nimbus.test": ["matrix-handbook", "matrix-runbook"],
    "eng.manager@nimbus.test": ["matrix-design", "matrix-handbook", "matrix-runbook"],
    "hr.specialist@nimbus.test": ["matrix-handbook", "matrix-leave"],
    "hr.manager@nimbus.test": ["matrix-handbook", "matrix-leave", "matrix-salaries"],
    "finance.analyst@nimbus.test": ["matrix-expenses", "matrix-handbook"],
    "legal.counsel@nimbus.test": ["matrix-contracts", "matrix-handbook"],
    "cfo@nimbus.test": sorted(title for title, _, _ in DOCUMENTS),
}


@pytest.fixture(scope="module")
def grid():
    settings = get_settings()
    emails = [email for email, *_ in PERSONAS]

    with psycopg.connect(settings.database_url_owner) as conn:
        before = conn.execute(
            "select email, password_hash from users where email = any(%s)", (emails,)
        ).fetchall()
        seed_personas(conn, PASSWORD)

        conn.execute("delete from documents where title like 'matrix-%'")
        for title, department, min_level in DOCUMENTS:
            document_id = conn.execute(
                "insert into documents (title, source_type, department, min_level, status)"
                " values (%s, 'md', %s, %s, 'ready') returning id",
                (title, department, min_level),
            ).fetchone()[0]
            conn.execute(
                "insert into chunks (document_id, ordinal, text, department, min_level)"
                " values (%s, 0, %s, 'ALL', 1)",
                (document_id, title),
            )
        conn.commit()

    yield

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from documents where title like 'matrix-%'")
        for email, password_hash in before:
            conn.execute(
                "update users set password_hash = %s where email = %s", (password_hash, email)
            )
        conn.commit()


def test_the_matrix_covers_every_persona():
    assert set(EXPECTED) == {email for email, *_ in PERSONAS}


@pytest.mark.parametrize("email", list(EXPECTED))
def test_each_persona_sees_exactly_their_documents_and_chunks(grid, email):
    access = authenticate(email, PASSWORD)

    with access_tx(access) as conn:
        documents = conn.execute(
            "select title from documents where title like 'matrix-%' order by title"
        ).fetchall()
        chunks = conn.execute(
            "select text from chunks where text like 'matrix-%' order by text"
        ).fetchall()

    assert [row[0] for row in documents] == EXPECTED[email]
    assert [row[0] for row in chunks] == EXPECTED[email]
