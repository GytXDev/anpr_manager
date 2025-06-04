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
        // État principal : sélection de période
        this.period = useState({ value: "monthly", start: "", end: "" });
        // Flag : true dès qu’on a chargé au moins une fois la période "custom"
        this.customLoaded = useState({ value: false });

        this.state = useState({
            loading: true,
            stats: [],
            monthly_manual: [],
            monthly_mobile: [],
            start: "",
            end: ""
        });

        this.formatCurrency = formatCurrency;
        this.globalStats = this._computeGlobalStats.bind(this);

        this.barInstance = null;
        this.donutInstance = null;

        onMounted(() => {
            this.loadData();
        });
    }

    async loadData() {
        if (this.period.value !== "custom") {
            this.customLoaded.value = false;
        }
        this.state.loading = true;

        let result;
        if (this.period.value === "custom") {
            if (!this.period.start || !this.period.end) {
                console.warn("Les dates personnalisées sont manquantes.");
                this.state.loading = false;
                return;
            }
            result = await rpc("/anpr_peage/analytic_data_custom", {
                start: this.period.start,
                end: this.period.end
            });
        } else {
            result = await rpc("/anpr_peage/analytic_data", {
                period: this.period.value
            });
        }

        if (result.status === "success") {
            this.state.stats = result.data || [];
            this.state.monthly_manual = result.monthly_manual || [];
            this.state.monthly_mobile = result.monthly_mobile || [];
            this.state.start = result.start;
            this.state.end = result.end;
        } else {
            console.error("Erreur retournée par le back-end :", result.message);
        }

        this.state.loading = false;
        this._renderCharts();
    }

    // On rend cette méthode async, pour qu’elle attende la fin de loadData()
    async loadCustomRange() {
        await this.loadData();
        // Ce flag passe à true une fois que loadData() a terminé :
        this.customLoaded.value = true;
    }

    showTransactions(userId) {
        const period = this.period.value;
        const start = this.period.start;
        const end = this.period.end;
        let url = `/anpr_peage/transactions/${userId}?period=${period}`;
        if (period === "custom" && start && end) {
            url += `&start=${start}&end=${end}`;
        }
        window.location.href = url;
    }

    exportPDF(userId) {
        const period = this.period.value;
        const start = this.period.start;
        const end = this.period.end;
        let url = `/anpr_peage/download_report_pdf?user_id=${userId}&period=${period}`;
        if (period === "custom" && start && end) {
            url += `&start=${start}&end=${end}`;
        }
        window.open(url, "_blank");
    }

    exportExcel(userId) {
        const period = this.period.value;
        const start = this.period.start;
        const end = this.period.end;
        let url = `/anpr_peage/download_report_excel?user_id=${userId}&period=${period}`;
        if (period === "custom" && start && end) {
            url += `&start=${start}&end=${end}`;
        }
        window.open(url, "_blank");
    }

    _renderCharts() {
        if (typeof window.Chart !== "function") {
            console.error("Chart.js n’est pas disponible !");
            return;
        }
        if (this.barInstance) this.barInstance.destroy();
        if (this.donutInstance) this.donutInstance.destroy();

        const barCanvas = document.getElementById("peageBarChart");
        const donutCanvas = document.getElementById("peageDonutChart");

        if (barCanvas) {
            const ctxBar = barCanvas.getContext("2d");
            this.barInstance = new window.Chart(ctxBar, {
                type: "bar",
                data: {
                    labels: ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"],
                    datasets: [
                        {
                            label: "Manuel",
                            data: this.state.monthly_manual,
                            backgroundColor: "#3B82F6",
                            borderRadius: 6,
                            barThickness: 12
                        },
                        {
                            label: "Mobile",
                            data: this.state.monthly_mobile,
                            backgroundColor: "#10B981",
                            borderRadius: 6,
                            barThickness: 12
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { top: 10, right: 20, bottom: 10, left: 10 } },
                    plugins: {
                        legend: {
                            display: true,
                            position: "top",
                            labels: { color: "#374151", boxWidth: 12, boxHeight: 12 }
                        },
                        tooltip: {
                            backgroundColor: "rgba(0,0,0,0.7)",
                            titleFont: { size: 14, weight: "500" },
                            bodyFont: { size: 12 },
                            padding: 8,
                            cornerRadius: 4,
                            callbacks: {
                                label: (ctx) => {
                                    const label = ctx.dataset.label;
                                    const value = ctx.parsed.y;
                                    return `${label} : ${new Intl.NumberFormat("fr-FR").format(value)} CFA`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: "#E5E7EB", lineWidth: 1, drawBorder: false },
                            ticks: {
                                callback: (val) => new Intl.NumberFormat("fr-FR").format(val) + " CFA",
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
                            categoryPercentage: 0.7,
                            barPercentage: 0.8
                        }
                    }
                }
            });
        }

        if (donutCanvas) {
            const ctxDonut = donutCanvas.getContext("2d");
            const caissiers = this.state.stats;
            this.donutInstance = new window.Chart(ctxDonut, {
                type: "doughnut",
                data: {
                    labels: caissiers.map((u) => u.name),
                    datasets: [
                        {
                            data: caissiers.map((u) => u.total),
                            backgroundColor: [
                                "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
                                "#6366F1", "#8B5CF6", "#EC4899", "#F472B6"
                            ],
                            borderWidth: 2
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: { color: "#374151", usePointStyle: true, boxWidth: 12 }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    const i = ctx.dataIndex;
                                    const nom = caissiers[i].name;
                                    const val = caissiers[i].total;
                                    return `${nom} : ${val.toLocaleString()} CFA`;
                                }
                            },
                            padding: 6,
                            cornerRadius: 4
                        }
                    },
                    layout: { padding: { top: 20, bottom: 10 } },
                    cutout: "60%"
                }
            });
        }
    }

    _computeGlobalStats() {
        let total_manual = 0,
            total_mobile = 0,
            total = 0,
            transactions = 0;
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