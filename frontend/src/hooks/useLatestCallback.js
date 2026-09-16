import { useCallback, useLayoutEffect, useRef } from 'react'

// Native media listeners retain their subscription while using the latest
// props. A parent render must never tear down the HLS decoder.
export default function useLatestCallback(callback) {
  const callbackRef = useRef(callback)
  useLayoutEffect(() => { callbackRef.current = callback }, [callback])
  return useCallback((...args) => callbackRef.current(...args), [])
}
