# Compatibilità con Odoo 19.0 verificata con Claude (2026-03-31)
# In attesa della migrazione di delivery_carrier_partner da parte di OCA
# Copyright 2017 Lorenzo Battistini - Agile Business Group
# Copyright 2020 Simone Vanin - Agile Business Group
# Copyright 2023 Simone Rubino - Aion Tech
# Copyright 2025 Simone Rubino
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "ITA - Fattura accompagnatoria",
    "summary": "Stampa della fattura accompagnatoria",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "website": "https://github.com/OCA/l10n-italy",
    "author": "Agile Business Group, " "Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "l10n_it_delivery_note",
    ],
    "data": [
        "views/account.xml",
        "views/report_invoice.xml",
    ],
}
