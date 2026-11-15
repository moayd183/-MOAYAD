# SkyShift AI v1.0.0 — final local quality checks

**Date:** 2026-11-14 (Asia/Riyadh). **Scope:** local source, mock I/O, simulated browser. External NASA network remains unavailable in the build environment; do not claim live validation of this patch.

## Results verified in this build

- `python -m pytest -q`: **74 passed**, including original search/resolver/WCS regressions and new HTTP 422 tests.
- `node --check frontend/static/app.js`: **passed**, JavaScript parses.
- `python scripts/final_browser_smoke.py`: **passed** in headless Chromium with explicit **test-only fixtures** (not NASA imagery): Arabic object search, helpful 422 error, annual request for 2025 and 2026, two side-by-side previews, difference image, English/Arabic switch, mobile viewport 390px with no horizontal overflow, and **0 uncaught JS errors**.
- API tests include HTTPS allowlist and safe-redirect behavior, status-preserving HTTP 422, rejection of unsafe ports, no retry for HTTP 403, multiple same-center FITS cutout sizes on 422, no fabricated fallback when all cutouts fail, annual fallback to another image in the same year, spectral pair selection, no false annual pair when none are usable, stale/unregistered records forbidden, and later-minus-earlier chronology.
- User-reported earlier Windows log showed real CDS and IRSA SIA responding 200 and real FITS retrieval after a transient 503, but the *updated* v1.0.0 annual/fallback and wavelength path has **not** been live tested here.

## Known, not verified or intentionally unavailable

- **Live NASA/IRSA SPHEREx FITS** for this version; DNS blocked in build environment.
- Optional `astropy` and `reproject` unavailable here. Unit tests mock FITS API boundaries; production scientific parsing and reprojection must be run on a Windows/macOS/Linux installation with `requirements-science.txt` installed.
- Full 102-band all-sky cube, science-grade PSF/background/cross-band calibration, Gaia proper-motion epoch propagation, confirmed source discovery, and public HTTPS hosting are **not implemented/verified**.
- WAVE-TAB approximates wavelength for display; actual science-grade analysis should use CWAVE/CBAND calibration, and only source-associated motion should be treated as an astronomical finding.
- HTTP 422 may still occur for individual archive files. The program now offers smaller **same-coordinate** cutouts, alternative authenticated records from the **same** calendar year, and explicit diagnostics; it cannot guarantee that an unsupported or corrupt NASA cutout becomes usable.

## Evidence files

- `reports/skyshift_final_comparison_desktop_MOCK.png` and `reports/skyshift_final_comparison_mobile_MOCK.png`: browser QA fixtures only, explicitly marked MOCK; they are **not** astronomical evidence.
- `scripts/final_browser_smoke.py`: reproducible browser fixture flow.
- `tests/test_final_resilience.py`, `tests/test_target_spectrum.py`: regression coverage for the user-reported failure and science correctness issues.

## How to verify with actual NASA data

On a network-enabled system with the science requirements installed, run `python scripts/validate_targets.py --live` and inspect `reports/targets_live.json`, then use the website to compare a 2025/2026 observation pair. Record original archive URLs, dates, detector, full FITS headers, target pixel and WCS-WAVE units. Verify actual PSF, image overlap, astrometric offsets and source morphology before claiming motion or brightness variability.
