module.exports = {
  testMatch: ['**/src/**/*.test.ts'],
  transform: { '^.+\\.tsx?$': ['ts-jest', { tsconfig: { module: 'CommonJS', moduleResolution: 'Node' } }] },
  testEnvironment: 'node',
};
