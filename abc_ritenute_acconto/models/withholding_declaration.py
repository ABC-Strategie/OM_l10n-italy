import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .withholding import PASSIVE_TYPES, REFUND_TYPES

DECLARATION_TYPES = [
    ("ordinary", "Ordinaria"),
    ("corrective", "Correttiva nei termini"),
    ("integrative", "Integrativa"),
]


class AbcWithholdingDeclaration(models.Model):
    _name = "abc.withholding.declaration"
    _description = "CU e 770 dell'anno"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc"
    _check_company_auto = True

    name = fields.Char(string="Riferimento", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True,
                                 default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    year = fields.Integer(string="Anno dei pagamenti", required=True,
                          default=lambda self: fields.Date.context_today(self).year - 1, tracking=True)
    declaration_type = fields.Selection(DECLARATION_TYPES, string="Tipo 770", default="ordinary", required=True)
    separate_sending = fields.Boolean(
        string="770 separato dalla parte dipendenti", default=True,
        help="Il quadro dei dipendenti resta al consulente paghe (D55).")
    state = fields.Selection(
        [("draft", "Bozza"), ("checked", "Controllata"), ("confirmed", "Confermata"), ("sent", "Trasmessa")],
        string="Stato", default="draft", required=True, tracking=True, copy=False)
    cu_ids = fields.One2many("abc.withholding.cu", "declaration_id", string="CU per percipiente")
    st_ids = fields.One2many("abc.withholding.st", "declaration_id", string="Quadro ST")
    check_errors = fields.Text(string="Errori bloccanti", readonly=True)
    check_warnings = fields.Text(string="Avvisi", readonly=True)
    total_withheld_cu = fields.Monetary(string="Ritenute nelle CU", compute="_compute_totals")
    total_withheld_st = fields.Monetary(string="Ritenute nel quadro ST", compute="_compute_totals")
    protocol_cu = fields.Char(string="Protocollo invio CU", tracking=True)
    protocol_770 = fields.Char(string="Protocollo invio 770", tracking=True)
    sent_date = fields.Date(string="Data trasmissione", tracking=True)
    receipt_cu = fields.Binary(string="Ricevuta CU", attachment=True)
    receipt_cu_name = fields.Char()
    receipt_770 = fields.Binary(string="Ricevuta 770", attachment=True)
    receipt_770_name = fields.Char()

    @api.depends("year")
    def _compute_name(self):
        for rec in self:
            rec.name = "CU e 770 - pagamenti %s" % (rec.year or "")

    @api.depends("cu_ids.line_ids.withheld_advance", "cu_ids.line_ids.withheld_final", "st_ids.withheld")
    def _compute_totals(self):
        for rec in self:
            cu_lines = rec.cu_ids.filtered(lambda c: c.cu_type != "cancellation").line_ids
            rec.total_withheld_cu = sum(cu_lines.mapped("withheld_advance")) + sum(cu_lines.mapped("withheld_final"))
            rec.total_withheld_st = sum(rec.st_ids.mapped("withheld"))

    # ------------------------------------------------------------------
    # Calcolo
    # ------------------------------------------------------------------
    def _abc_year_lines(self):
        self.ensure_one()
        return self.env["abc.withholding.line"].search([
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", "passive"),
            ("kind", "=", "payment"),
            ("payment_year", "=", self.year),
            ("state", "in", ("due", "paid")),
        ])

    def action_compute(self):
        for rec in self:
            if rec.state not in ("draft", "checked"):
                raise UserError(self.env._("Riportare la dichiarazione in bozza per ricalcolarla."))
            rec.cu_ids.unlink()
            rec.st_ids.unlink()
            lines = rec._abc_year_lines()
            rec._abc_compute_cu(lines)
            rec._abc_compute_st(lines)
            rec.write({"state": "draft", "check_errors": False, "check_warnings": False})
        return True

    def _abc_compute_cu(self, lines):
        groups = defaultdict(lambda: defaultdict(float))
        contributions = defaultdict(float)
        for line in lines:
            if line.is_contribution:
                contributions[line.partner_id] += line.amount
                continue
            key = (line.partner_id, line.reason or "A")
            data = groups[key]
            data["taxable"] += line.base_amount
            data["not_subject"] += line.n1_amount
            if line.is_final:
                data["withheld_final"] += line.amount
            else:
                data["withheld_advance"] += line.amount
        # Fornitori forfettari e minimi: compensi senza ritenuta, da indicare comunque (D58)
        for partner, amount in self._abc_flat_rate_payments().items():
            groups[(partner, "A")]["flat_rate"] += amount
        by_partner = defaultdict(list)
        for (partner, reason), data in groups.items():
            not_subject = data["not_subject"] + data["flat_rate"]
            code = self.company_id.abc_wh_cu_forfettario_code if data["flat_rate"] else self.company_id.abc_wh_cu_n1_code
            by_partner[partner].append(Command.create({
                "reason": reason,
                "gross": data["taxable"] + not_subject,
                "not_subject": not_subject,
                "not_subject_code": code if not_subject else False,
                "taxable": data["taxable"],
                "withheld_advance": data["withheld_advance"],
                "withheld_final": data["withheld_final"],
            }))
        vals_list = []
        for partner, commands in by_partner.items():
            vals_list.append({
                "declaration_id": self.id,
                "partner_id": partner.id,
                "social_contrib": contributions.get(partner, 0.0),
                "line_ids": commands,
            })
        self.env["abc.withholding.cu"].create(vals_list)

    def _abc_flat_rate_payments(self):
        """Pagamenti dell'anno a fornitori forfettari o minimi (nessuna ritenuta in fattura)."""
        self.ensure_one()
        totals = defaultdict(float)
        moves = self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", PASSIVE_TYPES),
            ("state", "=", "posted"),
            ("commercial_partner_id.abc_wh_flat_rate", "=", True),
        ])
        for move in moves:
            sign = -1 if move.move_type in REFUND_TYPES else 1
            for line in move.line_ids.filtered(lambda l: l.display_type == "payment_term"):
                for partial in line.matched_debit_ids | line.matched_credit_ids:
                    counterpart = partial.debit_move_id if partial.credit_move_id == line else partial.credit_move_id
                    if counterpart.move_id.move_type in PASSIVE_TYPES:
                        continue
                    if counterpart.date and counterpart.date.year == self.year:
                        totals[move.commercial_partner_id] += sign * partial.amount
        return totals

    def _abc_compute_st(self, lines):
        groups = defaultdict(lambda: {"withheld": 0.0, "paid": 0.0, "dates": set(), "late": False, "payments": set()})
        for line in lines.filtered(lambda l: not l.is_contribution):
            data = groups[(line.period, line.tributo_code or "")]
            data["withheld"] += line.amount
            if line.state == "paid":
                data["paid"] += line.amount
                if line.payment_id:
                    data["dates"].add(line.payment_id.date)
                    data["payments"].add(line.payment_id)
                    if line.date_due and line.payment_id.date > line.date_due:
                        data["late"] = True
        used_tributes = set()
        vals_list = []
        for (period, code), data in sorted(groups.items()):
            interest = penalty = 0.0
            for payment in data["payments"]:
                for trib in payment.tribute_ids.filtered(lambda t: t.tributo_code == code):
                    if trib.id in used_tributes:
                        continue
                    used_tributes.add(trib.id)
                    interest += trib.interest
                    penalty += trib.penalty
            vals_list.append({
                "declaration_id": self.id,
                "period": period,
                "tributo_code": code,
                "withheld": data["withheld"],
                "paid": data["paid"],
                "interest": interest,
                "penalty": penalty,
                "payment_date": max(data["dates"]) if data["dates"] else False,
                "late": data["late"],
            })
        self.env["abc.withholding.st"].create(vals_list)

    # ------------------------------------------------------------------
    # Controlli (8.6, D33)
    # ------------------------------------------------------------------
    def action_check(self):
        for rec in self:
            errors, warnings = rec._abc_checks()
            rec.write({
                "check_errors": "\n".join(errors) or False,
                "check_warnings": "\n".join(warnings) or False,
                "state": "checked" if not errors else "draft",
            })
        return True

    def _abc_checks(self):
        self.ensure_one()
        errors, warnings = [], []
        company = self.company_id
        for label, value in ((self.env._("firmatario"), company.abc_wh_signer_name),
                             (self.env._("codice fiscale del firmatario"), company.abc_wh_signer_fiscalcode),
                             (self.env._("codice carica del firmatario"), company.abc_wh_signer_role_code),
                             (self.env._("codice attivita'"), company.abc_wh_ateco_code)):
            if not value:
                errors.append(self.env._("Azienda: manca %s.", label))
        for cu in self.cu_ids:
            partner = cu.partner_id
            fiscal = (partner.l10n_it_codice_fiscale or "").strip().upper()
            name = partner.name
            if not fiscal:
                if partner.abc_wh_non_resident:
                    warnings.append(self.env._("%s: non residente senza codice fiscale italiano, indicare l'identificativo estero.", name))
                else:
                    errors.append(self.env._("%s: manca il codice fiscale.", name))
            elif len(fiscal) not in (11, 16):
                errors.append(self.env._("%(name)s: codice fiscale non valido (%(cf)s).", name=name, cf=fiscal))
            if not (partner.street and partner.zip and partner.city):
                errors.append(self.env._("%s: domicilio fiscale incompleto (indirizzo, CAP, comune).", name))
            if len(fiscal) == 16 and not (partner.abc_wh_birth_date and partner.abc_wh_birth_city and partner.abc_wh_gender):
                errors.append(self.env._("%s: persona fisica senza data, comune di nascita o sesso.", name))
            for line in cu.line_ids:
                if not line.reason:
                    errors.append(self.env._("%s: manca la causale.", name))
                if line.not_subject and not line.not_subject_code:
                    warnings.append(self.env._("%s: somme non soggette senza codice (configurarlo nell'azienda).", name))
        for st in self.st_ids:
            if not st.tributo_code:
                errors.append(self.env._("Quadro ST %s: ritenute senza codice tributo.", st.period))
            if not self.currency_id.is_zero(st.withheld - st.paid):
                warnings.append(self.env._(
                    "Quadro ST %(period)s, tributo %(code)s: operate %(w).2f, versate %(p).2f.",
                    period=st.period, code=st.tributo_code, w=st.withheld, p=st.paid))
            if st.late:
                warnings.append(self.env._("Quadro ST %s: versamento tardivo, verificare il ravvedimento.", st.period))
        if not self.currency_id.is_zero(self.total_withheld_cu - self.total_withheld_st):
            errors.append(self.env._(
                "Il totale delle ritenute nelle CU (%(cu).2f) e' diverso dal quadro ST (%(st).2f).",
                cu=self.total_withheld_cu, st=self.total_withheld_st))
        unpaid = self._abc_year_lines().filtered(lambda l: l.state == "due" and not l.is_contribution)
        if unpaid:
            warnings.append(self.env._("%s quote dell'anno risultano ancora da versare.", len(unpaid)))
        return errors, warnings

    def action_confirm(self):
        for rec in self:
            rec.action_check()
            if rec.check_errors:
                raise UserError(self.env._("Correggere gli errori bloccanti prima di confermare:\n%s", rec.check_errors))
            rec.state = "confirmed"
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True

    def action_mark_sent(self):
        for rec in self:
            if not (rec.protocol_cu or rec.protocol_770):
                raise UserError(self.env._("Indicare almeno un protocollo di invio."))
            rec.write({"state": "sent", "sent_date": rec.sent_date or fields.Date.context_today(self)})
        return True

    # ------------------------------------------------------------------
    # Uscite: Excel, PDF, email, telematico
    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy"})

        sheet = workbook.add_worksheet("CU lavoro autonomo")
        headers = ["Percipiente", "Codice fiscale", "Partita IVA", "Indirizzo", "CAP", "Comune", "Provincia",
                   "Data nascita", "Comune nascita", "Prov. nascita", "Sesso", "Tipo CU", "Causale",
                   "Ammontare lordo", "Somme non soggette", "Codice non soggette", "Imponibile",
                   "Ritenute a titolo d'acconto", "Ritenute a titolo d'imposta", "Ritenute sospese",
                   "Contributi previdenziali"]
        sheet.write_row(0, 0, headers, bold)
        row = 1
        type_labels = dict(self.env["abc.withholding.cu"]._fields["cu_type"].selection)
        for cu in self.cu_ids:
            p = cu.partner_id
            for index, line in enumerate(cu.line_ids):
                values = [p.name or "", p.l10n_it_codice_fiscale or "", p.vat or "", p.street or "", p.zip or "",
                          p.city or "", p.state_id.code or ""]
                sheet.write_row(row, 0, values)
                if p.abc_wh_birth_date:
                    sheet.write_datetime(row, 7, fields.Datetime.to_datetime(p.abc_wh_birth_date), date_fmt)
                sheet.write_row(row, 8, [p.abc_wh_birth_city or "", p.abc_wh_birth_province or "",
                                         p.abc_wh_gender or "", type_labels.get(cu.cu_type, ""), line.reason or ""])
                for col, amount in enumerate((line.gross, line.not_subject), start=13):
                    sheet.write(row, col, amount, money)
                sheet.write(row, 15, line.not_subject_code or "")
                for col, amount in enumerate((line.taxable, line.withheld_advance, line.withheld_final,
                                              line.withheld_suspended), start=16):
                    sheet.write(row, col, amount, money)
                sheet.write(row, 20, cu.social_contrib if index == 0 else 0.0, money)
                row += 1
        sheet.set_column(0, 20, 16)

        st = workbook.add_worksheet("770 quadro ST")
        st.write_row(0, 0, ["Periodo di riferimento", "Codice tributo", "Ritenute operate", "Importo versato",
                            "Interessi", "Sanzioni", "Ravvedimento", "Data versamento"], bold)
        for row, line in enumerate(self.st_ids, start=1):
            st.write(row, 0, "%s/%s" % ((line.period or "")[5:7], (line.period or "")[:4]))
            st.write(row, 1, line.tributo_code or "")
            st.write(row, 2, line.withheld, money)
            st.write(row, 3, line.paid, money)
            st.write(row, 4, line.interest, money)
            st.write(row, 5, line.penalty, money)
            st.write(row, 6, "X" if line.late else "")
            if line.payment_date:
                st.write_datetime(row, 7, fields.Datetime.to_datetime(line.payment_date), date_fmt)
        st.set_column(0, 7, 18)

        company = self.company_id
        info = workbook.add_worksheet("Frontespizio")
        rows = [
            ("Sostituto d'imposta", company.name),
            ("Codice fiscale", company.partner_id.l10n_it_codice_fiscale or company.vat or ""),
            ("Codice attivita'", company.abc_wh_ateco_code or ""),
            ("Firmatario", company.abc_wh_signer_name or ""),
            ("Codice fiscale firmatario", company.abc_wh_signer_fiscalcode or ""),
            ("Codice carica", company.abc_wh_signer_role_code or ""),
            ("Intermediario (CF)", company.abc_wh_intermediary_fiscalcode or ""),
            ("Iscrizione CAF / albo", company.abc_wh_intermediary_caf or ""),
            ("Tipo dichiarazione", dict(DECLARATION_TYPES).get(self.declaration_type)),
            ("Invio separato parte dipendenti", "Si" if self.separate_sending else "No"),
            ("Anno dei pagamenti", self.year),
        ]
        for row, (label, value) in enumerate(rows):
            info.write(row, 0, label, bold)
            info.write(row, 1, value)
        info.set_column(0, 1, 32)
        workbook.close()
        return self._abc_download(output.getvalue(), "CU_770_%s_%s.xlsx" % (self.year, company.name))

    def _abc_download(self, content, filename):
        # sudo: chi ha solo la consultazione deve poter esportare
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_print_cu(self):
        self.ensure_one()
        return self.env.ref("abc_ritenute_acconto.action_report_cu").report_action(self.cu_ids)

    def action_send_cu(self):
        """Invia le CU sintetiche ai percipienti dall'utente che le compila (D57)."""
        template = self.env.ref("abc_ritenute_acconto.mail_template_cu_send")
        for rec in self:
            if rec.state not in ("confirmed", "sent"):
                raise UserError(self.env._("Confermare la dichiarazione prima di inviare le CU."))
            for cu in rec.cu_ids.filtered(lambda c: not c.sent):
                if not (cu.partner_id.abc_wh_cu_email or cu.partner_id.email):
                    cu.message_post(body=self.env._("CU non inviata: il percipiente non ha un indirizzo email."))
                    continue
                template.send_mail(cu.id, force_send=False,
                                   email_values={"email_from": self.env.user.email_formatted})
                cu.sent = True
        return True

    def action_generate_telematic(self):
        """File telematici CU e 770 sul tracciato dell'Agenzia delle Entrate (D54)."""
        self.ensure_one()
        generator = getattr(self, "_abc_telematic_%s" % self.year, None)
        if not generator:
            raise UserError(self.env._(
                "Il tracciato telematico per l'anno %s non e' ancora disponibile nel modulo: le specifiche "
                "tecniche dell'Agenzia delle Entrate vengono pubblicate a inizio anno e vanno recepite in un "
                "aggiornamento annuale. Nel frattempo usare l'export Excel.", self.year))
        return generator()


class AbcWithholdingCu(models.Model):
    _name = "abc.withholding.cu"
    _description = "Certificazione Unica per percipiente"
    _inherit = ["mail.thread"]
    _order = "partner_id"

    name = fields.Char(string="Riferimento", compute="_compute_name", store=True)
    declaration_id = fields.Many2one("abc.withholding.declaration", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="declaration_id.company_id", store=True)
    currency_id = fields.Many2one(related="declaration_id.currency_id")
    year = fields.Integer(related="declaration_id.year", store=True)
    partner_id = fields.Many2one("res.partner", string="Percipiente", required=True)
    cu_type = fields.Selection(
        [("ordinary", "Ordinaria"), ("replacement", "Sostitutiva"), ("cancellation", "Annullamento")],
        string="Tipo CU", default="ordinary", required=True,
        help="Sostitutive e annullamenti senza limiti di numero (D61).")
    protocol_to_replace = fields.Char(string="Protocollo CU da sostituire/annullare")
    line_ids = fields.One2many("abc.withholding.cu.line", "cu_id", string="Righe per causale")
    social_contrib = fields.Monetary(string="Contributi previdenziali")
    total_gross = fields.Monetary(string="Totale lordo", compute="_compute_totals")
    total_withheld = fields.Monetary(string="Totale ritenute", compute="_compute_totals")
    sent = fields.Boolean(string="Inviata al percipiente", copy=False)

    @api.depends("partner_id.name", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = "CU %s - %s" % ((rec.year or 0) + 1, rec.partner_id.name or "")

    @api.depends("line_ids.gross", "line_ids.withheld_advance", "line_ids.withheld_final")
    def _compute_totals(self):
        for rec in self:
            rec.total_gross = sum(rec.line_ids.mapped("gross"))
            rec.total_withheld = sum(rec.line_ids.mapped("withheld_advance")) + sum(rec.line_ids.mapped("withheld_final"))


class AbcWithholdingCuLine(models.Model):
    _name = "abc.withholding.cu.line"
    _description = "Riga CU (lavoro autonomo) per causale"

    cu_id = fields.Many2one("abc.withholding.cu", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="cu_id.currency_id")
    reason = fields.Char(string="Causale")
    gross = fields.Monetary(string="Ammontare lordo corrisposto")
    not_subject = fields.Monetary(string="Somme non soggette")
    not_subject_code = fields.Char(string="Codice somme non soggette")
    taxable = fields.Monetary(string="Imponibile")
    withheld_advance = fields.Monetary(string="Ritenute a titolo d'acconto")
    withheld_final = fields.Monetary(string="Ritenute a titolo d'imposta")
    withheld_suspended = fields.Monetary(string="Ritenute sospese")


class AbcWithholdingSt(models.Model):
    _name = "abc.withholding.st"
    _description = "Riga del quadro ST del 770"
    _order = "period, tributo_code"

    declaration_id = fields.Many2one("abc.withholding.declaration", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="declaration_id.currency_id")
    period = fields.Char(string="Periodo (AAAA-MM)")
    tributo_code = fields.Char(string="Codice tributo")
    withheld = fields.Monetary(string="Ritenute operate")
    paid = fields.Monetary(string="Importo versato")
    interest = fields.Monetary(string="Interessi")
    penalty = fields.Monetary(string="Sanzioni")
    payment_date = fields.Date(string="Data versamento")
    late = fields.Boolean(string="Ravvedimento")
