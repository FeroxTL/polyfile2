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
- **Production**: `polyfile/web_assets/bundles/` (used when `DEBUG=False`, stats file `polyfile/webpack-stats.json`)

Production assets are part of the Python package; see
[Building a distribution](../operations/packaging.md).

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

## Upload queue

The SPA uploads files through a singleton queue in
`frontend/apps/dashboard/services/UploadManager.js`:

- Files are uploaded one at a time; a job moves through `queued`, `creating`, `uploading` and
  then `done`, `conflict`, `error` or `canceled`.
- The queue pauses on the first unresolved conflict or error, so the UI shows one actionable
  message at a time. Users can retry network/server failures, replace a conflicting file or
  skip it.
- Progress is byte-weighted across the whole batch (`percent`) and complemented by
  `completedCount`/`totalCount`.
- `cancelAll()` aborts in-flight XHRs, marks pending jobs as canceled and deletes placeholder
  nodes created by the queue.
- Replacing reuses the existing `FsNode`, so its UUID and share links do not change.
- A `beforeunload` listener asks the browser to confirm leaving while `hasPendingWork` is true.

`frontend/apps/dashboard/modals/upload_monitor.js` renders the UI. `UploadMonitorDocked` is the
fixed bottom-right panel used on desktop (no backdrop); `UploadMonitorModal` reuses the same
header and body inside a standard modal on mobile. The header collapses the body, shows the
overall progress and hosts an actions menu with "Cancel all uploads". The menu is implemented
without Bootstrap JS and uses fixed positioning so the panel or modal cannot clip it.

`frontend/apps/dashboard/modals/uploader.js` adapts file inputs and captures the target
`parent_id` at selection time. Component and service tests live next to the modules under
`__tests__/`.

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
