"""Versioned Europe-wide specialty and treatment-family taxonomy.

The first eight specialties and their body-area families follow the public My
Medical Gateway navigation model. FastClinic extends it for the broader private
clinic and wellness market. Raw clinic labels always remain on observations.
"""

from __future__ import annotations

import re


VERSION = "2026.09"
HIERARCHY = {
    "orthopaedics": ("Orthopaedics", ("hip", "knee", "shoulder", "spine", "foot and ankle", "sports injury"), "mymedicalgateway"),
    "gynaecology": ("Gynaecology", ("uterus", "ovaries", "endometriosis", "fertility"), "mymedicalgateway"),
    "ent": ("Ear, nose and throat", ("ear", "nose and sinus", "throat", "thyroid"), "mymedicalgateway"),
    "urology": ("Urology", ("prostate", "bladder", "ureter and kidney"), "mymedicalgateway"),
    "ophthalmology": ("Ophthalmology", ("cataract", "cornea", "glaucoma", "retina"), "mymedicalgateway"),
    "general_surgery": ("General surgery", ("bowel", "stomach", "gallbladder", "hernia"), "mymedicalgateway"),
    "cardiac": ("Cardiac", ("devices", "coronary intervention", "cardiac surgery", "vascular"), "mymedicalgateway"),
    "cosmetic": ("Cosmetic and corrective surgery", ("face", "breast", "body contouring", "hair restoration"), "mymedicalgateway"),
    "wellness": ("Wellness and longevity", ("IV therapy", "longevity", "preventive health", "recovery"), "fastclinic"),
    "diagnostics": ("Diagnostics and imaging", ("laboratory", "MRI and CT", "ultrasound", "endoscopy"), "fastclinic"),
    "oncology": ("Oncology", ("medical oncology", "radiotherapy", "cancer surgery"), "fastclinic"),
    "dental": ("Dental", ("implantology", "orthodontics", "oral surgery", "general dentistry"), "fastclinic"),
    "dermatology": ("Dermatology", ("medical dermatology", "aesthetic dermatology"), "fastclinic"),
    "bariatric": ("Bariatric and metabolic medicine", ("bariatric surgery", "metabolic care"), "fastclinic"),
    "rehabilitation": ("Rehabilitation and physiotherapy", ("physiotherapy", "inpatient rehabilitation"), "fastclinic"),
    "primary_care": ("Primary care", ("general practice", "internal medicine", "health screening"), "fastclinic"),
    "mental_health": ("Mental health", ("psychiatry", "psychology", "addiction care"), "fastclinic"),
}

RULES = (
    ("wellness:IV therapy", r"\biv\b|intraven|infus|infuz|laš|perfuzi|vitamin drip|glutath|nad\+"),
    ("wellness:longevity", r"longevity|anti[ -]?aging|ilgaamž"),
    ("orthopaedics:knee", r"knee|genunch|kelio|põlv|knie"),
    ("orthopaedics:hip", r"hip replacement|șold|klubo|puus|hüfte"),
    ("orthopaedics:spine", r"spine|spinal|disc(?:ectomy)?|stubur|selg|wirbelsäule"),
    ("gynaecology:uterus", r"hysterect|uter|fibroid|gimdos|dzemd"),
    ("urology:prostate", r"prostat"),
    ("ophthalmology:cataract", r"cataract|katarakt"),
    ("general_surgery:gallbladder", r"gallbladder|cholecyst|tulž|žultspūsl"),
    ("cardiac:coronary intervention", r"coronar|angioplast|cardiol|kardiol"),
    ("diagnostics:laboratory", r"laborator|blood test|kraujo tyr|analiz"),
    ("diagnostics:MRI and CT", r"\bmri\b|magnetic resonance|\bct\b|tomograph"),
    ("dental:implantology", r"dental implant|tooth implant|dantų implant|zahnimplant"),
    ("dermatology:medical dermatology", r"dermatolog"),
    ("bariatric:bariatric surgery", r"bariatric|gastric bypass|sleeve gastrect"),
    ("rehabilitation:physiotherapy", r"physiotherap|fizioterap|rehabilit"),
    ("primary_care:general practice", r"general practice|family medicine|perearst|šeimos gyd|ģimenes ār"),
    ("mental_health:psychiatry", r"psychiatr"),
)


def nodes():
    result = []
    for specialty, (label, families, source) in HIERARCHY.items():
        result.append(
            {"id": specialty, "parent_id": None, "level": "specialty", "label": label, "source": source}
        )
        result.extend(
            {
                "id": f"{specialty}:{family}",
                "parent_id": specialty,
                "level": "family",
                "label": family.title(),
                "source": source,
            }
            for family in families
        )
    return result


def ensure(connection) -> None:
    if connection.execute(
        "SELECT id FROM market_taxonomy_node WHERE version=? LIMIT 1", (VERSION,)
    ).fetchone():
        return
    for row in nodes():
        connection.execute(
            """INSERT INTO market_taxonomy_node
            (id,parent_id,level,label,source,version) VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,level=excluded.level,
             label=excluded.label,source=excluded.source,version=excluded.version""",
            (
                row["id"], row["parent_id"], row["level"], row["label"],
                row["source"], VERSION,
            ),
        )


def classify(text: str):
    value = str(text or "")
    for taxonomy_id, pattern in RULES:
        if re.search(pattern, value, re.I):
            return taxonomy_id
    return None


def map_service(connection, service_id: str, text: str) -> str | None:
    taxonomy_id = classify(text)
    if not taxonomy_id:
        return None
    connection.execute(
        """INSERT INTO market_service_taxonomy
        (service_id,taxonomy_id,method,confidence,version)
        VALUES (?,?,?,?,?) ON CONFLICT(service_id) DO NOTHING""",
        (service_id, taxonomy_id, "rule", "high", VERSION),
    )
    return taxonomy_id
