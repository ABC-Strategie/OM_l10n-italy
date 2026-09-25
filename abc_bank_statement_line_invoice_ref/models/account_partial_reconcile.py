# -*- coding: utf-8 -*-

from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _abc_affected_statement_lines(self):
        """Le transazioni bancarie il cui riferimento dipende da queste riconciliazioni.

        Sono le transazioni di uno dei due lati e, quando un lato e' un
        pagamento, le transazioni abbinate a quel pagamento: riconciliare
        pagamento e fattura cambia le fatture pagate dalla transazione.
        """
        moves = (self.debit_move_id + self.credit_move_id).move_id
        st_lines = moves.statement_line_id

        payment_lines = moves.filtered("origin_payment_id").line_ids
        payment_counterparts = (
            payment_lines.matched_debit_ids.debit_move_id + payment_lines.matched_credit_ids.credit_move_id
        )
        return st_lines | payment_counterparts.move_id.statement_line_id

    @api.model_create_multi
    def create(self, vals_list):
        """EXTENDS account: aggiorna il riferimento delle transazioni riconciliate.

        Copre il widget di corrispondenza bancaria, la riconciliazione automatica
        e l'abbinamento fatto dal lato della fattura.
        """
        partials = super().create(vals_list)
        if not self.env.context.get("abc_skip_invoice_ref"):
            partials.sudo()._abc_affected_statement_lines()._abc_update_ref_from_invoices()
        return partials

    def unlink(self):
        """EXTENDS account: ricalcola il riferimento quando si annulla una riconciliazione.

        Le transazioni coinvolte vanno lette prima della cancellazione; il
        ricalcolo, dopo, vede solo le fatture rimaste e svuota il riferimento
        se non ne resta nessuna.
        """
        st_lines = self.env["account.bank.statement.line"]
        if self and not self.env.context.get("abc_skip_invoice_ref"):
            st_lines = self.sudo()._abc_affected_statement_lines()
        res = super().unlink()
        st_lines._abc_update_ref_from_invoices(clear_if_empty=True)
        return res
