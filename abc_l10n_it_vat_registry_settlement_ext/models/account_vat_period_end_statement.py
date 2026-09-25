# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountVatPeriodEndStatement(models.Model):
    _inherit = "account.vat.period.end.statement"

    def _set_debit_lines(self, debit_tax, debit_line_ids, statement):
        before = len(debit_line_ids)
        super()._set_debit_lines(debit_tax, debit_line_ids, statement)
        if len(debit_line_ids) > before and not debit_line_ids[-1]["amount"]:
            debit_line_ids.pop()

    def _set_credit_lines(self, credit_tax, credit_line_ids, statement):
        before = len(credit_line_ids)
        super()._set_credit_lines(credit_tax, credit_line_ids, statement)
        if len(credit_line_ids) > before and not credit_line_ids[-1]["amount"]:
            credit_line_ids.pop()
