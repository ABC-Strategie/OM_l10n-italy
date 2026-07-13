# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.orm.domains import Domain
from odoo.addons.account_tax_balance.models.account_tax import AccountTax as AccountTaxBalance

class CompatibleDomain(list):
    def __init__(self, iterable=None):
        if iterable is not None:
            super().__init__(list(iterable) if isinstance(iterable, Domain) else iterable)
        else:
            super().__init__()

    def __and__(self, other):
        return CompatibleDomain(Domain(self) & Domain(other))

    def __rand__(self, other):
        return CompatibleDomain(Domain(other) & Domain(self))

    def __or__(self, other):
        return CompatibleDomain(Domain(self) | Domain(other))

    def __ror__(self, other):
        return CompatibleDomain(Domain(other) | Domain(self))

    def __iand__(self, other):
        res = Domain(self) & Domain(other)
        self.clear()
        self.extend(res)
        return self

    def __ior__(self, other):
        res = Domain(self) | Domain(other)
        self.clear()
        self.extend(res)
        return self


# Monkeypatch the methods of AccountTax defined in account_tax_balance

orig_get_balance_domain = AccountTaxBalance.get_balance_domain
def new_get_balance_domain(self, *args, **kwargs):
    res = orig_get_balance_domain(self, *args, **kwargs)
    return CompatibleDomain(res)
AccountTaxBalance.get_balance_domain = new_get_balance_domain


orig_get_base_balance_domain = AccountTaxBalance.get_base_balance_domain
def new_get_base_balance_domain(self, *args, **kwargs):
    res = orig_get_base_balance_domain(self, *args, **kwargs)
    return CompatibleDomain(res)
AccountTaxBalance.get_base_balance_domain = new_get_base_balance_domain


orig_get_move_lines_domain = AccountTaxBalance.get_move_lines_domain
def new_get_move_lines_domain(self, *args, **kwargs):
    res = orig_get_move_lines_domain(self, *args, **kwargs)
    return CompatibleDomain(res)
AccountTaxBalance.get_move_lines_domain = new_get_move_lines_domain


orig_get_move_line_partial_domain = AccountTaxBalance.get_move_line_partial_domain
def new_get_move_line_partial_domain(self, *args, **kwargs):
    res = orig_get_move_line_partial_domain(self, *args, **kwargs)
    return CompatibleDomain(res)
AccountTaxBalance.get_move_line_partial_domain = new_get_move_line_partial_domain


class AccountTax(models.Model):
    _inherit = "account.tax"
