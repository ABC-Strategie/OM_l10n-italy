# Copyright 2026 ABC-Strategie S.r.l.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import json
import logging

_logger = logging.getLogger(__name__)

OLD_FIELD = "date_vat_settlement"
NEW_FIELD = "l10n_it_vat_settlement_date"


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    _logger.info(
        "Pre-migration: rename %s to %s and fix legacy view references",
        OLD_FIELD,
        NEW_FIELD,
    )

    # La versione 16 del modulo usava il campo date_vat_settlement:
    # rinominiamo la colonna per preservare le date di competenza IVA
    # storiche ed evitare il ricalcolo di massa del campo computed.
    for table in ("account_move", "account_move_line"):
        if _column_exists(cr, table, OLD_FIELD) and not _column_exists(
            cr, table, NEW_FIELD
        ):
            cr.execute(
                f"ALTER TABLE {table} RENAME COLUMN {OLD_FIELD} TO {NEW_FIELD}"
            )
            _logger.info("Renamed column %s.%s to %s", table, OLD_FIELD, NEW_FIELD)

    # Le viste della vecchia versione (es. view_tax_form_vat) e le eventuali
    # personalizzazioni Studio referenziano ancora il vecchio nome campo e
    # fanno fallire la validazione della form di account.move
    # ("Field `date_vat_settlement` does not exist"): aggiorniamo i
    # riferimenti dentro arch_db.
    cr.execute(
        "SELECT id, arch_db FROM ir_ui_view WHERE arch_db::text LIKE %s",
        (f"%{OLD_FIELD}%",),
    )
    for view_id, arch_db in cr.fetchall():
        if not arch_db:
            continue
        new_arch_db = {
            lang: arch.replace(OLD_FIELD, NEW_FIELD) if arch else arch
            for lang, arch in arch_db.items()
        }
        if new_arch_db != arch_db:
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                (json.dumps(new_arch_db), view_id),
            )
            _logger.info(
                "Updated %s reference in ir_ui_view ID %s", OLD_FIELD, view_id
            )

    _logger.info("Pre-migration: %s cleanup finished.", OLD_FIELD)
