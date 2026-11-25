from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    abc_wh_journal_id = fields.Many2one(
        "account.journal",
        string="Registro varie ritenute",
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Registro di tipo varie in cui, al pagamento o all'incasso, si registra la scrittura "
             "che storna la ritenuta dal fornitore (o dal cliente) e apre il debito (o il credito) "
             "verso l'Erario.",
    )
    abc_wh_penalty_account_id = fields.Many2one(
        "account.account", string="Conto sanzioni da ravvedimento", check_company=True,
        help="Usato da \"Registra scrittura F24\" quando il versamento ha sanzioni.")
    abc_wh_interest_account_id = fields.Many2one(
        "account.account", string="Conto interessi da ravvedimento", check_company=True,
        help="Usato da \"Registra scrittura F24\" quando il versamento ha interessi.")
    abc_wh_f24_journal_id = fields.Many2one(
        "account.journal", string="Registro predefinito per l'F24",
        domain="[('type', 'in', ('bank', 'cash', 'credit', 'general')), ('company_id', '=', id)]",
        help="Proposto nei nuovi versamenti per \"Registra scrittura F24\".")
    abc_wh_penalty_code = fields.Char(
        string="Codice tributo sanzioni", default="8906",
        help="Da verificare con lo studio sull'anno del versamento.",
    )
    abc_wh_interest_code = fields.Char(
        string="Codice tributo interessi", default="1989",
        help="Da verificare con lo studio sull'anno del versamento.",
    )
    abc_wh_threshold = fields.Monetary(
        string="Soglia di rinvio versamento", default=100.0,
        currency_field="currency_id",
        help="Sotto questa soglia mensile il wizard propone il rinvio; "
             "l'utente puo' sempre versare (D22). Zero = nessuna proposta.",
    )
    abc_wh_reminder_days = fields.Char(
        string="Giorni di preavviso", default="5,3,1,0",
        help="Giorni prima della scadenza in cui inviare il promemoria (D29).",
    )
    abc_wh_responsible_ids = fields.Many2many(
        "res.users", "abc_wh_company_responsible_rel", "company_id", "user_id",
        string="Responsabili ritenute",
        help="Ricevono promemoria di versamento e avvisi sulle CU.",
    )
    abc_wh_start_date = fields.Date(
        string="Data di avvio del registro",
        help="Le fatture con data precedente non generano ritenute in automatico; "
             "si recuperano con il wizard di ricostruzione dello storico.",
    )
    abc_wh_income_type = fields.Selection(
        [("business", "Impresa (credito per competenza)"),
         ("self_employed", "Lavoratore autonomo (credito per cassa)")],
        string="Regime per le ritenute subite",
        compute="_compute_abc_wh_income_type", store=True, readonly=False,
        help="Ricavato dalla forma giuridica (N2): le societa' hanno codice "
             "fiscale numerico di 11 cifre e sono sempre impresa.",
    )
    # Dati del sostituto d'imposta per CU e 770
    abc_wh_signer_name = fields.Char(string="Firmatario (cognome e nome)")
    abc_wh_signer_fiscalcode = fields.Char(string="Codice fiscale firmatario")
    abc_wh_signer_role_code = fields.Char(
        string="Codice carica firmatario",
        help="Codice carica secondo le istruzioni del modello (es. 1 = rappresentante legale).",
    )
    abc_wh_ateco_code = fields.Char(string="Codice attivita' (ATECO)")
    abc_wh_intermediary_fiscalcode = fields.Char(string="Codice fiscale intermediario")
    abc_wh_intermediary_caf = fields.Char(string="Numero iscrizione CAF / albo")
    abc_wh_intermediary_commit_date = fields.Date(string="Data impegno alla trasmissione")
    abc_wh_cu_forfettario_code = fields.Char(
        string="Codice somme non soggette - forfettari",
        help="Codice da indicare nella CU per i compensi a soggetti in regime "
             "forfettario o di vantaggio, secondo le istruzioni dell'anno (D58).",
    )
    abc_wh_cu_n1_code = fields.Char(
        string="Codice somme non soggette - spese art. 15",
        help="Codice da indicare nella CU per le spese anticipate in nome e per "
             "conto (righe con natura N1), secondo le istruzioni dell'anno (D59).",
    )

    @api.depends("vat", "partner_id.l10n_it_codice_fiscale")
    def _compute_abc_wh_income_type(self):
        for company in self:
            if company.abc_wh_income_type:
                company.abc_wh_income_type = company.abc_wh_income_type
                continue
            fiscal = (company.partner_id.l10n_it_codice_fiscale or company.vat or "").upper()
            if fiscal.startswith("IT"):
                fiscal = fiscal[2:]
            if len(fiscal) == 16 and not fiscal.isdigit():
                # Persona fisica: per default lavoratore autonomo, modificabile
                company.abc_wh_income_type = "self_employed"
            else:
                company.abc_wh_income_type = "business"
