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
        }]
    }

};