/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

// 🚗 Configuration unique pour types, labels, tarifs et catégories
const VEHICLE_CONFIG = [
    // code, label, tarif (CFA), catégorie
    [0, "Autre", 1000, "Autres"],
    [1, "Véhicule particulier", 1500, "Car"],
    [2, "Camion", 28000, "Camion"],
    [3, "Berline", 1500, "Car"],
    [4, "Minivan", 5000, "4x4"],
    [5, "Camion léger", 28000, "Camion"],
    [7, "Deux-roues", 1000, "Autres"],
    [8, "Tricycle", 1000, "Autres"],
    [9, "SUV / MPV", 5000, "4x4"],
    [10, "Bus moyen", 7000, "Bus"],
    [11, "Véhicule motorisé", 1000, "Autres"],
    [12, "Véhicule non motorisé", 1000, "Autres"],
    [13, "Petite berline", 1500, "Car"],
    [14, "Mini berline", 1500, "Car"],
    [15, "Pickup", 5000, "4x4"],
    [16, "Camion conteneur", 28000, "Camion"],
    [17, "Mini camion / Remorque plateau", 28000, "Camion"],
    [18, "Camion benne", 28000, "Camion"],
    [19, "Grue / Véhicule de chantier", 28000, "Camion"],
    [20, "Camion citerne", 28000, "Camion"],
    [21, "Bétonnière", 28000, "Camion"],
    [22, "Camion remorqueur", 28000, "Camion"],
    [23, "Hatchback", 1500, "Car"],
    [24, "Berline classique (Saloon)", 1500, "Car"],
    [25, "Berline sport", 1500, "Car"],
    [26, "Minibus", 7000, "Bus"],
];
const CODE_TO_LABEL = new Map(VEHICLE_CONFIG.map(([c, l]) => [c, l]));
const CODE_TO_TARIFF = new Map(VEHICLE_CONFIG.map(([c, , t]) => [c, t]));
const CODE_TO_CATEGORY = new Map(VEHICLE_CONFIG.map(([c, , , cat]) => [c, cat]));
const LABEL_TO_CODE = new Map(VEHICLE_CONFIG.map(([c, l]) => [l, c]));

export class PeageDashboard extends Component {
    static template = "anpr_peage_dashboard";

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            transactions: [],
            date: this.formatDateTime(new Date()),
            detected_plate: null,
            detected_type: null,
            detected_type_code: null,
            detected_category: null,
            showModal: false,
            showMobileModal: false,
            hikcentral_error: false,
            form: { plate: "", vehicle_type: "", amount: 0 },
            mobileForm: { plate: "", vehicle_type: "", numero: "", amount: 0 },
            inputTarget: "plate",
            loading: false,
            result_message: "",
            payment_status: ""
        });

        onWillStart(async () => {
            try {
                const result = await rpc("/anpr_peage/start_hikcentral");
                this.state.hikcentral_error = result.status !== "success";
                console.log(result.status === "success" ?
                    "✅ HikCentral Listener démarré" :
                    `❌ Erreur démarrage HikCentral: ${result.message}`);
            } catch (e) {
                console.error("❌ Impossible de démarrer HikCentral:", e);
                this.state.hikcentral_error = true;
            }
            try {
                this.state.transactions = await rpc("/anpr_peage/transactions") || [];
            } catch (e) {
                console.error("❌ Erreur chargement transactions:", e);
            }
        });

        onMounted(() => {
            this._clock = setInterval(() => this.state.date = this.formatDateTime(new Date()), 1000);
            this._flask = setInterval(this._fetchLastPlate.bind(this), 1000);
            rpc("/anpr_peage/scroll_message", { message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK", permanent: true });
        });

        onWillUnmount(() => {
            clearInterval(this._clock);
            clearInterval(this._flask);
        });
    }

    async _fetchLastPlate() {
        try {
            const resp = await fetch("https://127.0.0.1:8090/last_plate");
            if (!resp.ok) throw new Error(resp.statusText);
            const data = await resp.json();
            if (data.plate) {
                const code = data.vehicle_type;
                const label = this.vehicleTypeToString(code);
                const tariff = this.getAmountFromVehicleTypeCode(code);
                const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
                this.state.detected_plate = data.plate;
                this.state.detected_type_code = code;
                this.state.detected_type = label;
                this.state.detected_category = category;
                this.state.form.amount = tariff;
                this.state.mobileForm.amount = tariff;
                console.log(`📸 ${data.plate} (${label}, catégorie : ${category}) -> ${tariff} CFA`);
            }
        } catch (e) {
            console.error("❌ Fetch last_plate:", e);
        }
    }

    formatDateTime(date) {
        return date.toLocaleString("fr-FR", { weekday: "short", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    openManualModal() {
        const code = this.state.detected_type_code;
        const label = this.vehicleTypeToString(code);
        const amount = this.getAmountFromVehicleTypeCode(code);
        const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
        this.state.form = { plate: this.state.detected_plate || "", vehicle_type: `${label} (${category})`, amount };
        this.state.showModal = true;
    }

    onVehicleTypeChangeModal(ev) {
        const label = ev.target.value;
        const code = this.getVehicleTypeCodeFromLabel(label);
        const amount = this.getAmountFromVehicleTypeCode(code);
        const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
        this.state.form.vehicle_type = `${label} (${category})`;
        this.state.form.amount = amount;
        rpc("/anpr_peage/scroll_message", { message: `TOTAL: ${amount} CFA`, permanent: true });
    }

    openMobileMoneyModal() {
        const code = this.state.detected_type_code;
        const label = this.vehicleTypeToString(code);
        const amount = this.getAmountFromVehicleTypeCode(code);
        const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
        this.state.mobileForm = { plate: this.state.detected_plate || "", vehicle_type: `${label} (${category})`, numero: "", amount };
        this.state.showMobileModal = true;
    }

    onVehicleTypeChangeMobile(ev) {
        const label = ev.target.value;
        const code = this.getVehicleTypeCodeFromLabel(label);
        const amount = this.getAmountFromVehicleTypeCode(code);
        const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
        this.state.mobileForm.vehicle_type = `${label} (${category})`;
        this.state.mobileForm.amount = amount;
        rpc("/anpr_peage/scroll_message", { message: `TOTAL: ${amount} CFA`, permanent: true });
    }

    async confirmManualPayment() {
        const { plate, vehicle_type, amount } = this.state.form;
        if (!plate || !vehicle_type || !amount) return this.notification.add("Veuillez remplir tous les champs.", { type: "warning" });
        this._addTransaction(plate, amount);
        try {
            const res = await rpc("/anpr_peage/pay_manuely", { plate, vehicle_type, amount });
            if (res.payment_status === "success") {
                this.notification.add("✅ Paiement manuel enregistré.", { type: "success" });
                this.closeModal();
            } else this.notification.add(`Échec: ${res.message}`, { type: "danger" });
        } catch {
            this.notification.add("Erreur de communication.", { type: "danger" });
        }
    }

    async confirmMobileMoneyPayment() {
        const { plate, vehicle_type, numero, amount } = this.state.mobileForm;
        if (!plate || !vehicle_type || !numero || !amount) return this.notification.add("⚠️ Remplis tous les champs.", { type: "warning" });
        this._addTransaction(plate, amount);
        try {
            const res = await rpc("/anpr_peage/pay", { plate, vehicle_type, numero, amount });
            this.notification.add(res.payment_status === "success" ? "✅ Paiement réussi!" : `⚠️ ${res.message}`, { type: res.payment_status === "success" ? "success" : "warning" });
            if (res.payment_status === "success") this.closeMobileModal();
        } catch {
            this.notification.add("❌ Erreur réseau.", { type: "danger" });
        }
    }

    _addTransaction(plate, amount) {
        const now = new Date();
        this.state.transactions.unshift({ id: this.state.transactions.length + 1, operator: "Ogooué Technologies", plate, date: now.toLocaleDateString(), time: now.toLocaleTimeString(), amount });
    }

    closeModal() {
        this.state.showModal = false;
        rpc("/anpr_peage/scroll_message", { message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK", permanent: true });
    }

    closeMobileModal() {
        this.state.showMobileModal = false;
        rpc("/anpr_peage/scroll_message", { message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK", permanent: true });
    }

    getAmountLabel() {
        return this.getAmountFromVehicleTypeCode(this.state.detected_type_code);
    }

    vehicleTypeToString(code) {
        return CODE_TO_LABEL.get(code) ?? "Inconnu";
    }

    getAmountFromVehicleTypeCode(code) {
        return CODE_TO_TARIFF.get(code) ?? 1000;
    }

    getVehicleTypeCodeFromLabel(label) {
        return LABEL_TO_CODE.get(label) ?? 0;
    }

   
}

registry.category("actions").add("anpr_peage_dashboard", PeageDashboard);
