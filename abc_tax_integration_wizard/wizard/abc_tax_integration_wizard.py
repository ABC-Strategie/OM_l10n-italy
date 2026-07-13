from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

class AbcTaxIntegrationWizard(models.TransientModel):
    _name = 'abc.tax.integration.wizard'
    _description = 'Anteprima XML Integrazione Fiscale'

    move_id = fields.Many2one('account.move', string='Fattura', required=True)
    xml_content = fields.Text(string='Contenuto XML', compute='_compute_xml_content')

    @api.depends('move_id')
    def _compute_xml_content(self):
        for wizard in self:
            if wizard.move_id:
                try:
                    # Controlla eventuali errori prima di generare l'XML
                    errors = wizard.move_id._l10n_it_edi_export_data_check()
                    if errors:
                        messages = []
                        for error_key, error_data in errors.items():
                            messages.append(error_data['message'])
                        wizard.xml_content = "Errore nella validazione dei dati:\n\n" + "\n".join(messages)
                    else:
                        # Genera l'XML
                        attachment_vals = wizard.move_id._l10n_it_edi_get_attachment_values(pdf_values=None)
                        wizard.xml_content = attachment_vals['raw'].decode('utf-8')
                except Exception as e:
                    wizard.xml_content = _("Errore durante la generazione dell'XML: %s") % str(e)
            else:
                wizard.xml_content = False

    def action_send(self):
        self.ensure_one()
        # Richiama l'azione di invio originale ma con un flag nel context per bypassare il wizard
        return self.move_id.with_context(bypass_tax_integration_wizard=True).action_l10n_it_edi_send()
