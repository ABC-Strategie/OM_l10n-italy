from odoo import models

class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_it_edi_get_values(self, pdf_values=None):
        res = super()._l10n_it_edi_get_values(pdf_values=pdf_values)
        
        # In Odoo 18/19, note lines are excluded by default in `base_amls`.
        # We want to include them in the XML.
        note_lines = self.invoice_line_ids.filtered(lambda x: x.display_type == 'line_note')
        if not note_lines:
            return res
            
        base_lines = res.get('base_lines', [])

        # Assign a default tax rate matching the first regular line (if any)
        # to avoid generating extra 0% / N2.2 tax summary blocks in the XML.
        default_aliquota_iva = [0.0]
        default_natura = 'N2.2'
        regular_lines = [
            bl for bl in base_lines 
            if bl.get('record') and bl['record'].display_type in ('product', 'rounding')
        ]
        if regular_lines:
            first_reg = regular_lines[0]
            if 'it_values' in first_reg:
                default_aliquota_iva = first_reg['it_values'].get('aliquota_iva_list', [0.0])
                default_natura = first_reg['it_values'].get('natura')
        
        # Create base_line entry for each note line
        for note in note_lines:
            it_values = {
                'numero_linea': 0, # Will be reassigned below
                'descrizione': note.name or 'Nota',
                'quantita': 0.0,
                'quantita_pd': 2,
                'prezzo_unitario': 0.0,
                'prezzo_totale': 0.0,
                'sconto_maggiorazione_list': [],
                'aliquota_iva_list': default_aliquota_iva,
                'ritenuta': False,
                'natura': default_natura,
                'altri_dati_gestionali_list': [],
            }
            
            base_lines.append({
                'record': note,
                'product_id': note.product_id,
                'it_values': it_values,
                'tax_details': {
                     'taxes_data': [],
                     'raw_total_excluded_currency': 0.0,
                },
                'discount': 0.0,
                'price_unit': 0.0,
                'quantity': 0.0,
                'gross_price_subtotal': 0.0,
            })
            
        # Re-sort base_lines: notes always first, then according to their original sequence
        invoice_line_ids = self.invoice_line_ids.ids
        def get_sequence(base_line):
            is_regular = 1
            seq = 9999
            try:
                record = base_line.get('record')
                if record and hasattr(record, 'display_type') and record.display_type == 'line_note':
                    is_regular = 0

                # If there are multiple lines generated for the same aml (e.g., OSS vat line),
                # we sort them right after the original line using id/1000 trick
                if record and hasattr(record, 'id') and isinstance(record.id, int):
                    seq = invoice_line_ids.index(record.id)
                elif record and hasattr(record, 'id'):
                    # if it's a NewId or string id (OSS vat)
                    if isinstance(record.id, str) and '_vat' in record.id:
                        aml_id = int(record.id.split('_')[0])
                        try:
                            seq = invoice_line_ids.index(aml_id) + 0.1
                        except ValueError:
                            pass
            except (ValueError, TypeError):
                pass
            return (is_regular, seq)
                
        base_lines.sort(key=get_sequence)
        
        # Re-assign numero_linea
        for index, base_line in enumerate(base_lines, start=1):
            if 'it_values' in base_line:
                base_line['it_values']['numero_linea'] = index
                
        # Ensure all tax rates/nature combinations in base_lines are present in tax_lines
        tax_lines = res.setdefault('tax_lines', [])
        existing_tax_keys = {
            (t.get('aliquota_iva'), t.get('natura'))
            for t in tax_lines
        }
        for base_line in base_lines:
            if 'it_values' in base_line:
                it_vals = base_line['it_values']
                natura = it_vals.get('natura')
                for rate in it_vals.get('aliquota_iva_list', []):
                    if (rate, natura) not in existing_tax_keys:
                        tax_lines.append({
                            'aliquota_iva': rate,
                            'natura': natura,
                            'arrotondamento': None,
                            'imponibile_importo': 0.0,
                            'imposta': 0.0,
                            'esigibilita_iva': 'I' if rate == 0.0 else None,
                            'riferimento_normativo': None,
                        })
                        existing_tax_keys.add((rate, natura))
                        
        res['base_lines'] = base_lines
        return res
