import asyncio
import datetime
from typing import List
import random
import logging
import struct
import time

from hexbytes import HexBytes
from sqlalchemy.exc import IntegrityError
from web3 import Web3


from models import Bet, create_bet, rollback_session, set_last_processed_block


logger = logging.getLogger(__name__)
BET_PLACED_TOPIC = "0x4f1eed5e863a822b0f9eb960dfdab2cc5a99beec4b191f2a7a9c7e28e5a15524"


class EventProvider:
    def __init__(self, entrypoints: List[str], contract_address: str, first_block: int, reactor):
        self.w3 = self.init_entrypoint(entrypoints)
        self.event_filter = self.init_filter(self.w3, contract_address, first_block)
        self.reactor = reactor

    def init_entrypoint(self, entrypoints: List[str]):
        while entrypoints:
            candidate = random.choice(entrypoints)
            w3 = Web3(Web3.HTTPProvider(candidate))
            try:
                if w3.isConnected():
                    logger.info("Found active entry point %s", candidate)
                    return w3
            except Exception:
                entrypoints.remove(candidate)
                logger.info("Unable to connect to entrypoint %s", candidate)
        else:
            raise RuntimeError("No active entrypoints")

    def init_filter(self, w3, contract_address: str, first_block: int):
        logger.info("Log filtering will start from block %d", first_block)
        return w3.eth.filter({
            "address": contract_address,
            "fromBlock": first_block + 1,
            "topics": [BET_PLACED_TOPIC]
        })

    async def run(self):
        logger.info("Running initial filter")
        result = self.w3.eth.getFilterLogs(self.event_filter.filter_id)
        await self.process_result(result)
        while True:
            logger.info("Fetching updates")
            result = self.w3.eth.getFilterChanges(self.event_filter.filter_id)
            await self.process_result(result)
            await asyncio.sleep(60)

    @staticmethod
    def decode_event(event) -> Bet:
        bet_id_raw, user = event.topics[1:3]
        user = user[-20:]
        bet_id = 0
        for bet_id_8b_chunk in struct.unpack('>4Q', bet_id_raw):
            bet_id = bet_id * 2**64 + bet_id_8b_chunk
        data_offset = 2  # to adjust 0x
        next_field_size = 64
        direction = int(event.data[data_offset:data_offset+next_field_size], 16)
        data_offset += next_field_size
        next_field_size = 64
        amount = HexBytes(event.data[data_offset:data_offset+next_field_size])
        res = dict(id=bet_id, tx=event.transactionHash, sender=user, amount=amount,
                   created=datetime.datetime.utcnow(), direction=direction)
        logger.info('Received Bet %s', res)
        return Bet(**res)
        
    async def process_result(self, result):
        logger.info('processing %s', result)
        max_block_num = 0
        for event in result:
            bet = self.decode_event(event)

            # Not trying to store a bet before a bet is actually made.
            # Otherwise we are at risk of not sending the bet to the exchange.
            # This may end up in creating two bets. But this can be handled
            # by the duplicate error exception handler.
            try:
                self.reactor.on_bet_created(bet)
            except IntegrityError as e:
                if e.orig.args[0] == 1062:
                    # Optimistic concurrency control, as this should not happen very ofnet.
                    logger.warn("Bet %d already exists. Removing orders...", bet.id)
                    self.clean_up()
                else:
                    raise

            max_block_num = max(max_block_num, event["blockNumber"])
        
        self.reactor.on_cycle_finished()
        set_last_processed_block(max_block_num)

    def clean_up(self):
        rollback_session()
