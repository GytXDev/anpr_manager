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
    'depends': ['base', 'web', 'account', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/peage_manager.xml',
        'views/res_config_settings_view.xml',
        'data/sequence.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # D'abord les composants enfants
            'anpr_peage_manager/static/src/js/CashDrawerScreen.js',
            'anpr_peage_manager/static/src/js/PeageDashboard.js',
            # Puis le composant principal
            'anpr_peage_manager/static/src/js/PeageMainApp.js',
            # Puis les templates
            'anpr_peage_manager/static/src/xml/cash_drawer_screen.xml',
            'anpr_peage_manager/static/src/xml/PeageDashboard.xml',
            'anpr_peage_manager/static/src/xml/peage_main_app.xml',
            # CSS
            'anpr_peage_manager/static/src/css/dashboard.css',
            'anpr_peage_manager/static/src/css/cash_drawer_screen.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}