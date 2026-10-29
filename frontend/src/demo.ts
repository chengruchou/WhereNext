// Demo travelers and example requests for showing the system at a booth.
//
// Each traveler is a reserved user ID with a fixed history of real Gowalla
// places. Loading one replaces that user's visits, so these IDs must not
// belong to anyone else in the database.

export interface DemoTraveler {
  key: string
  label: string
  description: string
  userId: number
  visits: number[] // raw POI IDs, oldest first
  firstVisit: string // ISO time of the first visit; the rest follow two hours apart
  requests: string[] // requests that show this traveler's case well
}

export const DEMO_TRAVELERS: DemoTraveler[] = [
  {
    key: 'austin',
    label: 'Austin coffee regular',
    description: 'Three coffee shops in downtown Austin',
    userId: 900001,
    visits: [18417, 15326, 480992],
    firstVisit: '2010-05-31T17:00:00Z',
    requests: ['A museum, nothing with coffee', 'A beach'],
  },
  {
    key: 'grapevine',
    label: 'Grapevine moviegoer',
    description: 'A mall, dinner, then a movie in Grapevine, TX',
    userId: 900002,
    visits: [15906, 18149, 9419],
    firstVisit: '2010-06-05T15:00:00Z',
    requests: ['I want to see a museum', 'A museum within 2 km on foot'],
  },
]

export const EXAMPLE_REQUESTS = [
  'A museum, nothing with coffee',
  'Somewhere new nearby',
  'A park within 2 km on foot',
]

export function visitTime (traveler: DemoTraveler, index: number): string {
  return new Date(Date.parse(traveler.firstVisit) + index * 2 * 3600 * 1000).toISOString()
}
