const assert = require('node:assert/strict');
const {visibleWindowBounds} = require('../dist/electron/window-state');
const small = {x: 0, y: 0, width: 800, height: 600};
assert.deepEqual(visibleWindowBounds({x: 4000, y: -500, width: 1800, height: 1000}, [small]), small);
const left = {x: -1920, y: 0, width: 1920, height: 1040};
const restored = visibleWindowBounds({x: -1800, y: 100, width: 1000, height: 700}, [small, left]);
assert.deepEqual(restored, {x: -1800, y: 100, width: 1000, height: 700});
assert.deepEqual(visibleWindowBounds({width: NaN, height: Infinity, x: Infinity}, [small]), small);
console.log('PASS: unplugged monitor, small screen, negative monitor coordinates, malformed saved bounds');
