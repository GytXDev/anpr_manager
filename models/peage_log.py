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

    @api.model
    def resend_failed_moves(self):
        failed_moves = self.env['failed.remote.move'].sudo().search([])
        for move in failed_moves:
            try:
                self._send_to_remote_odoo(
                    ref=move.ref,
                    date=str(move.date),
                    amount=move.amount,
                    plate=move.plate,
                    journal_code=move.journal_code,
                    debit_code=move.debit_code,
                    credit_code=move.credit_code,
                    user=move.user_id
                )
                move.sudo().unlink()
                _logger.info(f"[SYNC] Réussi : {move.ref}")
            except Exception as e:
                _logger.warning(f"[SYNC] Échec : {move.ref} → {e}")

    @api.model
    def _send_to_remote_odoo(self, ref, date, amount, plate, journal_code, debit_code, credit_code, user=None):
        import xmlrpc.client
        import logging
        _logger = logging.getLogger(__name__)

        user = user or self.env.user
        remote_url = user.remote_odoo_url
        db = user.remote_odoo_db
        login = user.remote_odoo_login
        password = user.remote_odoo_password
        prefix = user.remote_odoo_prefix or "[DISTANT]"

        common = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/common")
        uid = common.authenticate(db, login, password, {})

        if not uid:
            raise Exception("Échec d’authentification sur le serveur distant.")

        models = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/object")

        journal_ids = models.execute_kw(db, uid, password, 'account.journal', 'search', [[('code', '=', journal_code)]])
        journal_id = journal_ids[0] if journal_ids else models.execute_kw(db, uid, password, 'account.journal', 'create', [{
            'name': f'Péage {"Mobile" if journal_code == "PEAGE_MM" else "Manuel"}',
            'code': journal_code,
            'type': 'cash',
        }])

        debit_ids = models.execute_kw(db, uid, password, 'account.account', 'search', [[('code', '=', debit_code)]])
        debit_id = debit_ids[0] if debit_ids else models.execute_kw(db, uid, password, 'account.account', 'create', [{
            'name': 'Caisse (Péage)',
            'code': debit_code,
            'account_type': 'asset_cash',
        }])

        credit_ids = models.execute_kw(db, uid, password, 'account.account', 'search', [[('code', '=', credit_code)]])
        credit_id = credit_ids[0] if credit_ids else models.execute_kw(db, uid, password, 'account.account', 'create', [{
            'name': 'Produits Péage',
            'code': credit_code,
            'account_type': 'income',
        }])

        move_id = models.execute_kw(db, uid, password, 'account.move', 'create', [{
            'journal_id': journal_id,
            'ref': ref,
            'date': date,
            'line_ids': [
                (0, 0, {
                    'name': f"{prefix} Paiement péage {plate}",
                    'account_id': debit_id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f"{prefix} Recette péage {plate}",
                    'account_id': credit_id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ]
        }])

        models.execute_kw(db, uid, password, 'account.move', 'action_post', [[move_id]])
        _logger.info(f"[REMOTE] Écriture postée avec succès : {move_id}")