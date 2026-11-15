# SPHEREx IRSA 502 recovery

The Render-hosted application repeatedly received HTTP 502 Proxy Error from https://irsa.ipac.caltech.edu/SIA for real SPHEREx DR1 and QR3 queries. This response does NOT establish that the requested sky region has zero observations.

This change adds a bounded, allow-listed fallback using NASA/IPAC IRSA's officially documented TAP metadata service at https://irsa.ipac.caltech.edu/TAP/sync, querying the real spherex.artifact and spherex.plane tables. Only verified IRSA release-specific FITS URLs may be displayed. If neither service responds, the application reports unavailable and preserves both failure details. Deep-field classification, wavelength bounds, and absent timestamps are not inferred.

Test scope: mocked HTTP contract and failure tests. Live astronomy validation must be performed separately; successful Render deployment alone is not proof that the IRSA upstream is reachable.

References:
- https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/
- https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/
