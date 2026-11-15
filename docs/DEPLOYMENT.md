# Deployment and Operations

## Recommended deployment

Use a managed Linux Docker host or VM with at least **2 vCPUs / 4 GB RAM**, persistent data volume, and outbound HTTPS to IRSA, Caltech Exoplanet Archive, JPL SSD and CDS/mirror hosts. Downloading and reprojecting FITS cutouts may require additional memory; first test load and quotas. A public domain and TLS are required for judges.

### Docker Compose

```bash
cp .env.example .env
# Edit config if needed
sudo docker compose up --build -d
curl -fsS http://127.0.0.1:8000/api/health
```

Put Nginx, Traefik or Caddy in front of `127.0.0.1:8000`. Configure HTTPS, request-size limits, per-IP rate limiting, timeouts > 30 s for FITS download, and caching of static UI only. Do not cache API answers keyed only by object name.

### Reverse proxy notes

- Deny public access to `local_data` and server files; only use `/api` endpoints.
- Ensure the application receives proper proxy headers and HTTPS redirects.
- Mount `/app/local_data` on persistent storage; schedule backups of SQLite annotations.
- For multi-worker deployments move the in-memory trusted SIA record index to Redis (currently one-worker design) and SQL annotations to PostgreSQL with authentication.
- Use a job queue and storage quotas for large datasets before opening heavy FITS endpoints to the general public.
- Enable service monitoring, structured logs, cache retention/expiry and remote API circuit breakers for production. These are operational recommendations, **not implemented** in this release.

## Application environment

`SKYSHIFT_DATA_DIR` – storage path for cached FITS and SQLite.

`SKYSHIFT_MAX_REMOTE_BYTES` – single-response limit (defaults 45 MB).

`SKYSHIFT_HTTP_TIMEOUT` – upstream read timeout (defaults 18 s).

`LOG_LEVEL` – Python log level.

Never commit API keys or credentials. These public sources generally require no credentials for the endpoints used by the starter backend.

## Verify public deployment

1. Run `curl https://YOUR-DOMAIN/api/health` and confirm HTTP 200.
2. Search custom coordinates and check outgoing request logs for the correct RA/Dec in `POS=CIRCLE`.
3. Inspect SIA records; verify source FITS URLs really belong to the selected sky field.
4. Open a cutout and inspect WCS, detector, date and image preview.
5. Test two records with the same area and compatible wavelengths; run difference and compare quality masks.
6. Try an empty region and 503 simulation to confirm no substitute image appears.
7. Run `python scripts/validate_targets.py --live` in the deployed environment, keeping the output as judge evidence.
8. Check mobile display, language switch, no JavaScript errors, and degraded network error states.

**Not deployed in build environment:** no credentials, public cloud account or DNS privileges were provided. `https://YOUR-DOMAIN` is a placeholder in the documentation, not a claim that the site is live.
