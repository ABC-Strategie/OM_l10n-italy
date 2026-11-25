import base64
import logging

from lxml import etree

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

PASSIVE_TYPES = ("in_invoice", "in_refund")
ACTIVE_TYPES = ("out_invoice", "out_refund")
REFUND_TYPES = ("in_refund", "out_refund")
CONTRIBUTION_TYPES = ("RT03", "RT04", "RT05", "RT06")

CYCLES = [
    ("passive", "Passivo (operata sui fornitori)"),
    ("active", "Attivo (subita dai clienti)"),
]

# Causali CU (lavoro autonomo): stessi codici del campo l10n_it_withholding_reason di Odoo,
# con le descrizioni italiane delle istruzioni CU al posto delle etichette inglesi di l10n_it_edi.
WITHHOLDING_REASONS_IT = [
    ("A", "[A] Lavoro autonomo nell'esercizio abituale di arte o professione"),
    ("B", "[B] Utilizzazione economica da parte dell'autore o inventore di opere dell'ingegno, brevetti, "
          "processi, formule o informazioni"),
    ("C", "[C] Utili da associazione in partecipazione o cointeressenza con apporto di solo lavoro"),
    ("D", "[D] Utili spettanti ai soci promotori e ai soci fondatori di societa' di capitali"),
    ("E", "[E] Levata di protesti cambiari da parte dei segretari comunali"),
    ("G", "[G] Indennita' per cessazione di attivita' sportiva professionale"),
    ("H", "[H] Indennita' per cessazione di rapporti di agenzia (escluse quelle maturate entro il 31/12/2003 "
          "gia' tassate)"),
    ("I", "[I] Indennita' per cessazione da funzioni notarili"),
    ("K", "[K] Assegni di servizio civile universale (art. 16 D.Lgs. 40/2017)"),
    ("L", "[L] Utilizzazione economica di opere dell'ingegno, brevetti e simili da parte di soggetto diverso "
          "dall'autore o inventore"),
    ("L1", "[L1] Redditi da opere dell'ingegno, brevetti e simili percepiti da chi ha acquistato i diritti "
           "a titolo oneroso"),
    ("M", "[M] Lavoro autonomo non esercitato abitualmente, obblighi di fare, non fare o permettere"),
    ("M1", "[M1] Redditi da assunzione di obblighi di fare, non fare o permettere"),
    ("M2", "[M2] Lavoro autonomo non abituale con obbligo di iscrizione alla Gestione Separata INPS"),
    ("N", "[N] Indennita' di trasferta, rimborsi forfetari, premi e compensi per attivita' sportive "
          "dilettantistiche"),
    ("O", "[O] Lavoro autonomo non abituale senza obbligo di iscrizione alla Gestione Separata INPS"),
    ("O1", "[O1] Obblighi di fare, non fare o permettere senza obbligo di iscrizione alla Gestione Separata INPS"),
    ("P", "[P] Compensi a non residenti per l'uso o la concessione in uso di attrezzature industriali, "
          "commerciali o scientifiche in Italia"),
    ("Q", "[Q] Provvigioni ad agenti o rappresentanti di commercio monomandatari"),
    ("R", "[R] Provvigioni ad agenti o rappresentanti di commercio plurimandatari"),
    ("S", "[S] Provvigioni a commissionari"),
    ("T", "[T] Provvigioni a mediatori"),
    ("U", "[U] Provvigioni a procacciatori d'affari"),
    ("V", "[V] Provvigioni a incaricati delle vendite a domicilio e porta a porta"),
    ("V1", "[V1] Redditi da attivita' commerciali non esercitate abitualmente"),
    ("V2", "[V2] Prestazioni non abituali degli incaricati delle vendite a domicilio"),
    ("W", "[W] Corrispettivi per contratti d'appalto (art. 25-ter D.P.R. 600/1973)"),
    ("X", "[X] Canoni a societa' o stabili organizzazioni estere (art. 26-quater, c. 1, lett. a) e b) "
          "D.P.R. 600/1973)"),
    ("Y", "[Y] Canoni dal 01/01/2005 al 26/07/2005 a soggetti diversi dalla causale X"),
    ("Z", "[Z] Causale non piu' in uso"),
    ("ZO", "[ZO] Titolo diverso dai precedenti"),
]

STATES = [
    ("matured", "Maturata"),
    ("due", "Dovuta"),
    ("paid", "Versata"),
    ("suffered", "Subita"),
    ("certified", "Certificata"),
    ("deducted", "Scomputata"),
    ("not_operated", "Non operata"),
    ("offset", "Compensata con nota di credito"),
    ("cancelled", "Annullata"),
]


def _xp(tree, path):
    """XPath senza namespace sui nomi dei tag FatturaPA."""
    expr = "//" + "/".join('*[local-name()="%s"]' % part for part in path.split("/"))
    return tree.xpath(expr)


def _txt(node, tag):
    """Testo di un figlio diretto, indipendente dal namespace."""
    return (node.xpath('string(*[local-name()="%s"])' % tag) or "").strip()


class AbcWithholding(models.Model):
    _name = "abc.withholding"
    _description = "Ritenuta d'acconto"
    _inherit = ["mail.thread"]
    _order = "invoice_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Riferimento", compute="_compute_name", store=True)
    cycle = fields.Selection(CYCLES, string="Ciclo", required=True, index=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    move_id = fields.Many2one(
        "account.move", string="Fattura", required=True, index=True, ondelete="cascade",
        check_company=True,
    )
    move_type = fields.Selection(related="move_id.move_type", store=True, string="Tipo documento")
    tax_line_id = fields.Many2one("account.move.line", string="Riga ritenuta", ondelete="cascade", index=True)
    partner_line_id = fields.Many2one(
        "account.move.line", string="Riga ritenuta sul conto fornitore/cliente", index=True,
        help="Parte del debito (o del credito) che al pagamento viene stornata verso l'Erario. "
             "E' la riga ritenuta della fattura oppure, per le fatture registrate prima del modulo, "
             "la riga creata dalla ricostruzione dello storico.")
    tax_id = fields.Many2one(
        "account.tax", string="Imposta ritenuta", check_company=True,
        help="Vuota per le ritenute importate dal modulo OCA della versione 16.")
    legacy_tax_name = fields.Char(string="Ritenuta OCA (v16)", readonly=True)
    legacy_statement_id = fields.Integer(string="Id dichiarazione OCA", readonly=True, index=True)
    final_account_id = fields.Many2one(
        "account.account", string="Conto erariale", check_company=True,
        help="Conto su cui nasce il debito (o il credito) verso l'Erario al pagamento: "
             "Erario c/ritenute da versare, Debiti previdenziali, Crediti per ritenute subite.")
    partner_id = fields.Many2one("res.partner", string="Fornitore / Cliente", index=True)
    partner_vat = fields.Char(related="partner_id.vat", string="Partita IVA")
    partner_fiscalcode = fields.Char(related="partner_id.l10n_it_codice_fiscale", string="Codice fiscale")
    invoice_date = fields.Date(string="Data fattura")
    accounting_date = fields.Date(string="Data registrazione")
    invoice_ref = fields.Char(string="Riferimento fornitore")
    invoice_total = fields.Monetary(string="Totale documento")
    net_to_pay = fields.Monetary(string="Netto a pagare")
    withholding_type = fields.Char(string="Tipo (RT)")
    reason = fields.Char(string="Causale")
    tributo_code = fields.Char(string="Codice tributo")
    is_contribution = fields.Boolean(string="Contributo previdenziale")
    is_final = fields.Boolean(string="A titolo d'imposta")
    rate = fields.Float(string="Aliquota %")
    base_amount = fields.Monetary(string="Imponibile ritenuta")
    amount = fields.Monetary(string="Importo ritenuta")
    n1_amount = fields.Monetary(
        string="Spese non soggette (N1)",
        help="Spese anticipate in nome e per conto lette dall'XML (D59).",
    )
    xml_amount = fields.Monetary(string="Importo ritenuta da XML")
    xml_mismatch = fields.Boolean(string="Differenza con l'XML", index=True)
    possible_not_operated = fields.Boolean(
        string="Possibile ritenuta non operata",
        help="Il cliente sembra aver pagato il lordo (D42).",
    )
    line_ids = fields.One2many("abc.withholding.line", "withholding_id", string="Quote")
    allocated_amount = fields.Monetary(string="Quote generate", compute="_compute_amounts", store=True)
    residual_amount = fields.Monetary(string="Ancora da pagare/incassare", compute="_compute_amounts", store=True)
    state = fields.Selection(STATES, string="Stato", compute="_compute_state", store=True, index=True)

    @api.depends("move_id.name", "tax_id.name", "legacy_tax_name")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s" % (rec.move_id.name or "", rec.tax_id.name or rec.legacy_tax_name or "")

    @api.depends("amount", "line_ids.amount")
    def _compute_amounts(self):
        for rec in self:
            rec.allocated_amount = sum(rec.line_ids.mapped("amount"))
            rec.residual_amount = rec.amount - rec.allocated_amount

    @api.depends("cycle", "residual_amount", "line_ids.state", "line_ids.kind", "move_id.state")
    def _compute_state(self):
        active_order = ["suffered", "certified", "deducted"]
        for rec in self:
            payments = rec.line_ids.filtered(lambda l: l.kind == "payment")
            settled = rec.currency_id.is_zero(rec.residual_amount)
            if rec.move_id.state == "cancel":
                rec.state = "cancelled"
            elif rec.cycle == "passive":
                if payments.filtered(lambda l: l.state == "due"):
                    rec.state = "due"
                elif settled and rec.line_ids:
                    rec.state = "paid" if payments else "offset"
                else:
                    rec.state = "matured"
            else:
                operated = payments.filtered(lambda l: l.state != "not_operated")
                if not payments:
                    rec.state = "offset" if settled and rec.line_ids else "matured"
                elif not operated:
                    rec.state = "not_operated"
                else:
                    rec.state = min(operated.mapped("state"), key=active_order.index)

    # ------------------------------------------------------------------
    # Creazione dalle fatture
    # ------------------------------------------------------------------
    @api.model
    def _abc_create_from_moves(self, moves, force=False):
        """Crea le testate per le righe di ritenuta delle fatture confermate."""
        created = self.browse()
        for move in moves:
            if move.state != "posted" or move.move_type not in PASSIVE_TYPES + ACTIVE_TYPES:
                continue
            start = move.company_id.abc_wh_start_date
            ref_date = move.invoice_date or move.date
            if not force and start and ref_date and ref_date < start:
                continue
            tree = self._abc_get_einvoice_tree(move) if move.move_type in PASSIVE_TYPES else None
            if tree is not None:
                self._abc_update_partner_from_xml(move, tree)
            tax_lines = move.line_ids.filtered(
                lambda l: l.display_type == "tax" and l.tax_line_id and l.tax_line_id._abc_wh_is_withholding()
            )
            if not tax_lines:
                continue
            existing = self.sudo().search([("tax_line_id", "in", tax_lines.ids)])
            tax_lines -= existing.tax_line_id
            if not tax_lines:
                continue
            cycle = "passive" if move.move_type in PASSIVE_TYPES else "active"
            sign = -1 if move.move_type in REFUND_TYPES else 1
            net = sum(abs(l.balance) for l in move.line_ids if l.display_type == "payment_term")
            vals_list = []
            for line in tax_lines:
                tax = line.tax_line_id
                wtype = tax.l10n_it_withholding_type
                vals_list.append({
                    "cycle": cycle,
                    "company_id": move.company_id.id,
                    "move_id": move.id,
                    "tax_line_id": line.id,
                    "partner_line_id": line.id if line._abc_is_partner_withholding_line() else False,
                    "tax_id": tax.id,
                    "final_account_id": tax._abc_wh_final_account(refund=move.move_type in REFUND_TYPES).id,
                    "partner_id": move.commercial_partner_id.id,
                    "invoice_date": move.invoice_date or move.date,
                    "accounting_date": move.date,
                    "invoice_ref": move.ref,
                    "invoice_total": abs(move.amount_total_signed),
                    "net_to_pay": net,
                    "withholding_type": wtype,
                    "reason": tax.l10n_it_withholding_reason or False,
                    "is_contribution": wtype in CONTRIBUTION_TYPES,
                    "is_final": tax.abc_wh_final,
                    "rate": abs(tax.amount),
                    "base_amount": sign * abs(line.tax_base_amount),
                    "amount": sign * abs(line.balance),
                })
            records = self.sudo().create(vals_list)
            if tree is not None:
                records._abc_apply_xml(tree)
            for rec in records:
                rec.tributo_code = rec._abc_default_tributo()
            created |= records
        return created

    def _abc_default_tributo(self):
        self.ensure_one()
        if self.tax_id and self.tax_id.abc_wh_tributo_code:
            return self.tax_id.abc_wh_tributo_code
        if self.is_contribution:
            # ENASARCO e casse: non si versano con il codice tributo erariale
            return False
        code = self.env["abc.withholding.tributo.map"].sudo()._abc_get_code(
            self.reason, self.withholding_type, self.company_id)
        if code:
            return code
        return "1040" if self.withholding_type in ("RT01", "RT02") else False

    # ------------------------------------------------------------------
    # Lettura della fattura elettronica (D9, D10, D58, D59)
    # ------------------------------------------------------------------
    @api.model
    def _abc_get_einvoice_tree(self, move):
        move = move.sudo()
        content, name = None, ""
        if move.l10n_it_edi_attachment_file:
            content = base64.b64decode(move.l10n_it_edi_attachment_file)
            name = move.l10n_it_edi_attachment_name or ""
        else:
            attachment = self.env["ir.attachment"].sudo().search([
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                "|", ("name", "=ilike", "%.xml"), ("name", "=ilike", "%.xml.p7m"),
            ], order="id desc", limit=1)
            if attachment:
                content, name = attachment.raw, attachment.name or ""
        if not content:
            return None
        if name.lower().endswith(".p7m"):
            try:
                from odoo.addons.l10n_it_edi.tools.remove_signature import remove_signature
                content = remove_signature(content)
            except Exception:  # noqa: BLE001 - firma non decodificabile: si salta il controllo
                _logger.info("Fattura %s: impossibile leggere il file firmato", move.name)
                return None
        try:
            parser = etree.XMLParser(recover=True, resolve_entities=False)
            return etree.fromstring(content, parser)
        except Exception:  # noqa: BLE001
            return None

    @api.model
    def _abc_update_partner_from_xml(self, move, tree):
        regime = _xp(tree, "CedentePrestatore/DatiAnagrafici/RegimeFiscale")
        if not regime:
            return
        value = (regime[0].text or "").strip()
        partner = move.commercial_partner_id.sudo()
        flat = value in ("RF19", "RF02")
        if partner.abc_wh_tax_regime != value or partner.abc_wh_flat_rate != flat:
            partner.write({"abc_wh_tax_regime": value, "abc_wh_flat_rate": flat})

    def _abc_apply_xml(self, tree):
        """Confronta l'importo con l'XML e prende la causale dall'XML."""
        xml_by_type, reason_by_type = {}, {}
        for node in _xp(tree, "DatiGeneraliDocumento/DatiRitenuta"):
            wtype = _txt(node, "TipoRitenuta")
            try:
                amount = float(_txt(node, "ImportoRitenuta") or 0.0)
            except ValueError:
                amount = 0.0
            xml_by_type[wtype] = xml_by_type.get(wtype, 0.0) + amount
            reason = _txt(node, "CausalePagamento")
            if reason:
                reason_by_type.setdefault(wtype, reason)
        n1_total = 0.0
        for line in _xp(tree, "DettaglioLinee"):
            if _txt(line, "Natura").startswith("N1"):
                try:
                    n1_total += float(_txt(line, "PrezzoTotale") or 0.0)
                except ValueError:
                    continue
        mismatched = self.browse()
        for wtype in set(self.mapped("withholding_type")):
            group = self.filtered(lambda r: r.withholding_type == wtype)
            odoo_amount = sum(abs(a) for a in group.mapped("amount"))
            xml_amount = xml_by_type.get(wtype, 0.0)
            different = float_compare(odoo_amount, xml_amount, precision_digits=2) != 0
            group.write({"xml_amount": xml_amount, "xml_mismatch": different})
            if reason_by_type.get(wtype):
                group.write({"reason": reason_by_type[wtype]})
            if different:
                mismatched |= group
        main = self.filtered(lambda r: not r.is_contribution)[:1]
        if main and n1_total:
            main.n1_amount = n1_total
        for move in mismatched.move_id:
            recs = mismatched.filtered(lambda r: r.move_id == move)
            move.message_post(body=self.env._(
                "Attenzione: l'importo della ritenuta nel file XML (%(xml)s) e' diverso da quello "
                "calcolato da Odoo (%(odoo)s). Controllare la fattura prima del pagamento.",
                xml="%.2f" % sum(recs.mapped("xml_amount")),
                odoo="%.2f" % sum(abs(a) for a in recs.mapped("amount")),
            ))

    # ------------------------------------------------------------------
    # Quote: nascono dalle riconciliazioni (pagamenti, incassi, note di credito)
    # ------------------------------------------------------------------
    @api.model
    def _abc_process_partial(self, partial, transfer=True):
        for own, counterpart in ((partial.debit_move_id, partial.credit_move_id),
                                 (partial.credit_move_id, partial.debit_move_id)):
            if own.display_type != "payment_term":
                continue
            docs = self.sudo().search([("move_id", "=", own.move_id.id), ("state", "!=", "cancelled")])
            for doc in docs:
                if doc.line_ids.filtered(lambda l: l.partial_id == partial):
                    continue
                # Scritture del modulo (o dell'OCA) gia' note: non sono pagamenti
                if counterpart.move_id in (doc.line_ids.transfer_move_id | doc.partner_line_id.move_id):
                    continue
                doc._abc_allocate(partial, counterpart, transfer=transfer)

    def _abc_allocate(self, partial, counterpart, transfer=True):
        self.ensure_one()
        currency = self.currency_id
        net = self.net_to_pay
        if currency.is_zero(net) or currency.is_zero(self.amount):
            return self.env["abc.withholding.line"]
        paid = partial.amount
        counter_move = counterpart.move_id
        same_cycle = PASSIVE_TYPES if self.cycle == "passive" else ACTIVE_TYPES
        kind = "offset" if counter_move.move_type in same_cycle else "payment"
        previous_paid = sum(self.line_ids.mapped("paid_amount"))
        if float_compare(previous_paid + paid, net, precision_rounding=currency.rounding) >= 0:
            amount = self.amount - sum(self.line_ids.mapped("amount"))
        else:
            amount = currency.round(self.amount * paid / net)
        if currency.is_zero(amount):
            return self.env["abc.withholding.line"]
        ratio = amount / self.amount
        pay_date = counterpart.date or partial.max_date
        if kind == "offset":
            state = "offset"
        else:
            state = "due" if self.cycle == "passive" else "suffered"
        if self.cycle == "active" and self.company_id.abc_wh_income_type == "business":
            fiscal_year = (self.invoice_date or pay_date).year
        else:
            fiscal_year = pay_date.year
        line = self.env["abc.withholding.line"].sudo().create({
            "withholding_id": self.id,
            "kind": kind,
            "partial_id": partial.id,
            "counterpart_move_id": counter_move.id,
            "payment_date": pay_date,
            "paid_amount": paid,
            "amount": amount,
            "base_amount": currency.round(self.base_amount * ratio),
            "n1_amount": currency.round(self.n1_amount * ratio),
            "state": state,
            "fiscal_year": fiscal_year,
            "historical": not transfer,
        })
        if kind == "payment" and transfer:
            line._abc_create_settlement()
        elif kind == "offset":
            self._abc_reconcile_offset(counter_move)
        return line

    def _abc_reconcile_offset(self, counter_move):
        """Nota di credito compensata con la fattura: si compensano anche le righe ritenuta."""
        self.ensure_one()
        counter_docs = self.sudo().search([
            ("move_id", "=", counter_move.id),
            ("withholding_type", "=", self.withholding_type),
        ])
        lines = (self.partner_line_id | counter_docs.partner_line_id).filtered(
            lambda l: not l.reconciled and l.account_id == self.partner_line_id.account_id)
        if self.partner_line_id in lines and len(lines) > 1:
            lines.with_context(no_cash_basis=True).reconcile()

    def action_not_operated(self):
        """Il cliente ha pagato il lordo senza trattenere: il credito verso l'Erario non nasce (D42).

        Si storna la scrittura della ritenuta: la riga ritenuta sul conto del cliente resta
        chiusa dall'incasso del lordo.
        """
        for rec in self.filtered(lambda r: r.cycle == "active"):
            lines = rec.line_ids.filtered(lambda l: l.kind == "payment" and l.state == "suffered")
            if not lines:
                continue
            lines._abc_reverse_transfer()
            lines.write({"state": "not_operated"})
            rec.possible_not_operated = False
            rec.message_post(body=self.env._(
                "Ritenuta segnata come non operata dal cliente: stornata la scrittura della ritenuta."))
        return True

    def _abc_remove(self):
        """Elimina testate e quote quando la fattura torna in bozza o viene annullata."""
        lines = self.line_ids
        lines._abc_reverse_transfer()
        lines.with_context(abc_wh_force_unlink=True).sudo().unlink()
        self.sudo().unlink()

    def action_open_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }
