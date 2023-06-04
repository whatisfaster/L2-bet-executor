"""
This module is just a wrapper over python-binance module.
"""

from collections import defaultdict
import decimal
import enum
import decimal
from typing import Tuple, List
import logging
import pprint
import math

from binance_f import RequestClient
from binance_f.model.order import Order
from binance_f.model.constant import OrderSide, OrderType, OrderRespType, FuturesMarginType
from binance_f.exception.binanceapiexception import BinanceApiException

from models import BetDirection


logger = logging.getLogger(__name__)


class OrderRole(enum.Enum):
    INITIAL_MKT = enum.auto()
    TAKE_PROFIT = enum.auto()
    STOP_LOSS = enum.auto()


def inverse_role(r: OrderRole):
    if r == OrderRole.TAKE_PROFIT:
        return OrderRole.STOP_LOSS
    if r == OrderRole.STOP_LOSS:
        return OrderRole.TAKE_PROFIT
    raise Exception("Unable to reverse role %s", r)


def get_client_order_id(base: str, role: OrderRole) -> str:
    return f"{base}{role.value}"


def parse_client_order_id(order_id: str) -> Tuple[str, OrderRole]:
    base = order_id[:-1]
    order_role = OrderRole(int(order_id[-1]))
    return (base, order_role)


def client(fn):
    def _client(config, *args, **kwargs):
        client = RequestClient(
            api_key=config["API_Key"],
            secret_key=config["Secret_Key"],
            url=config["URL"],
        )
        return fn(client, *args, **kwargs)

    return _client


@client
def create_order(client, base_order_id: str, direction: BetDirection, position_usd_amount: decimal.Decimal, boundary_calculator):
    # TESTING
    position_usd_amount *= 1000

    leverage = 46
    position_usd_amount *= leverage

    client.change_initial_leverage("BTCUSDT", leverage)
    try:
        client.change_margin_type("BTCUSDT", FuturesMarginType.ISOLATED)
    except BinanceApiException as e:
        ok_errors = ['[Executing] -4046: No need to change margin type.'] # No need to change margin type
        logger.error("Raising the exception because error message %r is not in %r", e.error_message, ok_errors)
        if (e.error_message not in ok_errors):
            raise
    btc_price = client.get_mark_price(symbol="BTCUSDT").markPrice
    exact_value = position_usd_amount / decimal.Decimal(btc_price)
    # quantity = math.floor(exact_value / precision) * precision
    quantity = str(exact_value.quantize(decimal.Decimal('.001'), rounding=decimal.ROUND_DOWN))
    
    logger.info("BTC_price=%s, position_usd_amount=%s, quantity=%s",
                btc_price, position_usd_amount, quantity)
    try:
        result = client.post_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY if direction == BetDirection.UP else OrderSide.SELL,
            ordertype=OrderType.MARKET,
            quantity=quantity,
            positionSide="BOTH",
            newClientOrderId=get_client_order_id(base_order_id, OrderRole.INITIAL_MKT),
            newOrderRespType=OrderRespType.RESULT
        )
    except BinanceApiException as e:
        ok_errors = ['[Executing] -4015: Client order id is not valid.']
        logger.error("Raising the exception because error message %r is not in %r", e.error_message, ok_errors)
        if (e.error_message not in ok_errors):
            raise
        else:
            logger.info("Worked with overlap, tried to create an order with the same ID: %s, got rejected, its OK", get_client_order_id(base_order_id, OrderRole.INITIAL_MKT))
            return
    logger.info("Created and executed order for the position: %r", result)
    assert result.status == "FILLED"

    stop_loss_price, take_profit_price = boundary_calculator(decimal.Decimal(result.avgPrice), direction)
    if direction == BetDirection.UP:
        stop_loss_price = stop_loss_price.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_UP)
        take_profit_price = take_profit_price.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_DOWN)
    else:
        stop_loss_price = stop_loss_price.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_DOWN)
        take_profit_price = take_profit_price.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_UP)
    logger.info("Stop loss %s , take profit %s", stop_loss_price, take_profit_price)

    create_stoppers(client, result, direction, take_profit_price, stop_loss_price)


def create_stoppers(client, base_order: Order, direction: BetDirection,
                    take_profit_price: float = None, stop_loss_price: float = None):
    side = OrderSide.SELL if (direction == BetDirection.UP) else OrderSide.BUY
    base = parse_client_order_id(base_order.clientOrderId)[0]
    executed_qty = decimal.Decimal(base_order.executedQty).quantize(decimal.Decimal("0.001"))
    try:
        stop_loss_order = client.post_order(
            symbol=base_order.symbol,
            side=side,
            ordertype=OrderType.STOP_MARKET,
            quantity=executed_qty,
            stopPrice=str(stop_loss_price),
            positionSide="BOTH",
            newClientOrderId=get_client_order_id(base, OrderRole.STOP_LOSS),
        )
        logger.info("Created (ack) stop loss order: %r", stop_loss_order)
    except BinanceApiException as e:
        if e.error_message == '[Executing] -4015: Client order id is not valid.':
            # TODO: deduce position
            pass

    try:
        take_profit_order = client.post_order(
            symbol=base_order.symbol,
            side=side,
            ordertype=OrderType.TAKE_PROFIT_MARKET,
            quantity=executed_qty,
            stopPrice=str(take_profit_price),
            positionSide="BOTH",
            newClientOrderId=get_client_order_id(base, OrderRole.TAKE_PROFIT),
        )
        logger.info("Created (ack) take profit order: %r", take_profit_order)
    except BinanceApiException as e:
        if e.error_message == '[Executing] -4015: Client order id is not valid.':
            # TODO: deduce position, remove stop order
            pass


@client
def get_orders(client):
    # result = client.get_order(origClientOrderId="20210222064502")
    result = client.get_open_orders("BTCUSDT")
    pprint.pprint(result)


@client
def cancel_order(client, client_order_id):
    # result = client.get_order(origClientOrderId="20210222064502")
    # result = client.get_open_orders("BTCUSDT")
    result = client.cancel_order(symbol="BTCUSDT", origClientOrderId=client_order_id)
    pprint.pprint(result)


@client
def check_open_orders(client) -> Tuple[List[str], List[Tuple[str, OrderRole]]]:
    """
    Gets a list of open orders from Binance and classifies them as
      - orders still open (we need to check if they have timed out).
      - orders to close - orders where one of the legs was triggered,
        so we need to close the open leg, and check for the reward
        logic.

    Because our ClientOrderIDs have a format base+0 base+1 base+2,
    we can get all open orders and check if both of them (base+1, base+2)
    are open. If yes, then base order is still open. Otherwise, we need to close
    other orders and decide about payouts.
    """
    orders = client.get_open_orders("BTCUSDT")
    buckets = defaultdict(list)
    logger.info("Currently open orders: %r", orders)
    for order in orders:
        base, role = parse_client_order_id(order.clientOrderId)
        buckets[base].append(role)

    open_orders = []
    orders_to_close = []

    for base, open_roles in buckets.items():
        base = int(base)
        if len(open_roles) > 1:
            # NB! This method should be called on a same thread as
            # order creator, because stop order / take profit creation
            # is not transactional, so, if runs in parallel, it is possible
            # that this method will see only created stop-loss order, and
            # it'll make a decision that take profit is already closed.
            # But it was not created yet actually.
            open_orders.append(base)
        elif len(open_roles) == 1:
            orders_to_close.append((base, open_roles[0]))

    return open_orders, orders_to_close
