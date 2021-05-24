import argparse
import asyncio
import datetime
import logging
import sys
import time

import yaml

from binance_wrappers import (
    SUPPORTED_PRECISION,
    OrderRole,
    create_order,
    create_stoppers,
    get_orders,
    get_client_order_id,
    cancel_order,
    check_open_orders,
)
from contract import ContractCaller
from event_provider import EventProvider
from reactor import Reactor
from models import (
    Bet,
    create_bet,
    expire_bet,
    init_db,
    get_bet,
    get_last_processed_block,
    set_last_processed_block,
    get_stale_bets,
    BetDirection,
)


logger = logging.getLogger(__name__)


def extract_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=open)
    ns = parser.parse_args()

    config = yaml.load(ns.config)
    ns.config.close()
    return config


async def check_stale_bets_task(timeout, binance_config, contract_caller):
    while True:
        logging.debug("Checking for stale bets")
        stale_bets = get_stale_bets(timeout)
        for bet in stale_bets:
            contract_caller.mark_bet_as_expired(bet.id)
            expire_bet(bet.id)
            base_id = f'{bet.id}'
            logging.info("Processing stale bet %s", base_id)
            for role in (OrderRole.STOP_LOSS, OrderRole.TAKE_PROFIT):
                client_order_id = get_client_order_id(base_id, role)
                try:
                    cancel_order(binance_config, client_order_id)
                except Exception as e:
                    logging.warn(
                        "Unable to cancel the order. "
                        "Probably it was executed right now, but because "
                        "we were trying to cancel it, that means, that "
                        "we have a full right to claim it as an timed out. "
                        "Error: %s", e)
            
            # Remove position
            reversed_direction = BetDirection((bet.direction + 1) % 2)
            create_order(binance_config, f"{bet.id}", reversed_direction)
        await asyncio.sleep(60)


def main():
    config = extract_config()
    init_db(config["db"])

    contract_caller = ContractCaller(
        config["incoming"]["rpc"],
        config["incoming"]["contract"],
        config["rewards"]["sender_address"],
        config["rewards"]["private_key"],
    )

    reactor = Reactor(
        config=config,
        contract_caller=contract_caller,
        create_order=create_order,
        create_stoppers=create_stoppers,
        check_open_orders=check_open_orders,
        cancel_order=cancel_order,
    )
    events = EventProvider(
        config["incoming"]["rpc"],
        config["incoming"]["contract"],
        get_last_processed_block(config["incoming"]["first_block"]),
        reactor,
    )
    
    loop = asyncio.get_event_loop()
    loop.create_task(
        check_stale_bets_task(
            timeout=datetime.timedelta(seconds=config["algo"]["timeout-seconds"]),
            binance_config=config["binance"],
            contract_caller=contract_caller,
        )
    )

    loop.create_task(events.run())

    loop.run_forever()
    return
    contract_caller.on_bet_accepted()


    loop = asyncio.get_event_loop()
    loop.run_until_complete(events.run())
    return

    cfg = config["binance"]
    direction = BetDirection.DOWN
    base_order_id = create_bet(direction, "AHHHHA")
    base_order = create_order(cfg, base_order_id, direction)
    stop_loss_price, take_profit_price = (
        (
            base_order.avgPrice * (1.0 - config["algo"]["safebelt-trigger"] / 100.0),
            base_order.avgPrice * (1.0 + config["algo"]["win-trigger"] / 100.0),
        )
        if (direction == BetDirection.UP)
        else (
            base_order.avgPrice * (1.0 + config["algo"]["safebelt-trigger"] / 100.0),
            base_order.avgPrice * (1.0 - config["algo"]["win-trigger"] / 100.0),
        )
    )
    create_stoppers(
        cfg,
        base_order,
        direction,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )


    # get_orders(cfg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    sys.exit(main())