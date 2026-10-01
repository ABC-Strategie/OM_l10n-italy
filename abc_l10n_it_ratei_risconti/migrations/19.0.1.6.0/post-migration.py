# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Ricalcola giorni e quota di competenza del solo esercizio a D sulle righe esistenti."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['abc.rr.run.line'].with_context(active_test=False).search([])
    lines._compute_days_competence()
    lines.flush_recordset(['days_competence', 'competence_amount'])
