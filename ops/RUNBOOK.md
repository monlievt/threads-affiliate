# Runbook Operasional — Backup, Restore, dan Pemulihan Bencana

Petunjuk operasional praktis untuk operator Threads Affiliate Automation.

---

## 1. Prosedur Backup Otomatis & Manual

Sistem mendukung dua mekanisme backup:
1. **Hot Backup SQLite (Lokal / Cron):**
   - Menggunakan SQLite Online Backup API yang aman dijalankan saat aplikasi sedang berjalan (tanpa lock transaksi).
   - Menghasilkan file checksum `.sha256` untuk verifikasi integritas data.
   - Kebijakan retensi otomatis: mempertahankan 14 backup harian dan 8 backup mingguan.

### Menjalankan Backup Manual:
```bash
# Jalankan skrip backup dari root direktori repo:
./ops/backup.sh
```
File snapshot akan tersimpan di direktori `backup/app-YYYYMMDD_HHMMSS.db` beserta file checksum `backup/app-YYYYMMDD_HHMMSS.db.sha256`.

---

## 2. Prosedur Pemulihan (Disaster Recovery)

Jika terjadi kerusakan database atau kegagalan server:

### Langkah Pemulihan:
1. **Hentikan layanan backend sementara:**
   ```bash
   docker compose stop backend
   ```
2. **Jalankan pemulihan database:**
   ```bash
   # Pulihkan dari file backup terbaru secara otomatis:
   ./ops/restore.sh

   # ATAU pulihkan dari file backup spesifik:
   ./ops/restore.sh backup/app-20261109_120000.db
   ```
3. **Mekanisme Keamanan Otomatis Saat Restore:**
   - Skrip membuat salinan keselamatan database saat ini (`data/app.db.pre_restore_<timestamp>`).
   - Membersihkan file `-wal` dan `-shm` yang basi untuk mencegah korupsi transaksi.
   - Menjalankan `PRAGMA integrity_check` pada database baru.
   - **Enforce Kill Switch ON:** Secara otomatis menyetel status kill switch ke `ON` (`active=1`) dan mencatat audit log pemulihan. Hal ini mencegah sistem langsung melakukan publikasi postingan secara spontan setelah startup.
4. **Nyalakan kembali layanan backend:**
   ```bash
   docker compose up -d backend
   ```
5. **Verifikasi kesehatan sistem:**
   - Periksa `/health` (pastikan DB `ok`).
   - Tinjau draf berstatus `publishing` atau `scheduled` di dashboard.
   - Jika semua aman, nonaktifkan kill switch melalui dashboard atau Telegram bot `/resume`.

---

## 3. Replikasi Real-Time Litestream (RPO ~ 1 detik)

Untuk server produksi, replikasi WAL real-time ke Cloudflare R2 / Backblaze B2 dikonfigurasi melalui `ops/litestream.yml`.

Jalankan replikasi dengan:
```bash
litestream replicate -config ops/litestream.yml
```
Untuk merestore database dari Cloudflare R2:
```bash
litestream restore -config ops/litestream.yml -o data/app.db
```
