"""
app/debit/services/base.py
--------------------------
DebitServiceAdapter is a typing.Protocol — adapters implement the interface
by duck-typing, no inheritance required.

Each adapter encapsulates one Oracle table + one set of Pyro credentials.
The generic processor (app/debit/processor.py) only speaks this interface,
so adding SimSwap or ESIM later requires zero changes outside the adapter file.
"""

from typing import List, Protocol, runtime_checkable

from app.auth.token_manager import PyroAuthService


@runtime_checkable
class DebitServiceAdapter(Protocol):
    """Structural interface every debit service adapter must satisfy."""

    service_type:  str              # "FANCYSALE" | "SIMSWAP" | "ESIM"
    enabled:       bool
    batch_size:    int
    token_manager: PyroAuthService

    # ── Data access ────────────────────────────────────────────────────────────

    def fetch_and_claim(self, batch_size: int) -> List[dict]:
        """
        Atomically SELECT eligible records then claim them (set status → P).

        The UPDATE uses the same eligibility predicate as the SELECT to prevent
        double-claiming under concurrent restarts.  Only rows whose UPDATE
        returns rowcount == 1 are included in the returned list.

        Returns a list of full row dicts for claimed records (may be empty).
        """
        ...

    def map_to_pyro_params(self, record: dict) -> dict:
        """
        Map an Oracle row dict → kwargs for wallet_adjustment().

        Must return exactly:
            client_id, source_msisdn, dest_msisdn,
            amount (float), mpin (plain text, already decrypted), remarks
        Raises ValueError on decrypt or validation failure — processor catches this
        and marks the record as failed without calling Pyro.
        """
        ...

    def get_record_ref(self, record: dict) -> str:
        """
        Human-readable primary reference for logging.
        FancySale: REFID.  SimSwap/ESIM: their equivalent PK.
        """
        ...

    # ── State transitions ──────────────────────────────────────────────────────

    def mark_success(self, record: dict, pyro_txn_id: str, remarks: str) -> None:
        """
        Persist Pyro success to Oracle.
        FancySale: CAF_ENTRY_DONE='Y', TRANSACTION_ID=pyro_txn_id, PYRO_REMARKS=remarks.
        Non-fatal — log ERROR on DB failure, never raise.
        """
        ...

    def mark_failed(self, record: dict, remarks: str) -> None:
        """
        Persist Pyro failure to Oracle.
        FancySale: CAF_ENTRY_DONE='R', PYRO_REMARKS=remarks.
        Non-fatal — log ERROR on DB failure, never raise.
        """
        ...

    def reset_stuck_processing(self, stuck_minutes: int) -> int:
        """
        Reset CAF_ENTRY_DONE='P' records that have been stuck longer than
        stuck_minutes back to 'N' (eligible).
        Returns count of rows reset (0 if service is disabled).
        """
        ...