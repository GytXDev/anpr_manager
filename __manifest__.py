{
    'name': 'Péage',
    'version': '1.0.0',
    'category': 'Transport',
    'sequence': -99,
    'summary': 'Gestion du péage avec reconnaissance de plaques (ANPR)',
    'description': """
        Système de gestion de péage simulé avec sélection de type de véhicule,
        saisie de plaque, paiement via API et affichage du statut de transaction.
    """,
    'author': 'Ogooué Technologies',
    'website': 'https://ogoouetech.com',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/peage_manager.xml',
        'data/sequence.xml',
    ],
    'assets': {
    'web.assets_backend': [
            'anpr_peage_manager/static/src/js/main.js',
            'anpr_peage_manager/static/src/js/CashDrawerScreen.js',
            'anpr_peage_manager/static/src/js/PeageDashboard.js',
            'anpr_peage_manager/static/src/xml/template.xml',
            'anpr_peage_manager/static/src/xml/PeageDashboard.xml',
            'anpr_peage_manager/static/src/xml/cash_drawer_screen.xml',
            'anpr_peage_manager/static/src/css/dashboard.css',
            'anpr_peage_manager/static/src/css/cash_drawer_screen.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}