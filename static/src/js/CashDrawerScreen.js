/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class CashDrawerScreen extends Component {
    static template = "anpr_peage_cash_drawer_screen";
    static props = ["switchScreen"];

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");

        this.state = useState({
            currentTime: new Date(),
            openingAmount: 0,
            userName: "",
            userAvatar: "",
            userTotals: { manual: 0, mobile: 0, overall: 0 },
            globalTotals: { manual: 0, mobile: 0, overall: 0 },
        });

        onMounted(async () => {
            /* infos utilisateur */
            try {
                const user = await rpc("/anpr_peage/get_current_user");
                this.state.userName = user.name;
                this.state.userAvatar = user.avatar_url;
            } catch (e) {
                console.error("Impossible de charger l’utilisateur :", e);
            }

            /* horloge temps réel */
            this._timer = setInterval(() => {
                this.state.currentTime = new Date();
            }, 1000);

            /* totaux */
            await this.fetchTodayTotals();
        });

        onWillUnmount(() => {
            clearInterval(this._timer);
        });
    }

    formatDateTime(date) {
        return date.toLocaleString("fr-FR", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    async fetchTodayTotals() {
        /* résumé caissier */
        const userSum = await rpc("/anpr_peage/summary_user");
        /* résumé global  */
        const globalSum = await rpc("/anpr_peage/summary_global");

        this.state.userTotals = userSum;
        this.state.globalTotals = globalSum;
        /* pour compatibilité avec l’ancien “openingAmount” */
        this.state.openingAmount = userSum.overall;
    }

    onOpenCash() {
        // on passe à l'écran "dashboard"
        this.props.switchScreen("dashboard");
        this.notification.add(`Caisse ouverte avec ${this.state.openingAmount} CFA`, {
            type: "success",
        });
    }
}

registry.category("actions").add("anpr_peage_cash_drawer_screen", CashDrawerScreen);
