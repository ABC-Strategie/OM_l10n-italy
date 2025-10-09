#  Copyright 2024 Simone Rubino - Aion Tech
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# from openupgradelib import openupgrade

# MODEL_TO_RENAMED_FIELDS = {
#     "asset.depreciation.mode.line": [
#         ("from_nr", "from_year_nr"),
#         ("to_nr", "to_year_nr"),
#     ]
# }


# def _rename_fields(env):
#     openupgrade.rename_fields(
#         env,
#         [
#             (
#                 model_name,
#                 model_name.replace(".", "_"),
#                 field_spec[0],
#                 field_spec[1],
#             )
#             for model_name, field_specs in MODEL_TO_RENAMED_FIELDS.items()
#             for field_spec in field_specs
#         ],
#     )


# @openupgrade.migrate()
# def migrate(env, version):
#     _rename_fields(env)

#  Copyright 2024 ...
#  License AGPL-3.0 or later.

import logging
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

# (model, table, old_col, new_col)
RENAMES = [
    ("asset.depreciation.mode.line", "asset_depreciation_mode_line", "from_nr", "from_year_nr"),
    ("asset.depreciation.mode.line", "asset_depreciation_mode_line", "to_nr",   "to_year_nr"),
]

@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    fields_to_rename = []

    for model, table, old, new in RENAMES:
        old_exists = openupgrade.column_exists(cr, table, old)
        new_exists = openupgrade.column_exists(cr, table, new)

        # Caso richiesto: rinomina SOLO se esiste la vecchia e NON esiste la nuova
        if old_exists and not new_exists:
            _logger.info("Renaming column %s.%s -> %s", table, old, new)
            openupgrade.rename_columns(cr, {table: [(old, new)]})
            fields_to_rename.append((model, table, old, new))
        else:
            # Se la nuova esiste già (e la vecchia no), non facciamo nulla.
            # Se non esiste né vecchia né nuova, non facciamo nulla.
            # Se esistono entrambe (caso anomalo), non forziamo nulla (coerente con la tua richiesta).
            _logger.info(
                "Skip rename for %s.%s -> %s (old_exists=%s, new_exists=%s)",
                table, old, new, old_exists, new_exists
            )

    # Allinea i metadati SOLO per i renames effettivamente fatti
    if fields_to_rename:
        openupgrade.rename_fields(env, fields_to_rename)
