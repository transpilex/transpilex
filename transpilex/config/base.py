from pathlib import Path

SUPPORTED_FRAMEWORKS = ["PHP", "Laravel"]

SUPPORTED_PIPELINES = ["Gulp", "Vite"]
DEFAULT_PIPELINE = "Gulp"

UI_LIBRARIES = ["Bootstrap", "Tailwind"]
DEFAULT_UI_LIBRARY = "Bootstrap"

VITE_ONLY = ["Laravel", "RoR"]

SOURCE_PATH = "./html"
PAGES_PATH = f"{SOURCE_PATH}/src"
ASSETS_PATH = f"{SOURCE_PATH}/src/assets"
PARTIALS_PATH = f"{SOURCE_PATH}/src/partials"
DESTINATION_PATH = "./"

GULP_PLUGINS_FOLDER = "plugins"

GULP_DEV_DEPENDENCIES = {
    "autoprefixer": "^10.4.0",
    "gulp-concat": "^2.6.1",
    "cssnano": "^7.0.0",
    "gulp": "^5.0.0",
    "gulp-plumber": "^1.2.1",
    "gulp-npm-dist": "^1.0.4",
    "gulp-postcss": "^10.0.0",
    "gulp-rename": "^2.0.0",
    "gulp-rtlcss": "^2.0.0",
    "gulp-sass": "^5.0.0",
    "gulp-uglify-es": "^3.0.0",
    "node-sass-tilde-importer": "^1.0.2",
    "pixrem": "^5.0.0",
    "postcss": "^8.3.11",
    "sass": "1.77.6"
}

GULP_TW_DEV_DEPENDENCIES = {
    "@tailwindcss/postcss": "^4.1.13",
    "autoprefixer": "^10.4.0",
    "gulp-concat": "^2.6.1",
    "cssnano": "^7.0.0",
    "gulp": "^5.0.0",
    "gulp-plumber": "^1.2.1",
    "gulp-npm-dist": "^1.0.4",
    "gulp-postcss": "^10.0.0",
    "gulp-rename": "^2.0.0",
    "gulp-uglify-es": "^3.0.0",
    "pixrem": "^5.0.0",
    "postcss": "^8.3.11",
    "tailwindcss": "^4.0.7"
}

VITE_DEV_DEPENDENCIES = {
    "sass": "1.77.6"
}

VITE_TW_DEV_DEPENDENCIES = {
    "@tailwindcss/vite": "^4.0.7",
    "tailwindcss": "^4.0.7",
}

PUBLIC_ONLY_ASSETS = ["images", "img", "media", "data", "json"]

FOLDERS = {
    "charts", "sidebar", "topbar", "apex", "echart", "chartjs", "auth",
    "auth-card", "auth-split", "error", "apps", "tables", "datatables", "ui",
    "ecommerce", "form", "icons", "layouts", "maps", "forum", "plugins",
    "pages", "crm", "email", "finance", "hospital", "hrm", "invoice", "pos",
    "promo", "task", "users", "projects", "blog", "ticket", "dashboards", "sidenav", "auth-basic",
    "auth-cover", "auth-boxed", "auth-modern", "hr", "project", "auth-2", "auth-3", "misc", "dashboard", "utilities",
    "forms"
}

NO_NESTING_FOLDERS = {
    "auth", "auth-2", "auth-3",
    "auth-card", "auth-split", "auth-basic", "auth-cover", "auth-boxed", "auth-modern", "error",
}

# PHP
PHP_EXTENSION = '.php'

PHP_ASSETS_PATH = "src/assets"
PHP_PARTIALS_PATH = "src/partials"

PHP_VITE_ASSETS_PATH = "src"
PHP_VITE_PARTIALS_PATH = "partials"
PHP_VITE_CREATION_COMMAND = ['git', 'clone', 'https://github.com/transpilex/php-vite-boilerplate.git', '.']

PHP_VARIABLE_REPLACEMENT = r'<?php echo ($\1); ?>'

# Laravel
LARAVEL_PROJECT_CREATION_COMMAND = ['git', 'clone', 'https://github.com/transpilex/laravel-boilerplate.git', '.']
LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND = ['git', 'clone',
                                              'https://github.com/transpilex/laravel-boilerplate-with-auth.git', '.']

LARAVEL_EXTENSION = ".blade.php"
LARAVEL_ASSETS_PATH = "resources"
LARAVEL_PARTIALS_PATH = "resources/views/partials"
LARAVEL_RESOURCES_PRESERVE = ["views"]

LARAVEL_VARIABLE_REPLACEMENT = r'{{ $\1 }}'

LOG_COLORS = {
    "INFO": "\033[38;5;39m",
    "SUCCESS": "\033[38;5;35m",
    "WARNING": "\033[38;5;178m",
    "ERROR": "\033[38;5;203m",
    "RESET": "\033[0m",
    "GRAY": "\033[38;5;244m"
}

EXTRA_FILES = [
    "bun.lock",
    "yarn.lock",
    "package-lock.json"
]