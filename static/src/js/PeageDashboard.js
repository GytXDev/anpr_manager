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
                // Charger l'utilisateur
                const userInfo = await rpc('/anpr_peage/get_current_user');
                this.state.user = userInfo;

                // Vérifier la configuration Artemis
                const diag = await rpc("/anpr_peage/hikcentral_status");
                console.log("Diagnostic Artemis :", diag);

                if (diag.status !== 'ok') {
                    this.notification.add(`Paramètres manquants : ${diag.message}`, {
                        type: "warning",
                        sticky: true,
                    });
                } else {
                    this.state.allowed_cameras = diag.config.src_codes?.split(',') ?? [];
                    console.log("Caméras autorisées pour cet utilisateur :", this.state.allowed_cameras);
                }

                // Récupération de l'URL Flask
                const flaskData = await rpc("/anpr_peage/flask_status");
                if (flaskData.flask_url) {
                    this.state.flask_url = flaskData.flask_url;
                } else {
                    this.notification.add("flask_url manquant ou non configuré.", {
                        type: "warning",
                        sticky: true
                    });
                }

                // Démarrage du service HikCentral
                const result = await rpc("/anpr_peage/start_hikcentral");
                this.state.hikcentral_error = result.status !== "success";

                if (this.state.hikcentral_error) {
                    this.notification.add(
                        `Bonjour ${this.state.user?.name || "utilisateur"} — le service HikCentral n'est pas actif. Vérifiez la connexion Artemis.`,
                        { type: "warning", sticky: true }
                    );
                } else {
                    console.log("HikCentral Listener démarré");
                }

            } catch (e) {
                this.state.hikcentral_error = true;
                this.notification.add(
                    "Erreur lors de la tentative de démarrage de HikCentral.",
                    { type: "danger", sticky: true }
                );
                console.error("Erreur HikCentral/User:", e);
            }

            try {
                const result = await rpc("/anpr_peage/transactions_user");

                const paymentLabels = {
                    manual: "Manuel",
                    mobile: "Mobile Money"
                };

                this.state.transactions = (result || []).map(tx => ({
                    ...tx,
                    payment_method: paymentLabels[tx.payment_method] || "Inconnu"
                }));

                this.paginateTransactions();
            } catch (error) {
                console.error("Erreur lors du chargement des transactions :", error);
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
            const baseUrl = this.state.flask_url;
            const url = baseUrl;

            const resp = await fetch(url);
            const text = await resp.text();
            const data = JSON.parse(text);

            const srcIndex = data.src_index;

            // Vérification de la caméra autorisée
            const allowedSources = this.state.allowed_cameras ?? [];
            if (!allowedSources.includes(srcIndex)) {
                console.log(`Plaque ignorée (caméra non autorisée) : ${data.plate} - source : ${srcIndex}`);
                return;
            }

            if (data.plate) {
                this.lastFetchedPlate = data.plate;

                const code = parseInt(data.vehicle_type);
                const label = this.vehicleTypeToString(code);
                const tariff = this.getAmountFromVehicleTypeCode(code);
                const category = CODE_TO_CATEGORY.get(code) ?? "Inconnu";

                this.state.detected_plate = data.plate;
                this.state.detected_type_code = code;
                this.state.detected_type = label;
                this.state.detected_category = category;
                this.state.form.amount = tariff;
                this.state.mobileForm.amount = tariff;

                console.log(`${data.plate} (${label}, catégorie : ${category}) -> ${tariff} CFA, srcIndex : ${srcIndex ?? "non disponible"}`);

                // ✅ Envoyer le montant au VFD
                await rpc("/anpr_peage/scroll_message", {
                    message: `TOTAL: ${tariff} CFA`,
                    permanent: true
                });
            }

        } catch (e) {
            // Silencieux en production
            // console.error("Erreur fetch last_plate:", e);
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

    _resetDetectedPlate() {
        this.state.detected_plate = null;
        this.state.detected_type = null;
        this.state.detected_type_code = null;
        this.state.detected_category = null;
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

        // Vérification des champs requis
        if (!plate || !vehicle_type || !amount) {
            return this.notification.add("Veuillez remplir tous les champs.", { type: "warning" });
        }

        // Vérification de l'URL Flask
        if (!this.state.flask_url) {
            this.notification.add("❌ L'URL Flask n'est pas disponible.", { type: "warning" });
            return;
        }

        try {
            // Envoi de la requête de paiement
            const res = await rpc("/anpr_peage/pay_manuely", {
                plate,
                vehicle_type,
                amount,
                user_id: this.state.user.id,
            });

            if (res.payment_status === "success") {
                this._addTransaction(plate, amount, "manual");
                this.notification.add("Paiement manuel enregistré.", { type: "success" });

                // Récupération de la dernière plaque
                const lastPlateResponse = await fetch(this.state.flask_url, {
                    method: 'GET',
                });

                if (!lastPlateResponse.ok) {
                    throw new Error("Erreur lors de la récupération des données de la plaque.");
                }

                const lastPlateData = await lastPlateResponse.json();

                // Suppression de la plaque si elle existe
                if (lastPlateData.plate) {
                    const deleteResponse = await fetch(this.state.flask_url, {
                        method: 'DELETE',
                    });

                    if (!deleteResponse.ok) {
                        throw new Error("Erreur lors de la suppression de la plaque.");
                    }
                }

                this.closeModal();
                this._resetDetectedPlate();
            } else {
                this.notification.add(`Échec: ${res.message}`, { type: "danger" });
            }
        } catch (error) {
            console.error("Erreur lors de la requête :", error);
            this.notification.add("Erreur de communication avec le serveur. Le paiement peut avoir été enregistré.", { type: "danger" });
            this.closeModal();
        }
    }

    async confirmMobileMoneyPayment() {
        const { plate, vehicle_type, numero, amount } = this.state.mobileForm;
        if (!plate || !vehicle_type || !numero || !amount) {
            return this.notification.add("Remplis tous les champs.", { type: "warning" });
        }

        this.state.loading = true;

        const flask_url = this.state.flask_url;

        try {
            // Envoi du paiement à l'API
            const res = await rpc("/anpr_peage/pay", {
                plate,
                vehicle_type,
                numero,
                amount,
                user_id: this.state.user.id,
            });

            if (res.payment_status === "success") {
                this._addTransaction(plate, amount, "mobile");
                this.notification.add("Paiement réussi!", { type: "success" });

                // Appel de la route DELETE pour réinitialiser la plaque après paiement
                await fetch(flask_url, {
                    method: 'DELETE',
                });

                this.closeMobileModal();
                this._resetDetectedPlate();
            } else {
                this.notification.add(`⚠️ ${res.message}`, { type: "warning" });
            }
        } catch (error) {
            console.error("Erreur lors du traitement du paiement mobile :", error);
            this.notification.add("Erreur de communication avec le serveur.", { type: "danger" });
        } finally {
            this.state.loading = false; // Débloquer le bouton
        }
    }


    _addTransaction(plate, amount, payment_method) {
        const now = new Date();
        const id = Date.now();

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

        // Traduire la méthode de paiement en label
        const paymentLabels = {
            manual: "Manuel",
            mobile: "Mobile Money"
        };
        const paymentLabel = paymentLabels[payment_method] || "Inconnu";

        this.state.transactions.unshift({
            id,
            operator: this.state.user?.name || "Opérateur",
            plate,
            date,
            time,
            amount,
            payment_method: paymentLabel,  // On injecte le label au lieu de la valeur brute
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

    async fetchTodayTotals() {
        /* résumé caissier */
        const userSum = await rpc("/anpr_peage/summary_user");

        /* pour compatibilité avec l’ancien “openingAmount” */
        this.state.closingAmount = userSum.manual_total;
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