# anpr_peage_manager\models\peage_log.py
from odoo import models, fields, api
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
    ], string="Type de paiement")

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

    @api.model
    def get_current_user_info(self):
        """Ne crée rien, renvoie juste id, name et URL avatar."""
        user = self.env.user
        return {
            'id': user.id,
            'name': user.name,
            'avatar_url': f"/web/image/res.users/{user.id}/image_128",
        }