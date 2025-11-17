from pathlib import Path

from transpilex.config.project import ProjectConfig
from transpilex.utils.file import file_exists, copy_items
from transpilex.utils.logs import Log


def has_plugins_config(config: ProjectConfig):
    src_path = config.src_path / "plugins.config.js"
    dest_path = config.project_root_path / "plugins.config.js"

    plugins_config = file_exists(src_path)

    if plugins_config:
        copy_items(src_path, dest_path)
        Log.info(f"plugins.config.js is ready at: {dest_path}")
        return True
    else:
        return False


def add_gulpfile(config: ProjectConfig):
    plugins_config = has_plugins_config(config)

    tailwind = config.ui_library == "tailwind"

    imports = "const tailwindcss = require('@tailwindcss/postcss');" if tailwind else \
        "const gulpSass = require('gulp-sass');\nconst dartSass = require('sass');\nconst tildeImporter = require('node-sass-tilde-importer');\nconst rtlcss = require('gulp-rtlcss');"

    plugins_import = 'const pluginFile = require("./plugins.config"); // Import the plugins list' if plugins_config else f"""
const pluginFile = {{
    vendorsCSS: [],
    vendorsJS: []
}}
    """

    plugins_fn = f"""
// Copying Third Party Plugins Assets
const plugins = function () {{
    const out = paths.baseDistAssets + "/{config.gulp_config.plugins_folder}/";

    pluginFile.forEach(({{name, vendorsJS, vendorCSS, vendorFonts, assets, fonts, font, media, img, webfonts}}) => {{

        const handleError = (label, files) => (err) => {{
            const shortMsg = err.message.split('\\n')[0];
            console.error(`\\n${{label}} - ${{shortMsg}}`);
            throw new Error(` ${{label}} failed`);
        }};

        if (vendorsJS) {{
            src(vendorsJS)
                .on('error', handleError('vendorsJS'))
                .pipe(concat("vendors.min.js"))
                .pipe(dest(paths.baseDistAssets + "/js/"));
        }}

        if (vendorCSS) {{
          src(vendorCSS)
            .pipe(concat("vendors.min.css"))
            .on('error', handleError('vendorCSS'))
            .pipe(replace(/url\\((['"]?)(remixicon|boxicons)/g, "url($1fonts/$2"))
            .pipe(dest(paths.baseDistAssets + "/css/"));
        }}

        if (vendorFonts) {{
            src(vendorFonts)
                .on('error', handleError('vendorFonts'))
                .pipe(dest(paths.baseDistAssets + "/css/fonts/"));
        }}

        if (assets) {{
            src(assets)
                .on('error', handleError('assets'))
                .pipe(dest(`${{out}}${{name}}/`));
        }}

        if (img) {{
            src(img)
                .on('error', handleError('img'))
                .pipe(dest(`${{out}}${{name}}/img/`));
        }}

        if (media) {{
            src(media)
                .on('error', handleError('media'))
                .pipe(dest(`${{out}}${{name}}/`));
        }}

        if (fonts) {{
            src(fonts)
                .on('error', handleError('fonts'))
                .pipe(dest(`${{out}}${{name}}/fonts/`));
        }}

        if (font) {{
            src(font)
                .on('error', handleError('font'))
                .pipe(dest(`${{out}}${{name}}/font/`));
        }}

        if (webfonts) {{
            src(webfonts)
                .on('error', handleError('webfonts'))
                .pipe(dest(`${{out}}${{name}}/webfonts/`));
        }}
    }});

    return Promise.resolve();
}};
    """ if plugins_config else fr"""
const vendorStyles = function () {{
const out = paths.baseDistAssets + "/css/";

return src(pluginFile.vendorsCSS, {{sourcemaps: true, allowEmpty: true}})
    .pipe(concat('vendors.css'))
    .pipe(plumber()) // Checks for errors
    .pipe(postcss(processCss))
    .pipe(dest(out))
    .pipe(rename({{suffix: '.min'}}))
    .pipe(postcss(minifyCss)) // Minifies the result
    .pipe(dest(out));
}}


const vendorScripts = function () {{
    const out = paths.baseDistAssets + "/js/";

    return src(pluginFile.vendorsJS, {{sourcemaps: true, allowEmpty: true}})
        .pipe(concat('vendors.js'))
        .pipe(dest(out))
        .pipe(plumber()) // Checks for errors
        .pipe(uglify()) // Minifies the js
        .pipe(rename({{suffix: '.min'}}))
        .pipe(dest(out, {{sourcemaps: '.'}}));
}}


const plugins = function () {{
  const out = paths.baseDistAssets + "/{config.gulp_config.plugins_folder}/";
  return src(npmdist(), {{ base: "./node_modules" }})
    .pipe(rename(function (path) {{
      path.dirname = path.dirname.replace(/\/dist/, '').replace(/\\dist/, '');
    }}))
    .pipe(dest(out));
}};
    """

    plugins_task = "plugins," if plugins_config else "vendorStyles, vendorScripts, plugins,"

    functions = f"""
const processCss = [
    tailwindcss(),
    autoprefixer(), // adds vendor prefixes
    pixrem(), // add fallbacks for rem units
];

const minifyCss = [
    cssnano({{preset: 'default'}}), // minify result
];

const styles = function () {{
    const out = paths.baseDistAssets + "/css/";

    return src(paths.baseSrcAssets + "/css/style.css")
        .pipe(plumber()) // Checks for errors
        .pipe(postcss(processCss))
        .pipe(dest(out))
        .pipe(rename({{suffix: '.min'}}))
        .pipe(postcss(minifyCss)) // Minifies the result
        .pipe(dest(out));
}};

{plugins_fn}

const watchFiles = function () {{
    watch(paths.baseSrcAssets + "/css/**/*.css", series(styles));
}}

// Production Tasks
exports.default = series(
    {plugins_task}
    parallel(styles),
    parallel(watchFiles)
);

// Build Tasks
exports.build = series(
    {plugins_task}
    parallel(styles)
);

""" if tailwind else f"""
const sass = gulpSass(dartSass);
const uglify = gulUglifyES.default;

const processCss = [
    autoprefixer(), // adds vendor prefixes
    pixrem(), // add fallbacks for rem units
];

const minifyCss = [
    cssnano({{preset: 'default'}}), // minify result
];

const styles = function () {{
    const out = paths.baseDistAssets + "/css/";

    return src(paths.baseSrcAssets + "/scss/**/*.scss")
        .pipe(
            sass({{
                importer: tildeImporter,
                includePaths: [paths.baseSrcAssets + "/scss"],
            }}).on('error', sass.logError),
        )
        .pipe(plumber()) // Checks for errors
        .pipe(postcss(processCss))
        .pipe(dest(out))
        .pipe(rename({{suffix: '.min'}}))
        .pipe(postcss(minifyCss)) // Minifies the result
        .pipe(dest(out));
}};

const rtl = function () {{
    const out = paths.baseDistAssets + "/css/";

    return src(paths.baseSrcAssets + "/scss/**/*.scss")
        .pipe(
            sass({{
                importer: tildeImporter,
                includePaths: [paths.baseSrcAssets + "/scss"],
            }}).on('error', sass.logError),
        )
        .pipe(plumber()) // Checks for errors
        .pipe(postcss(processCss))
        .pipe(dest(out))
        .pipe(rtlcss())
        .pipe(rename({{suffix: "-rtl.min"}}))
        .pipe(postcss(minifyCss)) // Minifies the result
        .pipe(dest(out));
}};

{plugins_fn}

const watchFiles = function () {{
    watch(paths.baseSrcAssets + "/scss/**/*.scss", series(styles));
}}

// Production Tasks
exports.default = series(
    {plugins_task}
    parallel(styles),
    parallel(watchFiles)
);

// Build Tasks
exports.build = series(
    {plugins_task}
    parallel(styles)
);

// RTL Tasks
exports.rtl = series(
    {plugins_task}
    parallel(rtl),
    parallel(watchFiles)
);

// RTL Build Tasks
exports.rtlBuild = series(
    {plugins_task}
    parallel(rtl),
);
"""

    gulpfile_template = f"""
// Gulp and package
const {{src, dest, parallel, series, watch}} = require('gulp');

// Plugins
const autoprefixer = require('autoprefixer');
const concat = require('gulp-concat');
const cssnano = require('cssnano');
const pixrem = require('pixrem');
const plumber = require('gulp-plumber');
const postcss = require('gulp-postcss');
const rename = require('gulp-rename');
const gulUglifyES = require('gulp-uglify-es');
const npmdist = require('gulp-npm-dist');
const replace = require('gulp-replace');
{imports}

{plugins_import}

const paths = {{
    baseSrcAssets: "{config.gulp_config.src_path}",   // source assets directory
    baseDistAssets: "{config.gulp_config.dest_path}",  // build assets directory
}};

{functions}
    """.strip()

    gulpfile_path = config.project_root_path / "gulpfile.js"
    with open(gulpfile_path, "w", encoding="utf-8") as f:
        f.write(gulpfile_template)

    Log.info(f"gulpfile.js is ready at: {gulpfile_path}")
