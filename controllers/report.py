# anpr_peage_manager/controllers/report.py

from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
from pytz import timezone
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
import base64
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
        if today.month == 12:
            end = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(today.year, today.month + 1, 1) - timedelta(seconds=1)
    elif period == "quarterly":
        quarter = (today.month - 1) // 3 + 1
        start_month = 3 * (quarter - 1) + 1
        start = datetime(today.year, start_month, 1)
        end_month = start_month + 2
        if end_month == 12:
            end = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(today.year, end_month + 1, 1) - timedelta(seconds=1)
    elif period == "semiannual":
        start = datetime(today.year, 1 if today.month <= 6 else 7, 1)
        end = datetime(today.year, 6 if today.month <= 6 else 12, 30, 23, 59, 59)
    elif period == "yearly":
        start = datetime(today.year, 1, 1)
        end = datetime(today.year, 12, 31, 23, 59, 59)
    else:
        raise ValueError("Période inconnue")

    return start, end

def generate_report_pdf(period, start, end, user):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(f"<b>Rapport de caisse — {period.capitalize()}</b>", styles['Title'])
    info = Paragraph(
        f"Caissier : <b>{user.name}</b><br/>"
        f"Période : <b>{start.strftime('%d/%m/%Y')} → {end.strftime('%d/%m/%Y')}</b><br/>"
        f"Généré le : <b>{now_gabon().strftime('%d/%m/%Y %H:%M')}</b>",
        styles['Normal'])

    elements.extend([title, Spacer(1, 12), info, Spacer(1, 20)])

    logs = request.env['anpr.log'].sudo().search([
        ('user_id', '=', user.id),
        ('paid_at', '>=', start),
        ('paid_at', '<=', end),
        ('payment_status', '=', 'success')
    ], order="paid_at asc")

    def render_table(label, filtered_logs):
        elements.append(Paragraph(f"<b>{label}</b>", styles['Heading3']))
        data = [["Date", "Heure", "Plaque", "Montant (CFA)"]]
        total = 0
        for log in filtered_logs:
            dt = log.paid_at.strftime("%d/%m/%Y")
            hr = log.paid_at.strftime("%H:%M")
            plate = log.plate or "-"
            amount = f"{log.amount:,.0f}"
            data.append([dt, hr, plate, amount])
            total += log.amount

        table = Table(data, colWidths=[60*mm, 40*mm, 40*mm, 40*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ]))
        elements.extend([table, Spacer(1, 10)])
        return total

    total_manual = render_table("Paiements MANUELS", logs.filtered(lambda l: l.payment_method == 'manual'))
    total_mobile = render_table("Paiements MOBILE", logs.filtered(lambda l: l.payment_method == 'mobile'))

    total_global = total_manual + total_mobile
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Total MANUEL :</b> {total_manual:,.0f} CFA", styles['Normal']))
    elements.append(Paragraph(f"<b>Total MOBILE :</b> {total_mobile:,.0f} CFA", styles['Normal']))
    elements.append(Paragraph(f"<b>Total GÉNÉRAL :</b> {total_global:,.0f} CFA", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def send_report_email(to_email, subject, body, pdf_data, filename="rapport.pdf"):
    env = request.env
    smtp_user = env['ir.mail_server'].sudo().search([], limit=1).smtp_user or 'noreply@example.com'

    attachment = env['ir.attachment'].sudo().create({
        'name': filename,
        'type': 'binary',
        'datas': base64.b64encode(pdf_data).decode('utf-8'),
        'mimetype': 'application/pdf',
    })

    mail = env['mail.mail'].sudo().create({
        'subject': subject,
        'body_html': f"<p>{body}</p>",
        'email_to': to_email,
        'email_from': smtp_user,
        'attachment_ids': [(6, 0, [attachment.id])],
    })

    mail.send()
    _logger.info("Rapport envoyé à %s", to_email)

class ANPRReportController(http.Controller):

    @http.route('/anpr_peage/send_report', type='json', auth='user')
    def send_report(self, period):
        try:
            user = request.env.user
            start, end = compute_date_range(period)
            pdf = generate_report_pdf(period, start, end, user)
            subject = f"Rapport {period.capitalize()} - {user.name}"
            body = f"Voici le rapport {period} de la caisse de {user.name}"

            send_report_email(
                to_email="mahelguindja@gmail.com",
                subject=subject,
                body=body,
                pdf_data=pdf,
                filename=f"rapport_{period}.pdf"
            )

            return {'status': 'success', 'message': 'Rapport envoyé avec succès.'}

        except Exception as e:
            _logger.error("Erreur lors de l'envoi du rapport : %s", e)
            return {'status': 'error', 'message': str(e)}