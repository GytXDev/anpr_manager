# models/failed_remote_move.py
from odoo import models, fields

class FailedRemoteMove(models.Model):
    _name = 'failed.remote.move'
    _description = "Écritures échouées à envoyer au serveur distant"

    ref = fields.Char(required=True)
    date = fields.Date(required=True)
    amount = fields.Float(required=True)
    plate = fields.Char(required=True)
    journal_code = fields.Char(required=True)
    debit_code = fields.Char(required=True)
    credit_code = fields.Char(required=True)
    user_id = fields.Many2one('res.users', required=True)
    error_message = fields.Text()