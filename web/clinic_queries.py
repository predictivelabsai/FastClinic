"""Read-only queries for the FastClinic GP-clinic cockpit dashboards.

All dates are ISO strings ('YYYY-MM-DD HH:MM:SS'), so lexical comparisons stay
portable while the database adapter translates the small aggregation/date
format subset that differs between SQLite and PostgreSQL.
"""
from __future__ import annotations

from web.db import query, query_one, scalar, reference_date
from pms.catalog import gender_label


def _days_ago(n: int) -> str:
    """ISO date n days before the reference 'today'."""
    from datetime import date, timedelta
    ref = date.fromisoformat(reference_date())
    return (ref - timedelta(days=n)).isoformat()


# ----------------------------------------------------------------- overview ----
def overview_kpis() -> dict:
    ref = reference_date()
    d30, d90 = _days_ago(30), _days_ago(90)
    total_patients = scalar("SELECT COUNT(*) FROM subject WHERE deceased_at IS NULL") or 0
    active_90 = scalar(
        "SELECT COUNT(DISTINCT subject_id) FROM consultation WHERE consult_at >= ?", (d90,)
    ) or 0
    visits_30 = scalar(
        "SELECT COUNT(*) FROM consultation WHERE is_visit=1 AND consult_at >= ?", (d30,)
    ) or 0
    rev_90 = scalar(
        "SELECT ROUND(SUM(line_total_vat),0) FROM item WHERE item_at >= ?", (d90,)
    ) or 0
    rev_total = scalar("SELECT ROUND(SUM(line_total_vat),0) FROM item") or 0
    clients = scalar("SELECT COUNT(*) FROM party") or 0
    return {
        "reference_date": ref,
        "total_patients": total_patients,
        "active_90": active_90,
        "visits_30": visits_30,
        "rev_90": rev_90,
        "rev_total": rev_total,
        "clients": clients,
    }


def monthly_trend(months: int = 18) -> list[dict]:
    return query(
        """
        SELECT strftime('%Y-%m', consult_at) AS month,
               COUNT(*) AS visits,
               ROUND(SUM(revenue_vat),0) AS revenue
        FROM consultation
        WHERE consult_at IS NOT NULL
        GROUP BY month ORDER BY month DESC LIMIT ?
        """,
        (months,),
    )[::-1]


def revenue_by_category() -> list[dict]:
    return query(
        """
        SELECT category, COUNT(*) AS lines, ROUND(SUM(line_total_vat),2) AS revenue
        FROM item GROUP BY category ORDER BY revenue DESC
        """
    )


def demographics_mix() -> list[dict]:
    """Patient gender distribution for the demographics chart."""
    rows = query(
        "SELECT COALESCE(gender,'?') AS gender, COUNT(*) AS n FROM subject GROUP BY gender ORDER BY n DESC"
    )
    for r in rows:
        r["label"] = gender_label(r["gender"])
    return rows


def top_services(limit: int = 12) -> list[dict]:
    return query(
        """
        SELECT name, category, COUNT(*) AS times, ROUND(SUM(line_total_vat),2) AS revenue
        FROM item
        WHERE category NOT IN ('lab')
        GROUP BY name ORDER BY revenue DESC LIMIT ?
        """,
        (limit,),
    )


# ----------------------------------------------------------------- patients ----
def patient_list(search: str = "", limit: int = 200) -> list[dict]:
    where, params = "WHERE 1=1", []
    if search.strip():
        s = search.strip()
        where += (" AND (CAST(p.id AS TEXT) LIKE ? OR p.official_name LIKE ?"
                  " OR p.city LIKE ? OR p.nhs_number LIKE ?)")
        params += [f"%{s}%"] * 4
    params.append(limit)
    return query(
        f"""
        SELECT p.id, p.party_id, p.gender, p.official_name, p.city,
               p.date_of_birth, p.deceased_at, p.critical_notes, p.nhs_number,
               (SELECT COUNT(*) FROM consultation c WHERE c.subject_id=p.id) AS visits,
               (SELECT MAX(consult_at) FROM consultation c WHERE c.subject_id=p.id) AS last_visit,
               (SELECT ROUND(SUM(line_total_vat),2) FROM item i WHERE i.subject_id=p.id) AS lifetime_value
        FROM subject p
        {where}
        ORDER BY last_visit DESC NULLS LAST
        LIMIT ?
        """,
        tuple(params),
    )


def patient_detail(pid: int) -> dict | None:
    return query_one("SELECT * FROM subject WHERE id=?", (pid,))


def patient_consultations(pid: int) -> list[dict]:
    return query(
        """
        SELECT c.id, c.consult_at, c.revenue_vat, c.item_count,
               (SELECT GROUP_CONCAT(d.name, '; ') FROM diagnosis d WHERE d.consultation_id=c.id) AS diagnoses
        FROM consultation c WHERE c.subject_id=? ORDER BY c.consult_at DESC
        """,
        (pid,),
    )


def patient_items(pid: int, limit: int = 60) -> list[dict]:
    return query(
        """SELECT name, category, quantity, line_total_vat, item_at
           FROM item WHERE subject_id=? ORDER BY item_at DESC LIMIT ?""",
        (pid, limit),
    )


def patient_value(pid: int) -> dict:
    return query_one(
        """SELECT ROUND(SUM(line_total_vat),2) AS lifetime_value,
                  COUNT(DISTINCT consultation_id) AS visits,
                  MIN(item_at) AS first_seen, MAX(item_at) AS last_seen
           FROM item WHERE subject_id=?""",
        (pid,),
    ) or {}


# ----------------------------------------------------------------- clinical ----
def diagnosis_frequency(limit: int = 20) -> list[dict]:
    return query(
        """SELECT name, COUNT(*) AS n, COUNT(DISTINCT subject_id) AS patients
           FROM diagnosis WHERE name IS NOT NULL AND name != ''
           GROUP BY name ORDER BY n DESC LIMIT ?""",
        (limit,),
    )


def specialty_mix() -> list[dict]:
    """Case mix by clinical specialty — the operations lens across departments."""
    rows = query(
        """SELECT specialty,
                  COUNT(DISTINCT consultation_id) AS cases,
                  COUNT(*) AS lines,
                  ROUND(SUM(line_total_vat), 2) AS revenue
           FROM item WHERE specialty IS NOT NULL
           GROUP BY specialty ORDER BY revenue DESC"""
    )
    from pms.catalog import specialty_label
    for r in rows:
        r["label"] = specialty_label(r["specialty"])
    return rows


def category_mix() -> list[dict]:
    """Activity by type of work (surgery, dental, consultation, diagnostics …)."""
    rows = query(
        """SELECT category, COUNT(*) AS lines, ROUND(SUM(line_total_vat), 2) AS revenue
           FROM item GROUP BY category ORDER BY revenue DESC"""
    )
    from pms.catalog import category_label
    for r in rows:
        r["label"] = category_label(r["category"])
    return rows


def top_procedures(limit: int = 15, specialty: str = "") -> list[dict]:
    """Highest-revenue named procedures/treatments (excludes routine GP lines)."""
    where = ("WHERE category IN "
             "('surgery','dental','procedure','specialist_consult','imaging','pre_op')")
    params: list = []
    if specialty:
        where += " AND specialty = ?"
        params.append(specialty)
    params.append(limit)
    rows = query(
        f"""SELECT name, specialty, category, COUNT(*) AS n,
                   ROUND(SUM(line_total_vat), 2) AS revenue
            FROM item {where}
            GROUP BY name ORDER BY revenue DESC LIMIT ?""",
        tuple(params),
    )
    from pms.catalog import specialty_label
    for r in rows:
        r["specialty_label"] = specialty_label(r["specialty"])
    return rows


def surgical_kpis() -> dict:
    """Headline operational numbers for the surgical/specialty side of the clinic."""
    row = query_one(
        """SELECT COUNT(DISTINCT specialty) AS specialties,
                  COUNT(DISTINCT CASE WHEN category='surgery' THEN consultation_id END) AS surgical_cases,
                  ROUND(SUM(CASE WHEN category='surgery' THEN line_total_vat ELSE 0 END)) AS surgical_rev,
                  ROUND(SUM(CASE WHEN specialty='dental' THEN line_total_vat ELSE 0 END)) AS dental_rev
           FROM item WHERE specialty IS NOT NULL"""
    ) or {}
    return row


def clinician_activity() -> list[dict]:
    return query(
        """SELECT clinician_id,
                  COUNT(DISTINCT consultation_id) AS consultations,
                  COUNT(*) AS line_items,
                  ROUND(SUM(line_total_vat),2) AS revenue
           FROM item WHERE clinician_id IS NOT NULL
           GROUP BY clinician_id ORDER BY revenue DESC""",
    )
