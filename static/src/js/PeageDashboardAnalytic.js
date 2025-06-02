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
        // 1) Période sélectionnée
        this.period = useState({ value: "daily" });

        // 2) Données du dashboard
        this.state = useState({
            loading: true,
            stats: [],
            monthly: [],
            start: "",
            end: ""
        });
        this.formatCurrency = formatCurrency;
        this.globalStats = this._computeGlobalStats.bind(this);

        // 3) Références aux instances Chart.js pour pouvoir les détruire
        this.barInstance = null;
        this.donutInstance = null;

        onMounted(() => {
            this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;

        // --- 1) Appel RPC au back-end + log de la réponse ---
        const result = await rpc("/anpr_peage/analytic_data", { period: this.period.value });
        console.log("★ Résultat RPC analytic_data :", result);

        if (result.status === "success") {
            this.state.stats = result.data;
            this.state.monthly = result.monthly || [];
            this.state.start = result.start;
            this.state.end = result.end;
        } else {
            console.error("Erreur retournée par le back-end :", result.message);
        }

        this.state.loading = false;

        // 2) Dès qu’on a mis à jour `state`, on construit les graphiques :
        this._renderCharts();
    }

    _renderCharts() {
        // ** Vérifier que Chart.js est bien globalement chargé **
        if (typeof window.Chart !== "function") {
            console.error("Chart.js n'est pas disponible !");
            return;
        }

        // ** 2a) Remplacer barInstance et donutInstance existantes **
        if (this.barInstance) {
            this.barInstance.destroy();
            this.barInstance = null;
        }
        if (this.donutInstance) {
            this.donutInstance.destroy();
            this.donutInstance = null;
        }

        // ** 2b) Récupérer les deux <canvas> par leur id **
        const barCanvas = document.getElementById("peageBarChart");
        const donutCanvas = document.getElementById("peageDonutChart");

        // --- Bar Chart ---
        if (barCanvas) {
            const ctxBar = barCanvas.getContext("2d");

            // 3) Afficher en console ce qu’on va passer au bar chart
            console.log("→ Labels bar chart :", [
                "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
            ]);
            console.log("→ Valeurs bar chart :", this.state.monthly);

            this.barInstance = new window.Chart(ctxBar, {
                type: "bar",
                data: {
                    labels: [
                        "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
                    ],
                    datasets: [{
                        label: "Transactions mensuelles",
                        data: this.state.monthly,
                        backgroundColor: "#3B82F6",
                        borderRadius: 8,
                        barThickness: 24
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: value => new Intl.NumberFormat("fr-FR").format(value) + " CFA",
                                color: "#6B7280"
                            },
                            grid: { color: "#E5E7EB" }
                        },
                        x: {
                            ticks: { color: "#6B7280" },
                            grid: { display: false }
                        }
                    }
                }
            });
        } else {
            console.warn("⛔ Le <canvas id='peageBarChart'> n'a pas été trouvé dans le DOM.");
        }

        // --- Donut Chart ---
        if (donutCanvas) {
            const ctxDonut = donutCanvas.getContext("2d");
            const caissiers = this.state.stats;

            // 4) Afficher en console ce qu’on va passer au donut chart
            console.log("→ Noms caissiers pour donut :", caissiers.map(u => u.name));
            console.log("→ Totaux caissiers pour donut :", caissiers.map(u => u.total));

            this.donutInstance = new window.Chart(ctxDonut, {
                type: "doughnut",
                data: {
                    labels: caissiers.map(u => u.name),
                    datasets: [{
                        data: caissiers.map(u => u.total),
                        backgroundColor: [
                            '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
                            '#6366F1', '#8B5CF6', '#EC4899', '#F472B6',
                        ],
                        borderWidth: 2
                    }]
                },
                options: {
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: '#374151',
                                usePointStyle: true,
                                boxWidth: 12
                            }
                        }
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%'
                }
            });
        } else {
            console.warn("⛔ Le <canvas id='peageDonutChart'> n'a pas été trouvé dans le DOM.");
        }
    }

    _computeGlobalStats() {
        let total_manual = 0,
            total_mobile = 0,
            total = 0,
            transactions = 0;
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
