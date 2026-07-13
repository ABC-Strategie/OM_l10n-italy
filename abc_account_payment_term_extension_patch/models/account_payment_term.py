from dateutil.relativedelta import relativedelta

from odoo import models
from odoo.exceptions import UserError


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    def _compute_terms(
        self,
        date_ref,
        currency,
        company,
        tax_amount,
        tax_amount_currency,
        sign,
        untaxed_amount,
        untaxed_amount_currency,
        cash_rounding=None,
    ):
        if currency == company.currency_id:
            if not tax_amount_currency and tax_amount:
                tax_amount_currency = tax_amount
            if not untaxed_amount_currency and untaxed_amount:
                untaxed_amount_currency = untaxed_amount

        """Complete overwrite of compute method to fix argument swapping in base module."""
        if cash_rounding:
            raise UserError(
                self.env._("This module is not compatible with cash rounding")
            )
        self.ensure_one()
        company_currency = company.currency_id
        total_amount = remaining_amount = tax_amount + untaxed_amount
        total_amount_currency = remaining_amount_currency = (
            tax_amount_currency + untaxed_amount_currency
        )
        pay_term = {
            "total_amount": total_amount,
            "discount_percentage": self.discount_percentage
            if self.early_discount
            else 0.0,
            "discount_date": date_ref + relativedelta(days=(self.discount_days or 0))
            if self.early_discount
            else False,
            "discount_balance": 0,
            "line_ids": [],
        }

        if self.early_discount:
            # Early discount is only available on single line, 100% payment terms.
            discount_percentage = self.discount_percentage / 100.0
            if self.early_pay_discount_computation in ("excluded", "mixed"):
                pay_term["discount_balance"] = company_currency.round(
                    total_amount - untaxed_amount * discount_percentage
                )
                pay_term["discount_amount_currency"] = currency.round(
                    total_amount_currency
                    - untaxed_amount_currency * discount_percentage
                )
            else:
                pay_term["discount_balance"] = company_currency.round(
                    total_amount * (1 - discount_percentage)
                )
                pay_term["discount_amount_currency"] = currency.round(
                    total_amount_currency * (1 - discount_percentage)
                )

        residual_amount = total_amount
        residual_amount_currency = total_amount_currency
        precision_digits = currency.decimal_places
        company_precision_digits = company_currency.decimal_places
        next_date = date_ref
        for i, line in enumerate(self.line_ids):
            if not self.sequential_lines:
                # For all lines, the beginning date is `date_ref`
                next_date = line._get_due_date(date_ref)
            else:
                next_date = line._get_due_date(next_date)

            next_date = self.apply_payment_days(line, next_date)
            next_date = self.apply_holidays(next_date)

            term_vals = {
                "date": next_date,
                "company_amount": 0,
                "foreign_amount": 0,
            }

            if i == len(self.line_ids) - 1:
                # The last line is always the balance, no matter the type
                term_vals["company_amount"] = residual_amount
                term_vals["foreign_amount"] = residual_amount_currency
            elif line.value == "fixed":
                # Fixed amounts
                line_amount = line.compute_line_amount(
                    total_amount_currency,
                    remaining_amount_currency,
                    precision_digits,
                )
                company_line_amount = line.compute_line_amount(
                    total_amount,
                    remaining_amount,
                    company_precision_digits,
                )
                term_vals["company_amount"] = sign * company_line_amount
                term_vals["foreign_amount"] = sign * line_amount
            elif line.value == "percent_amount_untaxed":
                if company_currency != currency:
                    raise UserError(
                        self.env._(
                            "Percentage of amount untaxed can't be used with foreign "
                            "currencies"
                        )
                    )
                line_amount = line.compute_line_amount(
                    untaxed_amount_currency,
                    untaxed_amount_currency,
                    precision_digits,
                )
                company_line_amount = line.compute_line_amount(
                    untaxed_amount,
                    untaxed_amount,
                    company_precision_digits,
                )
                term_vals["company_amount"] = company_line_amount
                term_vals["foreign_amount"] = line_amount
            else:
                # Percentage amounts
                line_amount = line.compute_line_amount(
                    total_amount_currency,
                    remaining_amount_currency,
                    precision_digits,
                )
                company_line_amount = line.compute_line_amount(
                    total_amount,
                    remaining_amount,
                    company_precision_digits,
                )
                term_vals["company_amount"] = company_line_amount
                term_vals["foreign_amount"] = line_amount

            residual_amount -= term_vals["company_amount"]
            residual_amount_currency -= term_vals["foreign_amount"]
            pay_term["line_ids"].append(term_vals)

        return pay_term
