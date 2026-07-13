# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WithholdingTaxStatement(models.Model):
    _inherit = 'withholding.tax.statement'

    amount = fields.Float(
        string="WT amount applied",
        compute='_compute_abc_total',
        store=True,
        readonly=True,
    )
    amount_paid = fields.Float(
        string="WT amount paid",
        compute='_compute_abc_total',
        store=True,
        readonly=True,
    )

    @api.depends('move_ids.amount', 'move_ids.state')
    def _compute_abc_total(self):
        for statement in self:
            tot_wt_amount = 0.0
            tot_wt_amount_paid = 0.0
            for wt_move in statement.move_ids:
                tot_wt_amount += wt_move.amount
                if wt_move.state == 'paid':
                    tot_wt_amount_paid += wt_move.amount
            statement.amount = tot_wt_amount
            statement.amount_paid = tot_wt_amount_paid

    @api.model
    def action_sync_wt_moves(self):
        """
        Sincronizza i movimenti di pagamento delle ritenute d'acconto analizzando 
        lo stato dei pagamenti delle fatture collegate. Viene chiamato dalla Server Action.
        """
        statements = self.search([('invoice_id', '!=', False)])
        for st in statements:
            inv = st.invoice_id
            if inv.payment_state in ['paid', 'in_payment', 'partial']:
                existing_paid_amount = sum(m.amount for m in st.move_ids if m.state == 'paid')
                
                # Calcolo proporzionale del pagato
                if inv.amount_total > 0:
                    paid_ratio = (inv.amount_total - inv.amount_residual) / inv.amount_total
                    expected_paid_wt = st.tax * paid_ratio
                else:
                    expected_paid_wt = st.tax
                
                diff = expected_paid_wt - existing_paid_amount
                
                if abs(diff) > 0.01:
                    self.env['withholding.tax.move'].sudo().create({
                        'statement_id': st.id,
                        'date': fields.Date.context_today(self),
                        'partner_id': st.partner_id.id,
                        'withholding_tax_id': st.withholding_tax_id.id,
                        'amount': diff,
                        'state': 'paid',
                        'account_move_id': inv.id,
                    })
