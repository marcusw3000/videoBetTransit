import { MJPEG_HEALTH_URL } from '../config'

export async function getWorkerHealth() {
  const response = await fetch(MJPEG_HEALTH_URL, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`Worker health unavailable: ${response.status}`)
  }

  return response.json()
}
