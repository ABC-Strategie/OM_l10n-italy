# Copyright 2026 A.B.C. Srl
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "ITA - Intrastat (ponte verso l10n_it_intrastat_oca)",
    # Deve restare piu' alta della versione installata del vecchio modulo
    # (16.0.1.1.3): e' il cambio di versione a far lanciare a Odoo.sh `-u`.
    "version": "16.0.1.3.0",
    "category": "Hidden",
    "summary": "Modulo ponte della rinomina: fa installare l10n_it_intrastat_oca, "
    "che lo assorbe. Non installare su database nuovi.",
    "author": "A.B.C. Srl",
    "website": "https://github.com/ABC-Strategie/OM_l10n-italy",
    "license": "AGPL-3",
    # Aggiornando questo modulo, Odoo installa la dipendenza mancante: il suo
    # pre_init_hook assorbe questo modulo e ne cancella la riga. Vedi README.md.
    "depends": [
        "l10n_it_intrastat_oca",
    ],
    "data": [],
    "installable": True,
}
