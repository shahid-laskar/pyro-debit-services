import logging
from typing import List

from app.auth.token_manager import PyroAuthService

logger = logging.getLogger(__name__)


class EsimAdapter:
    service_type = "ESIM"
    implemented = False

    def __init__(
        self,
        token_manager:    PyroAuthService,
        enabled:          bool = False,
        batch_size:       int  = 200,
        interval_minutes: int  = 30,
        stuck_minutes:    int  = 10,
    ):
        self.token_manager    = token_manager
        self.enabled          = enabled
        self.batch_size       = batch_size
        self.interval_minutes = interval_minutes
        self.stuck_minutes    = stuck_minutes

        if enabled:
            logger.warning(
                "[ESIM] Adapter enabled but not yet implemented. "
                "Set ESIM_ENABLED=false until implementation is complete."
            )

    def fetch_and_claim(self, batch_size: int) -> List[dict]:
        if not self.enabled:
            return []
        raise NotImplementedError(
            "EsimAdapter.fetch_and_claim not yet implemented — "
            "set ESIM_ENABLED=false"
        )

    def map_to_pyro_params(self, record: dict) -> dict:
        raise NotImplementedError(
            "EsimAdapter.map_to_pyro_params not yet implemented"
        )

    def get_record_ref(self, record: dict) -> str:
        raise NotImplementedError(
            "EsimAdapter.get_record_ref not yet implemented"
        )

    def mark_success(self, record: dict, pyro_txn_id: str, remarks: str) -> None:
        raise NotImplementedError(
            "EsimAdapter.mark_success not yet implemented"
        )

    def mark_failed(self, record: dict, remarks: str) -> None:
        raise NotImplementedError(
            "EsimAdapter.mark_failed not yet implemented"
        )

    def reset_stuck_processing(self, stuck_minutes: int) -> int:
        if not self.enabled:
            return 0
        raise NotImplementedError(
            "EsimAdapter.reset_stuck_processing not yet implemented"
        )