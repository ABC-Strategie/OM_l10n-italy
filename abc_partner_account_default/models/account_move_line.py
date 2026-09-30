# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def default_get(self, fields):
        """EXTENDS account: se il contatto ha il proprio conto, la riga nuova non riceve un conto di default.

        Sulle righe aggiunte dalla fattura il core mette in account_id il conto predefinito del
        registro (dal journal_id che la vista passa nel contesto) o quello del suggerimento di
        quick encoding. Con un default il compute non parte e _compute_account_id non verrebbe
        mai chiamato: togliendo il default lasciamo decidere al compute, che applica il conto
        del contatto e la posizione fiscale della fattura.
        """
        defaults = super().default_get(fields)
        if (
            "account_id" in defaults
            and self.env.context.get("default_display_type") in (None, False, "product")
            and self._abc_context_partner_has_account()
        ):
            del defaults["account_id"]
        return defaults

    @api.model
    def _abc_context_partner_has_account(self):
        """Dice se il contatto della fattura, letto dal contesto, ha il conto per questo tipo di documento.

        In default_get la fattura non e' disponibile: la vista passa alle righe il commercial
        partner (default_partner_id), il tipo di documento (default_move_type) e il registro
        (journal_id). Senza tipo di documento si guarda il tipo del registro.
        """
        context = self.env.context
        partner = self.env["res.partner"].browse(context.get("default_partner_id")).exists()
        if not partner:
            return False
        journal = self.env["account.journal"].browse(context.get("journal_id")).exists()
        move_type = context.get("default_move_type")
        moves = self.env["account.move"]
        if move_type:
            sale = move_type in moves.get_sale_types(include_receipts=True)
            purchase = move_type in moves.get_purchase_types(include_receipts=True)
        else:
            sale = journal.type == "sale"
            purchase = journal.type == "purchase"
        if not (sale or purchase):
            return False
        return bool(partner._abc_get_invoice_account(journal.company_id or self.env.company, sale))

    @api.model
    def _abc_get_partner_account_for_move(self, move, partner=None):
        """Conto del contatto per le righe prodotto della fattura, gia' mappato dalla posizione fiscale.

        Si usa il contatto della fattura; partner serve solo se la fattura non lo ha ancora.
        Recordset vuoto se il documento non e' una fattura o se il contatto non ha il conto
        valorizzato: in quel caso resta il comportamento standard.
        """
        partner = move.commercial_partner_id or partner
        if not partner or not move.is_invoice(include_receipts=True):
            return self.env["account.account"]
        conto = partner._abc_get_invoice_account(
            move.company_id,
            sale=move.is_sale_document(include_receipts=True),
        )
        # Stessa mappatura che il core applica al conto del prodotto.
        if conto and move.fiscal_position_id:
            conto = move.fiscal_position_id.map_account(conto)
        return conto

    def _abc_get_partner_account(self):
        """Conto del contatto per questa riga, se e' una riga prodotto di fattura."""
        self.ensure_one()
        if self.display_type != "product":
            return self.env["account.account"]
        return self._abc_get_partner_account_for_move(self.move_id)

    @api.model
    def _predict_specific_account(self, move, name, partner):
        """EXTENDS account_accountant: la previsione da storico non scavalca il conto del contatto.

        Sulle righe senza prodotto delle fatture fornitore l'onchange sulla descrizione, l'import
        SdI (l10n_it_edi) e l'import UBL/CII assegnano direttamente il conto previsto dalle
        fatture precedenti del contatto, senza passare dal compute. Tutti passano da qui: se il
        contatto ha il proprio conto si restituisce quello, come id al pari del metodo originale.
        """
        conto = self._abc_get_partner_account_for_move(move, partner)
        if conto:
            return conto.id
        return super()._predict_specific_account(move, name, partner)

    @api.depends("move_id", "partner_id")
    def _compute_account_id(self):
        """EXTENDS account: il conto impostato sul contatto prevale su quello del prodotto.

        Il core valorizza account_id sulle righe prodotto leggendo i conti del prodotto o
        della sua categoria. Qui lasciamo fare al core e sovrascriviamo dopo, solo dove il
        contatto ha il proprio conto valorizzato, cosi' da non replicare la logica standard.

        Il core non dichiara dipendenze: senza move_id e partner_id cambiare cliente sulla
        fattura non farebbe ricalcolare il conto della riga.
        """
        super()._compute_account_id()
        for line in self:
            conto = line._abc_get_partner_account()
            if conto:
                line.account_id = conto
