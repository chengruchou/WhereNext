export interface PlaceInfo {
  name: string
  lat: number
  lng: number
  types: string[]
  photoUrl: string | null
}

export interface GowallaPlace {
  raw_poi_id: number
  latitude: number
  longitude: number
  checkins_count_from_events: number | null
  users_count_from_events: number | null
  item_id: number | null
  spot_latitude: number | null
  spot_longitude: number | null
  category_id: number | null
  category_name: string | null
  raw_categories: Array<{
    url: string | null
    name: string | null
  }> | null
  photos_count: number | null
  checkins_count: number | null
  users_count: number | null
  radius_meters: number | null
  highlights_count: number | null
  items_count: number | null
  max_items_count: number | null
  created_at: string | null
}

export interface UserHistory {
  log_id: number
  user_id: number
  visit_time: string | null
  poi_detail: GowallaPlace | null
}
