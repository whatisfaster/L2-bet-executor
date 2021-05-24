How to migrate the DB?
======================

In order to run migrations (including the initial one) you need to
update alembic.ini, copying there the value from config.yaml
for sqlalchemy.url.

Update `models.py` and then run

```
$ source venv/bin/activate
$ alembic revision --autogenerate -m "YOUR DESCRIPTION"
```

Before the first use
====================

1. Update `alembic.ini` with the correct db connection string.
1. Create the config.yml based on `config_sample.yml`
