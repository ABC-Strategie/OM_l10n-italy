# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade


def set_exclude_from_vat_settlements(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_tax SET exclude_from_vat_settlements = True
        WHERE vat_statement_account_id IS NULL;
        """,
    )


def pre_absorb_old_module(env):
    _detach_children(env, 3739)
    _disable_view_by_xmlid(env, "l10n_it_vat_statement_communication.view_tax_vsc_form")
    _disable_view_by_xmlid(env, "studio_customization.odoo_studio_fatturap_37189039-d2c5-4187-b7be-814a1f91510b")
    _disable_view_by_xmlid(env, "abc_efatturazione.fatturapa_attachment_in_tree_date")
    _disable_view_by_xmlid(env, "l10n_it_fatturapa_export_zip.view_fatturapa_in_attachment_tree")
    if openupgrade.is_module_installed(env.cr, "account_vat_period_end_statement"):
        openupgrade.update_module_names(
            env.cr,
            [
                (
                    "account_vat_period_end_statement",
                    "l10n_it_account_vat_period_end_settlement",
                ),
            ],
            merge_modules=True,
        )
        #set_exclude_from_vat_settlements(env)
        


def _disable_view_by_xmlid(env, xmlid: str):
    """Disattiva una vista (ir.ui.view) se esiste, identificata da XMLID."""
    if not xmlid or "." not in xmlid:
        return
    module, name = xmlid.split(".", 1)

    env.cr.execute(
        """
        UPDATE ir_ui_view v
        SET active = FALSE
        FROM ir_model_data d
        WHERE d.model = 'ir.ui.view'
          AND d.res_id = v.id
          AND d.module = %s
          AND d.name = %s
        """,
        (module, name),
    )
def _detach_children(env, parent_id: int):
    """Disattiva e stacca tutte le viste che ereditano parent_id (anche senza xmlid)."""
    env.cr.execute(
        """
        UPDATE ir_ui_view
        SET active = FALSE,
            inherit_id = NULL
        WHERE inherit_id = %s
        """,
        (parent_id,),
    )

