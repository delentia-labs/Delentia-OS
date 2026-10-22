import { gateFailure } from './gate';

test('a policy rejection blocks an otherwise high score', () => {
  expect(gateFailure('reject', 1, 0.6, true)).toMatch(/REJECT/);
});
test('explicit fail_on_reject=false still enforces the score floor', () => {
  expect(gateFailure('reject', 0.5, 0.6, false)).toMatch(/minimum/);
  expect(gateFailure('reject', 0.9, 0.6, false)).toBeNull();
});
test('threshold is inclusive', () => {
  expect(gateFailure('approve', 0.6, 0.6, true)).toBeNull();
  expect(gateFailure('approve', 0.599, 0.6, true)).not.toBeNull();
});
test.each([NaN, Infinity, -0.1, 1.1])('invalid API score %s fails closed', score => {
  expect(gateFailure('approve', score, 0.6, true)).not.toBeNull();
});
test.each([NaN, Infinity, -0.1, 1.1])('invalid minimum %s fails closed', minimum => {
  expect(gateFailure('approve', 0.9, minimum, true)).not.toBeNull();
});
