# -*- coding: utf-8 -*-

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import Form, tagged


@tagged("post_install", "-at_install")
class TestAbcPartnerAccountDefault(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Conti dedicati al contatto, diversi da quelli che il prodotto porterebbe da solo.
        cls.conto_ricavo_contatto = cls.copy_account(cls.company_data["default_account_revenue"])
        cls.conto_costo_contatto = cls.copy_account(cls.company_data["default_account_expense"])

    def _crea_fattura(self, move_type, partner, **valori):
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
            **valori,
        })

    def _crea_fattura_da_form(self, move_type, partner, descrizione="Riga descrittiva"):
        """Fattura con una riga descrittiva aggiunta come dall'interfaccia.

        Form passa alle righe il contesto della vista (journal_id, default_partner_id), quindi
        il core propone il conto predefinito del registro come default della riga nuova.
        """
        move_form = Form(self.env["account.move"].with_context(default_move_type=move_type))
        move_form.partner_id = partner
        move_form.invoice_date = fields.Date.from_string("2026-01-15")
        with move_form.invoice_line_ids.new() as line_form:
            line_form.name = descrizione
            line_form.price_unit = 100.0
        return move_form.save()

    def _registra_fattura_fornitore_storica(self, descrizione, conto):
        """Fattura fornitore registrata: e' lo storico da cui account_accountant prevede il conto."""
        fattura = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-01-10",
            "invoice_line_ids": [
                Command.create({
                    "name": descrizione,
                    "account_id": conto.id,
                    "quantity": 1,
                    "price_unit": 100.0,
                }),
            ],
        })
        fattura.action_post()
        return fattura

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

    def test_riga_nuova_da_form_fattura_cliente(self):
        """Riga aggiunta dall'interfaccia: il conto del contatto prevale sul default del registro."""
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fattura = self._crea_fattura_da_form("out_invoice", self.partner_a)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_ricavo_contatto)

    def test_riga_nuova_da_form_fattura_fornitore(self):
        """Riga aggiunta dall'interfaccia su fattura fornitore: vale il conto di costo del contatto."""
        self.partner_a.abc_property_account_expense_id = self.conto_costo_contatto
        fattura = self._crea_fattura_da_form("in_invoice", self.partner_a)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_costo_contatto)

    def test_riga_nuova_da_form_senza_conti_resta_lo_standard(self):
        """Contatto senza conti: la riga nuova tiene il conto predefinito del registro."""
        fattura = self._crea_fattura_da_form("out_invoice", self.partner_a)
        self.assertEqual(
            fattura.invoice_line_ids.account_id,
            fattura.journal_id.default_account_id,
        )

    def test_posizione_fiscale_mappa_il_conto_del_contatto(self):
        """Al conto del contatto si applica la mappatura della posizione fiscale della fattura."""
        conto_mappato = self.copy_account(self.company_data["default_account_revenue"])
        posizione_fiscale = self.env["account.fiscal.position"].create({
            "name": "Posizione fiscale test",
            "account_ids": [Command.create({
                "account_src_id": self.conto_ricavo_contatto.id,
                "account_dest_id": conto_mappato.id,
            })],
        })
        self.partner_a.abc_property_account_income_id = self.conto_ricavo_contatto
        fattura = self._crea_fattura(
            "out_invoice", self.partner_a, fiscal_position_id=posizione_fiscale.id,
        )
        self.assertEqual(fattura.invoice_line_ids.account_id, conto_mappato)

    def test_previsione_da_storico_non_scavalca_conto_contatto(self):
        """Fattura fornitore: scrivendo la descrizione, la previsione da storico non vince sul contatto."""
        descrizione = "Canone mensile consulenza direzionale"
        conto_storico = self.copy_account(self.company_data["default_account_expense"])
        self._registra_fattura_fornitore_storica(descrizione, conto_storico)

        # Senza conto sul contatto la previsione e' attiva e propone il conto dello storico.
        fattura = self._crea_fattura_da_form("in_invoice", self.partner_a, descrizione)
        self.assertEqual(fattura.invoice_line_ids.account_id, conto_storico)

        self.partner_a.abc_property_account_expense_id = self.conto_costo_contatto
        fattura = self._crea_fattura_da_form("in_invoice", self.partner_a, descrizione)
        self.assertEqual(fattura.invoice_line_ids.account_id, self.conto_costo_contatto)

    def test_previsione_per_import_restituisce_conto_contatto(self):
        """Il metodo usato dagli import SdI e UBL restituisce l'id del conto del contatto."""
        descrizione = "Canone mensile consulenza direzionale"
        conto_storico = self.copy_account(self.company_data["default_account_expense"])
        self._registra_fattura_fornitore_storica(descrizione, conto_storico)
        self.partner_a.abc_property_account_expense_id = self.conto_costo_contatto
        bozza = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
        })
        previsto = self.env["account.move.line"]._predict_specific_account(
            bozza, descrizione, self.partner_a,
        )
        self.assertEqual(previsto, self.conto_costo_contatto.id)
