# Copyright 2025 Giuseppe Borruso - Dinamiche Aziendali srl
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
from io import BytesIO

from lxml import etree

from odoo import api, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Spazi ammessi dentro un base64 "a capo", da togliere prima di decodificare.
_ASCII_WHITESPACE = b" \t\n\r\x0b\x0c"


class IrAttachmentInherit(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def get_fatturapa_preview_style_name(self):
        """Hook to have a clean inheritance."""
        return "FoglioStileAssoSoftware.xsl"

    @api.model
    def _l10n_it_edi_ext_decode_base64(self, content, name=None):
        """Alcuni programmi scaricano il .p7m come TESTO base64 invece che binario.

        Portato da OCA 18.0 (commit 0cd67e88, "some .xml.p7m are base64"): gli
        spazi vanno tolti PRIMA di decodificare, altrimenti ``validate=True``
        rifiuta un base64 che e' valido ma scritto su piu' righe.
        Restituisce il contenuto originale, invariato, se non e' base64.
        """
        try:
            stripped = bytes(content).translate(None, _ASCII_WHITESPACE)
            decoded = base64.b64decode(stripped, validate=True)
        except Exception:
            return content
        _logger.info(
            "'%s' riconosciuto come p7m codificato in base64 (%d byte ASCII -> %d byte DER).",
            name,
            len(content),
            len(decoded),
        )
        return decoded

    def _l10n_it_edi_ext_parse(self, content, name=None):
        """Albero XML della fattura, oppure ``None``.

        Si appoggia a ``account.move._parse_xml_with_recovery`` del core 19, che
        gia' prova il parsing diretto e poi ``remove_signature`` per le buste
        CAdES. Se anche quello fallisce, si riprova dopo aver decodificato un
        eventuale base64.
        """
        parse = self.env["account.move"]._parse_xml_with_recovery
        xml_tree = parse(content, name=name)
        if xml_tree is None:
            decoded = self._l10n_it_edi_ext_decode_base64(content, name=name)
            if decoded is not content:
                xml_tree = parse(decoded, name=name)
        return xml_tree

    def get_xml_string(self):
        """XML della fattura elettronica, anche da allegato firmato.

        ⛔ NON si decide piu' in base al ``mimetype``. Il controllo precedente
        accettava il p7m solo con ``mimetype == 'application/pkcs7-mime'``, e
        quel campo non e' garantito: su Comart 549 allegati ``.xml.p7m`` sono
        registrati come ``application/octet-stream`` (importati fra gennaio
        2022 e dicembre 2023) e l'anteprima moriva con "Invalid xml", pur
        essendo buste PKCS#7 valide - misurato sul build
        comart-migrazione-19-39930549 il 13/11/2026.

        Lo stesso caso e' corretto in OCA 18.0 con
        ``_is_l10n_it_edi_import_file``, che qui NON si puo' riusare: in Odoo
        19 quel metodo vive su ``account.move``, ha un'altra firma e riceve un
        ``file_data`` con l'albero gia' parsato.

        Si decide quindi sul CONTENUTO: e' una fattura elettronica se l'albero
        XML che se ne ricava ha la radice ``FatturaElettronica*``. Un PDF o un
        allegato estraneo non supera questo controllo.
        """
        xml_tree = self._l10n_it_edi_ext_parse(self.raw, name=self.name)
        if xml_tree is None or not etree.QName(xml_tree).localname.startswith(
            "FatturaElettronica"
        ):
            raise UserError(self.env._("Invalid xml %s.") % self.name)

        return etree.tostring(xml_tree, pretty_print=True, encoding="unicode").encode()

    def get_fattura_elettronica_preview(self):
        xsl_path = tools.misc.file_path(
            f"l10n_it_edi_extension/data/{self.get_fatturapa_preview_style_name()}"
        )
        xslt = etree.parse(xsl_path)
        xml_string = self.sudo().get_xml_string()
        xml_file = BytesIO(xml_string)
        recovering_parser = etree.XMLParser(recover=True, resolve_entities=False)
        dom = etree.parse(xml_file, parser=recovering_parser)
        transform = etree.XSLT(xslt)
        newdom = transform(dom)
        return etree.tostring(newdom, pretty_print=True, encoding="unicode")
