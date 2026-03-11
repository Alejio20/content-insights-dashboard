/**
 * @file Application entry point.
 * Mounts the root React component into the DOM with StrictMode enabled
 * for development-time checks (double-render detection, deprecated API
 * warnings, etc.).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
