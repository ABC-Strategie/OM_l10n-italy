# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade

OLD_MODULE_NAME = "l10n_it_intrastat_statement"
NEW_MODULE_NAME = "l10n_it_intrastat_statement_oca"


def pre_absorb_old_module(cr):
    """Assorbe il modulo omonimo pre-rinomina, prima dell'installazione.

    Lo Statement non collide con alcun modulo Enterprise: viene rinominato per
    restare coerente con `l10n_it_intrastat_oca`, da cui dipende, e con i nomi
    scelti da OCA per la 19.
    """
    if openupgrade.is_module_installed(cr, OLD_MODULE_NAME):
        openupgrade.update_module_names(
            cr,
            [
                (OLD_MODULE_NAME, NEW_MODULE_NAME),
            ],
            merge_modules=True,
        )
        _rename_report_references(cr)


def _rename_report_references(cr):
    """Aggiorna i riferimenti al modulo che NON sono ID esterni.

    `update_module_names` sposta `ir_model_data`, `ir_module_module` e le
    dipendenze, ma non tocca i campi che contengono il nome del modulo come
    *stringa*. I nove `ir.actions.report` dello Statement hanno `report_name` e
    `report_file` nella forma `<modulo>.report_intrastat_mod1`: senza questo
    passaggio resterebbero a puntare a un template che non si chiama piu' cosi',
    e la stampa della dichiarazione fallirebbe.

    `position(... in ...) = 1` invece di `LIKE`: gli underscore del nome del
    modulo sarebbero wildcard di LIKE, e la condizione sarebbe piu' larga del
    voluto. La sostituzione e' idempotente, perche' il prefisso gia' rinominato
    non contiene piu' la stringa cercata.
    """
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_act_report_xml
        SET report_name = replace(report_name, %(old)s, %(new)s),
            report_file = replace(report_file, %(old)s, %(new)s)
        WHERE position(%(old)s in report_name) = 1
           OR position(%(old)s in coalesce(report_file, '')) = 1
        """,
        {
            "old": OLD_MODULE_NAME + ".",
            "new": NEW_MODULE_NAME + ".",
        },
    )
