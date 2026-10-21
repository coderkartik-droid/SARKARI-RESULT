import sqlite3

c = sqlite3.connect("db.sqlite3")
tables = [
    r[0]
    for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
]
for t in tables:
    try:
        count = c.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        if count:
            print(f"{t}: {count}")
    except Exception as e:
        print(t, "ERR", e)
print("--- superusers ---")
try:
    for r in c.execute(
        "SELECT id, username, email, is_superuser, is_staff, is_active FROM accounts_emailuser WHERE is_superuser=1"
    ):
        print(r)
except Exception as e:
    print("superuser query err", e)
