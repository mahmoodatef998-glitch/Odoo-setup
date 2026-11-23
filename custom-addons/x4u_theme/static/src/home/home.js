import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";
import { fuzzyLookup } from "@web/core/utils/search";

/**
 * The 4U Home page: one card per app the user's role opens (the same apps as the
 * apps menu), and a search box to reach one fast.
 */
export class X4uHome extends Component {
    static template = "x4u_theme.Home";
    static props = ["*"];

    setup() {
        this.menu = useService("menu");
        this.state = useState({ query: "" });
        this.searchRef = useRef("search");
        this.userName = user.name;
        this.environmentLabel = session.x4u_environment_label || "";
        onMounted(() => this.searchRef.el?.focus());
    }

    get apps() {
        const apps = this.menu
            .getApps()
            .filter((app) => app.actionID && app.xmlid !== "x4u_theme.menu_x4u_home");
        const query = this.state.query.trim();
        return query ? fuzzyLookup(query, apps, (app) => app.name) : apps;
    }

    get greeting() {
        const hour = new Date().getHours();
        if (hour < 12) {
            return _t("Good morning");
        }
        return hour < 17 ? _t("Good afternoon") : _t("Good evening");
    }

    openApp(app) {
        this.menu.selectMenu(app);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter" && this.apps.length) {
            this.openApp(this.apps[0]);
        }
    }
}

registry.category("actions").add("x4u_home", X4uHome);
