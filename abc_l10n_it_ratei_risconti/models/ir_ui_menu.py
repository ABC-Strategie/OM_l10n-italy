# -*- coding: utf-8 -*-
from odoo import models

NATIVE_DEFERRED_MENUS = (
    'account_reports.menu_action_account_report_deferred_expense',
    'account_reports.menu_action_account_report_deferred_revenue',
)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        """Nasconde i menu nativi dei differimenti: li sostituisce questo modulo.
        Resta valido anche dopo un aggiornamento di account_reports."""
        res = super()._load_menus_blacklist()
        for xmlid in NATIVE_DEFERRED_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                res.append(menu.id)
        return res
