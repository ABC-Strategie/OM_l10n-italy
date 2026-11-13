# ABC - CIG e CUP sugli ordini di acquisto

Aggiunge sull'ordine di acquisto i campi **CIG** (Codice Identificativo
Gara) e **CUP** (Codice Unico di Progetto), nella scheda **Altre
informazioni**, gruppo "Fatturazione elettronica italiana".

La visibilità segue la stessa regola dell'ordine di vendita
(`l10n_it_edi_sale`): i campi compaiono se l'azienda è italiana e il
fornitore ha un codice destinatario di 6 caratteri (Pubblica
Amministrazione) o di 7 caratteri (codice SDI dei privati, ad esempio
subappalti su lavori pubblici).

CIG e CUP sono anche:

- colonne della vista lista (Richieste di preventivo, Ordini di acquisto,
  acquisti aperti dal fornitore), nascondibili dal selettore colonne;
- campi di ricerca e voci di **Raggruppa per** (CIG, CUP) nella ricerca
  delle Richieste di preventivo e degli Ordini di acquisto.

Note:

- I campi non vengono copiati quando si duplica l'ordine.
- I valori restano sull'ordine di acquisto: non vengono riportati sulla
  fattura fornitore.
