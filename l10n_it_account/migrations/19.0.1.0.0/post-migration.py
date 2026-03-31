import logging

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Script di post-migrazione per Odoo 19.
    Disattiva brutalmente tramite SQL le viste legacy (incluse quelle di Studio)
    che contengono riferimenti a campi o metodi rimossi, per evitare crash di Owl.
    """
    _logger.info("====================================================")
    _logger.info("Inizio bonifica delle viste legacy per la v19...")
    _logger.info("====================================================")

    # Query SQL pura per aggirare la validazione XML di Odoo
    query = """
        UPDATE ir_ui_view v
        SET active = false
        WHERE active = true
        AND EXISTS (
            SELECT 1
            FROM jsonb_each_text(v.arch_db) AS t(lang, xml)
            WHERE xml ILIKE %s
            OR xml ILIKE %s
        );
    """
    
    params = ('%name="admin_ref"%', '%name="action_open_export_send_sdi"%')
    cr.execute(query, params)
    
    # Contiamo quante viste abbiamo disattivato per avere un riscontro nel log
    archived_count = cr.rowcount
    _logger.info("Bonifica completata con successo: archiviate %s viste rotte.", archived_count)
    _logger.info("====================================================")