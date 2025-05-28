/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

function formatCurrency(amount) {
    return new Intl.NumberFormat("fr-FR", {
        style: "currency",
        currency: "XAF",
        minimumFractionDigits: 0,
    }).format(amount || 0);
}

export class PeageDashboardAnalytic extends Component {
    static template = "anpr_peage_dashboard_analytic";

    setup() {
        this.period = useState({ value: "daily" });
        this.state = useState({ loading: true, stats: [], monthly: [], start: "", end: "" });
        this.formatCurrency = formatCurrency;
        this.globalStats = this._computeGlobalStats.bind(this);
        this.chartRef = useState({ el: null });
        this.donutRef = useState({ el: null });

        onMounted(async () => {
            await this.loadData();
            this._renderCharts();
        });
    }

    async loadData() {
        this.state.loading = true;

        const result = await rpc("/anpr_peage/analytic_data", { period: this.period.value });

        if (result.status === "success") {
            this.state.stats = result.data;
            this.state.monthly = result.monthly || [];
            this.state.start = result.start;
            this.state.end = result.end;

            const totalGlobal = result.data.reduce((acc, user) => acc + user.total, 0);

            console.log("📊 Liste des caissiers avec leurs chiffres d'affaires :");
            result.data.forEach((user) => {
                const percent = totalGlobal > 0 ? ((user.total / totalGlobal) * 100).toFixed(2) : 0;
                console.log(`- ${user.name} → ${user.total.toLocaleString()} CFA (${percent}%)`);
            });

            console.log(`\n💰 Total Global : ${totalGlobal.toLocaleString()} CFA`);
        }

        this.state.loading = false;
    }

    _renderCharts() {
        if (this.chartRef.el) {
            const ctx = this.chartRef.el.getContext("2d");

            new Chart(ctx, {
                type: "bar",
                data: {
                    labels: [
                        "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
                    ],
                    datasets: [{
                        label: "Transactions mensuelles",
                        data: this.state.monthly,
                        backgroundColor: "#3B82F6"
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function (value) {
                                    return new Intl.NumberFormat("fr-FR").format(value) + " CFA";
                                }
                            }
                        }
                    }
                }
            });
        }

        if (this.donutRef.el) {
            const ctx = this.donutRef.el.getContext("2d");
            const caissiers = this.state.stats;

            new Chart(ctx, {
                type: "doughnut",
                data: {
                    labels: caissiers.map(u => u.name),
                    datasets: [{
                        data: caissiers.map(u => u.total),
                        backgroundColor: [
                            '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
                            '#6366F1', '#8B5CF6', '#EC4899', '#F472B6',
                        ],
                    }]
                },
                options: {
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: '#374151',
                                boxWidth: 14
                            }
                        }
                    },
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        }
    }

    _computeGlobalStats() {
        let total_manual = 0, total_mobile = 0, total = 0, transactions = 0;
        for (const user of this.state.stats) {
            total_manual += user.manual_total || 0;
            total_mobile += user.mobile_total || 0;
            total += user.total || 0;
            transactions += user.transactions || 0;
        }
        return { total_manual, total_mobile, total, transactions };
    }
}

registry.category("actions").add("anpr_peage_dashboard_analytic", PeageDashboardAnalytic);