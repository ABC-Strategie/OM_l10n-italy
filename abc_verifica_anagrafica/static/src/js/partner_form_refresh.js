/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { onWillUnmount } from "@odoo/owl";

const NOTIFICATION_TYPE = "abc_va/partner_updated";
// Modelli le cui schede vanno ricaricate quando cambia l'esito di verifica
// del contatto: la scheda del contatto stesso e i documenti che lo
// riportano (preventivi/ordini, fatture), così i banner compaiono da soli.
const PARTNER_MODEL = "res.partner";
const DOCUMENT_MODELS = ["sale.order", "account.move"];

function many2oneId(value) {
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0];
    }
    if (typeof value === "object") {
        return value.id;
    }
    return value;
}

/**
 * Ricarica la scheda quando il server segnala che la verifica del codice
 * fiscale o della partita IVA di un contatto si è conclusa (verifica
 * sincrona o elaborata dal cron). La notifica arriva sul bus dell'utente che
 * ha innescato la verifica; la scheda viene ricaricata solo se riguarda il
 * contatto interessato e non ha modifiche non salvate.
 */
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        const model = this.props.resModel;
        if (model !== PARTNER_MODEL && !DOCUMENT_MODELS.includes(model)) {
            return;
        }
        const bus = this.env.services.bus_service;
        if (!bus || typeof bus.subscribe !== "function") {
            return;
        }
        const onPartnerUpdated = (payload) => {
            const root = this.model && this.model.root;
            if (!root || root.isNew || !payload || root.dirty) {
                return;
            }
            let concerned = false;
            if (model === PARTNER_MODEL) {
                concerned = root.resId === payload.partner_id;
            } else {
                const data = root.data || {};
                concerned = [many2oneId(data.partner_id), many2oneId(data.commercial_partner_id)]
                    .includes(payload.partner_id);
            }
            if (concerned) {
                root.load();
            }
        };
        bus.subscribe(NOTIFICATION_TYPE, onPartnerUpdated);
        onWillUnmount(() => bus.unsubscribe(NOTIFICATION_TYPE, onPartnerUpdated));
    },
});
