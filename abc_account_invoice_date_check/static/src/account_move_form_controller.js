import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { AccountMoveFormController } from "@account/components/account_move_form/account_move_form";

// Conferma di una fattura con l'avviso sulla data: popup con "Conferma" e
// "Annulla" prima del salvataggio e della chiamata ad action_post. Il
// controllo e' lato client perche' nessun override di action_post venga
// eseguito se l'utente annulla.
patch(AccountMoveFormController.prototype, {
    async beforeExecuteActionButton(clickParams) {
        const warning = this.model.root.data.abc_invoice_date_warning;
        if (clickParams.name === "action_post" && warning) {
            const confirmed = await new Promise((resolve) => {
                this.dialogService.add(
                    ConfirmationDialog,
                    {
                        title: _t("Data fattura non cronologica"),
                        body: `${warning}\n\n${_t("Confermare comunque la fattura?")}`,
                        confirmLabel: _t("Conferma"),
                        cancelLabel: _t("Annulla"),
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    },
                    // X o Esc: come Annulla.
                    { onClose: () => resolve(false) }
                );
            });
            if (!confirmed) {
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});
