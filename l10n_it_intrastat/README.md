# l10n_it_intrastat (modulo ponte)

Modulo **senza codice e senza dati**. Serve solo a completare, su un database esistente, la rinomina
`l10n_it_intrastat` → `l10n_it_intrastat_oca`, fatta per sbloccare la migrazione a Odoo 19 (vedi il
commit 03560702f e `l10n_it_intrastat_oca/hooks.py`).

**Non installarlo su database nuovi**: lì va installato direttamente `l10n_it_intrastat_oca`.

## Perché serve

Il merge del vecchio modulo nel nuovo è fatto dal `pre_init_hook` di `l10n_it_intrastat_oca`, che parte solo
quando quel modulo viene **installato**. Alla build, Odoo.sh lancia `-u` solo dei moduli già installati con la
versione cambiata e non installa mai moduli nuovi. Senza questo ponte, `l10n_it_intrastat_oca` non viene
installato, l'hook non parte e il vecchio modulo resta "installato" senza codice
(`Some modules are not loaded`, `Missing model account.invoice.intrastat`).

## Come funziona

1. Nel database il vecchio `l10n_it_intrastat` è installato a 16.0.1.1.3, questo ponte è a 16.0.1.3.0: Odoo.sh
   vede la versione cambiata e lancia `-u l10n_it_intrastat`.
2. `button_upgrade` installa le dipendenze non installate: `l10n_it_intrastat_oca` passa a "da installare".
3. Il ponte viene rinviato, perché la sua dipendenza non è ancora caricata (log INFO `Unmet dependencies`).
4. All'installazione di `l10n_it_intrastat_oca` il `pre_init_hook` trova il vecchio modulo "da aggiornare",
   sposta i suoi ID esterni e le dipendenze sul nuovo nome e cancella la riga del vecchio modulo, cioè di
   questo ponte.
5. A fine aggiornamento resta installato solo `l10n_it_intrastat_oca`, con tabelle e dati invariati.

Dalla build successiva il ponte ricompare tra i moduli come "non installato", senza dati: è innocuo.

## Quando toglierlo

Dopo il passaggio a Odoo 19 di tutti i database (stage e produzione). Non va portato nel codice 19.
