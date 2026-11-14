---
name: form-defaults
description: Default answers for recurring form questions that are not in the answer bank tables
metadata:
  type: feedback
---
- Interview recording / AI-notetaker consent: `config/profile.json` → `logistics.recording_consent`.
- "How did you hear about us?": the job-board option when the list has one, else `logistics.how_did_you_hear_default`.
- Terms, privacy, arbitration and data-sharing consents: always left for the candidate.

**Why:** these come up on most forms and the candidate set them once during /setup.
**How to apply:** record the chosen value in the form snapshot. Related: [[application-record-lifecycle]].
