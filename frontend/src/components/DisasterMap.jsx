
import { useEffect, useRef } from 'react'
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap
} from 'react-leaflet'

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import MarkerClusterGroup from 'react-leaflet-cluster'
import 'react-leaflet-cluster/dist/assets/MarkerCluster.css'
import 'react-leaflet-cluster/dist/assets/MarkerCluster.Default.css'

// Disaster markers: red, orange or green
const createDisasterIcon = (severity) => {
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
      box-shadow:0 0 12px ${color};
    "></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9]
  })
}

// Blue markers for unverified OSM warehouse locations
const warehouseIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:12px;
    height:12px;
    background:#3b82f6;
    border:2px solid white;
    border-radius:50%;
    box-shadow:0 0 6px #3b82f6;
  "></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6]
})

function MapUpdater({ incidents, warehouses, routeResult }) {
  const map = useMap()

  const lastRouteRef = useRef(null)
  const lastMarkersKeyRef = useRef('')

  useEffect(() => {
    const coordinates = routeResult?.geometry?.coordinates

    // Focus on a route only when a NEW route arrives.
    if (
      routeResult?.geometry?.type === 'LineString' &&
      Array.isArray(coordinates) &&
      coordinates.length >= 2
    ) {
      if (lastRouteRef.current === routeResult) {
        return
      }

      const routePositions = coordinates
        .filter(
          point =>
            Array.isArray(point) &&
            point.length >= 2 &&
            Number.isFinite(Number(point[0])) &&
            Number.isFinite(Number(point[1]))
        )
        .map(([longitude, latitude]) => [
          Number(latitude),
          Number(longitude)
        ])

      if (routePositions.length >= 2) {
        lastRouteRef.current = routeResult

        map.fitBounds(routePositions, {
          padding: [60, 60],
          maxZoom: 13,
          animate: true
        })

        return
      }
    }

    // Default map view.
    const positions = [
      ...incidents.map(item => [
        Number(item.latitude),
        Number(item.longitude)
      ]),
      ...warehouses.map(item => [
        Number(item.latitude),
        Number(item.longitude)
      ])
    ]

    // Detect actual marker changes, not unrelated React renders.
    const markersKey = JSON.stringify(positions)

    const routeWasDisplayed = lastRouteRef.current !== null

    if (
      !routeWasDisplayed &&
      markersKey === lastMarkersKeyRef.current
    ) {
      return
    }

    lastRouteRef.current = null
    lastMarkersKeyRef.current = markersKey

    if (positions.length > 0) {
      map.fitBounds(positions, {
        padding: [35, 35],
        maxZoom: 9
      })
    }
  }, [incidents, warehouses, routeResult, map])

  return null
}


function RoutePopupCloser({ routeResult }) {
  const map = useMap()

  useEffect(() => {
    if (
      routeResult?.geometry?.type === 'LineString' &&
      routeResult.geometry.coordinates?.length >= 2
    ) {
      map.closePopup()
    }
  }, [routeResult, map])

  return null
}



function DisasterMap({
  incidents = [],
  discoveredWarehouses = [],
  onAnalyzeIncident,
  aiAnalyses = {},
  analyzingId = null,
  onSelectRouteIncident,
  onSelectRouteWarehouse,
  routeResult = null
}) {


  const validCoordinates = (item) =>
    item.latitude != null &&
    item.longitude != null &&
    Number.isFinite(Number(item.latitude)) &&
    Number.isFinite(Number(item.longitude)) &&
    Math.abs(Number(item.latitude)) <= 90 &&
    Math.abs(Number(item.longitude)) <= 180

  const validIncidents = incidents.filter(validCoordinates)
  const validWarehouses =
    discoveredWarehouses.filter(validCoordinates)

  return (
    <MapContainer
      center={[22.5, 79]}
      zoom={5}
      scrollWheelZoom={true}
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

<MapUpdater
  incidents={validIncidents}
  warehouses={validWarehouses}
  routeResult={routeResult}
/>
  <RoutePopupCloser routeResult={routeResult} />
     {/* Discovered warehouse locations */}
<MarkerClusterGroup
  chunkedLoading
  showCoverageOnHover={false}
  spiderfyOnMaxZoom={true}
>
  {validWarehouses.map(warehouse => (
        <Marker
          key={warehouse.id}
          position={[
            Number(warehouse.latitude),
            Number(warehouse.longitude)
          ]}
          icon={warehouseIcon}
        >
          <Popup>
            <strong>{warehouse.name}</strong>
            <div>Source: OpenStreetMap</div>
            <div>Status: Unverified location</div>
            <div>Inventory: Unknown</div>

<button
  type="button"
  onClick={() => onSelectRouteWarehouse?.(warehouse)}
  style={{
    display: 'block',
    width: '100%',
    marginTop: '12px',
    padding: '10px',
    backgroundColor: '#2563eb',
    color: '#ffffff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer'
  }}
>
  Select for Routing
</button>

            <a
              href={warehouse.source_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              View OpenStreetMap record
            </a>
          </Popup>
        </Marker>
        ))}
</MarkerClusterGroup>


{/* Calculated driving route */}
{routeResult?.geometry?.type === 'LineString' &&
  Array.isArray(routeResult.geometry.coordinates) &&
  routeResult.geometry.coordinates.length >= 2 && (
    <Polyline
      positions={routeResult.geometry.coordinates.map(
        ([longitude, latitude]) => [latitude, longitude]
      )}
      pathOptions={{
        color: '#06b6d4',
        weight: 5,
        opacity: 0.9
      }}
    />
  )}

      {/* Disaster incident locations */}
      {validIncidents.map(incident => (
        <Marker
          key={incident.id}
          position={[
            Number(incident.latitude),
            Number(incident.longitude)
          ]}
          icon={createDisasterIcon(incident.severity)}
        >
          <Popup minWidth={300} maxWidth={420} maxHeight={480}>
  <div
    style={{
      fontSize: '15px',
      lineHeight: '1.7',
      color: '#0f172a',
      padding: '6px'
    }}
  >
              <h3
  style={{
    fontSize: '19px',
    fontWeight: '700',
    lineHeight: '1.4',
    color: '#0f172a',
    marginBottom: '12px',
    paddingBottom: '10px',
    borderBottom: '1px solid #e2e8f0'
  }}
>
                {incident.location || 'Unknown location'}
              </h3>

              <div><strong>Severity:</strong> {incident.severity || 'Unknown'}</div>
              <div><strong>Disaster:</strong> {incident.type || 'Unknown'}</div>
              <div><strong>Reported date:</strong> {incident.time || 'Unavailable'}</div>

              {incident.people != null && (
                <div>
                  <strong>Reported population figure:</strong> {incident.people}
                </div>
              )}

              <div>
                <strong>Coordinates:</strong>{' '}
                {Number(incident.latitude).toFixed(3)},{' '}
                {Number(incident.longitude).toFixed(3)}
              </div>

              <div>
                <strong>Source:</strong> {incident.source || 'GDACS'}
              </div>

              {incident.source_url && (
                <a
                  href={incident.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: 'inline-block', marginTop: '10px' }}
                >
                  View official GDACS report
                </a>
              )}


{/* Compact popup actions */}
<div
  style={{
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
    marginTop: '12px'
  }}
>
  <button
    type="button"
    onClick={() => onSelectRouteIncident?.(incident)}
    style={{
      padding: '10px 6px',
      backgroundColor: '#16a34a',
      color: 'white',
      border: 'none',
      borderRadius: '7px',
      fontSize: '13px',
      fontWeight: '600',
      cursor: 'pointer'
    }}
  >
    Select Route
  </button>

  <button
    type="button"
    onClick={() => onAnalyzeIncident?.(incident.id)}
    disabled={analyzingId !== null}
    style={{
      padding: '10px 6px',
      backgroundColor: '#0891b2',
      color: 'white',
      border: 'none',
      borderRadius: '7px',
      fontSize: '13px',
      fontWeight: '600',
      cursor: analyzingId !== null ? 'wait' : 'pointer',
      opacity: analyzingId !== null ? 0.6 : 1
    }}
  >
    {analyzingId === incident.id
      ? 'Analyzing...'
      : 'AI Analysis'}
  </button>
</div>



              <p style={{ fontSize: '11px', color: '#666', marginTop: '10px' }}>
                Marker coordinates do not represent the full disaster impact area.
              </p>
            </div>
          </Popup>
        </Marker>
      ))}

    </MapContainer>
  )
}

export default DisasterMap
