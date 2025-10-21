from pathlib import Path

SUPPORTED_FRAMEWORKS = ["PHP", "Laravel", "CodeIgniter", "CakePHP", "Symfony", "Node", "Django", "Flask", "Core",
                        "MVC",
                        "Blazor", "Spring", "RoR"]

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

VITE_DEV_DEPENDENCIES = {
}

# PHP
PHP_EXTENSION = '.php'

PHP_ASSETS_PATH = "./src/assets"
PHP_PARTIALS_PATH = Path("src/partials")

PHP_VITE_ASSETS_PATH = "./src"
PHP_VITE_PARTIALS_PATH = Path("partials")
PHP_VITE_CREATION_COMMAND = ['git', 'clone', 'https://github.com/transpilex/php-vite-boilerplate.git', '.']

PHP_VARIABLE_REPLACEMENT = r'<?php echo ($\1); ?>'

LOG_COLORS = {
    "INFO": "\033[38;5;39m",
    "SUCCESS": "\033[38;5;35m",
    "WARNING": "\033[38;5;178m",
    "ERROR": "\033[38;5;203m",
    "RESET": "\033[0m",
    "GRAY": "\033[38;5;244m"
}
