# ABC - Ritenute d'acconto attive e passive (Odoo 19)

Modulo `abc_ritenute_acconto`. Implementa la specifica "Specifica modulo Ritenute d'acconto attive e passive - Odoo 19" (decisioni D1-D62, N1-N4).

Dipende da `account`, `l10n_it_edi` (che in Odoo 19 contiene i campi ritenuta sulle imposte) e `mail`.

Guida di configurazione e uso per gli utenti: "Guida al modulo Ritenute d'acconto - Odoo 19" (https://claude.ai/artifact/A7LpnQkBYn8kL5JzBdKjLy).

## Schema contabile (D2, schema del vecchio modulo OCA)

Nessun conto d'appoggio e nessuna scrittura per cassa (CABA) sulle ritenute.

| Momento | Registro | Dare | Avere |
| --- | --- | --- | --- |
| Fattura fornitore | Acquisti | Costo + IVA | Fornitore al lordo (riga di scadenza = netto, riga ritenuta = ritenute) |
| Pagamento al fornitore | Banca | Fornitore (netto) | Banca |
| Pagamento, scrittura automatica del modulo | Varie | Fornitore (ritenute) | Erario c/ritenute da versare / Debiti previdenziali |
| Addebito F24 | Banca (riconciliazione) | Erario c/ritenute da versare | Banca |
| Fattura cliente | Vendite | Cliente al lordo | Ricavi + IVA |
| Incasso, scrittura automatica del modulo | Varie | Crediti per ritenute subite | Cliente (ritenute) |

Come funziona tecnicamente:

- Le ritenute restano imposte sulle righe della fattura (`l10n_it_withholding_type`), cosi' import ed export XML della fattura elettronica nativa funzionano come prima.
- Per le imposte con "Ritenuta sul conto del fornitore / cliente" (`abc_wh_on_partner`) la riga ritenuta della fattura viene registrata sul conto del fornitore (o del cliente) invece che sul conto dell'imposta. Per questo il modulo ridefinisce il controllo `_check_payable_receivable` di `account.move.line`, ammettendo come unica eccezione queste righe.
- "Registra pagamento" propone il netto: il wizard esclude le righe ritenuta.
- A ogni pagamento/incasso (riconciliazione della riga di scadenza) il modulo crea la quota e la scrittura nel registro varie, e la riconcilia con la riga ritenuta della fattura.
- Quando l'addebito F24 in banca viene riconciliato con le righe sul conto erariale, le quote risultano versate in automatico (versamento F24 "da riconciliazione bancaria", uno per movimento di banca). Se si toglie la riconciliazione, tornano da versare.
- Il versamento F24 del modulo non crea scritture: serve per preparare l'F24 (wizard, Excel, PDF) e per il 770.

## Cosa fa

| Area | Contenuto |
| --- | --- |
| Registro | Una testata per ogni ritenuta in fattura (fornitore o cliente), creata alla conferma della fattura |
| Quote | Una quota per ogni pagamento/incasso, in proporzione; data = data del pagamento |
| Scadenze | 16 del mese successivo, festivi e proroga di agosto; promemoria 5, 3, 1, 0 giorni prima |
| Versamento F24 | Wizard con soglia 100 euro facoltativa e mesi precedenti a scelta; sanzioni e interessi; quietanza facoltativa; export Excel e PDF; versato in automatico alla riconciliazione bancaria |
| Ciclo attivo | Credito all'incasso, anno fiscale secondo il regime dell'azienda; ritenuta non operata; controllo CU ricevute con solleciti; scomputo; eccedenze e utilizzi |
| CU e 770 | CU per percipiente e causale, quadro ST, controlli bloccanti; export Excel, PDF, invio email |
| Storico | Ricostruzione dal 01/01/2026; versamenti storici; passaggio delle fatture non pagate dal conto d'appoggio al fornitore |

## Limiti noti e punti da verificare in staging

- **Righe ritenuta nel widget "crediti in sospeso"**: una nota di credito con ritenuta del fornitore puo' comparire tra i crediti abbinabili alle altre sue fatture (e viceversa). Non abbinarla da li': si chiude con la nota di credito.
- **Arrotondamento di cassa**: se attivo, Odoo non considera la riga ritenuta nel calcolo dell'arrotondamento; da verificare se usato.
- **Chiusura IVA**: il modulo toglie le righe ritenuta dalla chiusura IVA (`use_in_tax_closing`), altrimenti la chiusura svuoterebbe i conti dei fornitori.
- **Da collaudare per primo**: registrazione di una fattura con ritenuta sul conto del fornitore (controllo `_check_payable_receivable`), "Registra pagamento" sul netto, riconciliazione bancaria della fattura dal widget banca (deve abbinare il netto, non la riga ritenuta), report scadenzario/partitario fornitori.
- **File telematici CU e 770**: pulsante presente, tracciato non implementato. Le specifiche dell'Agenzia per il 2027 escono a inizio 2027 (metodo `_abc_telematic_<anno>` su `abc.withholding.declaration`). Nel frattempo: export Excel.
- **PDF della CU**: prospetto con tutti i dati, non l'impaginazione del modello ministeriale.
- **Codici** non soggette (forfettari, spese art. 15), sanzioni (8906) e interessi (1989): configurabili sull'azienda, da confermare con lo studio ogni anno.
- **Pagamenti senza scrittura**: se il registro di pagamento non ha un conto "pagamenti in sospeso", la quota nasce alla riconciliazione con l'estratto conto, con la data della riga di banca.
- **Periodo chiuso**: se la data del pagamento cade in un periodo bloccato, la scrittura della ritenuta va alla data del giorno; la quota resta del mese del pagamento.
- Il modulo **non e' ancora stato installato su nessuna istanza**.

## Installazione

1. Copiare la cartella `abc_ritenute_acconto` nel repository dei moduli ABC collegato a Odoo.sh e fare push sul ramo di staging.
2. Aggiornare l'elenco moduli e installare "ABC - Ritenute d'acconto attive e passive".

## Configurazione (per ogni azienda)

Il modulo non e' legato a un cliente: vale per tutte le aziende Odoo 19 con localizzazione italiana. I codici conto citati sono quelli del piano dei conti standard l10n_it, a titolo di esempio.

1. **Azienda** (Impostazioni > Aziende > scheda "Ritenute d'acconto"): registro varie delle ritenute, responsabili dei promemoria, data di avvio, regime per le ritenute subite, firmatario e intermediario, codici CU.
2. **Imposte ritenuta**: Contabilita' > Configurazione > Ritenute > **Configura imposte ritenuta**. In un solo passaggio:
   - elenca le imposte ritenuta esistenti con gli avvisi (conto erariale mancante o incoerente, conto d'appoggio incoerente, fatture non pagate con la ritenuta sull'appoggio);
   - le configura: esigibilita' "in base alla fattura" senza conto d'appoggio, "Ritenuta sul conto del fornitore / cliente", codice tributo (1038 proposto per le aliquote da agente 11,5% e 4,6%), conti erariali riconciliabili;
   - propone le imposte standard che mancano (20% persone fisiche e giuridiche, 23% agenti, 30% non residenti, 4% condominio sulle vendite...) e le crea gia' configurate sui conti erariali indicati (es. 260200 Debiti per ritenute da versare, 160900 Crediti per ritenute subite).
   Altre imposte (ENASARCO, casse) si creano a mano come qualsiasi imposta e poi si configurano con lo stesso pulsante.
3. **Causali e codici tributo** (Contabilita' > Configurazione > Ritenute): tabella gia' caricata con A, M -> 1040 e Q, R -> 1038.
4. **Storico** (Configurazione > Ritenute > Ricostruisci storico), subito dopo il punto 2 e prima di registrare nuovi pagamenti. Dipende da come il cliente e' arrivato alla 19:

| Scenario | Come erano registrate le ritenute | Opzioni della ricostruzione |
| --- | --- | --- |
| Cliente nuovo sulla 19 | Imposte native "per cassa" con conto d'appoggio, oppure nessuna fattura con ritenuta | "Fatture dal", "versate fino al" = ultima scadenza gia' pagata, "Riporta sul fornitore/cliente le ritenute non ancora pagate" |
| Cliente migrato dalla 16 con il modulo OCA `l10n_it_withholding_tax` | Fornitore al lordo, dichiarazioni e movimenti ritenuta OCA (tabelle `withholding_tax_*` rimaste nel database) | "Importa lo storico del modulo OCA": importa ritenute e quote con lo stato dovuta/versata e le scritture OCA gia' fatte; per le fatture non ancora pagate separa la ritenuta residua dalla scadenza, cosi' "Registra pagamento" propone il netto |
| Cliente migrato dalla 16 che usava le imposte native | Come il cliente nuovo | Come il cliente nuovo |

Le due opzioni si possono usare insieme (fatture della 16 con OCA e fatture gia' registrate nella 19 con le imposte native). La ricostruzione si puo' rilanciare: non crea doppioni.

## Collaudo su staging

Casi della sezione 11 della specifica (1-26), su almeno un cliente nuovo e uno migrato dalla 16. Ordine consigliato:

1. Configurazione su una sola azienda, ricostruzione storico, quadratura dei conti erariali (ritenute da versare, ritenute subite) con il registro.
2. Ciclo passivo: casi 1-7 e 21-25 (fattura, pagamento totale e parziale, agosto, F24 riconciliato in banca, annullo, nota di credito, anticipo, compensazione, XML diverso, soglia, promemoria).
3. Ciclo attivo: casi 8-14 e 26.
4. CU e 770: casi 15-19; il caso 20 (telematico) resta aperto fino alle specifiche 2027.
5. Validazione dello studio sulle regole di compensazioni e note di credito (N1, casi 7 e 22).
6. Cliente migrato dalla 16: import OCA, confronto con le dichiarazioni OCA (menu del modulo `abc_account_withholding_tax_reports`, se installato), pagamento di una fattura OCA rimasta aperta, F24 di una quota OCA dovuta riconciliato in banca.
