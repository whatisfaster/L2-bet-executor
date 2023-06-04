import decimal
import logging

from binance_wrappers import inverse_role, get_client_order_id, OrderRole
from models import Bet, BetDirection, create_bet


class Reactor:
    def __init__(self, config, contract_caller, create_order, check_open_orders, cancel_order):
        self.config = config
        self.contract_caller = contract_caller
        self.create_order = create_order
        self.check_open_orders = check_open_orders
        self.cancel_order = cancel_order
        self.binance_config = self.config["binance"]

    def boundary_calculator(self, current_price, direction):
        safebelt_ratio = decimal.Decimal(self.config["algo"]["safebelt-trigger"]) / decimal.Decimal(100.0)
        wintrigger_ratio = decimal.Decimal(self.config["algo"]["win-trigger"]) / decimal.Decimal(100.0)
        stop_loss_price, take_profit_price = (
            (
                current_price * (decimal.Decimal(1.0) - safebelt_ratio),
                current_price * (decimal.Decimal(1.0) + wintrigger_ratio),
            )
            if (direction == BetDirection.UP)
            else (
                current_price * (decimal.Decimal(1.0) + safebelt_ratio),
                current_price * (decimal.Decimal(1.0) - wintrigger_ratio),
            )
        )
        return stop_loss_price, take_profit_price

    def on_bet_created(self, bet: Bet):
        base_order = self.create_order(self.binance_config, bet.id, BetDirection(bet.direction),
                                       decimal.Decimal(int(bet.amount.hex(), 16)) / decimal.Decimal(10**18),
                                       self.boundary_calculator)
        self.contract_caller.on_bet_accepted(bet.id)
        create_bet(bet)

    def on_cycle_finished(self):
        _, orders_to_close = self.check_open_orders(self.binance_config)
        self.process_orders_to_close(orders_to_close)

    def process_orders_to_close(self, orders_to_close):
        for base, role in orders_to_close:
            logging.info("Leg %s:%s still remains open, closing it", base, role)

            try:
                self.cancel_order(self.binance_config, get_client_order_id(base, role))
            except Exception as e:
                logging.exception("Unable to cancel order %s", e)

            if role == OrderRole.TAKE_PROFIT:
                logging.info(
                    "Take profit order %s:%s was still on fly, so stop loss was triggered.",
                    base,
                    role,
                )
                self.contract_caller.mark_bet_as_won(int(base), 1, 1)
            else:
                logging.info(
                    "Stop loss order %s:%s was still on fly, so take profit was triggered.",
                    base,
                    role,
                )
                self.contract_caller.mark_bet_as_won(int(base), 1, 1)

        # for base in open_orders:
        #         bet = get_bet(base)
        #         if bet:
        #             logger.debug(
        #                 "Order %s is %d seconds old",
        #                 bet.id,
        #                 (datetime.datetime.utcnow() - bet.created).total_seconds(),
        #             )
        #         else:
        #             logger.warning("Unable to find open bet %s in the system", base)