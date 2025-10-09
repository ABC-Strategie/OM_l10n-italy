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

from openupgradelib import openupgrade

# mapping: (model, table, old_col, new_col)
RENAMES = [
    ("asset.depreciation.mode.line", "asset_depreciation_mode_line", "from_nr", "from_year_nr"),
    ("asset.depreciation.mode.line", "asset_depreciation_mode_line", "to_nr", "to_year_nr"),
]

def _safe_rename(env):
    cr = env.cr
    for model, table, old, new in RENAMES:
        new_exists = openupgrade.column_exists(cr, table, new)
        old_exists = openupgrade.column_exists(cr, table, old)

        # Se entrambe esistono, porta i dati sulla nuova e rimuovi la vecchia
        if new_exists and old_exists:
            openupgrade.logged_query(cr, f"""
                UPDATE {table} SET {new} = COALESCE({new}, {old})
            """)
            openupgrade.logged_query(cr, f'ALTER TABLE "{table}" DROP COLUMN "{old}"')

        # Se esiste solo la vecchia, fai il vero rename
        elif (not new_exists) and old_exists:
            openupgrade.rename_columns(cr, {table: [(old, new)]})

        # In tutti i casi, sincronizza i metadati di Odoo (ir.model.fields)
        openupgrade.rename_field(env, model, old, new)

@openupgrade.migrate()
def migrate(env, version):
    _safe_rename(env)
