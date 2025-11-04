"""Integration tests for database operations."""

import pytest
from src.data.database import Database
from src.data.models import Base


@pytest.fixture
def test_db() -> Database:
    """Create test database.

    Returns:
        Test database instance
    """
    db = Database("sqlite:///:memory:")
    db.create_all_tables()
    return db


def test_database_creation(test_db: Database) -> None:
    """Test database table creation."""
    # Tables should be created
    assert test_db.engine is not None


# Add more integration tests as implementation progresses
