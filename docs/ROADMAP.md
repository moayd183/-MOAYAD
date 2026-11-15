# Scope and roadmap — 2026-11-14

## Implemented in code and locally tested

- Responsive original dark navy + lime visual identity, Arabic-first RTL, English toggle, 10 navigable pages.
- SIA2 query builder with dynamic sky coordinates, release/deep selection, detector and date filtering, sourced VOTable metadata, independent search state.
- Read-only IBE cutout URL construction from IRSA-sourced records, unique content cache keys, file size caps, remote retries/backoff and strict hostname/source path restriction.
- Astronomy target resolving code for direct decimal/sexagesimal coordinates, JPL Horizons (major bodies), NASA Exoplanet TAP, and CDS Sesame.
- Dynamic TAP exoplanet catalog and pager (full catalog fetched then paged in application; needs server-side optimization).
- Cached FITS science processing via Astropy: astrometric WCS check, image and mask rendering, selected WCS-WAVE wavelength, `FLAGS` and `VARIANCE`.
- Reproject-based WCS difference and inverse-variance stack with provisional compatibility checks, preliminary 3-pixel photometry, matching-wavelength multi-epoch aperture light curve and CSV export.
- Observation timeline, frame browsing, brightness/contrast/zoom, shareable coordinates, PNG/FITS download.
- User notes in SQLite with Needs Verification classification; sources and caveats visible.
- 33 passing isolated backend tests; browser UI screenshots without JavaScript runtime errors (offline screenshot context).

## Implemented but **not verified live**

- Actual calls to NASA SPHEREx SIA2, NASA Exoplanet Archive, JPL Horizons, CDS Sesame, and actual FITS cutout generation.
- Actual image WCS transformation with the modern SPHEREx FITS files in deployment. Required science dependencies are not installed in the build environment and no authentic FITS sample is embedded.
- All five named target coverage and motion/brightness analyses.
- Container deployment and cross-platform installation from external package indexes.

## Not implemented / partial

- Real scientific automatic motion candidate detector and ML model (no automatic discovery claims).
- Full Gaia DR3 astrometry, proper-motion epoch propagation, WISE overlays, Aladin Lite.
- Comprehensive 102-channel spectra, calibrated all-pixel bandpass maps, uncertainty-spectrum plot.
- Per-epoch moving-object trajectories, ephemeris propagation for moving targets across all acquired observation timestamps.
- Photometric background/PSF calibration, color correction, rigorously validated wavelength PSF matching, centroid cross-matching.
- GIF/MP4 encoding, interactive FITS pan/celestial cursor coordinate overlay, astrophysical source catalog annotations.
- Public multi-user authentication, rate limiting, moderation, file cache retention policy, distributed worker/job queue.
- React/TypeScript/Vite (a lightweight framework-free frontend was implemented instead to ensure runnable product without JS installation); full CI and Playwright against online endpoints.
- Canadian Space Agency NEOSSat or full Aladin/Space Apps design-reference image imitation (image reference wasn't supplied in the text attachment).
- Deployment to public URL.

These are deliberately documented as outstanding work, rather than UI controls presented as complete.
