# -*- coding: utf-8 -*-

from odoo import Command
from odoo.addons.account_accountant.tests.common import TestBankRecWidgetCommon
from odoo.tests import tagged

from odoo.addons.abc_bank_statement_line_invoice_ref.hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestAbcStatementLineInvoiceRef(TestBankRecWidgetCommon):

    def _invoice(self, amount, invoice_date="2026-03-12", move_type="out_invoice", ref=None, post=True):
        """Crea (e di norma conferma) una fattura, restituisce la fattura."""
        invoice = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": self.partner_a.id,
            "invoice_date": invoice_date,
            "ref": ref,
            "invoice_line_ids": [
                Command.create({"name": "Riga di test", "quantity": 1, "price_unit": amount, "tax_ids": []}),
            ],
        })
        if post:
            invoice.action_post()
        return invoice

    @staticmethod
    def _term_lines(invoice):
        return invoice.line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
        )

    def _st_line(self, amount, **kwargs):
        return self._create_st_line(amount=amount, date="2026-03-20", update_create_date=False, **kwargs)

    # -------------------------------------------------------------------------
    # Riconciliazione
    # -------------------------------------------------------------------------

    def test_customer_invoice_uses_number(self):
        """Fattura cliente: vale il numero, non il ref (che e' il numero d'ordine)."""
        invoice = self._invoice(100.0, ref="S03392")
        st_line = self._st_line(100.0)

        st_line.set_line_bank_statement_line(self._term_lines(invoice).ids)

        self.assertEqual(st_line.ref, f"{invoice.name} del 12/03/2026")

    def test_vendor_bill_uses_ref(self):
        """Fattura fornitore: vale il riferimento del fornitore."""
        bill = self._invoice(100.0, move_type="in_invoice", ref="FORN-2026-15")
        st_line = self._st_line(-100.0)

        st_line.set_line_bank_statement_line(self._term_lines(bill).ids)

        self.assertEqual(st_line.ref, "FORN-2026-15 del 12/03/2026")

    def test_vendor_bill_without_ref_uses_number(self):
        """Fattura fornitore senza ref: vale il numero della fattura."""
        bill = self._invoice(100.0, move_type="in_invoice")
        st_line = self._st_line(-100.0)

        st_line.set_line_bank_statement_line(self._term_lines(bill).ids)

        self.assertEqual(st_line.ref, f"{bill.name} del 12/03/2026")

    def test_draft_vendor_bill(self):
        """Fattura fornitore in bozza (senza numero): vale il ref del fornitore."""
        bill = self._invoice(100.0, move_type="in_invoice", ref="IT00082707", post=False)
        self.assertFalse(bill.name and bill.name != "/")
        st_line = self._st_line(-100.0)

        st_line.set_line_bank_statement_line(self._term_lines(bill).ids)

        self.assertEqual(st_line.ref, "IT00082707 del 12/03/2026")

    def test_multiple_invoices_sorted_by_date(self):
        """Piu' fatture: tutte, ordinate per data fattura, separate da virgola."""
        later = self._invoice(50.0, invoice_date="2026-03-15")
        earlier = self._invoice(100.0, invoice_date="2026-03-12")
        st_line = self._st_line(150.0)

        st_line.set_line_bank_statement_line((self._term_lines(later) + self._term_lines(earlier)).ids)

        self.assertEqual(st_line.ref, f"{earlier.name} del 12/03/2026, {later.name} del 15/03/2026")

    def test_existing_ref_is_overwritten(self):
        """Il riferimento importato con l'estratto conto viene sovrascritto."""
        invoice = self._invoice(100.0)
        st_line = self._st_line(100.0, ref="CRO 123456")

        st_line.set_line_bank_statement_line(self._term_lines(invoice).ids)

        self.assertEqual(st_line.ref, f"{invoice.name} del 12/03/2026")

    def test_reconciliation_from_invoice_side(self):
        """Abbinamento fatto dalla fattura (credito in sospeso): stesso risultato."""
        invoice = self._invoice(100.0)
        st_line = self._st_line(100.0, partner_id=self.partner_a.id)
        liquidity_line, _suspense, _other = st_line._seek_for_lines()

        invoice.js_assign_outstanding_line(liquidity_line.id)

        self.assertEqual(st_line.ref, f"{invoice.name} del 12/03/2026")

    # -------------------------------------------------------------------------
    # Annullamento
    # -------------------------------------------------------------------------

    def test_unreconcile_clears_ref(self):
        """Annullando l'unica riconciliazione il riferimento viene svuotato."""
        invoice = self._invoice(100.0)
        st_line = self._st_line(100.0)
        st_line.set_line_bank_statement_line(self._term_lines(invoice).ids)
        self.assertTrue(st_line.ref)

        st_line.delete_reconciled_line(st_line.line_ids[-1].id)

        self.assertFalse(st_line.ref)

    def test_unreconcile_one_of_two_keeps_the_other(self):
        """Togliendo una fattura resta il riferimento dell'altra."""
        first = self._invoice(100.0, invoice_date="2026-03-12")
        second = self._invoice(50.0, invoice_date="2026-03-15")
        st_line = self._st_line(150.0)
        st_line.set_line_bank_statement_line((self._term_lines(first) + self._term_lines(second)).ids)

        second_line = st_line.line_ids.filtered(
            lambda line: line.reconciled_lines_ids.move_id == second
        )
        st_line.delete_reconciled_line(second_line.id)

        self.assertEqual(st_line.ref, f"{first.name} del 12/03/2026")

    # -------------------------------------------------------------------------
    # Pagamento intermedio
    # -------------------------------------------------------------------------

    def test_invoice_paid_through_payment(self):
        """Banca -> pagamento -> fattura: vale la fattura pagata dal pagamento."""
        invoice = self._invoice(100.0)
        payment = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_method_line_id": self.inbound_payment_method_line.id,
            "payment_date": "2026-03-18",
        })._create_payments()
        self.assertTrue(payment.move_id, "Il test richiede un pagamento con conto transitorio")
        st_line = self._st_line(100.0)

        st_line.set_line_bank_statement_line(
            payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id).ids
        )

        self.assertEqual(st_line.ref, f"{invoice.name} del 12/03/2026")

    # -------------------------------------------------------------------------
    # Esecuzione una tantum e azione server
    # -------------------------------------------------------------------------

    def test_post_init_hook_fills_existing_lines(self):
        """L'hook compila le transazioni gia' riconciliate e non tocca le altre."""
        invoice = self._invoice(100.0)
        reconciled = self._st_line(100.0)
        reconciled.set_line_bank_statement_line(self._term_lines(invoice).ids)
        not_reconciled = self._st_line(70.0, ref="CRO 999")

        # Simula una riconciliazione fatta prima dell'installazione del modulo.
        self.env.flush_all()
        self.env.cr.execute("UPDATE account_move SET ref = NULL WHERE id = %s", [reconciled.move_id.id])
        self.env.invalidate_all()
        self.assertFalse(reconciled.ref)

        post_init_hook(self.env)

        self.assertEqual(reconciled.ref, f"{invoice.name} del 12/03/2026")
        self.assertEqual(not_reconciled.ref, "CRO 999")

    def test_server_action(self):
        """L'azione server ricompila il riferimento sulle righe selezionate."""
        invoice = self._invoice(100.0)
        st_line = self._st_line(100.0)
        st_line.set_line_bank_statement_line(self._term_lines(invoice).ids)
        st_line.ref = "modificato a mano"

        action = self.env.ref("abc_bank_statement_line_invoice_ref.action_abc_update_ref_from_invoices")
        action.with_context(active_model=st_line._name, active_ids=st_line.ids).run()

        self.assertEqual(st_line.ref, f"{invoice.name} del 12/03/2026")
