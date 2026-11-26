/** The user, 2026-11-26: the Delivery Note "sometimes refuses to upload".
 *
 * Odoo's FileInput disables its button while uploading and enables it again only when the upload
 * ends normally. An empty file (0 bytes) or a failed upload stopped it half-way: the button stayed
 * grey until the page was reloaded. Here an empty file gets a clear message instead, and the button
 * always comes back. Odoo's own file is not changed. */
import {FileInput} from "@web/core/file_input/file_input";
import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

patch(FileInput.prototype, {
    async onFileInputChange() {
        const input = this.fileInputRef.el;
        const files = input ? [...input.files] : [];
        const empty = files.filter((file) => !file.size);
        if (!files.length || empty.length) {
            if (empty.length) {
                this.env.services.notification.add(
                    _t(
                        "%s is empty (0 bytes), so it can't be uploaded. Choose the file again, or save a new copy of it first.",
                        empty.map((file) => file.name).join(", ")
                    ),
                    {type: "warning"}
                );
            }
            if (input) {
                input.value = null;
            }
            this.state.isDisable = false;
            return;
        }
        try {
            return await super.onFileInputChange(...arguments);
        } finally {
            this.state.isDisable = false;
            if (this.fileInputRef.el) {
                this.fileInputRef.el.value = null;
            }
        }
    },
});
