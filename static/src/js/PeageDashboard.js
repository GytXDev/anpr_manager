/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

const VEHICLE_CONFIG = [
    [0, "Autre", 1500, "Autres"],
    [1, "Véhicule particulier", 1500, "Car"],
    [2, "Camion", 28000, "Camion"],
    [3, "Berline", 1500, "Car"],
    [4, "Minivan", 5000, "4x4"],
    [5, "Camion léger", 28000, "Camion"],
    [7, "Deux-roues", 1500, "Car"],
    [8, "Tricycle", 1500, "Car"],
    [9, "SUV / MPV", 5000, "4x4"],
    [10, "Bus moyen", 7000, "Bus"],
    [11, "Véhicule motorisé", 1500, "Car"],
    [12, "Véhicule non motorisé", 1500, "Car"],
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
const CATEGORY_TO_TARIFF = new Map(
    VEHICLE_CONFIG.map(([, , t, cat]) => [cat, t])
);


export class PeageDashboard extends Component {
    static template = "anpr_peage_dashboard";

    setup() {
        this.notification = useService("notification");
        this.vehicleCategories = Array.from(new Set(VEHICLE_CONFIG.map(([, , , cat]) => cat)));
        this.state = useState({
            transactions: [],
            paginated: [],
            currentPage: 1,
            itemsPerPage: 7,
            closingAmount: 0,
            showCloseConfirm: false,
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
                    "HikCentral Listener démarré" :
                    `Erreur démarrage HikCentral: ${result.message}`);
            } catch (e) {
                console.error("Impossible de démarrer HikCentral:", e);
                this.state.hikcentral_error = true;
            }
            try {
                const result = await rpc("/anpr_peage/transactions_user");
                this.state.transactions = result || [];
                this.paginateTransactions();
            } catch (error) {
                console.error("Erreur lors du chargement des transactions :", error);
            }
            try {
                const userInfo = await rpc('/anpr_peage/get_current_user');
                this.state.user = userInfo;
            } catch (error) {
                console.error("Erreur lors de la récupération de l'utilisateur");
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
            console.error(" Fetch last_plate:", e);
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
        this.state.form = {
            plate: this.state.detected_plate || "",
            vehicle_type: category,
            amount
        };
        this.state.showModal = true;
    }

    closeModal() {
        this.state.showModal = false;
        this.resetForms();
        rpc("/anpr_peage/scroll_message", {
            message: "*VFD DISPLAY PD220 * HAVE  A NICE DAY AND THANK ",
            permanent: true
        });
    }

    selectVehicleType(cat) {
        this.state.form.vehicle_type = cat;
        this.state.form.amount = CATEGORY_TO_TARIFF.get(cat) ?? 1500;
        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${this.state.form.amount} CFA`,
            permanent: true,
        });
    }


    onKeyboardKeyClick(ev) {
        const key = ev.currentTarget.dataset.key;
        this.state.form.plate += key;
    }

    onKeyboardKeyClickMobile(ev) {
        const key = ev.currentTarget.dataset.key;
        if (this.state.inputTarget === 'plate') {
            this.state.mobileForm.plate += key;
        } else if (this.state.inputTarget === 'numero') {
            this.state.mobileForm.numero += key;
        }
    }

    clearMobileInput() {
        if (this.state.inputTarget === 'plate') {
            this.state.mobileForm.plate = '';
        } else if (this.state.inputTarget === 'numero') {
            this.state.mobileForm.numero = '';
        }
    }

    clearPlate() {
        this.state.form.plate = "";
    }

    openMobileMoneyModal() {
        const code = this.state.detected_type_code;
        const label = this.vehicleTypeToString(code);
        const amount = this.getAmountFromVehicleTypeCode(code);
        const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";
        this.state.mobileForm = {
            plate: this.state.detected_plate || "",
            vehicle_type: category,
            numero: "",
            amount
        };

        this.state.showMobileModal = true;
    }

    selectVehicleTypeMobile(cat) {
        this.state.mobileForm.vehicle_type = cat;
        this.state.mobileForm.amount = CATEGORY_TO_TARIFF.get(cat) ?? 1500;
        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${this.state.mobileForm.amount} CFA`,
            permanent: true,
        });
    }


    async confirmManualPayment() {
        const { plate, vehicle_type, amount } = this.state.form;
        if (!plate || !vehicle_type || !amount)
            return this.notification.add("Veuillez remplir tous les champs.", { type: "warning" });

        try {
            const res = await rpc("/anpr_peage/pay_manuely", {
                plate,
                vehicle_type,
                amount,
                user_id: this.state.user.id,
            });

            if (res.payment_status === "success") {
                this._addTransaction(plate, amount); // seulement si succès
                this.notification.add("Paiement manuel enregistré.", { type: "success" });
                this.closeModal();
            } else {
                this.notification.add(`Échec: ${res.message}`, { type: "danger" });
            }
        } catch {
            this.notification.add("Erreur de communication avec le serveur.", { type: "danger" });
        }
    }

    async confirmMobileMoneyPayment() {
        const { plate, vehicle_type, numero, amount } = this.state.mobileForm;
        if (!plate || !vehicle_type || !numero || !amount)
            return this.notification.add("Remplis tous les champs.", { type: "warning" });

        this.state.loading = true;

        try {
            const res = await rpc("/anpr_peage/pay", {
                plate,
                vehicle_type,
                numero,
                amount,
                user_id: this.state.user.id,
            });

            if (res.payment_status === "success") {
                this._addTransaction(plate, amount);
                this.notification.add("Paiement réussi!", { type: "success" });
                this.closeMobileModal();
            } else {
                this.notification.add(`⚠️ ${res.message}`, { type: "warning" });
            }
        } catch {
            this.notification.add("Erreur réseau.", { type: "danger" });
        } finally {
            this.state.loading = false; // Débloquer le bouton
        }
    }



    _addTransaction(plate, amount) {
        const now = new Date();
        const id = Date.now();  // Identifiant unique côté client

        const optionsDate = {
            timeZone: "Africa/Libreville",
            day: "2-digit",
            month: "2-digit",
            year: "numeric"
        };
        const optionsTime = {
            timeZone: "Africa/Libreville",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
        };

        const date = now.toLocaleDateString("fr-FR", optionsDate);
        const time = now.toLocaleTimeString("fr-FR", optionsTime);

        this.state.transactions.unshift({
            id,
            operator: this.state.user?.name || "Opérateur",
            plate,
            date,
            time,
            amount
        });

        this.paginateTransactions();
    }


    closeMobileModal() {
        this.state.showMobileModal = false;
        this.resetForms();
        rpc("/anpr_peage/scroll_message", { message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK", permanent: true });
    }

    handleError(error) {
        console.error("Owl Error caught:", error);
        this.notification.add("Une erreur est survenue", { type: "danger" });
    }


    getAmountLabel() {
        return this.getAmountFromVehicleTypeCode(this.state.detected_type_code);
    }

    vehicleTypeToString(code) {
        return CODE_TO_LABEL.get(code) ?? "Inconnu";
    }

    getAmountFromVehicleTypeCode(code) {
        return CODE_TO_TARIFF.get(code) ?? 1500;
    }

    getVehicleTypeCodeFromLabel(label) {
        return LABEL_TO_CODE.get(label) ?? 0;
    }

    closeCashDrawer() {
        this.state.showCloseConfirm = true;
    }

    confirmCloseCashDrawer() {
        this.props.switchScreen("cash");
        this.notification.add(`Caisse fermée ${this.state.closingAmount} CFA`, {
            type: "success",
        });
        this.state.showCloseConfirm = false;
    }

    cancelCloseCashDrawer() {
        this.state.showCloseConfirm = false;
    }

    resetForms() {
        this.state.form = { plate: "", vehicle_type: "", amount: 0 };
        this.state.mobileForm = { plate: "", vehicle_type: "", numero: "", amount: 0 };
    }

    paginateTransactions() {
        const start = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const end = start + this.state.itemsPerPage;
        this.state.paginated = this.state.transactions.slice(start, end);
    }

    changePage(delta) {
        const newPage = this.state.currentPage + delta;
        const totalPages = Math.ceil(this.state.transactions.length / this.state.itemsPerPage);
        if (newPage >= 1 && newPage <= totalPages) {
            this.state.currentPage = newPage;
            this.paginateTransactions();
        }
    }


}

registry.category("actions").add("anpr_peage_dashboard", PeageDashboard);