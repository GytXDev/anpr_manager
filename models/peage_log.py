# anpr_peage_manager\models\peage_log.py
from odoo import models, fields, api
import pytz
from datetime import datetime

class AnprLog(models.Model):
    _name = 'anpr.log'
    _description = 'Historique des passages ANPR'

    user_id = fields.Many2one('res.users', string="Caissier", default=lambda self: self.env.uid)
    plate = fields.Char(string="Plaque d'immatriculation", required=True)
    vehicle_type = fields.Selection([
        ('car',     'Car'),
        ('4x4',     '4x4 / SUV'),
        ('bus',     'Bus'),
        ('camion',  'Camion'),
        ('autres',  'Autres'),
    ], string="Type de véhicule", required=True)


    payment_status = fields.Selection([
        ('pending', 'En attente'),
        ('success', 'Paiement réussi'),
        ('failed', 'Paiement échoué')
    ], string="Statut du paiement", default='pending')

    payment_method = fields.Selection([
        ('manual', 'Manuel'),
        ('mobile', 'Mobile Money'),
        ('subscription', 'Abonnement')
    ], string="Type de paiement")


    transaction_message = fields.Text(string="Message de transaction")
    amount = fields.Float(string="Montant payé")
    paid_at = fields.Datetime(string="Date de paiement")
    accounted = fields.Boolean(string="Comptabilisé", default=False)
    created_at = fields.Datetime(
        string="Date de création",
        default=lambda self: datetime.now(pytz.timezone("Africa/Libreville")).replace(tzinfo=None)
    )

    def mark_as_success(self, message):
        self.payment_status = 'success'
        self.transaction_message = message
        self.paid_at = datetime.now(pytz.timezone("Africa/Libreville")).replace(tzinfo=None)

    def mark_as_failed(self, message):
        self.payment_status = 'failed'
        self.transaction_message = message

    