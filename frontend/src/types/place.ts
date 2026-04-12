export interface PlaceInfo {
  name: string
  lat: number
  lng: number
  types: string[]
  photoUrl: string | null
}

export interface GowallaPlace {
  raw_poi_id: number;
  latitude: number;
  longitude: number;
  checkins_count_from_events: number;
  users_count_from_events: number;
  item_id: number;
  spot_latitude: number;
  spot_longitude: number;
  category_id: number;
  category_name: string;
  raw_categories: Array<{
    url: string;
    name: string;
  }>;
  photos_count: number;
  checkins_count: number;
  users_count: number;
  radius_meters: number;
  highlights_count: number;
  items_count: number;
  max_items_count: number;
  created_at: string;
}