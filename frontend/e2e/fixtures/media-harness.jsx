import React from 'react'
import { createRoot } from 'react-dom/client'
import VideoPlayer from '../../src/components/VideoPlayer.jsx'
import CameraManagementCard from '../../src/components/CameraManagementCard.jsx'

export { React, VideoPlayer, CameraManagementCard }
// Test-only mount utility, not a production fast-refresh boundary.
// eslint-disable-next-line react-refresh/only-export-components
export function mount(Component) {
  createRoot(document.getElementById('root')).render(React.createElement(Component))
}
