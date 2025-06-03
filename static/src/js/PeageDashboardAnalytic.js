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
        // 1) La période sélectionnée
        this.period = useState({ value: "daily" });

        // 2) Données du dashboard : on stocke deux tableaux mensuels
        this.state = useState({
            loading: true,
            stats: [],
            monthly_manual: [],  // tableau des montants "manual" par mois
            monthly_mobile: [],  // tableau des montants "mobile" par mois
            start: "",
            end: ""
        });
        this.formatCurrency = formatCurrency;
        this.globalStats = this._computeGlobalStats.bind(this);

        // 3) On stocke les instances Chart.js pour pouvoir les détruire
        this.barInstance = null;
        this.donutInstance = null;

        onMounted(() => {
            this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;

        // Appel RPC
        const result = await rpc("/anpr_peage/analytic_data", { period: this.period.value });
        console.log("★ Résultat RPC analytic_data :", result);

        if (result.status === "success") {
            this.state.stats = result.data || [];

            // On récupère les deux tableaux mensuels
            this.state.monthly_manual = result.monthly_manual || [];
            this.state.monthly_mobile = result.monthly_mobile || [];
            this.state.start = result.start;
            this.state.end = result.end;
        } else {
            console.error("Erreur retournée par le back-end :", result.message);
        }

        this.state.loading = false;

        // Dès que state a changé, on dessine les graphiques
        this._renderCharts();
    }

    showTransactions(userId, ev) {
        ev.preventDefault();
        window.location.href = `/anpr_peage/transactions/${userId}`;
    }

    _renderCharts() {
        // 1) Vérifier que Chart.js est bien chargé
        if (typeof window.Chart !== "function") {
            console.error("Chart.js n'est pas disponible !");
            return;
        }

        // 2) Si des instances existantes, on les détruit d’abord
        if (this.barInstance) {
            this.barInstance.destroy();
            this.barInstance = null;
        }
        if (this.donutInstance) {
            this.donutInstance.destroy();
            this.donutInstance = null;
        }

        const barCanvas = document.getElementById("peageBarChart");
        const donutCanvas = document.getElementById("peageDonutChart");

        /* -------------------------------
           A) BAR CHART : Manuel vs Mobile
        ------------------------------- */
        if (barCanvas) {
            const ctxBar = barCanvas.getContext("2d");

            console.log("→ Labels bar chart :",
                ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
            );
            console.log("→ Montants mensuels MANUEL :", this.state.monthly_manual);
            console.log("→ Montants mensuels MOBILE :", this.state.monthly_mobile);

            this.barInstance = new window.Chart(ctxBar, {
                type: "bar",
                data: {
                    labels: [
                        "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
                    ],
                    datasets: [
                        {
                            label: "Manuel",
                            data: this.state.monthly_manual,
                            backgroundColor: "#3B82F6",  // bleu
                            borderRadius: 6,
                            barThickness: 12      // barre plus fine
                        },
                        {
                            label: "Mobile",
                            data: this.state.monthly_mobile,
                            backgroundColor: "#10B981",  // vert
                            borderRadius: 6,
                            barThickness: 12
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: {
                        padding: { top: 10, right: 20, bottom: 10, left: 10 }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: "top",
                            labels: {
                                color: "#374151",
                                boxWidth: 12,
                                boxHeight: 12
                            }
                        },
                        tooltip: {
                            backgroundColor: "rgba(0,0,0,0.7)",
                            titleFont: { size: 14, weight: "500" },
                            bodyFont: { size: 12 },
                            padding: 8,
                            cornerRadius: 4,
                            callbacks: {
                                label: function (context) {
                                    const label = context.dataset.label; // "Manuel" ou "Mobile"
                                    const value = context.parsed.y;
                                    return `${label} : ${new Intl.NumberFormat("fr-FR").format(value)} CFA`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: "#E5E7EB",
                                lineWidth: 1,
                                drawBorder: false
                            },
                            ticks: {
                                callback: value => new Intl.NumberFormat("fr-FR").format(value) + " CFA",
                                color: "#6B7280",
                                maxTicksLimit: 6
                            }
                        },
                        x: {
                            grid: { display: false },
                            ticks: {
                                color: "#6B7280",
                                autoSkip: true,
                                maxTicksLimit: 12,
                                maxRotation: 0
                            },
                            // Pour grouper/rapprocher les barres de chaque mois :
                            categoryPercentage: 0.7,
                            barPercentage: 0.8
                        }
                    }
                }
            });
        } else {
            console.warn("⛔ Le <canvas id='peageBarChart'> n'existe pas dans le DOM.");
        }

        /* ---------------------------------
           B) DONUT CHART : Répartition par caissier
        ---------------------------------- */
        if (donutCanvas) {
            const ctxDonut = donutCanvas.getContext("2d");
            const caissiers = this.state.stats;

            console.log("→ Noms caissiers pour donut :", caissiers.map(u => u.name));
            console.log("→ Totaux caissiers pour donut :", caissiers.map(u => u.total));

            this.donutInstance = new window.Chart(ctxDonut, {
                type: "doughnut",
                data: {
                    labels: caissiers.map(u => u.name),
                    datasets: [{
                        data: caissiers.map(u => u.total),
                        backgroundColor: [
                            "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
                            "#6366F1", "#8B5CF6", "#EC4899", "#F472B6"
                        ],
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: {
                                color: "#374151",
                                usePointStyle: true,
                                boxWidth: 12
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    const i = context.dataIndex;
                                    const nom = caissiers[i].name;
                                    const val = caissiers[i].total;
                                    return `${nom} : ${val.toLocaleString()} CFA`;
                                }
                            },
                            padding: 6,
                            cornerRadius: 4
                        }
                    },
                    layout: {
                        padding: { top: 20, bottom: 10 }
                    },
                    cutout: "60%"
                }
            });
        } else {
            console.warn("⛔ Le <canvas id='peageDonutChart'> n'existe pas dans le DOM.");
        }
    }

    _computeGlobalStats() {
        let total_manual = 0, total_mobile = 0, total = 0, transactions = 0;
        for (const u of this.state.stats) {
            total_manual += u.manual_total || 0;
            total_mobile += u.mobile_total || 0;
            total += u.total || 0;
            transactions += u.transactions || 0;
        }
        return { total_manual, total_mobile, total, transactions };
    }
}

registry.category("actions").add("anpr_peage_dashboard_analytic", PeageDashboardAnalytic);