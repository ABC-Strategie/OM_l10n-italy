from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    abc_wh_tax_regime = fields.Char(
        string="Regime fiscale (da XML)",
        help="Valore di RegimeFiscale letto dall'ultima fattura elettronica ricevuta "
             "(RF19 forfettario, RF02 minimi, RF01 ordinario...).",
    )
    abc_wh_flat_rate = fields.Boolean(
        string="Forfettario o minimi",
        help="Compensi non soggetti a ritenuta da indicare comunque in CU (D58). "
             "Impostato in automatico dall'XML, modificabile.",
    )
    abc_wh_non_resident = fields.Boolean(string="Non residente ai fini delle ritenute")
    abc_wh_residence_cert = fields.Binary(string="Certificato di residenza fiscale", attachment=True)
    abc_wh_residence_cert_name = fields.Char(string="Nome file certificato")
    abc_wh_residence_cert_expiry = fields.Date(string="Validita' certificato fino al")
    # Dati anagrafici per la CU dei percipienti persone fisiche
    abc_wh_birth_date = fields.Date(string="Data di nascita")
    abc_wh_birth_city = fields.Char(string="Comune di nascita")
    abc_wh_birth_province = fields.Char(string="Provincia di nascita (sigla)")
    abc_wh_gender = fields.Selection([("M", "M"), ("F", "F")], string="Sesso")
    abc_wh_cu_email = fields.Char(
        string="Email per invio CU",
        help="Se vuota si usa l'email del contatto.",
    )
