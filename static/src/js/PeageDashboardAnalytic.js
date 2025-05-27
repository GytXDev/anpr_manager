/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/utils/hooks";

export class PeageDashboardAnalytic extends Component {
    static template = "anpr_peage_dashboard_analytic";

}
registry.category("actions").add("anpr_peage_dashboard_analytic", PeageDashboardAnalytic);