# anpr_peage_manager/controllers/analytic_dashboard.py

from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
from pytz import timezone
from .pay import generate_receipt_content
import logging

_logger = logging.getLogger(__name__)

def now_gabon():
    return datetime.now(timezone("Africa/Libreville")).replace(tzinfo=None)

def compute_date_range(period):
    today = now_gabon().date()
    if period == "daily":
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
    elif period == "weekly":
        start = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif period == "monthly":
        start = datetime(today.year, today.month, 1)
        end = datetime(today.year + (today.month // 12), (today.month % 12) + 1, 1) - timedelta(seconds=1)
    elif period == "quarterly":
        quarter = (today.month - 1) // 3 + 1
        start_month = 3 * (quarter - 1) + 1
        start = datetime(today.year, start_month, 1)
        end = datetime(today.year, start_month + 3, 1) - timedelta(seconds=1)
    elif period == "semiannual":
        start = datetime(today.year, 1 if today.month <= 6 else 7, 1)
        end = datetime(today.year, 7 if today.month <= 6 else 13, 1) - timedelta(seconds=1)
    elif period == "yearly":
        start = datetime(today.year, 1, 1)
        end = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
    else:
        raise ValueError("Période inconnue")
    return start, end

class PeageAnalyticDashboardController(http.Controller):

    @http.route('/anpr_peage/analytic_data', type='json', auth='user')
    def get_analytic_data(self, period, prefix=None):
        try:
            start, end = compute_date_range(period)

            # On récupère tous les utilisateurs qui ont des logs (filtrés plus bas)
            logs_domain = [
                ('paid_at', '>=', start.replace(month=1, day=1)),
                ('paid_at', '<=', end),
                ('payment_status', '=', 'success')
            ]
            if prefix:
                logs_domain.append(('site_prefix', '=', prefix))

            all_logs = request.env['anpr.log'].sudo().search(logs_domain)
            users = all_logs.mapped('user_id')

            result = []
            monthly_manual = [0] * 12
            monthly_mobile = [0] * 12

            for user in users:
                user_logs = [log for log in all_logs if log.user_id.id == user.id and start <= log.paid_at <= end]

                for log in user_logs:
                    midx = log.paid_at.month - 1
                    if log.payment_method == 'manual':
                        monthly_manual[midx] += log.amount or 0
                    elif log.payment_method == 'mobile':
                        monthly_mobile[midx] += log.amount or 0

                manual_total = sum(log.amount for log in user_logs if log.payment_method == 'manual')
                mobile_total = sum(log.amount for log in user_logs if log.payment_method == 'mobile')
                transaction_count = len(user_logs)

                result.append({
                    'id': user.id,
                    'name': user.name,
                    'avatar': f"/web/image/res.users/{user.id}/image_128",
                    'manual_total': manual_total,
                    'mobile_total': mobile_total,
                    'total': manual_total + mobile_total,
                    'transactions': transaction_count
                })

            return {
                'status': 'success',
                'data': result,
                'monthly_manual': monthly_manual,
                'monthly_mobile': monthly_mobile,
                'start': start.strftime('%d/%m/%Y'),
                'end': end.strftime('%d/%m/%Y'),
            }

        except Exception as e:
            _logger.error("Erreur dans le backend analytique : %s", e)
            return {'status': 'error', 'message': str(e)}

    # Route pour la période personnalisée
    @http.route('/anpr_peage/analytic_data_custom', type='json', auth='user')
    def get_analytic_data_custom(self, start=None, end=None):
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(hours=23, minutes=59, seconds=59)

            # On récupère tous les utilisateurs qui ont des logs (filtrés plus bas)
            logs_domain = [
                ('paid_at', '>=', start_dt.replace(month=1, day=1)),
                ('paid_at', '<=', end_dt),
                ('payment_status', '=', 'success')
            ]
            
            all_logs = request.env['anpr.log'].sudo().search(logs_domain)
            users = all_logs.mapped('user_id')

            result = []
            monthly_manual = [0] * 12
            monthly_mobile = [0] * 12

            for user in users:
                user_logs = [log for log in all_logs if log.user_id.id == user.id and start_dt <= log.paid_at <= end_dt]

                for log in user_logs:
                    midx = log.paid_at.month - 1
                    if log.payment_method == 'manual':
                        monthly_manual[midx] += log.amount or 0
                    elif log.payment_method == 'mobile':
                        monthly_mobile[midx] += log.amount or 0

                manual_total = sum(log.amount for log in user_logs if log.payment_method == 'manual')
                mobile_total = sum(log.amount for log in user_logs if log.payment_method == 'mobile')
                transaction_count = len(user_logs)

                result.append({
                    'id': user.id,
                    'name': user.name,
                    'avatar': f"/web/image/res.users/{user.id}/image_128",
                    'manual_total': manual_total,
                    'mobile_total': mobile_total,
                    'total': manual_total + mobile_total,
                    'transactions': transaction_count
                })

            return {
                'status': 'success',
                'data': result,
                'monthly_manual': monthly_manual,
                'monthly_mobile': monthly_mobile,
                'start': start_dt.strftime('%d/%m/%Y'),
                'end': end_dt.strftime('%d/%m/%Y')
            }

        except Exception as e:
            _logger.error("Erreur dans le backend analytique personnalisé : %s", e)
            return {'status': 'error', 'message': str(e)}

    @http.route('/anpr_peage/transactions/<int:user_id>', type='http', auth='user')
    def redirect_to_transactions(self, user_id, period="monthly", start=None, end=None, **kwargs):
        try:
            action = request.env.ref('anpr_peage_manager.action_anpr_log_list_only').sudo().read()[0]

            if period == "custom" and start and end:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            else:
                start_dt, end_dt = compute_date_range(period)

            user = request.env['res.users'].sudo().browse(user_id)

            domain = [
                ['user_id', '=', user_id],
                ['payment_status', '=', 'success'],
                ['paid_at', '>=', start_dt.strftime('%Y-%m-%d %H:%M:%S')],
                ['paid_at', '<=', end_dt.strftime('%Y-%m-%d %H:%M:%S')],
            ]

            context = {
                "default_user_filter_display": f"Transactions de {user.name} du {start_dt.strftime('%d/%m/%Y')} au {end_dt.strftime('%d/%m/%Y')}",
                "default_dashboard_back": "/web#action=anpr_peage_dashboard_analytic"
            }

            return request.redirect(
                f"/web#action={action['id']}"
                f"&model=anpr.log"
                f"&view_type=list"
                f"&domain={domain}"
                f"&context={context}"
            )

        except Exception as e:
            _logger.error("Erreur lors de la redirection vers la vue liste des transactions : %s", e)
            return request.not_found()