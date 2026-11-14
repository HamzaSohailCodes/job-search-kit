# H-1B sponsorship evidence (optional module)

Turn it on with `"modules": {"h1b": true}` in `config/profile.json`, for a candidate who needs a new employer
to file a visa petition (`work_authorization.needs_sponsorship: true`). When it is off, every code path below is
skipped: no lookups, no no-sponsor list, column Q of the tracker stays blank.

## What it does

- `h1b_lookup.py` looks up an employer's H-1B Labor Condition Application (LCA) filings in the public US
  Department of Labor disclosure data, as indexed by h1bdata.info, and returns a verdict:
  `sponsors` (5+ filings in the last two calendar years), `some` (1–4), `none` (nothing found) or `unknown`.
  `evidence()` turns that into the one-line text for the tracker's **H-1B Evidence** column (Q).
  Results are cached for 30 days in `batches/h1b_cache.json` (override with `$H1B_CACHE`).
- `profile/no_sponsor_companies.txt` lists companies that said **in writing** they don't sponsor (a posting,
  a rejection email). `scripts/screen.py` reads it; the apply-batch filter and gate drop those companies.
  `/review-emails` adds to it.

Who uses it: `apply-batch` (`gate.py --h1b`, `build_rows.py` for column Q) and `search-jobs` (column Q on new rows).

```bash
python3 modules/h1b/h1b_lookup.py "Acme" "Globex"
python3 modules/h1b/h1b_lookup.py --json --force "Acme"
```

## Caveats

- **Evidence, never a knockout by itself.** A posting that says "we don't sponsor" is a knockout; a missing
  filing history is not. Young startups show `none` because they haven't hired on a visa yet. `none` at a
  company with hundreds of employees is a real signal; rank it low rather than dropping it automatically.
- **Name matching is fuzzy.** The data is keyed on legal employer names. The lookup tries the name as given,
  then `Inc`/`LLC`/`Corp`/`Technologies` suffixes and a de-camel-cased form ("AcmeCloud" → "Acme Cloud"),
  and keeps only employers whose name is the company's own name or a legal/group variant of it.
  A brand that differs from its legal name can still read `none` wrongly: check by hand when it matters.
- **`unknown` / "lookup ambiguous"** means a generic word (think "Titan", "Atlas") matched several unrelated
  employers, so the filings were not counted. Look the employer up by hand.
- **Read the employer in the cell.** A `sponsors`/`some` result whose employer name is a different company with
  a similar name is still possible for generic names.
- Filings show intent to hire on a visa, not that a given team or role will sponsor. Ask the recruiter about a
  transfer or new petition in the first reply, before technical rounds.
- The lookup scrapes a public page; it needs network access and can break if the page layout changes
  (then everything reads `unknown` with an `error`).
