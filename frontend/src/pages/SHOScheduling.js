import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [debugLogs, setDebugLogs] = useState([]);
  const [errorMessage, setErrorMessage] = useState(null);

  const [tempChangeFurnaces, setTempChangeFurnaces] = useState({});
  const [overrides, setOverrides] = useState({ machine_id: 'DDS (544)', priority_type: '', before_job: '', after_job: '' });

  const computeMasterSchedule = async () => {
    setLoading(true); setErrorMessage(null); setScheduleData(null); setDebugLogs([]);

    const constraintPayload = {
      target_date: targetDate,
      temp_change_furnaces: Object.keys(tempChangeFurnaces).filter(k => tempChangeFurnaces[k]),
      overrides: []
    };

    try {
      const res = await fetch(`https://scm-backend-pshv.onrender.com/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(constraintPayload)
      });
      const json = await res.json();
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
        setDebugLogs(json.logs || []);
        if (json.logs && json.logs[json.logs.length - 1].includes("Total jobs ready for scheduling: 0")) {
            setErrorMessage("Zero jobs extracted. Check Debug Logs below to see which sheets failed.");
        }
      } else {
        setErrorMessage(json.detail || "Error connecting to execution engine.");
      }
    } catch (err) {
      setErrorMessage(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO Shop Floor Matrix Engine</h1>
          <p className="subtitle">Reading exact STD/HR Machine Rates & Zeroset Plan execution.</p>
        </div>
        <div className="action-block">
          <label>Plan Date:</label>
          <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Reading Google Sheets...' : 'Compile Master Matrix'}
          </button>
        </div>
      </header>

      {errorMessage && <div className="error-banner"><b>Pipeline Alert:</b> {errorMessage}</div>}

      {/* DEBUG LOGGER */}
      {debugLogs.length > 0 && (
        <div className="debug-panel">
          <h3>Backend Extraction Log (Google Sheets Check)</h3>
          <ul>{debugLogs.map((log, i) => <li key={i}>{log}</li>)}</ul>
        </div>
      )}

      {scheduleData && (
        <div className="shopfloor-layout-grid">
          {/* ZONE 1: FACE GRINDING */}
          <div className="process-zone-column">
            <h2 className="zone-header face-color">Face Grinding Process</h2>
            {Object.keys(scheduleData.face).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip face-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Run</th><th>Shift</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.face[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Idle (No Demand)</td></tr>
                    ) : (
                      scheduleData.face[machine].map((j, idx) => (
                        <tr key={idx}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* ZONE 2: OD GRINDING */}
          <div className="process-zone-column">
            <h2 className="zone-header od-color">OD Grinding Process</h2>
            {Object.keys(scheduleData.od).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip od-strip">{machine}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Bearing Run</th><th>Shift</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.od[machine].length === 0 ? (
                      <tr><td colSpan="3" className="no-load-row">Idle (No Demand)</td></tr>
                    ) : (
                      scheduleData.od[machine].map((j, idx) => (
                        <tr key={idx}><td>{j.job}</td><td className="center-txt bold-txt">{j.shift}</td><td className="center-txt prio-tag">{j.priority}</td></tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* ZONE 3: HEAT TREATMENT */}
          <div className="process-zone-column">
            <h2 className="zone-header ht-color">Heat Treatment Furnaces</h2>
            {Object.keys(scheduleData.ht).map((machine) => (
              <div key={machine} className="machine-card-block">
                <div className="machine-title-strip ht-strip"><span>{machine}</span></div>
                <table className="zone-data-table">
                  <thead><tr><th>Target Type</th><th>Net Qty</th><th>Start</th><th>Exit</th></tr></thead>
                  <tbody>
                    {scheduleData.ht[machine].length === 0 ? (
                      <tr><td colSpan="4" className="no-load-row">Furnace Cool</td></tr>
                    ) : (
                      scheduleData.ht[machine].map((j, idx) => (
                        <tr key={idx}>
                          <td className="bold-txt">{j.job}</td>
                          <td className="center-txt qty-txt">{j.qty.toLocaleString()}</td>
                          <td className="center-txt text-muted">{j.start}h</td>
                          <td className="center-txt bold-txt">{j.end}h</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;
