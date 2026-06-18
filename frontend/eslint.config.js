// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    files: ['**/*.ts', '**/*.tsx'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off',
      'no-undef': 'off',
      'react/no-unescaped-entities': 'off',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', '.expo/**', 'src/**', 'components/risk/**'],
  },
]);
