import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOScheduling = () => {
  const [targetDate, setTargetDate] = useState('01 APR 2026');
  const [loading, setLoading] = useState(false);
  const [matrixRows, setMatrixRows] = useState([]);
  const [errorMessage, setErrorMessage] = useState(null);

  const computeMasterSchedule = async () => {
    setLoading(true);
    setErrorMessage(null);
    setMatrixRows([]);

    try {
      const API = 'https://scm-backend-pshv.onrender.com';
      const res = await fetch(`${API}/api/v1/generate-schedule`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ target_date: targetDate })
      });

      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        throw new Error("Server did not return valid JSON data.");
      }

      const json = await res.json();
      
      if (res.ok && json.status === "success") {
        // Group the data directly into your shop floor's real machine columns
        buildMasterMatrix(json.data.grinding, json.data.heat_treatment);
      } else {
        setErrorMessage(json.detail || "Failed to process data sheet rules.");
      }
    } catch (err) {
      setErrorMessage(`Connection Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const buildMasterMatrix = (grindingData, htData) => {
    // 1. Group Face Grinding by Machine
    const face_dds544 = grindingData.filter(g => g.machine === "DDS (544)");
    const face_gardner1016 = grindingData.filter(g => g.machine.includes("1016"));
    const face_dds709 = grindingData.filter(g => g.machine.includes("709"));
    const face_gardner1601 = grindingData.filter(g => g.machine.includes("1601"));

    // 2. Group OD Grinding by Machine
    const od_cell2 = grindingData.filter(g => g.machine.includes("Cell 2"));
    const od_cell1 = grindingData.filter(g => g.machine.includes("Cell 1"));
    const od_cell3 = grindingData.filter(g => g.machine.includes("Cell 3"));
    const od_cell4 = grindingData.filter(g => g.machine.includes("Cell 4"));

    // 3. Group Heat Treatment by Furnace Groupings matching your sheet columns
    const ht_aichelin = htData.filter(h => h.furnace.includes("AICHELIN"));
    const ht_castlink = htData.filter(h => h.furnace.includes("CASTLINK"));
    const ht_roller = htData.filter(h => h.furnace.includes("ROLLER"));
    const ht_simplicity = htData.filter(h => h.furnace.includes("SIMPLICITY"));

    // Determine total depth required to render all assets side by side
    const maxLength = Math.max(
      face_dds544.length, face_gardner1016.length, face_dds709.length, face_gardner1601.length,
      od_cell2.length, od_cell1.length, od_cell3.length, od_cell4.length,
      ht_aichelin.length, ht_castlink.length, ht_roller.length, ht_simplicity.length
    );

    const compiledRows = [];
    for (let i = 0; i < maxLength; i++) {
      compiledRows.push({
        face1: face_dds544[i] || null,
        face2: face_gardner1016[i] || null,
        face3: face_dds709[i] || null,
        face4: face_gardner1601[i] || null,
        od1: od_cell2[i] || null,
        od2: od_cell1[i] || null,
        od3: od_cell3[i] || null,
        od4: od_cell4[i] || null,
        ht1: ht_aichelin[i] || null,
        ht2: ht_castlink[i] || null,
        ht3: ht_roller[i] || null,
        ht4: ht_simplicity[i] || null,
      });
    }
    setMatrixRows(compiledRows);
  };

  return (
    <div className="sho-container">
      <header className="sho-header">
        <div className="title-block">
          <h1>Face & OD Grinding / Heat Treatment Master Schedule</h1>
          <p>Live Compilation Matrix from Production & Buffer Worksheets</p>
        </div>
        <div className="action-block">
          <div className="date-input">
            <label>Date Plan:</label>
            <input type="text" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </div>
          <button className="compute-button" onClick={computeMasterSchedule} disabled={loading}>
            {loading ? 'Running Engine...' : 'Generate Shop Floor Plan'}
          </button>
        </div>
      </header>

      {errorMessage && (
        <div className="error-banner">
          <strong>Execution Alert:</strong> {errorMessage}
        </div>
      )}

      <div className="matrix-view">
        {matrixRows.length === 0 ? (
          <div className="panel-placeholder">Awaiting execution. Click 'Generate Shop Floor Plan' above to display matrix.</div>
        ) : (
          <div className="table-responsive">
            <table className="master-floor-sheet">
              <thead>
                {/* Level 1 Headers */}
                <tr className="level-1-header">
                  <th colSpan="4">Face Grinding</th>
                  <th colSpan="4">OD Grinding</th>
                  <th colSpan="8">Heat Treatment Section</th>
                </tr>
                {/* Level 2 Headers: Real Assets */}
                <tr className="level-2-header">
                  <th>DDS (544)</th>
                  <th>Gardner (1016)</th>
                  <th>DDS Cell (709)</th>
                  <th>Gardner (1601)</th>
                  <th>CL-46 Cell 2</th>
                  <th>CL-46 Cell 1</th>
                  <th>CL-46 Cell 3</th>
                  <th>CL-46 Cell 4</th>
                  <th colSpan="2">AICHELIN (896)</th>
                  <th colSpan="2">CASTLINK (1018)</th>
                  <th colSpan="2">ROLLER (148)</th>
                  <th colSpan="2">SIMPLICITY (1238)</th>
                </tr>
                <tr className="level-3-header">
                  <th>Item Run</th><th>Item Run</th><th>Item Run</th><th>Item Run</th>
                  <th>Item Run</th><th>Item Run</th><th>Item Run</th><th>Item Run</th>
                  <th>Type</th><th>Qty</th><th>Type</th><th>Qty</th>
                  <th>Type</th><th>Qty</th><th>Type</th><th>Qty</th>
                </tr>
              </thead>
              <tbody>
                {matrixRows.map((row, index) => (
                  <tr key={index}>
                    {/* Face Columns */}
                    <td className="cell-face">{row.face1 ? `${row.face1.family}---${row.face1.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-face">{row.face2 ? `${row.face2.family}---${row.face2.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-face">{row.face3 ? `${row.face3.family}---${row.face3.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-face">{row.face4 ? `${row.face4.family}---${row.face4.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>

                    {/* OD Columns */}
                    <td className="cell-od">{row.od1 ? `${row.od1.family}---${row.od1.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-od">{row.od2 ? `${row.od2.family}---${row.od2.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-od">{row.od3 ? `${row.od3.family}---${row.od3.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-od">{row.od4 ? `${row.od4.family}---${row.od4.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>

                    {/* HT Columns (Item & Quantity paired side-by-side) */}
                    <td className="cell-ht">{row.ht1 ? `${row.ht1.family}---${row.ht1.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-ht font-weight-bold">{row.ht1 ? row.ht1.quantity.toLocaleString() : ''}</td>
                    
                    <td className="cell-ht-alt">{row.ht2 ? `${row.ht2.family}---${row.ht2.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-ht-alt font-weight-bold">{row.ht2 ? row.ht2.quantity.toLocaleString() : ''}</td>

                    <td className="cell-ht">{row.ht3 ? `${row.ht3.family}---${row.ht3.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-ht font-weight-bold">{row.ht3 ? row.ht3.quantity.toLocaleString() : ''}</td>

                    <td className="cell-ht-alt">{row.ht4 ? `${row.ht4.family}---${row.ht4.channel.includes('CH') ? 'OR' : 'IR'}` : ''}</td>
                    <td className="cell-ht-alt font-weight-bold">{row.ht4 ? row.ht4.quantity.toLocaleString() : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default SHOScheduling;
