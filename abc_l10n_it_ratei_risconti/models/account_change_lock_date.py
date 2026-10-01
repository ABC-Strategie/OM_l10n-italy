# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountChangeLockDate(models.TransientModel):
    _inherit = 'account.change.lock.date'

    @api.onchange('fiscalyear_lock_date', 'hard_lock_date')
    def _onchange_abc_rr_lock_date(self):
        """Solo avviso, mai blocco: segnala ratei e risconti non ancora elaborati."""
        dates = [d for d in (self.fiscalyear_lock_date, self.hard_lock_date) if d]
        if not dates:
            return
        company = self.company_id or self.env.company
        lock = max(dates)
        closing = company._abc_rr_closing_date(lock)
        if closing != lock:
            # blocco a meta' esercizio: si controlla la chiusura precedente
            date_from = fields.Date.to_date(company.compute_fiscalyear_dates(lock)['date_from'])
            closing = date_from - relativedelta(days=1)
        pending = self.env['abc.rr.run']._pending_sources_count(company, closing)
        if pending:
            return {'warning': {
                'title': self.env._("Ratei e risconti"),
                'message': self.env._(
                    "Ci sono %(n)s righe o schede con competenza a cavallo del %(date)s non ancora "
                    "elaborate. La data di blocco viene comunque salvata.",
                    n=pending, date=closing.strftime('%d/%m/%Y')),
                'type': 'notification',
            }}
