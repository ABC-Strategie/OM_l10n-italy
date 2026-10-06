# Intrastat su Odoo 19: rinomina in `*_oca` — analisi

Branch `19.0-ottobre-26` di `OM_l10n-italy`, nato da `abc-19.0` @ `681e202`. Lavoro trasversale a tutti i
clienti 19: il problema è emerso su Finance Consulting, ma lì è risolto senza codice (§6).
Analisi del 06/10/2026. Fonti: sorgenti dei branch citati, log dell'upgrade odoo.sh di Finance Consulting
(build 39312326), sorgente Enterprise 19 locale (`2de1512`, 29/07/2026).

Ogni punto distingue il **fatto misurato** dalla **conclusione**.

## 1. Il problema

**Fatto.** Enterprise 19 ha introdotto un modulo `l10n_it_intrastat` (OEEL-1, `auto_install`, dipende da
`account_intrastat` e `l10n_it_reports`). Non esiste su Enterprise 16, 17 e 18.
`abc-19.0` contiene un `l10n_it_intrastat` OCA omonimo e un `l10n_it_intrastat_statement` che ne dipende.

**Fatto (Finance Consulting, 06/10).**
- Upgrade delle 08:03 UTC: la piattaforma tratta l'OCA come modulo standard, cancella i suoi record e si ferma
  su `res.company.intrastat_min_amount`.
- Upgrade delle 10:35 UTC: la piattaforma scrive `Custom module 'l10n_it_intrastat' renamed to
  'l10n_it_intrastat_custom'` e prosegue. Sul build 19, lo Statement (installato, codice presente) dipende da
  `l10n_it_intrastat`: Odoo installa quello **Enterprise** insieme ad `account_intrastat`, `sale/purchase/stock_intrastat`,
  e si ferma con `Field res.company.intrastat_custom_id with unknown comodel_name 'account.intrastat.custom'`.

**Conclusione.** Finché l'OCA si chiama `l10n_it_intrastat`, su ogni cliente Enterprise che lo ha installato la
migrazione si rompe. La rinomina in `*_oca` è necessaria.

## 2. OCA ha già scelto la stessa strada

**Fatto.** PR aperte su `OCA/l10n-italy` (issue di tracciamento #4930), autore Giuseppe Borruso, 06/02/2026:
- **#5089** `[19.0][MIG] l10n_it_intrastat_oca` (stato GitHub: `dirty`, cioè in conflitto con `19.0`);
- **#5088** `[19.0][MIG] l10n_it_intrastat_statement_oca` (contiene un commit `[DONT MERGE] test-requirements.txt`).

Non sono ancora unite. `upstream/19.0` oggi ha 13 moduli, l'Intrastat non c'è.

Scaricate in locale come `upstream/pr/5089` e `upstream/pr/5088`.

**Conclusione.** Stessi nomi che volevamo usare noi. Allinearsi alle PR significa che, quando OCA unirà, il nostro
codice sarà sostituibile da quello ufficiale senza un'altra rinomina.

## 3. Cosa contiene oggi `abc-19.0`

**Fatto.** Rispetto a `upstream/18.0` (OCA 18), escluse le traduzioni:

| Modulo | Differenze |
|---|---|
| `l10n_it_intrastat` | versione `18.0.1.1.0` → `19.0.1.0.0`; `depends` `account` → `stock`, `stock_account`; un test riscritto; README/index |
| `l10n_it_intrastat_statement` | solo la versione `18.0.1.0.0` → `19.0.1.0.0` |

Gli ultimi due commit su questi moduli sono `9b4118a` «[UPD] manifest versions to 19» e `dbee5bb` «[UPD] manifest»
(05-06/03/2026). Nel codice di `l10n_it_intrastat` **nessun file usa `stock`**: la dipendenza aggiunta non serve
a nulla di ciò che il modulo fa.

**Conclusione.** Il port A.B.C. è OCA 18 con la versione cambiata. Non contiene gli adattamenti a Odoo 19 che
invece le PR OCA hanno (§4).

## 4. `abc-19.0` contro le PR OCA 19

### `l10n_it_intrastat` → `l10n_it_intrastat_oca` (#5089)

| Punto | `abc-19.0` | PR OCA |
|---|---|---|
| `depends` | product, **stock, stock_account**, uom | product, **account**, uom |
| rinomina | — | `pre_init_hook` `pre_absorb_old_module` + `migrations/19.0.1.0.0/pre-migrate.py` |
| migrazione `18.0.1.0.0` (campo `intrastat` → `l10n_it_oca_intrastat` su `account.fiscal.position`) | presente | **rimossa** |
| `name_search` di `report.intrastat.code` | override con firma 16-18 (`args=`) | sostituito da `_rec_names_search` |
| messaggi | `_("...") % x` | `self.env._("...", x)` |
| onchange dominio | lista | `Domain(...)` |
| azioni | `<field name="type">` | `<field name="path">` (URL leggibili 19) |
| search view | `<group expand="0" string=...>` | `<group>` |
| xmlid nei file dati | `l10n_it_intrastat.` | `l10n_it_intrastat_oca.` |

Il hook OCA rinomina **solo se** `l10n_it_intrastat` è installato **ed** è la versione OCA: lo riconosce dal
record `l10n_it_intrastat.intrastat_category_2014_01012100` di `report.intrastat.code`. Così non tocca mai il
modulo Enterprise omonimo.

Nota sul `name_search`: `web_name_search` su 19 lo chiama per **posizione** (`odoo/addons/web/models/models.py:54`),
quindi l'override vecchio oggi funziona. È codice superato, non un errore che si vede.

### `l10n_it_intrastat_statement` → `l10n_it_intrastat_statement_oca` (#5088)

- `depends` → `l10n_it_intrastat_oca`;
- stesso hook, ma **senza condizione**: Enterprise non ha uno Statement, il nome vecchio è solo OCA;
- `default=_metodo` → `default=lambda self: self._metodo()` (sequenze e progressivo);
- `self._context` → `self.env.context`; `Domain(...)`; messaggi con `self.env._(..., x)`;
- `hasattr(self, "cancellation")` nel controllo della sezione 4;
- tutti i riferimenti `l10n_it_intrastat_statement.` → `..._oca.`: `report_name`, `report_file`, `paperformat_id`,
  percorso dell'immagine `agenzia_dogane.jpg` nei report.

**Conclusione.** Conviene **partire dal codice delle PR OCA**, non rinominare il port di `abc-19.0`: le PR hanno
già la rinomina fatta bene e gli adattamenti a 19 che il nostro port non ha.

## 5. Cosa manca alle PR OCA per i nostri casi

Le PR pensano al salto **18 → 19 con OpenUpgrade**. I nostri clienti fanno **16 → 19**, e quelli Enterprise passano
dalla **piattaforma di upgrade di Odoo** (odoo.sh), non da OpenUpgrade.

### 5.1 Il nome `l10n_it_intrastat_custom`
**Fatto.** La piattaforma, il 06/10 alle 10:35 UTC, ha rinominato l'OCA in `l10n_it_intrastat_custom`
(funzione `rename_custom_module` di `odoo/upgrade-util`, chiamata da uno script privato di Odoo).
**Non sappiamo** se lo fa per ogni database o se è stato uno script specifico per Finance Consulting: alle
08:03 dello stesso giorno non l'aveva fatto.
**Proposta.** Il hook assorbe **anche** `l10n_it_intrastat_custom`, se installato.

### 5.2 La migrazione del campo della posizione fiscale
**Fatto.** OCA 18 rinomina `account.fiscal.position.intrastat` in `l10n_it_oca_intrastat`
(`migrations/18.0.1.0.0/pre-migration.py`). La PR 19 l'ha tolta, perché nel salto 18→19 è già avvenuta.
**Conclusione.** Nel salto 16→19 serve ancora. Ma col hook il modulo viene **installato**, e all'installazione gli
script `migrations/` **non girano**: la rinomina del campo va fatta **dentro il hook**, se la colonna vecchia esiste e
quella nuova no. Da verificare: chi definisce `intrastat` su `account.fiscal.position` nel 19 (il core `account` 19
non lo definisce più; Finance Consulting aveva 0 posizioni fiscali con `intrastat = true`).

### 5.3 Collisione di campi con `account_intrastat` Enterprise
**Fatto.** `product.template.intrastat_code_id` esiste in tutti e due, con comodel diversi:
- OCA: `report.intrastat.code`;
- Enterprise `account_intrastat` (`models/product.py:12`): `account.intrastat.code`.
Le PR OCA non dichiarano `excludes`.
**Conclusione.** I due moduli non possono convivere. Proposta: `"excludes": ["account_intrastat"]` su
`l10n_it_intrastat_oca`, come `l10n_it_riba_oca` fa con `l10n_it_riba`. Da decidere: impedisce anche
l'installazione automatica del `l10n_it_intrastat` Enterprise, che dipende da `account_intrastat`.

### 5.4 Quando gira il hook
**Conclusione.** Il hook gira solo quando qualcuno **installa** `l10n_it_intrastat_oca`. Dopo l'upgrade il DB ha
il modulo col nome vecchio (o `_custom`) senza codice: resta «installato ma non caricabile» finché non si
installa il nuovo. Passo da scrivere nella procedura di migrazione di ogni cliente che usa Intrastat.
⚠️ Se nel DB 19 resta un `l10n_it_intrastat` OCA **non** rinominato (piattaforma che non lo rinomina), Odoo lo
caricherebbe col codice Enterprise e cancellerebbe campi e colonne OCA **prima** del hook. In quel caso la rinomina
va fatta prima del caricamento dei moduli, cioè sul 16 o dalla piattaforma. Da chiarire con il punto 5.1.

## 6. Finance Consulting: il caso da cui è nato, risolto senza codice

**Fatto.** Intrastat mai usato (0 dichiarazioni, 0 righe, solo valori di default) e disinstallato in produzione
il 06/10, verificato con query di sola lettura. L'upgrade delle 10:19 UTC ha usato un backup di **prima** della
disinstallazione (nel log la piattaforma apre ancora i menu Intrastat).
**Conclusione.** Con un backup successivo alla disinstallazione l'Intrastat non c'è più nel DB e la collisione non
scatta. Per un cliente che l'Intrastat **lo usa**, disinstallarlo non è possibile: è per loro che serve questo branch,
ed è su un cliente così che la rinomina va provata.

## 7. `custom-abc-19.0` ha già una rinomina a metà

**Fatto.** Su `origin/custom-abc-19.0` (ultimo commit `b0b77f5`, 01/10/2026; 14 commit propri, 9 indietro rispetto
a `abc-19.0`), Fabrizio Dadamo il 16/07/2026 (`82d0022`, `57982b7`, «[UPD]intrastat») ha:
- rinominato la cartella `l10n_it_intrastat` → `l10n_it_intrastat_oca`, nome visualizzato «ITA - Intrastat (OCA)»,
  codice identico al port di `abc-19.0` (cambiano solo gli xmlid in `security/intrastat_rules.xml` e `views/account.xml`);
- lasciato `l10n_it_intrastat_statement` col suo nome, ma con `depends` → `l10n_it_intrastat_oca` e gli xmlid aggiornati.

Non c'è **nessun hook** e nessuna migrazione del nome del modulo. `depends` resta product, stock, stock_account, uom.

**Conclusione.** Il nome è quello giusto, ma un DB che ha l'Intrastat OCA installato come `l10n_it_intrastat` non
viene ricollegato a `l10n_it_intrastat_oca`: i dati restano intestati al nome vecchio. Mancano anche gli adattamenti
a 19 del §4. Lo Statement non è rinominato, mentre OCA lo rinomina.

### 7.1 Il merge di `custom-abc-19.0` porta anche dei doppioni
**Fatto.** `custom-abc-19.0` contiene sei moduli OCA che esistono già negli OCA annidati di `OM_base_l10n-italy` 19.0:
`account_financial_report`, `account_tax_balance` (account-financial-reporting), `account_fiscal_year`
(account-financial-tools), `date_range` (server-ux), `report_xlsx`, `report_xml` (reporting-engine).
**Conclusione.** Dopo il merge, lo stesso nome di modulo starà in due cartelle dell'addons-path e vincerà quella che
viene prima. Va deciso quale copia tenere, dopo averle confrontate.

### 7.2 Ordine consigliato
**Conclusione.** Se il merge di `custom-abc-19.0` va fatto, farlo **prima** e **poi** il lavoro
sull'Intrastat sopra il risultato. Al contrario, il merge finale incontrerebbe la rinomina di Fabrizio sugli stessi
file e darebbe conflitti di rinomina.

## 8. Piano

- [ ] Decidere se il merge di `origin/custom-abc-19.0` entra in questo branch (era pensato per Finance Consulting);
      se sì, farlo per primo (§7.2) risolvendo i doppioni (§7.1)
- [ ] Decidere: partire dalle PR OCA #5089/#5088 (proposta) o completare la rinomina di `custom-abc-19.0`
- [ ] Portare su questo branch i moduli `l10n_it_intrastat_oca` e `l10n_it_intrastat_statement_oca` dalle PR,
      al posto di quelli presenti dopo il merge; escluso il commit `[DONT MERGE]`
- [ ] Hook: assorbire anche `l10n_it_intrastat_custom` (§5.1)
- [ ] Hook: rinomina della colonna della posizione fiscale nel salto 16→19 (§5.2), dopo aver verificato chi la definisce
- [ ] Decidere `excludes: ["account_intrastat"]` (§5.3)
- [ ] Verificare che nessun modulo dei repo 19 dipenda dai nomi vecchi (06/10: solo lo Statement, già incluso)
- [ ] Test in locale: installazione pulita; DB 16 con Intrastat OCA → 19 → installazione `_oca` → dati conservati
- [ ] Chiarire con Odoo se la rinomina in `_custom` è generica o specifica (§5.1, §5.4)
- [ ] Riportare in `abc-19.0` (decisione separata: è il branch di tutti i clienti)

## 9. Il branch riparte da `custom-abc-19.0` (06/10/2026, pomeriggio)

Decisione dell'utente: `19.0-ottobre-26` = `custom-abc-19.0` (`b0b77f5`) + questo documento. Il merge di
`custom-abc-19.0` del §7.2 non serve più, perché il branch nasce da lì. Il §7.1 resta vero: i sei doppioni con
gli OCA di `OM_base_l10n-italy` sono già dentro questo branch.

### 9.1 I 9 commit di `abc-19.0` che questo branch non ha

**Fatto.** `custom-abc-19.0` si è staccato da `abc-19.0` a `62f4f17`. Da allora `abc-19.0` ha 9 commit propri:

| Commit | Data | Cosa |
|---|---|---|
| `681e202` | 22/07 | fix tax_id error |
| `c83b5f7` | 15/07 | `l10n_it_vat_settlement_date`: pre-migration che rinomina `date_vat_settlement` |
| `b4a567c` | 15/07 | `l10n_it_vat_settlement_date`: eliminati i file di test |
| `6ce2433` | 15/07 | `l10n_it_vat_settlement_date`: test disattivati sulla build di migrazione |
| `6498802` | 14/07 | `odoo.osv.expression` (deprecato in 19) → `odoo.fields.Domain` |
| `61ae67f` | 22/06 | bugfix — tra l'altro aggiunge `migrate_old_module` a `l10n_it_riba_oca/hooks.py` |
| `5d86add` | 17/06 | Odoo 19: via `odoo.fields.first` (deprecato) |
| `5d36233` | 15/06 | `l10n_it_vat_registries`: pre-migration che toglie il riferimento al campo obsoleto `cee_type` |
| `4942c26` | 12/06 | `l10n_it_asset_management`: gruppi/privilegi 19, `users`→`user_ids`, search view |

**Fatto (difetto presente su questo branch).** `l10n_it_riba_oca/migrations/18.0.1.0.0/pre-migrate.py` chiama
`hooks.migrate_old_module(cr)`, ma su `custom-abc-19.0` `hooks.py` definisce solo `pre_absorb_old_module`.
La funzione l'ha aggiunta `61ae67f`, che qui manca.
**Conclusione.** Su un DB in cui quella migrazione gira, l'aggiornamento di `l10n_it_riba_oca` si ferma con
`AttributeError`. Gli altri commit sono adattamenti a 19 e migrazioni di campo che servono nel salto 16→19.
Proposta: **merge di `abc-19.0` in `19.0-ottobre-26`**. Decisione dell'utente.

### 9.2 Confronto modulo per modulo con OCA 18.0, OCA 19.0 e le PR 19

Riferimenti: `upstream/18.0` @ `8f654e6` (02/10/2026), `upstream/19.0` @ `b4d0fab` (24/09/2026), issue
OCA #4930 (elenco delle migrazioni 19: «unita» = già in `19.0`, «PR aperta» = proposta non ancora unita).
Le differenze escludono traduzioni, README e `static`. «nostro vs OCA 18» misura quanto il port A.B.C. si è
allontanato da OCA 18. «nostro vs OCA 19» quanto dista dalla versione ufficiale 19, dove esiste.

**Già migrati da OCA alla 19 e presenti da noi** (12): `abicab`, `account`, `account_invoice_start_end_dates`,
`account_stamp`, `appointment_code`, `ateco`, `central_journal_reportlab`, `currency_rate_update_boi`,
`edi_related_document`, `fiscalcode_sale`, `vat_registries`. Le differenze più grandi rispetto all'ufficiale sono
su `account` (+44 −207), `account_stamp` (+71 −195), `central_journal_reportlab` (+116 −58), `vat_registries`
(+94 −76): vanno lette una per una prima di decidere se sostituire il nostro con l'ufficiale. Possono contenere
correzioni A.B.C. o migrazioni 16→19 che OCA non ha.

**In OCA 18 ma assenti da noi**:
- `l10n_it_amount_to_text`: **già migrato da OCA alla 19**, da noi manca;
- `l10n_it_pos_fiscalcode`: nessuna PR 19. ⚠️ Finance Consulting lo ha installato sul 16;
- con PR 19 aperta: `l10n_it_delivery_note_customer_code`, `l10n_it_edi_pec`, `l10n_it_edi_sdi`,
  `l10n_it_edi_sender_partner`, `l10n_it_edi_td29`;
- senza PR: `l10n_it_edi_accompanying_invoice`.

**Intrastat**: da noi `l10n_it_intrastat_oca` (rinomina di Fabrizio, senza hook) e `l10n_it_intrastat_statement`
(nome vecchio). In OCA: PR aperte con entrambi rinominati e i hook (§2, §4).

**RiBa, il precedente**: OCA ha rinominato `l10n_it_riba` → `l10n_it_riba_oca` alla 18, con hook e
`migrations/18.0.1.0.0/pre-migrate.py`. Nella PR 19 (#5090) **hook e migrazione sono stati tolti**, perché da 18 a
19 il nome non cambia più. Il nostro `l10n_it_riba_oca` li **conserva**, e serve: i nostri clienti saltano da 16.
È lo stesso schema da seguire per l'Intrastat: hook all'installazione + migrazione per OpenUpgrade, tenuti anche
dopo che OCA li avrà tolti.

**Conclusione sull'Intrastat.** Sì, va rinominato anche lo Statement e servono i hook, come per la RiBa. La
rinomina di Fabrizio è il primo passo, ma senza hook un DB che arriva dal 16 resta col nome vecchio.

Tabella completa:

| Modulo | nostro | OCA 18 | OCA 19 | PR #4930 | nostro vs OCA 19 | nostro vs OCA 18 |
|---|---|---|---|---|---|---|
| `l10n_it_abicab` | 19.0.1.0.0 | 18.0.1.0.0 | 19.0.1.0.0 | unita #5067 | 3 file, +5 -8 | 3 file, +6 -4 |
| `l10n_it_accompanying_invoice` | 19.0.1.0.0 | 18.0.1.0.0 | — | PR aperta #5068 |  | 3 file, +24 -3 |
| `l10n_it_account` | 19.0.1.0.1 | 18.0.1.1.2 | 19.0.1.0.0 | unita #5072 | 6 file, +44 -207 | 6 file, +38 -196 |
| `l10n_it_account_invoice_start_end_dates` | 19.0.1.0.0 | 18.0.1.0.1 | 19.0.1.0.0 | unita #5318 | 3 file, +43 -62 | 2 file, +8 -17 |
| `l10n_it_account_stamp` | 19.0.1.0.0 | 18.0.1.2.2 | 19.0.1.0.0 | unita #5069 | 11 file, +71 -195 | 6 file, +31 -25 |
| `l10n_it_account_vat_period_end_settlement` | 19.0.1.0.0 | 18.0.1.0.6 | — | PR aperta #5319 |  | 4 file, +100 -41 |
| `l10n_it_amount_to_text` | — | 18.0.1.0.0 | 19.0.1.0.0 | unita #5122 |  |  |
| `l10n_it_appointment_code` | 19.0.1.0.0 | 18.0.1.0.0 | 19.0.1.0.0 | unita #5073 | 1 file, +1 -0 | 1 file, +1 -1 |
| `l10n_it_asset_management` | 19.0.1.0.0 | 18.0.1.1.1 | — | PR aperta #5074 |  | 9 file, +15 -61 |
| `l10n_it_ateco` | 19.0.1.0.0 | 18.0.1.0.0 | 19.0.1.0.0 | unita #5075 | 3 file, +5 -2 | 3 file, +3 -5 |
| `l10n_it_bill_of_entry` | 19.0.1.0.0 | 18.0.1.0.0 | — | PR aperta #5076 |  | 2 file, +4 -2 |
| `l10n_it_central_journal_reportlab` | 19.0.1.0.0 | 18.0.1.2.1 | 19.0.1.0.0 | unita #5077 | 3 file, +116 -58 | 2 file, +1 -3 |
| `l10n_it_currency_rate_update_boi` | 19.0.1.0.0 | 18.0.1.0.0 | 19.0.1.0.0 | unita #5078 | 4 file, +1 -32 | 1 file, +1 -1 |
| `l10n_it_delivery_note` | 19.0.1.0.1 | 18.0.1.2.0 | — | PR aperta #5081 |  | 23 file, +201 -872 |
| `l10n_it_delivery_note_batch` | 19.0.1.0.0 | 18.0.1.0.0 | — | PR aperta #5079 |  | 1 file, +1 -1 |
| `l10n_it_delivery_note_customer_code` | — | 18.0.1.0.0 | — | PR aperta #5213 |  |  |
| `l10n_it_delivery_note_order_link` | 19.0.1.0.0 | 18.0.1.0.0 | — | PR aperta #5080 |  | 1 file, +1 -1 |
| `l10n_it_edi_accompanying_invoice` | — | 18.0.1.0.0 | — |   |  |  |
| `l10n_it_edi_doi_extension` | 19.0.1.0.1 | 18.0.1.1.2 | — | PR aperta #5082 |  | 16 file, +59 -1619 |
| `l10n_it_edi_extension` | 19.0.1.0.0 | 18.0.1.12.3 | — | PR aperta #5083 |  | 27 file, +280 -1751 |
| `l10n_it_edi_pec` | — | 18.0.1.1.0 | — | PR aperta #5218 |  |  |
| `l10n_it_edi_related_document` | 19.0.1.0.0 | 18.0.1.2.1 | 19.0.1.0.0 | unita #5084 | 5 file, +14 -34 | 3 file, +21 -25 |
| `l10n_it_edi_sdi` | — | 18.0.1.0.0 | — | PR aperta #5217 |  |  |
| `l10n_it_edi_sender_partner` | — | 18.0.1.0.0 | — | PR aperta #5140 |  |  |
| `l10n_it_edi_td29` | — | 18.0.1.0.0 | — | PR aperta #5272 |  |  |
| `l10n_it_financial_statement_eu` | 19.0.1.0.0 | 18.0.1.0.0 | — | PR aperta #5085 |  | 2 file, +2 -2 |
| `l10n_it_financial_statements_report` | 19.0.1.1.0 | 18.0.1.1.1 | — | PR aperta #5086 |  | 2 file, +3 -3 |
| `l10n_it_fiscalcode_sale` | 19.0.1.0.0 | 18.0.1.0.0 | 19.0.1.0.0 | unita #5087 | 1 file, +2 -5 | 1 file, +1 -1 |
| `l10n_it_hr_payroll_document` | — | — | — | PR aperta #5256 |  |  |
| `l10n_it_intrastat` | — | 18.0.1.1.0 | — |   |  |  |
| `l10n_it_intrastat_oca` | 19.0.1.0.0 | — | — | PR aperta #5089 |  |  |
| `l10n_it_intrastat_statement` | 19.0.1.0.0 | 18.0.1.0.0 | — |   |  | 4 file, +9 -9 |
| `l10n_it_intrastat_statement_oca` | — | — | — | PR aperta #5088 |  |  |
| `l10n_it_location_nuts` | 19.0.1.0.0 | 18.0.1.0.1 | — | PR aperta #5098 |  | 2 file, +1 -2 |
| `l10n_it_pos_fiscalcode` | — | 18.0.1.0.0 | — |   |  |  |
| `l10n_it_riba_oca` | 19.0.1.0.0 | 18.0.1.3.0 | — | PR aperta #5090 |  | 8 file, +112 -179 |
| `l10n_it_vat_registries` | 19.0.1.0.0 | 18.0.1.2.3 | 19.0.1.0.0 | unita #5091 | 8 file, +94 -76 | 4 file, +36 -76 |
| `l10n_it_vat_settlement_communication` | 19.0.1.0.0 | 18.0.1.0.3 | — | PR aperta #5092 |  | 5 file, +21 -47 |
| `l10n_it_vat_settlement_date` | 19.0.1.0.0 | 18.0.1.0.2 | — | PR aperta #5093 |  | 3 file, +14 -37 |
| `l10n_it_website_portal_fiscalcode` | 19.0.1.0.0 | 18.0.1.0.0 | — |   |  | 4 file, +3 -73 |

Moduli nostri non l10n_it: `abc_account_payment_term_extension_patch`, `abc_account_withholding_tax_reports`, `abc_bank_statement_line_invoice_ref`, `abc_date_range_fix`, `abc_l10n_it_compatibility`, `abc_l10n_it_edi_note_line`, `abc_l10n_it_ratei_risconti`, `abc_l10n_it_vat_registry_settlement_ext`, `abc_modelli_scritture`, `abc_partner_account_default`, `abc_tax_integration_wizard`, `abc_verifica_anagrafica`, `abc_verifica_anagrafica_sale`, `account_financial_report`, `account_fiscal_year`, `account_tax_balance`, `bitti_financial_statements`, `date_range`, `partner_default_purchase_tax`, `report_xlsx`, `report_xml`
