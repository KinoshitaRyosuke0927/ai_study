// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// React Router v6 の Future Flag Warning をテストログから除外
//（必要なwarnまで消さないよう、対象メッセージのみフィルタ）
const originalWarn = console.warn;
console.warn = (...args) => {
	const firstArg = args[0];
	if (typeof firstArg === 'string' && firstArg.includes('React Router Future Flag Warning')) {
		return;
	}
	originalWarn(...args);
};
