import React, { useState, useEffect } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [activeTab, setActiveTab] = useState('buffer');
  const [grindUnit, setGrindUnit] = useState('Boxes');
  const [htUnit, setHtUnit] = useState('Rings');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);

  // Replicate exact Downtime Day tracking columns from image
  const [bufferRows, setBufferRows] = useState([]);
  const dgbbChannels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5','Remark'];
  const trbChannels = ['T01','T02','T03','T04','T05','T06','T07','T08','T09','T10'];

  useEffect(() => {
    // Generate dates matching the Excel file (starting 2026-03-01)
    const rows = [];
    for (let i = 1; i <= 31; i++) {
      const dateStr = `2026-03-${i.toString().padStart(2, '0')}`;
      let rowData = { date: dateStr, dgbb: {}, trb: {} };
      dgbbChannels.forEach(ch => rowData.dgbb[ch] = '');
      trbChannels.forEach(ch => rowData.trb[ch] = '');
      rows.push(rowData);
    }
    setBufferRows(rows);
  }, []);

  const handleCellChange = (rowIndex, category, colName, value) => {
    const newRows = [...bufferRows];
    newRows[rowIndex][category][colName] = value;
    setBufferRows(newRows);
  };

  const downloadBufferCSV = () => {
    let csv = ",DGBB - Expected Material Downtime in Day,,,,,,,,,,,,TRB- Expected Material Downtime in Day\n";
    csv += "Date," + dgbbChannels.join(",") + ",,Date," + trbChannels.join(",") + "\n";
    
    bufferRows.forEach(row => {
      const dgbbVals = dgbbChannels.map(ch => row.dgbb[ch] || "").join(",");
      const trbVals = trbChannels.map(ch => row.trb[ch] || "").join(",");
      csv += `${row.date},${dgbbVals},,${row.date},${trbVals}\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = `Data.xlsx_Export.csv`;
    link.click();
  };

  const saveBufferToBackend = async () => {
    try {
      await fetch(`http://localhost:8000/api/v1/save-buffer`, {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ grind_unit: grindUnit, ht_unit: htUnit, data: bufferRows })
      });
      alert("Matrix Saved! Logic will now route skipping Face/OD based on downtime inputs.");
    } catch (err) { console.error("Save failed", err); }
  };

  const generateSchedule = async () => {
    setLoading(true);
    try {
      // Assuming we are scheduling for 01-APR-2026 based on your Excel
      const res = await fetch(`http://localhost:8000/api/v1/generate-schedule`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_date: '2026-04-01' })
      });
      const json = await res.json();
      if (json.status === "success") {
        setScheduleData(json.data);
        setActiveTab('schedule');
      } else { alert("Error generating schedule: " + json.message); }
    } catch (err) { console.error(err); }
    setLoading(false);
  };

  return (
    <div className="sho-wrapper">
      <div className="top-nav">
        <div className="tabs">
          <button className={activeTab === 'buffer' ? 'active' : ''} onClick={() => setActiveTab('buffer')}>1. Data Matrix (Expected Downtime)</button>
          <button className={activeTab === 'schedule' ? 'active' : ''} onClick={() => setActiveTab('schedule')}>2. Generated Schedule (Face/OD/HT)</button>
        </div>
        <div className="actions">
          <label>Grind Buffer Unit: <select value={grindUnit} onChange={e=>setGrindUnit(e.target.value)}><option>Boxes</option><option>Days</option><option>Rings</option></select></label>
          <label>HT Buffer Unit: <select value={htUnit} onChange={e=>setHtUnit(e.target.value)}><option>Rings</option><option>Boxes</option><option>Days</option></select></label>
          <button className="btn-save" onClick={saveBufferToBackend}>Save Configuration</button>
          <button className="btn-run" onClick={generateSchedule} disabled={loading}>{loading ? 'Calculating...' : 'Run Pipeline'}</button>
        </div>
      </div>

      {activeTab === 'buffer' && (
        <div className="excel-container">
          <div className="toolbar">
            <button onClick={downloadBufferCSV}>⬇ Export exactly as CSV</button>
          </div>
          <div className="table-scroll">
            <table className="excel-table buffer-table">
              <thead>
                <tr>
                  <th className="blank-cell"></th>
                  <th colSpan={dgbbChannels.length} className="section-head dgbb-head">DGBB - Expected Material Downtime in Day</th>
                  <th className="blank-cell divider-col"></th>
                  <th className="blank-cell"></th>
                  <th colSpan={trbChannels.length} className="section-head trb-head">TRB- Expected Material Downtime in Day</th>
                </tr>
                <tr>
                  <th className="row-head">Date</th>
                  {dgbbChannels.map(ch => <th key={ch}>{ch}</th>)}
                  <th className="divider-col"></th>
                  <th className="row-head">Date</th>
                  {trbChannels.map(ch => <th key={ch}>{ch}</th>)}
                </tr>
              </thead>
              <tbody>
                {bufferRows.map((row, i) => (
                  <tr key={i}>
                    <td className="date-cell">{row.date}</td>
                    {dgbbChannels.map(ch => (
                      <td key={'dgbb'+ch}><input type="text" value={row.dgbb[ch]} onChange={e => handleCellChange(i, 'dgbb', ch, e.target.value)} /></td>
                    ))}
                    <td className="divider-col"></td>
                    <td className="date-cell">{row.date}</td>
                    {trbChannels.map(ch => (
                      <td key={'trb'+ch}><input type="text" value={row.trb[ch]} onChange={e => handleCellChange(i, 'trb', ch, e.target.value)} /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'schedule' && scheduleData && (
        <div className="excel-container schedule-container">
          <div className="schedule-header-row">
            <h2>Face & OD Grinding Schedule</h2>
            <h3>Date :- 01/04/2026</h3>
          </div>
          <div className="table-scroll">
            <table className="excel-table sched-table">
              <thead>
                <tr>
                  <th colSpan="4" className="section-head face-head">Face Grinding</th>
                  <th className="divider-col"></th>
                  <th colSpan="4" className="section-head od-head">OD Grinding</th>
                  <th className="divider-col"></th>
                  <th colSpan="6" className="section-head ht-head">HEAT TREATMENT &nbsp;&nbsp;&nbsp; DATE - 01/04/2026</th>
                </tr>
                <tr className="sub-head-row">
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift</th><th>Priority</th>
                  <th className="divider-col"></th>
                  <th>Machine / Type</th><th>STD BOX</th><th>Shift</th><th>Priority</th>
                  <th className="divider-col"></th>
                  <th colSpan="3">AICHELIN.(896) (350 kg/h)</th>
                  <th colSpan="3">CASTLINK FURNACE( 1018 ) (250 kg/h)</th>
                </tr>
                <tr className="col-def-row">
                  <th></th><th></th><th>1/2/3</th><th>P1/P2</th>
                  <th className="divider-col"></th>
                  <th></th><th></th><th>1/2/3</th><th>P1/P2</th>
                  <th className="divider-col"></th>
                  <th>Type</th><th>QTY</th><th>Channel</th>
                  <th>Type</th><th>QTY</th><th>Channel</th>
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
                {scheduleData.face["DDS (544)"].map((faceJob, idx) => {
                   const odJob = scheduleData.od["CL -46 Cell 2 ( 0945 + 0839 )"]?.[idx] || {};
                   const ht1 = scheduleData.ht["AICHELIN.(896)"]?.[idx] || {};
                   const ht2 = scheduleData.ht["CASTLINK FURNACE( 1018 )"]?.[idx] || {};
                   
                   // Dynamic rings-to-box conversion for UI display
                   const faceBoxes = faceJob.qty ? Math.round(faceJob.qty / 1300) : ''; 
                   const odBoxes = odJob.qty ? Math.round(odJob.qty / 80) : '';
                   
                   return (
                    <tr key={idx}>
                      <td className="job-cell">{faceJob.job || ''}</td><td className="center">{faceBoxes}</td><td className="center">{faceJob.shift || ''}</td><td className="center">{faceJob.priority || ''}</td>
                      <td className="divider-col"></td>
                      <td className="job-cell">{odJob.job || ''}</td><td className="center">{odBoxes}</td><td className="center">{odJob.shift || ''}</td><td className="center">{odJob.priority || ''}</td>
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
