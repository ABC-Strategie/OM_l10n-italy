# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade

OLD_MODULE_NAME = "l10n_it_intrastat"
NEW_MODULE_NAME = "l10n_it_intrastat_oca"


def pre_absorb_old_module(cr):
    """Assorbe il modulo omonimo pre-rinomina, prima dell'installazione.

    Odoo 19 Enterprise ha introdotto un modulo proprio chiamato
    `l10n_it_intrastat`, che non esiste su 16, 17 e 18. Finche' il modulo OCA
    porta quello stesso nome tecnico, nella migrazione a 19 la piattaforma di
    upgrade risolve il nome con il modulo Enterprise e cancella come orfani i
    record `ir_model_data` creati dall'OCA, fermandosi sul primo campo che non
    puo' rimuovere.

    Rinominando qui, cioe' *sul 16*, il database arriva all'upgrade senza piu'
    nulla intestato a `l10n_it_intrastat`: il modulo Enterprise trova il nome
    libero e l'upgrade prosegue. La rinomina non puo' essere fatta da un hook
    sul 19, perche' quello girerebbe all'installazione del modulo nuovo, cioe'
    dopo il punto in cui l'upgrade si interrompe.

    Sul 16 la guardia non deve distinguere l'OCA dall'omonimo Enterprise, come
    invece fanno le PR OCA per la 19: su questa versione l'Enterprise non
    esiste, quindi `l10n_it_intrastat` e' senza ambiguita' il modulo OCA.

    Sono rinominati i moduli, non i modelli: `account.invoice.intrastat` e gli
    altri restano com'erano, con le loro tabelle e i loro dati. Il modulo
    Enterprise omonimo non dichiara alcun modello, quindi non c'e' nessuna
    omonimia di tabella da sciogliere.
    """
    if openupgrade.is_module_installed(cr, OLD_MODULE_NAME):
        openupgrade.update_module_names(
            cr,
            [
                (OLD_MODULE_NAME, NEW_MODULE_NAME),
            ],
            merge_modules=True,
        )
