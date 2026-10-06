import psycopg
import pytest

from bastion.config import get_settings
from bastion.ingestion.validate import TYPES

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("source_type", sorted({source_type for source_type, _ in TYPES.values()}))
def test_the_database_accepts_every_type_the_validator_returns(source_type):
    with psycopg.connect(get_settings().database_url_owner) as conn:
        conn.execute(
            "insert into documents (title, source_type, department, min_level)"
            " values ('type-check', %s, 'ALL', 1)",
            (source_type,),
        )
        conn.rollback()