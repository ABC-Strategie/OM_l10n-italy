from collections import defaultdict
from datetime import date

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from ..models.withholding import ACTIVE_TYPES, PASSIVE_TYPES


class AbcWithholdingRebuildWizard(models.TransientModel):
    _name = "abc.withholding.rebuild.wizard"
    _description = "Ricostruzione dello storico ritenute"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    cycle = fields.Selection(
        [("passive", "Ciclo passivo"), ("active", "Ciclo attivo")], string="Ciclo", default="passive", required=True,
        help="Per il ciclo attivo lo storico non si ricostruisce (D51): usare solo se serve davvero.")
    date_from = fields.Date(
        string="Fatture dal", required=True,
        default=lambda self: self.env.company.abc_wh_start_date
        or fields.Date.context_today(self).replace(month=1, day=1),
        help="Per avere CU e 770 completi partire dal 1 gennaio dell'anno dei pagamenti da certificare.")
    import_oca = fields.Boolean(
        string="Importa lo storico del modulo OCA (clienti migrati dalla 16)",
        help="Legge dal database le dichiarazioni e i movimenti ritenuta del vecchio modulo OCA "
             "l10n_it_withholding_tax: crea ritenute e quote con il loro stato (dovuta / versata) e "
             "prepara le fatture non ancora pagate per lo schema del modulo.")
    paid_until = fields.Date(
        string="Considera versate le scadenze fino al",
        help="Le quote con scadenza fino a questa data vengono marcate come versate, "
             "con un versamento storico per mese senza scritture contabili (D6).")
    migrate_transit = fields.Boolean(
        string="Riporta sul fornitore/cliente le ritenute non ancora pagate",
        help="Passaggio allo schema del modulo (D2): per le fatture registrate prima, con la ritenuta "
             "sul conto d'appoggio delle imposte per cassa, la parte non ancora pagata viene girata "
             "dal conto d'appoggio al fornitore (o al cliente), con una scrittura per fattura. "
             "Prima togliere l'esigibilita' per cassa dalle imposte ritenuta.")
    migration_date = fields.Date(string="Data della scrittura di passaggio", default=fields.Date.context_today)
    result = fields.Text(string="Esito", readonly=True)

    def action_run(self):
        self.ensure_one()
        Wh = self.env["abc.withholding"].sudo()
        types = PASSIVE_TYPES if self.cycle == "passive" else ACTIVE_TYPES
        moves = self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", types),
            ("state", "=", "posted"),
            ("invoice_date", ">=", self.date_from),
        ])
        created = Wh._abc_create_from_moves(moves, force=True)
        partials = moves.line_ids.filtered(lambda l: l.display_type == "payment_term")
        partials = partials.matched_debit_ids | partials.matched_credit_ids
        for partial in partials.sorted(lambda p: (p.max_date, p.id)):
            Wh._abc_process_partial(partial, transfer=False)
        lines = created.line_ids
        messages = [self.env._("Ritenute create: %(n)s, quote create: %(q)s.", n=len(created), q=len(lines))]
        if self.import_oca:
            messages.append(self._abc_import_oca())
        if self.paid_until and self.cycle == "passive":
            messages.append(self._abc_mark_paid())
        if self.migrate_transit:
            messages.append(self._abc_migrate_transit())
        self.result = "\n".join(messages)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _abc_mark_paid(self):
        """Quote da storico (ricostruite o importate dall'OCA) con scadenza passata: versate (D6)."""
        lines = self.env["abc.withholding.line"].search([
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", "passive"),
            ("historical", "=", True),
            ("payment_id", "=", False),
            ("kind", "=", "payment"),
            ("state", "=", "due"),
            ("is_contribution", "=", False),
            ("date_due", "<=", self.paid_until),
        ])
        count = self._abc_group_paid(lines)
        return self.env._("Quote marcate come versate: %(n)s, in %(p)s versamenti storici.",
                          n=len(lines), p=count)

    def _abc_group_paid(self, lines, dates=None):
        """Versamenti storici (senza scritture), uno per scadenza e mese: le quote risultano versate."""
        by_due = defaultdict(lambda: self.env["abc.withholding.line"])
        for line in lines:
            by_due[(line.date_due, line.period)] |= line
        Payment = self.env["abc.withholding.payment"]
        for (due, period), group in sorted(by_due.items(), key=lambda item: (item[0][0] or date.min, item[0][1] or "")):
            payment_date = max((dates or {}).get(l.id) or due or l.payment_date for l in group)
            payment = Payment.create({
                "company_id": self.company_id.id,
                "date": payment_date,
                "period": period,
                "historical": True,
                "note": self.env._("Versamento storico creato dalla ricostruzione del registro."),
            })
            group.write({"payment_id": payment.id})
            payment.with_context(abc_wh_auto=True).action_confirm()
        return len(by_due)

    # ------------------------------------------------------------------
    # Clienti migrati dalla 16: dati del modulo OCA l10n_it_withholding_tax
    # ------------------------------------------------------------------
    def _abc_table_columns(self, table):
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
        return {row[0] for row in self.env.cr.fetchall()}

    def _abc_import_oca(self):
        cr = self.env.cr
        for table in ("withholding_tax", "withholding_tax_statement", "withholding_tax_move"):
            cr.execute("SELECT to_regclass(%s)", (table,))
            if not cr.fetchone()[0]:
                return self.env._("Nessun dato del modulo OCA nel database: niente da importare.")
        company = self.company_id
        journal = company.abc_wh_journal_id
        if not journal:
            raise UserError(self.env._("Configurare il registro varie delle ritenute."))

        # Definizioni delle ritenute OCA (con causale, se il modulo delle causali c'era)
        wt_cols = self._abc_table_columns("withholding_tax")
        reason_join, reason_col = "", "NULL"
        # 16: l10n_it_withholding_tax_reason -> payment.reason; versioni precedenti: causale.pagamento
        for col, table in (("payment_reason_id", "payment_reason"), ("causale_pagamento_id", "causale_pagamento")):
            if col in wt_cols and "code" in self._abc_table_columns(table):
                reason_join = "LEFT JOIN %s cp ON cp.id = wt.%s" % (table, col)
                reason_col = "cp.code"
                break
        cr.execute("""
            SELECT wt.id, wt.name, wt.wt_types, wt.account_payable_id, wt.account_receivable_id, %s
              FROM withholding_tax wt %s
             WHERE wt.company_id = %%s
        """ % (reason_col, reason_join), (company.id,))
        definitions = {row[0]: row for row in cr.fetchall()}
        if not definitions:
            return self.env._("Nessuna ritenuta OCA per questa azienda.")

        cr.execute("""
            SELECT s.id, COALESCE(s.invoice_id, s.move_id), s.withholding_tax_id, s.base, s.tax
              FROM withholding_tax_statement s
             WHERE s.withholding_tax_id = ANY(%s)
        """, (list(definitions),))
        statements = cr.fetchall()
        cr.execute("""
            SELECT m.statement_id, m.id, m.date, m.state, m.amount, m.wt_account_move_id, m.reconcile_partial_id,
                   m.account_move_id
              FROM withholding_tax_move m
             WHERE m.statement_id = ANY(%s)
             ORDER BY m.date, m.id
        """, ([s[0] for s in statements],))
        statement_invoice = {s[0]: s[1] for s in statements}
        oca_moves = defaultdict(list)
        skipped = 0
        for row in cr.fetchall():
            # Solo movimenti nati da un pagamento vero: quelli senza pagamento, o con la fattura
            # stessa al posto del pagamento, sono residui di migrazioni o rigenerazioni
            if not row[7] or row[7] == statement_invoice.get(row[0]):
                skipped += 1
                continue
            oca_moves[row[0]].append(row[:7])

        Wh = self.env["abc.withholding"].sudo()
        Line = self.env["abc.withholding.line"].sudo()
        already = set(Wh.search([("legacy_statement_id", ">", 0)]).mapped("legacy_statement_id"))
        invoices = self.env["account.move"].browse({s[1] for s in statements if s[1]}).exists()
        wt_total = defaultdict(float)
        for st_id, move_id, _wt, _base, tax in statements:
            wt_total[move_id] += abs(tax or 0.0)

        created = Wh.browse()
        paid_lines = Line.browse()
        paid_dates = {}
        types = PASSIVE_TYPES + ACTIVE_TYPES
        for st_id, move_id, wt_id, base, tax in statements:
            invoice = invoices.filtered(lambda m: m.id == move_id)
            if st_id in already or not invoice or invoice.company_id != company \
                    or invoice.move_type not in types or invoice.state != "posted":
                continue
            moves = oca_moves.get(st_id, [])
            open_oca = any(m[3] == "due" for m in moves)
            if (invoice.invoice_date or invoice.date) < self.date_from and not open_oca \
                    and invoice.payment_state in ("paid", "reversed"):
                continue
            definition = definitions[wt_id]
            _id, name, wt_types, acc_payable, acc_receivable, reason = definition
            cycle = "passive" if invoice.move_type in PASSIVE_TYPES else "active"
            sign = -1 if invoice.move_type in ("in_refund", "out_refund") else 1
            wtype = self._abc_oca_type(wt_types, invoice.commercial_partner_id)
            total = abs(invoice.amount_total_signed)
            wh = Wh.create({
                "cycle": cycle,
                "company_id": company.id,
                "move_id": invoice.id,
                "partner_id": invoice.commercial_partner_id.id,
                "invoice_date": invoice.invoice_date or invoice.date,
                "accounting_date": invoice.date,
                "invoice_ref": invoice.ref,
                "invoice_total": total,
                "net_to_pay": total - wt_total[move_id],
                "withholding_type": wtype,
                "reason": reason or ("A" if wt_types == "ritenuta" else "ZO"),
                "is_contribution": wtype not in ("RT01", "RT02"),
                "rate": abs(tax / base * 100.0) if base else 0.0,
                "base_amount": sign * abs(base or 0.0),
                "amount": sign * abs(tax or 0.0),
                "final_account_id": (acc_payable if cycle == "passive" else acc_receivable) or False,
                "legacy_tax_name": name,
                "legacy_statement_id": st_id,
            })
            wh.tributo_code = wh._abc_default_tributo()
            created |= wh
            for _st, _m, oca_date, oca_state, oca_amount, wt_move_id, partial_id in moves:
                if not oca_date:
                    continue
                partial = self.env["account.partial.reconcile"].browse(partial_id).exists() if partial_id \
                    else self.env["account.partial.reconcile"]
                amount = sign * abs(oca_amount or 0.0)
                ratio = amount / wh.amount if wh.amount else 0.0
                if cycle == "active" and company.abc_wh_income_type == "business":
                    fiscal_year = wh.invoice_date.year
                else:
                    fiscal_year = oca_date.year
                line = Line.create({
                    "withholding_id": wh.id,
                    "kind": "payment",
                    "partial_id": partial.id or False,
                    "payment_date": oca_date,
                    "paid_amount": abs(wh.net_to_pay * ratio),
                    "amount": amount,
                    "base_amount": wh.currency_id.round(wh.base_amount * ratio),
                    "state": "due" if cycle == "passive" else "suffered",
                    "fiscal_year": fiscal_year,
                    "historical": True,
                    "transfer_move_id": wt_move_id if wt_move_id and
                    self.env["account.move"].browse(wt_move_id).exists() else False,
                })
                if cycle == "passive" and oca_state == "paid" and not wh.is_contribution:
                    paid_lines |= line
            self._abc_absorb_oca_rounding(wh, moves, invoice)
            self._abc_split_oca_residual(wh, journal)
        groups = self._abc_group_paid(paid_lines, paid_dates) if paid_lines else 0
        return self.env._(
            "Storico OCA: %(n)s ritenute importate, %(p)s quote gia' versate in %(g)s versamenti storici; "
            "%(s)s movimenti OCA scartati perche' senza pagamento.",
            n=len(created), p=len(paid_lines), g=groups, s=skipped)

    def _abc_absorb_oca_rounding(self, wh, moves, invoice):
        """L'OCA arrotonda ogni movimento: il centesimo di differenza va sull'ultima quota."""
        residual = wh.residual_amount
        last = wh.line_ids.sorted(lambda l: (l.payment_date, l.id))[-1:]
        if not last or wh.currency_id.is_zero(residual):
            return
        fully_paid = invoice.payment_state in ("paid", "in_payment") and not any(m[3] == "due" for m in moves)
        if fully_paid or abs(residual) <= 0.05 or residual * wh.amount < 0:
            last.amount += residual

    def _abc_oca_type(self, wt_types, partner):
        if wt_types == "enasarco":
            return "RT04"
        if wt_types == "inps":
            return "RT03"
        if wt_types == "enpam":
            return "RT05"
        if wt_types == "other":
            return "RT06"
        fiscal = (partner.l10n_it_codice_fiscale or "").strip()
        return "RT01" if len(fiscal) == 16 and not fiscal.isdigit() else "RT02"

    def _abc_split_oca_residual(self, wh, journal):
        """Fattura OCA non ancora pagata del tutto: la ritenuta residua diventa una riga a parte.

        Nella 16 il debito verso il fornitore e' un'unica scadenza al lordo. La parte di ritenuta
        ancora aperta viene spostata su una riga separata dello stesso fornitore, cosi'
        "Registra pagamento" propone il netto e al pagamento il modulo storna la ritenuta.
        """
        residual = wh.residual_amount
        currency = wh.currency_id
        if currency.is_zero(residual) or wh.partner_line_id or residual * wh.amount <= 0:
            return
        term = wh.move_id.line_ids.filtered(
            lambda l: l.display_type == "payment_term" and not l.reconciled)[:1]
        if not term or currency.compare_amounts(abs(term.amount_residual), abs(residual)) < 0:
            wh.message_post(body=self.env._(
                "Storico OCA: ritenuta residua %.2f non separata, la scadenza della fattura non ha "
                "un importo aperto sufficiente. Verificare a mano.", residual))
            return
        amount = abs(residual)
        # Passivo: la scadenza e' in avere, si chiude con un dare; attivo il contrario
        close_debit = term.balance < 0
        label = self.env._("Ritenuta %s: separazione dalla scadenza (storico OCA)", wh.move_id.name)
        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": wh.company_id.id,
            "date": self.migration_date or fields.Date.context_today(self),
            "ref": label,
            "line_ids": [
                Command.create({
                    "account_id": term.account_id.id, "partner_id": term.partner_id.id, "name": label,
                    "debit": amount if close_debit else 0.0, "credit": 0.0 if close_debit else amount,
                    "date_maturity": term.date_maturity,
                }),
                Command.create({
                    "account_id": term.account_id.id, "partner_id": term.partner_id.id, "name": label,
                    "debit": 0.0 if close_debit else amount, "credit": amount if close_debit else 0.0,
                    "date_maturity": term.date_maturity,
                }),
            ],
        })
        move.action_post()
        closing = move.line_ids.filtered(lambda l: (l.debit > 0) == close_debit)[:1]
        (closing + term).with_context(abc_wh_skip=True, no_cash_basis=True).reconcile()
        wh.partner_line_id = move.line_ids - closing

    def _abc_migrate_transit(self):
        """Fatture registrate con il conto d'appoggio: la ritenuta non pagata torna sul fornitore/cliente.

        Passivo: Dare conto d'appoggio / Avere fornitore. Attivo: Dare cliente / Avere conto d'appoggio.
        La riga sul fornitore/cliente diventa la riga ritenuta che il modulo chiude al pagamento.
        """
        journal = self.company_id.abc_wh_journal_id
        if not journal:
            raise UserError(self.env._("Configurare il registro varie delle ritenute."))
        withholdings = self.env["abc.withholding"].search([
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", self.cycle),
            ("state", "in", ("matured", "due", "suffered")),
            ("partner_line_id", "=", False),
        ])
        currency = self.company_id.currency_id
        moves = self.env["account.move"]
        for wh in withholdings:
            tax = wh.tax_id
            transit = wh.tax_line_id.account_id
            amount = wh.residual_amount
            if not tax.abc_wh_on_partner or currency.is_zero(amount) \
                    or transit.account_type in ("asset_receivable", "liability_payable"):
                continue
            partner = wh.partner_id.with_company(self.company_id)
            partner_account = partner.property_account_payable_id if wh.cycle == "passive" \
                else partner.property_account_receivable_id
            if not partner_account:
                continue
            # Importo positivo = fattura, negativo = nota di credito
            if wh.cycle == "passive":
                transit_debit = amount
            else:
                transit_debit = -amount
            label = self.env._("Ritenuta %s: passaggio dal conto d'appoggio", wh.move_id.name)
            move = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": self.company_id.id,
                "date": self.migration_date,
                "ref": label,
                "line_ids": [
                    Command.create({
                        "account_id": transit.id, "partner_id": wh.partner_id.id, "name": label,
                        "debit": max(transit_debit, 0.0), "credit": max(-transit_debit, 0.0),
                    }),
                    Command.create({
                        "account_id": partner_account.id, "partner_id": wh.partner_id.id, "name": label,
                        "debit": max(-transit_debit, 0.0), "credit": max(transit_debit, 0.0),
                    }),
                ],
            })
            move.action_post()
            wh.partner_line_id = move.line_ids.filtered(lambda l: l.account_id == partner_account)[:1]
            moves |= move
        if not moves:
            return self.env._("Nessuna ritenuta da riportare sul fornitore/cliente.")
        return self.env._("Scritture di passaggio dal conto d'appoggio: %s.", len(moves))
