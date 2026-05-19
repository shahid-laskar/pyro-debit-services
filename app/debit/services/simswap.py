"""
app/debit/services/simswap.py
------------------------------
SimSwap debit adapter — STUB.  Not yet implemented.

Set SIMSWAP_ENABLED=true in .env only after:
  1. Oracle table DDL and column mapping are confirmed with the team.
  2. NotImplementedError bodies below are replaced with real logic.

fetch_and_claim() returns [] when disabled so the scheduler job is harmless.
"""

import logging
from typing import List

from app.auth.token_manager import PyroAuthService

logger = logging.getLogger(__name__)


class SimswapAdapter:
    service_type = "SIMSWAP"
    implemented = False

    def __init__(
        self,
        token_manager: PyroAuthService,
        enabled:       bool = False,
        batch_size:    int  = 200,
    ):
        self.token_manager = token_manager
        self.enabled       = enabled
        self.batch_size    = batch_size

        if enabled:
            logger.warning(
                "[SIMSWAP] Adapter enabled but not yet implemented. "
                "Set SIMSWAP_ENABLED=false until implementation is complete."
            )

    def fetch_and_claim(self, batch_size: int) -> List[dict]:
        if not self.enabled:
            return []
        raise NotImplementedError(
            "SimswapAdapter.fetch_and_claim not yet implemented — "
            "set SIMSWAP_ENABLED=false"
        )

    def map_to_pyro_params(self, record: dict) -> dict:
        raise NotImplementedError(
            "SimswapAdapter.map_to_pyro_params not yet implemented"
        )

    def get_record_ref(self, record: dict) -> str:
        raise NotImplementedError(
            "SimswapAdapter.get_record_ref not yet implemented"
        )

    def mark_success(self, record: dict, pyro_txn_id: str, remarks: str) -> None:
        raise NotImplementedError(
            "SimswapAdapter.mark_success not yet implemented"
        )

    def mark_failed(self, record: dict, remarks: str) -> None:
        raise NotImplementedError(
            "SimswapAdapter.mark_failed not yet implemented"
        )

    def reset_stuck_processing(self, stuck_minutes: int) -> int:
        if not self.enabled:
            return 0
        raise NotImplementedError(
            "SimswapAdapter.reset_stuck_processing not yet implemented"
        )
