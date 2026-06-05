# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)

MIGRATION_MAP = {
    "stock.picking.transport.condition": [
        "transport_condition_PF",
        "transport_condition_PA",
        "transport_condition_PAF",
    ],
    "stock.picking.goods.appearance": [
        "goods_appearance_CAR",
        "goods_appearance_BAN",
        "goods_appearance_SFU",
        "goods_appearance_CBA",
    ],
    "stock.picking.transport.reason": [
        "transport_reason_VEN",
        "transport_reason_VIS",
        "transport_reason_RES",
    ],
    "stock.picking.transport.method": [
        "transport_method_MIT",
        "transport_method_DES",
        "transport_method_COR",
    ],
}


def get_referencing_columns(cr, table_name):
    query = """
        SELECT 
            tc.table_name, 
            kcu.column_name
        FROM 
            information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' 
          AND ccu.table_name = %s;
    """
    cr.execute(query, (table_name,))
    return cr.fetchall()


def merge_records(cr, table_name, old_id, new_id):
    if old_id == new_id:
        return
    
    # Find all columns referencing this table
    referencing = get_referencing_columns(cr, table_name)
    for ref_table, ref_col in referencing:
        # Update referencing records to point to the old record instead of the new record.
        _logger.info("Merging table %s: updating %s.%s from %s to %s", table_name, ref_table, ref_col, new_id, old_id)
        query = f'UPDATE "{ref_table}" SET "{ref_col}" = %s WHERE "{ref_col}" = %s'
        cr.execute(query, (old_id, new_id))
    
    # Delete the new duplicate record
    _logger.info("Deleting duplicate record ID %s from %s", new_id, table_name)
    query = f'DELETE FROM "{table_name}" WHERE id = %s'
    cr.execute(query, (new_id,))


def migrate(cr, version):
    if not version:
        return

    for model, xml_ids in MIGRATION_MAP.items():
        table_name = model.replace(".", "_")
        
        # Check if the table exists
        cr.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
            (table_name,),
        )
        if not cr.fetchone()[0]:
            continue

        for xml_id in xml_ids:
            # Check if there is an entry for l10n_it_delivery_note_base
            cr.execute(
                "SELECT res_id, id FROM ir_model_data WHERE module = %s AND name = %s AND model = %s",
                ("l10n_it_delivery_note_base", xml_id, model),
            )
            base_res = cr.fetchone()
            
            # Check if there is an entry for l10n_it_delivery_note
            cr.execute(
                "SELECT res_id, id FROM ir_model_data WHERE module = %s AND name = %s AND model = %s",
                ("l10n_it_delivery_note", xml_id, model),
            )
            note_res = cr.fetchone()

            if base_res and not note_res:
                # Scenario 1: Only base XML ID exists. Rename the module in ir_model_data to l10n_it_delivery_note.
                # Verify base record exists in table
                cr.execute(f'SELECT id FROM "{table_name}" WHERE id = %s', (base_res[0],))
                if cr.fetchone():
                    _logger.info("Moving XML ID %s.%s to l10n_it_delivery_note.%s", "l10n_it_delivery_note_base", xml_id, xml_id)
                    cr.execute(
                        "UPDATE ir_model_data SET module = %s WHERE id = %s",
                        ("l10n_it_delivery_note", base_res[1]),
                    )
                else:
                    # XML ID exists but actual record is missing. Delete the orphaned XML ID.
                    cr.execute("DELETE FROM ir_model_data WHERE id = %s", (base_res[1],))
            elif base_res and note_res:
                # Scenario 2: Both base and note XML IDs exist.
                base_res_id = base_res[0]
                note_res_id = note_res[0]
                
                # Verify both records exist in the table
                cr.execute(f'SELECT id FROM "{table_name}" WHERE id IN (%s, %s)', (base_res_id, note_res_id))
                found_ids = [r[0] for r in cr.fetchall()]
                
                if base_res_id in found_ids and note_res_id in found_ids:
                    merge_records(cr, table_name, base_res_id, note_res_id)
                    cr.execute(
                        "UPDATE ir_model_data SET res_id = %s WHERE id = %s",
                        (base_res_id, note_res[1]),
                    )
                    cr.execute(
                        "DELETE FROM ir_model_data WHERE id = %s",
                        (base_res[1],),
                    )
                elif base_res_id in found_ids:
                    # Only the base record exists. Update the note XML ID to point to the base record, and delete base XML ID.
                    cr.execute(
                        "UPDATE ir_model_data SET res_id = %s WHERE id = %s",
                        (base_res_id, note_res[1]),
                    )
                    cr.execute(
                        "DELETE FROM ir_model_data WHERE id = %s",
                        (base_res[1],),
                    )
                elif note_res_id in found_ids:
                    # Only the note record exists. Delete base XML ID.
                    cr.execute(
                        "DELETE FROM ir_model_data WHERE id = %s",
                        (base_res[1],),
                    )
