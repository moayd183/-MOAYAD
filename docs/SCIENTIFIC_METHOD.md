# Scientific methods, provenance, and non-claims

**Build version:** 1.0.0, **date:** 2026-11-14.

## Provenance chain

1. The user supplies RA/Dec in ICRS-like decimal or sexagesimal notation, or a name. Name resolution uses JPL Horizons (time-dependent for Solar System), NASA Exoplanet Archive `pscomppars` (host-system coordinates, not a resolved planet image), or CDS Sesame (catalog coordinates).
2. For each target, the backend sends a new `POS=CIRCLE RA Dec radius` query to IRSA SIA2 for each selected SPHEREx release, never reusing another object's observations.
3. The returned VOTable is parsed by field names and restricted to trusted on-premises IRSA `/ibe/data/spherex/` FITS URLs; records expose `obs_id`, collection, celestial metadata, detector, date, spectral interval and original archive access link.
4. A selected record's official FITS `access_url` is appended with `center=RA,Dec&size=Narcmin&gzip=false`. This uses IRSA's documented on-premises IBE cutout service. No screenshots or generated image assets masquerade as imagery.
5. Cached FITS records are keyed using observation ID, collection, source URL, detector, observation date, spectral limits, target coordinates and field size. Download requests require prior registered SIA2 records.
6. If Astropy is available, the service opens FITS `IMAGE`, `FLAGS`, `VARIANCE`, the astrometric WCS and spectral WCS-WAVE (when readable). A WCS check ensures the requested target sky coordinate is inside the actual FITS pixels. For visualization, flags/non-finite/variance-invalid pixels are masked; the remaining finite values are percentile/asinh stretched and emitted as display PNG. PNG brightness is **not calibrated science photometry**.
7. Genuine loaded frames can be navigated in observation-date order. The timeline does **not** imply a target is physically detected, only that the field was observed.

## Difference and stacking

- Requires **two cached, genuine FITS cutouts**.
- Samples approximate WCS-WAVE central wavelength at the target sky coordinate in each cutout and rejects differences greater than 4% by relative wavelength. This is only a **center-sample compatibility safeguard**, not an all-pixel bandpass-matching validation.
- Reprojects image, variance and quality mask from frame B to spatial WCS of frame A via `reproject_interp`, masking insufficient footprint and bad pixels.
- Difference is `image_later_on_earlier - image_earlier`, with approximate pixelwise noise `sqrt(variance_A + variance_B)` and internal SNR. A source in a difference image is **not** automatically a confirmed variable star or new planet.
- Stack is an inverse-variance weighted combination of the two images with valid pixel masks.

### Limitations of comparison

The current method does not do PSF homogenization, robust relative photometric calibration, astrometric star-residual QA, exposure-by-exposure artifact modeling, a field-dependent full WCS-WAVE bandpass matching procedure, or scientifically validated motion-source association. For this reason, comparison is **exploratory**, not a publication-ready discovery pipeline. A full-grade implementation would require reference source matching, cross-epoch photometric zero-point calibration and artifact injection-recovery tests.

## Aperture photometry

- Uses a fixed circular radius of 3 pixels at the cutout center.
- Calculates integrated apparent intensity converted from MJy/sr to Jy using WCS pixel solid angle, with variance-based uncertainty.
- Rejects apertures with over 20% invalid pixels.
- **Not** background-subtracted, PSF-corrected, color-corrected or source-confirmed; show results as preliminary only. Dates are taken from FITS record metadata.

## Spectrum Explorer

- Uses true SIA2 `em_min`/`em_max` and the six SPHEREx detector ranges documented by IRSA.
- Does **not** fabricate a 102-sample spectrum. The full 102-channel spectrum extraction and fitted scientific uncertainty chart were **not implemented** in this build.
- `WCS-WAVE` is read to sample central wavelength when possible for comparison; the science service does not offer every-pixel spectral curve extraction yet.

## Moving objects and epoch propagation

- JPL Horizons resolves a major Solar System object's geocentric apparent RA/Dec on the **user-selected date**, not a frozen value.
- The current search uses that date's sky position to look for SPHEREx fields. It **does not propagate each candidate frame's ephemeris back to its own observation time**. Accordingly, temporal image playback should not be interpreted as a planetary motion track for Mars/Jupiter/etc.
- CDS Sesame stellar results currently reflect catalog epoch rather than propagated Gaia DR3 proper motion. High-proper-motion targets like Barnard's Star and WISE 0855 require proper-motion propagation before rigorous cross-year alignment.

## No-data and remote service failures

- An empty SIA2 result returns `No SPHEREx observations available for this target` and no images.
- An HTTP 422 from an IBE cutout can trigger a same-center smaller-size retry and, during annual comparison, a different genuine record from the **same year**. The delivered field size is stated in provenance. A transient HTTP failure is retried up to 3 attempts with exponential backoff; after final failure the API returns an explicit upstream error, not a substitute frame.
- Partial errors for individual collections remain visible, rather than declaring complete coverage.
- External services may change schema and availability over time. Confirm IRSA release documentation regularly.

## Object detection claims

There is no trained source-motion classifier or scientifically vetted candidate scoring in this implementation. User annotations remain `needs_verification`. Unavailable features are not represented as completed discoveries, even if a visual comparison reveals a bright residual.

## Required follow-up for a science-grade validation

1. Run the five challenge targets against the live NASA archives and save actual SIA2 VOTables and cutouts with source identifiers.
2. Validate the exact FITS WCS/WCS-WAVE coordinate mapping on cutouts from all six detectors; inspect SIP warnings rather than ignoring them.
3. Check image date/time and detector filter positions per target; choose true matched bandpasses and measure overlap for every pixel.
4. Validate source centroid stability with Gaia calibrators and known motion targets. Run quality filters, background and PSF corrections.
5. Verify individual targets are detected above scientifically stated sensitivity thresholds, separately from field coverage.
6. Document data rights, use DR1 DOI and acknowledge IPAC/IRSA.

## Spectral WCS correction and its limits (v1.0.0)

IRSA's official SPHEREx tutorial requires `spectral_wcs.sip = None` for the alternative WCS-WAVE: the wavelength is detector-fixed, not subject to the spatial SIP distortion. This release applies that correction. The comparison samples approximate WAVE-TAB wavelengths **at the original requested target sky coordinate**, converting the reported axis units into micrometers. This is a conservative screening heuristic (4% center-wavelength difference), not proof that full spatially varying bandpasses match. IRSA's explanatory supplement distinguishes approximate WAVE-TAB visualization from science-level CWAVE/CBAND calibrations. Accordingly, do not interpret the red/blue residual map as confirmed physical variability without PSF, photometric and field-dependent spectral controls.

Source: https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/ ; https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/
