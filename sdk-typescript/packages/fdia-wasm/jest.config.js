module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  testMatch: ["<rootDir>/src/__tests__/**/*.test.ts"],
  collectCoverage: true,
  coverageDirectory: "coverage",
  coverageThreshold: {
    global: { lines: 90, functions: 90, branches: 80 },
  },
};
