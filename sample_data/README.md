# No fake SPHEREx observations

This directory is intentionally empty. The build runtime cannot fetch real NASA FITS science frames. Adding generated or mislabeled files to the live viewer would violate observational provenance. Future offline fixtures must be real redistributable FITS files with exact observation IDs, archive provenance, dates and license details, accompanied by an explicit OFFLINE label.

Tests currently use in-memory mocked **metadata only** for API contract testing. They are not scientific data and are never exposed in the live UI.
