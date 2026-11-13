# -*- coding: utf-8 -*-
from odoo import fields, models

from .account_move import DUE_DATE_CTX


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    def action_confirm(self):
        # Le scritture sono create dentro il metodo standard: la data viene
        # sostituita in account.move.create grazie al contesto.
        return super(AccountLoan, self.with_context(**{DUE_DATE_CTX: True})).action_confirm()

    def action_abc_realign_move_dates(self):
        """Ridata alla scadenza della rata le scritture gia' generate dal prestito."""
        Move = self.env['account.move']
        to_redate = Move
        skipped = Move
        for move in self.line_ids.generated_move_ids:
            due_date = move.generating_loan_line_id.date
            if move.state == 'cancel' or move.date == due_date:
                continue
            lock_date = move.company_id._get_user_fiscal_lock_date(move.journal_id)
            if (
                move.inalterable_hash
                or due_date <= lock_date
                or (move.state == 'posted' and move.date <= lock_date)
            ):
                skipped |= move
            else:
                to_redate |= move

        posted = to_redate.filtered(lambda m: m.state == 'posted')
        # Come in account_loans.action_confirm, lo storno va confermato senza
        # reversed_entry_id, altrimenti _post lo riconcilierebbe con la
        # riclassificazione: il collegamento viene ripristinato dopo la conferma.
        reversed_entries = {move: move.reversed_entry_id for move in posted if move.reversed_entry_id}
        posted.button_draft()
        for due_date, moves in to_redate.grouped(lambda m: m.generating_loan_line_id.date).items():
            moves.date = due_date
        # Il numero di una scrittura gia' confermata resta legato al mese della
        # vecchia data: se il mese cambia va azzerato, la conferma ne assegna uno nuovo.
        to_redate.filtered(lambda m: m.posted_before and not m._sequence_matches_date()).name = False
        Move.union(*reversed_entries).reversed_entry_id = False
        # _post(soft=False) rifiuta le scritture future con auto_post attivo:
        # erano gia' confermate, quindi lo si sospende solo per la riconferma.
        today = fields.Date.context_today(self)
        future = posted.filtered(lambda m: m.auto_post != 'no' and m.date > today)
        future_auto_post = future.grouped('auto_post')
        future.auto_post = 'no'
        posted._post(soft=False)
        for auto_post, moves in future_auto_post.items():
            moves.auto_post = auto_post
        for move, reversed_entry in reversed_entries.items():
            move.reversed_entry_id = reversed_entry

        for loan, moves in to_redate.grouped('loan_id').items():
            loan.message_post(body=self.env._(
                "Date di %(count)s scritture riallineate alla scadenza della rata.",
                count=len(moves),
            ))

        if skipped:
            message = self.env._(
                "%(count)s scritture riallineate. Non modificate perché in periodo bloccato o protette da hash: %(names)s",
                count=len(to_redate),
                names=", ".join(skipped.mapped('display_name')),
            )
        else:
            message = self.env._("%(count)s scritture riallineate alla scadenza della rata.", count=len(to_redate))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._("Riallineamento date prestito"),
                'message': message,
                'type': 'warning' if skipped else 'success',
                'sticky': bool(skipped),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
