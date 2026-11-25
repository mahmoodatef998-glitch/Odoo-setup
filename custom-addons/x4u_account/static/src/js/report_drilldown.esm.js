/** Spec §22 G3: a click on a line of an OCA accounting report opens its document.
 *
 * Odoo links every cell that has res-model / res-id: the Entry opens the invoice, bill or journal
 * entry, but the date, label and amounts open the journal item, one line of it, which is not what
 * the accountant is looking for. Here a click on a journal item opens its entry instead; journals,
 * accounts and partners keep opening themselves. */
import {ReportAction} from "@web/webclient/actions/reports/report_action";
import {patch} from "@web/core/utils/patch";
import {useEffect} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

const JOURNAL_ITEM = '[res-model="account.move.line"][res-id]';

patch(ReportAction.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.props.report_name.startsWith("account_financial_report.")) {
            return;
        }
        const orm = useService("orm");
        const action = useService("action");
        const openEntry = async (lineId) => {
            const [line] = await orm.read("account.move.line", [lineId], ["move_id"]);
            action.doAction({
                type: "ir.actions.act_window",
                res_model: "account.move",
                res_id: line.move_id[0],
                views: [[false, "form"]],
                target: "current",
            });
        };
        // Capture phase: before Odoo's own link on the cell opens the journal item.
        const onClick = (ev) => {
            const cell = ev.target.closest(JOURNAL_ITEM);
            const lineId = cell && parseInt(cell.getAttribute("res-id"), 10);
            if (lineId) {
                ev.preventDefault();
                ev.stopPropagation();
                openEntry(lineId);
            }
        };
        useEffect(
            (iframe) => {
                if (!iframe) {
                    return;
                }
                const onLoad = () => {
                    const doc = iframe.contentDocument;
                    if (doc && !doc.x4uDrilldown) {
                        doc.x4uDrilldown = true;
                        doc.addEventListener("click", onClick, true);
                    }
                };
                iframe.addEventListener("load", onLoad);
                onLoad();
                return () => iframe.removeEventListener("load", onLoad);
            },
            () => [this.iframe.el]
        );
    },
});
