# Database Backup and Recovery Guide

## Backup Strategy

### Automated Backups (Recommended for Production)

For production deployments using PostgreSQL, set up automated backups:

```bash
# Daily backup at 2 AM
0 2 * * * pg_dump -U your_user -h localhost your_database > /backups/db_$(date +\%Y\%m\%d).sql

# Keep last 7 days, last 4 weeks, last 12 months
```

### Manual Backup (SQLite Development)

```bash
# Stop the application first to ensure consistency
# Then backup the database file
cp db.sqlite3 db.sqlite3.backup-$(date +%Y%m%d-%H%M%S).sqlite3

# Or using SQLite's built-in backup
sqlite3 db.sqlite3 ".backup 'db.sqlite3.backup-$(date +%Y%m%d-%H%M%S).sqlite3'"
```

### Important Files to Backup

1. **Database**: `db.sqlite3` (SQLite) or PostgreSQL database
2. **Media files**: `media/` directory (uploaded images, PDFs)
3. **Environment variables**: `.env` file (contains secrets)
4. **Migrations**: All files in `*/migrations/` directories

## Recovery Procedure

### SQLite Recovery

```bash
# Stop the application
# Replace the corrupted database with the backup
cp db.sqlite3.backup-YYYYMMDD-HHMMSS.sqlite3 db.sqlite3

# Verify integrity
sqlite3 db.sqlite3 "PRAGMA integrity_check;"

# Restart the application
```

### PostgreSQL Recovery

```bash
# Drop the current database (if needed)
dropdb your_database

# Create a new database
createdb your_database

# Restore from backup
psql -U your_user -h localhost your_database < /backups/db_YYYYMMDD.sql

# Run any pending migrations
python manage.py migrate
```

## Media Files Backup

```bash
# Backup media directory
tar -czf media-backup-$(date +%Y%m%d).tar.gz media/

# Restore
tar -xzf media-backup-YYYYMMDD.tar.gz
```

## Migration to PostgreSQL (Production)

When moving from SQLite to PostgreSQL:

1. Export SQLite data:
```bash
python manage.py dumpdata > data.json
```

2. Configure PostgreSQL in `.env`:
```
DB_ENGINE=django.db.backends.postgresql
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

3. Create PostgreSQL database and run migrations:
```bash
createdb your_database
python manage.py migrate
```

4. Import data:
```bash
python manage.py loaddata data.json
```

## Security Notes

- **Never commit database backups to Git**
- **Encrypt backups in production** (e.g., using gpg)
- **Store backups in a separate location** from the application server
- **Test recovery procedures regularly**
- **Keep multiple backup generations** (daily, weekly, monthly)
