import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer'); // 'buffer' or 'schedule'
  const [targetDate, setTargetDate] = useState('2026-04-01');
  
  // Buffer Units
  const [grindUnit, setGrindUnit] = useState('Boxes');
  const [htUnit, setHtUnit] = useState('Rings');

  // Buffer Editable Grid State (Simplified sample channels)
  const initialGrid = [
    { channel: 'CH01', part: 'IR', face_val: '', face_type: '', od_val: '', od_type: '', ht_val: '', ht_type: '' },
    { channel: 'CH01', part: 'OR', face_val: '', face_type: '', od_val: '', od_type: '', ht_val: '', ht_type: '' },
    { channel: '5', part: 'IR', face_val: '', face_type: '', od_val: '', od_type: '', ht_val: '', ht_type: '' },
    { channel: '5', part: 'OR', face_val: '', face_type: '', od_val: '', od_type: '', ht_val: '', ht_type: '' }
  ];
  const [bufferGrid, setBufferGrid] = useState(initialGrid);

  const [scheduleData, setScheduleData] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleGridChange = (index, field, value) => {
    const newGrid = [...bufferGrid];
    newGrid[index][field] = value;
    setBufferGrid(newGrid);
  };

  const saveBufferToBackend = async () => {
    const payload = { date: targetDate, grinding_unit: grindUnit, ht_unit: htUnit, entries: bufferGrid };
    try {
      const res = await fetch(`https://your-backend-url.onrender.com/api/v1/save-buffer`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const json = await res.json();
      alert(json.message);
    } catch (err) { alert("Failed to save buffer."); }
  };

  const downloadBufferCSV = () => {
    let csv = "Channel,Part,Face Buffer,Face Type,OD Buffer,OD Type,HT Buffer,HT Type\n";
    bufferGrid.forEach(row => {
      csv += `${row.channel},${row.part},${row.face_val},${row.face_type},${row.od_val},${row.od_type},${row.ht_val},${row.ht_type}\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = `Buffer_${targetDate}.csv`;
    link.click();
  };

  const generateSchedule = async () => {
    setLoading(true);
    try {
      const res = await fetch(`https://your-backend-url.onrender.com/api/v1/generate-schedule`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_date: targetDate })
      });
      const json = await res.json();
      if (json.status === "success") {
        setScheduleData(json.data);
        setActiveTab('schedule');
      } else { alert(json.message); }
    } catch (err) { alert("Error generating schedule."); }
    setLoading(false);
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div>
          <h1>SHO Planning Matrix</h1>
          <div className="tab-buttons">
            <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Daily Buffer Editor</button>
            <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Master Schedule</button>
          </div>
        </div>
        <div className="action-block">
          <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="calendar-picker"/>
        </div>
      </header>

      {/* TAB 1: BUFFER EDITOR */}
      {activeTab === 'buffer' && (
        <div className="panel">
          <div className="panel-header">
            <h3>Update Shop Floor Buffers</h3>
            <div className="unit-selectors">
              <label>Grind Buffer Unit: <select value={grindUnit} onChange={e=>setGrindUnit(e.target.value)}><option>Boxes</option><option>Days</option></select></label>
              <label>HT Buffer Unit: <select value={htUnit} onChange={e=>setHtUnit(e.target.value)}><option>Rings</option><option>Days</option></select></label>
              <button className="btn-secondary" onClick={downloadBufferCSV}>Download CSV</button>
              <button className="btn-primary" onClick={saveBufferToBackend}>Save Buffer</button>
            </div>
          </div>
          <table className="excel-table">
            <thead>
              <tr><th>Channel</th><th>Part</th><th>Face Buffer</th><th>Type</th><th>OD Buffer</th><th>Type</th><th>HT Buffer</th><th>Type</th></tr>
            </thead>
            <tbody>
              {bufferGrid.map((row, i) => (
                <tr key={i}>
                  <td className="bold">{row.channel}</td><td className="bold">{row.part}</td>
                  <td><input value={row.face_val} onChange={e => handleGridChange(i, 'face_val', e.target.value)} placeholder="0"/></td>
                  <td><input value={row.face_type} onChange={e => handleGridChange(i, 'face_type', e.target.value)} placeholder="e.g. 6310"/></td>
                  <td><input value={row.od_val} onChange={e => handleGridChange(i, 'od_val', e.target.value)} placeholder="0"/></td>
                  <td><input value={row.od_type} onChange={e => handleGridChange(i, 'od_type', e.target.value)} placeholder="e.g. 6310"/></td>
                  <td><input value={row.ht_val} onChange={e => handleGridChange(i, 'ht_val', e.target.value)} placeholder="0"/></td>
                  <td><input value={row.ht_type} onChange={e => handleGridChange(i, 'ht_type', e.target.value)} placeholder="e.g. 6310"/></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="generate-bar">
            <button className="btn-huge" onClick={generateSchedule} disabled={loading}>{loading ? 'Computing...' : 'Generate Schedule >>'}</button>
          </div>
        </div>
      )}

      {/* TAB 2: SCHEDULE */}
      {activeTab === 'schedule' && scheduleData && (
        <div className="shopfloor-grid">
          {/* FACE */}
          <div className="zone-col">
            <h2 className="zone-title face">Face Grinding Matrix</h2>
            {Object.keys(scheduleData.face).map(m => (
              <div key={m} className="machine-card">
                <div className="machine-head">{m}</div>
                <table>
                  <thead><tr><th>Job</th><th>Req Qty</th></tr></thead>
                  <tbody>{scheduleData.face[m].length===0 ? <tr><td colSpan="2">Idle</td></tr> : scheduleData.face[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.qty}</td></tr>)}</tbody>
                </table>
              </div>
            ))}
          </div>

          {/* OD */}
          <div className="zone-col">
            <h2 className="zone-title od">OD Grinding Matrix</h2>
            {Object.keys(scheduleData.od).map(m => (
              <div key={m} className="machine-card">
                <div className="machine-head">{m}</div>
                <table>
                  <thead><tr><th>Job</th><th>Req Qty</th></tr></thead>
                  <tbody>{scheduleData.od[m].length===0 ? <tr><td colSpan="2">Idle</td></tr> : scheduleData.od[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.qty}</td></tr>)}</tbody>
                </table>
              </div>
            ))}
          </div>

          {/* HT */}
          <div className="zone-col">
            <h2 className="zone-title ht">Heat Treatment Furnaces</h2>
            {Object.keys(scheduleData.ht).map(m => (
              <div key={m} className="machine-card">
                <div className="machine-head">{m}</div>
                <table>
                  <thead><tr><th>Job</th><th>Qty</th><th>Window</th></tr></thead>
                  <tbody>{scheduleData.ht[m].length===0 ? <tr><td colSpan="3">Cool</td></tr> : scheduleData.ht[m].map((j, i) => <tr key={i}><td>{j.job}</td><td>{j.qty}</td><td>{j.start} - {j.end}h</td></tr>)}</tbody>
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
