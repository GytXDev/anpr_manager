module.exports = {
    content: [
        './**/*.xml',
        './**/*.js',
        // './**/*.ts',
    ],
    prefix: 'tw-', // préfixe pour éviter les conflits avec Odoo
    corePlugins: {
        preflight: false,        
    },
    theme: {
        extend: {},
    },
    plugins: [],
}