from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    _inherit = "account.tax"

    abc_wh_on_partner = fields.Boolean(
        string="Ritenuta sul conto del fornitore / cliente",
        help="Schema del vecchio modulo OCA (D2). In fattura la ritenuta resta sul conto del "
             "fornitore (o del cliente), cosi' il debito (o il credito) e' al lordo; al pagamento "
             "una scrittura nel registro varie la storna e apre il debito verso l'Erario sul conto "
             "indicato nella ripartizione dell'imposta. Richiede l'esigibilita' 'in base alla fattura'.",
    )
    abc_wh_tributo_code = fields.Char(
        string="Codice tributo F24",
        help="Se vuoto si usa la tabella causale -> codice tributo.",
    )
    abc_wh_final = fields.Boolean(
        string="Ritenuta a titolo d'imposta",
        help="Es. compensi di lavoro autonomo a non residenti (D14).",
    )

    @api.constrains("abc_wh_on_partner", "tax_exigibility")
    def _check_abc_wh_on_partner(self):
        for tax in self:
            if tax.abc_wh_on_partner and tax.tax_exigibility == "on_payment":
                raise ValidationError(self.env._(
                    "L'imposta %s registra la ritenuta sul conto del fornitore/cliente: l'esigibilita' "
                    "deve essere 'in base alla fattura', altrimenti Odoo creerebbe anche le scritture "
                    "per cassa sul conto d'appoggio.", tax.name))

    def _abc_wh_is_withholding(self):
        self.ensure_one()
        return bool(self.l10n_it_withholding_type) and self.amount < 0

    def _abc_wh_final_account(self, refund=False):
        """Conto su cui nasce il debito/credito verso l'Erario (ripartizione dell'imposta)."""
        self.ensure_one()
        lines = self.refund_repartition_line_ids if refund else self.invoice_repartition_line_ids
        return lines.filtered(lambda l: l.repartition_type == "tax" and l.account_id)[:1].account_id

    @api.model
    def _prepare_base_line_tax_repartition_grouping_key(self, base_line, base_line_grouping_key, tax_data, tax_rep_data):
        """La riga ritenuta della fattura va sul conto del fornitore/cliente invece che sull'Erario."""
        key = super()._prepare_base_line_tax_repartition_grouping_key(
            base_line, base_line_grouping_key, tax_data, tax_rep_data)
        tax = tax_data["tax"]
        partner = base_line.get("partner_id")
        if tax.abc_wh_on_partner and tax._abc_wh_is_withholding() and partner:
            record = base_line.get("record")
            is_aml = isinstance(record, models.BaseModel) and record._name == "account.move.line"
            move = record.move_id if is_aml and record.move_id else None
            company = move.company_id if move else tax.company_id
            use = (tax_data.get("group") or tax).type_tax_use
            if use not in ("purchase", "sale"):
                use = tax.type_tax_use
            if move and move.is_invoice(include_receipts=True):
                use = "purchase" if move.is_purchase_document(include_receipts=True) else "sale"
            partner = partner.with_company(company)
            account = partner.property_account_payable_id if use == "purchase" \
                else partner.property_account_receivable_id
            if account and move and move.fiscal_position_id:
                account = move.fiscal_position_id.map_account(account)
            if account:
                key["account_id"] = account.id
        return key

    # La ritenuta sul conto del fornitore/cliente non deve entrare nella chiusura IVA
    @api.model_create_multi
    def create(self, vals_list):
        taxes = super().create(vals_list)
        taxes._abc_wh_sync_tax_closing()
        return taxes

    def write(self, vals):
        res = super().write(vals)
        if "abc_wh_on_partner" in vals or "invoice_repartition_line_ids" in vals \
                or "refund_repartition_line_ids" in vals:
            self._abc_wh_sync_tax_closing()
        return res

    def _abc_wh_sync_tax_closing(self):
        lines = (self.filtered("abc_wh_on_partner").invoice_repartition_line_ids
                 | self.filtered("abc_wh_on_partner").refund_repartition_line_ids)
        lines = lines.filtered(lambda l: l.repartition_type == "tax" and l.use_in_tax_closing)
        if lines:
            lines.write({"use_in_tax_closing": False})
