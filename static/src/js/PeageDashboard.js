/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

// Traduction du code numérique renvoyé par le backend en chaîne de catégorie
const CODE_TO_CATEGORY_TEXT = {
    0: "Autres",
    1: "Car",
    2: "Camion",
    3: "Car",
    4: "4x4",
    5: "Camion",
    7: "Car",
    8: "Car",
    9: "4x4",
    10: "Bus",
    11: "Car",
    12: "Car",
    13: "Car",
    14: "Car",
    15: "4x4",
    16: "Camion",
    17: "Camion",
    18: "Camion",
    19: "Camion",
    20: "Camion",
    21: "Camion",
    22: "Camion",
    23: "Car",
    24: "Car",
    25: "Car",
    26: "Bus",
};

const CODE_TO_TYPE_TEXT = {
    0: "Autre",
    1: "Véhicule particulier",
    2: "Camion",
    3: "Berline",
    4: "Minivan",
    5: "Camion léger",
    7: "Deux-roues",
    8: "Tricycle",
    9: "SUV / MPV",
    10: "Bus moyen",
    11: "Véhicule motorisé",
    12: "Véhicule non motorisé",
    13: "Petite berline",
    14: "Mini berline",
    15: "Pickup",
    16: "Camion conteneur",
    17: "Mini camion / Remorque plateau",
    18: "Camion benne",
    19: "Grue / Véhicule de chantier",
    20: "Camion citerne",
    21: "Bétonnière",
    22: "Camion remorqueur",
    23: "Hatchback",
    24: "Berline classique (Saloon)",
    25: "Berline sport",
    26: "Minibus",
};

export class PeageDashboard extends Component {
    static template = "anpr_peage_dashboard";

    setup() {
        this.notification = useService("notification");

        // vehicleCategories doit exister dès le premier render (même vide)
        this.vehicleCategories = [];

        this.state = useState({
            transactions: [],
            paginated: [],
            currentPage: 1,
            itemsPerPage: 7,
            closingAmount: 0,
            showCloseConfirm: false,
            date: this.formatDateTime(new Date()),
            detected_plate: null,
            detected_type_code: null,
            detected_type: null,
            detected_category: null,
            showModal: false,
            showMobileModal: false,
            hikcentral_error: false,
            form: { plate: "", vehicle_type: "", amount: 0 },
            mobileForm: { plate: "", vehicle_type: "", numero: "", amount: 0 },
            inputTarget: "plate",
            loading: false,
            result_message: "",
            payment_status: "",
            userConfig: null,
            allowed_cameras: [],
            flask_url: null,
        });

        // Table “catégorie → tarif HT” (sera rempli après récupération de userConfig)
        this.tarifsHT = {};

        // flag pour contrôler la boucle de fetch + délai
        this._continueFetching = true;
        this._flaskTimerId = null;

        onWillStart(async () => {
            // 1) Charger la configuration actuelle de l’utilisateur
            const userInfo = await rpc('/anpr_peage/get_current_user');
            this.state.userConfig = userInfo;

            // 2) Construire la table “catégorie → tarif HT”
            this.tarifsHT = {
                "Autres": userInfo.price_autre || 1500,
                "Car": userInfo.price_car || 1500,
                "Camion": userInfo.price_camion || 28000,
                "4x4": userInfo.price_4x4 || 5000,
                "Bus": userInfo.price_bus || 7000,
            };
            this.vehicleCategories = Object.keys(this.tarifsHT);

            // 3) Récupérer la liste des caméras autorisées
            this.state.allowed_cameras = Array.isArray(userInfo.artemis_event_src_codes)
                ? userInfo.artemis_event_src_codes.map(c => parseInt(c, 10)).filter(c => !isNaN(c))
                : (typeof userInfo.artemis_event_src_codes === "string"
                    ? userInfo.artemis_event_src_codes.split(',').map(c => parseInt(c.trim(), 10)).filter(c => !isNaN(c))
                    : []);
            console.log("→ DEBUG onWillStart: allowed_cameras =", this.state.allowed_cameras);

            // 4) Récupérer l’URL Flask pour la détection de plaque
            const flaskData = await rpc("/anpr_peage/flask_status");
            if (flaskData.flask_url) {
                this.state.flask_url = flaskData.flask_url;
            } else {
                this.notification.add("flask_url manquant ou non configuré.", {
                    type: "warning", sticky: true
                });
            }
            console.log("→ DEBUG onWillStart: flask_url =", this.state.flask_url);

            // 5) Charger l’historique des transactions de l’utilisateur
            try {
                const resultTx = await rpc("/anpr_peage/transactions_user");
                const paymentLabels = { manual: "Manuel", mobile: "Mobile Money", subscription: "Abonnement" };
                this.state.transactions = (resultTx || []).map(tx => ({
                    ...tx,
                    payment_method: paymentLabels[tx.payment_method] || "Inconnu"
                }));
                this.paginateTransactions();
            } catch (err) {
                console.error("Erreur chargement transactions :", err);
            }
        });

        onMounted(() => {
            // 1) Horloge à la seconde
            this._clock = setInterval(() => {
                this.state.date = this.formatDateTime(new Date());
            }, 1000);

            // 2) Lancer la première détection après un délai initial de 1 s
            this._flaskTimerId = setTimeout(this._fetchAndReschedule.bind(this), 1000);

            // 3) Message VFD par défaut
            rpc("/anpr_peage/scroll_message", {
                message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK",
                permanent: true
            });
        });

        onWillUnmount(() => {
            clearInterval(this._clock);
            // Annuler la prochaine exécution prévue (setTimeout)
            clearTimeout(this._flaskTimerId);
            this._continueFetching = false;
        });
    }

    /**
     * Calcule le montant TTC (HT + TVA) pour une catégorie textuelle.
     */
    getTTC(catText) {
        const baseHT = (this.tarifsHT[catText] != null)
            ? this.tarifsHT[catText]
            : 1500;
        const tauxTVA = (this.state.userConfig && this.state.userConfig.tva_rate) || 0;
        return Math.round(baseHT * (1 + tauxTVA / 100));
    }

    /**
     * Lance un cycle de détection + pause de 6 s avant l’appel suivant.
     */
    async _fetchAndReschedule() {
        if (!this._continueFetching) {
            return;
        }
        await this._fetchLastPlate();
        // Après avoir terminé _fetchLastPlate, attendre 6000 ms, puis si toujours actif, relancer
        this._flaskTimerId = setTimeout(this._fetchAndReschedule.bind(this), 6000);
    }

    /**
     * Interroge Flask pour la dernière plaque détectée, calcule le TTC,
     * affiche sur le VFD, et renseigne les formulaires.
     */
    async _fetchLastPlate() {
        try {
            const resp = await fetch(this.state.flask_url);
            const data = await resp.json();
            const srcIndex = data.src_index;
            const allowed = this.state.allowed_cameras;

            // Si la caméra n'est pas autorisée, on sort immédiatement
            if (!allowed.includes(srcIndex)) {
                console.log(`Plaque ignorée (caméra non autorisée) : ${data.plate} (src=${srcIndex})`);
                return;
            }

            // Si Flask renvoie une plaque valide
            if (data.plate) {
                // Vérifier d'abord si c'est un abonné
                const isSubscribed = await rpc("/anpr_peage/check_subscription", {
                    plate: data.plate
                });

                if (isSubscribed.exists) {
                    await rpc("/anpr_peage/scroll_message", {
                        message: "ABONNE - PASSAGE AUTORISE",
                        permanent: true
                    });

                    this._addTransaction(data.plate, isSubscribed.amount || 0, "subscription");

                    // Réafficher message par défaut après 4 secondes
                    setTimeout(() => {
                        rpc("/anpr_peage/scroll_message", {
                            message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK",
                            permanent: true
                        });
                    }, 4000);
                }
                else {
                    // Cas non abonné ou solde insuffisant => paiement normal
                    const code = parseInt(data.vehicle_type, 10);
                    const category = CODE_TO_CATEGORY_TEXT[code] || "Autres";
                    const humanLabel = CODE_TO_TYPE_TEXT[code] || "Autre";
                    const tarifTTC = this.getTTC(category);

                    this.state.detected_plate = data.plate;
                    this.state.detected_type_code = code;
                    this.state.detected_type = humanLabel;
                    this.state.detected_category = category;

                    this.state.form = {
                        plate: data.plate,
                        vehicle_type: category,
                        amount: tarifTTC
                    };
                    this.state.mobileForm = {
                        plate: data.plate,
                        vehicle_type: category,
                        numero: "",
                        amount: tarifTTC
                    };

                    await rpc("/anpr_peage/scroll_message", {
                        message: `TOTAL: ${tarifTTC} CFA`,
                        permanent: true
                    });
                }
            }
        } catch (e) {
            console.warn("Erreur _fetchLastPlate", e);
        }
    }

    formatDateTime(date) {
        return date.toLocaleString("fr-FR", {
            weekday: "short", year: "numeric", month: "long", day: "numeric",
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
    }

    // Ouvre la modale “Paiement Manuel” – on affiche directement le TTC
    openManualModal() {
        const code = this.state.detected_type_code;
        const category = CODE_TO_CATEGORY_TEXT[code] || null;
        let montantTTC = 0;
        if (category) {
            montantTTC = this.getTTC(category);
        }
        this.state.form = {
            plate: this.state.detected_plate || "",
            vehicle_type: category || "",
            amount: montantTTC
        };
        this.state.showModal = true;
    }

    // Ferme la modale “Paiement Manuel”
    closeModal() {
        this.state.showModal = false;
        this.resetForms();
        rpc("/anpr_peage/scroll_message", {
            message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK",
            permanent: true
        });
    }

    // Ferme la modale "Paiement Mobile Money"
    closeMobileModal() {
        this.state.showMobileModal = false;
        this.resetForms();
        rpc("/anpr_peage/scroll_message", {
            message: "*VFD DISPLAY PD220 * HAVE A NICE DAY AND THANK",
            permanent: true
        });
    }

    // Quand l’opérateur clique sur une vignette catégorie dans la modale manuelle
    selectVehicleType(cat) {
        this.state.form.vehicle_type = cat;
        const montantTTC = this.getTTC(cat);
        this.state.form.amount = montantTTC;
        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${montantTTC} CFA`,
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

    // Ouvre la modale “Paiement Mobile Money” avec TTC
    openMobileMoneyModal() {
        const code = this.state.detected_type_code;
        const category = CODE_TO_CATEGORY_TEXT[code] || null;
        let montantTTC = 0;
        if (category) {
            montantTTC = this.getTTC(category);
        }
        this.state.mobileForm = {
            plate: this.state.detected_plate || "",
            vehicle_type: category || "",
            numero: "",
            amount: montantTTC
        };
        this.state.showMobileModal = true;
    }

    _resetDetectedPlate() {
        this.state.detected_plate = null;
        this.state.detected_type_code = null;
        this.state.detected_category = null;
        this.state.detected_type = null;
    }

    selectVehicleTypeMobile(cat) {
        this.state.mobileForm.vehicle_type = cat;
        const montantTTC = this.getTTC(cat);
        this.state.mobileForm.amount = montantTTC;
        rpc("/anpr_peage/scroll_message", {
            message: `TOTAL: ${montantTTC} CFA`,
            permanent: true,
        });
    }

    async confirmManualPayment() {
        const { plate, vehicle_type } = this.state.form;
        const montantTTC = this.getTTC(vehicle_type || "");
        if (!plate || !vehicle_type || montantTTC <= 0) {
            return this.notification.add("Veuillez remplir la plaque et sélectionner un type de véhicule.", {
                type: "warning"
            });
        }
        if (!this.state.flask_url) {
            this.notification.add("❌ L'URL Flask n'est pas disponible.", { type: "warning" });
            return;
        }
        try {
            const res = await rpc("/anpr_peage/pay_manuely", {
                plate,
                vehicle_type,
                amount: montantTTC,
                user_id: this.state.userConfig.id,
            });
            if (res.payment_status === "success") {
                // Effacer l’aperçu précédent pour laisser le temps de correction
                this._resetDetectedPlate();

                this._addTransaction(plate, montantTTC, "manual");
                this.notification.add("Paiement manuel enregistré.", { type: "success" });
                await fetch(this.state.flask_url, { method: 'DELETE' });
                this.closeModal();
            } else {
                this.notification.add(`Échec : ${res.message}`, { type: "danger" });
            }
        } catch (error) {
            console.error("Erreur requête :", error);
            this.notification.add(
                "Erreur de communication ; le paiement peut avoir été enregistré.",
                { type: "danger" }
            );
            this.closeModal();
        }
    }

    async confirmMobileMoneyPayment() {
        const { plate, vehicle_type, numero } = this.state.mobileForm;
        const montantTTC = this.getTTC(vehicle_type || "");
        if (!plate || !vehicle_type || !numero || montantTTC <= 0) {
            return this.notification.add("Veuillez remplir tous les champs et sélectionner un type de véhicule.", {
                type: "warning"
            });
        }
        this.state.loading = true;
        try {
            const res = await rpc("/anpr_peage/pay", {
                plate,
                vehicle_type,
                numero,
                amount: montantTTC,
                user_id: this.state.userConfig.id,
            });
            if (res.payment_status === "success") {
                // Effacer l’aperçu précédent pour laisser le temps de correction
                this._resetDetectedPlate();

                this._addTransaction(plate, montantTTC, "mobile");
                this.notification.add("Paiement réussi !", { type: "success" });
                await fetch(this.state.flask_url, { method: 'DELETE' });
                this.closeMobileModal();
            } else {
                this.notification.add(`⚠️ ${res.message}`, { type: "warning" });
            }
        } catch (error) {
            console.error("Erreur paiement mobile :", error);
            this.notification.add("Erreur de communication avec le serveur.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    _addTransaction(plate, amount, payment_method) {
        const now = new Date();
        const id = Date.now();
        const optionsDate = { timeZone: "Africa/Libreville", day: "2-digit", month: "2-digit", year: "numeric" };
        const optionsTime = { timeZone: "Africa/Libreville", hour: "2-digit", minute: "2-digit", hour12: false };
        const date = now.toLocaleDateString("fr-FR", optionsDate);
        const time = now.toLocaleTimeString("fr-FR", optionsTime);
        const paymentLabels = { manual: "Manuel", mobile: "Mobile Money", subscription: "Abonnement" };
        const paymentLabel = paymentLabels[payment_method] || "Inconnu";

        this.state.transactions.unshift({
            id,
            operator: this.state.userConfig?.name || "Opérateur",
            plate,
            date,
            time,
            amount,
            payment_method: paymentLabel,
        });
        this.paginateTransactions();
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

    resetForms() {
        this.state.form = { plate: "", vehicle_type: "", amount: 0 };
        this.state.mobileForm = { plate: "", vehicle_type: "", numero: "", amount: 0 };
    }

    formatDateTime(date) {
        return date.toLocaleString("fr-FR", {
            weekday: "short", year: "numeric", month: "long", day: "numeric",
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
    }
}

registry.category("actions").add("anpr_peage_dashboard", PeageDashboard);