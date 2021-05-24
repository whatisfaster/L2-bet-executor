import random
from typing import List
import logging
import json

from web3 import Web3


logger = logging.getLogger(__name__)


class ContractCaller:
    def __init__(
        self,
        entrypoints: List[str],
        contract_address: str,
        sender_address: str,
        private_key: str,
    ):
        self.entrypoint = entrypoints
        self.contract_address = contract_address
        self.private_key = private_key
        self.w3 = self.init_entrypoint(entrypoints)
        with open("abi.json") as abi_file:
            abi = json.load(abi_file)
        self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
        self.nonce = self.w3.eth.getTransactionCount(sender_address)
        logger.debug("Started ContractCaller, nonce=%d", self.nonce)

    def on_bet_accepted(self, bet_id):
        self.make_call(self.contract.functions.betAccepted(bet_id, 1, 0, 2))

    def mark_bet_as_expired(self, bet_id):
        self.make_call(self.contract.functions.betCanceled(bet_id))

    def mark_bet_as_won(self, bet_id, closing_price, amount):
        self.make_call(self.contract.functions.betWon(bet_id, closing_price, amount))

    def mark_bet_as_lost(self, bet_id, closing_price, amount):
        self.make_call(self.contract.functions.betLost(bet_id, closing_price, amount))

    def make_call(self, bounded_fn):
        txn = bounded_fn.buildTransaction(
            {
                "chainId": 97,
                "gas": 200000,
                "gasPrice": Web3.toWei("200", "gwei"),
                "nonce": self.nonce,
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.private_key)
        self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        self.nonce = self.nonce + 1

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
