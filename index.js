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
            "ignorePatterns": ['*.spec.ts'],
            "patterns": [".*"],

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
        "no-underscore-dangle": "off",
        "quote-props": [
            "error",
            "as-needed"
        ],
        "quotes": [
            "error",
            "single"
        ]
    }

};