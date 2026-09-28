# db-query

Database access for agents. SQLite works out of the box (stdlib);
Postgres/MySQL go through their CLIs when a `--url` DSN is given.

```sh
db_query.py --db app.db --tables
db_query.py --db app.db --schema users
db_query.py --db app.db --sql "SELECT * FROM orders WHERE total > 100" --limit 20
db_query.py --url postgresql://localhost/db --sql "SELECT 1"
```

Rows stream as a JSON array on stdout. Write queries run too (the
result is an empty array) — the caller is responsible for safety.
