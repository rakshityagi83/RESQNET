
import { useEffect } from 'react'
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Circle,
  useMap
} from 'react-leaflet'

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const createIcon = (severity) => {
  const color =
    severity === 'Red' ? '#ef4444' :
    severity === 'Orange' ? '#f59e0b' :
    '#22c55e'

  return L.divIcon({
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
}

function MapUpdater({ incidents }) {
  const map = useMap()

  useEffect(() => {
    if (incidents.length > 0) {
      const positions = incidents.map((incident) => [
        incident.latitude,
        incident.longitude
      ])

      map.fitBounds(positions, { padding: [40, 40], maxZoom: 7 })
    }
  }, [incidents, map])

  return null
}

function DisasterMap({ incidents = [] }) {
  const validIncidents = incidents.filter(
    (incident) =>
      Number.isFinite(Number(incident.latitude)) &&
      Number.isFinite(Number(incident.longitude))
  )

  const firstIncident = validIncidents[0]

  const center = firstIncident
    ? [Number(firstIncident.latitude), Number(firstIncident.longitude)]
    : [20, 0]

  return (
    <MapContainer
      center={center}
      zoom={firstIncident ? 5 : 2}
      scrollWheelZoom={true}
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <MapUpdater incidents={validIncidents} />

      {validIncidents.map((incident) => {
        const position = [
          Number(incident.latitude),
          Number(incident.longitude)
        ]

        return (
          <Circle
            key={incident.id}
            center={position}
            radius={50000}
            pathOptions={{
              color: incident.severity === 'Red' ? '#ef4444' :
                incident.severity === 'Orange' ? '#f59e0b' : '#22c55e',
              fillOpacity: 0.12,
            }}
          >
            <Marker
              position={position}
              icon={createIcon(incident.severity)}
            >
              <Popup>
                <strong>{incident.location}</strong>
                <br />
                Alert: {incident.severity}
                <br />
                Type: {incident.type}
                <br />
                Source: {incident.source}
                <br />
                <a href={incident.source_url} target="_blank" rel="noreferrer">
                  GDACS event report
                </a>
              </Popup>
            </Marker>
          </Circle>
        )
      })}
    </MapContainer>
  )
}

export default DisasterMap
