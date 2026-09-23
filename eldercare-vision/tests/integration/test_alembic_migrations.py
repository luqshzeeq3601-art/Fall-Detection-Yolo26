"""Integration tests for Alembic database migrations (P5-001)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class TestAlembicMigrations:
    """Test suite verifying Alembic migrations upgrade, downgrade, and schema consistency."""

    @pytest.fixture
    def alembic_config(self, tmp_path: Path) -> tuple[Config, str]:
        """Create a temporary SQLite database and configured Alembic Config."""
        db_file = tmp_path / "migration_test.db"
        db_url = f"sqlite:///{db_file.as_posix()}"

        root = Path(__file__).resolve().parents[2]
        ini_path = root / "alembic.ini"
        assert ini_path.is_file(), f"alembic.ini missing at {ini_path}"

        cfg = Config(str(ini_path))
        cfg.set_main_option("sqlalchemy.url", db_url)
        # Ensure script location is absolute
        script_location = str(root / "src" / "eldercare" / "db" / "migrations")
        cfg.set_main_option("script_location", script_location)

        return cfg, db_url

    def test_migration_upgrade_and_downgrade_lifecycle(
        self, alembic_config: tuple[Config, str]
    ) -> None:
        """Verify full upgrade to head, schema inspection, and clean downgrade to base."""
        cfg, db_url = alembic_config
        engine = create_engine(db_url)

        # 1. Run upgrade to head
        command.upgrade(cfg, "head")

        # 2. Inspect created schema
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        expected_tables = {
            "cameras",
            "incidents",
            "incident_evidence",
            "incident_reviews",
            "agent_enrichments",
            "alembic_version",
        }
        assert expected_tables.issubset(table_names), (
            f"Missing tables: {expected_tables - table_names}"
        )

        # 3. Verify columns in incidents table
        columns = {col["name"] for col in inspector.get_columns("incidents")}
        expected_incident_columns = {
            "id",
            "camera_id",
            "track_id",
            "started_at",
            "confirmed_at",
            "ended_at",
            "detector_state",
            "fall_score",
            "model_name",
            "model_version",
            "config_version",
            "evidence_features",
            "created_at",
        }
        assert expected_incident_columns == columns

        # 4. Insert data using raw SQL to verify constraints
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO cameras (id, name, status) VALUES ('cam-1', 'Test Cam', 'online')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO incidents (id, camera_id, track_id, started_at, confirmed_at, "
                    "detector_state, fall_score, model_name, model_version, config_version, "
                    "evidence_features) VALUES ('inc-1', 'cam-1', 'trk-1', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP, 'FALL_CONFIRMED', 0.95, 'yolo26s-pose.pt', '1.0', "
                    "'1.0', '{}')"
                )
            )
            result = conn.execute(text("SELECT count(*) FROM incidents")).scalar()
            assert result == 1

        # 5. Run downgrade to base
        command.downgrade(cfg, "base")

        # 6. Verify tables are dropped
        inspector = inspect(engine)
        post_downgrade_tables = set(inspector.get_table_names())
        # Only alembic_version might remain after downgrade to base
        assert "incidents" not in post_downgrade_tables
        assert "cameras" not in post_downgrade_tables

        # 7. Re-upgrade to head to prove idempotency
        command.upgrade(cfg, "head")
        inspector = inspect(engine)
        assert expected_tables.issubset(set(inspector.get_table_names()))
