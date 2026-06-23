import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const computeMasterSchedule = async () => {
    setLoading(true);
    setErrorMessage(null);
    setScheduleData(null);

    try {
      const API = 'https://scm-backend-pshv.onrender.com';
      const res = await fetch(`${API}/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_date: targetDate })
      });

      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        setScheduleData(json.data);
      } else {
        setErrorMessage(json.detail || "Failed to process data sheet rules.");
      }
    } catch (err) {
      setErrorMessage(`Connection Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const renderFaceBlock = (machineName) => {
    const jobs = scheduleData.face[machineName] || [];
    if (jobs.length === 0) return <tr><td colSpan="3" className="empty-cell">-</td></tr>;
    return jobs.map((job, idx) => (
      <tr key={`${machineName}-${idx}`}>
        <td className="job-cell">{job.job}</td>
        <td className="center-cell">{job.shift}</td>
        <td className="center-cell">{job.priority}</td>
      </tr>
    ));
  };

  const renderODBlock = (machineName) => {
    const jobs = scheduleData.od[machineName] || [];
    if (jobs.length === 0) return <tr><td colSpan="3" className="empty-cell">-</td></tr>;
    return jobs.map((job, idx) => (
      <tr key={`${machineName}-${idx}`}>
        <td className="job-cell alt-bg">{job.job}</td>
        <td className="center-cell alt-bg">{job.shift}</td>
        <td className="center-cell alt-bg">{job.priority}</td>
      </tr>
    ));
  };

  const renderHTBlock = (machineName, capacity) => {
    const jobs = scheduleData.ht[machineName] || [];
    if (jobs.length === 0) return <tr><td colSpan="4" className="empty-cell">-</td></tr>;
    return jobs.map((job, idx) => (
      <tr key={`${machineName}-${idx}`}>
        <td className="job-cell ht-bg">{job.job}</td>
        <td className="center-cell ht-bg font-bold">{job.qty}</td>
        <td className="center-cell ht-bg text-muted">{job.channel}</td>
        {idx === 0 ? <td className="center-cell ht-cap" rowSpan={Math.max(1, jobs.length)}>{capacity}</td> : null}
      </tr>
    ));
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>SHO Face / OD Grinding & HT Schedule</h1>
        </div>
        <div className="action-block">
          <label>Target Date:</label>
          <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Compiling Matrices...' : 'Generate Plan'}
          </button>
        </div>
      </header>

      {errorMessage && <div className="error-banner"><b>Backend Error:</b> {errorMessage}</div>}

      {scheduleData && (
        <div className="table-responsive">
          <table className="master-floor-sheet">
            <thead>
              <tr className="main-header-row">
                <th colSpan="3">Face Grinding</th>
                <th colSpan="3">OD Grinding</th>
                <th colSpan="8">HEAT TREATMENT (DATE: {targetDate})</th>
              </tr>
            </thead>
            <tbody>
              
              {/* --- SECTION 1 --- */}
              <tr className="sub-header-row">
                <th className="mach-header">DDS (544)</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">CL -46 Cell 2 ( 0945 + 0839 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">AICHELIN.(896)</th>
                <th>QTY</th><th>CH</th><th>350</th>
                <th className="mach-header">CASTLINK FURNACE( 1018 )</th>
                <th>QTY</th><th>CH</th><th>250</th>
              </tr>
              <tr>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderFaceBlock("DDS (544)")}</tbody></table>
                </td>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderODBlock("CL-46 Cell 2 ( 0945 + 0839 )")}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("AICHELIN.(896)", 350)}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("CASTLINK FURNACE( 1018 )", 250)}</tbody></table>
                </td>
              </tr>

              {/* --- SECTION 2 --- */}
              <tr className="sub-header-row">
                <th className="mach-header">Gardner ( 1016 + USA 1996 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">CL-46 Cell 1 ( 0661 + 1125 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">ROLLER FURNACE ( 148 )</th>
                <th>QTY</th><th>CH</th><th>250</th>
                <th className="mach-header">SIMPLICITY FURNACE(1238)</th>
                <th>QTY</th><th>CH</th><th>180</th>
              </tr>
              <tr>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderFaceBlock("Gardner ( 1016 + USA 1996 )")}</tbody></table>
                </td>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderODBlock("CL-46 Cell 1 ( 0661 + 1125 )")}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("ROLLER FURNACE ( 148 )", 250)}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("SIMPLICITY FURNACE(1238)", 180)}</tbody></table>
                </td>
              </tr>

              {/* --- SECTION 3 --- */}
              <tr className="sub-header-row">
                <th className="mach-header">DDS Cell ( 709 + 1186 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">CL-46 Cell 3 ( 1600 + 1903 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">BIRLEC FURNACE ( 1158 )</th>
                <th>QTY</th><th>CH</th><th>170</th>
                <th className="mach-header">SHOEI FURNACE ( 1062 )</th>
                <th>QTY</th><th>CH</th><th>350</th>
              </tr>
              <tr>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderFaceBlock("DDS Cell ( 709 + 1186 )")}</tbody></table>
                </td>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderODBlock("CL-46 Cell 3 ( 1600 + 1903 )")}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("BIRLEC FURNACE ( 1158 )", 170)}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("SHOEI FURNACE ( 1062 )", 350)}</tbody></table>
                </td>
              </tr>

              {/* --- SECTION 4 --- */}
              <tr className="sub-header-row">
                <th className="mach-header">Gardner (1601)</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">CL-46 Cell 4 ( 170 + 1904 )</th>
                <th>Shift</th><th>Pri.</th>
                <th className="mach-header">AICHELIN UNITHERM ( 2033 )</th>
                <th>QTY</th><th>CH</th><th>250</th>
                <th colSpan="4" className="mach-header bg-dark-blank"></th>
              </tr>
              <tr>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderFaceBlock("Gardner (1601)")}</tbody></table>
                </td>
                <td colSpan="3" className="block-container">
                  <table className="inner-table"><tbody>{renderODBlock("CL-46 Cell 4 ( 170 + 1904 )")}</tbody></table>
                </td>
                <td colSpan="4" className="block-container">
                  <table className="inner-table"><tbody>{renderHTBlock("AICHELIN UNITHERM ( 2033 )", 250)}</tbody></table>
                </td>
                <td colSpan="4" className="block-container bg-dark-blank"></td>
              </tr>

            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default SHOScheduling;
