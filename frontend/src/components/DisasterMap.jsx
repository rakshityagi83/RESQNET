
import { Fragment } from 'react'
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Circle,
} from 'react-leaflet'

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const normalLocations = [
  {
    name: 'Sector 15',
    position: [28.4089, 77.3178],
    severity: 'Critical',
    people: 1250,
    color: '#f43f5e',
  },
  {
    name: 'Green Valley',
    position: [28.4150, 77.3050],
    severity: 'High',
    people: 840,
    color: '#f59e0b',
  },
  {
    name: 'Old Town',
    position: [28.4020, 77.3300],
    severity: 'Medium',
    people: 320,
    color: '#eab308',
  },
]

const additionalFloodLocations = [
  {
    name: 'Riverfront Colony',
    position: [28.4200, 77.3250],
    severity: 'Critical',
    people: 1100,
    color: '#f43f5e',
  },
  {
    name: 'East Industrial Area',
    position: [28.3970, 77.3100],
    severity: 'High',
    people: 760,
    color: '#f59e0b',
  },
  {
    name: 'Lakeview Extension',
    position: [28.4250, 77.2950],
    severity: 'High',
    people: 550,
    color: '#f59e0b',
  },
]

const createIcon = (color) =>
  L.divIcon({
    className: '',
    html: `<div style="
      width:18px;
      height:18px;
      background:${color};
      border:3px solid white;
      border-radius:50%;
      box-shadow:0 0 15px ${color};
    "></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })

function DisasterMap({ simulation }) {
  const locations = simulation
    ? [...normalLocations, ...additionalFloodLocations]
    : normalLocations

  return (
    <MapContainer
      center={[28.4089, 77.3178]}
      zoom={14}
      scrollWheelZoom={true}
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {locations.map((location) => (
        <Fragment key={location.name}>
          <Circle
            center={location.position}
            radius={350}
            pathOptions={{
              color: location.color,
              fillColor: location.color,
              fillOpacity: 0.15,
            }}
          />

          <Marker
            position={location.position}
            icon={createIcon(location.color)}
          >
            <Popup>
              <strong>{location.name}</strong>
              <br />
              Severity: {location.severity}
              <br />
              People affected: {location.people}
            </Popup>
          </Marker>
        </Fragment>
      ))}
    </MapContainer>
  )
}

export default DisasterMap
