#  Copyright 2024 Sergio Zanchetta
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.upgrade import util


def migrate(cr, version):
    # Aggiorna i record bloccati ricaricando l'XML da data.xml (bypassando noupdate)
    # in conformità alle best practices di migrazione di Odoo 19
    util.update_record_from_xml(cr, "l10n_it_account_stamp.l10n_it_account_stamp_2_euro")
    util.update_record_from_xml(cr, "base.main_company")
