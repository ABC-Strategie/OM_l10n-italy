from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("move_id.partner_id", "move_id.fiscal_position_id")
    def _compute_tax_ids(self):
        # Prima lascia che Odoo calcoli le imposte come di consueto
        # (prodotto / conto / default azienda, gia' rimappate dalla posizione
        # fiscale). NB: verificare che il nome del compute del campo tax_ids sia
        # ancora "_compute_tax_ids" sul sorgente esatto della propria Odoo 19.
        super()._compute_tax_ids()
        for line in self:
            move = line.move_id
            # Solo fatture / note di credito FORNITORE.
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            # Solo righe reali (niente sezioni/note) e SENZA prodotto:
            # per le righe con prodotto si mantiene il comportamento standard.
            if line.display_type != "product" or line.product_id:
                continue
            partner_tax = move.partner_id.property_purchase_tax_id
            if not partner_tax:
                continue
            # L'imposta indicata sul fornitore ha la precedenza su questa riga.
            # Si applica comunque la posizione fiscale: se l'imposta scelta sul
            # fornitore non e' sorgente di alcuna mappatura (es. gia' "22% S IC")
            # resta invariata; se e' un'imposta base (es. "22%") viene rimappata.
            taxes = partner_tax
            if move.fiscal_position_id:
                taxes = move.fiscal_position_id.map_tax(partner_tax)
            line.tax_ids = taxes
