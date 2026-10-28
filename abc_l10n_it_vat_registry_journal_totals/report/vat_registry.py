# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models


class ReportRegistroIva(models.AbstractModel):
    _inherit = "report.l10n_it_vat_registries.report_registro_iva"

    @api.model
    def _get_report_values(self, docids, data=None):
        res = super()._get_report_values(docids, data=data)
        res["journal_totals"] = self._get_journal_totals
        return res

    def _get_journal_totals(self, journal_id, move_ids, data):
        """Riepilogo per aliquota delle registrazioni di un solo sezionale.

        Usa lo stesso calcolo dei totali finali (_compute_totals_tax), ristretto
        al sezionale: la somma dei parziali coincide con il totale generale.
        """
        journal = self.env["account.journal"].browse(journal_id)
        moves = self.env["account.move"].browse(move_ids).filtered(
            lambda move: move.journal_id == journal
        )
        used_taxes = self.env["account.tax"]
        for move in moves:
            used_taxes |= self._get_tax_lines(move, data)[1]

        journal_data = dict(data, journal_ids=[journal.id], rc_journal_ids=[])
        lines = []
        totals = {"base": 0.0, "tax": 0.0, "deductible": 0.0, "undeductible": 0.0}
        # I saldi delle imposte (base_balance, balance, ...) sono campi calcolati
        # non memorizzati che non dipendono dal context: in cache resterebbero i
        # valori di un altro sezionale o dell'intero registro. Si invalida prima
        # del calcolo e dopo, così i Totali finali ricalcolano su tutto il registro.
        self.env["account.tax"].invalidate_model()
        for tax in used_taxes.sorted():
            tax_tuple = self._compute_totals_tax(tax, journal_data)
            # stessa scelta del template dei totali: saldo fornitori per il
            # registro acquisti, saldo clienti negli altri casi
            if data["registry_type"] == "supplier":
                tax_amount = tax_tuple[8]
            else:
                tax_amount = tax_tuple[7]
            line = {
                "name": tax_tuple[0],
                "base": tax_tuple[1],
                "tax": tax_amount,
                "deductible": tax_tuple[3],
                "undeductible": tax_tuple[4],
            }
            for key in totals:
                totals[key] += line[key]
            lines.append(line)
        self.env["account.tax"].invalidate_model()
        return {
            "journal_name": journal.name,
            "lines": lines,
            "totals": totals,
        }
