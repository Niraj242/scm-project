import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('2026-06-25'); 
  const [bufferUnit, setBufferUnit] = useState('Days'); 
  const [loading, setLoading] = useState(false);
  
  const [scheduleData, setScheduleData] = useState(null);
  const [shortageMatrix, setShortageMatrix] = useState([]);
  const [directArrivals, setDirectArrivals] = useState({});
  
  // Overrides State
  const [jobBefore, setJobBefore] = useState('');
  const [jobAfter, setJobAfter] = useState('');

  const computeMasterSchedule = async () => {
    setLoading(true);
    
    const formattedArrivals = Object.entries(directArrivals).map(([key, val]) => ({
      item_code: key, direct_qty: val
    })).filter(x => x.direct_qty > 0);

    const payload = {
      target_date: targetDate,
      buffer_unit: bufferUnit,
      temp_change_furnaces: [],
      overrides: [{ machine_id: "ALL", priority_type: "P1", job_before: jobBefore, job_after: jobAfter }],
      direct_arrivals: formattedArrivals
    };

    try {
      const res = await fetch(`https://your-backend-url.onrender.com/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
        setShortageMatrix(json.shortage_matrix);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO APS Matrix Engine</h1>
          <p className="subtitle">Stock-Capped Scheduling & Box Consumption Logic</p>
        </div>
        <div className="action-block">
          <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="calendar-picker"/>
          <select value={bufferUnit} onChange={(e) => setBufferUnit(e.target.value)} className="calendar-picker">
            <option value="Days">Buffer in Days</option>
            <option value="Boxes">Buffer in Boxes</option>
            <option value="Rings">Buffer in Rings</option>
          </select>
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Processing Sheets...' : 'Generate Plan'}
          </button>
        </div>
      </header>

      <div className="overrides-panel">
        <h3>Planner Sequence Override</h3>
        <div className="form-row">
          <input type="text" placeholder="Job A (e.g. 6310 OR)" value={jobBefore} onChange={e => setJobBefore(e.target.value)} />
          <span> BEFORE </span>
          <input type="text" placeholder="Job B (e.g. 32211 IR)" value={jobAfter} onChange={e => setJobAfter(e.target.value)} />
        </div>
      </div>

      {shortageMatrix.length > 0 && (
        <div className="shortage-panel">
          <h2 className="zone-header">Material Shortage & Planner Override Matrix</h2>
          <table className="zone-data-table full-width">
            <thead>
              <tr>
                <th>Item Description</th>
                <th>Daily Req (Rings)</th>
                <th>Daily Burn (Boxes)</th>
                <th>Physical Stk Store</th>
                <th>Direct to Channel</th>
                <th>SHO Require-TODAY</th>
                <th>SHO Require-TOMORROW</th>
              </tr>
            </thead>
            <tbody>
              {shortageMatrix.map((row, idx) => (
                <tr key={idx}>
                  <td className="bold-txt">{row.item}</td>
                  <td className="center-txt">{row.req_qty}</td>
                  <td className="center-txt text-muted">{row.daily_burn}</td>
                  <td className="center-txt qty-txt">{row.store_avail}</td>
                  <td className="center-txt">
                    <input type="number" placeholder="Enter Qty" className="override-input"
                           onChange={(e) => setDirectArrivals({...directArrivals, [row.item]: parseFloat(e.target.value) || 0})}/>
                  </td>
                  <td className={`center-txt ${row.req_today === 'no material required' ? 'text-muted' : 'prio-tag'}`}>
                    {row.req_today}
                  </td>
                  <td className="center-txt text-muted">0</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {scheduleData && (
         <div className="shopfloor-layout-grid">
           {/* FACE GRINDING */}
           <div className="process-zone-column">
            <h2 className="zone-header face-color">Face Grinding Matrix</h2>
            {Object.keys(scheduleData.face).map((m) => (
              <div key={m} className="machine-card-block">
                <div className="machine-title-strip face-strip">{m}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Component</th><th>Shift Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.face[m].length === 0 ? <tr><td colSpan="3" className="no-load-row">Idle</td></tr> : 
                     scheduleData.face[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.shift}</td><td>{j.priority}</td></tr>)}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

           {/* OD GRINDING */}
           <div className="process-zone-column">
            <h2 className="zone-header od-color">OD Grinding Matrix</h2>
            {Object.keys(scheduleData.od).map((m) => (
              <div key={m} className="machine-card-block">
                <div className="machine-title-strip od-strip">{m}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Component</th><th>Shift Window</th><th>Priority</th></tr></thead>
                  <tbody>
                    {scheduleData.od[m].length === 0 ? <tr><td colSpan="3" className="no-load-row">Idle</td></tr> : 
                     scheduleData.od[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.shift}</td><td>{j.priority}</td></tr>)}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

           {/* HEAT TREATMENT */}
           <div className="process-zone-column">
            <h2 className="zone-header ht-color">Heat Treatment (Furnace)</h2>
            {Object.keys(scheduleData.ht).map((m) => (
              <div key={m} className="machine-card-block">
                <div className="machine-title-strip ht-strip">{m}</div>
                <table className="zone-data-table">
                  <thead><tr><th>Target Type</th><th>Net Qty</th><th>Start</th><th>Exit</th></tr></thead>
                  <tbody>
                    {scheduleData.ht[m].length === 0 ? <tr><td colSpan="4" className="no-load-row">Furnace Cool</td></tr> : 
                     scheduleData.ht[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.qty}</td><td>{j.start}h</td><td>{j.end}h</td></tr>)}
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
