# anpr_peage_manager/controllers/open_drawer.py

import socket
import logging

# Commandes ESC/POS
INIT_PRINTER = b"\x1b\x40"
OPEN_DRAWER = b"\x1b\x70\x00\x19\xFA"

_logger = logging.getLogger(__name__)

def open_cash_drawer(ip_address, port):
    """
    Ouvre le tiroir-caisse via l'imprimante à l'adresse IP et port donnés.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as printer:
            printer.settimeout(10)
            printer.connect((ip_address, port))
            printer.sendall(INIT_PRINTER + OPEN_DRAWER)
        return True, None
    except Exception as e:
        _logger.error("Erreur ouverture tiroir-caisse : %s", e, exc_info=True)
        return False, str(e)
