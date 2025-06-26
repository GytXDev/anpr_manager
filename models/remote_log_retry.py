# anpr_peage_manager\models\remote_log_retry.py
from odoo import models, fields, api
import xmlrpc.client
import logging

_logger = logging.getLogger(__name__)

class RemoteLogRetry(models.Model):
    _name = 'anpr.remote.log.retry'
    _description = 'Logs à réessayer en envoi distant'

    plate = fields.Char(required=True)
    vehicle_type = fields.Char()
    amount = fields.Float()
    transaction_message = fields.Char()
    payment_status = fields.Char()
    payment_method = fields.Char()
    paid_at = fields.Datetime()
    user_id = fields.Many2one('res.users', required=True)
    site_prefix = fields.Char()
    state = fields.Selection(
        [('pending', 'En attente'), ('sent', 'Envoyé')],
        default='pending'
    )

    @api.model
    def resend_failed_remote_logs(self):
        logs = self.search([('state', '=', 'pending')])
        for log in logs:
            user = log.user_id
            if not all([user.remote_odoo_url, user.remote_odoo_db, user.remote_odoo_login, user.remote_odoo_password]):
                _logger.warning(f"[CRON] Paramètres incomplets pour l'utilisateur {user.name}")
                continue

            try:
                # Authentification
                common = xmlrpc.client.ServerProxy(f"{user.remote_odoo_url}/xmlrpc/2/common")
                uid = common.authenticate(user.remote_odoo_db, user.remote_odoo_login, user.remote_odoo_password, {})
                if not uid:
                    raise Exception("Échec d’authentification sur le serveur distant.")

                models = xmlrpc.client.ServerProxy(f"{user.remote_odoo_url}/xmlrpc/2/object")

                # Création du caissier distant si nécessaire
                peage_id = user.peage_server_id
                if not peage_id:
                    peage_id = models.execute_kw(
                        user.remote_odoo_db, uid, user.remote_odoo_password,
                        'res.users', 'create',
                        [{'name': user.name, 'login': user.login}]
                    )
                    user.peage_server_id = peage_id

                # Préparation des données
                log_data = {
                    'plate': log.plate,
                    'vehicle_type': log.vehicle_type,
                    'amount': log.amount,
                    'transaction_message': f"{log.site_prefix or '[DISTANT]'} {log.transaction_message}",
                    'payment_status': log.payment_status or 'success',
                    'payment_method': log.payment_method or 'manual',
                    'paid_at': log.paid_at,
                    'user_id': peage_id,
                    'site_prefix': log.site_prefix or '[DISTANT]',
                }

                # Envoi du log
                models.execute_kw(user.remote_odoo_db, uid, user.remote_odoo_password, 'anpr.log', 'create', [log_data])
                _logger.info(f"[CRON] Log envoyé avec succès : {log.plate}")
                
                # Suppression du log local après succès
                log.unlink()

            except Exception as e:
                _logger.error(f"[CRON] Erreur lors de l'envoi du log {log.plate} : {e}")