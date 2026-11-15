# NASA Space Apps Challenge — Submission Preparation

**Do not present the current build as a fully validated astronomy discovery pipeline.** Complete the following before submission.

1. Publish the Docker deployment on a reliable public HTTPS URL with an internet connection and persistent storage.
2. Test an arbitrary sky coordinate, including one the developers did not preselect; save IRSA SIA query parameters, raw VOTable results and at least one FITS cutout source URL.
3. Test the five required named targets separately and save results to `reports/targets_live.json` using `python scripts/validate_targets.py --live`. Resolve all high-proper-motion stars to the relevant exposure epochs before interpreting pixel motion.
4. For at least one target with two usable comparable epochs, demonstrate temporal playback with actual dates, and difference imaging only after full wavelength/PSF/photometric QA.
5. Include screenshots of the **actual live FITS view**, the source inspector and the science warning for absent data; do not use the decorative homepage illustration as observation evidence.
6. Validate accessibility and bilingual UI with Arabic names and LTR astronomical identifiers. Fix responsive issues on physical or emulated phones.
7. Record a concise demonstration video: name or coordinates → official resolver → SIA2 result → real FITS image → playback → source link → limitations.
8. Prepare the GitHub repository link, deployment URL, readme, documentation, main data credits and open-source license; verify the current challenge page and eligibility rules directly with the organizer.
9. Display the endorsement disclaimer: "This project uses publicly available NASA and partner data. NASA does not endorse this project."
10. Explain the difference between images of a host star system, direct detection of an exoplanet, and the mere sky-region coverage of a detector.

## Suggested title

**SkyShift AI — Explore the Changing Sky with Real SPHEREx Data**

## Suggested 150-word description

SkyShift AI is a bilingual scientific sky explorer built around NASA's SPHEREx mission. Users can look up celestial objects or enter sky coordinates, access source-linked SPHEREx observations via the IRSA archive, and follow how astronomical images change across observation dates. The application preserves scientific provenance, including archive collection, original FITS links, detector information and spectral ranges. Its exploratory analysis tools can perform image registration, differences and preliminary photometric measurements under explicit data-quality and wavelength compatibility conditions. SkyShift AI distinguishes archive coverage from confirmed detection and never substitutes another object's imagery for missing data. Designed for public education and reproducible research, it invites users to mark candidates that require follow-up verification, rather than claim discoveries prematurely. This source release is a functional local application with mock-tested workflows; live NASA archive validation and additional science-grade quality controls are outstanding and must be completed before judging.
