# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Tipologie conto (account_type Odoo 19) e loro lato "naturale".
DEBIT_TYPES = (
    "asset_receivable", "asset_cash", "asset_current", "asset_non_current",
    "asset_prepayments", "asset_fixed",
    "expense", "expense_depreciation", "expense_direct_cost",
)
CREDIT_TYPES = (
    "liability_payable", "liability_current", "liability_non_current",
    "liability_credit_card", "equity", "equity_unaffected",
    "income", "income_other",
)


def natural_side(account_type):
    """Restituisce 'dare' / 'avere' / False in base alla natura del conto."""
    if account_type in DEBIT_TYPES:
        return "dare"
    if account_type in CREDIT_TYPES:
        return "avere"
    return False


class ScritturaTemplate(models.Model):
    _name = "abc.modelli.scritture.template"
    _description = "Modello di scrittura contabile"
    _order = "name"

    name = fields.Char("Nome modello", required=True)
    descrizione = fields.Char(
        "Descrizione della scrittura",
        help="Descrizione generale della registrazione (es. 'RILEVAZIONE STIPENDI').",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Registro (Varie)",
        domain="[('type', '=', 'general')]",
        help="Registro di tipo Varie sul quale verrà creata la scrittura.",
    )
    state = fields.Selection(
        [("bozza", "Bozza"), ("confermato", "Confermato")],
        default="bozza",
        string="Stato",
        readonly=True,
        copy=False,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Azienda", default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id", string="Valuta")
    line_ids = fields.One2many(
        "abc.modelli.scritture.template.line",
        "template_id",
        string="Righe",
        copy=True,
    )
    totale_dare = fields.Monetary(
        string="Totale Dare", compute="_compute_totali", currency_field="currency_id"
    )
    totale_avere = fields.Monetary(
        string="Totale Avere", compute="_compute_totali", currency_field="currency_id"
    )
    sbilancio = fields.Monetary(
        string="Sbilancio (Dare - Avere)",
        compute="_compute_totali",
        currency_field="currency_id",
    )

    @api.depends("line_ids.dare", "line_ids.avere")
    def _compute_totali(self):
        for rec in self:
            dare = sum(rec.line_ids.mapped("dare"))
            avere = sum(rec.line_ids.mapped("avere"))
            rec.totale_dare = dare
            rec.totale_avere = avere
            rec.sbilancio = dare - avere

    def action_conferma(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(
                    _("Aggiungi almeno una riga prima di confermare il modello.")
                )
            rec.state = "confermato"

    def action_riporta_in_bozza(self):
        # Richiamato dal pulsante "Modifica modello", protetto da avviso di conferma
        # nella vista (attributo confirm).
        self.write({"state": "bozza"})

    def action_genera_scrittura(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Genera scrittura da modello"),
            "res_model": "abc.modelli.scritture.genera",
            "view_mode": "form",
            "target": "new",
            "context": {"default_template_id": self.id},
        }


class ScritturaTemplateLine(models.Model):
    _name = "abc.modelli.scritture.template.line"
    _inherit = ["analytic.mixin"]
    _description = "Riga del modello di scrittura"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "abc.modelli.scritture.template",
        string="Modello",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    account_id = fields.Many2one(
        "account.account",
        string="Conto",
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Partner")
    name = fields.Char("Etichetta")
    dare = fields.Monetary("Dare", currency_field="currency_id")
    avere = fields.Monetary("Avere", currency_field="currency_id")
    currency_id = fields.Many2one(related="template_id.currency_id")
    lato_naturale = fields.Selection(
        [("dare", "Dare"), ("avere", "Avere")],
        string="Lato naturale",
        compute="_compute_avviso_lato",
    )
    avviso_lato = fields.Char(string="Avviso", compute="_compute_avviso_lato")

    @api.depends("account_id", "dare", "avere")
    def _compute_avviso_lato(self):
        for line in self:
            nat = natural_side(line.account_id.account_type) if line.account_id else False
            line.lato_naturale = nat
            msg = False
            if nat == "dare" and line.avere and not line.dare:
                msg = _("Conto di norma in Dare, qui movimentato in Avere.")
            elif nat == "avere" and line.dare and not line.avere:
                msg = _("Conto di norma in Avere, qui movimentato in Dare.")
            line.avviso_lato = msg

    @api.onchange("dare", "avere", "account_id")
    def _onchange_avvisa_lato(self):
        nat = natural_side(self.account_id.account_type) if self.account_id else False
        if nat == "dare" and self.avere and not self.dare:
            return {
                "warning": {
                    "title": _("Lato insolito per questo conto"),
                    "message": _(
                        "Il conto %s di norma si movimenta in Dare, "
                        "ma qui è in Avere.\nProcedi solo se è corretto."
                    )
                    % self.account_id.display_name,
                }
            }
        if nat == "avere" and self.dare and not self.avere:
            return {
                "warning": {
                    "title": _("Lato insolito per questo conto"),
                    "message": _(
                        "Il conto %s di norma si movimenta in Avere, "
                        "ma qui è in Dare.\nProcedi solo se è corretto."
                    )
                    % self.account_id.display_name,
                }
            }
