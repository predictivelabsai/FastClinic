"""Public compliance, trust, and interoperability roadmap for FastClinic."""

from fasthtml.common import *

from .account_auth import AUTH_CSS, AUTH_JS, auth_modal
from .i18n import t
from .landing import CSS as LANDING_CSS
from .landing import FAVICON, LANGUAGE_JS, language_switcher
from .seo import seo_meta


COMPLIANCE_CSS = """
.trust{--accent:#1e6fb8;--deep:#123a5c;--tint:#eef7ff;--ink:#111827;--muted:#667085;--line:#e7eaf0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:var(--ink)}
.trust *{box-sizing:border-box}.trust-main{overflow:hidden}.trust-wrap{width:min(1120px,calc(100% - 48px));margin-inline:auto}.trust-hero{padding:88px 0 64px;background:radial-gradient(circle at 82% 8%,rgba(30,111,184,.14),transparent 34%),linear-gradient(180deg,#fff 0%,#f7fbff 100%);border-bottom:1px solid var(--line)}
.trust-kicker{display:block;color:var(--accent);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.16em}.trust-hero h1{max-width:920px;margin:18px 0 22px;font-size:clamp(42px,6.5vw,72px);line-height:1.03;letter-spacing:-.052em}.trust-lede{max-width:810px;margin:0;color:var(--muted);font-size:20px;line-height:1.65}
.trust-pills{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}.trust-pill{display:inline-flex;align-items:center;gap:8px;padding:9px 13px;border:1px solid rgba(30,111,184,.2);border-radius:999px;background:#fff;color:var(--deep);font-size:13px;font-weight:700}.trust-dot{width:8px;height:8px;border-radius:50%;background:#1f9d68}.trust-dot.plan{background:#d08b18}
.trust-section{padding:72px 0;border-bottom:1px solid var(--line);scroll-margin-top:72px}.trust-section.tint{background:var(--tint)}.trust-head{max-width:780px;margin-bottom:30px}.trust-head h2{margin:10px 0 12px;font-size:clamp(30px,4vw,42px);letter-spacing:-.035em}.trust-head p,.trust-copy{color:var(--muted);font-size:16px;line-height:1.7}.trust-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.trust-card{padding:24px;border:1px solid var(--line);border-radius:18px;background:#fff;box-shadow:0 8px 28px rgba(17,24,39,.035)}.trust-card h3{margin:0 0 10px;font-size:19px}.trust-card p{margin:0;color:var(--muted);line-height:1.6}.trust-card .trust-label{display:block;margin-bottom:16px;color:var(--accent);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.1em}
.trust-list{margin:0;padding-left:20px;color:var(--muted);line-height:1.65}.trust-list li+li{margin-top:10px}.trust-list strong{color:var(--ink)}.trust-two{display:grid;grid-template-columns:1.05fr .95fr;gap:38px;align-items:start}.trust-callout{padding:24px;border-left:4px solid var(--accent);border-radius:0 16px 16px 0;background:var(--tint);color:var(--deep);line-height:1.65}.trust-callout p{margin:0}.trust-callout p+p{margin-top:12px}
.trust-table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:18px;background:#fff}.trust-table{width:100%;border-collapse:collapse;min-width:720px}.trust-table th,.trust-table td{padding:15px 18px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:14px;line-height:1.5}.trust-table th{background:#f8fafc;color:var(--deep);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.trust-table tr:last-child td{border-bottom:0}.trust-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);font-weight:700}
.adapter-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.adapter-card{padding:24px;border:1px solid rgba(30,111,184,.18);border-radius:18px;background:rgba(255,255,255,.9)}.adapter-top{display:flex;align-items:start;justify-content:space-between;gap:12px}.adapter-card h3{margin:0;font-size:20px}.adapter-status{flex:none;padding:5px 9px;border-radius:999px;background:#fff2da;color:#855800;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}.adapter-card p{color:var(--muted);line-height:1.6}.trust-link{color:var(--accent);font-size:13px;font-weight:750;text-decoration:none}.trust-link:hover{text-decoration:underline}
.roadmap{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;counter-reset:phase}.roadmap-card{position:relative;padding:22px;border:1px solid var(--line);border-radius:18px;background:#fff}.roadmap-card:before{counter-increment:phase;content:"0" counter(phase);display:block;margin-bottom:18px;color:var(--accent);font-size:12px;font-weight:800}.roadmap-card h3{margin:0 0 8px;font-size:17px}.roadmap-card p{margin:0;color:var(--muted);font-size:14px;line-height:1.55}
.trust-sources{display:flex;flex-wrap:wrap;gap:10px}.trust-source{padding:9px 12px;border:1px solid var(--line);border-radius:10px;color:var(--deep);background:#fff;text-decoration:none;font-size:13px;font-weight:650}.trust-source:hover{border-color:var(--accent)}.trust-contact{display:grid;grid-template-columns:1fr auto;align-items:center;gap:28px;padding:34px;border-radius:22px;background:var(--deep);color:#fff}.trust-contact h2{margin:0 0 8px;font-size:30px}.trust-contact p{margin:0;color:#d7e8f5;line-height:1.6}.trust-contact a{color:#fff}.trust-contact-btn{display:inline-flex;padding:11px 17px;border-radius:999px;background:#fff;color:var(--deep)!important;text-decoration:none;font-weight:750;white-space:nowrap}.trust-note{margin-top:24px;color:var(--muted);font-size:12px;line-height:1.6}
.lp-nav-link.active{color:var(--accent)}.trust-footer-links{display:flex;gap:18px;flex-wrap:wrap}.trust-footer-links a{color:var(--accent);text-decoration:none}
@media(max-width:900px){.trust-grid,.roadmap{grid-template-columns:repeat(2,minmax(0,1fr))}.trust-two{grid-template-columns:1fr}}
@media(max-width:680px){.trust-wrap{width:min(100% - 32px,1120px)}.trust-hero{padding:64px 0 48px}.trust-section{padding:54px 0}.trust-grid,.adapter-grid,.roadmap{grid-template-columns:1fr}.trust-contact{grid-template-columns:1fr;padding:26px}.trust-lede{font-size:18px}.trust-footer-links{flex-direction:column;gap:8px}}
"""


def _bullet_list(items):
    return Ul(*[Li(item) for item in items], cls="trust-list")


def compliance_page(lang="en"):
    """Render the public, localized compliance and interoperability page."""
    T = lambda text: t(text, lang)
    description = T(
        "FastClinic's transparent Europe-first path for GDPR operations, FHIR R4 interoperability, EHDS readiness, security controls, and national health-system adapters."
    )

    return Html(
        Head(
            Title(T("FastClinic Compliance & Trust · FastSME")),
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Meta(name="description", content=description),
            *seo_meta(
                path="/compliance",
                title=T("Compliance & Trust for European Private Clinics · FastClinic"),
                description=description,
            ),
            Link(rel="icon", type="image/svg+xml", href=FAVICON),
            Link(rel="preconnect", href="https://fonts.googleapis.com"),
            Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;750&display=swap"),
            Style(LANDING_CSS + AUTH_CSS + COMPLIANCE_CSS),
        ),
        Body(
            Nav(
                A(Span("F", cls="lp-mark"), Span("FastClinic", cls="lp-brand-name"), href="/", cls="lp-brand"),
                Div(
                    A(T("Product"), href="/", cls="lp-nav-link"),
                    A(T("Developers"), href="/developers", cls="lp-nav-link"),
                    A(T("Compliance"), href="/compliance", aria_current="page", cls="lp-nav-link active"),
                    language_switcher(lang, "/compliance"),
                    Button(T("Sign In"), type="button", onclick="authOpen('login')", cls="lp-signin"),
                    cls="lp-nav-actions",
                ),
                cls="lp-nav",
            ),
            Main(
                Div(
                    Section(
                        Div(
                            Span(T("Compliance & trust"), cls="trust-kicker"),
                            H1(T("Compliance & Trust for European Private Clinics")),
                            P(T("FastClinic is designed for private multi-specialty clinics operating under EU law. Patient data protection, auditability, and interoperability are product requirements—not afterthoughts."), cls="trust-lede"),
                            Div(
                                Span(Span(cls="trust-dot"), T("Current: synthetic data only"), cls="trust-pill"),
                                Span(Span(cls="trust-dot plan"), T("Roadmap: production controls and national adapters"), cls="trust-pill"),
                                cls="trust-pills",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-hero",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Status at a glance"), cls="trust-kicker"), H2(T("Clear about what exists—and what comes next.")), P(T("This page separates verified demo capabilities from production requirements and future integration work.")), cls="trust-head"),
                            Div(
                                Article(Span(T("Available today"), cls="trust-label"), H3(T("Synthetic operations cockpit")), P(T("The public demo and repository contain no protected health information. They demonstrate appointments, patient and party relationships, consent-gated communications, billing, recall, reporting, and a read-only AI assistant using synthetic records.")), cls="trust-card"),
                                Article(Span(T("Production path"), cls="trust-label"), H3(T("Controls before real patient data")), P(T("Production deployments require an EU/EEA residency profile, encryption and key management, fine-grained access control, append-only audit evidence, retention controls, incident response, and processor agreements.")), cls="trust-card"),
                                Article(Span(T("Not claimed"), cls="trust-label"), H3(T("No certification shortcut")), P(T("FastClinic is not currently ISO 27001 or ISO 27701 certified, the public demo is not a production EHR, and this page is not a legal compliance guarantee for a deploying clinic.")), cls="trust-card"),
                                cls="trust-grid",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Our commitments"), cls="trust-kicker"), H2(T("Europe-first by design.")), P(T("The production architecture and operating model are being shaped around the following commitments.")), cls="trust-head"),
                            Div(
                                _bullet_list([
                                    Strong(T("European production deployment policy — "), T("data residency and processing within the EU/EEA.")),
                                    Strong(T("Privacy by design and by default — "), T("supporting GDPR Article 25 from product design through deployment configuration.")),
                                    Strong(T("Special-category safeguards — "), T("health data requires both an Article 6 basis and an Article 9 condition under applicable national law.")),
                                    Strong(T("Synthetic public surface — "), T("no PHI in the open-source demo, public API, fixtures, or repository.")),
                                ]),
                                _bullet_list([
                                    Strong(T("Correct people model — "), T("subjects of care are separate from contactable or billable parties, including guardians for minors.")),
                                    Strong(T("Purpose-aware communications — "), T("consent and opt-out enforcement distinguishes operational follow-up from marketing.")),
                                    Strong(T("Auditable operations — "), T("access controls and append-only evidence are production-readiness requirements.")),
                                    Strong(T("Interoperability path — "), T("FHIR R4-based adapters are planned for EHDS-aligned and national exchange.")),
                                ]),
                                cls="trust-two",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section tint",
                        id="commitments",
                    ),
                    Section(
                        Div(
                            Div(Span(T("GDPR alignment"), cls="trust-kicker"), H2(T("Tools for the controller; evidence for the processor relationship.")), P(T("A clinic remains responsible for its lawful purposes, national clinical-record obligations, and patient-facing processes. FastClinic's role depends on the deployment and contract.")), cls="trust-head"),
                            Div(
                                _bullet_list([
                                    T("Record lawful bases and purposes without treating clinical processing and marketing consent as the same thing."),
                                    T("Support access, rectification, restriction, and portable export where applicable; erasure remains subject to legal retention and other GDPR exceptions."),
                                    T("Provide deployment materials for records of processing, processor agreements, retention schedules, and Data Protection Impact Assessments."),
                                    T("Apply encryption in transit and at rest, least privilege, role-based access, secure sessions, secrets management, and structured logging in production profiles."),
                                    T("Prepare incident evidence so controllers can assess risk and, where GDPR Article 33 requires it, notify the supervisory authority within 72 hours where feasible."),
                                    T("Support a designated DPO or privacy contact; whether a DPO is legally required depends on the clinic's processing and scale."),
                                ]),
                                Div(
                                    P(Strong(T("Health-care condition.")), " ", T("GDPR Article 9(2)(h) may support processing for health care or the management of health systems where its conditions and relevant EU or Member State law are met. It does not replace the need to document the Article 6 basis and local rules.")),
                                    P(Strong(T("AI boundary.")), " ", T("Before any model receives real patient data, the deployment must resolve provider location, contracts, international transfers, minimisation, retention, human oversight, and purpose limitation. EU-hosted or local models are preferred.")),
                                    cls="trust-callout",
                                ),
                                cls="trust-two",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                        id="gdpr",
                    ),
                    Section(
                        Div(
                            Div(Span(T("FHIR & EHDS"), cls="trust-kicker"), H2(T("A normalised core with standards at the boundary.")), P(T("EHDS establishes the European Electronic Health Record exchange format and future common specifications for interoperability and logging. FastClinic plans to use FHIR R4 as its primary implementation spine, with HL7 Europe, IPS, and national profiles applied by adapters.")), cls="trust-head"),
                            Div(
                                Table(
                                    Thead(Tr(Th(T("FastClinic concept")), Th(T("FHIR R4 mapping")), Th(T("Adapter responsibility")))),
                                    Tbody(
                                        Tr(Td(T("Subject of care")), Td(Span("Patient", cls="trust-code")), Td(T("National identifiers, demographics, and required extensions"))),
                                        Tr(Td(T("Guardian or contactable party")), Td(Span("RelatedPerson", cls="trust-code"), " / ", Span("Patient.contact", cls="trust-code")), Td(T("Relationship coding, authority, representation, and consent attribution"))),
                                        Tr(Td(T("Appointment and visit")), Td(Span("Appointment", cls="trust-code"), " / ", Span("Encounter", cls="trust-code")), Td(T("National status, referral, location, and workflow profiles"))),
                                        Tr(Td(T("Diagnosis and performed care")), Td(Span("Condition", cls="trust-code"), " / ", Span("Procedure", cls="trust-code")), Td(T("Terminology bindings, code systems, and specialty rules"))),
                                        Tr(Td(T("Payer and coverage")), Td(Span("Coverage", cls="trust-code"), " / ", Span("Organization", cls="trust-code")), Td(T("Insurance identifiers, eligibility, claims, and private-pay rules"))),
                                        Tr(Td(T("Clinician and clinic")), Td(Span("Practitioner", cls="trust-code"), " / ", Span("PractitionerRole", cls="trust-code"), " / ", Span("Organization", cls="trust-code")), Td(T("Professional registries, authentication, and organisation identifiers"))),
                                        Tr(Td(T("Consent and audit evidence")), Td(Span("Consent", cls="trust-code"), " / ", Span("AuditEvent", cls="trust-code")), Td(T("Local consent regimes, purpose, provenance, and disclosure policy"))),
                                    ),
                                    cls="trust-table",
                                ),
                                cls="trust-table-wrap",
                            ),
                            P(T("The current public API is a typed, versioned read surface over synthetic data. Production write paths and conformant FHIR import/export are roadmap work, not current capabilities."), cls="trust-copy"),
                            cls="trust-wrap",
                        ),
                        cls="trust-section tint",
                        id="fhir",
                    ),
                    Section(
                        Div(
                            Div(Span(T("National adapters"), cls="trust-kicker"), H2(T("One core; country-specific identity, terminology, policy, and transport.")), P(T("Adapter targets below are discovery candidates, not implemented integrations or delivery commitments. The first production pilots will determine sequence and exact conformance scope.")), cls="trust-head"),
                            Div(
                                Article(Div(H3(T("Estonia · TEHIK / upTIS")), Span(T("Discovery"), cls="adapter-status"), cls="adapter-top"), P(T("Map Estonian identifiers and terminology, current document exchange, emerging FHIR R4 assets, professional access, representation, and secure national exchange requirements.")), A(T("Official TEHIK overview ↗"), href="https://www.tehik.ee/en/health-information-system", target="_blank", rel="noopener noreferrer", cls="trust-link"), cls="adapter-card"),
                                Article(Div(H3(T("Finland · Kanta")), Span(T("Discovery"), cls="adapter-status"), cls="adapter-top"), P(T("Support the transition in which CDA R2 remains common while Kanta introduces FHIR progressively, including national profiles, code sets, testing, certification, authorisation, and logging requirements.")), A(T("Official Kanta FHIR roadmap ↗"), href="https://www.kanta.fi/en/system-developers/fhir-technology-and-kanta", target="_blank", rel="noopener noreferrer", cls="trust-link"), cls="adapter-card"),
                                Article(Div(H3(T("Germany · gematik ePA")), Span(T("Discovery"), cls="adapter-status"), cls="adapter-top"), P(T("Follow gematik's FHIR R4 implementation guides for ePA services, Telematics Infrastructure identities, audit events, terminology, and applicable conformity assessment.")), A(T("Official gematik FHIR guide ↗"), href="https://gemspec.gematik.de/ig/fhir/epa/1.3.1/downloads.html", target="_blank", rel="noopener noreferrer", cls="trust-link"), cls="adapter-card"),
                                Article(Div(H3(T("Netherlands · Nictiz / MedMij")), Span(T("Discovery"), cls="adapter-status"), cls="adapter-top"), P(T("Map Dutch care information models and FHIR R4 profiles, then implement the MedMij trust framework and supplier qualification where patient-mediated exchange is in scope.")), A(T("Official Nictiz MedMij overview ↗"), href="https://www.nictiz.nl/programmas/medmij/", target="_blank", rel="noopener noreferrer", cls="trust-link"), cls="adapter-card"),
                                cls="adapter-grid",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                        id="adapters",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Security & operational controls"), cls="trust-kicker"), H2(T("Production readiness means verifiable controls.")), P(T("The target control system combines technical safeguards, operating procedures, supplier governance, and evidence that can be reviewed by clinics and auditors.")), cls="trust-head"),
                            Div(
                                Article(H3(T("Identity & access")), P(T("Fine-grained RBAC, least privilege, MFA and SSO options, secure sessions, and professional-identity hooks for national adapters.")), cls="trust-card"),
                                Article(H3(T("Audit & resilience")), P(T("Append-only evidence for clinically and administratively significant actions, monitoring, backups, incident response, and recoverability testing.")), cls="trust-card"),
                                Article(H3(T("Assurance path")), P(T("ISO 27001 and ISO 27701 are target frameworks, informed by ISO 27799 health-security guidance and NIS2 supply-chain and risk-management expectations. They are not current certifications.")), cls="trust-card"),
                                cls="trust-grid",
                            ),
                            Div(
                                P(Strong(T("MDR / SaMD boundary.")), " ", T("Scheduling, billing, records, and operational recall are not intended to diagnose or recommend treatment. Patient-specific decision support will remain gated and separately assessed before release; features with a medical intended purpose may require medical-device compliance.")),
                                cls="trust-callout",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section tint",
                        id="security",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Patient rights & transparency"), cls="trust-kicker"), H2(T("Find, explain, export, restrict.")), P(T("The system is being designed to help clinics locate a person's data, explain its provenance, export it in structured form, and apply restriction or erasure where legally required. Clinical retention duties and legal holds remain enforceable.")), cls="trust-head"),
                            P(T("For minors and represented adults, communications and rights workflows use the appropriate guardian or authorised party relationship instead of assuming the subject of care is directly contactable."), cls="trust-copy"),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Roadmap"), cls="trust-kicker"), H2(T("From synthetic demo to auditable multi-country platform.")), cls="trust-head"),
                            Div(
                                Article(H3(T("Foundation")), P(T("Synthetic pipeline, subject/party model, consent gates, balanced ledger, evaluation suite, and multilingual product surfaces.")), cls="roadmap-card"),
                                Article(H3(T("Production readiness")), P(T("EU-only deployment profiles, RBAC, encryption defaults, audit matrix, retention and legal holds, DPIA/processing-record/DPA templates, and structured export.")), cls="roadmap-card"),
                                Article(H3(T("FHIR core")), P(T("Conformant read surface, later controlled writes, validation, Encounter and Appointment fidelity, and the first pilot-led national adapter.")), cls="roadmap-card"),
                                Article(H3(T("Operational maturity")), P(T("Patient portal primitives, stronger identity, ISO gap analysis, NIS2-aligned playbooks, additional adapters, and continuous EHDS monitoring.")), cls="roadmap-card"),
                                cls="roadmap",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section tint",
                        id="roadmap",
                    ),
                    Section(
                        Div(
                            Div(Span(T("Primary references"), cls="trust-kicker"), H2(T("Standards and legislation behind the approach.")), P(T("National requirements and EHDS implementing acts will evolve. Adapter conformance must be checked against the authoritative version in force for each deployment.")), cls="trust-head"),
                            Div(
                                A(T("EU General Data Protection Regulation ↗"), href="https://eur-lex.europa.eu/eli/reg/2016/679/oj", target="_blank", rel="noopener noreferrer", cls="trust-source"),
                                A(T("European Health Data Space Regulation ↗"), href="https://eur-lex.europa.eu/eli/reg/2025/327/oj", target="_blank", rel="noopener noreferrer", cls="trust-source"),
                                A(T("NIS2 Directive ↗"), href="https://eur-lex.europa.eu/eli/dir/2022/2555/oj", target="_blank", rel="noopener noreferrer", cls="trust-source"),
                                A(T("HL7 FHIR R4 specification ↗"), href="https://hl7.org/fhir/R4/", target="_blank", rel="noopener noreferrer", cls="trust-source"),
                                A(T("HL7 Europe FHIR specifications ↗"), href="https://hl7.eu/fhir/", target="_blank", rel="noopener noreferrer", cls="trust-source"),
                                cls="trust-sources",
                            ),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                    ),
                    Section(
                        Div(
                            Div(
                                Div(H2(T("Compliance questions, DPA requests, or DPIA support")), P(T("Contact the FastClinic team. The formal Data Protection Officer or privacy contact for production services is still to be designated."))),
                                A("compliance@fastclinic.dev", href="mailto:compliance@fastclinic.dev", cls="trust-contact-btn"),
                                cls="trust-contact",
                            ),
                            P(T("This page describes design intent and current capabilities. Formal certifications, legal assessment, and specific national registrations or notifications remain the responsibility of the deploying clinic and will be documented as they are achieved."), cls="trust-note"),
                            cls="trust-wrap",
                        ),
                        cls="trust-section",
                        id="contact",
                    ),
                    cls="trust trust-main",
                ),
            ),
            Footer(
                Span(T("FastClinic is part of the open-source FastSME suite.")),
                Div(A(T("Product"), href="/"), A(T("Developers"), href="/developers"), A(T("Compliance"), href="/compliance"), cls="trust-footer-links"),
                cls="lp-footer trust",
            ),
            auth_modal("FastClinic", T),
            Script(AUTH_JS + LANGUAGE_JS),
            style="margin:0;background:#fff",
        ),
        lang=lang,
    )
