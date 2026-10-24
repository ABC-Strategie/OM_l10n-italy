from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestNoteLine(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_country('it')
    def setUpClass(cls):
        super().setUpClass()
        # contesto: niente verifiche anagrafiche esterne dei moduli installati
        cls.cliente = cls.env['res.partner'].with_context(abc_va_skip_trigger=True).create({
            'name': 'Cliente note test', 'country_id': cls.env.ref('base.it').id,
            'street': 'Via Roma 1', 'zip': '00100', 'city': 'Roma',
            'l10n_it_codice_fiscale': 'RSSMRA80A01H501U',
        })

    def test_righe_nota_nell_xml(self):
        fattura = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_line_ids': [
                (0, 0, {'display_type': 'line_note', 'name': 'Nota di prova'}),
                (0, 0, {'name': 'Servizio', 'quantity': 1, 'price_unit': 100.0}),
            ],
        })
        valori = fattura._l10n_it_edi_get_values()
        note = [bl for bl in valori['base_lines'] if bl['record'].display_type == 'line_note']
        self.assertEqual(len(note), 1)
        # anche con l10n_it_edi_extension installato l'XML si genera
        self.assertIn('admin_ref', note[0]['it_values'])
        xml = fattura._l10n_it_edi_render_xml()
        xml = xml if isinstance(xml, bytes) else xml.encode()
        self.assertIn(b'Nota di prova', xml)
