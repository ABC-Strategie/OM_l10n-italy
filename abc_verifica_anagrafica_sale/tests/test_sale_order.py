# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

CF = 'RSSMRA85T10A562S'


@tagged('post_install', '-at_install', 'abc_va')
class TestSaleOrder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'abc_va_enabled': True,
            'abc_va_client_id': 'clientid-0123456789',
            'abc_va_client_secret': 'SECRET-abcdef123456',
            'abc_va_secret_expiry': fields.Date.today() + timedelta(days=365),
            'abc_va_on_invalid': 'block_document',
            'abc_va_trigger_on_sale': True,
            'abc_va_name_check': 'off',
        })
        cls.product = cls.env['product.product'].create([{
            'name': 'Servizio test', 'type': 'service', 'list_price': 10.0,
        }])
        cls.Queue = cls.env['abc.va.queue']

    def _person(self, state=None):
        partner = self.env['res.partner'].with_context(abc_va_skip_trigger=True).create([{
            'name': 'Persona', 'l10n_it_codice_fiscale': CF,
        }])
        if state:
            partner._abc_va_apply_result(state, 'esito di test', CF)
        return partner

    def _order(self, partner):
        return self.env['sale.order'].create([{
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})],
        }])

    def _pending(self, partner):
        return self.Queue.search([('partner_id', '=', partner.id), ('state', '=', 'pending')])

    def test_block_invalid(self):
        order = self._order(self._person('invalid'))
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_error_never_blocks(self):
        order = self._order(self._person('error'))
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_warn(self):
        self.company.abc_va_on_invalid = 'warn'
        order = self._order(self._person('invalid'))
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertIn('non valido', ' '.join(order.message_ids.mapped(lambda m: str(m.body))))

    def test_on_use_trigger(self):
        partner = self._person()
        order = self._order(partner)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertEqual(len(self._pending(partner)), 1)

    def test_on_use_trigger_disabled(self):
        self.company.abc_va_trigger_on_sale = False
        partner = self._person()
        self._order(partner).action_confirm()
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_quotation_save_triggers_verification(self):
        # la verifica parte al salvataggio del preventivo, non alla conferma
        partner = self._person()
        order = self._order(partner)
        self.assertEqual(order.state, 'draft')
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertEqual(len(self._pending(partner)), 1)
        # cambio cliente sul preventivo: anche il nuovo viene accodato
        other = self._person()
        order.partner_id = other
        self.assertEqual(other.abc_va_state, 'pending')

    def test_quotation_save_skip_context(self):
        partner = self._person()
        self.env['sale.order'].with_context(abc_va_skip_trigger=True).create([{
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})],
        }])
        self.assertEqual(partner.abc_va_state, 'not_verified')
