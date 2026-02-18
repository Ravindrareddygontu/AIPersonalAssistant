module.exports = {
    testEnvironment: 'jsdom',
    roots: ['<rootDir>/static/js'],
    testMatch: ['**/__tests__/**/*.test.js'],
    testPathIgnorePatterns: ['/node_modules/', 'setup.js'],
    moduleFileExtensions: ['js'],
    transform: {
        '^.+\\.js$': 'babel-jest'
    },
    moduleNameMapper: {
        '^(\\.{1,2}/.*)\\.js$': '$1'
    },
    setupFilesAfterEnv: ['<rootDir>/static/js/__tests__/setup.js'],
    collectCoverageFrom: [
        'static/js/modules/**/*.js',
        '!static/js/modules/app.js'
    ],
    coverageDirectory: 'coverage',
    verbose: true
};

