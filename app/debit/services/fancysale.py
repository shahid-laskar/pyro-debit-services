"""
app/debit/services/fancysale.py
--------------------------------
FancySaleAdapter — reads from Oracle CAF_ADMIN.VANITYSALE_FRANCH_DATA and
drives the wallet-debit flow through Pyro /erp-stock-api/service-wallet-adjustment.

MPIN decryption strategy
------------------------
The MPIN column is encrypted at rest using Oracle's own symmetric cipher via the
database function CAF_ADMIN.F_DECRYPT.  We therefore decrypt at query time:

    CAF_ADMIN.F_DECRYPT(MPIN) AS plain_mpin

in the SELECT — the result is already plain text by the time Python sees it.
We do NOT call the Python decrypt() function for MPIN; fancysale_secret_key is
only used by the Pyro HTTP client to encrypt the request body.

State machine (CAF_ENTRY_DONE)
-------------------------------
  N   → P  : fetch_and_claim()
  QM  → P  : fetch_and_claim() — MPIN corrected by Sanchar Mitra
  QB  → P  : fetch_and_claim() — balance topped up by Sanchar Mitra
  P   → Y  : mark_success()
  P   → R  : mark_failed()
  P   → N  : reset_stuck_processing() — scheduler cleanup job
"""

import logging
from typing import List

from app.auth.token_manager import PyroAuthService
from app.db.oracle import get_oracle_conn

logger = logging.getLogger(__name__)

# ── Oracle state constants ────────────────────────────────────────────────────
VS_STATUS_N  = "N"      # new / eligible
VS_STATUS_P  = "P"      # processing (set by us)
VS_STATUS_Y  = "Y"      # success    (set by us)
VS_STATUS_R  = "R"      # rejected   (set by us on Pyro failure)
VS_STATUS_QM = "QM"     # MPIN error — Sanchar Mitra sets; we re-pick after fix
VS_STATUS_QB = "QB"     # Balance error — Sanchar Mitra sets; we re-pick after top-up

FETCH_ELIGIBLE = (VS_STATUS_N, VS_STATUS_QM, VS_STATUS_QB)


class FancySaleAdapter:
    """Full implementation of DebitServiceAdapter for FancySale."""

    service_type  = "FANCYSALE"
    implemented   = True

    def __init__(
        self,
        token_manager: PyroAuthService,
        enabled:       bool = True,
        batch_size:    int  = 200,
    ):
        self.token_manager = token_manager
        self.enabled       = enabled
        self.batch_size    = batch_size

    # ── Interface implementation ───────────────────────────────────────────────

    def fetch_and_claim(self, batch_size: int) -> List[dict]:
        """
        Step 1 — SELECT eligible rows ordered by TRANS_DATE ASC.
        Step 2 — Attempt atomic claim for each row (UPDATE WHERE state IN eligible).
        Step 3 — Only rows whose UPDATE returned rowcount == 1 are returned.

        MPIN is decrypted inside Oracle by CAF_ADMIN.F_DECRYPT so Python receives
        plain text in the 'plain_mpin' column — no further decrypt needed.
        """
        if not self.enabled:
            return []

        select_sql = """
            SELECT
                REFID,
                CTOPUPNO,
                FANCY_NO,
                AMOUNT,
                CAF_ADMIN.F_DECRYPT(MPIN) AS plain_mpin,
                MPIN_LENGTH,
                SS_REQUEST_ID,
                CSCCODE,
                CIRCLE_CODE,
                TRANS_DATE,
                MODULE_TYPE,
                CAF_ENTRY_DONE
            FROM CAF_ADMIN.VANITYSALE_FRANCH_DATA
            WHERE CAF_ENTRY_DONE IN ('N', 'QM', 'QB')
              AND ROWNUM <= :batch_size
            ORDER BY TRANS_DATE ASC
        """

        claim_sql = """
            UPDATE CAF_ADMIN.VANITYSALE_FRANCH_DATA
            SET    CAF_ENTRY_DONE = 'P',
                   CAF_ENTRY_DATE = SYSDATE,
                   PYRO_REMARKS   = 'Processing started'
            WHERE  REFID          = :refid
              AND  CAF_ENTRY_DONE IN ('N', 'QM', 'QB')
        """

        claimed: List[dict] = []
        with get_oracle_conn() as conn:
            cur = conn.cursor()

            # Fetch candidates
            cur.execute(select_sql, batch_size=batch_size)
            cols = [c[0].lower() for c in cur.description]
            candidates = [dict(zip(cols, row)) for row in cur.fetchall()]

            if not candidates:
                return []

            # Attempt to claim each one
            for row in candidates:
                cur.execute(claim_sql, refid=row["refid"])
                if cur.rowcount == 1:
                    claimed.append(row)
                else:
                    logger.warning(
                        "[FANCYSALE] fetch_and_claim: REFID=%s already claimed by another "
                        "process — skipping", row["refid"]
                    )

            conn.commit()

        logger.info("[FANCYSALE] fetch_and_claim: %d/%d rows claimed",
                    len(claimed), len(candidates))
        return claimed

    def map_to_pyro_params(self, record: dict) -> dict:
        """
        Map Oracle row → wallet_adjustment() kwargs.

        MPIN comes in as plain_mpin (already decrypted by Oracle F_DECRYPT).
        Validates MPIN length against MPIN_LENGTH column.
        Raises ValueError on any validation failure — processor catches this.
        """
        mpin = record.get("plain_mpin") or ""
        mpin = str(mpin).strip()
        expected_len = int(record.get("mpin_length") or 0)

        if not mpin:
            raise ValueError(
                f"REFID={record['refid']}: plain_mpin is empty after Oracle F_DECRYPT"
            )
        if expected_len and len(mpin) != expected_len:
            raise ValueError(
                f"REFID={record['refid']}: MPIN length mismatch — "
                f"got {len(mpin)}, expected {expected_len}"
            )

        # CTOPUPNO and FANCY_NO are NUMBER in Oracle — cast to int then str to
        # strip any decimal point or leading zeros Oracle might have added.
        source_msisdn = str(int(record["ctopupno"]))
        dest_msisdn   = str(int(record["fancy_no"]))
        amount        = float(record["amount"])
        client_id     = str(record["ss_request_id"])
        remarks       = str(record.get("module_type") or "FANCYSALE")

        return dict(
            client_id=client_id,
            source_msisdn=source_msisdn,
            dest_msisdn=dest_msisdn,
            amount=amount,
            mpin=mpin,
            remarks=remarks,
        )

    def get_record_ref(self, record: dict) -> str:
        return str(record.get("refid", "UNKNOWN"))

    def mark_success(self, record: dict, pyro_txn_id: str, remarks: str) -> None:
        """Write Y + TRANSACTION_ID + PYRO_REMARKS + PROCESSED_SM to Oracle."""
        sql = """
            UPDATE CAF_ADMIN.VANITYSALE_FRANCH_DATA
            SET    CAF_ENTRY_DONE = 'Y',
                   TRANSACTION_ID = :pyro_txn_id,
                   PYRO_REMARKS   = :remarks,
                   PROCESSED_SM   = 'Y'
            WHERE  REFID          = :refid
              AND  CAF_ENTRY_DONE = 'P'
        """
        try:
            with get_oracle_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, {
                    "pyro_txn_id": pyro_txn_id[:100] if pyro_txn_id else None,
                    "remarks":     remarks[:2000],
                    "refid":       record["refid"],
                })
                if cur.rowcount == 0:
                    logger.warning(
                        "[FANCYSALE] mark_success: REFID=%s rowcount=0 "
                        "(already moved out of P?)", record["refid"]
                    )
                conn.commit()
        except Exception as exc:
            logger.error(
                "[FANCYSALE] mark_success DB failure (non-fatal) REFID=%s: %s",
                record["refid"], exc
            )


    def mark_failed(self, record: dict, remarks: str) -> None:
        """Write R + PYRO_REMARKS to Oracle."""
        sql = """
            UPDATE CAF_ADMIN.VANITYSALE_FRANCH_DATA
            SET    CAF_ENTRY_DONE = 'R',
                   PYRO_REMARKS   = :remarks
            WHERE  REFID          = :refid
              AND  CAF_ENTRY_DONE = 'P'
        """
        try:
            with get_oracle_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, {
                    "remarks": remarks[:2000],
                    "refid":   record["refid"],
                })
                if cur.rowcount == 0:
                    logger.warning(
                        "[FANCYSALE] mark_failed: REFID=%s rowcount=0 "
                        "(already moved out of P?)", record["refid"]
                    )
                conn.commit()
        except Exception as exc:
            logger.error(
                "[FANCYSALE] mark_failed DB failure (non-fatal) REFID=%s: %s",
                record["refid"], exc
            )


    def reset_stuck_processing(self, stuck_minutes: int) -> int:
        """
        Reset P records that have been stuck longer than stuck_minutes back to N.
        Records pre-dating this service (CAF_ENTRY_DATE IS NULL) are intentionally
        excluded — run the one-time manual SQL from the deployment guide first.
        """
        if not self.enabled:
            return 0

        sql = """
            UPDATE CAF_ADMIN.VANITYSALE_FRANCH_DATA
            SET    CAF_ENTRY_DONE = 'N',
                   PYRO_REMARKS   = 'Reset: stuck in processing state'
            WHERE  CAF_ENTRY_DONE  = 'P'
              AND  CAF_ENTRY_DATE IS NOT NULL
              AND  CAF_ENTRY_DATE  < SYSDATE - (:stuck_minutes / 1440)
        """
        try:
            with get_oracle_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, stuck_minutes=stuck_minutes)
                count = cur.rowcount
                conn.commit()
            if count:
                logger.warning(
                    "[FANCYSALE] reset_stuck_processing: reset %d stuck-P row(s) "
                    "older than %d min back to N", count, stuck_minutes
                )
            return count
        except Exception as exc:
            logger.error("[FANCYSALE] reset_stuck_processing error: %s", exc)
            return 0
