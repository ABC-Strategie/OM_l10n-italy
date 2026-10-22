# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.l10n_it_account_vat_period_end_settlement.tests.common import (
    TestVATStatementCommon,
)


@tagged("post_install", "-at_install")
class TestVatStatementZeroRate(TestVATStatementCommon):
    """Aliquote 0% nelle righe della liquidazione IVA."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Imposte 0% senza conti sulle righe di ripartizione, come quelle
        # del piano dei conti italiano che il modulo base non considera.
        cls.tax_zero_purchase = cls._create_zero_tax("0% test acquisti", "purchase")
        cls.tax_zero_sale = cls._create_zero_tax("0% test vendite", "sale")
        cls.tax_zero_unused = cls._create_zero_tax("0% test non usata", "purchase")

    @classmethod
    def _create_zero_tax(cls, name, type_tax_use):
        return cls.env["account.tax"].create(
            {
                "name": name,
                "amount": 0.0,
                "amount_type": "percent",
                "type_tax_use": type_tax_use,
                "company_id": cls.company.id,
            }
        )

    def setUp(self):
        super().setUp()
        self.env.user.company_id = self.company.id

    def _create_invoice(self, move_type, tax, amount=100.0):
        return self.init_invoice(
            move_type,
            invoice_date=self.recent_date,
            amounts=[amount],
            taxes=tax,
            post=True,
        )

    def _new_statement(self, accounts=None):
        if accounts is None:
            accounts = self.env["account.account"].browse()
        statement = self._get_statement(
            self.current_period,
            self.recent_date,
            accounts,
        )
        statement.compute_amounts()
        return statement

    def test_zero_rate_purchase_with_base(self):
        """0% di acquisto movimentata: riga a credito a importo zero."""
        self._create_invoice("in_invoice", self.tax_zero_purchase)

        statement = self._new_statement()

        line = statement.credit_vat_account_line_ids.filtered(
            lambda line: line.tax_id == self.tax_zero_purchase
        )
        self.assertEqual(len(line), 1)
        self.assertEqual(line.amount, 0.0)
        self.assertFalse(line.account_id)
        self.assertNotIn(
            self.tax_zero_purchase,
            statement.debit_vat_account_line_ids.tax_id,
        )

    def test_zero_rate_sale_with_base(self):
        """0% di vendita movimentata: riga a debito a importo zero."""
        self._create_invoice("out_invoice", self.tax_zero_sale)

        statement = self._new_statement()

        line = statement.debit_vat_account_line_ids.filtered(
            lambda line: line.tax_id == self.tax_zero_sale
        )
        self.assertEqual(len(line), 1)
        self.assertEqual(line.amount, 0.0)
        self.assertNotIn(
            self.tax_zero_sale,
            statement.credit_vat_account_line_ids.tax_id,
        )

    def test_not_moved_taxes_excluded(self):
        """Le imposte senza movimenti nel periodo non generano righe."""
        self._create_invoice("in_invoice", self.tax_zero_purchase)

        statement = self._new_statement()

        statement_taxes = (
            statement.credit_vat_account_line_ids.tax_id
            | statement.debit_vat_account_line_ids.tax_id
        )
        self.assertNotIn(self.tax_zero_unused, statement_taxes)
        self.assertNotIn(self.tax_zero_sale, statement_taxes)
        self.assertNotIn(
            self.company_data_2["default_tax_purchase"], statement_taxes
        )

    def test_account_filter_excludes_zero_rate_without_account(self):
        """Con il filtro conti le 0% senza conto non vengono aggiunte."""
        tax = self.company_data_2["default_tax_purchase"]
        self._create_invoice("in_invoice", tax)
        self._create_invoice("in_invoice", self.tax_zero_purchase)

        statement = self._new_statement(tax._get_credit_accounts())

        statement_taxes = statement.credit_vat_account_line_ids.tax_id
        self.assertIn(tax, statement_taxes)
        self.assertNotIn(self.tax_zero_purchase, statement_taxes)

    def test_report_shows_zero_rate(self):
        """La stampa riporta l'aliquota 0% movimentata."""
        self._create_invoice("in_invoice", self.tax_zero_purchase)
        statement = self._new_statement()

        report_content, _report_type = self.env[
            "ir.actions.report"
        ]._render_qweb_html(
            "l10n_it_account_vat_period_end_settlement.report_vat_statement",
            statement.ids,
        )

        self.assertIn(self.tax_zero_purchase.name, report_content.decode())

    def test_create_move_with_zero_rate(self):
        """La scrittura di liquidazione ignora le righe 0% senza conto."""
        tax = self.company_data_2["default_tax_sale"]
        self._create_invoice("out_invoice", tax, amount=1000.0)
        self._create_invoice("in_invoice", self.tax_zero_purchase)
        statement = self._new_statement()
        self.assertIn(
            self.tax_zero_purchase,
            statement.credit_vat_account_line_ids.tax_id,
        )

        statement.create_move()

        self.assertEqual(statement.move_id.state, "posted")
        self.assertFalse(
            statement.move_id.line_ids.filtered(lambda line: not line.account_id)
        )
