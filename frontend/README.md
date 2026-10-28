# Polyfile frontend

## Setup

```bash
npm install --include=dev
```

## Builds

Development (output: `../web_dev_assets/`, stats: `../webpack-dev-stats.json`):

```bash
npm run build_dev
# or
npm run watch
```

Production (output: `../polyfile/web_assets/`, stats: `../polyfile/webpack-stats.json`):

```bash
npm run build
```

Production assets are required before building the Python package. Development assets are
kept locally and are not part of the distribution.
