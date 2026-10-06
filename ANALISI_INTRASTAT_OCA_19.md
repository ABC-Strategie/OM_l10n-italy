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
