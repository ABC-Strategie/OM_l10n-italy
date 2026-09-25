# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError

from odoo.addons.abc_modelli_scritture.models.scrittura_template import natural_side


class GeneraScrittura(models.TransientModel):
    _name = "abc.modelli.scritture.genera"
    _description = "Genera scrittura contabile da modello"

    template_id = fields.Many2one(
        "abc.modelli.scritture.template", string="Modello", required=True
    )
    data = fields.Date(
        "Data registrazione", required=True, default=fields.Date.context_today
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Registro (Varie)",
        domain="[('type', '=', 'general')]",
        required=True,
    )
    descrizione = fields.Char("Descrizione")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_ids = fields.One2many(
        "abc.modelli.scritture.genera.line", "wizard_id", string="Righe"
    )
    totale_dare = fields.Monetary(
        compute="_compute_totali", currency_field="currency_id"
    )
    totale_avere = fields.Monetary(
        compute="_compute_totali", currency_field="currency_id"
    )
    sbilancio = fields.Monetary(
        string="Sbilancio (Dare - Avere)",
        compute="_compute_totali",
        currency_field="currency_id",
    )

    @api.depends("line_ids.dare", "line_ids.avere")
    def _compute_totali(self):
        for wiz in self:
            dare = sum(wiz.line_ids.mapped("dare"))
            avere = sum(wiz.line_ids.mapped("avere"))
            wiz.totale_dare = dare
            wiz.totale_avere = avere
            wiz.sbilancio = dare - avere

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = self.env.context.get("default_template_id")
        if template_id:
            template = self.env["abc.modelli.scritture.template"].browse(template_id)
            res["descrizione"] = template.descrizione
            res["journal_id"] = template.journal_id.id
            righe = []
            for line in template.line_ids:
                righe.append(
                    Command.create(
                        {
                            "sequence": line.sequence,
                            "account_id": line.account_id.id,
                            "name": line.name,
                            "partner_id": line.partner_id.id,
                            "dare": line.dare,
                            "avere": line.avere,
                            "analytic_distribution": line.analytic_distribution,
                        }
                    )
                )
            res["line_ids"] = righe
        return res

    def action_crea(self):
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Seleziona il registro (Varie)."))

        move_lines = []
        for line in self.line_ids:
            if not line.account_id:
                continue
            # Le righe lasciate a zero non entrano nella scrittura.
            if self.currency_id.is_zero(line.dare) and self.currency_id.is_zero(
                line.avere
            ):
                continue
            move_lines.append(
                Command.create(
                    {
                        "account_id": line.account_id.id,
                        "name": line.name or self.descrizione or "",
                        "partner_id": line.partner_id.id or False,
                        "debit": line.dare,
                        "credit": line.avere,
                        "analytic_distribution": line.analytic_distribution or False,
                    }
                )
            )

        if not move_lines:
            raise UserError(
                _(
                    "Nessuna riga con importo: inserisci almeno un importo "
                    "in Dare o in Avere."
                )
            )
        if not self.currency_id.is_zero(self.sbilancio):
            raise UserError(
                _(
                    "La scrittura non quadra: totale Dare %(dare)s, totale Avere "
                    "%(avere)s. Correggi gli importi prima di creare la scrittura."
                )
                % {"dare": self.totale_dare, "avere": self.totale_avere}
            )

        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal_id.id,
                "date": self.data,
                "ref": self.descrizione or "",
                "line_ids": move_lines,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Scrittura generata"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }


class GeneraScritturaLine(models.TransientModel):
    _name = "abc.modelli.scritture.genera.line"
    _inherit = ["analytic.mixin"]
    _description = "Riga della scrittura da generare"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "abc.modelli.scritture.genera", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    account_id = fields.Many2one(
        "account.account",
        string="Conto",
        required=True,
    )
    name = fields.Char("Etichetta")
    partner_id = fields.Many2one("res.partner", string="Partner")
    dare = fields.Monetary("Dare", currency_field="currency_id")
    avere = fields.Monetary("Avere", currency_field="currency_id")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    avviso_lato = fields.Char(string="Avviso", compute="_compute_avviso_lato")

    @api.depends("account_id", "dare", "avere")
    def _compute_avviso_lato(self):
        for line in self:
            nat = natural_side(line.account_id.account_type) if line.account_id else False
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
                    "title": _("Lato insolito"),
                    "message": _(
                        "Il conto %s di norma va in Dare, ma qui è movimentato in Avere."
                    )
                    % self.account_id.display_name,
                }
            }
        if nat == "avere" and self.dare and not self.avere:
            return {
                "warning": {
                    "title": _("Lato insolito"),
                    "message": _(
                        "Il conto %s di norma va in Avere, ma qui è movimentato in Dare."
                    )
                    % self.account_id.display_name,
                }
            }
