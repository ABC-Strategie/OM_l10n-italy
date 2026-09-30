# -*- coding: utf-8 -*-

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestAbcPartnerAccountDefault(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Conti dedicati al contatto, diversi da quelli che il prodotto porterebbe da solo.
        cls.conto_ricavo_contatto = cls.copy_account(cls.company_data["default_account_revenue"])
        cls.conto_costo_contatto = cls.copy_account(cls.company_data["default_account_expense"])

    def _crea_fattura(self, move_type, partner):
        return self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": partner.id,
            "invoice_date": "2026-01-15",
            "invoice_line_ids": [
                Command.create({
                    "product_id": self.product_a.id,
                    "quantity": 1,
                    "price_unit": 100.0,
                }),
            ],
        })

    # -------------------------------------------------------------------------

    def test_senza_conti_sul_contatto_resta_lo_standard(self):
        """Contatto senza conti impostati: la riga usa il conto del prodotto."""
        fattura = self._crea_fattura("out_invoice", self.partner_a)
        self.assertEqual(
            fattura.invoice_line_ids.account_id,
            self.company_data["default_account_revenue"],
        )

    def test_conto_ricavo_del_contatto_vince_sul_prodotto(self):
        """Fattura cliente: il conto di ricavo del contatto sovrascrive quello del prodotto."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fattura = self._crea_fattura("out_invoice", self.partner_a)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_ricavo_contatto)

    def test_conto_ricavo_vale_anche_sulle_note_di_credito(self):
        """Il conto di ricavo si applica anche alle note di credito cliente."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        nota = self._crea_fattura("out_refund", self.partner_a)
        self.assertEqual(nota.invoice_line_ids.account_id, self.conto_ricavo_contatto)

    def test_conto_costo_del_contatto_sulle_fatture_fornitore(self):
        """Fattura fornitore: il conto di costo del contatto sovrascrive quello del prodotto."""
        self.partner_a.abc_property_account_expense_id = self.conto_costo_contatto
        fattura = self._crea_fattura("in_invoice", self.partner_a)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_costo_contatto)

    def test_i_due_conti_non_si_incrociano(self):
        """Il conto di ricavo non deve finire su una fattura fornitore, e viceversa."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fornitore = self._crea_fattura("in_invoice", self.partner_a)
        self.assertEqual(
            fornitore.invoice_line_ids.account_id,
            self.company_data["default_account_expense"],
        )

        self.partner_a.abc_property_account_income_id = False
        self.partner_a.abc_property_account_expense_id = self.conto_costo_contatto
        cliente = self._crea_fattura("out_invoice", self.partner_a)
        self.assertEqual(
            cliente.invoice_line_ids.account_id,
            self.company_data["default_account_revenue"],
        )

    def test_cambio_contatto_aggiorna_il_conto(self):
        """Cambiando cliente sulla fattura il conto della riga segue il nuovo contatto.

        E' il caso coperto dall'aggiunta di partner_id al depends: il core dipende dal
        solo move_id e senza quella aggiunta la riga resterebbe sul conto precedente.
        """
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fattura = self._crea_fattura("out_invoice", self.partner_b)
        self.assertEqual(
            fattura.invoice_line_ids.account_id,
            self.company_data["default_account_revenue"],
        )

        fattura.partner_id = self.partner_a
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_ricavo_contatto)

    def test_contatto_figlio_usa_i_conti_dell_azienda_madre(self):
        """Le impostazioni contabili si leggono dal commercial_partner_id."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        figlio = self.env["res.partner"].create({
            "name": "Contatto figlio",
            "parent_id": self.partner_a.id,
        })
        fattura = self._crea_fattura("out_invoice", figlio)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_ricavo_contatto)

    def test_righe_senza_prodotto(self):
        """Anche le righe descrittive senza prodotto prendono il conto del contatto."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fattura = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-01-15",
            "invoice_line_ids": [
                Command.create({"name": "Riga descrittiva", "quantity": 1, "price_unit": 100.0}),
            ],
        })
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_ricavo_contatto)
