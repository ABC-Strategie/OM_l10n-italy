# -*- coding: utf-8 -*-

from odoo import models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # -------------------------------------------------------------------------
    # Helper
    # -------------------------------------------------------------------------

    def _abc_get_paid_invoices(self):
        """Le fatture pagate da questa transazione.

        Sono le fatture riconciliate direttamente con le righe della transazione
        e quelle riconciliate con un pagamento a sua volta abbinato alla
        transazione (banca -> pagamento -> fattura). Sono comprese note di
        credito e ricevute.
        """
        self.ensure_one()
        liquidity_lines, _suspense_lines, _other_lines = self._seek_for_lines()
        lines = self.move_id.line_ids - liquidity_lines
        counterpart_moves = (
            lines.matched_debit_ids.debit_move_id + lines.matched_credit_ids.credit_move_id
        ).move_id - self.move_id

        invoices = counterpart_moves.filtered(lambda move: move.is_invoice(include_receipts=True))
        payment_moves = counterpart_moves.filtered("origin_payment_id")
        return invoices | payment_moves._get_reconciled_invoices()

    def _abc_format_invoice_ref(self, invoices):
        """Il testo del riferimento: "FT/001 del 12/03/2026, FT/002 del 15/03/2026".

        Documenti cliente: il numero della fattura (il ref contiene il numero
        dell'ordine di vendita). Documenti fornitore: il ref, cioe' il numero sul
        documento del fornitore. In entrambi i casi, se manca, vale l'altro.
        La data e' sempre in formato gg/mm/aaaa, indipendente dalla lingua
        dell'utente: l'aggiornamento puo' partire anche da cron o installazione.
        """
        def invoice_date(invoice):
            return invoice.invoice_date or invoice.date

        def invoice_ref(invoice):
            # Le fatture in bozza, abbinabili dal widget, non hanno ancora un numero.
            number = invoice.name if invoice.name and invoice.name != "/" else ""
            if invoice.is_sale_document(include_receipts=True):
                return number or invoice.ref
            return invoice.ref or number

        invoices = invoices.filtered(invoice_ref).sorted(lambda inv: (invoice_date(inv), inv.name or ""))
        return ", ".join(
            "%s del %s" % (invoice_ref(invoice), invoice_date(invoice).strftime("%d/%m/%Y"))
            for invoice in invoices
        )

    def _abc_update_ref_from_invoices(self, clear_if_empty=False):
        """Compila il riferimento delle transazioni con le fatture pagate.

        Il valore sovrascrive sempre quello presente. Senza fatture la
        transazione non viene toccata, cosi' i riferimenti importati
        dall'estratto conto restano; con clear_if_empty (annullamento di una
        riconciliazione) il riferimento viene invece svuotato.

        :return: le transazioni il cui riferimento e' stato modificato.
        """
        # sudo(): le fatture pagate devono essere trovate anche quando le regole
        # di record ne nascondono qualcuna all'utente che riconcilia.
        updated = self.browse()
        for st_line in self.sudo().exists():
            invoices = st_line._abc_get_paid_invoices()
            if invoices:
                new_ref = st_line._abc_format_invoice_ref(invoices)
            elif clear_if_empty:
                new_ref = False
            else:
                continue
            if (st_line.ref or False) == new_ref:
                continue
            # Si scrive direttamente sul movimento (ref e' ereditato via _inherits).
            # skip_is_manually_modified: il movimento non va marcato come
            # modificato a mano per un aggiornamento automatico.
            st_line.move_id.with_context(
                skip_readonly_check=True,
                skip_is_manually_modified=True,
            ).write({"ref": new_ref})
            updated |= st_line
        return self.browse(updated.ids)

    # -------------------------------------------------------------------------
    # Azioni
    # -------------------------------------------------------------------------

    def action_abc_update_ref_from_invoices(self):
        """Azione server "Aggiorna riferimento da fatture" sulle righe selezionate."""
        self._abc_update_ref_from_invoices()
