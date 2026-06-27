import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('input');
  const [targetDate, setTargetDate] = useState('');
  const [copyDate, setCopyDate] = useState('');
  const [scheduleData, setScheduleData] = useState(null);

  const channels = ["CH 01", "CH 02", "CH 03", "CH 04", "CH 05"];

  const handleGenerateSchedule = async () => {
    try {
      // Use absolute URL to prevent Vercel 405 Method Not Allowed errors
      const response = await fetch('https://scm-backend-pshv.onrender.com/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_date: targetDate,
          buffers: [] // Populate with actual table state in production
        })
      });
      const data = await response.json();
      setScheduleData(data);
      setActiveTab('master');
    } catch (error) {
      console.error("Error generating schedule:", error);
      alert("Ensure backend is running and URL is correct.");
    }
  };

  return (
    <div className="scheduling-container">
      <header className="header-controls">
        <h2>Production Plan & Tracking</h2>
        <div className="date-controls">
          <div>
            <label>Target Date: </label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </div>
          <div className="copy-setup">
            <label>Copy From: </label>
            <input type="date" value={copyDate} onChange={(e) => setCopyDate(e.target.value)} />
            <button className="btn-secondary">Copy Setup</button>
          </div>
        </div>
      </header>

      <div className="tabs">
        <button className={activeTab === 'input' ? 'active' : ''} onClick={() => setActiveTab('input')}>
          Buffer & Input Setup
        </button>
        <button className={activeTab === 'master' ? 'active' : ''} onClick={() => setActiveTab('master')}>
          Master Schedule View
        </button>
      </div>

      {activeTab === 'input' && (
        <div className="tab-content input-tab">
          <div className="table-actions">
            <select>
              <option value="days">Input Unit: Days Buffer</option>
              <option value="boxes">Input Unit: Boxes</option>
              <option value="rings">Input Unit: Ring Count</option>
            </select>
            <button className="btn-primary" onClick={handleGenerateSchedule}>Run Schedule Engine</button>
          </div>
          <table className="buffer-table">
            <thead>
              <tr>
                <th>PART</th>
                {channels.map(ch => (
                  <th colSpan="2" key={ch}>{ch}</th>
                ))}
              </tr>
              <tr>
                <th>Type</th>
                {channels.map((ch, idx) => (
                  <React.Fragment key={idx}>
                    <th>IR</th><th>OR</th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>OD Buffer</strong></td>
                {channels.map((ch, idx) => (
                  <React.Fragment key={idx}>
                    <td><input type="text" placeholder="e.g. 1.2" /></td>
                    <td><input type="text" placeholder="e.g. 0.3" /></td>
                  </React.Fragment>
                ))}
              </tr>
              <tr>
                <td><strong>Next Type</strong></td>
                 {channels.map((ch, idx) => (
                  <React.Fragment key={idx}>
                    <td><input type="text" placeholder="6328" /></td>
                    <td><input type="text" placeholder="6328" /></td>
                  </React.Fragment>
                ))}
              </tr>
              {/* Additional rows for Face Buffer, HT Buffer follow same pattern */}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'master' && scheduleData && (
        <div className="tab-content master-tab">
          <div className="grinding-schedule">
            <h3>Face & OD Grinding Schedule - {targetDate}</h3>
            <table className="master-table">
              <thead>
                <tr>
                  <th>Machine Name</th>
                  <th>STD BOX</th>
                  <th colSpan="3" className="shift-header shift-1">SHIFT 1 (8AM - 4PM)</th>
                  <th colSpan="3" className="shift-header shift-2">SHIFT 2 (4PM - 12AM)</th>
                  <th colSpan="3" className="shift-header shift-3">SHIFT 3 (12AM - 8AM)</th>
                </tr>
                <tr>
                  <th></th>
                  <th></th>
                  <th className="shift-1">QTY</th><th className="shift-1">JOB</th><th className="shift-1">PRI</th>
                  <th className="shift-2">QTY</th><th className="shift-2">JOB</th><th className="shift-2">PRI</th>
                  <th className="shift-3">QTY</th><th className="shift-3">JOB</th><th className="shift-3">PRI</th>
                </tr>
              </thead>
              <tbody>
                {scheduleData.face_od_grinding.map((row, idx) => (
                  <tr key={idx}>
                    <td><strong>{row.machine}</strong><br/><small>{row.type}</small></td>
                    <td>{row.std_box}</td>
                    
                    <td className="shift-1">{row.shift_1.qty || '-'}</td>
                    <td className="shift-1">{row.shift_1.job}</td>
                    <td className="shift-1"><strong>{row.shift_1.priority}</strong></td>
                    
                    <td className="shift-2">{row.shift_2.qty || '-'}</td>
                    <td className="shift-2">{row.shift_2.job}</td>
                    <td className="shift-2"><strong>{row.shift_2.priority}</strong></td>
                    
                    <td className="shift-3">{row.shift_3.qty || '-'}</td>
                    <td className="shift-3">{row.shift_3.job}</td>
                    <td className="shift-3"><strong>{row.shift_3.priority}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ht-schedule">
            <h3>Heat Treatment Schedule</h3>
            <div className="furnace-grid">
              {scheduleData.heat_treatment.map((furnace, idx) => (
                <div key={idx} className="furnace-card">
                  <h4>{furnace.furnace} <br/><span>({furnace.capacity})</span></h4>
                  <table className="ht-table">
                    <thead>
                      <tr>
                        <th>QTY (Kg)</th><th>JOB</th><th>CH</th>
                      </tr>
                    </thead>
                    <tbody>
                      {furnace.jobs.map((job, jIdx) => (
                        <tr key={jIdx}>
                          <td>{job.qty_kg}</td>
                          <td>{job.job}</td>
                          <td>{job.channel}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;
