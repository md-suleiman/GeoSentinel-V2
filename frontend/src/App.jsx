import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";


function MapClickHandler({ onLocationSelect }) {
  useMapEvents({
    click(e) {
      onLocationSelect(
        e.latlng.lat,
        e.latlng.lng
      );
    },
  });

  return null;
}


function MapFocusHandler({ location }) {
  const map = useMap();

  useEffect(() => {
    if (!location) return;

    map.flyTo(
      [location.latitude, location.longitude],
      Math.max(map.getZoom(), 10),
      { duration: 0.8 }
    );
  }, [location, map]);

  return null;
}


/* -------------------------------- */
/* Formatting helpers */
/* -------------------------------- */

function formatDistance(distance) {
  if (distance === null || distance === undefined) {
    return "—";
  }

  if (distance < 1000) {
    return `${Math.round(distance)} m`;
  }

  return `${(distance / 1000).toFixed(2)} km`;
}


function formatRoadType(type) {
  if (!type) {
    return "Unknown";
  }

  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}


function formatSettlementType(type) {
  if (!type) {
    return "Unknown";
  }

  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}


/* -------------------------------- */
/* Authority response priority */
/* -------------------------------- */

function AuthorityPriority({ recentAnalyses, reports, onViewLocation }) {
  const analyses = (recentAnalyses || [])
    .filter((analysis) => analysis?.result?.risk_level && analysis.result.risk_level !== "Not Applicable")
    .map((analysis) => {
      const lat = Number(analysis.latitude);
      const lon = Number(analysis.longitude);
      const verifiedNearby = (reports || [])
        .filter((report) => report.status === "Verified")
        .map((report) => ({
          ...report,
          distanceKm: haversineDistanceKm(
            lat,
            lon,
            Number(report.latitude),
            Number(report.longitude)
          ),
        }))
        .filter((report) => Number.isFinite(report.distanceKm) && report.distanceKm <= 5)
        .sort((a, b) => a.distanceKm - b.distanceKm);

      const infrastructure = analysis.result.infrastructure || {};
      const roadDistance = Number(infrastructure.nearest_road?.distance_m);
      const settlementDistance = Number(infrastructure.nearest_settlement?.distance_m);
      const infrastructureScore =
        (Number.isFinite(roadDistance) && roadDistance <= 2000 ? 8 : Number.isFinite(roadDistance) && roadDistance <= 5000 ? 4 : 0) +
        (Number.isFinite(settlementDistance) && settlementDistance <= 2000 ? 6 : Number.isFinite(settlementDistance) && settlementDistance <= 5000 ? 3 : 0);
      const evidenceScore = Math.min(verifiedNearby.length * 15, 30);
      const priorityScore = Math.min(100, Number(analysis.result.risk_score || 0) + evidenceScore + infrastructureScore);
      const priority = priorityScore >= 70 ? "HIGH" : priorityScore >= 40 ? "MEDIUM" : "ROUTINE";

      return {
        ...analysis,
        lat,
        lon,
        verifiedNearby,
        infrastructure,
        priorityScore,
        priority,
      };
    })
    .sort((a, b) => b.priorityScore - a.priorityScore);

  if (analyses.length === 0) {
    return (
      <section className="admin-card admin-priority-card">
        <div className="admin-section-title">
          <div className="admin-section-icon">🚨</div>
          <div>
            <h2>Response Priority Queue</h2>
            <p>Ranked locations that have been analyzed in the current monitoring session.</p>
          </div>
        </div>
        <div className="admin-empty">
          No analyzed locations yet. Analyze locations on the monitoring map to build the response queue.
        </div>
      </section>
    );
  }

  return (
    <section className="admin-card admin-priority-card">
      <div className="admin-section-title">
        <div className="admin-section-icon">🚨</div>
        <div>
          <h2>Response Priority Queue</h2>
          <p>Ranked using AI risk, verified field evidence, and proximity to potentially exposed infrastructure.</p>
        </div>
      </div>

      <div className="priority-explainer">
        <span><strong>Higher priority</strong> means the location has stronger combined evidence for authority attention.</span>
      </div>

      <div className="priority-list">
        {analyses.map((item, index) => {
          const risk = item.result.risk_level;
          const priorityClass = item.priority.toLowerCase();
          const road = item.infrastructure.nearest_road;
          const settlement = item.infrastructure.nearest_settlement;
          const action = item.priority === "HIGH"
            ? "Field inspection recommended first"
            : item.priority === "MEDIUM"
            ? "Monitor and verify if conditions change"
            : "Routine monitoring";

          return (
            <div className={`priority-item ${priorityClass}`} key={`${item.latitude}-${item.longitude}-${index}`}>
              <div className="priority-rank">#{index + 1}</div>
              <div className="priority-main">
                <div className="priority-topline">
                  <strong>{item.priority} PRIORITY</strong>
                  <span>Priority score {Math.round(item.priorityScore)}/100</span>
                </div>
                <div className="priority-location-row">
                  <div className="priority-location">
                    📍 {item.latitude.toFixed(4)}, {item.longitude.toFixed(4)}
                  </div>
                  <button
                    type="button"
                    className="priority-map-button"
                    onClick={() => onViewLocation(item)}
                  >
                    View on Map
                  </button>
                </div>
                <div className="priority-facts">
                  <span><b>AI risk:</b> {risk} ({item.result.risk_score}/100)</span>
                  <span><b>Verified reports:</b> {item.verifiedNearby.length}</span>
                  {road && <span><b>Nearest road:</b> {road.name || "Unnamed road"} · {formatDistance(road.distance_m)}</span>}
                  {settlement && <span><b>Nearest settlement:</b> {settlement.name || "Unnamed settlement"} · {formatDistance(settlement.distance_m)}</span>}
                </div>
                <div className="priority-action">
                  <span>Recommended action</span>
                  <strong>{action}</strong>
                </div>
                {item.verifiedNearby.length > 0 && (
                  <div className="priority-evidence">
                    ✓ Verified evidence: {item.verifiedNearby.slice(0, 2).map((report) => `#${report.id} ${report.report_type} (${formatDistance(report.distanceKm * 1000)})`).join(" · ")}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function haversineDistanceKm(lat1, lon1, lat2, lon2) {
  if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) {
    return NaN;
  }

  const earthRadiusKm = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;

  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}


function getReportMarkerColor(report) {
  // Green means authority-verified evidence.
  // All unverified field reports remain red.
  if (report.status === "Verified") return "#16a34a";
  return "#dc2626";
}

function formatReportDate(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}


function AdminDashboard({
  reports,
  recentAnalyses,
  onClose,
  onUpdateReportStatus,
  updatingId,
  onViewLocation,
}) {
  const pending = (reports || []).filter((report) => !report.status || report.status === "Pending").length;
  const verified = (reports || []).filter((report) => report.status === "Verified").length;
  const rejected = (reports || []).filter((report) => report.status === "Rejected").length;

  return (
    <div className="admin-overlay">
      <div className="admin-shell">
        <div className="admin-header">
          <div className="admin-header-brand">
            <div className="admin-brand-mark" aria-hidden="true">
              <svg viewBox="0 0 64 52">
                <path d="M4 48 25 8l10 18 9-14 16 36" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="m37 39 6 6 14-17" fill="none" stroke="#39d98a" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="admin-brand-name">Geo<span>Sentinel</span></div>
            <div className="admin-brand-divider" />
            <div className="admin-title-block">
              <div className="admin-title">Authority Dashboard</div>
              <div className="admin-subtitle">Incident verification and response prioritization</div>
            </div>
          </div>
          <button className="admin-close" onClick={onClose}>✕ Close</button>
        </div>

        <div className="admin-body">
          <div className="admin-stats">
            <div className="admin-stat pending-stat">
              <span>Pending Reports</span>
              <strong>{pending}</strong>
              <small>Awaiting verification</small>
            </div>
            <div className="admin-stat verified-stat">
              <span>Verified</span>
              <strong>{verified}</strong>
              <small>Authority-confirmed</small>
            </div>
            <div className="admin-stat rejected-stat">
              <span>Rejected</span>
              <strong>{rejected}</strong>
              <small>Excluded from evidence</small>
            </div>
            <div className="admin-stat risk-stat">
              <span>Analyzed Locations</span>
              <strong>{recentAnalyses.length}</strong>
              <small>Available for prioritization</small>
            </div>
          </div>

          <div className="admin-content-stack">
            <section className="admin-card admin-queue-card">
              <div className="admin-card-heading">
                <div>
                  <h2>Field Evidence Queue</h2>
                  <p>Verify citizen observations before they become authority-confirmed evidence.</p>
                </div>
                <span className="admin-queue-count">{pending} pending</span>
              </div>

              {(reports || []).length === 0 ? (
                <div className="admin-empty">No field reports available.</div>
              ) : (
                <div className="admin-report-list">
                  {(reports || []).map((report) => {
                    const status = report.status || "Pending";
                    const isPending = status === "Pending";
                    const statusClass = status.toLowerCase();
                    return (
                      <div className="admin-report" key={report.id}>
                        <div className="admin-report-title-block">
                          <strong>#{report.id} {report.report_type}</strong>
                        </div>

                        <div className="admin-report-info">
                          <div className="admin-report-coords">
                            📍 {Number(report.latitude).toFixed(4)}, {Number(report.longitude).toFixed(4)}
                          </div>
                          {report.description ? (
                            <p className="admin-report-description">{report.description}</p>
                          ) : (
                            <p className="admin-report-description admin-report-no-description">No description provided.</p>
                          )}
                        </div>

                        <div className="admin-report-actions-column">
                          {isPending && (
                            <div className="admin-report-actions admin-report-actions-inline">
                              <button
                                className="admin-verify"
                                onClick={() => onUpdateReportStatus(report.id, "Verified")}
                                disabled={updatingId === report.id}
                              >
                                {updatingId === report.id ? "Updating..." : "✓ Verify"}
                              </button>
                              <button
                                className="admin-reject"
                                onClick={() => onUpdateReportStatus(report.id, "Rejected")}
                                disabled={updatingId === report.id}
                              >
                                {updatingId === report.id ? "Updating..." : "✕ Reject"}
                              </button>
                            </div>
                          )}
                        </div>

                        <div className="admin-report-media-column">
                          <span className={`admin-report-status ${statusClass}`}>{status}</span>
                          {report.photo_url && (
                            <button
                              type="button"
                              className="admin-view-image"
                              onClick={() => {
                                const photoUrl = report.photo_url.startsWith("http")
                                  ? report.photo_url
                                  : `http://127.0.0.1:8000${report.photo_url}`;
                                window.open(photoUrl, "_blank", "noopener,noreferrer");
                              }}
                            >
                              🖼 View Image
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

            </section>

            <AuthorityPriority
              recentAnalyses={recentAnalyses}
              reports={reports}
              onViewLocation={onViewLocation}
            />
          </div>

          <div className="admin-footer-note">
            <span>🔒</span>
            <div><strong>Authority-only controls</strong><br />Verification actions are restricted to authorized personnel.</div>
          </div>
        </div>
      </div>
    </div>
  );
}


function FieldReportContent({
  latitude,
  longitude,
  reportType,
  setReportType,
  reportDescription,
  setReportDescription,
  reportPhoto,
  setReportPhoto,
  reportSubmitting,
  submitReport,
  reportMessage,
}) {
  return (
    <div
      style={{
        padding: "16px 20px 20px",
      }}
    >
      <div
        style={{
          padding: "12px",
          borderRadius: "10px",
          background: "#f8fafc",
          border: "1px solid #e2e8f0",
        }}
      >
        <div className="coordinate-grid report-coordinate-grid">
          <div className="coordinate-card latitude-card">
            <div className="metric-icon">⌖</div>
            <div>
              <span>Latitude</span>
              <strong>{latitude.toFixed(4)}</strong>
            </div>
          </div>
          <div className="coordinate-card longitude-card">
            <div className="metric-icon">⌖</div>
            <div>
              <span>Longitude</span>
              <strong>{longitude.toFixed(4)}</strong>
            </div>
          </div>
        </div>

        <label>Report type</label>
        <select
          value={reportType}
          onChange={(event) => setReportType(event.target.value)}
          style={{
            width: "100%",
            padding: "10px",
            borderRadius: "8px",
            border: "1px solid #cbd5e1",
            background: "#ffffff",
            color: "#0f172a",
            fontSize: "14px",
            minHeight: "42px",
          }}
        >
          <option value="Landslide observed">Landslide observed</option>
          <option value="Rockfall / debris fall">Rockfall / debris fall</option>
          <option value="Road damage">Road damage</option>
          <option value="Road blockage">Road blockage</option>
          <option value="Cracks / ground movement">Cracks / ground movement</option>
          <option value="Flooding / waterlogging">Flooding / waterlogging</option>
          <option value="Other">Other</option>
        </select>

        <label>Description</label>
        <textarea
          value={reportDescription}
          onChange={(event) => setReportDescription(event.target.value)}
          placeholder="Describe what you observed..."
          rows={5}
          className="report-description-input"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "10px",
            borderRadius: "8px",
            border: "1px solid #cbd5e1",
            resize: "vertical",
            fontFamily: "inherit",
            fontSize: "14px",
          }}
        />

        <label>Photo</label>
        <input
          type="file"
          accept="image/*"
          className="report-photo-input"
          onChange={(event) => setReportPhoto(event.target.files?.[0] || null)}
          style={{ width: "100%", fontSize: "13px" }}
        />

        {reportPhoto && (
          <p style={{ margin: "8px 0 0", fontSize: "12px", color: "#475569" }}>
            Attached: {reportPhoto.name}
          </p>
        )}

        <button onClick={submitReport} disabled={reportSubmitting} style={{ marginTop: "14px" }}>
          {reportSubmitting ? "Submitting..." : "Submit Field Report"}
        </button>

        {reportMessage && (
          <p
            style={{
              margin: "10px 0 0",
              fontSize: "13px",
              color: reportMessage.includes("successfully") ? "#15803d" : "#b91c1c",
              fontWeight: "600",
            }}
          >
            {reportMessage}
          </p>
        )}
      </div>
    </div>
  );
}

function RecentAnalysesContent({ recentAnalyses, onSelect }) {
  if (recentAnalyses.length === 0) {
    return (
      <div className="recent-menu-empty">
        <div className="recent-menu-empty-icon">◷</div>
        <strong>No locations analyzed yet</strong>
        <span>Click a location on the map to create your first analysis.</span>
      </div>
    );
  }

  return (
    <div className="recent-menu-list">
      {recentAnalyses.map((analysis, index) => (
        <button
          key={index}
          type="button"
          className="recent-analysis"
          onClick={() => onSelect(analysis)}
        >
          <div>
            <strong className={`recent-risk-${analysis.result.risk_level.toLowerCase()}`}>
              {analysis.result.risk_level} Risk
            </strong>
            <span>
              {analysis.latitude.toFixed(4)}, {analysis.longitude.toFixed(4)}
            </span>
          </div>
          <strong>{analysis.result.risk_score}/100</strong>
        </button>
      ))}
    </div>
  );
}

function App() {

  const [latitude, setLatitude] = useState(25.6);
  const [longitude, setLongitude] = useState(94.1);
  const [editingCoordinates, setEditingCoordinates] = useState(false);
  const [latitudeInput, setLatitudeInput] = useState("25.6");
  const [longitudeInput, setLongitudeInput] = useState("94.1");

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const [historicalLandslides, setHistoricalLandslides] =
    useState([]);

  const [recentAnalyses, setRecentAnalyses] = useState(() => {
    try {
      const saved = localStorage.getItem("geosentinel_recent_analyses_v1");
      if (!saved) return [];

      const parsed = JSON.parse(saved);

      if (!Array.isArray(parsed)) return [];

      return parsed
        .filter(
          (analysis) =>
            analysis &&
            Number.isFinite(Number(analysis.latitude)) &&
            Number.isFinite(Number(analysis.longitude)) &&
            analysis.result
        )
        .slice(0, 20);
    } catch (error) {
      console.error("Could not restore recent analyses:", error);
      return [];
    }
  });

  const [mapFocusLocation, setMapFocusLocation] = useState(null);
  const [locatingUser, setLocatingUser] = useState(false);

  const [reports, setReports] = useState([]);
  const [reportType, setReportType] = useState("Landslide observed");
  const [reportDescription, setReportDescription] = useState("");
  const [reportPhoto, setReportPhoto] = useState(null);
  const [reportSubmitting, setReportSubmitting] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportUpdatingId, setReportUpdatingId] = useState(null);
  const [adminLoginOpen, setAdminLoginOpen] = useState(false);
  const [adminAuthenticated, setAdminAuthenticated] = useState(() => {
    try {
      return localStorage.getItem("geosentinel_admin_authenticated_v1") === "true";
    } catch {
      return false;
    }
  });
  const [adminDashboardOpen, setAdminDashboardOpen] = useState(() => {
    try {
      return localStorage.getItem("geosentinel_admin_dashboard_open_v1") === "true";
    } catch {
      return false;
    }
  });
  const [adminUsername, setAdminUsername] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [adminLoginError, setAdminLoginError] = useState("");
  const [reportMenuOpen, setReportMenuOpen] = useState(false);
  const [recentMenuOpen, setRecentMenuOpen] = useState(false);


  /* -------------------------------- */
  /* Persist recent analyses locally */
  /* -------------------------------- */

  useEffect(() => {
    try {
      localStorage.setItem(
        "geosentinel_recent_analyses_v1",
        JSON.stringify(recentAnalyses.slice(0, 20))
      );
    } catch (error) {
      console.error("Could not save recent analyses:", error);
    }
  }, [recentAnalyses]);


  /* -------------------------------- */
  /* Persist authority login locally */
  /* -------------------------------- */

  useEffect(() => {
    try {
      localStorage.setItem(
        "geosentinel_admin_authenticated_v1",
        adminAuthenticated ? "true" : "false"
      );
      localStorage.setItem(
        "geosentinel_admin_dashboard_open_v1",
        adminDashboardOpen ? "true" : "false"
      );
    } catch (error) {
      console.error("Could not save admin login state:", error);
    }
  }, [adminAuthenticated, adminDashboardOpen]);


  /* -------------------------------- */
  /* Load historical landslides */
  /* -------------------------------- */

  useEffect(() => {

    fetch("/landslides_ner.csv")
      .then((response) => response.text())
      .then((text) => {

        const lines = text.trim().split("\n");

        const headers = lines[0].split(",");

        const latIndex =
          headers.indexOf("latitude");

        const lonIndex =
          headers.indexOf("longitude");


        const points = lines
          .slice(1)
          .map((line) => {

            const values = line.split(",");

            return {
              latitude: Number(
                values[latIndex]
              ),

              longitude: Number(
                values[lonIndex]
              ),
            };

          })
          .filter(
            (point) =>
              Number.isFinite(
                point.latitude
              ) &&
              Number.isFinite(
                point.longitude
              )
          );


        setHistoricalLandslides(points);

      })
      .catch((error) => {

        console.error(
          "Could not load historical landslides:",
          error
        );

      });

  }, []);


  /* -------------------------------- */
  /* Analyze location */
  /* -------------------------------- */

  async function analyzeLocation(
    lat,
    lon
  ) {

    setLatitude(lat);
    setLongitude(lon);

    setLoading(true);

    try {

      const response = await fetch(
        "http://127.0.0.1:8000/predict",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            latitude: Number(lat),
            longitude: Number(lon),
          }),
        }
      );


      if (!response.ok) {

        throw new Error(
          "Prediction request failed"
        );

      }


      const data =
        await response.json();


      setResult(data);


      /* Only save real risk analyses */

      if (
        data.risk_level !==
        "Not Applicable"
      ) {

        setRecentAnalyses(
          (previous) => [
            {
              id: `${Number(lat).toFixed(6)}-${Number(lon).toFixed(6)}-${Date.now()}`,
              latitude: Number(lat),
              longitude: Number(lon),
              result: data,
              analyzedAt: new Date().toISOString(),
            },

            ...previous,

          ].slice(0, 20)
        );

      }

    } catch (error) {

      console.error(error);

      alert(
        "Could not connect to GeoSentinel API."
      );

    } finally {

      setLoading(false);

    }

  }


  /* -------------------------------- */
  /* Use device location */
  /* -------------------------------- */

  function startCoordinateEdit() {
    setLatitudeInput(String(latitude));
    setLongitudeInput(String(longitude));
    setEditingCoordinates(true);
  }

  function applyCoordinates() {
    const nextLatitude = Number(latitudeInput);
    const nextLongitude = Number(longitudeInput);

    if (!Number.isFinite(nextLatitude) || nextLatitude < -90 || nextLatitude > 90) {
      alert("Latitude must be between -90 and 90.");
      return;
    }

    if (!Number.isFinite(nextLongitude) || nextLongitude < -180 || nextLongitude > 180) {
      alert("Longitude must be between -180 and 180.");
      return;
    }

    setLatitude(nextLatitude);
    setLongitude(nextLongitude);
    setMapFocusLocation({ latitude: nextLatitude, longitude: nextLongitude });
    setEditingCoordinates(false);
    analyzeLocation(nextLatitude, nextLongitude);
  }

  function cancelCoordinateEdit() {
    setEditingCoordinates(false);
    setLatitudeInput(String(latitude));
    setLongitudeInput(String(longitude));
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      alert("Location access is not supported by this browser.");
      return;
    }

    setLocatingUser(true);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;

        setLatitude(lat);
        setLongitude(lon);
        setMapFocusLocation({ latitude: lat, longitude: lon });

        // Automatically run the risk assessment for the user's current location.
        analyzeLocation(lat, lon);
        setLocatingUser(false);
      },
      (error) => {
        console.error("Could not access device location:", error);
        setLocatingUser(false);

        if (error.code === 1) {
          alert("Location permission was denied. Please allow location access in your browser settings.");
        } else {
          alert("Could not determine your current location. Please try again.");
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  }


  /* -------------------------------- */
  /* Field reports */
  /* -------------------------------- */

  async function loadReports() {
    try {
      const response = await fetch("http://127.0.0.1:8000/reports");

      if (!response.ok) {
        throw new Error("Could not load reports");
      }

      const data = await response.json();
      setReports(data.reports || []);
    } catch (error) {
      console.error("Could not load field reports:", error);
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  async function submitReport() {
    if (!reportType) {
      alert("Please select a report type.");
      return;
    }

    setReportSubmitting(true);
    setReportMessage("");

    try {
      let photoData = null;

      if (reportPhoto) {
        if (reportPhoto.size > 5 * 1024 * 1024) {
          throw new Error("Photo must be 5 MB or smaller.");
        }

        photoData = await new Promise((resolve, reject) => {
          const reader = new FileReader();

          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error("Could not read the photo."));

          reader.readAsDataURL(reportPhoto);
        });
      }

      const response = await fetch(
        "http://127.0.0.1:8000/reports",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            latitude: Number(latitude),
            longitude: Number(longitude),
            report_type: reportType,
            description: reportDescription,
            photo_name: reportPhoto ? reportPhoto.name : null,
            photo_data: photoData,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Report submission failed"
        );
      }

      setReportDescription("");
      setReportPhoto(null);
      setReportMessage(
        `Report #${data.report.id} submitted successfully.`
      );

      await loadReports();
    } catch (error) {
      console.error(error);
      setReportMessage(
        error.message || "Could not submit report."
      );
    } finally {
      setReportSubmitting(false);
    }
  }


  /* -------------------------------- */
  /* Authority verification */
  /* -------------------------------- */

  async function updateReportStatus(reportId, status) {
    setReportUpdatingId(reportId);

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/reports/${reportId}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Could not update report status."
        );
      }

      // Reload the canonical report list from the backend after the update.
      // This guarantees the UI uses the same status/data that a refresh would show.
      await loadReports();
    } catch (error) {
      console.error(error);
      alert(error.message || "Could not update report status.");
    } finally {
      setReportUpdatingId(null);
    }
  }


  function handleAdminLogin(event) {
    event.preventDefault();

    // Demo-only client-side gate for the SIH prototype.
    if (adminUsername === "admin" && adminPassword === "admin") {
      setAdminAuthenticated(true);
      setAdminDashboardOpen(true);
      setAdminLoginOpen(false);
      setAdminLoginError("");
      setAdminPassword("");
      return;
    }

    setAdminLoginError("Invalid admin credentials.");
  }


  /* -------------------------------- */
  /* Risk color */
  /* -------------------------------- */

  const riskColor =
    result?.risk_level === "High"
      ? "#dc2626"
      : result?.risk_level === "Medium"
      ? "#f59e0b"
      : result?.risk_level === "Low"
      ? "#16a34a"
      : "#64748b";


  return (

    <div className="app">

      <style>{`
        html, body, #root {
          width: 100%;
          min-width: 100%;
          min-height: 100%;
          margin: 0;
          padding: 0;
        }

        body {
          display: block !important;
          place-items: initial !important;
          overflow: hidden;
        }

        #root {
          max-width: none !important;
        }

        .app {
          width: 100vw !important;
          height: 100vh !important;
          min-height: 100vh !important;
          max-width: none !important;
          margin: 0 !important;
          border-radius: 0 !important;
          overflow: hidden !important;
          display: flex !important;
          flex-direction: column !important;
        }

        .topbar {
          width: 100% !important;
          box-sizing: border-box !important;
          flex-shrink: 0 !important;
        }

        .dashboard {
          width: 100% !important;
          max-width: none !important;
          flex: 1 1 auto !important;
          min-height: 0 !important;
          height: calc(100vh - 76px) !important;
          grid-template-columns: minmax(0, 1fr) 470px !important;
          gap: 0 !important;
        }

        .map-section {
          min-width: 0 !important;
          min-height: 0 !important;
          height: 100% !important;
          border-radius: 0 !important;
        }

        .map {
          width: 100% !important;
          height: 100% !important;
          min-height: 0 !important;
        }

        .sidebar {
          min-width: 0 !important;
          min-height: 0 !important;
          height: 100% !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          box-sizing: border-box !important;
          padding: 18px !important;
        }

        @media (max-width: 900px) {
          body { overflow: auto; }
          .app { height: auto !important; min-height: 100vh !important; overflow: visible !important; }
          .dashboard { height: auto !important; display: block !important; }
          .map-section { height: 55vh !important; min-height: 420px !important; }
          .sidebar { height: auto !important; overflow: visible !important; }
        }
      `}</style>


      {/* -------------------------------- */}
      {/* Header */}
      {/* -------------------------------- */}

      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 64 52" role="img">
              <path d="M4 48 25 8l10 18 9-14 16 36" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="m37 39 6 6 14-17" fill="none" stroke="#39d98a" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="brand-copy">
            <div className="brand-title">Geo<span>Sentinel</span></div>
          </div>
          <div className="brand-divider" />
          <div className="brand-tagline">AI-powered landslide risk monitoring for Northeast India</div>
        </div>

        <nav className="top-nav" aria-label="Primary navigation">
          <a className="active" href="#map">⌂ <span>Home</span></a>
          <button
            type="button"
            className="top-nav-link"
            onClick={() => {
              setReportMenuOpen(true);
              setRecentMenuOpen(false);
            }}
          >
            ▣ <span>Report Here</span>
          </button>
          <button
            type="button"
            className="top-nav-link"
            onClick={() => {
              setRecentMenuOpen(true);
              setReportMenuOpen(false);
            }}
          >
            ◷ <span>Recent Analysis</span>
          </button>
        </nav>

        <div className="top-actions">
          <button
            className="admin-trigger"
            onClick={() => {
              if (adminAuthenticated) {
                setAdminDashboardOpen(true);
              } else {
                setAdminLoginOpen(true);
                setAdminLoginError("");
              }
            }}
            title="Open Authority Dashboard"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="5" y="10" width="14" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth="2" />
              <circle cx="12" cy="15.5" r="1.2" fill="currentColor" />
            </svg>
            {adminAuthenticated ? "Authority Dashboard" : "Admin"}
          </button>
        </div>
      </header>

      {adminLoginOpen && (
        <div className="login-overlay" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAdminLoginOpen(false);
        }}>
          <form className="login-card" onSubmit={handleAdminLogin}>
            <div className="login-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="5" y="10" width="14" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth="2" />
              </svg>
            </div>
            <h2>Authority Login</h2>
            <p>Restricted access to the GeoSentinel authority dashboard</p>

            <label>Username</label>
            <input
              value={adminUsername}
              onChange={(event) => setAdminUsername(event.target.value)}
              autoFocus
              autoComplete="off"
              placeholder="Enter username"
            />

            <label>Password</label>
            <input
              type="text"
              className="demo-password-input"
              value={adminPassword}
              onChange={(event) => setAdminPassword(event.target.value)}
              autoComplete="off"
              spellCheck="false"
              placeholder="Enter password"
            />

            {adminLoginError && <div className="login-error">{adminLoginError}</div>}

            <div className="login-actions">
              <button type="button" className="login-cancel" onClick={() => setAdminLoginOpen(false)}>Cancel</button>
              <button type="submit" className="login-submit">Sign in</button>
            </div>
            <div className="login-note">SIH prototype admin access</div>
          </form>
        </div>
      )}

      {adminAuthenticated && adminDashboardOpen && (
        <AdminDashboard
          reports={reports}
          recentAnalyses={recentAnalyses}
          onClose={() => setAdminDashboardOpen(false)}
          onUpdateReportStatus={updateReportStatus}
          updatingId={reportUpdatingId}
          onViewLocation={(analysis) => {
            setLatitude(analysis.lat);
            setLongitude(analysis.lon);
            setResult(analysis.result);
            setMapFocusLocation({
              latitude: analysis.lat,
              longitude: analysis.lon,
            });
            setAdminDashboardOpen(false);
          }}
        />
      )}


      {reportMenuOpen && (
        <div
          className="menu-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setReportMenuOpen(false);
          }}
        >
          <div className="menu-modal">
            <div className="menu-modal-header">
              <div>
                <h2>Report Here</h2>
                <p>Submit field evidence from the selected map location.</p>
              </div>
              <button type="button" className="menu-modal-close" onClick={() => setReportMenuOpen(false)}>×</button>
            </div>
            <FieldReportContent
              latitude={latitude}
              longitude={longitude}
              reportType={reportType}
              setReportType={setReportType}
              reportDescription={reportDescription}
              setReportDescription={setReportDescription}
              reportPhoto={reportPhoto}
              setReportPhoto={setReportPhoto}
              reportSubmitting={reportSubmitting}
              submitReport={submitReport}
              reportMessage={reportMessage}
            />
          </div>
        </div>
      )}

      {recentMenuOpen && (
        <div
          className="menu-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setRecentMenuOpen(false);
          }}
        >
          <div className="menu-modal recent-menu-modal">
            <div className="menu-modal-header">
              <div>
                <h2>Recent Analysis</h2>
                <p>Your recently analyzed locations, saved on this device.</p>
              </div>
              <button type="button" className="menu-modal-close" onClick={() => setRecentMenuOpen(false)}>×</button>
            </div>
            <RecentAnalysesContent
              recentAnalyses={recentAnalyses}
              onSelect={(analysis) => {
                setLatitude(analysis.latitude);
                setLongitude(analysis.longitude);
                setResult(analysis.result);
                setRecentMenuOpen(false);
              }}
            />
          </div>
        </div>
      )}

      {/* -------------------------------- */}
      {/* Dashboard */}
      {/* -------------------------------- */}

      <main className="dashboard" id="map">


        {/* -------------------------------- */}
        {/* Map */}
        {/* -------------------------------- */}

        <section className="map-section" style={{ position: "relative" }}>

          <MapContainer
            center={[27.5, 93.5]}
            zoom={6}
            className="map"
          >

            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />


            <MapClickHandler
              onLocationSelect={
                analyzeLocation
              }
            />

            <MapFocusHandler location={mapFocusLocation} />


            {/* -------------------------------- */}
            {/* Historical landslides */}
            {/* -------------------------------- */}

            {historicalLandslides.map(
              (point, index) => (

                <CircleMarker
                  key={`historical-${index}`}

                  center={[
                    point.latitude,
                    point.longitude,
                  ]}

                  radius={4}

                  pathOptions={{
                    color: "#7c3aed",
                    fillColor: "#7c3aed",
                    fillOpacity: 0.7,
                    weight: 1,
                  }}
                >

                  <Popup>

                    <strong>
                      Historical Landslide
                    </strong>

                    <br />

                    Recorded location

                  </Popup>

                </CircleMarker>

              )
            )}


            {/* -------------------------------- */}
            {/* Field reports */}
            {/* -------------------------------- */}

            {reports
              .filter(
                (report) =>
                  Number.isFinite(Number(report.latitude)) &&
                  Number.isFinite(Number(report.longitude))
              )
              .map((report) => {
                const markerColor = getReportMarkerColor(report);

                return (
                  <CircleMarker
                    key={`report-${report.id}`}
                    center={[
                      Number(report.latitude),
                      Number(report.longitude),
                    ]}
                    radius={8}
                    pathOptions={{
                      color: "#ffffff",
                      fillColor: markerColor,
                      fillOpacity: 0.95,
                      weight: 2,
                    }}
                  >
                    <Popup>
                      <div style={{ minWidth: "220px", maxWidth: "280px" }}>
                        <strong>Field Report #{report.id}</strong>

                        <div
                          style={{
                            marginTop: "6px",
                            fontWeight: "700",
                            color: markerColor,
                          }}
                        >
                          {report.report_type}
                        </div>

                        <div style={{ marginTop: "5px" }}>
                          Status: <strong>{report.status || "Pending"}</strong>
                        </div>

                        {report.description && (
                          <div style={{ marginTop: "7px" }}>
                            {report.description}
                          </div>
                        )}

                        <div
                          style={{
                            marginTop: "7px",
                            fontSize: "11px",
                            color: "#64748b",
                          }}
                        >
                          {Number(report.latitude).toFixed(4)},{" "}
                          {Number(report.longitude).toFixed(4)}
                          <br />
                          {formatReportDate(
                            report.created_at || report.createdAt
                          )}
                        </div>

                        {report.photo_url && (
                          <img
                            src={
                              report.photo_url.startsWith("http")
                                ? report.photo_url
                                : `http://127.0.0.1:8000${report.photo_url}`
                            }
                            alt={`Field report ${report.id}`}
                            style={{
                              width: "100%",
                              maxHeight: "160px",
                              objectFit: "cover",
                              borderRadius: "8px",
                              marginTop: "9px",
                            }}
                          />
                        )}
                      </div>
                    </Popup>
                  </CircleMarker>
                );
              })}

            {/* -------------------------------- */}
            {/* Current selected location */}
            {/* -------------------------------- */}

            {result && (

              <CircleMarker
                center={[
                  latitude,
                  longitude,
                ]}

                radius={12}

                pathOptions={{
                  color: riskColor,
                  fillColor: riskColor,
                  fillOpacity: 0.75,
                }}
              >

                <Popup>

                  <strong>
                    {result.risk_level}
                  </strong>


                  {result.risk_level !==
                    "Not Applicable" && (

                    <>

                      <br />

                      Risk Score:{" "}
                      {result.risk_score}
                      /100

                    </>

                  )}

                </Popup>

              </CircleMarker>

            )}



          </MapContainer>

          <div className="map-legend" aria-label="Map legend">
            <div className="map-legend-title">Map Legend</div>
            <div className="map-legend-item">
              <span className="map-legend-dot historical-dot" />
              <span>Historical Landslide</span>
            </div>
            <div className="map-legend-item">
              <span className="map-legend-dot report-pending-dot" />
              <span>Field Report (Pending)</span>
            </div>
            <div className="map-legend-item">
              <span className="map-legend-dot report-verified-dot" />
              <span>Field Report (Verified)</span>
            </div>
            <div className="map-legend-item">
              <span className="map-legend-dot report-rejected-dot" />
              <span>Field Report (Rejected)</span>
            </div>
          </div>

        </section>


        {/* -------------------------------- */}
        {/* Sidebar */}
        {/* -------------------------------- */}

        <aside className="sidebar">


          {/* -------------------------------- */}
          {/* Location panel */}
          {/* -------------------------------- */}

          <div className="panel">

            <h2>
              Risk Assessment
            </h2>


            <p className="muted">
              Click anywhere on the map
              to analyze landslide risk.
            </p>


            <div className="coordinate-grid">
              <div className="coordinate-card latitude-card">
                <div className="metric-icon">⌖</div>
                <div className="coordinate-copy">
                  <span>Latitude</span>
                  {editingCoordinates ? (
                    <input
                      className="coordinate-edit-input"
                      type="number"
                      step="0.0001"
                      min="-90"
                      max="90"
                      value={latitudeInput}
                      onChange={(event) => setLatitudeInput(event.target.value)}
                      aria-label="Latitude"
                    />
                  ) : (
                    <button
                      type="button"
                      className="coordinate-value-button"
                      onClick={startCoordinateEdit}
                      title="Click to edit coordinates"
                    >
                      {latitude.toFixed(4)}
                    </button>
                  )}
                </div>
              </div>

              <div className="coordinate-card longitude-card">
                <div className="metric-icon">⌖</div>
                <div className="coordinate-copy">
                  <span>Longitude</span>
                  {editingCoordinates ? (
                    <input
                      className="coordinate-edit-input"
                      type="number"
                      step="0.0001"
                      min="-180"
                      max="180"
                      value={longitudeInput}
                      onChange={(event) => setLongitudeInput(event.target.value)}
                      aria-label="Longitude"
                    />
                  ) : (
                    <button
                      type="button"
                      className="coordinate-value-button"
                      onClick={startCoordinateEdit}
                      title="Click to edit coordinates"
                    >
                      {longitude.toFixed(4)}
                    </button>
                  )}
                </div>
              </div>
            </div>

            {editingCoordinates && (
              <div className="coordinate-edit-actions">
                <span>Enter known coordinates</span>
                <div>
                  <button type="button" className="coordinate-cancel-button" onClick={cancelCoordinateEdit}>
                    Cancel
                  </button>
                  <button type="button" className="coordinate-apply-button" onClick={applyCoordinates}>
                    Apply Location
                  </button>
                </div>
              </div>
            )}


            <div className="location-action-row">
              <button
                type="button"
                className="use-location-button"
                onClick={useMyLocation}
                disabled={loading || locatingUser}
              >
                {locatingUser ? "Finding location..." : "⌖ Use My Location"}
              </button>

              <button
                type="button"
                className="analyze-button"
                onClick={() =>
                  analyzeLocation(
                    latitude,
                    longitude
                  )
                }
                disabled={loading}
              >
                {loading
                  ? "Analyzing..."
                  : "Analyze Selected Location"}
              </button>
            </div>

          </div>


          {/* -------------------------------- */}
          {/* Not Applicable */}
          {/* -------------------------------- */}

          {result &&
            result.risk_level ===
              "Not Applicable" && (

            <div className="panel result-panel">

              <h2>
                Location Assessment
              </h2>


              <div className="risk-badge not-applicable">
                Not Applicable
              </div>


              <div className="not-applicable-message">

                <h3>

                  {result.location_type ===
                  "water"
                    ? "Water body detected"
                    : "Airport area detected"}

                </h3>


                <p>
                  {result.message}
                </p>


                <p className="muted">
                  Landslide risk assessment
                  is not applicable at this
                  location.
                </p>

              </div>


              <div className="explanation">

                <h3>
                  Why?
                </h3>


                <ul>

                  {result.explanation.map(
                    (reason, index) => (

                      <li key={index}>
                        {reason}
                      </li>

                    )
                  )}

                </ul>

              </div>

            </div>

          )}


          {/* -------------------------------- */}
          {/* Normal Risk Result */}
          {/* -------------------------------- */}

          {result &&
            result.risk_level !==
              "Not Applicable" && (

            <>

              <div className="panel result-panel">

                <h2>
                  Risk Result
                </h2>


                <div
                  className={`risk-badge ${result.risk_level.toLowerCase()}`}
                >

                  {result.risk_level}
                  {" "}
                  Risk

                </div>


                <div className="probability">

                  {result.risk_score}

                  <span
                    style={{
                      fontSize: "18px",
                    }}
                  >
                    /100
                  </span>

                </div>


                <p className="muted">
                  Environmental risk score
                </p>


                <div className="environment-grid">
                  <div className="environment-card rainfall-card">
                    <div className="metric-icon">☔</div>
                    <div className="metric-copy">
                      <span>Rainfall</span>
                      <strong>{result.environment.rainfall_mm} <small>mm</small></strong>
                    </div>
                  </div>

                  <div className="environment-card elevation-card">
                    <div className="metric-icon">▲</div>
                    <div className="metric-copy">
                      <span>Elevation</span>
                      <strong>{result.environment.elevation_m} <small>m</small></strong>
                    </div>
                  </div>

                  <div className="environment-card slope-card">
                    <div className="metric-icon">◒</div>
                    <div className="metric-copy">
                      <span>Slope</span>
                      <strong>{result.environment.slope_percent}<small>%</small></strong>
                    </div>
                  </div>
                </div>


                {/* -------------------------------- */}
                {/* Explanation */}
                {/* -------------------------------- */}

                <div className="explanation">

                  <h3>
                    Why this score?
                  </h3>


                  <ul>

                    {result.explanation.map(
                      (reason, index) => (

                        <li key={index}>
                          {reason}
                        </li>

                      )
                    )}

                  </ul>

                </div>


                {/* -------------------------------- */}
                {/* Prediction / Location */}
                {/* -------------------------------- */}

                <div className="detail-grid prediction-grid">
                  <div className="detail-card">
                    <span>Prediction</span>
                    <strong>
                      {result.landslide_prediction === 1
                        ? "Potential landslide"
                        : "Lower risk"}
                    </strong>
                  </div>

                  <div className="detail-card">
                    <span>Location</span>
                    <strong>{latitude.toFixed(3)}, {longitude.toFixed(3)}</strong>
                  </div>
                </div>

              </div>

              {/* ================================================= */}
              {/* INFRASTRUCTURE IMPACT */}
              {/* ================================================= */}

              {result.infrastructure && (

                <div className="panel infrastructure-panel">

                  <h2>
                    Infrastructure Impact
                  </h2>


                  <p className="infrastructure-subtitle">
                    Nearby infrastructure that may
                    be exposed to this risk.
                  </p>


                  {/* -------------------------------- */}
                  {/* Nearest Road */}
                  {/* -------------------------------- */}

                  {result.infrastructure.nearest_road ? (

                    <div className="infrastructure-card">

                      <h3>
                        🛣️ Nearest Road
                      </h3>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Name
                        </span>

                        <span className="infrastructure-value">
                          {result.infrastructure.nearest_road.name ||
                            "Unnamed road"}
                        </span>

                      </div>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Type
                        </span>

                        <span className="infrastructure-value">
                          {formatRoadType(
                            result.infrastructure.nearest_road.type
                          )}
                        </span>

                      </div>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Distance
                        </span>

                        <span className="infrastructure-value">
                          {formatDistance(
                            result.infrastructure.nearest_road.distance_m
                          )}
                        </span>

                      </div>


                      {result.infrastructure
                        .potentially_exposed_roads
                        ?.length > 0 ? (

                        <span className="infrastructure-exposed">
                          ⚠ Potentially exposed
                        </span>

                      ) : (

                        <span className="infrastructure-safe">
                          ✓ No immediate exposure
                        </span>

                      )}

                    </div>

                  ) : (

                    <div className="infrastructure-card">

                      <h3>
                        🛣️ Road Network
                      </h3>

                      <p className="muted">
                        No nearby mapped road found.
                      </p>

                    </div>

                  )}


                  {/* -------------------------------- */}
                  {/* Nearest Settlement */}
                  {/* -------------------------------- */}

                  {result.infrastructure
                    .nearest_settlement ? (

                    <div className="infrastructure-card">

                      <h3>
                        🏘️ Nearest Settlement
                      </h3>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Name
                        </span>

                        <span className="infrastructure-value">
                          {result.infrastructure.nearest_settlement.name ||
                            "Unnamed settlement"}
                        </span>

                      </div>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Type
                        </span>

                        <span className="infrastructure-value">
                          {formatSettlementType(
                            result.infrastructure
                              .nearest_settlement.type
                          )}
                        </span>

                      </div>


                      <div className="infrastructure-row">

                        <span className="infrastructure-label">
                          Distance
                        </span>

                        <span className="infrastructure-value">
                          {formatDistance(
                            result.infrastructure
                              .nearest_settlement
                              .distance_m
                          )}
                        </span>

                      </div>


                      {result.infrastructure
                        .potentially_exposed_settlements
                        ?.length > 0 ? (

                        <span className="infrastructure-exposed">
                          ⚠ Potentially exposed
                        </span>

                      ) : (

                        <span className="infrastructure-safe">
                          ✓ No immediate exposure
                        </span>

                      )}

                    </div>

                  ) : (

                    <div className="infrastructure-card">

                      <h3>
                        🏘️ Settlements
                      </h3>

                      <p className="muted">
                        No nearby mapped settlement found.
                      </p>

                    </div>

                  )}


                  {/* -------------------------------- */}
                  {/* Interpretation */}
                  {/* -------------------------------- */}

                  <div className="infrastructure-note">

                    <strong>
                      ⚠ Interpretation
                    </strong>

                    "Potentially exposed" indicates
                    proximity to a predicted risk area.
                    It does not confirm that a road is
                    blocked or infrastructure is damaged.

                  </div>

                </div>

              )}

              <div className="panel risk-key-panel">
                <div className="sidebar-panel-heading">
                  <div className="sidebar-panel-icon">◉</div>
                  <div>
                    <h3>Risk Levels</h3>
                    <p>AI risk shown on the assessment marker.</p>
                  </div>
                </div>
                <div className="risk-key-grid">
                  <div className="risk-key high-key"><span className="risk-key-dot" />High Risk</div>
                  <div className="risk-key medium-key"><span className="risk-key-dot" />Medium Risk</div>
                  <div className="risk-key low-key"><span className="risk-key-dot" />Low Risk</div>
                </div>
              </div>

            </>

          )}


        </aside>

      </main>

    </div>

  );
}


export default App;