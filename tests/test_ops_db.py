from web import ops_db


def test_sqlite_operational_schema_and_generated_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    with ops_db.connect(tmp_path / "operations.sqlite") as connection:
        cursor = connection.execute(
            "INSERT INTO reminder(subject_id,category,status,created_at) VALUES(?,?,?,?)",
            (42, "review", "pending", "2026-08-14T12:00:00"),
        )
        connection.commit()
        assert cursor.lastrowid > 0
        row = connection.execute("SELECT * FROM reminder WHERE id=?", (cursor.lastrowid,)).fetchone()
        assert row["subject_id"] == 42
        roles = connection.execute(
            "SELECT role FROM access_role ORDER BY sort_order"
        ).fetchall()
        assert [row["role"] for row in roles] == [
            "admin", "practitioner", "receptionist", "billing", "patient",
        ]
        for table in (
            "clinic_location", "clinic_room", "booking_policy",
            "appointment_participant", "appointment_notification",
        ):
            found = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone()
            assert found is not None
        assert connection.execute(
            "SELECT timezone FROM booking_policy WHERE code='default'"
        ).fetchone()["timezone"] == "Europe/Tallinn"


def test_explicit_ops_path_keeps_tests_off_postgres(tmp_path, monkeypatch):
    monkeypatch.delenv("FASTCLINIC_OPS_BACKEND", raising=False)
    monkeypatch.setenv("FASTCLINIC_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "isolated.sqlite"))
    assert ops_db.backend_name() == "sqlite"
