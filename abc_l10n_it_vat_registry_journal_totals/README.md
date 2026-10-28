# ABC - Registro IVA: parziali per sezionale

Nella stampa PDF del registro IVA (`l10n_it_vat_registries`), quando
l'ordinamento è **Registro - Data - Numero**, in fondo a ogni sezione
(sezionale) viene stampato il riepilogo parziale per aliquota con le stesse
colonne dei Totali finali: Imponibile, Imposta, Detraibile, Indetraibile,
più la riga **Totale sezione**.

I parziali sono calcolati con la stessa logica dei Totali finali, ristretta
al singolo sezionale (data di competenza IVA, split payment e reverse charge
compresi), quindi la loro somma coincide con il Totale generale.

Note:
- Con l'ordinamento **Data - Numero** il registro non ha sezioni e i
  parziali non vengono stampati.
- I parziali compaiono anche con **Stampa solo i totali**.
- La stampa XLSX non è modificata.
