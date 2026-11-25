import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AbcWithholdingPayment(models.Model):
    _name = "abc.withholding.payment"
    _description = "Versamento F24 ritenute"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Numero", default="/", copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True,
                                 default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Date(string="Data versamento", required=True, default=fields.Date.context_today, tracking=True)
    period = fields.Char(string="Mese di riferimento (AAAA-MM)", tracking=True)
    line_ids = fields.One2many("abc.withholding.line", "payment_id", string="Quote versate")
    tribute_ids = fields.One2many("abc.withholding.payment.tribute", "payment_id", string="Righe F24")
    amount_withholding = fields.Monetary(string="Ritenute", compute="_compute_totals", store=True)
    amount_penalty = fields.Monetary(string="Sanzioni", compute="_compute_totals", store=True)
    amount_interest = fields.Monetary(string="Interessi", compute="_compute_totals", store=True)
    amount_total = fields.Monetary(string="Totale a debito", compute="_compute_totals", store=True)
    compensation_ids = fields.One2many(
        "abc.withholding.payment.compensation", "payment_id", string="Compensazioni",
        help="Crediti erariali usati in compensazione nello stesso F24 (righe a credito).")
    amount_compensated = fields.Monetary(string="Compensato con crediti", compute="_compute_totals", store=True)
    amount_to_pay = fields.Monetary(
        string="Saldo F24 da pagare", compute="_compute_totals", store=True,
        help="Totale a debito meno le compensazioni: e' l'addebito in banca, anche zero.")
    journal_id = fields.Many2one(
        "account.journal", string="Registro della scrittura F24", check_company=True,
        compute="_compute_journal_id", store=True, readonly=False, precompute=True,
        domain="[('type', 'in', ('bank', 'cash', 'credit', 'general'))]",
        help="Per \"Registra scrittura F24\": registro banca da cui si paga il saldo (oppure un registro "
             "varie se l'F24 e' tutto in compensazione).")
    state = fields.Selection(
        [("draft", "Bozza"), ("confirmed", "Confermato"), ("cancelled", "Annullato")],
        string="Stato", default="draft", required=True, tracking=True, copy=False)
    bank_move_id = fields.Many2one(
        "account.move", string="Scrittura F24", check_company=True, copy=False, tracking=True,
        help="Scrittura che chiude il debito verso l'Erario: l'addebito F24 in banca, anche con "
             "compensazioni, registrata a mano o con \"Registra scrittura F24\".")
    auto = fields.Boolean(
        string="Da riconciliazione bancaria", readonly=True, copy=False,
        help="Creato in automatico quando l'addebito F24 e' stato riconciliato con il debito verso l'Erario.")
    historical = fields.Boolean(string="Versamento storico", readonly=True,
                                help="Creato dalla ricostruzione dello storico (D6).")
    receipt = fields.Binary(string="Quietanza F24", attachment=True)
    receipt_name = fields.Char(string="Nome file quietanza")
    missing_receipt = fields.Boolean(string="Senza quietanza", compute="_compute_missing_receipt", store=True)
    is_late = fields.Boolean(string="Con ravvedimento", compute="_compute_is_late", store=True)
    note = fields.Text(string="Note")

    @api.depends("line_ids.amount", "tribute_ids.penalty", "tribute_ids.interest", "compensation_ids.amount")
    def _compute_totals(self):
        for rec in self:
            rec.amount_withholding = sum(rec.line_ids.mapped("amount"))
            rec.amount_penalty = sum(rec.tribute_ids.mapped("penalty"))
            rec.amount_interest = sum(rec.tribute_ids.mapped("interest"))
            rec.amount_total = rec.amount_withholding + rec.amount_penalty + rec.amount_interest
            rec.amount_compensated = sum(rec.compensation_ids.mapped("amount"))
            rec.amount_to_pay = rec.amount_total - rec.amount_compensated

    f24_move_generated = fields.Boolean(string="Scrittura F24 creata dal modulo", readonly=True, copy=False)

    @api.depends("company_id")
    def _compute_journal_id(self):
        for rec in self:
            if not rec.journal_id or rec.journal_id.company_id != rec.company_id:
                rec.journal_id = rec.company_id.abc_wh_f24_journal_id

    @api.depends("receipt")
    def _compute_missing_receipt(self):
        for rec in self:
            rec.missing_receipt = not rec.receipt

    @api.depends("date", "line_ids.date_due")
    def _compute_is_late(self):
        for rec in self:
            rec.is_late = bool(rec.date) and any(l.date_due and rec.date > l.date_due for l in rec.line_ids)

    # ------------------------------------------------------------------
    def action_compute_tributes(self):
        """Ricalcola le righe F24 per codice tributo e anno, conservando sanzioni e interessi."""
        for rec in self.filtered(lambda r: r.state == "draft" or r.auto):
            missing = rec.line_ids.filtered(lambda l: not l.tributo_code)
            if missing and not self.env.context.get("abc_wh_auto"):
                raise UserError(self.env._(
                    "Quote senza codice tributo: %s. Impostarlo sulla ritenuta o nella tabella "
                    "causali e codici tributo.", ", ".join(missing.move_id.mapped("name"))))
            groups = defaultdict(float)
            for line in rec.line_ids:
                groups[(line.tributo_code or "", line.payment_year)] += line.amount
            old = {(t.tributo_code, t.year): t for t in rec.tribute_ids}
            commands = []
            for key, amount in sorted(groups.items()):
                if key in old:
                    commands.append(Command.update(old.pop(key).id, {"amount": amount}))
                else:
                    commands.append(Command.create({"tributo_code": key[0], "year": key[1], "amount": amount}))
            commands += [Command.delete(t.id) for t in old.values()]
            rec.tribute_ids = commands
        return True

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.line_ids:
                raise UserError(self.env._("Il versamento non contiene quote."))
            not_due = rec.line_ids.filtered(lambda l: l.state != "due")
            if not_due:
                raise UserError(self.env._("Alcune quote non sono piu' dovute: %s", ", ".join(not_due.move_id.mapped("name"))))
            rec.action_compute_tributes()
            rec._abc_assign_name()
            rec.line_ids.write({"state": "paid"})
            rec.state = "confirmed"
            if rec.bank_move_id and not rec.auto:
                rec._abc_reconcile_f24_move()
            if not rec.receipt:
                rec.message_post(body=self.env._(
                    "Versamento confermato senza quietanza F24: allegarla appena disponibile."))
        return True

    def action_create_f24_move(self):
        """Registra l'F24: Dare debiti erariali (+ sanzioni e interessi), Avere crediti compensati e banca.

        Poi conferma il versamento. In alternativa la scrittura si registra a mano e si collega.
        """
        for rec in self:
            if rec.state != "draft" or rec.bank_move_id:
                raise UserError(self.env._(
                    "Il versamento del %s ha gia' una scrittura F24 o non e' in bozza.", rec.date.strftime("%d/%m/%Y")))
            if not rec.line_ids:
                raise UserError(self.env._("Il versamento non contiene quote."))
            not_due = rec.line_ids.filtered(lambda l: l.state != "due")
            if not_due:
                raise UserError(self.env._("Alcune quote non sono piu' dovute: %s", ", ".join(not_due.move_id.mapped("name"))))
            missing = rec.line_ids.filtered("transfer_missing")
            if missing:
                raise UserError(self.env._(
                    "Per queste fatture la scrittura della ritenuta non e' stata registrata, quindi il debito "
                    "verso l'Erario non esiste ancora: %s. Configurare il registro varie e rifare la "
                    "riconciliazione del pagamento.", ", ".join(missing.move_id.mapped("name"))))
            rec.action_compute_tributes()
            rec.write({"bank_move_id": rec._abc_create_f24_move().id, "f24_move_generated": True})
            rec.action_confirm()
        return True

    def _abc_reconcile_f24_move(self):
        """Chiude le righe del debito verso l'Erario con la scrittura F24 (registrata dal modulo o a mano)."""
        for rec in self:
            erario = rec.line_ids._abc_erario_lines()
            for account in erario.account_id.filtered("reconcile"):
                lines = (rec.bank_move_id.line_ids | erario).filtered(
                    lambda l: l.account_id == account and not l.reconciled and l.parent_state == "posted")
                if lines.filtered(lambda l: l.debit) and lines.filtered(lambda l: l.credit):
                    lines.with_context(abc_wh_skip=True).reconcile()

    def _abc_create_f24_move(self):
        self.ensure_one()
        company = self.company_id
        journal = self.journal_id
        if not journal:
            raise UserError(self.env._("Indicare il registro della scrittura F24."))
        if self.currency_id.compare_amounts(self.amount_to_pay, 0.0) < 0:
            raise UserError(self.env._("Le compensazioni superano il totale a debito dell'F24."))
        label = self.env._("Versamento F24 ritenute del %s", self.date.strftime("%d/%m/%Y"))
        debits = defaultdict(float)
        for line in self.line_ids:
            account = line.withholding_id.final_account_id
            if not account:
                raise UserError(self.env._("Ritenuta %s senza conto erariale.", line.move_id.name))
            debits[account] += line.amount
        for amount, account, what in ((self.amount_penalty, company.abc_wh_penalty_account_id, "sanzioni"),
                                      (self.amount_interest, company.abc_wh_interest_account_id, "interessi")):
            if self.currency_id.is_zero(amount):
                continue
            if not account:
                raise UserError(self.env._("Configurare nell'azienda il conto %s da ravvedimento.", what))
            debits[account] += amount
        commands = []
        for account, amount in debits.items():
            if self.currency_id.is_zero(amount):
                continue
            commands.append(Command.create({
                "account_id": account.id, "name": label,
                "debit": max(amount, 0.0), "credit": max(-amount, 0.0),
            }))
        for comp in self.compensation_ids:
            commands.append(Command.create({
                "account_id": comp.account_id.id,
                "name": "%s - compensazione %s %s" % (label, comp.tributo_code or "", comp.year or ""),
                "debit": 0.0, "credit": comp.amount,
            }))
        if journal.currency_id and journal.currency_id != company.currency_id:
            raise UserError(self.env._("Il registro della scrittura F24 deve essere in euro."))
        if not self.currency_id.is_zero(self.amount_to_pay):
            if journal.type not in ("bank", "cash", "credit"):
                raise UserError(self.env._(
                    "C'e' un saldo da pagare di %.2f euro: usare un registro banca.", self.amount_to_pay))
            # Conto dei pagamenti in sospeso, se c'e': l'addebito dell'estratto conto si abbina a questa riga
            bank_account = (journal.outbound_payment_method_line_ids.payment_account_id[:1]
                            or company.account_journal_payment_credit_account_id
                            or journal.default_account_id)
            if not bank_account:
                raise UserError(self.env._("Il registro %s non ha un conto predefinito.", journal.name))
            commands.append(Command.create({
                "account_id": bank_account.id, "name": label, "debit": 0.0, "credit": self.amount_to_pay,
            }))
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": company.id,
            "date": self.date,
            "ref": label,
            "line_ids": commands,
        })
        move.action_post()
        return move

    def _abc_release_f24_move(self):
        """Annullo del versamento: riapre il debito verso l'Erario e storna la scrittura creata dal modulo."""
        today = fields.Date.context_today(self)
        for rec in self.filtered("bank_move_id"):
            move = rec.bank_move_id
            erario_accounts = rec.line_ids._abc_erario_lines().account_id
            move.line_ids.filtered(lambda l: l.account_id in erario_accounts).with_context(
                abc_wh_skip=True).remove_move_reconcile()
            if rec.f24_move_generated and move.state == "posted":
                move.line_ids.with_context(abc_wh_skip=True).remove_move_reconcile()
                move.with_context(abc_wh_skip=True)._reverse_moves(
                    [{"date": today, "ref": self.env._("Annullo %s", move.ref or "")}], cancel=True)
            else:
                rec.message_post(body=self.env._(
                    "Versamento annullato: la scrittura F24 %s non e' stata toccata e non e' piu' collegata.",
                    move.display_name))
            rec.write({"bank_move_id": False, "f24_move_generated": False})

    def _abc_assign_name(self):
        for rec in self.filtered(lambda r: r.name == "/"):
            rec.name = self.env["ir.sequence"].with_company(rec.company_id).next_by_code(
                "abc.withholding.payment") or "/"

    def _abc_refresh_auto(self):
        """Versamento nato dalla riconciliazione bancaria: righe F24 e stato sempre allineati."""
        for rec in self:
            # Restano nel versamento solo le quote chiuse dall'addebito F24
            rec.line_ids.filtered(lambda l: l.state == "due").write({"payment_id": False})
            rec.action_compute_tributes()
            rec._abc_assign_name()
            if rec.state != "confirmed":
                rec.state = "confirmed"
                rec.message_post(body=self.env._(
                    "Versamento registrato dalla riconciliazione bancaria dell'F24 (%s).",
                    rec.bank_move_id.display_name))

    def action_cancel(self):
        for rec in self:
            if rec.auto and rec.state == "confirmed":
                raise UserError(self.env._(
                    "Il versamento %s nasce dalla riconciliazione bancaria: per annullarlo togliere "
                    "la riconciliazione dell'addebito F24 in banca.", rec.name))
            if rec.state == "confirmed":
                rec._abc_release_f24_move()
            rec.line_ids.filtered(lambda l: l.state == "paid").write({"state": "due"})
            rec.state = "cancelled"
        return True

    def action_draft(self):
        self.filtered(lambda r: r.state == "cancelled").write({"state": "draft"})
        return True

    def unlink(self):
        if self.filtered(lambda r: r.state == "confirmed"):
            raise UserError(self.env._("Annullare il versamento prima di eliminarlo."))
        self.line_ids.write({"payment_id": False})
        return super().unlink()

    # ------------------------------------------------------------------
    # Export Excel del riepilogo F24 (D20)
    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy"})

        sheet = workbook.add_worksheet("Riepilogo F24")
        sheet.write_row(0, 0, ["Codice tributo", "Anno di riferimento", "Ritenute", "Interessi", "Sanzioni", "Totale"], bold)
        for row, trib in enumerate(self.tribute_ids, start=1):
            sheet.write(row, 0, trib.tributo_code)
            sheet.write(row, 1, trib.year)
            sheet.write(row, 2, trib.amount, money)
            sheet.write(row, 3, trib.interest, money)
            sheet.write(row, 4, trib.penalty, money)
            sheet.write(row, 5, trib.amount + trib.interest + trib.penalty, money)
        row = len(self.tribute_ids) + 2
        sheet.write(row, 0, "Righe F24 da compilare", bold)
        sheet.write_row(row + 1, 0, ["Codice tributo", "Anno di riferimento", "Importo a debito"], bold)
        row += 2
        for trib in self.tribute_ids:
            sheet.write(row, 0, trib.tributo_code)
            sheet.write(row, 1, trib.year)
            sheet.write(row, 2, trib.amount, money)
            row += 1
        company = self.company_id
        for code, attr in ((company.abc_wh_penalty_code, "penalty"), (company.abc_wh_interest_code, "interest")):
            for trib in self.tribute_ids.filtered(lambda t: t[attr]):
                sheet.write(row, 0, code or "")
                sheet.write(row, 1, trib.year)
                sheet.write(row, 2, trib[attr], money)
                row += 1
        sheet.write(row, 1, "Totale a debito", bold)
        sheet.write(row, 2, self.amount_total, money)
        if self.compensation_ids:
            row += 2
            sheet.write(row, 0, "Compensazioni (importi a credito)", bold)
            sheet.write_row(row + 1, 0, ["Codice tributo", "Anno di riferimento", "Importo a credito", "Conto"], bold)
            row += 2
            for comp in self.compensation_ids:
                sheet.write(row, 0, comp.tributo_code or "")
                sheet.write(row, 1, comp.year or "")
                sheet.write(row, 2, comp.amount, money)
                sheet.write(row, 3, comp.account_id.display_name or "")
                row += 1
            sheet.write(row, 1, "Totale a credito", bold)
            sheet.write(row, 2, self.amount_compensated, money)
        row += 2
        sheet.write(row, 1, "Saldo F24 da pagare", bold)
        sheet.write(row, 2, self.amount_to_pay, money)
        sheet.set_column(0, 5, 18)

        detail = workbook.add_worksheet("Dettaglio fatture")
        headers = ["Fornitore", "Codice fiscale", "Fattura", "Data fattura", "Data pagamento",
                   "Mese", "Scadenza", "Codice tributo", "Causale", "Imponibile", "Ritenuta"]
        detail.write_row(0, 0, headers, bold)
        for row, line in enumerate(self.line_ids.sorted(lambda l: (l.tributo_code or "", l.payment_date)), start=1):
            detail.write(row, 0, line.partner_id.name or "")
            detail.write(row, 1, line.partner_fiscalcode or "")
            detail.write(row, 2, line.move_id.name or "")
            detail.write_datetime(row, 3, fields.Datetime.to_datetime(line.invoice_date), date_fmt) if line.invoice_date else None
            detail.write_datetime(row, 4, fields.Datetime.to_datetime(line.payment_date), date_fmt)
            detail.write(row, 5, line.period or "")
            detail.write_datetime(row, 6, fields.Datetime.to_datetime(line.date_due), date_fmt) if line.date_due else None
            detail.write(row, 7, line.tributo_code or "")
            detail.write(row, 8, line.reason or "")
            detail.write(row, 9, line.base_amount, money)
            detail.write(row, 10, line.amount, money)
        detail.set_column(0, 10, 16)
        workbook.close()
        return self._abc_download(output.getvalue(), "F24_ritenute_%s.xlsx" % (self.name or self.id))

    def _abc_download(self, content, filename):
        # sudo: chi ha solo la consultazione deve poter esportare
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }


class AbcWithholdingPaymentCompensation(models.Model):
    _name = "abc.withholding.payment.compensation"
    _description = "Credito usato in compensazione nell'F24 ritenute"
    _order = "id"
    _check_company_auto = True

    @api.constrains("amount")
    def _check_amount(self):
        if any(c.currency_id.compare_amounts(c.amount, 0.0) <= 0 for c in self):
            raise ValidationError(self.env._("L'importo compensato deve essere maggiore di zero."))

    payment_id = fields.Many2one("abc.withholding.payment", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="payment_id.company_id")
    currency_id = fields.Many2one(related="payment_id.currency_id")
    account_id = fields.Many2one(
        "account.account", string="Conto del credito", required=True, check_company=True,
        help="Es. Credito IVA, Credito d'imposta ZES: e' il conto che la scrittura F24 accredita.")
    tributo_code = fields.Char(string="Codice tributo del credito", help="Es. 6099 per il credito IVA annuale.")
    year = fields.Integer(string="Anno di riferimento")
    amount = fields.Monetary(string="Importo a credito", required=True)
    note = fields.Char(string="Note")


class AbcWithholdingPaymentTribute(models.Model):
    _name = "abc.withholding.payment.tribute"
    _description = "Riga F24 del versamento ritenute"
    _order = "tributo_code, year"

    payment_id = fields.Many2one("abc.withholding.payment", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="payment_id.currency_id")
    tributo_code = fields.Char(string="Codice tributo", required=True)
    year = fields.Integer(string="Anno di riferimento", required=True)
    amount = fields.Monetary(string="Ritenute")
    interest = fields.Monetary(string="Interessi da ravvedimento")
    penalty = fields.Monetary(string="Sanzioni da ravvedimento")
