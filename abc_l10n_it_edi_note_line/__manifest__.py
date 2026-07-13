{
    'name': 'ABC L10n IT EDI Note Line',
    'version': '19.0.1.0.1',
    'category': 'Accounting/Localizations',
    'summary': 'Export note lines in Italian EDI XML',
    'author': "Fabrizio D'Adamo",
    'website': 'www.abcstrategie.it',
    'description': """
    In Odoo 19 (master) / 18, note lines (display_type="line_note") are excluded from the Italian electronic invoice XML (FatturaPA).
    This module restores the behavior of exporting note lines as <DettaglioLinee> in the XML.
    """,
    'depends': ['l10n_it_edi'],
    'data': [],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
