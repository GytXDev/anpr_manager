/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

export class PeageScreen extends Component {
    static template = "anpr_peage_manager";

    setup() {
        this.state = useState({
            vehicle_type: '',
            plate: '',
            numero: '',
            amount: 0,
            result_message: '',
            payment_status: '',
            loading: false,
        });

        // Tarifs statiques par type de véhicule
        this.tarifs = {
            voiture: 200,
            bus: 1000,
            taxi: 700,
            moto: 300,
            camion: 1500,
        };
    }

    onVehicleTypeChange(ev) {
        const type = ev.target.value;
        this.state.vehicle_type = type;
        this.state.amount = this.tarifs[type] || 0;
    }

    async onPayClick() {
        this.state.result_message = '';
        this.state.payment_status = '';
        this.state.loading = true;

        const { vehicle_type, plate, numero, amount } = this.state;

        if (!vehicle_type || !plate || !numero || !amount) {
            this.state.result_message = "Veuillez remplir tous les champs.";
            this.state.payment_status = 'failed';
            this.state.loading = false;
            return;
        }

        try {
            const result = await rpc("/anpr_peage/pay", {
                plate,
                vehicle_type,
                numero,
                amount,
            });

            this.state.result_message = result.message;
            this.state.payment_status = result.payment_status || 'unknown';
        } catch (error) {
            console.error("Erreur de paiement :", error);
            this.state.result_message = "Erreur de communication avec le serveur.";
            this.state.payment_status = 'failed';
        }

        this.state.loading = false;
    }
}

registry.category("actions").add("anpr_peage_manager", PeageScreen);