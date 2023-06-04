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

Usage
=====

```
$ source venv/bin/activate
$ python main.py config.yaml
```



Description
===========

Script runs two tasks:
 - one to monitor smart contracts. Every time new event happens:
   a) new bet is created + stop loss order + take profit order
   b) last processed block is updated (so that we don't re-scan on restart)
   c) event is signalled to the contract (so the funds are now locked)

 - one to monitor open sl/tp orders
   a) if both open - checking that they are not too old
   b) if only one is opened - sl or tp event happened, figure out what remained (how? we are using the last digit of an client order id to encode this)
   c) if none is there - well :( not nice, that means we are not updating statuses of orders fast enough, and because of some crazy volatility both orders were triggered.
   