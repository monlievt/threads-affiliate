# AGENTS.md — Aturan untuk agent pengembang

## Misi
Bangun "Threads Affiliate Automation" sesuai `docs/`. Prioritas: **keselamatan akun > kebenaran > kesederhanaan > fitur**.

## Aturan keras (tidak boleh dilanggar)
1. Hanya memakai API resmi Threads. Dilarang scraping, bot like/follow, atau otomasi browser pada Threads.
2. Semua publish WAJIB lewat `PublishGuard` (docs/06). Tidak ada jalur publish yang melewatinya, termasuk skrip dev/test.
3. Kill switch default **ON saat start** (`KILL_SWITCH_ON_START=true`). Sistem tidak boleh posting sampai admin menyalakannya.
4. Jangan menaikkan batas keras di docs/06 atau `.env` tanpa persetujuan eksplisit user.
5. Jangan pernah menulis token, API key, atau password ke log, repo, atau response API. Token disimpan terenkripsi.
6. Jangan menghasilkan klaim harga, diskon, stok, rating palsu, klaim kesehatan, atau urgensi palsu dalam konten (docs/06 §4).
7. Link affiliate hanya dari domain pada allowlist (`benable.com` secara default). Tidak ada pemendek link atau cloaking buatan sendiri.
8. Setiap postingan berafiliasi harus memuat disclosure sesuai pengaturan.
9. Jangan mengarang endpoint API atau nama field. Tandai `[VERIFIKASI]` dan minta user cek dokumentasi resmi bila ragu.

## Cara kerja
- Baca `docs/` berurutan sebelum menulis kode. Jika ada konflik antar dokumen, tanya user.
- Kerjakan satu tiket sekali (docs/09). Tiap tiket: rencana singkat → implementasi → test → ringkasan → berhenti.
- Perubahan skema DB: buat migrasi Alembic, jangan edit tabel manual. Minta konfirmasi dulu.
- Tulis test untuk semua logika di `safety/`, `scheduler/`, `content/validators`. Cakupan minimal 85% untuk modul tersebut.
- Tidak ada panggilan jaringan nyata di unit test. Gunakan fake/mocking; sediakan `FakeThreadsClient`.
- Setiap aksi sistem yang berdampak keluar (publish, reply, kirim telegram) dicatat di tabel `audit_log`.

## Konvensi kode
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, slowapi (rate limit API), ruff + mypy (strict untuk `safety/`).
- Frontend: Next.js (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query.
- Waktu disimpan UTC; tampil di UI dengan `Asia/Jakarta`.
- Struktur repo: lihat docs/03 §6. Jangan menambah dependensi besar tanpa alasan tertulis.
- Commit kecil, pesan Conventional Commits.

## Definition of Done (semua tiket)
Test lulus, lint/type-check bersih, dokumen terkait diperbarui, tidak ada secret di diff, perilaku aman saat gagal (fail closed: jika ragu, jangan posting).
