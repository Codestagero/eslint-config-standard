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
            "patterns": [".*", "!*.spec.ts"]
        }],
        "@typescript-eslint/explicit-member-accessibility": ["error", {
            "accessibility": "no-public"
        }
        ],
        "arrow-parens": [
            "error",
            "as-needed",
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
        ],
        "semi": ["error", "always"],
        "arrow-body-style": ["error", "as-needed"],
        "eqeqeq": "error",
        "capitalized-comments": ["error"],
        "curly": "error",
        "no-lonely-if": "error",
        "no-redeclare": "error",
        "no-unneeded-ternary": "error",
        "no-var": "error",
        "prefer-const": "error",
        "prefer-exponentiation-operator": "error",
        "yoda": "error",
        "spaced-comment": ["error", "always"]
    }

};