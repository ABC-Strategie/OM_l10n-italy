from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from .date_utils import period_of, withholding_due_date
from .withholding import CYCLES, REFUND_TYPES

LINE_STATES = [
    ("due", "Dovuta"),
    ("paid", "Versata"),
    ("suffered", "Subita"),
    ("certified", "Certificata"),
    ("deducted", "Scomputata"),
    ("not_operated", "Non operata"),
    ("offset", "Compensata con nota di credito"),
]
LOCKED_STATES = ("paid", "certified", "deducted")


class AbcWithholdingLine(models.Model):
    _name = "abc.withholding.line"
    _description = "Quota di ritenuta (per pagamento o incasso)"
    _order = "payment_date desc, id desc"

    @api.depends("move_id.name", "payment_date")
    def _compute_display_name(self):
        for line in self:
            date = line.payment_date.strftime("%d/%m/%Y") if line.payment_date else ""
            line.display_name = "%s - %s" % (line.move_id.name or "", date)

    withholding_id = fields.Many2one(
        "abc.withholding", string="Ritenuta", required=True, ondelete="cascade", index=True)
    cycle = fields.Selection(CYCLES, related="withholding_id.cycle", store=True, string="Ciclo")
    company_id = fields.Many2one(related="withholding_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="withholding_id.currency_id")
    partner_id = fields.Many2one(related="withholding_id.partner_id", store=True, string="Fornitore / Cliente")
    partner_fiscalcode = fields.Char(related="withholding_id.partner_fiscalcode")
    move_id = fields.Many2one(related="withholding_id.move_id", store=True, string="Fattura")
    invoice_date = fields.Date(related="withholding_id.invoice_date", store=True)
    invoice_ref = fields.Char(related="withholding_id.invoice_ref")
    tributo_code = fields.Char(related="withholding_id.tributo_code", store=True, string="Codice tributo")
    reason = fields.Char(related="withholding_id.reason", store=True, string="Causale")
    withholding_type = fields.Char(related="withholding_id.withholding_type", store=True, string="Tipo (RT)")
    rate = fields.Float(related="withholding_id.rate", string="Aliquota %")
    is_contribution = fields.Boolean(related="withholding_id.is_contribution", store=True)
    is_final = fields.Boolean(related="withholding_id.is_final", store=True)
    kind = fields.Selection(
        [("payment", "Pagamento / incasso"), ("offset", "Nota di credito")],
        string="Origine", required=True, default="payment")
    partial_id = fields.Many2one("account.partial.reconcile", string="Riconciliazione", ondelete="set null", index=True)
    counterpart_move_id = fields.Many2one("account.move", string="Pagamento / contropartita")
    payment_date = fields.Date(string="Data pagamento / incasso", required=True, index=True)
    paid_amount = fields.Monetary(string="Importo pagato / incassato")
    amount = fields.Monetary(string="Quota ritenuta")
    base_amount = fields.Monetary(string="Imponibile della quota")
    n1_amount = fields.Monetary(string="Spese non soggette della quota")
    period = fields.Char(string="Mese di competenza", compute="_compute_dates", store=True, index=True)
    payment_year = fields.Integer(string="Anno del pagamento", compute="_compute_dates", store=True, index=True)
    date_due = fields.Date(string="Scadenza versamento", compute="_compute_dates", store=True, index=True)
    fiscal_year = fields.Integer(string="Anno fiscale del credito", index=True)
    state = fields.Selection(LINE_STATES, string="Stato", required=True, index=True)
    state_label = fields.Char(string="Descrizione stato", compute="_compute_state_label")
    transfer_move_id = fields.Many2one(
        "account.move", string="Scrittura ritenuta", readonly=True, index=True,
        help="Scrittura nel registro varie che storna la ritenuta dal fornitore/cliente verso l'Erario.")
    transfer_missing = fields.Boolean(string="Scrittura ritenuta non creata")
    payment_id = fields.Many2one("abc.withholding.payment", string="Versamento F24", ondelete="set null", index=True)
    payment_doc_date = fields.Date(related="payment_id.date", string="Data versamento", store=True)
    cu_received_id = fields.Many2one("abc.withholding.cu.received", string="CU ricevuta", ondelete="set null")
    deduction_year = fields.Integer(string="Dichiarazione dell'anno")
    historical = fields.Boolean(string="Da storico")
    is_overdue = fields.Boolean(string="Scaduta", compute="_compute_overdue", search="_search_is_overdue")
    days_to_due = fields.Integer(string="Giorni alla scadenza", compute="_compute_overdue")

    @api.depends("payment_date", "cycle")
    def _compute_dates(self):
        for line in self:
            if not line.payment_date:
                line.period = False
                line.payment_year = 0
                line.date_due = False
                continue
            line.period = period_of(line.payment_date)
            line.payment_year = line.payment_date.year
            line.date_due = withholding_due_date(line.payment_date) if line.cycle == "passive" else False

    @api.depends("state")
    def _compute_state_label(self):
        labels = dict(LINE_STATES)
        for line in self:
            label = labels.get(line.state, "")
            line.state_label = "Scaduta" if line.is_overdue else label

    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.cycle == "passive" and line.state == "due" and line.date_due:
                line.days_to_due = (line.date_due - today).days
                line.is_overdue = line.date_due < today
            else:
                line.days_to_due = 0
                line.is_overdue = False

    def _search_is_overdue(self, operator, value):
        # In Odoo 19 i domini arrivano normalizzati: ('is_overdue', 'in', {True})
        if operator not in ("in", "not in"):
            return NotImplemented
        today = fields.Date.context_today(self)
        domain = Domain([("cycle", "=", "passive"), ("state", "=", "due"), ("date_due", "<", today)])
        positive = (operator == "in") == (True in value)
        return domain if positive else ~domain

    # ------------------------------------------------------------------
    # Scrittura della ritenuta al pagamento (schema OCA, D2)
    #   passivo: Dare fornitore / Avere Erario c/ritenute da versare (o Debiti v/ENASARCO)
    #   attivo:  Dare Erario c/ritenute subite / Avere cliente
    # La riga sul fornitore/cliente si riconcilia con la riga ritenuta della fattura.
    # ------------------------------------------------------------------
    def _abc_create_settlement(self):
        for line in self:
            wh = line.withholding_id
            partner_line = wh.partner_line_id
            final = wh.final_account_id
            if not partner_line or not final or line.currency_id.is_zero(line.amount):
                # Imposta non configurata con lo schema del modulo: contabilita' standard di Odoo
                continue
            journal = wh.company_id.abc_wh_journal_id
            if not journal:
                line.transfer_missing = True
                wh.move_id.message_post(body=self.env._(
                    "Scrittura della ritenuta non creata: manca il registro varie delle ritenute "
                    "nella configurazione dell'azienda."))
                continue
            partner_account = partner_line.account_id
            if wh.cycle == "passive":
                debit_account, credit_account = partner_account, final
            else:
                debit_account, credit_account = final, partner_account
            if line.amount < 0:
                debit_account, credit_account = credit_account, debit_account
            amount = abs(line.amount)
            label = self.env._("Ritenuta %(doc)s - pagamento del %(date)s",
                               doc=wh.move_id.name, date=line.payment_date.strftime("%d/%m/%Y"))
            move_date = line.payment_date
            locks = [d for d in (getattr(wh.company_id, "fiscalyear_lock_date", False),
                                 getattr(wh.company_id, "hard_lock_date", False)) if d]
            if locks and move_date <= max(locks):
                # Periodo chiuso: il giroconto va alla data odierna, la quota resta del mese del pagamento
                move_date = fields.Date.context_today(self)
            move = self.env["account.move"].sudo().create({
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": wh.company_id.id,
                "date": move_date,
                "ref": label,
                "line_ids": [
                    Command.create({"account_id": debit_account.id, "partner_id": wh.partner_id.id,
                                    "name": label, "debit": amount, "credit": 0.0}),
                    Command.create({"account_id": credit_account.id, "partner_id": wh.partner_id.id,
                                    "name": label, "debit": 0.0, "credit": amount}),
                ],
            })
            move.action_post()
            line.write({"transfer_move_id": move.id, "transfer_missing": False})
            counter = move.line_ids.filtered(lambda l: l.account_id == partner_account)
            if partner_line.reconciled:
                # La ritenuta e' gia' stata chiusa da un pagamento del lordo
                wh.possible_not_operated = True
                wh.message_post(body=self.env._(
                    "La riga ritenuta risulta gia' pagata: il fornitore/cliente sembra aver ricevuto o "
                    "versato il lordo. Verificare; per il ciclo attivo usare \"Ritenuta non operata\"."))
            else:
                # no_cash_basis: lo storno della ritenuta non e' un pagamento ai fini dell'IVA per cassa
                (counter + partner_line).with_context(abc_wh_skip=True, no_cash_basis=True).reconcile()

    def _abc_erario_lines(self):
        """Righe sul conto erariale delle scritture della ritenuta."""
        lines = self.env["account.move.line"]
        for line in self:
            final = line.withholding_id.final_account_id
            lines |= line.transfer_move_id.line_ids.filtered(lambda l: l.account_id == final)
        return lines

    @api.model
    def _abc_process_bank_partial(self, partial):
        """Riconciliazione bancaria dell'F24 sul conto erariale: le quote risultano versate.

        Le quote chiuse vengono raccolte in un versamento F24 automatico, uno per movimento
        di banca, con la data del movimento.
        """
        sides = partial.debit_move_id | partial.credit_move_id
        lines = self.sudo().search([
            ("transfer_move_id", "in", sides.move_id.ids),
            ("cycle", "=", "passive"),
            ("state", "=", "due"),
            ("is_contribution", "=", False),
            ("tributo_code", "!=", False),
        ])
        for line in lines:
            erario = line._abc_erario_lines()
            if not erario or not all(l.reconciled for l in erario):
                continue
            bank_line = (sides - erario)[:1]
            own_moves = line.transfer_move_id | line.transfer_move_id.reversal_move_ids
            if not bank_line or bank_line.move_id in own_moves:
                continue
            payment = self.env["abc.withholding.payment"].sudo().search([
                ("bank_move_id", "=", bank_line.move_id.id), ("state", "!=", "cancelled")], limit=1)
            if not payment and line.payment_id.state == "draft":
                # Versamento preparato col wizard: lo conferma la riconciliazione bancaria
                payment = line.payment_id
                payment.write({"bank_move_id": bank_line.move_id.id, "auto": True, "date": bank_line.date})
            if not payment:
                payment = self.env["abc.withholding.payment"].sudo().create({
                    "company_id": line.company_id.id,
                    "date": bank_line.date,
                    "period": line.period,
                    "bank_move_id": bank_line.move_id.id,
                    "auto": True,
                })
            line.write({"payment_id": payment.id, "state": "paid"})
            payment.with_context(abc_wh_auto=True)._abc_refresh_auto()

    @api.model
    def _abc_unprocess_bank_partials(self, partials):
        """Annullata la riconciliazione bancaria dell'F24: le quote tornano da versare."""
        sides = partials.debit_move_id | partials.credit_move_id
        lines = self.sudo().search([
            ("transfer_move_id", "in", sides.move_id.ids),
            ("state", "=", "paid"),
            ("payment_id.auto", "=", True),
            ("payment_id.bank_move_id", "in", sides.move_id.ids),
        ])
        payments = lines.payment_id
        lines.write({"state": "due", "payment_id": False})
        for payment in payments:
            if payment.line_ids:
                payment.with_context(abc_wh_auto=True)._abc_refresh_auto()
            else:
                payment.write({"state": "cancelled"})

    def _abc_reverse_transfer(self):
        today = fields.Date.context_today(self)
        for line in self.filtered(lambda l: l.transfer_move_id.state == "posted"):
            # Si riapre prima la riga ritenuta della fattura, poi si storna la scrittura
            line.transfer_move_id.line_ids.sudo().with_context(abc_wh_skip=True).remove_move_reconcile()
            line.transfer_move_id.sudo().with_context(abc_wh_skip=True)._reverse_moves(
                [{"date": today, "ref": self.env._("Storno %s", line.transfer_move_id.ref or "")}],
                cancel=True,
            )
            line.transfer_move_id = False

    # ------------------------------------------------------------------
    # Protezioni
    # ------------------------------------------------------------------
    def _abc_check_removable(self):
        for line in self:
            if line.state in LOCKED_STATES or line.payment_id.state == "confirmed":
                raise UserError(self.env._(
                    "La ritenuta di %(doc)s (pagamento del %(date)s) e' gia' %(state)s: "
                    "annullare prima il versamento, la CU o lo scomputo collegati.",
                    doc=line.move_id.name,
                    date=line.payment_date.strftime("%d/%m/%Y"),
                    state=dict(LINE_STATES).get(line.state, line.state).lower(),
                ))

    def _abc_remove_for_partials(self, partials):
        lines = self.sudo().search([("partial_id", "in", partials.ids)])
        if not lines:
            return
        lines._abc_check_removable()
        lines.write({"payment_id": False})
        lines._abc_reverse_transfer()
        lines.with_context(abc_wh_force_unlink=True).unlink()

    def unlink(self):
        if not self.env.context.get("abc_wh_force_unlink"):
            self._abc_check_removable()
        return super().unlink()

    def action_open_move(self):
        self.ensure_one()
        return self.withholding_id.action_open_move()
