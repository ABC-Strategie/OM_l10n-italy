# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date

REFUND_TYPES = ("out_refund", "in_refund")

# Chiave dell'avviso nel dizionario restituito da _get_alerts().
ABC_DATE_ALERT = "abc_invoice_date_before_last_posted"


class AccountMove(models.Model):
    _inherit = "account.move"

    abc_invoice_date_warning = fields.Text(
        string="Avviso data fattura",
        compute="_compute_abc_invoice_date_warning",
        help="Valorizzato quando la data fattura e' anteriore a quella dell'ultima "
             "fattura confermata della stessa serie. Solo informativo: non blocca la conferma.",
    )

    # -------------------------------------------------------------------------
    # Helper
    # -------------------------------------------------------------------------

    def _abc_date_check_applies(self):
        """True se il controllo sulla data si applica a questo documento.

        Il vincolo sullo stato bozza fa comparire l'avviso esattamente nei due
        momenti richiesti - creazione e reimpostazione a bozza - e lo fa sparire
        alla conferma. Le fatture fornitore sono escluse: la loro data fattura e'
        quella del fornitore e non segue la nostra numerazione.
        """
        self.ensure_one()
        return (
            self.state == "draft"
            and self.journal_id.abc_invoice_date_check
            and self.is_sale_document(include_receipts=True)
        )

    def _abc_series_domain(self):
        """Dominio dei documenti confermati della stessa serie, senza il periodo.

        Stesso registro e, se il registro ha la sequenza dedicata per le note di
        credito, fatture e note di credito separate: come in
        _get_last_sequence_domain del core.
        """
        self.ensure_one()
        domain = [
            ("journal_id", "=", self.journal_id.id),
            ("state", "=", "posted"),
        ]
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        if self.journal_id.refund_sequence:
            domain.append(
                ("move_type", "in" if self.move_type in REFUND_TYPES else "not in", REFUND_TYPES)
            )
        return domain

    def _abc_sequence_date_range(self, series_domain):
        """Inizio e fine del periodo di numerazione (anno o mese) del documento.

        La numerazione nativa riparte a ogni periodo, e la periodicita' si deduce
        dal formato di un numero della serie, come in _get_last_sequence_domain
        del core: il numero del documento se ne ha gia' uno (reimpostato a bozza),
        altrimenti l'ultimo confermato fino alla sua data, altrimenti il primo
        numero che Odoo assegnerebbe.
        """
        self.ensure_one()
        reference_name = self.name if self.name and self.name != "/" else False
        if not reference_name:
            reference_name = self.sudo().search(
                series_domain + [("date", "<=", self.date)], order="date desc, id desc", limit=1
            ).name
        if not reference_name:
            reference_name = self._get_starting_sequence()
        try:
            sequence_number_reset = self._deduce_sequence_number_reset(reference_name)
        except ValidationError:
            # Numero non interpretabile: nessun filtro sul periodo, piuttosto che
            # mandare in errore il form.
            sequence_number_reset = "never"
        date_start, date_end, *_dummy = self._get_sequence_date_range(sequence_number_reset)
        return date_start, date_end

    def _abc_last_posted_invoice(self):
        """L'ultimo documento confermato della stessa serie del numeratore.

        La serie e' quella con cui la numerazione nativa calcola il progressivo:
        stesso registro, stesso periodo di numerazione e, se il registro ha la
        sequenza dedicata per le note di credito, fatture e note di credito
        separate. Una fattura di fine anno registrata a gennaio prende il numero
        dell'anno precedente, quindi va confrontata solo con quell'anno.
        """
        self.ensure_one()
        series_domain = self._abc_series_domain()
        domain = series_domain + [("invoice_date", "!=", False)]
        if self.date:
            date_start, date_end = self._abc_sequence_date_range(series_domain)
            domain += [("date", ">=", date_start), ("date", "<=", date_end)]
        # sudo(): l'avviso deve essere affidabile anche quando le regole di record
        # nascondono documenti di altri utenti. Espone solo numero e data di un
        # documento dello stesso registro.
        return self.sudo().search(domain, order="invoice_date desc, id desc", limit=1)

    # -------------------------------------------------------------------------
    # Avviso
    # -------------------------------------------------------------------------

    @api.depends("state", "invoice_date", "date", "journal_id", "move_type",
                 "journal_id.abc_invoice_date_check")
    def _compute_abc_invoice_date_warning(self):
        for move in self:
            move.abc_invoice_date_warning = False
            if not move._abc_date_check_applies():
                continue
            # Sulle fatture cliente appena create la data fattura e' spesso vuota:
            # in quel caso vale la data contabile, che e' obbligatoria.
            move_date = move.invoice_date or move.date
            if not move_date:
                continue
            last = move._abc_last_posted_invoice()
            if last and move_date < last.invoice_date:
                move.abc_invoice_date_warning = _(
                    "La data fattura (%(date)s) e' anteriore a quella dell'ultima fattura "
                    "confermata del registro: %(last_name)s del %(last_date)s.\n"
                    "Per mantenere la numerazione cronologica, impostare una data dal "
                    "%(last_date)s in poi.",
                    date=format_date(self.env, move_date),
                    last_name=last.name or "/",
                    last_date=format_date(self.env, last.invoice_date),
                )

    @api.depends("abc_invoice_date_warning")
    def _compute_alerts(self):
        """EXTENDS account: aggiunge la dipendenza dal nostro avviso.

        Le _compute_alerts del core non dipendono da invoice_date, quindi senza
        questo override il banner non si aggiornerebbe alla modifica della data.
        Non serve ricopiare le depends del core: Field.get_depends usa resolve_mro,
        che raccoglie tutte le implementazioni del compute lungo la MRO e ne somma
        le @api.depends.
        """
        return super()._compute_alerts()

    def _get_alerts(self):
        """EXTENDS account: mostra l'avviso nel banner nativo della fattura."""
        alerts = super()._get_alerts()
        if self.abc_invoice_date_warning:
            alerts[ABC_DATE_ALERT] = {
                "level": "warning",
                "message": self.abc_invoice_date_warning,
            }
        return alerts
