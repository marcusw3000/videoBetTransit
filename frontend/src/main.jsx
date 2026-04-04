import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { installEmbedSdk } from './embed'
import './styles.css'

installEmbedSdk()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
