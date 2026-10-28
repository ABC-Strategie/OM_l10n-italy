# -*- coding: utf-8 -*-

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from odoo.addons.abc_account_invoice_date_check.models.account_move import ABC_DATE_ALERT


@tagged("post_install", "-at_install")
class TestAbcInvoiceDateCheck(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data["default_journal_sale"]
        cls.purchase_journal = cls.company_data["default_journal_purchase"]
        # Intestatario estero: sul database del cliente bbs_partner_extensions
        # blocca la conferma delle fatture a clienti italiani senza codice fiscale.
        cls.partner_a.country_id = cls.env.ref("base.be")

    def _draft_invoice(self, invoice_date, move_type="out_invoice", journal=None):
        return self.env["account.move"].create({
            "move_type": move_type,
            "journal_id": (journal or self.journal).id,
            "partner_id": self.partner_a.id,
            "invoice_date": invoice_date,
            "date": invoice_date,
            "invoice_line_ids": [
                Command.create({"name": "Riga di test", "quantity": 1, "price_unit": 100.0}),
            ],
        })

    def _post_invoice(self, invoice_date, move_type="out_invoice", journal=None):
        move = self._draft_invoice(invoice_date, move_type=move_type, journal=journal)
        move.action_post()
        return move

    # -------------------------------------------------------------------------
    # Casella sul registro
    # -------------------------------------------------------------------------

    def test_flag_default_on_sale_journals(self):
        """La casella e' accesa di default sui registri vendita e spenta sugli altri."""
        self.assertTrue(self.journal.abc_invoice_date_check)
        self.assertFalse(self.purchase_journal.abc_invoice_date_check)

        new_sale_journal = self.env["account.journal"].create({
            "name": "Vendite test",
            "code": "VTST",
            "type": "sale",
        })
        self.assertTrue(new_sale_journal.abc_invoice_date_check)

    def test_no_warning_when_flag_disabled(self):
        """Con la casella spenta il controllo non si applica."""
        self.journal.abc_invoice_date_check = False
        self._post_invoice("2026-03-12")

        draft = self._draft_invoice("2026-03-05")
        self.assertFalse(draft.abc_invoice_date_warning)
        self.assertNotIn(ABC_DATE_ALERT, draft.alerts or {})

    def test_no_warning_on_vendor_bill(self):
        """Le fatture fornitore sono escluse anche con la casella accesa."""
        self.purchase_journal.abc_invoice_date_check = True
        self._post_invoice("2026-03-12", move_type="in_invoice", journal=self.purchase_journal)

        draft = self._draft_invoice("2026-03-05", move_type="in_invoice", journal=self.purchase_journal)
        self.assertFalse(draft.abc_invoice_date_warning)

    # -------------------------------------------------------------------------
    # Avviso
    # -------------------------------------------------------------------------

    def test_no_warning_when_date_is_later_or_equal(self):
        """Data pari o successiva all'ultima confermata: nessun avviso."""
        self._post_invoice("2026-03-12")

        self.assertFalse(self._draft_invoice("2026-03-12").abc_invoice_date_warning)
        self.assertFalse(self._draft_invoice("2026-03-20").abc_invoice_date_warning)

    def test_warning_when_date_is_earlier(self):
        """Data anteriore all'ultima confermata: avviso e alert di livello warning."""
        last = self._post_invoice("2026-03-12")

        draft = self._draft_invoice("2026-03-05")
        warning = draft.abc_invoice_date_warning
        self.assertTrue(warning)
        # Il messaggio nomina l'ultima fattura confermata e la data minima ammessa.
        self.assertIn(last.name, warning)

        self.assertIn(ABC_DATE_ALERT, draft.alerts)
        self.assertEqual(draft.alerts[ABC_DATE_ALERT]["level"], "warning")

    def test_no_warning_once_posted(self):
        """L'avviso riguarda solo le bozze: alla conferma sparisce."""
        self._post_invoice("2026-03-12")

        draft = self._draft_invoice("2026-03-05")
        self.assertTrue(draft.abc_invoice_date_warning)

        draft.action_post()
        self.assertFalse(draft.abc_invoice_date_warning)

    def test_alert_updates_when_date_changes(self):
        """L'alert si aggiunge e si toglie al variare della data, senza salvare."""
        self._post_invoice("2026-03-12")

        draft = self._draft_invoice("2026-03-12")
        baseline = dict(draft.alerts or {})
        self.assertNotIn(ABC_DATE_ALERT, baseline)

        # Retrodatando, il nostro alert si aggiunge a quelli del core senza sostituirli.
        draft.invoice_date = "2026-03-05"
        self.assertEqual(set(draft.alerts) - set(baseline), {ABC_DATE_ALERT})

        # Riportando la data in avanti l'alert sparisce.
        draft.invoice_date = "2026-03-12"
        self.assertNotIn(ABC_DATE_ALERT, draft.alerts or {})

    # -------------------------------------------------------------------------
    # Popup di conferma
    # -------------------------------------------------------------------------

    def test_confirmation_popup_is_wired(self):
        """Il popup legge l'avviso dal form, e il suo script e' nel bundle del backend."""
        arch = self.env["account.move"].get_views(
            [(self.env.ref("account.view_move_form").id, "form")]
        )["views"]["form"]["arch"]
        self.assertIn('name="abc_invoice_date_warning"', arch)

        IrAsset = self.env["ir.asset"]
        paths = IrAsset._get_asset_paths("web.assets_backend", IrAsset._get_asset_params())
        self.assertTrue(any(
            "abc_account_invoice_date_check/static/src/account_move_form_controller.js" in path
            for path, *_dummy in paths
        ))

    # -------------------------------------------------------------------------
    # Periodo di numerazione
    # -------------------------------------------------------------------------

    def test_previous_year_has_its_own_series(self):
        """Una fattura di fine anno registrata a gennaio e' confrontata solo con il suo anno."""
        self._post_invoice("2026-01-05")

        # Prendera' un numero del 2025: le fatture del 2026 non fanno da riferimento.
        late = self._draft_invoice("2025-12-30")
        self.assertFalse(late.abc_invoice_date_warning)

        # Il riferimento resta l'ultima confermata del 2025.
        last_2025 = self._post_invoice("2025-12-31")
        earlier = self._draft_invoice("2025-12-20")
        self.assertTrue(earlier.abc_invoice_date_warning)
        self.assertIn(last_2025.name, earlier.abc_invoice_date_warning)

    # -------------------------------------------------------------------------
    # Reimposta a bozza
    # -------------------------------------------------------------------------

    def test_reset_to_draft_of_last_invoice_has_no_warning(self):
        """Riaprire l'ultima fattura non segnala nulla: il riferimento e' la precedente."""
        self._post_invoice("2026-03-05")
        last = self._post_invoice("2026-03-12")

        last.button_draft()
        self.assertEqual(last.state, "draft")
        self.assertFalse(last.abc_invoice_date_warning)

    def test_reset_to_draft_of_older_invoice_warns(self):
        """Riaprire una fattura piu' vecchia segnala il rischio sulla cronologia."""
        older = self._post_invoice("2026-03-05")
        newer = self._post_invoice("2026-03-12")

        older.button_draft()
        warning = older.abc_invoice_date_warning
        self.assertTrue(warning)
        self.assertIn(newer.name, warning)

    # -------------------------------------------------------------------------
    # Serie delle note di credito
    # -------------------------------------------------------------------------

    def test_refund_series_is_independent(self):
        """Con sequenza dedicata, le note di credito hanno un riferimento separato."""
        self.journal.refund_sequence = True
        self._post_invoice("2026-03-12")

        # Nessuna nota di credito confermata: la fattura del 12/03 non fa da riferimento.
        refund = self._draft_invoice("2026-03-05", move_type="out_refund")
        self.assertFalse(refund.abc_invoice_date_warning)

        self._post_invoice("2026-03-12", move_type="out_refund")
        later_refund = self._draft_invoice("2026-03-05", move_type="out_refund")
        self.assertTrue(later_refund.abc_invoice_date_warning)

    def test_shared_series_includes_refunds(self):
        """Senza sequenza dedicata, fatture e note di credito sono la stessa serie."""
        self.journal.refund_sequence = False
        self._post_invoice("2026-03-12")

        refund = self._draft_invoice("2026-03-05", move_type="out_refund")
        self.assertTrue(refund.abc_invoice_date_warning)
