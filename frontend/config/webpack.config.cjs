"use strict";

const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const BundleTracker = require("webpack-bundle-tracker");
const ESLintPlugin = require('eslint-webpack-plugin');

const rootDir = path.resolve(__dirname, "..");
const srcDir = path.resolve(rootDir, "src");

module.exports = (env, argv) => {
  const isProduction = argv.mode === "production";

  let bundleStatsFile = path.resolve("../webpack-dev-stats.json");
  if (isProduction) {
    bundleStatsFile = path.resolve("../webpack-dev-stats.json");
  }

  return {
    context: __dirname,
    devtool: isProduction ? "nosources-source-map" : "source-map",
    entry: {
      dashboard: {
        import: [
          path.resolve(rootDir, "apps/dashboard/index.js"),
          path.resolve(rootDir, "apps/dashboard/dashboard.scss"),
          path.resolve(rootDir, "apps/dashboard/image-viewer.scss"),
        ],
        dependOn: "vendor",
      },
      publicShare: {
        import: [
          path.resolve(rootDir, "apps/public_share/index.js"),
          path.resolve(rootDir, "apps/dashboard/image-viewer.scss"),
        ],
        dependOn: "vendor",
      },
      vendor: ["mithril", path.resolve(srcDir, "styles/vendor.scss")],
      blockForm: [path.resolve(srcDir, 'styles/block-form.scss')],
    },
    output: {
      filename: "[name]-[fullhash].js",
      clean: true,
    },
    plugins: [
      new ESLintPlugin({
        configType: 'flat',
        context: path.resolve(__dirname, '../'),
        extensions: ['js', 'jsx', 'ts', 'tsx', 'cjs'],
      }),
      new MiniCssExtractPlugin({
        filename: "static/css/[name].[contenthash].css",
        linkType: "text/css",
      }),
      new BundleTracker({
        relativePath: true,
        path: path.dirname(bundleStatsFile),
        filename: path.basename(bundleStatsFile),
      }),
    ],
    module: {
      rules: [
        {
          test: /\.(scss|css)$/i,
          use: [
            MiniCssExtractPlugin.loader,
            "css-loader",
            "resolve-url-loader",
            {
              loader: "sass-loader",
              options: {
                sassOptions: {
                  // Ignore Bootrstrap "Sass @import rules are deprecated"
                  quietDeps: true,
                  silenceDeprecations: ["import"],
                },
              },
            },
          ],
        },
        {
          test: /\.(png|svg|jpg|jpeg|gif)$/i,
          type: "asset/resource",
          generator: {
            filename: "static/img/[hash][ext][query]",
          },
        },
        {
          test: /\.(svg|eot|woff|woff2|ttf)$/i,
          type: "asset/resource",
          generator: {
            filename: "static/fonts/[hash][ext][query]",
          },
        },
        {
          test: /\.js$/,
          exclude: /node_modules/,
          use: {
            loader: "babel-loader",
            options: {
              presets: [
                ["@babel/preset-env", { targets: { node: "current" } }],
              ],
              plugins: [
                [
                  "@babel/plugin-transform-react-jsx",
                  {
                    pragma: "m",
                    pragmaFrag: "'['",
                  },
                ],
              ],
            },
          },
        },
      ],
    },
  };
};
