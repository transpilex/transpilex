SUPPORTED_FRAMEWORKS = [
    "PHP",
    "Laravel",
    "Django",
    "Core",
    "MVC",
    "RoR",
    "CakePHP",
    "Codeigniter",
    "Node",
    "Flask",
    "Symfony",
    "Spring",
    "Blazor"
]

SUPPORTED_PIPELINES = ["Gulp", "Vite"]
DEFAULT_PIPELINE = "Gulp"

UI_LIBRARIES = ["Bootstrap", "Tailwind"]
DEFAULT_UI_LIBRARY = "Bootstrap"

VITE_ONLY = ["Laravel"]

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
    "gulp": "^4.0.2",
    "gulp-plumber": "^1.2.1",
    "gulp-npm-dist": "^1.0.4",
    "gulp-postcss": "^10.0.0",
    "gulp-rename": "^2.0.0",
    "gulp-replace": "^1.1.4",
    "gulp-rtlcss": "^2.0.0",
    "gulp-sass": "^5.0.0",
    "gulp-uglify-es": "^3.0.0",
    "node-sass-tilde-importer": "^1.0.2",
    "pixrem": "^5.0.0",
    "postcss": "^8.3.11",
    "sass": "1.77.6",
}

GULP_TW_DEV_DEPENDENCIES = {
    "@tailwindcss/postcss": "^4.1.13",
    "autoprefixer": "^10.4.0",
    "gulp-concat": "^2.6.1",
    "cssnano": "^7.0.0",
    "gulp": "^4.0.2",
    "gulp-plumber": "^1.2.1",
    "gulp-npm-dist": "^1.0.4",
    "gulp-postcss": "^10.0.0",
    "gulp-rename": "^2.0.0",
    "gulp-uglify-es": "^3.0.0",
    "pixrem": "^5.0.0",
    "postcss": "^8.3.11",
    "tailwindcss": "^4.0.7",
}

VITE_DEV_DEPENDENCIES = {"sass": "1.77.6"}

VITE_TW_DEV_DEPENDENCIES = {"@tailwindcss/vite": "^4.0.7"}

PUBLIC_ONLY_ASSETS = ["images", "img", "media", "data", "json"]

# For generating folder structure
FOLDERS = {
    "dashboard",
    "dashboards",
    "apps",
    "ecommerce",
    "hr",
    "project",
    "promo",
    "task",
    "users",
    "projects",
    "blog",
    "ticket",
    "forum",
    "crm",
    "email",
    "finance",
    "hospital",
    "hrm",
    "invoice",
    "pos",
    "pages",
    "misc",
    "plugins",
    "auth",
    "auth-2",
    "auth-3",
    "auth-card",
    "auth-split",
    "auth-basic",
    "auth-cover",
    "auth-boxed",
    "auth-modern",
    "error",
    "layouts",
    "sidebar",
    "topbar",
    "sidenav",
    "ui",
    "base-ui",
    "form",
    "forms",
    "chart",
    "charts",
    "apex",
    "echart",
    "chartjs",
    "table",
    "tables",
    "datatables",
    "icon",
    "icons",
    "map",
    "maps",
    "utilities",
    "navigation",
    "landing",
    "invoices",
    "contacts",
}

# No further nesting will take place inside these folders
NO_NESTING_FOLDERS = {
    "dashboard",
    "dashboards",
    "pages",
    "misc",
    "plugins",
    "auth",
    "auth-2",
    "auth-3",
    "auth-card",
    "auth-split",
    "auth-basic",
    "auth-cover",
    "auth-boxed",
    "auth-modern",
    "error",
    "ui",
    "base-ui",
    "form",
    "forms",
    "icon",
    "icons",
    "map",
    "maps",
    "landing",
}

# PHP
PHP_EXTENSION = ".php"
PHP_ASSETS_PATH = "src/assets"
PHP_PARTIALS_PATH = "src/partials"

PHP_VITE_ASSETS_PATH = "src"
PHP_VITE_PARTIALS_PATH = "partials"
PHP_VITE_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/php-vite-boilerplate.git",
    ".",
]

PHP_VARIABLE_REPLACEMENT = r"<?php echo ($\1); ?>"

# Laravel
LARAVEL_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/laravel-boilerplate.git",
    ".",
]
LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/laravel-boilerplate-with-auth.git",
    ".",
]
LARAVEL_EXTENSION = ".blade.php"
LARAVEL_ASSETS_PATH = "resources"
LARAVEL_PARTIALS_PATH = "resources/views/partials"
LARAVEL_RESOURCES_PRESERVE = ["views"]

LARAVEL_VARIABLE_REPLACEMENT = r"{{ $\1 }}"

# Django
DJANGO_COOKIECUTTER_REPO = "https://github.com/transpilex/cookiecutter-django.git"
DJANGO_EXTENSION = ".html"
DJANGO_ASSETS_PATH = "static"
DJANGO_PARTIALS_PATH = "templates/partials"

DJANGO_VARIABLE_REPLACEMENT = r"{{ \1 }}"

# Dot Net
SLN_FILE_CREATION_COMMAND = "dotnet new sln -n"

# Core
CORE_COOKIECUTTER_REPO = "https://github.com/transpilex/cookiecutter-core.git"
CORE_EXTENSION = ".cshtml"
CORE_ADDITIONAL_EXTENSION = ".cshtml.cs"
CORE_ASSETS_PATH = "wwwroot"
CORE_VITE_ASSETS_PATH = "Assets"
CORE_PARTIALS_PATH = "Pages/Shared/Partials"
CORE_VARIABLE_REPLACEMENT = r"@\1"

# MVC
MVC_COOKIECUTTER_REPO = "https://github.com/transpilex/cookiecutter-mvc.git"
MVC_EXTENSION = ".cshtml"
MVC_ASSETS_PATH = "wwwroot"
MVC_VITE_ASSETS_PATH = "Assets"
MVC_PARTIALS_PATH = "Views/Shared/Partials"
MVC_VARIABLE_REPLACEMENT = r"@\1"

# RoR
ROR_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/ror-boilerplate.git",
    ".",
]
ROR_VITE_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/ror-vite-boilerplate.git",
    ".",
]
ROR_EXTENSION = ".html.erb"
ROR_ASSETS_PATH = "public"
ROR_VITE_ASSETS_PATH = "frontend"
ROR_PARTIALS_PATH = "app/views/layouts/partials"
ROR_VARIABLE_REPLACEMENT = r"<%= \1 %>"
ROR_TAILWIND_PLUGINS = (
    '\ngem "tailwindcss-ruby", "~> 4.1"\n gem "tailwindcss-rails", "~> 4.4"\n'
)

# CakePHP
CAKEPHP_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/cakephp-boilerplate.git",
    ".",
]
CAKEPHP_EXTENSION = ".php"
CAKEPHP_ASSETS_PATH = "webroot"
CAKEPHP_PARTIALS_PATH = "templates/element"
CAKEPHP_VARIABLE_REPLACEMENT = r"<?= $\1 ?>"
CAKEPHP_ASSETS_PRESERVE = ["index.php", ".htaccess"]

# Codeigniter
CODEIGNITER_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/codeigniter-boilerplate.git",
    ".",
]
CODEIGNITER_EXTENSION = ".php"
CODEIGNITER_ASSETS_PATH = "public"
CODEIGNITER_PARTIALS_PATH = "app/Views"
CODEIGNITER_VARIABLE_REPLACEMENT = r"<?= $\1 ?>"
CODEIGNITER_ASSETS_PRESERVE = ["index.php", ".htaccess", "manifest.json", "robots.txt"]

# Node
NODE_EXTENSION = ".ejs"
NODE_ASSETS_PATH = "public"
NODE_PARTIALS_PATH = "views"
NODE_VARIABLE_REPLACEMENT = r"<%- \1 %>"
NODE_DEPENDENCIES = {
    "cookie-parser": "^1.4.7",
    "ejs": "^3.1.10",
    "express": "^5.1.0",
    "express-ejs-layouts": "^2.5.1",
    "express-fileupload": "^1.5.2",
    "express-session": "^1.18.2",
    "nodemon": "^3.1.11",
    "npm-run-all": "^4.1.5",
    "path": "^0.12.7",
}

# Flask
FLASK_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/flask-boilerplate.git",
    ".",
]
FLASK_PROJECT_CREATION_COMMAND_AUTH = [
    "git",
    "clone",
    "https://github.com/transpilex/flask-boilerplate-with-auth.git",
    ".",
]
FLASK_EXTENSION = ".html"
FLASK_ASSETS_PATH = "apps/static"
FLASK_PARTIALS_PATH = "apps/templates/partials"
FLASK_VARIABLE_REPLACEMENT = r"{{ \1 }}"

# Symfony
SYMFONY_PROJECT_CREATION_COMMAND = [
    "git",
    "clone",
    "https://github.com/transpilex/symfony-boilerplate.git",
    ".",
]
SYMFONY_EXTENSION = ".html.twig"
SYMFONY_ASSETS_PATH = "public"
SYMFONY_PARTIALS_PATH = "templates/partials"
SYMFONY_VARIABLE_REPLACEMENT = r"{{ (\1) ? \1 : '' }}"
SYMFONY_ASSETS_PRESERVE = ["index.php"]

# Spring Boot
SPRING_COOKIECUTTER_REPO = "https://github.com/transpilex/cookiecutter-spring-boot.git"
SPRING_EXTENSION = '.html'
SPRING_ASSETS_PATH = "src/main/resources/static"
SPRING_PARTIALS_PATH = "src/main/resources/templates/shared/partials"

# Blazor
BLAZOR_COOKIECUTTER_REPO = "https://github.com/transpilex/cookiecutter-blazor.git"
BLAZOR_EXTENSION = '.razor'
BLAZOR_ASSETS_PATH = "wwwroot"
BLAZOR_PARTIALS_PATH = "Components/Layout/Partials"
BLAZOR_VARIABLE_REPLACEMENT = r"@\1"

RESERVE_KEYWORDS = {
    "abstract", "continue", "for", "new", "switch",
    "assert", "default", "goto", "package", "synchronized",
    "boolean", "do", "if", "private", "this",
    "break", "double", "implements", "protected", "throw",
    "byte", "else", "import", "public", "throws",
    "case", "enum", "instanceof", "return", "transient",
    "catch", "extends", "int", "short", "try",
    "char", "final", "interface", "static", "void",
    "class", "finally", "long", "strictfp", "volatile",
    "const", "float", "native", "super", "while"
}

LOG_COLORS = {
    "INFO": "\033[38;5;39m",
    "SUCCESS": "\033[38;5;35m",
    "WARNING": "\033[38;5;178m",
    "ERROR": "\033[38;5;203m",
    "RESET": "\033[0m",
    "GRAY": "\033[38;5;244m",
}
