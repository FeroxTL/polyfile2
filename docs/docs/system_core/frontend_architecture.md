# Frontend architecture

## Technology stack

- **Framework**: [Mithril.js](https://mithril.js.org/) 2.3.8
- **UI Framework**: [Bootstrap](https://getbootstrap.com/) 5.3.8
- **Icons**: [Font Awesome](https://fontawesome.com/) 7.3.1
- **Build tool**: [Webpack](https://webpack.js.org/) 5.108.4
- **Testing**: [Vitest](https://vitest.dev/) 5.0.5 with coverage via `@vitest/coverage-v8`
- **Package manager**: npm (workspaces enabled)

## Project structure

Frontend code is in `frontend/`:

```
frontend/
├── apps/           # Application entry points
│   ├── dashboard/  # Main dashboard app
│   └── public_share/ # Public share viewer app
├── config/         # Webpack configuration
├── core/           # Shared components and utilities (npm workspace)
└── src/            # Source files, styles
```

## Build configuration

Webpack is configured in `frontend/config/webpack.config.cjs` with:

- **Entry points**: `dashboard`, `publicShare`, `vendor`, `blockForm`
- **Output**: Content-hashed JS files (`[name]-[fullhash].js`)
- **CSS**: Extracted via `mini-css-extract-plugin` to `static/css/[name].[contenthash].css`
- **Loaders**: Babel (JSX), Sass/SCSS, CSS, resolve-url-loader
- **Plugins**: ESLint, BundleTracker (for Django integration), MiniCssExtractPlugin

### Build outputs

- **Development**: `web_dev_assets/bundles/` (used when `DEBUG=True`, stats file `webpack-dev-stats.json`)
- **Production**: `polyfile/web_assets/bundles/` (used when `DEBUG=False`, stats file `webpack-stats.json`)

### NPM scripts

```json
{
  "watch": "webpack --config config/webpack.config.cjs --mode development --watch --output-path ../web_dev_assets/bundles",
  "build_dev": "webpack --config config/webpack.config.cjs --mode development --output-path ../web_dev_assets/bundles",
  "build": "webpack --config config/webpack.config.cjs --mode production --output-path ../polyfile/web_assets/bundles",
  "test": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

## Coding standards

- **Named exports only** - Components must use named exports, not default exports
```js
// Correct
export const FsNodeEmptyDirectoryView = () => { ... };

// Incorrect
export default FsNodeEmptyDirectoryView;
```
- **ESLint compliance** - Run `npx eslint .` in the `frontend/` directory before committing
- **Mithril patterns** - Follow Mithril.js component patterns consistent with existing codebase

## Django integration

Frontend assets are integrated via `django-webpack-loader`. The loader reads stats files specified by `WEBPACK_STATS_FILE` setting and injects bundles into Django templates.
