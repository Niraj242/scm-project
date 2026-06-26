import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

// Using your exact production URL for backend
const API_BASE = 'https://scm-backend-pshv.onrender.com';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer');
  
  // Dates & Copying
  const [targetDate, setTargetDate] = useState('2026-04-01');
  const [copyDate, setCopyDate] = useState('');
  
  const [dgbbUnit, setDgbbUnit] = useState('Days');
  const [trbUnit, setTrbUnit] = useState('Days');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);

  const dgbbChannels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5'];
  const trbChannels = ['T01','T02','T03','T04','T05','T06','T07','T08','T09','T10'];
  const parts = ['IR', 'OR'];

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

  const initializeEmptyGrid = () => {
    let dData = {}; 
    let tData = {};
    dgbbChannels.forEach(ch => {
      dData[ch] = { IR: {}, OR: {} };
      bufferFields.forEach(f => { dData[ch].IR[f.key] = ''; dData[ch].OR[f.key] = ''; });
    });
    trbChannels.forEach(ch => {
      tData[ch] = { IR: {}, OR: {} };
      bufferFields.forEach(f => { tData[ch].IR[f.key] = ''; tData[ch].OR[f.key] = ''; });
    });
    setDgbbData(dData); 
    setTrbData(tData);
  };

  useEffect(() => {
    const fetchDateData = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/get-buffer?date=${targetDate}`);
        const json = await res.json();
        if (json.status === "success" && json.data) {
          setDgbbData(json.data.dgbb); 
          setTrbData(json.data.trb);
          setDgbbUnit(json.data.dgbb_unit); 
          setTrbUnit(json.data.trb_unit);
        } else {
          initializeEmptyGrid();
        }
      } catch (err) { 
        initializeEmptyGrid(); 
      }
    };
    fetchDateData();
  }, [targetDate]);

  const handleCopy = async () => {
    if(!copyDate) return alert("Please select a date to copy data from.");
    try {
      const res = await fetch(`${API_BASE}/api/v1/get-buffer?date=${copyDate}`);
      const json = await res.json();
      if (json.status === "success" && json.data) {
        setDgbbData(json.data.dgbb); 
        setTrbData(json.data.trb);
        alert(`Successfully copied data from ${copyDate}. Click 'Save Sheet Configurations' to apply it to ${targetDate}.`);
      } else { 
        alert(`No saved data found for ${copyDate}.`); 
      }
    } catch (err) { 
      alert("Failed to fetch data for the selected copy date."); 
    }
  };

  const handleCellChange = (category, channel, part, field, value) => {
    if (category === 'dgbb') {
      setDgbbData(prev => ({ ...prev, [channel]: { ...prev[channel], [part]: { ...prev[channel][part], [field]: value } } }));
    } else {
      setTrbData(prev => ({ ...prev, [channel]: { ...prev[channel], [part]: { ...prev[channel][part], [field]: value } } }));
    }
  };

  const calculateTotal = (data, channel, part) => {
    if (!data[channel] || !data[channel][part]) return '';
    const total = (parseFloat(data[channel][part].face_buf) || 0) + 
                  (parseFloat(data[channel][part].od_buf) || 0) + 
                  (parseFloat(data[channel][part].ht_buf) || 0) + 
                  (parseFloat(data[channel][part].line_buf) || 0);
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
      if (result.status === "success") alert(`Successfully saved configurations for ${targetDate}`);
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
      } else { 
        alert("Pipeline error: " + json.message); 
      }
    } catch (err) { 
      alert("Network processing timeout."); 
    }
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
          <div className="date-group">
            <label>Target Date: <input type="date" value={targetDate} onChange={e => setTargetDate(e.target.value)} /></label>
          </div>
          <div className="date-group copy-group">
            <label>Copy Setup From: <input type="date" value={copyDate} onChange={e => setCopyDate(e.target.value)} /></label>
            <button className="btn-sm" onClick={handleCopy}>Copy Setup</button>
          </div>
          
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

          <button className="btn-save" onClick={saveBufferData}>Save Sheet Configurations</button>
          <button className="btn-run" onClick={generateSchedule} disabled={loading}>{loading ? 'Routing...' : 'Run Pipeline Engine'}</button>
        </div>
      </div>

      {activeTab === 'buffer' && (
        <div className="excel-container">
          <div className="table-scroll">
            <table className="excel-table buffer-table">
              <thead>
                <tr>
                  <th className="avail-title">Available Buffer</th>
                  <th colSpan={dgbbChannels.length * 2} className="section-head dgbb-head">DGBB Table Configuration</th>
                  <th className="divider-col"></th>
                  <th colSpan={trbChannels.length * 2} className="section-head trb-head">TRB Table Configuration</th>
                </tr>
                <tr className="channel-row">
                  <th className="row-head-title-main">Line Channels</th>
                  {dgbbChannels.map(ch => <th key={ch} colSpan="2" className="col-head">{ch}</th>)}
                  <th className="divider-col"></th>
                  {trbChannels.map(ch => <th key={ch} colSpan="2" className="col-head">{ch}</th>)}
                </tr>
                <tr className="part-row">
                  <th className="row-head-title-main">Part (IR/OR)</th>
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
                  <td className="row-head-title">Accumulated Buffer</td>
                  {dgbbChannels.map(ch => parts.map(p => <td key={`dt_${ch}_${p}`} className="center bold">{calculateTotal(dgbbData, ch, p)}</td>))}
                  <td className="divider-col"></td>
                  {trbChannels.map(ch => parts.map(p => <td key={`tt_${ch}_${p}`} className="center bold">{calculateTotal(trbData, ch, p)}</td>))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'schedule' && scheduleData && (
        <div className="excel-container schedule-container">
          <div className="table-scroll">
            <table className="excel-table sched-table">
              <thead>
                <tr className="main-header">
                  <th className="mach-col">Machine Name</th>
                  <th className="type-col">Machine Type</th>
                  <th className="std-col">STD BOX</th>
                  <th className="shift-head s1">SHIFT1 (A) QTY</th>
                  <th className="shift-head s1">SHIFT1 JOB NAME</th>
                  <th className="shift-head s1">PRIORITY</th>
                  <th className="shift-head s2">SHIFT2 (B) QTY</th>
                  <th className="shift-head s2">SHIFT2 JOB NAME</th>
                  <th className="shift-head s2">PRIORITY</th>
                  <th className="shift-head s3">SHIFT3 (C) QTY</th>
                  <th className="shift-head s3">SHIFT3 JOB NAME</th>
                  <th className="shift-head s3">PRIORITY</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(scheduleData).map(([machName, data]) => {
                  const maxRows = Math.max(1, data.shifts["1"].length, data.shifts["2"].length, data.shifts["3"].length);
                  return Array.from({ length: maxRows }).map((_, idx) => {
                    const s1 = data.shifts["1"][idx] || {}; 
                    const s2 = data.shifts["2"][idx] || {}; 
                    const s3 = data.shifts["3"][idx] || {};
                    return (
                      <tr key={`${machName}_${idx}`}>
                        <td className="bold">{idx === 0 ? machName : ''}</td>
                        <td>{idx === 0 ? data.type : ''}</td>
                        <td></td>
                        <td className="center bold s1-cell">{s1.qty || ''}</td>
                        <td className="job-txt s1-cell">{s1.job || ''}</td>
                        <td className="center s1-cell">{s1.priority || ''}</td>
                        <td className="center bold s2-cell">{s2.qty || ''}</td>
                        <td className="job-txt s2-cell">{s2.job || ''}</td>
                        <td className="center s2-cell">{s2.priority || ''}</td>
                        <td className="center bold s3-cell">{s3.qty || ''}</td>
                        <td className="job-txt s3-cell">{s3.job || ''}</td>
                        <td className="center s3-cell">{s3.priority || ''}</td>
                      </tr>
                    );
                  });
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
