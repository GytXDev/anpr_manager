/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class PeageDashboard extends Component {
    static template = "anpr_peage_dashboard";

    setup() {
        this.notification = useService("notification");

        this.tarifs = {
            voiture: 200,
            bus: 1000,
            taxi: 700,
            moto: 300,
            camion: 1500,
        };

        this.state = useState({
            transactions: [],
            date: this.formatDateTime(new Date()),
            detected_plate: null,
            detected_type: null,
            showModal: false,
            showMobileModal: false,
            hikcentral_error: false,
            form: {
                plate: "",
                vehicle_type: "",
                amount: 0,
            },
            mobileForm: {
                plate: "",
                vehicle_type: "",
                numero: "",
                amount: 0,
            }
        });

        this.intervalId = null;

        onWillStart(async () => {
            try {
                // ➡️ 1. Lancer automatiquement HikCentral au chargement de la page
                const result = await rpc("/anpr_peage/start_hikcentral");
                if (result.status === "success") {
                    console.log("✅ HikCentral Listener démarré avec succès !");
                    this.state.hikcentral_error = false; // Tout va bien
                } else {
                    console.error("❌ Erreur démarrage HikCentral :", result.message);
                    this.state.hikcentral_error = true; // Problème détecté
                }
            } catch (error) {
                console.error("❌ Impossible de démarrer HikCentral :", error);
                this.state.hikcentral_error = true; // Problème détecté
            }

            // ➡️ 2. Charger les transactions normales
            try {
                const result = await rpc("/anpr_peage/transactions");
                this.state.transactions = result || [];
            } catch (error) {
                console.error("❌ Erreur lors du chargement des transactions :", error);
            }
        });



        onMounted(() => {
            // ⏰ Mettre à jour l'horloge en temps réel
            this.intervalId = setInterval(() => {
                this.state.date = this.formatDateTime(new Date());
            }, 1000);

            // 🛜 Nouvelle boucle pour interroger Flask en live
            this.flaskInterval = setInterval(async () => {
                try {
                    const response = await fetch("https://127.0.0.1:8090/last_plate", { method: "GET" });
                    if (response.ok) {
                        const data = await response.json();
                        if (data.plate) {
                            this.state.detected_plate = data.plate;
                            this.state.detected_type = this.vehicleTypeToString(data.vehicle_type);
                            console.log(`📸 Nouvelle détection : ${data.plate} (${this.state.detected_type})`);
                        }
                    }
                    else {
                        console.error("❌ Erreur récupération /last_plate :", response.statusText);
                    }
                } catch (error) {
                    console.error("❌ Impossible de contacter le serveur Flask :", error);
                }
            }, 1000); // toutes les 1 seconde

            rpc("/anpr_peage/scroll_message", {
                message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
                permanent: true
            });
        });


        onWillUnmount(() => {
            clearInterval(this.intervalId);
            clearInterval(this.flaskInterval);
        });

    }

    formatDateTime(date) {
        return date.toLocaleString("fr-FR", {
            weekday: "short",
            year: "numeric",
            month: "long",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    openManualModal() {
        this.state.form = {
            plate: this.state.detected_plate || "",
            vehicle_type: this.state.detected_type || "",
            amount: this.tarifs[this.state.detected_type] || 0,
        };
        this.state.showModal = true;
    }

    closeModal() {
        this.state.showModal = false;
        rpc("/anpr_peage/scroll_message", {
            message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
            permanent: true
        });
    }

    onVehicleTypeChangeModal(ev) {
        const type = ev.target.value;
        this.state.form.vehicle_type = type;
        this.state.form.amount = this.tarifs[type] || 0;

        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${this.state.form.amount} CFA`,
            permanent: true
        });
    }

    onKeyboardKeyClick(ev) {
        const key = ev.currentTarget.dataset.key;
        this.state.form.plate += key;
    }

    clearPlate() {
        this.state.form.plate = "";
    }

    async confirmManualPayment() {
        const { plate, vehicle_type, amount } = this.state.form;
        if (!plate || !vehicle_type || !amount) {
            this.notification.add("Veuillez remplir tous les champs.", { type: "warning" });
            return;
        }

        const now = new Date();
        this.state.transactions.unshift({
            id: this.state.transactions.length + 1,
            operator: "Ogooué Technologies",
            plate,
            date: now.toLocaleDateString(),
            time: now.toLocaleTimeString(),
            amount,
        });

        try {
            const result = await rpc("/anpr_peage/pay_manuely", { plate, vehicle_type, amount });

            if (result.payment_status === "success") {
                this.notification.add("✅ Paiement manuel enregistré avec succès.", { type: "success" });
                this.closeModal();
                await rpc("/anpr_peage/scroll_message", { message: "MERCI ET BONNE JOURNEE" });
                setTimeout(() => {
                    rpc("/anpr_peage/scroll_message", {
                        message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
                        permanent: true
                    });
                }, 5000);
            } else {
                this.notification.add("Échec du paiement : " + result.message, { type: "danger" });
            }
        } catch (error) {
            console.error("❌ Erreur API :", error);
            this.notification.add("Erreur de communication avec le serveur.", { type: "danger" });
        }
    }

    openMobileMoneyModal() {
        const type = this.state.detected_type;
        this.state.mobileForm = {
            plate: this.state.detected_plate || "",
            vehicle_type: type || "",
            numero: "",
            amount: this.tarifs[type] || 0,
        };
        this.state.showMobileModal = true;
    }

    closeMobileModal() {
        this.state.showMobileModal = false;
        rpc("/anpr_peage/scroll_message", {
            message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
            permanent: true
        });
    }

    onMobileKeyClick(ev) {
        const key = ev.currentTarget.dataset.key;
        this.state.mobileForm.numero += key;
    }

    onKeyboardKeyClickMobile(ev) {
        const key = ev.currentTarget.dataset.key;
        const target = this.state.inputTarget;
        if (target === "plate") this.state.mobileForm.plate += key;
        else if (target === "numero") this.state.mobileForm.numero += key;
    }

    clearMobileInput() {
        const target = this.state.inputTarget;
        if (target === "plate") this.state.mobileForm.plate = "";
        else if (target === "numero") this.state.mobileForm.numero = "";
    }

    onKeyboardKeyClickForMobilePlate(ev) {
        const key = ev.currentTarget.dataset.key;
        this.state.mobileForm.plate += key;
    }

    clearMobilePlate() {
        this.state.mobileForm.plate = "";
    }

    onVehicleTypeChangeMobile(ev) {
        const type = ev.target.value;
        this.state.mobileForm.vehicle_type = type;
        this.state.mobileForm.amount = this.tarifs[type] || 0;

        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${this.state.mobileForm.amount} CFA`,
            permanent: true
        });
    }

    async confirmMobileMoneyPayment() {
        const { plate, vehicle_type, numero, amount } = this.state.mobileForm;

        if (!plate || !vehicle_type || !numero || !amount) {
            this.notification.add("⚠️ Veuillez remplir tous les champs.", { type: "warning" });
            return;
        }

        this.state.loading = true;

        const now = new Date();
        this.state.transactions.unshift({
            id: this.state.transactions.length + 1,
            operator: "Ogooué Technologies",
            plate,
            date: now.toLocaleDateString(),
            time: now.toLocaleTimeString(),
            amount,
        });

        try {
            const result = await rpc("/anpr_peage/pay", { plate, vehicle_type, numero, amount });
            this.state.result_message = result.message;
            this.state.payment_status = result.payment_status || "unknown";

            if (this.state.payment_status === "success") {
                this.notification.add("✅ Paiement Mobile Money réussi !", { type: "success" });
                this.closeMobileModal();
                await rpc("/anpr_peage/scroll_message", { message: "MERCI ET BONNE JOURNEE" });
                setTimeout(() => {
                    rpc("/anpr_peage/scroll_message", {
                        message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
                        permanent: true
                    });
                }, 5000);
            } else if (this.state.payment_status === "cancelled") {
                this.notification.add("❌ Paiement annulé.", { type: "danger" });
            } else {
                this.notification.add("⚠️ Échec du paiement : " + this.state.result_message, { type: "warning" });
            }

        } catch (error) {
            console.error("Erreur de paiement :", error);
            this.state.result_message = "Erreur de communication avec le serveur.";
            this.state.payment_status = "failed";
            this.notification.add("❌ Erreur réseau : Veuillez vérifier votre connexion.", { type: "danger" });
        }

        this.state.loading = false;
    }

    getAmountLabel() {
        return this.tarifs[this.state.detected_type] || 500;
    }

    vehicleTypeToString(type) {
        switch (type) {
            case 0:
                return "Autre";
            case 1:
                return "Véhicule particulier";
            case 2:
                return "Camion";
            case 3:
                return "Berline";
            case 4:
                return "Minivan";
            case 5:
                return "Camion léger";
            case 6:
                return "Piéton";
            case 7:
                return "Deux-roues";
            case 8:
                return "Tricycle";
            case 9:
                return "SUV / MPV";
            case 10:
                return "Bus moyen";
            case 11:
                return "Véhicule motorisé";
            case 12:
                return "Véhicule non motorisé";
            case 13:
                return "Petite berline";
            case 14:
                return "Mini berline";
            case 15:
                return "Pickup";
            case 16:
                return "Camion conteneur";
            case 17:
                return "Mini camion / Remorque plateau";
            case 18:
                return "Camion benne";
            case 19:
                return "Grue / Véhicule de chantier";
            case 20:
                return "Camion citerne";
            case 21:
                return "Bétonnière";
            case 22:
                return "Camion remorqueur";
            case 23:
                return "Hatchback";
            case 24:
                return "Berline classique (Saloon)";
            case 25:
                return "Berline sport";
            case 26:
                return "Minibus";
            default:
                return "Inconnu";
        }
    }


    onExportExcel() {
        this.notification.add("📤 Export Excel déclenché !", { type: "info" });
    }
}

registry.category("actions").add("anpr_peage_dashboard", PeageDashboard);