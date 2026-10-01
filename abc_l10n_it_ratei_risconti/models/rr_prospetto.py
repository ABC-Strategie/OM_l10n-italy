# -*- coding: utf-8 -*-
import base64
import io
from collections import OrderedDict

import xlsxwriter

from odoo import fields, models

from .rr_compute import RR_TYPES

AMOUNT_KEYS = ('base', 'competence', 'amount', 'within', 'beyond', 'beyond_5y')


def _n_rows(n):
    return '%s %s' % (n, 'riga' if n == 1 else 'righe')


class AbcRrRunLine(models.Model):
    _inherit = 'abc.rr.run.line'

    # ------------------------------------------------------------------
    # Pulsanti PDF / XLSX della lista "Prospetto": aprono la finestra dei filtri
    # ------------------------------------------------------------------
    def _open_prospetto_wizard(self, output):
        ctx = {'default_output': output}
        if self:
            ctx.update({'default_line_ids': [(6, 0, self.ids)], 'default_date_from': False, 'default_date_to': False})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Prospetto ratei e risconti'),
            'res_model': 'abc.rr.prospetto.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_prospetto_pdf(self):
        return self._open_prospetto_wizard('pdf')

    def action_prospetto_xlsx(self):
        return self._open_prospetto_wizard('xlsx')

    # ------------------------------------------------------------------
    # Dati raggruppati: data di chiusura > tipologia > conto rateo/risconto
    # ------------------------------------------------------------------
    def _prospetto_row(self):
        self.ensure_one()
        sg = self._natural_sign()
        return {
            'line': self,
            'base': self.base_amount * sg,
            'competence': self.competence_amount * sg,
            'amount': self.amount * sg,
            'within': self.final_within * sg,
            'beyond': self.final_beyond * sg,
            'beyond_5y': self.amount_beyond_5y * sg,
        }

    @staticmethod
    def _empty_totals():
        return dict.fromkeys(AMOUNT_KEYS, 0.0)

    @staticmethod
    def _add_totals(totals, row):
        for key in AMOUNT_KEYS:
            totals[key] += row[key]

    def get_prospetto_groups(self):
        """Struttura per PDF ed Excel. Importi esposti positivi, come in bilancio."""
        type_labels = dict(RR_TYPES)
        type_order = [t for t, _l in RR_TYPES]
        lines = self.sorted(lambda l: (
            l.closing_date or fields.Date.today(),
            type_order.index(l.rr_type) if l.rr_type in type_order else 99,
            l.rr_account_id.code or '',
            l.date_start or fields.Date.today(),
            l.id,
        ))
        dates = OrderedDict()
        for line in lines:
            row = line._prospetto_row()
            d = dates.setdefault(line.closing_date, {
                'closing_date': line.closing_date, 'company': line.company_id,
                'types': OrderedDict(), 'totals': self._empty_totals(), 'count': 0})
            t = d['types'].setdefault(line.rr_type, {
                'label': type_labels.get(line.rr_type, line.rr_type),
                'accounts': OrderedDict(), 'totals': self._empty_totals(), 'count': 0})
            a = t['accounts'].setdefault(line.rr_account_id.id, {
                'account': line.rr_account_id, 'rows': [], 'totals': self._empty_totals()})
            a['rows'].append(row)
            for bucket in (d, t, a):
                self._add_totals(bucket['totals'], row)
            d['count'] += 1
            t['count'] += 1
        result = []
        for d in dates.values():
            types = []
            for t in d['types'].values():
                t['accounts'] = list(t['accounts'].values())
                types.append(t)
            d['types'] = types
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _prospetto_xlsx_action(self):
        content = self._prospetto_xlsx_content()
        name = 'Prospetto ratei e risconti %s.xlsx' % fields.Date.today().strftime('%Y%m%d')
        attachment = self.env['ir.attachment'].create({
            'name': name,
            'datas': base64.b64encode(content),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _prospetto_xlsx_content(self):
        groups = self.get_prospetto_groups()
        company = self[:1].company_id or self.env.company
        out = io.BytesIO()
        wb = xlsxwriter.Workbook(out, {'in_memory': True})
        ws = wb.add_worksheet('Ratei e risconti')

        # impaginazione orizzontale, tutte le colonne su una pagina in larghezza
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        ws.repeat_rows(3)
        ws.set_footer('&L%s&RPagina &P di &N' % (company.name or '').replace('&', '&&'))

        blue = '#2B3A8C'
        f_title = wb.add_format({'bold': True, 'font_size': 14, 'font_color': blue})
        f_sub = wb.add_format({'italic': True, 'font_color': '#666666'})
        f_head = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': blue, 'border': 1,
                                'text_wrap': True, 'valign': 'vcenter', 'align': 'center'})
        f_txt = wb.add_format({'border': 1, 'valign': 'top'})
        f_wrap = wb.add_format({'border': 1, 'valign': 'top', 'text_wrap': True})
        f_date = wb.add_format({'border': 1, 'num_format': 'dd/mm/yyyy', 'valign': 'top'})
        f_int = wb.add_format({'border': 1, 'num_format': '#,##0', 'valign': 'top'})
        f_num = wb.add_format({'border': 1, 'num_format': '#,##0.00', 'valign': 'top'})
        f_g1 = wb.add_format({'bold': True, 'bg_color': '#C9D0EE', 'border': 1})
        f_g1n = wb.add_format({'bold': True, 'bg_color': '#C9D0EE', 'border': 1, 'num_format': '#,##0.00'})
        f_g2 = wb.add_format({'bold': True, 'bg_color': '#E4E8F7', 'border': 1})
        f_g2n = wb.add_format({'bold': True, 'bg_color': '#E4E8F7', 'border': 1, 'num_format': '#,##0.00'})
        f_g3 = wb.add_format({'italic': True, 'bg_color': '#F3F4FA', 'border': 1})
        f_g3n = wb.add_format({'italic': True, 'bg_color': '#F3F4FA', 'border': 1, 'num_format': '#,##0.00'})
        f_tot = wb.add_format({'bold': True, 'top': 2, 'bottom': 2})
        f_totn = wb.add_format({'bold': True, 'top': 2, 'bottom': 2, 'num_format': '#,##0.00'})

        headers = [
            ('Elaborazione', 14), ('Tipologia', 15), ('Conto rateo/risconto', 26), ('Conto di costo/ricavo', 26),
            ('Partner', 22), ('Documento', 18), ('Data doc.', 11), ('Descrizione', 30),
            ('Data inizio', 11), ('Data fine', 11), ('Gg totali', 8), ('Gg competenza esercizio', 11), ('Gg rateo/risconto', 10),
            ('Imponibile', 13), ('Competenza esercizio', 13), ('Rateo/Risconto alla data', 14),
            ('Entro 12 mesi', 13), ('Oltre 12 mesi', 13), ('Di cui oltre 5 anni', 13),
        ]
        first_amount_col = 13
        last_col = len(headers) - 1
        for col, (_h, width) in enumerate(headers):
            ws.set_column(col, col, width)

        ws.write(0, 0, 'Prospetto ratei e risconti - %s' % (company.name or ''), f_title)
        dates_txt = ', '.join(g['closing_date'].strftime('%d/%m/%Y') for g in groups if g['closing_date'])
        ws.write(1, 0, 'Data di chiusura: %s - estratto il %s' % (
            dates_txt or '-', fields.Date.context_today(self).strftime('%d/%m/%Y')), f_sub)
        ws.set_row(3, 32)
        for col, (h, _w) in enumerate(headers):
            ws.write(3, col, h, f_head)
        ws.freeze_panes(4, 0)

        def write_totals(r, label, totals, fmt, fmt_n):
            ws.merge_range(r, 0, r, first_amount_col - 1, label, fmt)
            for i, key in enumerate(AMOUNT_KEYS):
                ws.write_number(r, first_amount_col + i, totals[key], fmt_n)

        def write_group(r, label, fmt):
            ws.merge_range(r, 0, r, last_col, label, fmt)

        r = 4
        grand = self._empty_totals()
        for g in groups:
            closing = g['closing_date'].strftime('%d/%m/%Y') if g['closing_date'] else '-'
            write_group(r, 'Data di chiusura %s (%s)' % (closing, _n_rows(g['count'])), f_g1)
            r += 1
            for t in g['types']:
                write_group(r, '%s (%s)' % (t['label'], _n_rows(t['count'])), f_g2)
                r += 1
                for a in t['accounts']:
                    for row in a['rows']:
                        line = row['line']
                        ws.write(r, 0, line.run_id.name or '', f_txt)
                        ws.write(r, 1, t['label'], f_txt)
                        ws.write(r, 2, line.rr_account_id.display_name or '', f_wrap)
                        ws.write(r, 3, line.account_id.display_name or '', f_wrap)
                        ws.write(r, 4, line.partner_id.display_name or '', f_wrap)
                        ws.write(r, 5, line.move_id.name or line.card_id.name or '', f_wrap)
                        if line.move_date:
                            ws.write_datetime(r, 6, fields.Datetime.to_datetime(line.move_date), f_date)
                        else:
                            ws.write_blank(r, 6, None, f_txt)
                        ws.write(r, 7, line.name or '', f_wrap)
                        for col, d in ((8, line.date_start), (9, line.date_end)):
                            if d:
                                ws.write_datetime(r, col, fields.Datetime.to_datetime(d), f_date)
                            else:
                                ws.write_blank(r, col, None, f_txt)
                        ws.write_number(r, 10, line.days_total, f_int)
                        ws.write_number(r, 11, line.days_competence, f_int)
                        ws.write_number(r, 12, line.days_rr, f_int)
                        for i, key in enumerate(AMOUNT_KEYS):
                            ws.write_number(r, first_amount_col + i, row[key], f_num)
                        r += 1
                    write_totals(r, 'Totale conto %s' % (a['account'].display_name or '-'), a['totals'], f_g3, f_g3n)
                    r += 1
                write_totals(r, 'Totale %s' % t['label'], t['totals'], f_g2, f_g2n)
                r += 1
            write_totals(r, 'Totale al %s' % closing, g['totals'], f_g1, f_g1n)
            r += 1
            self._add_totals(grand, g['totals'])
        if len(groups) > 1:
            write_totals(r, 'Totale generale', grand, f_tot, f_totn)
        ws.print_area(0, 0, max(r, 4), last_col)
        wb.close()
        return out.getvalue()
