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
  
  const [selectedFamily, setSelectedFamily] = useState(null); 
  const [detailData, setDetailData] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // --- CALCULATOR STATES ---
  const [selectedCells, setSelectedCells] = useState({});
  const [isDragging, setIsDragging] = useState(false);
  const [calcResult, setCalcResult] = useState(null);
  const [currentOperation, setCurrentOperation] = useState(null);

  const timerRef = useRef(null);

  const selectionTotal = Object.values(selectedCells).reduce((sum, val) => sum + val, 0);

  const handleMouseDown = (e, cellId, value) => {
    if (e.button !== 0) return;
    const numVal = parseFloat(String(value).replace(/,/g, '')) || 0;
    
    if (e.ctrlKey || e.metaKey) {
      setSelectedCells(prev => {
        const newSel = { ...prev };
        if (newSel[cellId] !== undefined) delete newSel[cellId];
        else newSel[cellId] = numVal;
        return newSel;
      });
    } else {
      setSelectedCells({ [cellId]: numVal });
    }
    setIsDragging(true);
  };

  const handleMouseEnter = (e, cellId, value) => {
    if (!isDragging) return;
    const numVal = parseFloat(String(value).replace(/,/g, '')) || 0;
    setSelectedCells(prev => ({ ...prev, [cellId]: numVal }));
  };

  useEffect(() => {
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener('mouseup', handleMouseUp);
    return () => window.removeEventListener('mouseup', handleMouseUp);
  }, []);

  const handleCalcOp = (op) => {
    if (op === 'C') {
      setCalcResult(null);
      setCurrentOperation(null);
      setSelectedCells({});
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
        setSelectedCells({});
      }
      return;
    }

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
    setSelectedCells({});
  };

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
        if (!res.ok) throw new Error("Could not retrieve variant sequential logs.");
        const json = await res.json();
        setDetailData(json.data || []);
      } catch (err) {
        console.error(err.message);
      } finally {
        setDetailLoading(false);
      }
    };
    fetchVariantDetails();
  }, [selectedFamily, startDate, endDate]);

  const fetchTBEDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');

      let url = `${API}/tbe_all_mos`;
      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) url += `?${queryParams.join('&')}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error(`Server returned status code: ${res.status}`);
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setSummaryData([]);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(fetchTBEDashboard, 4000);
      } else {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      }
    } catch (err) {
      setIsInitializing(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const exportToCSV = () => {
    const headers = ['Channel', 'MO Reference', 'Family/Variant', 'Ring Type', 'SHO In', 'SHO QTY', 'SCRAP QTY', 'TB Out', 'TB QTY', 'CH In', 'CH Out', 'CH QTY', 'Status Flow'];
    const csvRows = [
      headers.join(','),
      ...summaryData.map(r => [
        `"${r.channel_ref}"`, `"${r.mo_ref}"`, `"${r.product_variant}"`, `"${r.ring_type}"`,
        `"${r.sho_in}"`, r.sho_qty, r.scrap_qty, `"${r.tb_out}"`, r.tb_qty, 
        `"${r.ch_in}"`, `"${r.ch_out}"`, r.ch_qty, `"${r.status}"`
      ].join(','))
    ].join('\n');

    const blob = new Blob([csvRows], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `TBE_Export_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  const filteredSummary = summaryData.filter(item => {
    return (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
      (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase())) ||
      (item.mo_ref && String(item.mo_ref).toLowerCase().includes(search.toLowerCase()));
  });

  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.channel_ref !== b.channel_ref) return String(a.channel_ref || '').localeCompare(String(b.channel_ref || ''));
    if (a.product_variant !== b.product_variant) return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
    return String(a.ring_type || '').localeCompare(String(b.ring_type || ''));
  });

  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    if (!currentRef) return 1;
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef) return 0; 
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef) span++;
    return span;
  };

  const getFamilyRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    const currentFam = dataArray[currentIndex].product_variant;
    if (!currentRef || !currentFam) return 1;
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef && dataArray[currentIndex - 1].product_variant === currentFam) return 0; 
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef && dataArray[currentIndex + span].product_variant === currentFam) span++;
    return span;
  };

  const isCalcActive = Object.keys(selectedCells).length > 0 || calcResult !== null;

  return (
    <div className="traceability-container" style={{ fontFamily: 'Segoe UI, Roboto, sans-serif' }}>
      <div className="header-section" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
        <div>
          <h1>TBE Tracking Log</h1>
          <p className="sub-tag">Synchronized Channel & Ring Family Sequencing Matrices</p>
        </div>
        
        {/* --- CALCULATOR WIDGET --- */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 14px', 
          background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', 
          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
          visibility: isCalcActive ? 'visible' : 'hidden',
          transition: 'opacity 0.2s'
        }}>
          <span style={{ fontFamily: 'monospace', fontWeight: 'bold', fontSize: '1.2em', color: '#0f172a', minWidth: '100px', textAlign: 'right' }}>
            {calcResult !== null ? calcResult.toLocaleString() : ''}
            {currentOperation ? ` ${currentOperation} ` : ''}
            {(selectionTotal !== 0 || calcResult === null) ? selectionTotal.toLocaleString() : ''}
          </span>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('+')}>+</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('-')}>-</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('*')}>*</button>
            <button style={{ padding: '2px 8px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('/')}>/</button>
            <button style={{ padding: '2px 8px', border: '1px solid #3b82f6', background: '#eff6ff', color: '#1d4ed8', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('=')}>=</button>
            <button style={{ padding: '2px 8px', border: '1px solid #f87171', background: '#fef2f2', color: '#b91c1c', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => handleCalcOp('C')}>C</button>
          </div>
        </div>

        <div className="control-actions">
          <input type="date" className="search-box" title="Start Date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <span style={{margin: '0 5px', color: '#64748b'}}>to</span>
          <input type="date" className="search-box" title="End Date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          <button className="back-btn" style={{margin: '0 10px'}} onClick={exportToCSV}>Export CSV</button>
          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchTBEDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>
          <input className="search-box" placeholder="Search Channel, MO, or Family..." value={search} onChange={(e) => setSearch(e.target.value)} disabled={isInitializing} />
        </div>
      </div>

      {error && <div className="error-box">⚠️ Network Error: {error}</div>}
      {isInitializing && <div className="initializing-box"><div className="spinner"></div><p><strong>Compiling Remote Workbook Matrix Caches...</strong></p></div>}
      {loading && !isInitializing && <div className="loading-spinner">Querying server memory buffer...</div>}

      {!loading && !isInitializing && (
        <div className="table-wrapper" style={{ maxHeight: '680px', overflowY: 'auto', border: '1px solid #cbd5e1', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)', position: 'relative' }}>
          <table className="table table-hover mb-0" style={{ whiteSpace: 'nowrap', borderCollapse: 'collapse', width: '100%', textAlign: 'center' }}>
            <thead style={{ backgroundColor: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
              <tr>
                <th style={{ padding: '15px', color: '#475569' }}>Channel</th>
                <th style={{ padding: '15px', color: '#475569' }}>MO Reference</th>
                <th style={{ padding: '15px', color: '#475569' }}>Family Variant</th>
                <th style={{ padding: '15px', color: '#475569' }}>Type</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>SHO In</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>SHO QTY</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#991b1b', backgroundColor: '#fef2f2' }}>SCRAP</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>TB Out</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>TB QTY</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569' }}>CH In/Out</th>
                <th style={{ padding: '15px', textAlign: 'center', color: '#475569', backgroundColor: '#eef2ff' }}>CH QTY</th>
                <th style={{ padding: '15px', color: '#475569' }}>Status Flow</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                const familySpan = getFamilyRowSpan(sortedSummary, idx);
                const uniqueKey = `${row.channel_ref || 'b'}-${row.product_variant || 'b'}-${row.ring_type || 'b'}-${idx}`;
                
                return (
                  <tr key={uniqueKey} className="tbe-row" style={{ borderBottom: '1px solid #e2e8f0' }}>
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} style={{ padding: '12px 15px', fontWeight: '600', color: '#0f172a', borderBottom: '1px solid #e2e8f0', verticalAlign: 'middle' }}>{row.channel_ref || '-'}</td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'middle' }}>
                        <span className="badge bg-light text-dark border text-wrap text-start" style={{ lineHeight: '1.4' }}>{row.mo_ref || '-'}</span>
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} style={{ padding: '12px 15px', fontWeight: '700', color: '#334155', borderBottom: '1px solid #e2e8f0', cursor: 'pointer', verticalAlign: 'middle' }} onClick={() => setSelectedFamily({ ch: row.channel_ref, fam: row.product_variant })}>
                        <span style={{ textDecoration: 'underline', color: '#0284c7' }}>{row.product_variant}</span>
                      </td>
                    )}
                    <td style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0' }}>
                      <span className={`badge ${row.ring_type === 'OM' ? 'bg-primary' : row.ring_type === 'IM' ? 'bg-success' : 'bg-secondary'}`}>{row.ring_type}</span>
                    </td>
                    
                    <td style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{row.sho_in || '-'}</td>
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `sho-${idx}`, row.sho_qty)} 
                      onMouseEnter={(e) => handleMouseEnter(e, `sho-${idx}`, row.sho_qty)} 
                      style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', background: selectedCells[`sho-${idx}`] !== undefined ? '#bae6fd' : '', cursor: 'cell', fontWeight: 'bold' }}>
                      {row.sho_qty ? Number(row.sho_qty).toLocaleString() : '0'}
                    </td>
                    
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `scrap-${idx}`, row.scrap_qty)} 
                      onMouseEnter={(e) => handleMouseEnter(e, `scrap-${idx}`, row.scrap_qty)} 
                      style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#b91c1c', background: selectedCells[`scrap-${idx}`] !== undefined ? '#fecaca' : '#fef2f2', cursor: 'cell', fontWeight: 'bold' }}>
                      {row.scrap_qty ? Number(row.scrap_qty).toLocaleString() : '0'}
                    </td>

                    <td style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{row.tb_out || '-'}</td>
                    <td 
                      onMouseDown={(e) => handleMouseDown(e, `tb-${idx}`, row.tb_qty)} 
                      onMouseEnter={(e) => handleMouseEnter(e, `tb-${idx}`, row.tb_qty)} 
                      style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', background: selectedCells[`tb-${idx}`] !== undefined ? '#bae6fd' : '', cursor: 'cell', fontWeight: 'bold' }}>
                      {row.tb_qty ? Number(row.tb_qty).toLocaleString() : '0'}
                    </td>
                    
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.85rem', verticalAlign: 'middle' }}>
                        <div>{row.ch_in || '-'}</div>
                        <div>to</div>
                        <div>{row.ch_out || '-'}</div>
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td 
                        rowSpan={familySpan} 
                        onMouseDown={(e) => handleMouseDown(e, `ch-${idx}`, row.ch_qty)} 
                        onMouseEnter={(e) => handleMouseEnter(e, `ch-${idx}`, row.ch_qty)} 
                        style={{ padding: '12px 15px', textAlign: 'center', borderBottom: '1px solid #e2e8f0', background: selectedCells[`ch-${idx}`] !== undefined ? '#bae6fd' : '', cursor: 'cell', fontWeight: 'bold', verticalAlign: 'middle' }}>
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                      </td>
                    )}
                    
                    <td style={{ padding: '12px 15px', borderBottom: '1px solid #e2e8f0' }}>
                      <span className={`status-pill ${row.status && row.status.includes('Completed') ? 'status-completed' : 'status-default'}`}>{row.status || 'In Process'}</span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr><td colSpan="12" className="text-center py-5 text-muted">No matrices found for current filter criteria.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Drilldown Modal */}
      {selectedFamily && (
        <div className="modal-overlay" onClick={() => setSelectedFamily(null)}>
          <div className="modal-content-custom" onClick={e => e.stopPropagation()}>
            <div className="modal-header-custom bg-dark text-white p-3 d-flex justify-content-between align-items-center rounded-top">
              <h5 className="mb-0">Execution Details: <span className="text-warning">{selectedFamily.fam}</span> (Channel: {selectedFamily.ch})</h5>
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
                            <span className={`dept-tag ${vRow.department.toLowerCase().replace(/[\s\(\)\/]+/g, '-')}`}>
                              {vRow.department}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{ color: '#0f172a', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>{vRow.variant}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.in_date}</td>
                          <td style={{ padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>{vRow.out_date}</td>
                          
                          <td className="fw-bold" 
                            onMouseDown={(e) => handleMouseDown(e, `modal-qty-${vIdx}`, vRow.qty)}
                            onMouseEnter={(e) => handleMouseEnter(e, `modal-qty-${vIdx}`, vRow.qty)}
                            style={{ 
                              padding: '10px', borderBottom: '1px solid #e2e8f0', textAlign: 'center',
                              background: selectedCells[`modal-qty-${vIdx}`] !== undefined ? '#bae6fd' : 'inherit',
                              userSelect: 'none', cursor: 'cell'
                            }}>
                            {Number(vRow.qty).toLocaleString()}
                          </td>
                          
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
