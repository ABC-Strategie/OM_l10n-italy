#  Copyright 2024 Sergio Zanchetta
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    # Aggiorna i record bloccati ricaricando l'XML da data.xml (bypassando noupdate)
    cr.execute("UPDATE ir_model_data SET noupdate=False WHERE module='l10n_it_account_stamp' AND name='l10n_it_account_stamp_2_euro'")
    cr.execute("UPDATE ir_model_data SET noupdate=False WHERE module='base' AND name='main_company'")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    openupgrade.load_data(env, 'l10n_it_account_stamp', 'data/data.xml')
