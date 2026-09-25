# Copyright 2026 ABC Strategie
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import api, fields, models
from odoo.tools.misc import format_date, formatLang


class ReportFinancialStatementsFull(models.AbstractModel):
    _name = "report.bitti_financial_statements.report_full"
    _description = "Situazione contabile a sezioni contrapposte (SP + CE)"
    _inherit = "report.l10n_it_financial_statements_report.report"

    # Sezioni stampate, nell'ordine, con il lato su cui compare l'utile
    SECTIONS = (
        # (tipo OCA, lato dell'utile: 'right' = passività, 'left' = costi)
        ("balance_sheet", "right"),
        ("profit_loss", "left"),
    )

    def get_column_data(self):
        res = super().get_column_data()
        res["balance_sheet"].update({
            "title": self.env._("SITUAZIONE PATRIMONIALE"),
            "left": {"section": "assets", "name": self.env._("ATTIVITA'")},
            "right": {"section": "liabilities", "name": self.env._("PASSIVITA'")},
        })
        res["profit_loss"].update({
            "title": self.env._("CONTO ECONOMICO"),
            "left": {"section": "expenses", "name": self.env._("COMPONENTI NEGATIVE DI REDDITO")},
            "right": {"section": "incomes", "name": self.env._("COMPONENTI POSITIVE DI REDDITO")},
        })
        return res

    # ------------------------------------------------------------------
    # Dati per il template
    # ------------------------------------------------------------------
    @api.model
    def _get_report_values(self, docids, data=None):
        data = dict(data or {})
        wizard = self.env["trial.balance.report.wizard"].browse(data["wizard_id"])
        company = wizard.company_id or self.env.company
        currency = company.currency_id

        sections = []
        for rep_type, profit_side in self.SECTIONS:
            section_data = dict(data, financial_statements_report_type=rep_type)
            report_data = self.compute_data_for_report(section_data)
            sections.append(self._bitti_build_section(report_data, section_data, profit_side, currency))

        return {
            "doc_ids": wizard.ids,
            "doc_model": wizard._name,
            "docs": wizard,
            "company": company,
            "header": self._bitti_header(company, data),
            "sections": sections,
        }

    def _bitti_header(self, company, data):
        def strip_country(code):
            code = (code or "").strip()
            if code[:2].upper() == "IT" and code[2:].isdigit():
                return code[2:]
            return code

        partner = company.partner_id
        address = " ".join(filter(None, [
            partner.street, partner.street2, partner.zip, partner.city,
            partner.state_id.code and f"({partner.state_id.code})",
        ]))
        return {
            "company_name": company.name,
            "codice_fiscale": strip_country(partner.l10n_it_codice_fiscale or partner.vat),
            "partita_iva": strip_country(partner.vat),
            "address": address,
            "date_from": format_date(self.env, data.get("date_from")),
            "date_to": format_date(self.env, data.get("date_to")),
            "only_posted_moves": data.get("only_posted_moves"),
            "printed_on": fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime("%d/%m/%Y %H:%M"),
        }

    def _bitti_build_section(self, report_data, wizard_data, profit_side, currency):
        hide_zero = wizard_data.get("hide_account_at_0")
        hide_codes = wizard_data.get("hide_accounts_codes")
        accounts_data = report_data.get("accounts_data", {})

        def fmt(amount):
            return formatLang(self.env, amount or 0.0, digits=2)

        group_prefixes = {}

        def group_has_nonzero(line, nonzero_codes):
            group_id = line.get("group_id")
            if group_id not in group_prefixes:
                group = self.env["account.group"].browse(group_id)
                group_prefixes[group_id] = (group.code_prefix_start or "", group.code_prefix_end or "")
            start, end = group_prefixes[group_id]
            if not start:
                return True
            return any(
                start <= code[:len(start)] and code[:len(end)] <= end
                for code in nonzero_codes
            )

        def prepare_lines(lines):
            # Elimina conti a zero e gruppi senza conti valorizzati (se richiesto)
            lines = [dict(line) for line in lines]
            if hide_zero:
                nonzero_codes = {
                    accounts_data.get(line["account_id"], {}).get("code") or ""
                    for line in lines
                    if line.get("account_id") and not currency.is_zero(line.get("ending_balance", 0.0))
                }
                lines = [
                    line for line in lines
                    if (line.get("account_id") and not currency.is_zero(line.get("ending_balance", 0.0)))
                    or (not line.get("account_id") and group_has_nonzero(line, nonzero_codes))
                ]
            result = []
            for line in lines:
                account_id = line.get("account_id")
                if account_id:
                    account_data = accounts_data.get(account_id, {})
                    code = account_data.get("code") or line.get("code") or ""
                    name = account_data.get("name") or line.get("name") or ""
                else:
                    code = line.get("complete_code") or line.get("code") or ""
                    name = line.get("name") or ""
                result.append({
                    "code": "" if hide_codes else code,
                    "name": name,
                    "amount": fmt(line.get("ending_balance")),
                    "is_group": not account_id,
                    "level": line.get("level") or 1,
                })
            return result

        left_lines = prepare_lines(report_data["section_debit_ids"])
        right_lines = prepare_lines(report_data["section_credit_ids"])
        rows = [
            {
                "left": left_lines[i] if i < len(left_lines) else None,
                "right": right_lines[i] if i < len(right_lines) else None,
            }
            for i in range(max(len(left_lines), len(right_lines)))
        ]

        total_left = currency.round(report_data["total_debit"])
        total_right = currency.round(report_data["total_credit"])
        # Risultato: positivo = utile. SP: attività - passività; CE: ricavi - costi
        if profit_side == "right":
            result = total_left - total_right
        else:
            result = total_right - total_left
        if currency.compare_amounts(result, 0.0) >= 0:
            result_side = profit_side
            result_label = self.env._("Utile")
        else:
            result_side = "left" if profit_side == "right" else "right"
            result_label = self.env._("Perdita")
        pareggio = max(total_left, total_right)

        return {
            "title": report_data["title"],
            "left_col_name": report_data["left_col_name"],
            "right_col_name": report_data["right_col_name"],
            "rows": rows,
            "total_left": fmt(total_left),
            "total_right": fmt(total_right),
            "result_side": result_side,
            "result_label": result_label,
            "result_amount": fmt(abs(result)),
            "pareggio_amount": fmt(pareggio),
            "show_result": not currency.is_zero(result),
        }
