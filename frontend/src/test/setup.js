/**
 * @file Vitest global setup.
 * Extends expect() with jest-dom matchers (toBeInTheDocument, etc.)
 * so component tests can assert against rendered DOM nodes.
 */

import '@testing-library/jest-dom'
