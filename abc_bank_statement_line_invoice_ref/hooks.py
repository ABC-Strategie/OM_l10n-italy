# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def post_init_hook(env):
    """Compila una tantum il riferimento sulle transazioni gia' riconciliate.

    Considera tutte le transazioni con almeno una riga riconciliata, anche solo
    in parte. Quelle senza fatture pagate non vengono toccate.

    tracking_disable: evita un messaggio nel chatter per ogni transazione.
    Ogni transazione passa in un savepoint: un errore viene registrato nel log
    e non blocca l'installazione.
    """
    StLine = env["account.bank.statement.line"].with_context(tracking_disable=True)
    st_lines = StLine.search([
        ("state", "!=", "cancel"),
        "|",
        ("line_ids.matched_debit_ids", "!=", False),
        ("line_ids.matched_credit_ids", "!=", False),
    ])
    _logger.info("Riferimento da fatture: %s transazioni riconciliate da elaborare", len(st_lines))

    updated = failed = 0
    for start in range(0, len(st_lines), BATCH_SIZE):
        batch = st_lines[start:start + BATCH_SIZE]
        for st_line in batch:
            try:
                with env.cr.savepoint():
                    updated += len(st_line._abc_update_ref_from_invoices())
            except Exception:
                failed += 1
                # Dopo il rollback del savepoint la cache non e' piu' affidabile.
                env.invalidate_all(flush=False)
                _logger.warning(
                    "Riferimento da fatture: impossibile aggiornare la transazione %s",
                    st_line.id, exc_info=True,
                )
        # Libera la cache fra un blocco e l'altro.
        env.invalidate_all()
        _logger.info(
            "Riferimento da fatture: elaborate %s/%s transazioni",
            min(start + BATCH_SIZE, len(st_lines)), len(st_lines),
        )

    _logger.info(
        "Riferimento da fatture: %s transazioni aggiornate, %s in errore", updated, failed,
    )
