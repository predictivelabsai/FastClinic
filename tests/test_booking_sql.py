import pytest

from web import booking_sql, ops_db


@pytest.fixture()
def booking_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "booking.sqlite"))
    with ops_db.connect():
        pass


def test_schema_context_contains_ingested_and_operational_booking_models():
    document = booking_sql.schema_document()
    assert "treatment" in document["tables"]
    assert "appointment_type" in document["fastclinic_booking_context"]["tables"]
    assert "clinic_room" in document["fastclinic_booking_context"]["allowed_tables"]
    assert "subject" not in document["fastclinic_booking_context"]["allowed_tables"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM appointment",
    "SELECT subject_id FROM appointment",
    "SELECT * FROM appointment",
    "SELECT * FROM user",
    "SELECT * FROM appointment; SELECT * FROM appointment_type",
    "PRAGMA table_info(appointment)",
])
def test_booking_sql_rejects_mutation_sensitive_and_unapproved_queries(sql):
    with pytest.raises(booking_sql.BookingSQLError):
        booking_sql.validate_sql(sql)


def test_booking_sql_executes_approved_bounded_select(booking_db):
    rows = booking_sql.run_sql(
        "SELECT code,name,duration_min FROM appointment_type WHERE active=1 ORDER BY name"
    )
    assert rows and {row["code"] for row in rows} >= {"general", "dermatology"}


def test_booking_sql_caps_model_supplied_limit():
    sql = booking_sql.validate_sql(
        "SELECT code,name FROM appointment_type LIMIT 999999", limit=50,
    )
    assert sql.endswith("LIMIT 50")


def test_text_to_sql_uses_model_but_enforces_guard(booking_db, monkeypatch):
    class Response:
        content = "```sql\nSELECT code,name,duration_min FROM appointment_type WHERE active=1\n```"

    class Model:
        def invoke(self, messages):
            assert "fastclinic_booking_context" not in str(messages)
            return Response()

    from graph import clinic_assistant
    monkeypatch.setattr(clinic_assistant, "make_model", lambda: Model())
    sql = booking_sql.text_to_sql("I need a dermatology consultation")
    assert sql.startswith("SELECT") and "LIMIT 50" in sql
    assert booking_sql.run_sql(sql)
