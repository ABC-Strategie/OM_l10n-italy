# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    abc_invoice_date_check = fields.Boolean(
        string="Controllo data fattura",
        compute="_compute_abc_invoice_date_check",
        store=True,
        readonly=False,
        help="Avvisa sulle fatture in bozza di questo registro quando la data fattura e' "
             "anteriore a quella dell'ultima fattura confermata della stessa serie.\n"
             "Solo informativo: non blocca la conferma.",
    )

    @api.depends("type")
    def _compute_abc_invoice_date_check(self):
        """Attivo di default sui registri vendita.

        Il campo e' memorizzato: all'installazione Odoo lo calcola sui registri
        esistenti, poi resta modificabile a mano registro per registro.
        """
        for journal in self:
            journal.abc_invoice_date_check = journal.type == "sale"
