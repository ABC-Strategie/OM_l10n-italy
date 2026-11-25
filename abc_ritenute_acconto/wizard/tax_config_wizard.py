from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ..models.withholding import CONTRIBUTION_TYPES, WITHHOLDING_REASONS_IT

AGENT_RATES = (11.5, 4.6)  # 23% sul 50% o sul 20% delle provvigioni

# Imposte ritenuta standard proposte quando mancano (clienti nuovi o migrati senza imposte native).
# (uso, nome, aliquota, tipo RT, causale, codice tributo, a titolo d'imposta)
STANDARD_TAXES = [
    ("purchase", "Ritenuta 20% persone fisiche", -20.0, "RT01", "A", "1040", False),
    ("purchase", "Ritenuta 20% persone giuridiche", -20.0, "RT02", "A", "1040", False),
    ("purchase", "Ritenuta 23% agenti (base 50%)", -11.5, "RT01", "Q", "1038", False),
    ("purchase", "Ritenuta 23% agenti (base 20%)", -4.6, "RT01", "Q", "1038", False),
    ("purchase", "Ritenuta 30% non residenti", -30.0, "RT01", "A", "1040", True),
    ("sale", "Ritenuta subita 20% persone fisiche", -20.0, "RT01", "A", False, False),
    ("sale", "Ritenuta subita 20% persone giuridiche", -20.0, "RT02", "A", False, False),
    ("sale", "Ritenuta subita 23% agenti (base 50%)", -11.5, "RT01", "Q", False, False),
    ("sale", "Ritenuta subita 4% condominio", -4.0, "RT02", "ZO", False, False),
]


class AbcWithholdingTaxConfigWizard(models.TransientModel):
    _name = "abc.withholding.tax.config.wizard"
    _description = "Configurazione delle imposte ritenuta"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    set_exigibility = fields.Boolean(
        string="Esigibilita' in base alla fattura", default=True,
        help="Toglie l'esigibilita' per cassa e il conto d'appoggio.")
    set_on_partner = fields.Boolean(string="Ritenuta sul conto del fornitore / cliente", default=True)
    set_tributo = fields.Boolean(string="Imposta i codici tributo proposti", default=True)
    set_reconcile = fields.Boolean(
        string="Rendi riconciliabili i conti erariali", default=True,
        help="Serve per chiudere il debito verso l'Erario con l'addebito F24 in banca.")
    line_ids = fields.One2many("abc.withholding.tax.config.line", "wizard_id", string="Imposte ritenuta")
    template_ids = fields.One2many(
        "abc.withholding.tax.template.line", "wizard_id", string="Imposte standard mancanti")
    purchase_account_id = fields.Many2one(
        "account.account", string="Conto per le ritenute da versare",
        domain="[('company_ids', 'in', company_id)]",
        help="Conto erariale delle nuove imposte d'acquisto (es. Erario c/ritenute da versare).")
    sale_account_id = fields.Many2one(
        "account.account", string="Conto per le ritenute subite",
        domain="[('company_ids', 'in', company_id)]",
        help="Conto erariale delle nuove imposte di vendita (es. Crediti per ritenute subite).")
    open_invoice_count = fields.Integer(string="Fatture aperte con ritenuta sull'appoggio", compute="_compute_open")
    result = fields.Text(string="Esito", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env["res.company"].browse(res.get("company_id")) or self.env.company
        if "line_ids" in fields_list:
            res["line_ids"] = [Command.create(vals) for vals in self._abc_lines_vals(company)]
        if "template_ids" in fields_list:
            res["template_ids"] = [Command.create(vals) for vals in self._abc_template_vals(company)]
        existing = self.env["account.tax"].with_context(active_test=False).search([
            ("company_id", "=", company.id), ("l10n_it_withholding_type", "!=", False), ("amount", "<", 0)])
        for use, field in (("purchase", "purchase_account_id"), ("sale", "sale_account_id")):
            if field in fields_list:
                accounts = self.env["account.account"]
                for tax in existing.filtered(lambda t: t.type_tax_use == use
                                             and t.l10n_it_withholding_type in ("RT01", "RT02")):
                    accounts |= tax._abc_wh_final_account()
                res[field] = accounts[:1].id or False
        return res

    @api.model
    def _abc_template_vals(self, company):
        """Imposte standard che l'azienda non ha ancora (stesso uso, tipo, causale e aliquota)."""
        existing = self.env["account.tax"].with_context(active_test=False).search([
            ("company_id", "=", company.id), ("l10n_it_withholding_type", "!=", False)])
        vals_list = []
        for use, name, amount, wtype, reason, tributo, final in STANDARD_TAXES:
            found = existing.filtered(
                lambda t: t.type_tax_use == use and t.l10n_it_withholding_type == wtype
                and float_compare(t.amount, amount, precision_digits=4) == 0)
            if found:
                continue
            vals_list.append({
                "create_tax": False,
                "type_tax_use": use,
                "name": name,
                "amount": amount,
                "withholding_type": wtype,
                "reason": reason,
                "tributo_code": tributo,
                "is_final": final,
            })
        return vals_list

    def _abc_tax_group(self):
        Group = self.env["account.tax.group"]
        company = self.company_id
        existing = self.env["account.tax"].search([
            ("company_id", "=", company.id), ("l10n_it_withholding_type", "!=", False)], limit=1)
        if existing:
            return existing.tax_group_id
        group = Group.search([("company_id", "=", company.id), ("name", "ilike", "ritenut")], limit=1)
        return group or Group.create({
            "name": "Ritenute",
            "company_id": company.id,
            "country_id": company.account_fiscal_country_id.id,
        })

    def _abc_create_templates(self):
        """Crea le imposte standard selezionate, gia' configurate per lo schema del modulo."""
        templates = self.template_ids.filtered("create_tax")
        if not templates:
            return []
        group = self._abc_tax_group()
        messages = []
        for tpl in templates:
            account = self.purchase_account_id if tpl.type_tax_use == "purchase" else self.sale_account_id
            if not account:
                raise UserError(self.env._(
                    "Indicare il conto erariale per le nuove imposte di %s.",
                    "acquisto" if tpl.type_tax_use == "purchase" else "vendita"))
            if not tpl.reason:
                raise UserError(self.env._("Indicare la causale per l'imposta %s.", tpl.name))
            if self.set_reconcile and not account.reconcile:
                account.reconcile = True
            repartition = [
                Command.create({"repartition_type": "base", "factor_percent": 100.0}),
                Command.create({"repartition_type": "tax", "factor_percent": 100.0, "account_id": account.id}),
            ]
            tax = self.env["account.tax"].create({
                "name": tpl.name,
                "company_id": self.company_id.id,
                "country_id": self.company_id.account_fiscal_country_id.id,
                "type_tax_use": tpl.type_tax_use,
                "amount_type": "percent",
                "amount": tpl.amount,
                "sequence": 50,  # dopo l'IVA: la fattura elettronica marca le righe con ritenuta
                "tax_group_id": group.id,
                "tax_exigibility": "on_invoice",
                "l10n_it_withholding_type": tpl.withholding_type,
                "l10n_it_withholding_reason": tpl.reason,
                "abc_wh_on_partner": True,
                "abc_wh_tributo_code": tpl.tributo_code or False,
                "abc_wh_final": tpl.is_final,
                "invoice_repartition_line_ids": repartition,
                "refund_repartition_line_ids": [
                    Command.create({"repartition_type": "base", "factor_percent": 100.0}),
                    Command.create({"repartition_type": "tax", "factor_percent": 100.0, "account_id": account.id}),
                ],
            })
            messages.append(self.env._("Creata l'imposta %s.", tax.name))
        return messages

    @api.depends("line_ids.open_invoice_count")
    def _compute_open(self):
        for wiz in self:
            wiz.open_invoice_count = sum(wiz.line_ids.mapped("open_invoice_count"))

    @api.model
    def _abc_lines_vals(self, company):
        taxes = self.env["account.tax"].with_context(active_test=False).search([
            ("company_id", "=", company.id),
            ("l10n_it_withholding_type", "!=", False),
            ("amount", "<", 0),
        ], order="type_tax_use, name")
        return [self._abc_line_vals(tax) for tax in taxes]

    @api.model
    def _abc_line_vals(self, tax):
        final = tax._abc_wh_final_account()
        transit = tax.cash_basis_transition_account_id
        wtype = tax.l10n_it_withholding_type
        warnings = []
        tributo = tax.abc_wh_tributo_code or self.env["abc.withholding.tributo.map"]._abc_get_code(
            tax.l10n_it_withholding_reason, wtype, tax.company_id)
        if not tributo and wtype in ("RT01", "RT02"):
            if any(float_compare(abs(tax.amount), rate, precision_digits=2) == 0 for rate in AGENT_RATES):
                tributo = "1038"
                warnings.append(self.env._("Aliquota da agente: proposto 1038 invece del 1040 della causale."))
            else:
                tributo = "1040"
                warnings.append(self.env._("Causale senza codice in tabella: proposto 1040, verificare."))
        if wtype in CONTRIBUTION_TYPES:
            tributo = tax.abc_wh_tributo_code or False
            warnings.append(self.env._("Contributo previdenziale: non si versa con il codice tributo erariale."))
        if not final:
            warnings.append(self.env._("Manca il conto nella ripartizione dell'imposta: indicare il conto erariale."))
        else:
            if tax.type_tax_use == "purchase" and not final.account_type.startswith("liability"):
                warnings.append(self.env._("Acquisti: il conto erariale %s non e' un debito.", final.display_name))
            if tax.type_tax_use == "sale" and not final.account_type.startswith("asset"):
                warnings.append(self.env._("Vendite: il conto erariale %s non e' un credito.", final.display_name))
        if transit:
            if tax.type_tax_use == "purchase" and transit.account_type.startswith("asset"):
                warnings.append(self.env._(
                    "Il conto d'appoggio %s e' un credito su un'imposta d'acquisto: configurazione da verificare.",
                    transit.display_name))
            if tax.type_tax_use == "sale" and transit.account_type.startswith("liability"):
                warnings.append(self.env._(
                    "Il conto d'appoggio %s e' un debito su un'imposta di vendita: configurazione da verificare.",
                    transit.display_name))
        open_moves = self._abc_open_moves_on_transit(tax)
        if open_moves:
            warnings.append(self.env._(
                "%s fatture non ancora pagate hanno la ritenuta sul conto d'appoggio: dopo la configurazione "
                "lanciare subito la ricostruzione dello storico con \"Riporta sul fornitore/cliente\".",
                len(open_moves)))
        return {
            "tax_id": tax.id,
            "apply": tax.active,
            "proposed_tributo": tributo or False,
            "warning": "\n".join(warnings) or False,
            "open_invoice_count": len(open_moves),
        }

    @api.model
    def _abc_open_moves_on_transit(self, tax):
        transit = tax.cash_basis_transition_account_id
        if not transit:
            return self.env["account.move"]
        lines = self.env["account.move.line"].search([
            ("company_id", "=", tax.company_id.id),
            ("tax_line_id", "=", tax.id),
            ("account_id", "=", transit.id),
            ("parent_state", "=", "posted"),
            ("move_id.payment_state", "in", ("not_paid", "partial", "in_payment")),
        ])
        return lines.move_id

    def action_apply(self):
        self.ensure_one()
        lines = self.line_ids.filtered("apply")
        if not lines and not self.template_ids.filtered("create_tax"):
            raise UserError(self.env._("Selezionare almeno un'imposta da configurare o da creare."))
        messages = self._abc_create_templates()
        for line in lines:
            tax = line.tax_id
            vals = {}
            if self.set_exigibility and tax.tax_exigibility != "on_invoice":
                vals.update({"tax_exigibility": "on_invoice", "cash_basis_transition_account_id": False})
            if self.set_on_partner and not tax.abc_wh_on_partner:
                vals["abc_wh_on_partner"] = True
            if self.set_tributo and line.proposed_tributo and tax.abc_wh_tributo_code != line.proposed_tributo:
                vals["abc_wh_tributo_code"] = line.proposed_tributo
            if vals:
                tax.write(vals)
                messages.append(self.env._("%(tax)s (%(use)s): aggiornata.", tax=tax.name, use=tax.type_tax_use))
            if self.set_reconcile:
                for refund in (False, True):
                    final = tax._abc_wh_final_account(refund=refund)
                    if final and not final.reconcile:
                        final.reconcile = True
                        messages.append(self.env._("Conto %s reso riconciliabile.", final.display_name))
        if self.open_invoice_count:
            messages.append(self.env._(
                "Attenzione: %s fatture non pagate hanno ancora la ritenuta sul conto d'appoggio. "
                "Lanciare ora Configurazione > Ritenute > Ricostruisci storico con \"Riporta sul "
                "fornitore/cliente\", prima di registrare nuovi pagamenti.", self.open_invoice_count))
        self.result = "\n".join(messages) or self.env._("Nessuna modifica: le imposte erano gia' configurate.")
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class AbcWithholdingTaxTemplateLine(models.TransientModel):
    _name = "abc.withholding.tax.template.line"
    _description = "Imposta ritenuta standard da creare"

    wizard_id = fields.Many2one("abc.withholding.tax.config.wizard", required=True, ondelete="cascade")
    create_tax = fields.Boolean(string="Crea")
    type_tax_use = fields.Selection([("purchase", "Acquisti"), ("sale", "Vendite")], string="Uso", required=True)
    name = fields.Char(string="Nome", required=True)
    amount = fields.Float(string="Aliquota effettiva %", digits=(16, 4),
                          help="Negativa. Es. -11,5 = 23% sul 50% delle provvigioni.")
    # ENASARCO (RT04) escluso: richiede la cassa TC07, si crea a mano
    withholding_type = fields.Selection(
        [("RT01", "RT01 - Persone fisiche"), ("RT02", "RT02 - Persone giuridiche")],
        string="Tipo", required=True)
    reason = fields.Selection(WITHHOLDING_REASONS_IT, string="Causale")
    tributo_code = fields.Char(string="Codice tributo")
    is_final = fields.Boolean(string="A titolo d'imposta")


class AbcWithholdingTaxConfigLine(models.TransientModel):
    _name = "abc.withholding.tax.config.line"
    _description = "Imposta ritenuta da configurare"

    wizard_id = fields.Many2one("abc.withholding.tax.config.wizard", required=True, ondelete="cascade")
    apply = fields.Boolean(string="Applica", default=True)
    tax_id = fields.Many2one("account.tax", string="Imposta", required=True)
    type_tax_use = fields.Selection(related="tax_id.type_tax_use", string="Uso")
    withholding_type = fields.Selection(related="tax_id.l10n_it_withholding_type", string="Tipo")
    reason = fields.Selection(WITHHOLDING_REASONS_IT, related="tax_id.l10n_it_withholding_reason", string="Causale")
    amount = fields.Float(related="tax_id.amount", string="Aliquota")
    tax_exigibility = fields.Selection(related="tax_id.tax_exigibility", string="Esigibilita' attuale")
    transition_account_id = fields.Many2one(
        related="tax_id.cash_basis_transition_account_id", string="Conto d'appoggio attuale")
    on_partner = fields.Boolean(related="tax_id.abc_wh_on_partner", string="Gia' sul fornitore/cliente")
    current_tributo = fields.Char(related="tax_id.abc_wh_tributo_code", string="Codice tributo attuale")
    proposed_tributo = fields.Char(string="Codice tributo proposto")
    final_account_id = fields.Many2one(
        "account.account", string="Conto erariale", compute="_compute_final_account")
    open_invoice_count = fields.Integer(string="Fatture aperte sull'appoggio")
    warning = fields.Text(string="Avvisi")

    @api.depends("tax_id")
    def _compute_final_account(self):
        for line in self:
            line.final_account_id = line.tax_id._abc_wh_final_account() if line.tax_id else False
