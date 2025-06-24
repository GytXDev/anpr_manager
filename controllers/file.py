from odoo import http, fields
from odoo.http import request
from datetime import datetime, time
from pytz import timezone
from io import BytesIO
from reportlab.pdfgen import canvas
import base64
import logging

_logger = logging.getLogger(__name__)

# Heure locale Gabon
def now_gabon():
    return datetime.now(timezone("Africa/Libreville")).replace(tzinfo=None)

# Génère un PDF avec l'heure actuelle
def generate_dummy_pdf():
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.drawString(100, 800, "📄 Rapport de fermeture de caisse")
    p.drawString(100, 780, f"Date : {now_gabon().strftime('%d/%m/%Y à %H:%M')}")
    p.drawString(100, 760, "Merci pour votre travail 💼")
    p.showPage()
    p.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# Envoie un mail avec un PDF en pièce jointe
def send_closing_report_email_with_pdf(subject, body, to_email, pdf_content, filename="rapport_caisse.pdf"):
    env = request.env
    smtp_user = env['ir.mail_server'].sudo().search([], limit=1).smtp_user or 'noreply@example.com'

    mail = env['mail.mail'].sudo().create({
        'subject': subject,
        'body_html': f"<p>{body}</p>",
        'email_to': to_email,
        'email_from': smtp_user,
    })

    env['ir.attachment'].sudo().create({
        'name': filename,
        'type': 'binary',
        'datas': base64.b64encode(pdf_content),
        'res_model': 'mail.mail',
        'res_id': mail.id,
        'mimetype': 'application/pdf',
    })

    mail.send()
    _logger.info("✅ Email de fermeture envoyé à %s avec pièce jointe %s", to_email, filename)

# Contrôleur Odoo
class AnprPeageController(http.Controller):

    @http.route('/anpr_peage/logout_user', type='json', auth='user', csrf=False)
    def logout_user(self):
        try:
            user = request.env.user
            heure_locale = now_gabon().strftime('%d/%m/%Y à %H:%M')
            subject = f"Fermeture de caisse — {user.name}"
            body = f"La caisse de {user.name} a été fermée avec succès le {heure_locale}."

            pdf = generate_dummy_pdf()

            send_closing_report_email_with_pdf(
                subject=subject,
                body=body,
                to_email="mahelguindja@gmail.com",
                pdf_content=pdf
            )

            request.session.logout()

            return {
                'status': 'success',
                'message': 'Caisse fermée, mail avec PDF envoyé, utilisateur déconnecté.'
            }

        except Exception as e:
            _logger.error("Erreur lors de la fermeture de caisse : %s", e)
            return {
                'status': 'error',
                'message': str(e)
            }