import datetime
from enum import Enum, auto
import logging

from sqlalchemy import Column, Integer, String, DateTime, CHAR, BINARY, update, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_engine = None
_session = None

Base = declarative_base()


class BetDirection(Enum):
    UP = 0
    DOWN = 1


class StateKeys(Enum):
    LAST_PROCESSED_BLOCK = "LB"


class Outcome(Enum):
    WIN = auto()
    LOSE = auto()
    TIMEOUT = auto()


class State(Base):
    __tablename__ = "state"

    name = Column(CHAR(10), primary_key=True)
    value = Column(CHAR(10))


class Bet(Base):
    __tablename__ = "bets"

    id = Column(Integer, primary_key=True)
    # ex.: 0xfaafd0e5a2414ae8a9828d360d56a3e57e963b3e5b98b15c4145792e474ee025
    tx = Column(BINARY(32), nullable=False)
    # ex.: 0x8BB2f0CB5e81B1228843f31F403bE4799db64818
    sender = Column(BINARY(20), nullable=False)
    # ex.: 0x0000000000000000000000000000000000000000000000000000000000000000
    #        0000000000000000000000000000000000000000000000000000000000000001
    amount = Column(BINARY(32), nullable=False)
    created = Column(DateTime, nullable=False)
    direction = Column(Integer, nullable=False)  # class BidDirection
    outcome = Column(Integer)  # class Outcome


def init_db(config: dict):
    """ config should contain "conn" item """
    global _engine
    global _session
    _engine = create_engine(config["conn"])
    _session = sessionmaker(bind=_engine)()


def get_last_processed_block(default: int):
    res = (
        _session.query(State)
        .filter_by(name=StateKeys.LAST_PROCESSED_BLOCK.value)
        .first()
    )
    return int(res.value) if res is not None else default


def set_last_processed_block(block: int):
    _session.commit()
    sql = (
        f"INSERT INTO {State.__tablename__} ({State.name.key}, {State.value.key}) "
        f"VALUES (:name, :value) "
        f"ON DUPLICATE KEY UPDATE value = GREATEST(:value, value)"
    )

    with _engine.connect() as con:
        #logging.debug("Setting last processed block to %s %s", sql, (StateKeys.LAST_PROCESSED_BLOCK.value, block))
        #con.execute(sql, {"name": StateKeys.LAST_PROCESSED_BLOCK.value, "value": block})
        con.execute(text(sql), {"name": StateKeys.LAST_PROCESSED_BLOCK.value, "value": block})

def create_bet(bet: Bet):
    _session.add(bet)
    _session.commit()
    return bet.id


def rollback_session():
    _session.rollback()


def get_bet(base):
    bet = _session.query(Bet).filter_by(id=base).first()
    return bet


def expire_bet(base):
    stmt = update(Bet).where(Bet.id == base).values(outcome=Outcome.TIMEOUT.value)
    _session.execute(stmt)
    _session.commit()


def get_stale_bets(timeout):
    now = datetime.datetime.utcnow()
    bets = (
        _session.query(Bet)
        .filter(Bet.outcome == None, Bet.created < now - timeout)
        .all()
    )
    return bets
