#  Copyright 2024 Sergio Zanchetta
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(
        env, "l10n_it_account_stamp", "migrations/18.0.1.0.0/noupdate_changes.xml"
    )
    # In Odoo 18+, ir.model.fields.translate is a varchar, but openupgradelib
    # expects it to be a boolean, causing a DatatypeMismatch error in PostgreSQL.
    # We remove this call because it is broken in openupgradelib and redundant
    # since load_data handles translation updates.
    pass
