# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("move_id", "partner_id")
    def _compute_account_id(self):
        """EXTENDS account: il conto impostato sul contatto prevale su quello del prodotto.

        Il core valorizza account_id sulle righe prodotto leggendo i conti del prodotto o
        della sua categoria. Qui lasciamo fare al core e sovrascriviamo dopo, solo dove il
        contatto ha il proprio conto valorizzato, cosi' da non replicare la logica standard.

        Il depends aggiunge partner_id: quello del core e' il solo move_id e senza questa
        aggiunta cambiare cliente sulla fattura non farebbe ricalcolare il conto della riga.
        """
        super()._compute_account_id()
        for line in self:
            if line.display_type != "product" or not line.move_id.is_invoice(include_receipts=True):
                continue
            # I campi sono company_dependent e le impostazioni contabili dei contatti figli
            # sono gestite sull'azienda madre: si legge dal commercial_partner_id.
            company = line.company_id or line.move_id.company_id
            partner = line.move_id.commercial_partner_id
            if not partner:
                continue
            partner = partner.with_company(company)
            if line.move_id.is_sale_document(include_receipts=True):
                conto = partner.abc_property_account_income_id
            elif line.move_id.is_purchase_document(include_receipts=True):
                conto = partner.abc_property_account_expense_id
            else:
                continue
            if not conto:
                continue
            # Stessa mappatura che il core applica al conto del prodotto.
            fiscal_position = line.move_id.fiscal_position_id
            if fiscal_position:
                conto = fiscal_position.map_account(conto)
            line.account_id = conto
