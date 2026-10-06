# Copyright 2026 ABC-Strategie S.r.l.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import json
import logging
import re

_logger = logging.getLogger(__name__)

# Campo di account.tax tolto da OCA il 04/04/2025 (REF removing cee_type),
# senza migrazione dei valori: sulla 19 nessun modulo lo definisce piu', e
# ogni vista che lo nomina non supera la validazione.
FIELD = "cee_type"
FIELD_TAG_PATTERNS = (
    re.compile(r'<field\s+name=["\']cee_type["\'][^>]*/>'),
    re.compile(r'<field\s+name=["\']cee_type["\'][^>]*>.*?</field>', re.DOTALL),
)
# Viste dei clienti: senza xmlid, create da Studio o esportate.
CUSTOMER_VIEW_MODULES = ("__export__", "studio_customization")


def _clean_arch(arch):
    for pattern in FIELD_TAG_PATTERNS:
        arch = pattern.sub("", arch)
    return arch


def _clean_field_tags(cr):
    """Toglie i tag <field name="cee_type"> da tutte le viste che lo nominano."""
    cr.execute(
        "SELECT id, arch_db FROM ir_ui_view WHERE arch_db::text LIKE %s",
        (f"%{FIELD}%",),
    )
    for view_id, arch_db in cr.fetchall():
        if not arch_db:
            continue
        new_arch_db = {
            lang: _clean_arch(arch) if arch else arch
            for lang, arch in arch_db.items()
        }
        if new_arch_db != arch_db:
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                (json.dumps(new_arch_db), view_id),
            )
            _logger.info("cee_type: tolto il campo dalla vista %s", view_id)


def _disable_remaining_customer_views(cr):
    """Rete di sicurezza per le forme che le regex non coprono.

    Per esempio <xpath expr="//field[@name='cee_type']">, <label for="cee_type">
    o un'espressione invisible="... cee_type ...". Si disattivano solo le viste
    dei clienti: quelle dei moduli vengono riscritte dal loro XML, e in
    aggiornamento Odoo non riscrive il campo active (vedi ir_ui_view.py), quindi
    spegnerle le lascerebbe spente per sempre. Per quelle solo un avviso.
    """
    cr.execute(
        """
        SELECT v.id, d.module
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
                 ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE v.active AND v.arch_db::text LIKE %s
        """,
        (f"%{FIELD}%",),
    )
    modules_by_view = {}
    for view_id, module in cr.fetchall():
        modules_by_view.setdefault(view_id, set()).add(module)
    customer_ids, module_ids = [], []
    for view_id, modules in sorted(modules_by_view.items()):
        if all(not m or m in CUSTOMER_VIEW_MODULES for m in modules):
            customer_ids.append(view_id)
        else:
            module_ids.append(view_id)
    if customer_ids:
        cr.execute(
            "UPDATE ir_ui_view SET active = FALSE WHERE id IN %s",
            (tuple(customer_ids),),
        )
        _logger.warning(
            "cee_type: disattivate %s viste personalizzate che lo nominano ancora "
            "(da correggere e riattivare): %s",
            len(customer_ids),
            customer_ids,
        )
    if module_ids:
        _logger.warning(
            "cee_type: viste di moduli che lo nominano ancora, lasciate al "
            "ricaricamento del loro XML: %s",
            module_ids,
        )


def migrate(cr, version):
    if not version:
        return
    _logger.info("Pre-migration: riferimenti al campo rimosso %s nelle viste", FIELD)
    _clean_field_tags(cr)
    _disable_remaining_customer_views(cr)
