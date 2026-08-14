# NHS / GP Connect adapter

**Status:** mapping implemented (2026-08-14). Live PDS / GP Connect / IM1 / SSP
calls remain gated. See `docs/CLINIC_OS_PLAN.md` §9 and §10 Q1.

The adapter is a **translation layer**, not a pass-through. FastClinic's core
emits vanilla FHIR R4; this module applies UK Core R4 profiles and, separately,
translates that view to GP Connect STU3. The two FHIR versions are not
compatible.

```
web/adapters/nhs/
  identifiers.py   NHS Number modulus 11 (offline)
  profiles.py      UK Core R4 + CareConnect-GPC STU3
  live.py          PDS / GP Connect — AdapterNotAvailable until onboarded
  __init__.py      NhsAdapter (CountryAdapter)
```

`web/adapters/nhs_gpconnect.py` is a compatibility facade over that package.

## What works offline

| Surface | Behaviour |
|---|---|
| `verify_identifier` | Modulus-11 check digit. Never claims a PDS match (`traced=false`). |
| `export_subject` | UK Core R4 by default; `release=stu3` for GP Connect CareConnect profiles. |
| `import_record` | Re-normalises Patient / RelatedPerson (national relationship codes → core `role`). |
| `push_reminder` | Projects vaccine → `ImmunizationRecommendation`, else `Task` / `CommunicationRequest`. Does not write to the spine. |

Relationship codes stay in the adapter. Core `guardian` becomes UK Core
`PRN` + `GUARD`; inbound UK/GP Connect codes map back to the core enum.

`ImmunizationRecommendation` is the structural split that proves the version
split is real: R4 uses `recommendation.dateCriterion`; STU3 uses
`recommendation.date`.

## What stays gated

Live calls raise `AdapterNotAvailable` unless `NHS_LIVE_ENABLED=true` **and**
the matching credentials are present. Even then `live.py` refuses to invent a
client — the first live implementation must follow the official IGs in force
at onboarding.

| Env | Surface |
|---|---|
| `NHS_PDS_BASE_URL`, `NHS_PDS_API_KEY` | PDS Patient retrieval (UK Core R4) |
| `NHS_GPCONNECT_ENDPOINT`, `NHS_GPCONNECT_FROM_ASID`, `NHS_GPCONNECT_TO_ASID` | GP Connect Access Record / appointments |

Still unresolved by public documentation (do not assume):

- Other GP Connect packs (Access Record HTML, Appointment Management, Send
  Document) and their FHIR versions.
- Spine Security Proxy / JWT specifics.
- IM1 Pairing vs Bulk vs Transactional eligibility.
- NHS App / NHS login.
- PDS / SDS environment auth patterns.

Until NHS England API onboarding answers *can a non-supplier open-source
project obtain sandbox credentials, and what does production access require?*,
treat live connectivity as unschedulable. The mapping layer does not wait.

Expected production gates (confirm during onboarding): DCB0129 / DCB0160,
DTAC, DSPT, possibly GPIT Futures supplier status.
