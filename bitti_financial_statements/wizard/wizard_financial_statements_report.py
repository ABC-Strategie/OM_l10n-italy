# Copyright 2026 ABC Strategie
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import fields, models
from odoo.exceptions import UserError

BITTI_FULL = "bitti_full"


class ReportFinancialStatementsWizard(models.TransientModel):
    _inherit = "trial.balance.report.wizard"

    financial_statements_report_type = fields.Selection(
        selection_add=[(BITTI_FULL, "Situazione contabile a sezioni contrapposte (SP + CE)")],
        ondelete={BITTI_FULL: "set null"},
    )

    def _print_report(self, report_type):
        self.ensure_one()
        if self.financial_statements_report_type != BITTI_FULL:
            return super()._print_report(report_type)
        if report_type == "xlsx":
            raise UserError(self.env._(
                "L'export XLSX non è disponibile per il documento unico: "
                "selezionare separatamente Stato patrimoniale o Conto economico."
            ))
        report_data = self._prepare_report_data()
        if report_type == "qweb-html":
            xml_id = "bitti_financial_statements.action_report_full_html"
        else:
            xml_id = "bitti_financial_statements.action_report_full_pdf"
        return self.env.ref(xml_id).report_action(self, data=report_data)
