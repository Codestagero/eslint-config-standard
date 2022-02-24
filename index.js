module.exports = {

    globals: {
    },

    rules: {
        "@typescript-eslint/explicit-function-return-type": [
          "error"
        ],
        "require-jsdoc": ["error", {
          "require": {
            "FunctionDeclaration": true,
            "MethodDefinition": true,
            "ClassDeclaration": false,
            "ArrowFunctionExpression": false,
            "FunctionExpression": false
          }
        }],
        "no-restricted-imports": ["error", {
          "patterns": [".*"]
        }],
        "@typescript-eslint/explicit-member-accessibility": ["error", {
            "accessibility": "no-public"
          }
        ],
        "arrow-parens": [
          "error",
          "as-needed",
          {
            "requireForBlockBody": true
          }
        ],
        "brace-style": [
          "error"
        ],
        "sort-imports": ["error", {
            "ignoreCase": false,
            "ignoreDeclarationSort": false,
            "ignoreMemberSort": false,
            "memberSyntaxSortOrder": ["none", "all", "multiple", "single"],
            "allowSeparatedGroups": false
        }],
        "no-underscore-dangle": "off",
        "quote-props": [
          "error",
          "as-needed"
        ],
        "quotes": [
          "error",
          "single"
        ],
        "no-restricted-imports": ["error", {
          "patterns": [".*"]
        }]
    }

};