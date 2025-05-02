# anpr_peage_manager/controllers/pay.py
from odoo import _
from pytz import timezone
from datetime import datetime
import textwrap
import logging
import re

_logger = logging.getLogger(__name__)

# ESC/POS commandes
INIT_PRINTER   = b"\x1b\x40"           # Init imprimante
CENTER_TEXT    = b"\x1b\x61\x01"       # Centrer texte
FEEDS_5        = b"\n" * 5
CUT_FULL       = b"\x1b\x69"           # Coupe complète
OPEN_DRAWER    = b"\x1b\x70\x00\x19\xFA"

# Code-barres (CODE39 — compatible max)
BARCODE_HEIGHT = b"\x1d\x68\x50"       # Hauteur : 80 dots
BARCODE_WIDTH  = b"\x1d\x77\x02"       # Largeur moyenne
SELECT_CODE39  = b"\x1d\x6b\x04"       # Type CODE39

def generate_receipt_content(plate, vehicle_type, numero, amount, status_message, ticket_number, open_drawer=True):
    """
    Génère le contenu ESC/POS du reçu avec un code-barres CODE39 basé sur la plaque.
    """

    now = datetime.now(timezone("Africa/Libreville")).strftime("%d/%m/%Y %H:%M:%S")
    show_numero = numero != "MANUEL"

    # Texte du reçu
    body = textwrap.dedent(f"""\

        OTECHPEAGE
        ----------------------------
        TICKET N° {ticket_number}
        REÇU DE PAIEMENT
        ----------------------------
        Ogooué Technologies
        Date    : {now}
        ----------------------------
        Véhicule: {vehicle_type.upper()}
        Plaque  : {plate}
        {f"Numéro  : {numero}" if show_numero else ""}
        Montant : {amount} CFA
        Statut  : {status_message.upper()}
        ----------------------------
    """)

    try:
        # Encodage CP850
        text_bytes = body.encode('cp850', errors='replace')

        # Nettoyage de la plaque pour le code-barres (CODE39)
        cleaned_plate = re.sub(r'[^A-Z0-9]', '', plate.upper())  # Exemple : TR123AB
        barcode_data = cleaned_plate.encode('ascii') + b"\x00"   # null-terminated

        # Construction de la séquence du code-barres
        barcode_bytes = (
            BARCODE_HEIGHT +
            BARCODE_WIDTH +
            SELECT_CODE39 +
            barcode_data
        )

        # Message complet
        parts = [
            INIT_PRINTER,
            CENTER_TEXT,
            text_bytes,
            barcode_bytes,
            FEEDS_5,
        ]
        if open_drawer:
            parts.append(OPEN_DRAWER)
        parts.append(CUT_FULL)

        return b"".join(parts)

    except Exception as e:
        _logger.error("Erreur génération reçu POS: %s", e, exc_info=True)
        error_msg = _("ERREUR REÇU : %s") % str(e)
        return error_msg.encode('ascii', errors='ignore')