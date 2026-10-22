# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountVatPeriodEndStatement(models.Model):
    _inherit = "account.vat.period.end.statement"

    def _get_period_base_amount(self, tax, statement, registry_type):
        """Imponibile dell'imposta sommato sui periodi della liquidazione."""
        base = 0.0
        for period in statement.date_range_ids:
            base += tax._compute_totals_tax(
                {
                    "from_date": period.date_start,
                    "to_date": period.date_end,
                    "registry_type": registry_type,
                }
            )[1]  # position 1 is base
        return base

    # Una riga a importo zero si scarta solo se l'imposta non e' stata
    # movimentata: le aliquote 0% con imponibile nel periodo restano visibili.
    def _set_debit_lines(self, debit_tax, debit_line_ids, statement):
        before = len(debit_line_ids)
        super()._set_debit_lines(debit_tax, debit_line_ids, statement)
        if (
            len(debit_line_ids) > before
            and not debit_line_ids[-1]["amount"]
            and not self._get_period_base_amount(debit_tax, statement, "customer")
        ):
            debit_line_ids.pop()

    def _set_credit_lines(self, credit_tax, credit_line_ids, statement):
        before = len(credit_line_ids)
        super()._set_credit_lines(credit_tax, credit_line_ids, statement)
        if (
            len(credit_line_ids) > before
            and not credit_line_ids[-1]["amount"]
            and not self._get_period_base_amount(credit_tax, statement, "supplier")
        ):
            credit_line_ids.pop()

    def _get_credit_debit_lines(self, statement):
        credit_line_ids, debit_line_ids = super()._get_credit_debit_lines(statement)
        # Il modulo base considera solo le imposte con un conto IVA sulle righe
        # di ripartizione, mentre le aliquote 0% di solito non ne hanno: le
        # aggiungiamo qui, e i metodi sopra tengono solo quelle movimentate.
        # Senza conto non si possono attribuire a un filtro conti, quindi con
        # il filtro attivo restano escluse.
        if statement.account_ids:
            return credit_line_ids, debit_line_ids
        taxes = self.env["account.tax"].search(
            [
                ("exclude_from_vat_settlements", "=", False),
                ("type_tax_use", "in", ["sale", "purchase"]),
            ]
        )
        zero_taxes = taxes.filtered(
            lambda t: not t._get_tax_amount()
            and not t._get_debit_accounts()
            and not t._get_credit_accounts()
        )
        for tax in zero_taxes:
            if tax.type_tax_use == "sale":
                self._set_debit_lines(tax, debit_line_ids, statement)
            else:
                self._set_credit_lines(tax, credit_line_ids, statement)
        return credit_line_ids, debit_line_ids
