// Small formatting helpers shared by the request and route panels.

// "a museum" -> "museum": phrases come straight from the user's wording.
export function cleanPhrase(phrase: string): string {
  return phrase.trim().replace(/^(a|an|the|some)\s+/i, '')
}

export function formatKm(km: number): string {
  return `${km < 10 ? km.toFixed(2) : km.toFixed(1)} km`
}

// Same great-circle distance as the backend's haversine_km.
export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const rad = Math.PI / 180
  const dLat = (lat2 - lat1) * rad
  const dLng = (lng2 - lng1) * rad
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2
  return 2 * 6371.0088 * Math.asin(Math.sqrt(h))
}
