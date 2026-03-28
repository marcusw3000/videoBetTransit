import axios from 'axios'
import { MJPEG_HEALTH_URL } from '../config'

const operationsApi = axios.create({
  timeout: 5000,
})

export async function getOperationsHealth() {
  const { data } = await operationsApi.get(MJPEG_HEALTH_URL)
  return data
}
