# anpr_peage_manager\models\peage_log.py
from odoo import models, fields, api
from datetime import datetime

class AnprLog(models.Model):
    _name = 'anpr.log'
    _description = 'Historique des passages ANPR'

    plate = fields.Char(string="Plaque d'immatriculation", required=True)
    vehicle_type = fields.Selection([
        ('voiture', 'Voiture'),
        ('bus', 'Bus'),
        ('taxi', 'Taxi'),
        ('moto', 'Moto'),
        ('camion', 'Camion')
    ], string="Type de véhicule", required=True)

    payment_status = fields.Selection([
        ('pending', 'En attente'),
        ('success', 'Paiement réussi'),
        ('failed', 'Paiement échoué')
    ], string="Statut du paiement", default='pending')

    transaction_message = fields.Text(string="Message de transaction")
    amount = fields.Float(string="Montant payé")
    paid_at = fields.Datetime(string="Date de paiement")
    created_at = fields.Datetime(string="Date de création", default=lambda self: fields.Datetime.now())

    def mark_as_success(self, message):
        self.payment_status = 'success'
        self.transaction_message = message
        self.paid_at = datetime.now()

    def mark_as_failed(self, message):
        self.payment_status = 'failed'
        self.transaction_message = message