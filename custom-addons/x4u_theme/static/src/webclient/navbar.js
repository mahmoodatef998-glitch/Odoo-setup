import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    /** "Training" on the training database, empty on the real one. */
    get x4uEnvironmentLabel() {
        return session.x4u_environment_label || "";
    },
});
