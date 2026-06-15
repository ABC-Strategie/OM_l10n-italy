# Copyright 2026 ABC-Strategie S.r.l.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging
import json
import re

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("Pre-migration: Cleaning up legacy cee_type field references in ir_ui_view to prevent Registry load crashes")

    # Select all views that contain 'cee_type' in their arch
    cr.execute("SELECT id, arch_db FROM ir_ui_view WHERE arch_db::text LIKE '%cee_type%'")
    rows = cr.fetchall()

    for row_id, arch_db in rows:
        if not arch_db:
            continue
        new_arch_db = {}
        updated = False
        for lang, arch in arch_db.items():
            if not arch:
                new_arch_db[lang] = arch
                continue

            # Remove any occurrence of cee_type field in XML
            # Pattern for <field name="cee_type" ... />
            cleaned_arch = re.sub(r'<field\s+name=["\']cee_type["\'][^>]*/>', '', arch)
            # Pattern for <field name="cee_type" ...> ... </field>
            cleaned_arch = re.sub(r'<field\s+name=["\']cee_type["\'][^>]*>.*?</field>', '', cleaned_arch, flags=re.DOTALL)

            if cleaned_arch != arch:
                updated = True
            new_arch_db[lang] = cleaned_arch

        if updated:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(new_arch_db), row_id))
            _logger.info("Cleaned legacy cee_type reference from ir_ui_view ID %s", row_id)

    _logger.info("Pre-migration: legacy cee_type cleanup finished.")
