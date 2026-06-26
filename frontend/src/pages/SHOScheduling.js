import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer');
  const [targetDate, setTargetDate] = useState('2026-04-01');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);

  // Channels Setup
  const dgbbChannels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5'];
  const trbChannels = ['T01','T02','T03','T04','T05','T06','T07','T08','T09','T10'];

  // Buffer Rows matching your exact description
  const bufferFields = [
    { key: 'part', label: 'Part (IR/OR)' },
    { key: 'line_buf', label: 'Line Buffer' },
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
    // Initialize empty grid data
    let dData = {}; let tData = {};
    dgbbChannels.forEach(ch => { dData[ch] = {}; bufferFields.forEach(f => dData[ch][f.key] = ''); });
    trbChannels.forEach(ch => { tData[ch] = {}; bufferFields.forEach(f => tData[ch][f.key] = ''); });
    setDgbbData(dData); setTrbData(tData);
  }, []);

  const handleCellChange = (category, channel, field, value) => {
    if (category === 'dgbb') {
      setDgbbData({ ...dgbbData, [channel]: { ...dgbbData[channel], [field]: value } });
    } else {
      setTrbData({ ...trbData, [channel]: { ...trbData[channel], [field]: value } });
    }
  };

  const calculateTotal = (data, channel) => {
    const f = parseFloat(data[channel]?.face_buf) || 0;
    const o = parseFloat(data[channel]?.od_buf) || 0;
    const h = parseFloat(data[channel]?.ht_buf) || 0;
    const l = parseFloat(data[channel]?.line_buf) || 0;
    const total = f + o + h + l;
    return total > 0 ? total.toFixed(1) : '';
  };

  const saveBufferData = async () => {
    try {
      await fetch(`http://localhost:8000/api/v1/save-buffer`, {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ date: targetDate, dgbb: dgbbData, trb: trbData })
      });
      alert(`Buffer Data for ${targetDate} Saved Successfully!`);
    } catch (err) { alert("Failed to save buffer data."); }
  };

  const generateSchedule = async () => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/generate-schedule`, {
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
    <div className="sho-wrapper">
      <div className="top-nav">
        <div className="tabs">
          <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Daily Buffer Input</button>
          <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Production Schedule</button>
        </div>
        <div className="actions">
          <label className="bold-label">Target Date: </label>
          <input type="date" className="date-picker" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          <button className="btn-save" onClick={saveBufferData}>Save Buffer</button>
          <button className="btn-run" onClick={generateSchedule} disabled={loading}>{loading ? 'Computing...' : 'Generate Plan'}</button>
        </div>
      </div>

      {activeTab === 'buffer' && (
        <div className="excel-container">
          <div className="table-scroll">
            <table className="excel-table buffer-table">
              <thead>
                <tr>
                  <th className="blank-cell"></th>
                  <th colSpan={dgbbChannels.length} className="section-head dgbb-head">DGBB - Daily Buffer (Days)</th>
                  <th className="divider-col"></th>
                  <th colSpan={trbChannels.length} className="section-head trb-head">TRB - Daily Buffer (Days)</th>
                </tr>
                <tr>
                  <th className="row-head">Buffer Section</th>
                  {dgbbChannels.map(ch => <th key={ch} className="col-head">{ch}</th>)}
                  <th className="divider-col"></th>
                  {trbChannels.map(ch => <th key={ch} className="col-head">{ch}</th>)}
                </tr>
              </thead>
              <tbody>
                {bufferFields.map((field) => (
                  <tr key={field.key}>
                    <td className="row-head-title">{field.label}</td>
                    {/* DGBB Columns */}
                    {dgbbChannels.map(ch => (
                      <td key={'d_'+ch} className={field.key.includes('type') ? 'type-cell' : 'val-cell'}>
                        <input type="text" value={dgbbData[ch]?.[field.key] || ''} onChange={e => handleCellChange('dgbb', ch, field.key, e.target.value)} />
                      </td>
                    ))}
                    <td className="divider-col"></td>
                    {/* TRB Columns */}
                    {trbChannels.map(ch => (
                      <td key={'t_'+ch} className={field.key.includes('type') ? 'type-cell' : 'val-cell'}>
                        <input type="text" value={trbData[ch]?.[field.key] || ''} onChange={e => handleCellChange('trb', ch, field.key, e.target.value)} />
                      </td>
                    ))}
                  </tr>
                ))}
                {/* Total Row */}
                <tr className="total-row">
                  <td className="row-head-title">Total Buffer (Days)</td>
                  {dgbbChannels.map(ch => <td key={'dt_'+ch} className="center bold">{calculateTotal(dgbbData, ch)}</td>)}
                  <td className="divider-col"></td>
                  {trbChannels.map(ch => <td key={'tt_'+ch} className="center bold">{calculateTotal(trbData, ch)}</td>)}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SCHEDULE TAB REMAINS EXACTLY THE SAME AS PREVIOUS */}
      {activeTab === 'schedule' && scheduleData && (
        <div className="excel-container schedule-container">
          <div className="schedule-header-row">
            <h2>Face & OD Grinding Schedule</h2>
            <h3>Date :- {targetDate.split('-').reverse().join('/')}</h3>
          </div>
          <div className="table-scroll">
            <table className="excel-table sched-table">
              <thead>
                <tr>
                  <th colSpan="4" className="section-head face-head">Face Grinding</th>
                  <th className="divider-col"></th>
                  <th colSpan="4" className="section-head od-head">OD Grinding</th>
                  <th className="divider-col"></th>
                  <th colSpan="6" className="section-head ht-head">HEAT TREATMENT &nbsp;&nbsp; DATE - {targetDate.split('-').reverse().join('/')}</th>
                </tr>
                <tr className="sub-head-row">
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift</th><th>Priority</th>
                  <th className="divider-col"></th>
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift</th><th>Priority</th>
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
                      <td className="job-cell">{faceJob.job || ''}</td><td className="center">{faceJob.qty || ''}</td><td className="center">{faceJob.shift || ''}</td><td className="center">{faceJob.priority || ''}</td>
                      <td className="divider-col"></td>
                      <td className="job-cell">{odJob.job || ''}</td><td className="center">{odJob.qty || ''}</td><td className="center">{odJob.shift || ''}</td><td className="center">{odJob.priority || ''}</td>
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
