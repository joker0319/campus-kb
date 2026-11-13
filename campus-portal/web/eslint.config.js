import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  // ---------- 忽略范围 ----------
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'coverage/**',
      // Vite 加载配置文件时留下的临时产物
      'vite.config.ts.timestamp-*.mjs',
    ],
  },

  // ---------- 基础规则 ----------
  js.configs.recommended,

  // ---------- TypeScript ----------
  // 开启类型感知检查：需要读取 tsconfig，能抓到 no-floating-promises 这类
  // 纯语法规则抓不到的真实 bug
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: {
          // 配置文件不在 tsconfig 的 include 范围内，单独放行
          allowDefaultProject: ['*.config.js', 'vite.config.ts'],
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // tsconfig 开了 verbatimModuleSyntax，类型导入必须显式标注 type
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      // 未使用变量：允许 _ 前缀显式表示「故意不用」
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // 这些在 UI 层是噪音：模板字符串里必然是 string，事件处理里常见 void 返回
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        { allowNumber: true, allowBoolean: true },
      ],
    },
  },

  // ---------- 构建 / 工具配置文件 ----------
  // 这些文件不在业务 tsconfig 里，拿不到完整类型；关掉类型感知规则避免误报
  {
    files: ['*.config.{js,ts}', 'vite.config.ts'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: globals.node },
  },

  // ---------- React ----------
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      ...reactHooks.configs['recommended-latest'].rules,
      // 组件文件只导出组件，保证 Fast Refresh 可靠
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },

  // ---------- 测试文件 ----------
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**/*.ts'],
    rules: {
      // 测试里断言非空是常态，类型系统在这里帮不上忙
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
    },
  },

  // ---------- 必须放最后 ----------
  // 关掉与 Prettier 冲突的格式类规则，格式交给 Prettier 独占
  prettier,
);
