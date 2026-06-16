import React, { useState, useEffect, useRef } from 'react';
import './TBE.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');
  
  // Drilldown Breakout States
  const [selectedFamily, setSelectedFamily] = useState(null); 
  const [detailData, setDetailData] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // --- CALCULATOR STATES ---
  const [isCalcMode, setIsCalcMode] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedCells, setSelectedCells] = useState({});
  const [selectionTotal, setSelectionTotal] = useState(0);
  const [calcResult, setCalcResult] = useState(null);
  const [currentOperation, setCurrentOperation] = useState(null);

  const timerRef = useRef(null);

  // --- CALCULATOR LOGIC ---
  const handleCellMouseDown = (cellId, cellValue) => {
    if (!isCalcMode) return;
    setIsDragging(true);
    const numVal = parseFloat(String(cellValue).replace(/,/g, '')) || 0;
    setSelectedCells({ [cellId]: numVal });
    setSelectionTotal(numVal);
  };

  const handleCellMouseEnter = (cellId, cellValue) => {
    if (!isCalcMode || !isDragging) return;
    setSelectedCells(prev => {
      if (prev[cellId] !== undefined) return prev; // already selected
      const numVal = parseFloat(String(cellValue).replace(/,/g, '')) || 0;
      const newSelection = { ...prev, [cellId]: numVal };
      const newTotal = Object.values(newSelection).reduce((acc, val) => acc + val, 0);
      setSelectionTotal(newTotal);
      return newSelection;
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  useEffect(() => {
    window.addEventListener('mouseup', handleMouseUp);
    return () => window.removeEventListener('mouseup', handleMouseUp);
  }, []);

  const handleCalcOperation = (op) => {
    if (op === 'C') {
        setCalcResult(null);
        setSelectionTotal(0);
        setSelectedCells({});
        setCurrentOperation(null);
        return;
    }

    if (op === '=') {
        if (currentOperation && calcResult !== null) {
            let res = calcResult;
            if (currentOperation === '+') res += selectionTotal;
            if (currentOperation === '-') res -= selectionTotal;
            if (currentOperation === '*') res *= selectionTotal;
            if (currentOperation === '/') res = selectionTotal !== 0 ? res / selectionTotal : 0;
            
            setCalcResult(res);
            setCurrentOperation(null);
            setSelectionTotal(0);
            setSelectedCells({});
        }
        return;
    }

    // Math operations (+, -, *, /)
    if (calcResult === null) {
        setCalcResult(selectionTotal);
    } else if (currentOperation) {
        let res = calcResult;
        if (currentOperation === '+') res += selectionTotal;
        if (currentOperation === '-') res -= selectionTotal;
        if (currentOperation === '*') res *= selectionTotal;
        if (currentOperation === '/') res = selectionTotal !== 0 ? res / selectionTotal : 0;
        setCalcResult(res);
    }
    setCurrentOperation(op);
    setSelectionTotal(0);
    setSelectedCells({});
  };

  const renderSelectableCell = (id, value, isBold = false) => {
    const isSelected = selectedCells[id] !== undefined;
    return (
      <td 
        className={isCalcMode ? 'select-none' : ''}
        style={{ 
          padding: '12px 15px', 
          textAlign: 'center', 
          borderBottom: '1px solid #e2e8f0',
          fontWeight: isBold ? 'bold' : 'normal',
          cursor: isCalcMode ? 'cell' : 'default',
          transition: 'background-color 0.1s',
          ...(isSelected ? { backgroundColor: '#dbeafe', outline: '2px solid #3b82f6', outlineOffset: '-2px', zIndex: 10 } : {})
        }}
        onMouseDown={() => handleCellMouseDown(id, value)}
        onMouseEnter={() => handleCellMouseEnter(id, value)}
      >
        {Number(value).toLocaleString()}
      </td>
    );
  };


  // --- API LOGIC ---
  useEffect(() => {
    fetchTBEDashboard();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [startDate, endDate]);

  useEffect(() => {
    if (!selectedFamily) {
      setDetailData([]);
      return;
    }

    const fetchVariantDetails = async () => {
      try {
        setDetailLoading(true);
        let url = `${API}/tbe_variant_details?ch=${encodeURIComponent(selectedFamily.ch)}&fam=${encodeURIComponent(selectedFamily.fam)}`;
        if (startDate) url += `&start_date=${startDate}`;
        if (endDate) url += `&end_date=${endDate}`;

        const res = await fetch(url);
        const data = await res.json();
        setDetailData(data.data || []);
      } catch (err) {
        console.error("Variant fetch error", err);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchVariantDetails();
  }, [selectedFamily, startDate, endDate]);

  const fetchTBEDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      
      let url = `${API}/tbe_all_mos`;
      const params = new URLSearchParams();
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      if (params.toString()) url += `?${params.toString()}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error('Network response was not ok');
      const data = await res.json();
      
      if (data.status === 'initializing') {
        setIsInitializing(true);
        if (!timerRef.current) {
          timerRef.current = setTimeout(fetchTBEDashboard, 15000);
        }
      } else {
        setIsInitializing(false);
        setSummaryData(data.data || []);
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch (err) {
      setError('Failed to load TBE matrices. Ensure backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const getStatusClass = (status) => {
    if (!status) return 'status-default';
    if (status.includes('Completed')) return 'status-completed';
    if (status.includes('Channel Only') || status.includes('SHO Logged')) return 'status-channel';
    if (status.includes('Missing')) return 'status-missing';
    if (status.includes('In Process')) return 'status-process';
    return 'status-default';
  };

  const exportToCSV = () => {
    const headers = ['Channel', 'MO Reference', 'Family/Variant', 'Ring Type', 'SHO QTY', 'SHO In', 'TB QTY', 'TB Out', 'CH QTY', 'CH In', 'CH Out', 'Status'];
    const csvRows = [
      headers.join(','),
      ...summaryData.map(r => [
        `"${r.channel_ref}"`,
        `"${r.mo_ref}"`,
        `"${r.product_variant}"`,
        `"${r.ring_type}"`,
        r.sho_qty, `"${r.sho_in}"`,
        r.tb_qty, `"${r.tb_out}"`,
        r.ch_qty, `"${r.ch_in}"`,
        `"${r.ch_out}"`,
        `"${r.status}"`
      ].join(','))
    ].join('\\n');

    const blob = new Blob([csvRows], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `TBE_Export_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  const filteredData = summaryData.filter(row => 
    row.channel_ref.toLowerCase().includes(search.toLowerCase()) ||
    row.product_variant.toLowerCase().includes(search.toLowerCase()) ||
    row.mo_ref.toLowerCase().includes(search.toLowerCase()) ||
    row.status.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="container-fluid p-4 tbe-container" style={{ backgroundColor: '#f8fafc', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
      
      <div className="d-flex flex-wrap justify-content-between align-items-center mb-4 gap-3 bg-white p-3 rounded shadow-sm border">
        
        {/* TITLE & CALCULATOR TOGGLE */}
        <div className="d-flex align-items-center gap-3">
          <h2 className="tbe-title mb-0" style={{ fontWeight: '700', color: '#1e293b' }}>TBE Tracking Log</h2>
          
          <button 
            className={`btn btn-sm ${isCalcMode ? 'btn-primary shadow-inner' : 'btn-outline-secondary'}`}
            onClick={() => {
              setIsCalcMode(!isCalcMode);
              if (isCalcMode) {
                setSelectedCells({});
                setSelectionTotal(0);
                setCalcResult(null);
                setCurrentOperation(null);
              }
            }}
            style={{ fontWeight: '600' }}
            title="Drag over table numbers to calculate"
          >
            🧮 {isCalcMode ? 'Calc Mode: ON' : 'Calc Mode: OFF'}
          </button>

          {isCalcMode && (
            <div className="d-flex align-items-center bg-light border rounded px-2 py-1 shadow-sm gap-2">
                <span className="font-monospace fw-bold px-2 bg-white border rounded" style={{ fontSize: '1rem', minWidth: '100px', textAlign: 'right' }}>
                    {calcResult !== null ? calcResult.toLocaleString() : ''} 
                    {currentOperation ? ` ${currentOperation} ` : ''} 
                    {(selectionTotal !== 0 || calcResult === null) ? selectionTotal.toLocaleString() : ''}
                </span>
                <button className="btn btn-sm btn-light border fw-bold px-2 py-0" onClick={() => handleCalcOperation('+')}>+</button>
                <button className="btn btn-sm btn-light border fw-bold px-2 py-0" onClick={() => handleCalcOperation('-')}>-</button>
                <button className="btn btn-sm btn-light border fw-bold px-2 py-0" onClick={() => handleCalcOperation('*')}>*</button>
                <button className="btn btn-sm btn-light border fw-bold px-2 py-0" onClick={() => handleCalcOperation('/')}>/</button>
                <button className="btn btn-sm btn-primary fw-bold px-2 py-0" onClick={() => handleCalcOperation('=')}>=</button>
                <button className="btn btn-sm btn-danger fw-bold px-2 py-0" onClick={() => handleCalcOperation('C')}>C</button>
            </div>
          )}
        </div>

        {/* CALENDAR & SEARCH FILTERS */}
        <div className="d-flex align-items-center gap-3 flex-wrap">
          <input 
            type="text" 
            placeholder="Search Ch, Fam, MO..." 
            className="form-control" 
            style={{ width: '220px', borderRadius: '8px' }}
            value={search} onChange={(e) => setSearch(e.target.value)} 
          />
          <div className="d-flex align-items-center gap-2">
            <span className="text-muted fw-semibold">Start:</span>
            <input 
              type="date" 
              className="form-control" 
              style={{ borderRadius: '8px' }}
              value={startDate} onChange={(e) => setStartDate(e.target.value)} 
            />
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="text-muted fw-semibold">End:</span>
            <input 
              type="date" 
              className="form-control" 
              style={{ borderRadius: '8px' }}
              value={endDate} onChange={(e) => setEndDate(e.target.value)} 
            />
          </div>
          <button className="btn btn-dark fw-semibold" style={{ borderRadius: '8px' }} onClick={exportToCSV}>Export CSV</button>
        </div>
      </div>

      {isInitializing && (
        <div className="alert alert-warning shadow-sm border-warning rounded">
          <h5 className="mb-1">⚡ Compiling TBE Matrices...</h5>
          <p className="mb-0">The backend is currently building cross-department relationships. This happens once on server restart. Please wait...</p>
        </div>
      )}

      {error && <div className="alert alert-danger shadow-sm">{error}</div>}

      <div className="table-responsive bg-white shadow-sm border rounded" style={{ overflowX: 'auto', minHeight: '500px' }}>
        <table className="table table-hover mb-0" style={{ whiteSpace: 'nowrap', borderCollapse: 'collapse', width: '100%' }}>
          <thead style={{ backgroundColor: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
            <tr>
              <th style={{ padding: '15px', color: '#475569' }}>Channel</th>
              <th style={{ padding: '15px', color: '#475569' }}>MO Reference</th>
              <th style={{ padding: '15px', color: '#475569' }}>Family Variant</th>
              <th style={{ padding: '15px', color: '#475569' }}>Type</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>SHO In</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>SHO QTY</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>TB Out</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>TB QTY</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>CH In/Out</th>
              <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>CH QTY</th>
              <th style={{ padding: '15px', color: '#475569' }}>Status Flow</th>
            </tr>
          </thead>
          <tbody>
            {loading && !isInitializing ? (
              <tr><td colSpan="11" className="text-center py-5 text-muted fw-bold">Syncing Data Streams...</td></tr>
            ) : filteredData.map((row, idx) => (
              <tr 
                key={idx} 
                onClick={() => {
                   if (!isCalcMode) setSelectedFamily({ ch: row.channel_ref, fam: row.product_variant });
                }} 
                style={{ cursor: isCalcMode ? 'default' : 'pointer' }}
                className="tbe-row"
              >
                <td style={{ padding: '12px 15px', fontWeight: '600', color: '#0f172a', borderBottom: '1px solid #e2e8f0' }}>{row.channel_ref}</td>
                <td style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <span className="badge bg-light text-dark border text-wrap text-start" style={{ lineHeight: '1.4' }}>{row.mo_ref || '-'}</span>
                </td>
                <td style={{ padding: '12px 15px', fontWeight: '700', color: '#334155', borderBottom: '1px solid #e2e8f0' }}>{row.product_variant}</td>
                <td style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0' }}>
                  <span className={`badge ${row.ring_type === 'OM' ? 'bg-primary' : row.ring_type === 'IM' ? 'bg-success' : 'bg-secondary'}`}>
                    {row.ring_type}
                  </span>
                </td>
                
                <td style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{row.sho_in}</td>
                {renderSelectableCell(`main-sho-${idx}`, row.sho_qty, true)}

                <td style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{row.tb_out}</td>
                {renderSelectableCell(`main-tb-${idx}`, row.tb_qty, true)}

                <td style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.85rem' }}>
                  <div>{row.ch_in}</div>
                  <div>to</div>
                  <div>{row.ch_out}</div>
                </td>
                {renderSelectableCell(`main-ch-${idx}`, row.ch_qty, true)}
                
                <td style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0' }}>
                  <span className={`status-pill ${getStatusClass(row.status)}`}>{row.status}</span>
                </td>
              </tr>
            ))}
            {filteredData.length === 0 && !loading && !isInitializing && (
              <tr><td colSpan="11" className="text-center py-5 text-muted">No matrices found for current filter criteria.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* --- DRILLDOWN MODAL --- */}
      {selectedFamily && (
        <div className="modal-overlay" onClick={() => setSelectedFamily(null)}>
          <div className="modal-content-custom" onClick={e => e.stopPropagation()}>
            <div className="modal-header-custom bg-dark text-white p-3 d-flex justify-content-between align-items-center rounded-top">
              <h5 className="mb-0">
                Execution Details: <span className="text-warning">{selectedFamily.fam}</span> (Channel: {selectedFamily.ch})
              </h5>
              <button className="btn btn-sm btn-light fw-bold" onClick={() => setSelectedFamily(null)}>Close</button>
            </div>
            <div className="modal-body-custom p-4 bg-white rounded-bottom" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              {detailLoading ? (
                <div className="text-center py-5 text-muted fw-bold">Extracting sequential timeline...</div>
              ) : detailData.length === 0 ? (
                <div className="text-center py-5 text-muted">No specific breakdown found for this variant.</div>
              ) : (
                <div className="table-responsive">
                  <table className="table table-sm table-bordered">
                    <thead className="table-light">
                      <tr>
                        <th style={{ color: '#475569', padding: '10px' }}>MO Block</th>
                        <th style={{ color: '#475569', padding: '10px' }}>Department Node</th>
                        <th style={{ color: '#475569', padding: '10px' }}>Logged Variant</th>
                        <th style={{ textAlign: 'center', color: '#475569', padding: '10px' }}>In Date</th>
                        <th style={{ textAlign: 'center', color: '#475569', padding: '10px' }}>Out Date</th>
                        <th style={{ textAlign: 'center', color: '#475569', padding: '10px', backgroundColor: '#eef2ff' }}>Quantity</th>
                        <th style={{ textAlign: 'center', color: '#475569', padding: '10px' }}>Execution State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.map((vRow, vIdx) => (
                        <tr key={vIdx} className="execution-row">
                          <td className="text-start" style={{ padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.mo_ref}</td>
                          <td className="text-start" style={{ padding: '10px', borderBottom: '1px solid #e2e8f0' }}>
                            <span className={`dept-tag ${vRow.department.toLowerCase().replace(/\s+/g, '-')}`}>
                              {vRow.department}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{ color: '#0f172a', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.variant}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.in_date}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.out_date}</td>
                          
                          {/* Re-use the selectable cell component here! */}
                          {renderSelectableCell(`detail-qty-${vIdx}`, vRow.qty, true)}

                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
                            <span className="execution-status-dot">{vRow.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TBE;
