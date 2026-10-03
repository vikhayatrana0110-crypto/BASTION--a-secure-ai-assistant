import psycopg
import pytest

from bastion.config import get_settings

pytestmark = pytest.mark.integration

EMAIL = "privilege-test@nimbus.test"


@pytest.fixture
def user():
    settings = get_settings()

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from users where email ilike %s", (EMAIL,))
        user_id = conn.execute(
            "insert into users (email, password_hash, level, departments)"
            " values (%s, 'x', 2, '{HR}') returning id",
            (EMAIL,),
        ).fetchone()[0]
        conn.commit()

    yield user_id

    with psycopg.connect(settings.database_url_owner) as conn:
        conn.execute("delete from users where email ilike %s", (EMAIL,))
        conn.commit()


def test_the_worker_cannot_read_users_even_with_a_forged_context(user):
    with psycopg.connect(get_settings().database_url_worker) as conn:
        conn.execute("select set_config('app.user_id', %s, true)", (str(user),))

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select password_hash from users")


def test_emails_are_unique_regardless_of_case(user):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                "insert into users (email, password_hash, level, departments)"
                " values (%s, 'x', 1, '{ENG}')",
                (EMAIL.upper(),),
            )
