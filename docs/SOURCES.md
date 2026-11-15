# Source registry

Checked against accessible documentation on **2026-11-14**.

| Source | Official link | Program usage |
|---|---|---|
| NASA/IPAC SPHEREx archive | https://irsa.ipac.caltech.edu/Missions/spherex.html | Mission data releases, archive attribution |
| SPHEREx Data Access (Nov 12, 2026 update) | https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/ | SIA2 collections, release precedence, FITS cutout syntax |
| SPHEREx Data Releases | https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-releases/ | DR1 supersedes earlier observations from QR2; QR3 complementary |
| SPHEREx FITS tutorial | https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/ | FITS IMAGE, FLAGS, VARIANCE, SIP & WCS-WAVE |
| IRSA cutout API | https://irsa.ipac.caltech.edu/ibe/cutouts.html | IBE `center` and `size` query syntax |
| NASA Exoplanet Archive TAP | https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html | `pscomppars` fields; dynamic planet records |
| JPL Horizons | https://ssd-api.jpl.nasa.gov/doc/horizons.html | Dated geocentric apparent solar-system coordinates |
| CDS Sesame | https://cds.unistra.fr/doc/sesame.htx | Name resolution for non-solar-system sky targets |

**As of November 9, 2026**, CDS reported cybersecurity-related service degradation. The code tries a documented Sesame mirror at `vizier.idia.ac.za` first. This may still fail; the app does not invent coordinates in its place.

The SPHEREx DR1 images should cite DOI **10.26131/IRSA678**; all-sky cube DOI **10.26131/IRSA679**. This application currently uses **spectral image MEFs**, not DR1 all-sky cube extraction.

The interface's orbital hero is **original CSS artwork** and is explicitly marked an illustration. It is not a NASA observation. No NASA or Space Apps trademark is used as an endorsement logo.

No Canadian Space Agency NEOSSat images, WISE imagery, Gaia DR3 overlays, or Aladin Lite features are embedded in this release. Those future additions must have their own provenance and license checks.
