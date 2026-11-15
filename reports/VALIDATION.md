# Validation record — SkyShift AI build 0.2.4

**Date:** 2026-11-14 (UTC+03:00)

## Environment

- Python FastAPI/Pydantic + NumPy + Pillow available locally.
- `astropy`, `reproject`, `photutils`, `pyvo`, `astroquery` **not** available in this build runtime; `requirements-science.txt` provided.
- Outbound astronomy services: **network/DNS blocked in build runtime** (`httpx.ConnectError: Temporary failure in name resolution`).
- UI captured via headless Chromium using in-memory injection of the actual HTML/CSS/JS, because browser navigation to local URLs was also blocked by administrative policy.
- Server started locally and health endpoint verified. It reports `live_connection_tested: false`.

## Unit and contract test outcomes

| Test | Expected | Observed | Status |
|---|---|---|---|
| Decimal/sexagesimal parsing | Accurate RA/Dec | Matched independent expected values | PASS |
| Invalid coordinates | Reject | 422 or ValueError | PASS |
| Direct coordinates | No name-resolver service call | Test confirmed no remote call | PASS |
| VOTable parse | Correct fields/detector/date | Synthetic XML contract fixture parsed | PASS (mock) |
| Wrong FITS host | Reject source | Rejected | PASS |
| Cross-target cache key | Unique | Different target/FOV yields distinct keys | PASS |
| SIA search positions | Unique per sky coordinates | Verified `POS=CIRCLE` changes | PASS (mock) |
| Duplicate records | Deduplicated | One result for identical observation URLs | PASS (mock) |
| No data | Empty list, no fabricated images | Correct empty status | PASS (mock) |
| HTTP 503 → recovery | Retry then return | 3 attempts, success only on 200 | PASS (mock) |
| HTTP 503 persistent | Explicit upstream error | No fallback data | PASS (mock) |
| Unauthorized frame | Forbidden | HTTP 403 | PASS |
| Known solar system IDs | No frozen coordinates | All catalog coordinates null until resolution | PASS |
| Five required target statuses | Never claim untested PASS | All `not_live_tested` | PASS |
| App HTML and API health | Load | HTTP 200 | PASS |
| UI JavaScript smoke | No runtime exceptions | 0 page errors in offline injection | PASS |
| UI mobile 390 px | No horizontal overflow | False | PASS |

**Automated Pytest suite:** 61 tests passed in the latest local test run; run `python -m pytest -q` to recheck latest source. Mocked results are engineering test fixtures **not actual NASA observations**.

## CDS mirror incident fix (2026-11-14)

- Replaced incorrect `/ObjectName` path with documented `?ObjectName` query to Sesame XML endpoint.
- Added trusted Harvard mirror and allow-listed redirect handling (max 5 hops, loop and unsafe host rejection).
- Added source-backed WISE 0855 name alias to the full catalog identifier.
- Added regression tests for mirror fallback, proper name encoding, safe/unsafe redirects, loop detection, namespace-tolerant XML, and refusal to fabricate coordinates when unavailable.
- These tests **mock** network responses. No live mirror connection was possible in the build environment, and the repair must be confirmed on an internet-enabled system before being called fully verified.

## NASA five target validation

| Target | Coordinates | SIA2 coverage | Playback | WCS & spectral QA | Live test status |
|---|---|---|---|---|---|
| Barnard's Star | Resolve dynamically | Not tested | Not tested | Not tested | NOT RUN |
| Epsilon Indi B | Resolve dynamically | Not tested | Not tested | Not tested | NOT RUN |
| WISE 0855 | 133.795129°, −7.245147° from challenge text | Not tested | Not tested | Not tested | NOT RUN |
| RW Aurigae | Resolve dynamically | Not tested | Not tested | Not tested | NOT RUN |
| R Draconis | Resolve dynamically | Not tested | Not tested | Not tested | NOT RUN |

A missing or visually undetected target is not by itself proof of a code error; distinguish archive coverage and target detectability. Gaia proper-motion propagation is a pending work item.

## Follow-up on an internet-enabled machine

Run `python scripts/validate_targets.py --live` and save the resulting JSON report, then check source FITS links, wavelengths, alignment and actual frame thumbnails. Investigate service outages, rate limits and calibrations. Do not mark the targets passed based on mocks or screenshot visuals.


## 2026-11-14 · v0.2.2 search diagnostics
- 44 local automated tests passed; `node --check frontend/static/app.js` passed.
- Added per-collection SIA2 archive row, supported URL, filter, and failed-connection diagnostics.
- No live IRSA response was retrieved from this execution environment. The presence of DR1 all-sky cube data is documented by IRSA but not automatically previewed in this UI.


## 2026-11-14 · v0.2.3 frame-build HTTP 500 regression
- A user-provided Windows terminal log confirmed CDS Sesame and NASA/IPAC IRSA SIA2 responded HTTP 200 for WISE 0855 and Barnard's Star, and FITS data was downloaded successfully after HTTP 503 retry. That is evidence of successful user-side fetches, **not** verification that FITS astrometry or full playback is scientifically correct.
- `POST /api/spherex/frames/build` failed at `main.py` when `round(x, 2)` received a NumPy ndarray returned by Astropy WCS for a scalar sky coordinate. This is a **local Python conversion bug**, not evidence that no NASA observations exist.
- Fixed by accepting a single finite pixel coordinate from Python/NumPy scalar or size-one ndarray, then converting to float before checking target bounds or rounding. Ambiguous multi-value and non-finite WCS pixels now produce a clear client error instead of HTTP 500.
- **56 automated tests passed locally** (`python -m pytest -q`), including regression cases for the real HTTP endpoint with ndarray positions. Network and actual Astropy FITS data processing were mocked in the regression tests because the build environment has no Astropy or live NASA access.
- Actual user machine re-test is still needed; Astropy SIP/WCS consistency warnings from the actual FITS header should be reviewed scientifically. These warnings were not the direct cause of the HTTP 500 and were not suppressed.


## Annual comparison update (v0.2.4)

- 61 local `pytest` checks passed (metadata time/year sampling, API, service safety, file handling, signed difference + previous tests).
- An in-memory Chromium UI test passed using **mocked** 2025/2026 API responses: year selectors, frame load, side-by-side presentation, difference display, and no JavaScript exceptions.
- No live NASA requests were made in the build runtime for these new annual comparison features.
- Side-by-side auto-stretched previews must not be construed as quantitative inter-year brightness changes; the WCS difference requires consistent wavelength and separate PSF/background checks for inference.
- WISE 0855 is high proper motion; sky positions must be propagated by epoch for robust motion detection. This is not yet implemented.
