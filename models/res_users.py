# anpr_peage_manager/models/res_users.py
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    # ————— ARTEMIS / FLASK / MOBILE MONEY / VFD EXISTANTS —————
    artemis_app_key         = fields.Char("Clé App Artemis")
    artemis_app_secret      = fields.Char("Secret App Artemis")
    artemis_url             = fields.Char("URL Artemis")
    artemis_token           = fields.Char("Token Artemis")
    artemis_event_dest_url  = fields.Char("URL Flask (eventDest)")
    artemis_event_src_codes = fields.Char("Liste caméras ANPR")
    flask_url               = fields.Char("URL Serveur Flask")
    payment_api_url         = fields.Char("URL API Mobile Money")
    vfd_url                 = fields.Char("URL Serveur VFD")

    # ————— IMPRESSION ESC/POS —————
    printer_ip   = fields.Char("IP de l'imprimante")
    printer_port = fields.Integer("Port de l'imprimante", default=9100)

    # ————— NOUVEAUX CHAMPS PAR UTILISATEUR : TVA + TARIFS HT —————
    tva_rate    = fields.Float(
        string="Taux de TVA (%)",
        default=18.0,
        help="Pourcentage de TVA à appliquer sur les tarifs (ex: 18 → 18%)."
    )
    price_autre   = fields.Float(
        string="Tarif « Autre » (HT, en CFA)",
        default=1500.0,
        help="Tarif hors taxe pour la catégorie « Autre »."
    )
    price_car     = fields.Float(
        string="Tarif « Voiture particulière » (HT, en CFA)",
        default=1500.0,
        help="Tarif hors taxe pour la catégorie « Voiture particulière »."
    )
    price_camion  = fields.Float(
        string="Tarif « Camion » (HT, en CFA)",
        default=28000.0,
        help="Tarif hors taxe pour la catégorie « Camion »."
    )
    price_4x4 = fields.Float(
        string="Tarif « 4×4 » (HT, en CFA)",
        default=5000.0,
        help="Tarif hors taxe pour la catégorie « 4×4 »."
    )
    price_bus     = fields.Float(
        string="Tarif « Bus » (HT, en CFA)",
        default=7000.0,
        help="Tarif hors taxe pour la catégorie « Bus »."
    )

    # ————— NOUVEAU : Email d’envoi pour les rapports —————
    email_report_from = fields.Char(
        string="Email d'envoi du rapport",
        help="Adresse email qui sera utilisée comme expéditeur pour l’envoi des rapports."
    )

    # ————— Configuration du serveur distant —————
    remote_odoo_url = fields.Char("URL Odoo distant")
    remote_odoo_db = fields.Char("Base de données distante")
    remote_odoo_login = fields.Char("Utilisateur distant")
    remote_odoo_password = fields.Char("Mot de passe distant")
    remote_odoo_prefix = fields.Char("Préfixe des écritures distantes", default="[DISTANT]")

    # ————— ID du caissier sur le serveur en ligne —————
    peage_server_id = fields.Integer(string="ID Serveur Distant", help="Identifiant de l'utilisateur sur le serveur distant")