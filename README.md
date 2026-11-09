# Threads Affiliate Automation

Sistem otomasi postingan afiliasi di Threads (Meta) dengan kontrol keselamatan berlapis.

## Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 async + aiosqlite, Pydantic v2, structlog
- **Frontend**: Next.js (App Router), TypeScript, Tailwind, shadcn/ui
- **Infra**: Docker Compose, Caddy, SQLite WAL

## Quick Start

```bash
cp .env.example .env
# Edit .env dengan nilai yang sesuai
docker compose up --build
```

Cek status sistem:
```bash
curl http://localhost:8000/health
```

## Struktur Tiket

Lihat `docs/09-TICKETS.md` untuk daftar tiket pengembangan.

## Aturan

Lihat `AGENTS.md` untuk aturan keras agent pengembang.

## Keselamatan

- **Kill switch default ON** saat startup — sistem tidak akan posting sampai admin mengaktifkannya.
- Semua publish wajib melewati `PublishGuard`.
- Token tersimpan terenkripsi di DB, tidak di environment.
- Log di-scrub dari secret/token/key.
