# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.base_provider import ESITO_VALIDO
from ..tools import codice_fiscale as cf_tools
from ..tools import denominazione as den_tools
from ..tools.sanitize import sanitize_text

# Nome del campo sorgente del codice fiscale. In Odoo 19 è definito dal
# modulo l10n_it_edi (Char, size 16). Il modulo dipende da l10n_it_edi, ma
# ogni accesso passa da _abc_va_cf_field_name() così che, se il campo
# venisse rinominato o assente, la logica degradi senza errori invece di
# fallire.
CF_FIELD_NAME = 'l10n_it_codice_fiscale'
# Campo sorgente della partita IVA (base)
VAT_FIELD_NAME = 'vat'

STATE_SELECTION = [
    ('not_verified', 'Non verificato'),
    ('pending', 'In attesa di verifica'),
    ('valid', 'Valido'),
    ('invalid', 'Non valido'),
    ('error', 'Errore'),
    ('not_applicable', 'Non applicabile'),
]

PIVA_STATE_SELECTION = [
    ('not_verified', 'Non verificata'),
    ('pending', 'In attesa di verifica'),
    ('valid', 'Valida'),
    ('ceased', 'Cessata/sospesa'),
    ('invalid', 'Non valida'),
    ('error', 'Errore'),
    ('not_applicable', 'Non applicabile'),
]

NAME_MATCH_SELECTION = [
    ('match', 'Corrispondente'),
    ('mismatch', 'Non corrispondente'),
]

# Campi di esito per tipo di verifica: la logica di coda e UI è generica
KIND_FIELDS = {
    'cf': {
        'state': 'abc_va_state',
        'message': 'abc_va_message',
        'checked': 'abc_va_checked_value',
        'last': 'abc_va_last_check',
    },
    'piva': {
        'state': 'abc_va_piva_state',
        'message': 'abc_va_piva_message',
        'checked': 'abc_va_piva_checked_value',
        'last': 'abc_va_piva_last_check',
    },
}
KIND_LABELS = {'cf': 'codice fiscale', 'piva': 'partita IVA'}

GROUP_USER = 'abc_verifica_anagrafica.group_abc_va_user'
GROUP_MANAGER = 'abc_verifica_anagrafica.group_abc_va_manager'

# Context flag: impedisce che le scritture interne del modulo (esiti) o
# operazioni programmatiche (es. import massivi) inneschino nuove verifiche.
SKIP_TRIGGER = 'abc_va_skip_trigger'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Codice fiscale
    # ------------------------------------------------------------------
    abc_va_state = fields.Selection(
        selection=STATE_SELECTION,
        string='Verifica CF',
        default='not_verified',
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
        help="Esito della verifica del codice fiscale presso il provider "
             "configurato. 'Non applicabile' per soggetti diversi da persona "
             "fisica o senza codice fiscale.",
    )
    abc_va_last_check = fields.Datetime(
        string='Ultima verifica CF',
        readonly=True,
        copy=False,
    )
    abc_va_message = fields.Char(
        string='Esito verifica CF',
        readonly=True,
        copy=False,
        help="Esito leggibile dell'ultima verifica. Non contiene mai il "
             "payload grezzo della risposta.",
    )
    abc_va_checked_value = fields.Char(
        string='CF verificato',
        readonly=True,
        copy=False,
        help="Valore del codice fiscale su cui è stato dato l'esito. Se il "
             "codice fiscale cambia, l'esito precedente non è più valido.",
    )

    # ------------------------------------------------------------------
    # Partita IVA
    # ------------------------------------------------------------------
    abc_va_piva_state = fields.Selection(
        selection=PIVA_STATE_SELECTION,
        string='Verifica P.IVA',
        default='not_verified',
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
        help="Esito della verifica della partita IVA italiana presso il "
             "provider configurato. 'Cessata/sospesa' se esistente ma con "
             "attività cessata o sospesa.",
    )
    abc_va_piva_last_check = fields.Datetime(
        string='Ultima verifica P.IVA',
        readonly=True,
        copy=False,
    )
    abc_va_piva_message = fields.Char(
        string='Esito verifica P.IVA',
        readonly=True,
        copy=False,
    )
    abc_va_piva_checked_value = fields.Char(
        string='P.IVA verificata',
        readonly=True,
        copy=False,
    )
    abc_va_piva_denominazione = fields.Char(
        string='Denominazione AdE',
        readonly=True,
        copy=False,
        help="Denominazione del titolare della partita IVA secondo "
             "l'Anagrafe Tributaria.",
    )
    abc_va_piva_name_match = fields.Selection(
        selection=NAME_MATCH_SELECTION,
        string='Confronto denominazione',
        readonly=True,
        copy=False,
        help="Esito del confronto tra il nome del contatto e la "
             "denominazione AdE (forma giuridica, punteggiatura e ordine "
             "delle parole sono ignorati).",
    )
    abc_va_piva_start_date = fields.Date(
        string='Inizio attività (AdE)', readonly=True, copy=False)
    abc_va_piva_end_date = fields.Date(
        string='Cessazione attività (AdE)', readonly=True, copy=False)
    abc_va_piva_suspended_date = fields.Date(
        string='Sospensione attività (AdE)', readonly=True, copy=False)

    # ==================================================================
    # Accesso ai valori sorgente con degradazione
    # ==================================================================
    @api.model
    def _abc_va_cf_field_name(self):
        """Nome del campo codice fiscale, o None se assente sul modello."""
        return CF_FIELD_NAME if CF_FIELD_NAME in self._fields else None

    def _abc_va_get_cf(self):
        """Codice fiscale normalizzato (maiuscolo, senza spazi) o ''."""
        self.ensure_one()
        field_name = self._abc_va_cf_field_name()
        if not field_name:
            return ''
        value = self[field_name] or ''
        return ''.join(value.split()).upper()

    def _abc_va_get_piva(self):
        """Partita IVA italiana normalizzata a 11 cifre, o '' se assente o
        non italiana."""
        self.ensure_one()
        value = ''.join((self[VAT_FIELD_NAME] or '').split()).upper()
        if not value:
            return ''
        country_code = self.country_id.code
        if value.startswith('IT'):
            value = value[2:]
        elif country_code and country_code != 'IT':
            return ''
        return value if value.isdigit() and len(value) == 11 else ''

    def _abc_va_get_value(self, kind='cf'):
        return self._abc_va_get_cf() if kind == 'cf' else self._abc_va_get_piva()

    def _abc_va_is_applicable(self, kind='cf'):
        """True se il soggetto rientra nell'ambito della verifica.

        Codice fiscale: persone fisiche (non società), contatti principali
        (non indirizzi o contatti figli), con codice fiscale alfanumerico a
        16 caratteri. Un codice numerico a 11 cifre identifica un'impresa o
        un ente e non è oggetto di questa verifica.
        Partita IVA: qualunque contatto principale con partita IVA italiana
        di 11 cifre (aziende, enti, ditte individuali e professionisti).
        """
        self.ensure_one()
        if self.parent_id:
            return False
        if kind == 'piva':
            return bool(self._abc_va_get_piva())
        if self.is_company:
            return False
        cf = self._abc_va_get_cf()
        return len(cf) == 16 and cf.isalnum()

    def _abc_va_state(self, kind='cf'):
        self.ensure_one()
        return self[KIND_FIELDS[kind]['state']]

    def _abc_va_is_outdated(self, kind='cf'):
        """True se l'esito registrato si riferisce a un valore diverso da
        quello attuale."""
        self.ensure_one()
        checked = self[KIND_FIELDS[kind]['checked']]
        return bool(checked and checked != self._abc_va_get_value(kind))

    def _abc_va_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _abc_va_kind_enabled(self, company, kind):
        company = company.sudo()
        if not company.abc_va_enabled:
            return False
        return company.abc_va_piva_enabled if kind == 'piva' else True

    # ==================================================================
    # Coerenza tra le prime sei lettere del CF e il nome
    # ==================================================================
    def _abc_va_name_check_result(self):
        """Ritorna ``(ok, expected)`` dal controllo di coerenza tra codice
        fiscale e nome (vedi tools.codice_fiscale.name_matches)."""
        self.ensure_one()
        return cf_tools.name_matches(self._abc_va_get_cf(), self.name)

    def _abc_va_name_mismatch_message(self, expected):
        self.ensure_one()
        cf = self._abc_va_get_cf()
        return _(
            "Le prime sei lettere del codice fiscale (%(found)s) non sono "
            "coerenti con il nome '%(name)s': attese ad esempio %(expected)s. "
            "Verificare il codice fiscale oppure scrivere cognome e nome "
            "come risultano all'Anagrafe.",
            found=cf[:6], name=self.name,
            expected=' o '.join(expected[:2]),
        )

    @api.constrains('l10n_it_codice_fiscale', 'name', 'is_company', 'parent_id')
    def _check_abc_va_name_consistency(self):
        if self.env.context.get(SKIP_TRIGGER) or not self._abc_va_cf_field_name():
            return
        for partner in self:
            if not partner._abc_va_is_applicable():
                continue
            if partner._abc_va_company().sudo().abc_va_name_check != 'block':
                continue
            ok, expected = partner._abc_va_name_check_result()
            if not ok:
                raise ValidationError(partner._abc_va_name_mismatch_message(expected))

    # ==================================================================
    # Scrittura dell'esito
    # ==================================================================
    def _abc_va_apply_result(self, state, message, value, kind='cf', extra=None):
        """Scrive l'esito sul partner senza innescare nuove verifiche."""
        names = KIND_FIELDS[kind]
        vals = {
            names['state']: state,
            names['message']: sanitize_text(message, self._abc_va_secrets())[:500] or False,
            names['checked']: value or False,
            names['last']: fields.Datetime.now(),
        }
        if extra:
            vals.update(extra)
        self.sudo().with_context(**{SKIP_TRIGGER: True}).write(vals)

    def _abc_va_reset(self, state='pending', kind='cf'):
        """Azzera l'esito precedente (il valore è cambiato o è richiesta una
        nuova verifica). Il passaggio intermedio non viene tracciato nel
        chatter: vi compare solo l'esito finale."""
        names = KIND_FIELDS[kind]
        vals = {
            names['state']: state,
            names['message']: False,
            names['checked']: False,
            names['last']: False,
        }
        if kind == 'piva':
            vals.update({
                'abc_va_piva_denominazione': False,
                'abc_va_piva_name_match': False,
                'abc_va_piva_start_date': False,
                'abc_va_piva_end_date': False,
                'abc_va_piva_suspended_date': False,
            })
        self.sudo().with_context(**{SKIP_TRIGGER: True}, mail_notrack=True).write(vals)

    def _abc_va_apply_piva_outcome(self, esito, message, value, dati):
        """Applica l'esito di una verifica di partita IVA riuscita
        (valida o non valida), con i dati strutturati del provider:
        stato ``ceased`` se cessata o sospesa, confronto denominazione.
        Ritorna lo stato applicato."""
        self.ensure_one()
        dati = dati or {}
        if esito != ESITO_VALIDO:
            self._abc_va_apply_result(
                'invalid',
                _("Partita IVA non riscontrata in Anagrafe Tributaria: %s", message or ''),
                value, kind='piva',
                extra={'abc_va_piva_denominazione': False, 'abc_va_piva_name_match': False},
            )
            return 'invalid'
        secrets = self._abc_va_secrets()
        denominazione = sanitize_text(dati.get('denominazione') or '', secrets)[:200] or False
        end_date = self._abc_va_parse_date(dati.get('data_cessazione'))
        suspended_date = self._abc_va_parse_date(dati.get('data_sospensione'))
        start_date = self._abc_va_parse_date(dati.get('data_inizio'))
        name_match = False
        if denominazione:
            name_match = 'match' if den_tools.names_match(self.name, denominazione) else 'mismatch'
        if end_date:
            state = 'ceased'
            text = _("Partita IVA cessata il %s", end_date)
        elif suspended_date:
            state = 'ceased'
            text = _("Partita IVA sospesa dal %s", suspended_date)
        else:
            state = 'valid'
            text = _("Partita IVA valida")
        if denominazione:
            text = _("%(text)s: %(name)s", text=text, name=denominazione)
        if name_match == 'mismatch':
            text = _("%s (denominazione diversa dal nome del contatto)", text)
        self._abc_va_apply_result(state, text, value, kind='piva', extra={
            'abc_va_piva_denominazione': denominazione,
            'abc_va_piva_name_match': name_match,
            'abc_va_piva_start_date': start_date,
            'abc_va_piva_end_date': end_date,
            'abc_va_piva_suspended_date': suspended_date,
        })
        return state

    @staticmethod
    def _abc_va_parse_date(value):
        if not value:
            return False
        try:
            return fields.Date.to_date(str(value)[:10])
        except (ValueError, TypeError):
            return False

    def _abc_va_secrets(self):
        secrets = []
        for company in self.mapped(lambda p: p._abc_va_company()).sudo():
            secrets += [company.abc_va_client_secret, company.abc_va_client_id]
        return secrets

    # ==================================================================
    # Inneschi: creazione e modifica di codice fiscale / partita IVA
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        if not self.env.context.get(SKIP_TRIGGER):
            partners._abc_va_on_event(cf_changed=True)
            partners._abc_va_on_event(cf_changed=True, kind='piva')
        return partners

    def write(self, vals):
        cf_field = self._abc_va_cf_field_name()
        cf_changed = bool(cf_field and cf_field in vals)
        piva_changed = VAT_FIELD_NAME in vals or 'country_id' in vals
        scope_changed = 'is_company' in vals or 'parent_id' in vals
        res = super().write(vals)
        if not self.env.context.get(SKIP_TRIGGER):
            if cf_changed or scope_changed:
                self._abc_va_on_event(cf_changed=cf_changed)
            if piva_changed or scope_changed:
                self._abc_va_on_event(cf_changed=piva_changed, kind='piva')
        return res

    def _abc_va_on_event(self, cf_changed, kind='cf'):
        """Reagisce a un evento sul singolo soggetto (``cf_changed`` indica
        che il valore verificato è cambiato).

        - soggetto non applicabile: stato ``not_applicable`` se ha un valore
          o aveva un esito, altrimenti resta ``not_verified``;
        - verifica disattiva per la società: nessun accodamento, ma un esito
          riferito a un valore diverso viene azzerato;
        - altrimenti: esito azzerato, stato ``pending`` e richiesta in coda.
        Mai chiamate HTTP qui: il cron elabora la coda.
        """
        if kind == 'cf' and not self._abc_va_cf_field_name():
            return  # degradazione: campo assente, nessuna verifica possibile
        Queue = self.env['abc.va.queue']
        state_field = KIND_FIELDS[kind]['state']
        for partner in self:
            value = partner._abc_va_get_value(kind)
            if not partner._abc_va_is_applicable(kind):
                if value or partner[state_field] != 'not_verified':
                    partner._abc_va_apply_result(
                        'not_applicable',
                        _("Soggetto non rientrante nell'ambito di verifica."),
                        value, kind=kind,
                    )
                continue
            company = partner._abc_va_company()
            if not partner._abc_va_kind_enabled(company, kind):
                if cf_changed and partner._abc_va_is_outdated(kind):
                    partner._abc_va_reset('not_verified', kind=kind)
                continue
            needs_check = (
                cf_changed
                or partner[state_field] in ('not_verified', 'not_applicable')
                or partner._abc_va_is_outdated(kind)
            )
            if needs_check:
                partner._abc_va_reset('pending', kind=kind)
                Queue._abc_va_enqueue(partner, value, company, kind=kind, user=self.env.user)

    # ==================================================================
    # Innesco su uso effettivo (fattura, ordine, ...)
    # ==================================================================
    def _abc_va_on_use(self, company=None):
        """Da chiamare quando il contatto è coinvolto in un'operazione di
        business (conferma fattura, ordine, pratica). Accoda la verifica
        (codice fiscale e partita IVA) solo se il contatto non è mai stato
        verificato o il suo esito è riferito a un valore diverso: una volta
        verificato, gli usi successivi non fanno nulla. Mai chiamate HTTP.

        :param company: società che compie l'operazione (le sue credenziali
            e il suo throttle); default la società del contatto o corrente.
        """
        Queue = self.env['abc.va.queue']
        for partner in self:
            use_company = company or partner._abc_va_company()
            for kind in ('cf', 'piva'):
                if kind == 'cf' and not self._abc_va_cf_field_name():
                    continue
                if partner._abc_va_state(kind) != 'not_verified' and not partner._abc_va_is_outdated(kind):
                    continue
                if not partner._abc_va_is_applicable(kind):
                    continue
                if not partner._abc_va_kind_enabled(use_company, kind):
                    continue
                partner._abc_va_reset('pending', kind=kind)
                Queue._abc_va_enqueue(partner, partner._abc_va_get_value(kind), use_company,
                                      kind=kind, user=self.env.user)

    # ==================================================================
    # Problemi che impediscono o segnalano la conferma dei documenti
    # ==================================================================
    def _abc_va_confirm_issues(self, company):
        """Lista di ``(level, message)`` per i contatti in ``self`` rispetto
        alle policy della società: ``level`` è ``'block'`` o ``'warn'``. Gli
        stati ``error``, ``pending`` e ``not_verified`` non generano mai
        problemi: un guasto tecnico non ferma l'operatività."""
        company = company.sudo()
        issues = []

        def add(policy_value, message, block_value='block_document'):
            if policy_value == block_value:
                issues.append(('block', message))
            elif policy_value == 'warn':
                issues.append(('warn', message))

        for partner in self:
            name = partner.display_name
            if partner.abc_va_state == 'invalid':
                add(company.abc_va_on_invalid, _(
                    "il codice fiscale di %(name)s risulta non valido (%(reason)s)",
                    name=name, reason=partner.abc_va_message or ''))
            if partner.abc_va_piva_state == 'invalid':
                add(company.abc_va_on_invalid, _(
                    "la partita IVA di %(name)s risulta non valida (%(reason)s)",
                    name=name, reason=partner.abc_va_piva_message or ''))
            elif partner.abc_va_piva_state == 'ceased':
                add(company.abc_va_on_ceased, _(
                    "la partita IVA di %(name)s risulta cessata o sospesa (%(reason)s)",
                    name=name, reason=partner.abc_va_piva_message or ''))
            if (partner.abc_va_piva_state in ('valid', 'ceased')
                    and partner.abc_va_piva_name_match == 'mismatch'):
                add(company.abc_va_piva_name_check, _(
                    "il nome di %(name)s non corrisponde alla denominazione AdE "
                    "'%(ade)s'", name=name, ade=partner.abc_va_piva_denominazione or ''),
                    block_value='block')
        return issues

    def action_abc_va_align_name(self):
        """Allinea il nome del contatto alla denominazione AdE."""
        self.ensure_one()
        if not self.abc_va_piva_denominazione:
            raise UserError(_("Nessuna denominazione AdE disponibile per questo contatto."))
        self.write({'name': self.abc_va_piva_denominazione})
        self.sudo().with_context(**{SKIP_TRIGGER: True}).write({'abc_va_piva_name_match': 'match'})
        return True

    # ==================================================================
    # Verifica manuale puntuale
    # ==================================================================
    def action_abc_va_verify_now(self):
        """Pulsante "Verifica ora" sul singolo contatto (codice fiscale, o
        partita IVA con context ``abc_va_kind='piva'``).

        Esecuzione sincrona: l'operatore ha chiesto esplicitamente l'esito e
        lo riceve nella notifica, attendendo solo la latenza del provider.
        Il throttle è comunque rispettato (lock per società condiviso con il
        cron); se il limite è raggiunto o il servizio non risponde, la
        richiesta resta in coda ed è il cron a completarla.

        Anti-abuso: se esiste già un esito reale sullo stesso valore entro
        ``abc_va_recheck_hours``, viene riutilizzato senza chiamare il
        provider, salvo forzatura (context ``abc_va_force``) da parte di un
        amministratore del modulo.
        """
        self.ensure_one()
        kind = self.env.context.get('abc_va_kind', 'cf')
        if kind not in KIND_FIELDS:
            raise UserError(_("Tipo di verifica non riconosciuto."))
        user = self.env.user
        if not user.has_group(GROUP_USER):
            raise AccessError(_(
                "Solo gli utenti del gruppo 'Verifica anagrafica tributaria / "
                "Utente' possono richiedere una verifica."
            ))
        force = bool(self.env.context.get('abc_va_force')) and user.has_group(GROUP_MANAGER)

        if kind == 'cf' and not self._abc_va_cf_field_name():
            raise UserError(_(
                "Il campo codice fiscale non è disponibile su questa "
                "installazione: verifica non possibile."
            ))
        if not self._abc_va_is_applicable(kind):
            if kind == 'piva':
                raise UserError(_(
                    "La verifica si applica solo a contatti principali con "
                    "partita IVA italiana di 11 cifre."
                ))
            raise UserError(_(
                "La verifica si applica solo a persone fisiche (contatti "
                "principali) con codice fiscale alfanumerico di 16 caratteri."
            ))
        company = self._abc_va_company()
        if not company.sudo()._abc_va_is_operational() or not self._abc_va_kind_enabled(company, kind):
            raise UserError(_(
                "La verifica anagrafica (%(kind)s) non è attiva per la società "
                "%(company)s, oppure le credenziali non sono configurate o sono "
                "scadute. Contatta l'amministratore.",
                kind=KIND_LABELS[kind], company=company.display_name,
            ))

        value = self._abc_va_get_value(kind)
        Queue = self.env['abc.va.queue']

        if not force:
            cached = Queue._abc_va_find_cached(company, value, kind=kind)
            if cached:
                Queue._abc_va_apply_cached(self, cached, value, kind, company, user)
                return self._abc_va_notify(
                    _("Esito già disponibile"),
                    _("È presente una verifica recente sullo stesso valore: "
                      "l'esito è stato riutilizzato senza una nuova chiamata al provider."),
                    'info',
                )

        pending = Queue.sudo().search([
            ('partner_id', '=', self.id), ('kind', '=', kind),
            ('state', '=', 'pending'), ('value', '=', value),
        ], limit=1)
        if pending and not force and pending.next_try and pending.next_try > fields.Datetime.now():
            return self._abc_va_notify(
                _("Verifica già in coda"),
                _("Il servizio non ha risposto all'ultimo tentativo: nuovo tentativo "
                  "automatico alle %s.", fields.Datetime.to_string(pending.next_try)),
                'warning',
            )

        if not pending:
            self._abc_va_reset('pending', kind=kind)
        job = Queue._abc_va_enqueue(self, value, company, kind=kind, force=force, user=user)
        outcome = job._abc_va_process_now()
        return self._abc_va_notify_outcome(outcome, job)

    def _abc_va_notify_outcome(self, outcome, job):
        """Notifica per l'esito di una verifica sincrona."""
        self.ensure_one()
        job = job.sudo()
        kind = job.kind
        state = self._abc_va_state(kind)
        message = self[KIND_FIELDS[kind]['message']] or job.last_error or ''
        duration = job.log_id.duration_ms
        if duration and job.log_id.event == 'api':
            message = _("%(message)s (risposta del servizio in %(seconds).1f s)",
                        message=message, seconds=duration / 1000.0)
        if outcome == 'throttled':
            return self._abc_va_notify(
                _("Limite di chiamate raggiunto"),
                _("La verifica resta in coda e verrà elaborata automaticamente "
                  "appena il limite lo consente."),
                'warning', sticky=True,
            )
        if outcome == 'retry':
            return self._abc_va_notify(
                _("Servizio momentaneamente non disponibile"),
                _("%s La verifica resta in coda con nuovo tentativo automatico.", job.last_error or ''),
                'warning', sticky=True,
            )
        if state == 'valid':
            title = _("Partita IVA valida") if kind == 'piva' else _("Codice fiscale valido")
            return self._abc_va_notify(title, message, 'success')
        if state == 'ceased':
            return self._abc_va_notify(_("Partita IVA cessata o sospesa"), message, 'danger', sticky=True)
        if state == 'invalid':
            title = _("Partita IVA NON valida") if kind == 'piva' else _("Codice fiscale NON valido")
            return self._abc_va_notify(title, message, 'danger', sticky=True)
        if state == 'not_applicable':
            return self._abc_va_notify(_("Soggetto non applicabile"), message, 'info')
        return self._abc_va_notify(_("Verifica non riuscita"), message, 'warning', sticky=True)

    def _abc_va_notify(self, title, message, kind='info', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': kind,
                'sticky': sticky,
                # chiude l'azione: il client web ricarica la scheda del
                # contatto e mostra subito badge ed esito aggiornati
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
