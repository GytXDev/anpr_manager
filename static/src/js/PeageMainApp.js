/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { CashDrawerScreen } from "./CashDrawerScreen";
import { PeageDashboard } from "./PeageDashboard";

export class PeageMainApp extends Component {
    static template = "anpr_peage_main";
    static components = { CashDrawerScreen, PeageDashboard };

    setup() {
        // si tu veux switcher plus tard
        this.state = useState({ screen: "cash" });
        this.switchScreen = (screen) => (this.state.screen = screen);
    }
}

// on enregistre sous la même clé que dans ton action ir.actions.client
registry.category("actions").add("anpr_peage_main", PeageMainApp);
