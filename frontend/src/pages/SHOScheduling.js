import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

// Fix for 405 error: Uses env var in production or falls back to standard local FastAPI port
const API_BASE = process.env.REACT_APP_API_URL || 'https://scm-backend-pshv.onrender.com';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer');
  const [targetDate, setTargetDate] = useState('2026-04-01');
  const [dgbbUnit, setDgbbUnit] = useState('Days');
  const [trbUnit, setTrbUnit] = useState('Days');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);

  const dgbbChannels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5'];
  const trbChannels = ['T01','T02','T03','T04','T05','T06','T07','T08','T09','T10'];
  const parts = ['IR', 'OR'];

  // All rows strictly requested by your image setup
  const bufferFields = [
    { key: 'line_buf', label: 'Line Buffer' },
    { key: 'line_type', label: 'Line Type' },
    { key: 'face_buf', label: 'Face Buffer' },
    { key: 'face_type', label: 'Face Type' },
    { key: 'od_buf', label: 'OD Buffer' },
    { key: 'od_type', label: 'OD Type' },
    { key: 'ht_buf', label: 'HT Buffer' },
    { key: 'ht_type', label: 'HT Type' }
  ];

  const [dgbbData, setDgbbData] = useState({});
  const [trbData, setTrbData] = useState({});

  useEffect(() => {
    let dData = {}; let tData = {};
    dgbbChannels.forEach(ch => {
      dData[ch] = { IR: {}, OR: {} };
      bufferFields.forEach(f => { dData[ch].IR[f.key] = ''; dData[ch].OR[f.key] = ''; });
    });
    trbChannels.forEach(ch => {
      tData[ch] = { IR: {}, OR: {} };
      bufferFields.forEach(f => { tData[ch].IR[f.key] = ''; tData[ch].OR[f.key] = ''; });
    });
    setDgbbData(dData); setTrbData(tData);
  }, []);

  const handleCellChange = (category, channel, part, field, value) => {
    if (category === 'dgbb') {
      setDgbbData(prev => ({ ...prev, [channel]: { ...prev[channel], [part]: { ...prev[channel][part], [field]: value } } }));
    } else {
      setTrbData(prev => ({ ...prev, [channel]: { ...prev[channel], [part]: { ...prev[channel][part], [field]: value } } }));
    }
  };

  const calculateTotal = (data, channel, part) => {
    if (!data[channel] || !data[channel][part]) return '';
    const f = parseFloat(data[channel][part].face_buf) || 0;
    const o = parseFloat(data[channel][part].od_buf) || 0;
    const h = parseFloat(data[channel][part].ht_buf) || 0;
    const l = parseFloat(data[channel][part].line_buf) || 0;
    const total = f + o + h + l;
    return total > 0 ? total.toFixed(1) : '';
  };

  const saveBufferData = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/save-buffer`, {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ date: targetDate, dgbb_unit: dgbbUnit, trb_unit: trbUnit, dgbb: dgbbData, trb: trbData })
      });
      const result = await response.json();
      if (result.status === "success") alert(`Successfully saved grid matrices for ${targetDate}`);
    } catch (err) { 
      alert("Network Error: Could not connect to Backend."); 
    }
  };

  const generateSchedule = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/generate-schedule`, {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ target_date: targetDate })
      });
      const json = await res.json();
      if (json.status === "success") { 
        setScheduleData(json.data); 
        setActiveTab('schedule'); 
      } 
      else { alert("Pipeline error: " + json.message); }
    } catch (err) { alert("Network processing timeout."); }
    setLoading(false);
  };

  return (
    <div className="sho-wrapper">
      <div className="top-nav">
        <div className="tabs">
          <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Buffer Matrix Editor</button>
          <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Production Master View</button>
        </div>
        <div className="actions">
          <label className="bold-label">Target Sync Date: </label>
          <input type="date" className="date-picker" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          <div className="unit-controls">
            <label>DGBB Unit: 
              <select value={dgbbUnit} onChange={e => setDgbbUnit(e.target.value)}>
                <option>Days</option><option>No. of Rings</option><option>Boxes</option>
              </select>
            </label>
            <label>TRB Unit: 
              <select value={trbUnit} onChange={e => setTrbUnit(e.target.value)}>
                <option>Days</option><option>No. of Rings</option><option>Boxes</option>
              </select>
            </label>
          </div>
          <button className="btn-save" onClick={saveBufferData}>Save Grid Configurations</button>
          <button className="btn-run" onClick={generateSchedule} disabled={loading}>{loading ? 'Routing...' : 'Run Scheduling Engine'}</button>
        </div>
      </div>

      {activeTab === 'buffer' && (
        <div className="excel-container">
          <div className="table-scroll">
            <table className="excel-table buffer-table">
              <thead>
                <tr>
                  <th className="blank-cell"></th>
                  <th colSpan={dgbbChannels.length * 2} className="section-head dgbb-head">DGBB Table Configuration</th>
                  <th className="divider-col"></th>
                  <th colSpan={trbChannels.length * 2} className="section-head trb-head">TRB Table Configuration</th>
                </tr>
                {/* Channel Names (Spanning 2 columns for IR and OR) */}
                <tr className="channel-row">
                  <th className="row-head-title-main">Line Channels</th>
                  {dgbbChannels.map(ch => <th key={ch} colSpan="2" className="col-head">{ch}</th>)}
                  <th className="divider-col"></th>
                  {trbChannels.map(ch => <th key={ch} colSpan="2" className="col-head">{ch}</th>)}
                </tr>
                {/* IR / OR Sub Headers */}
                <tr className="part-row">
                  <th className="row-head-title-main">Part Type</th>
                  {dgbbChannels.map(ch => parts.map(p => <th key={`${ch}_${p}`} className="sub-col-head">{p}</th>))}
                  <th className="divider-col"></th>
                  {trbChannels.map(ch => parts.map(p => <th key={`${ch}_${p}`} className="sub-col-head">{p}</th>))}
                </tr>
              </thead>
              <tbody>
                {bufferFields.map((field) => (
                  <tr key={field.key}>
                    <td className="row-head-title">{field.label}</td>
                    {dgbbChannels.map(ch => parts.map(p => (
                      <td key={`d_${ch}_${p}`} className={field.key.includes('type') ? 'type-cell' : 'val-cell'}>
                        <input type="text" value={dgbbData[ch]?.[p]?.[field.key] || ''} onChange={e => handleCellChange('dgbb', ch, p, field.key, e.target.value)} />
                      </td>
                    )))}
                    <td className="divider-col"></td>
                    {trbChannels.map(ch => parts.map(p => (
                      <td key={`t_${ch}_${p}`} className={field.key.includes('type') ? 'type-cell' : 'val-cell'}>
                        <input type="text" value={trbData[ch]?.[p]?.[field.key] || ''} onChange={e => handleCellChange('trb', ch, p, field.key, e.target.value)} />
                      </td>
                    )))}
                  </tr>
                ))}
                <tr className="total-row">
                  <td className="row-head-title">Total Compiled Buffer</td>
                  {dgbbChannels.map(ch => parts.map(p => <td key={`dt_${ch}_${p}`} className="center bold">{calculateTotal(dgbbData, ch, p)}</td>))}
                  <td className="divider-col"></td>
                  {trbChannels.map(ch => parts.map(p => <td key={`tt_${ch}_${p}`} className="center bold">{calculateTotal(trbData, ch, p)}</td>))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SCHEDULE TAB - Matches exact layout requirements */}
      {activeTab === 'schedule' && scheduleData && (
        <div className="excel-container schedule-container">
          <div className="schedule-header-row">
            <h2>Face & OD Grinding Live Plan</h2>
            <h3>Target Date Matrix: {targetDate.split('-').reverse().join('/')}</h3>
          </div>
          <div className="table-scroll">
            <table className="excel-table sched-table">
              <thead>
                <tr>
                  <th colSpan="4" className="section-head face-head">Face Grinding Operations</th>
                  <th className="divider-col"></th>
                  <th colSpan="4" className="section-head od-head">OD Grinding Operations</th>
                  <th className="divider-col"></th>
                  <th colSpan="6" className="section-head ht-head">HEAT TREATMENT CAPACITY SEGMENTATION</th>
                </tr>
                <tr className="sub-head-row">
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift Name</th><th>Run Priority</th>
                  <th className="divider-col"></th>
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift Name</th><th>Run Priority</th>
                  <th className="divider-col"></th>
                  <th colSpan="3">AICHELIN.(896) (350 kg/h)</th>
                  <th colSpan="3">CASTLINK FURNACE( 1018 ) (250 kg/h)</th>
                </tr>
              </thead>
              <tbody>
                <tr className="machine-title-row">
                  <td colSpan="4" className="bold-cell">DDS (544)</td>
                  <td className="divider-col"></td>
                  <td colSpan="4" className="bold-cell">CL -46 Cell 2 ( 0945 + 0839 )</td>
                  <td className="divider-col"></td>
                  <td colSpan="6" className="blank-cell"></td>
                </tr>
                {scheduleData.face["DDS (544)"]?.map((faceJob, idx) => {
                   const odJob = scheduleData.od["CL-46 Cell 2 ( 0945 + 0839 )"]?.[idx] || {};
                   const ht1 = scheduleData.ht["AICHELIN.(896)"]?.[idx] || {};
                   const ht2 = scheduleData.ht["CASTLINK FURNACE( 1018 )"]?.[idx] || {};
                   return (
                    <tr key={idx}>
                      <td className="job-cell">{faceJob.job || ''}</td><td className="center bold">{faceJob.qty || ''}</td><td className="center">{faceJob.shift || ''}</td><td className="center">{faceJob.priority || ''}</td>
                      <td className="divider-col"></td>
                      <td className="job-cell">{odJob.job || ''}</td><td className="center bold">{odJob.qty || ''}</td><td className="center">{odJob.shift || ''}</td><td className="center">{odJob.priority || ''}</td>
                      <td className="divider-col"></td>
                      <td className="ht-type">{ht1.job || ''}</td><td className="center">{ht1.qty || ''}</td><td className="center">{ht1.channel || ''}</td>
                      <td className="ht-type">{ht2.job || ''}</td><td className="center">{ht2.qty || ''}</td><td className="center">{ht2.channel || ''}</td>
                    </tr>
                   );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
export default SHOScheduling;
