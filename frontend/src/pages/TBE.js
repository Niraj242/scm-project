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
  
  // MODIFIED: State for controlling the Raw Data details modal
  const [selectedDetails, setSelectedDetails] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    fetchTBEDashboard();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const fetchTBEDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');

      const res = await fetch(`${API}/tbe_all_mos`);
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

  const filteredSummary = summaryData.filter(item => {
    const matchesSearch = 
      (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
      (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase())) ||
      (item.mo_ref && String(item.mo_ref).toLowerCase().includes(search.toLowerCase()));

    let matchesDate = true;
    if (startDate || endDate) {
      const dates = [item.sho_in, item.tb_out, item.ch_in, item.ch_out].filter(d => d && d !== '-');
      
      if (dates.length === 0) {
        matchesDate = false; 
      } else {
        matchesDate = dates.some(d => {
          const dateObj = new Date(d);
          const s = startDate ? new Date(startDate) : new Date('1900-01-01');
          const e = endDate ? new Date(endDate) : new Date('2100-01-01');
          return dateObj >= s && dateObj <= e;
        });
      }
    }
    return matchesSearch && matchesDate;
  });

  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.channel_ref !== b.channel_ref) {
      return String(a.channel_ref || '').localeCompare(String(b.channel_ref || ''));
    }
    if (a.product_variant !== b.product_variant) {
      return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
    }
    return String(a.ring_type || '').localeCompare(String(b.ring_type || ''));
  });

  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    if (!currentRef) return 1;
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef) return 0; 
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef) {
      span++;
    }
    return span;
  };

  const getFamilyRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    const currentFam = dataArray[currentIndex].product_variant;
    if (!currentRef || !currentFam) return 1;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].channel_ref === currentRef &&
        dataArray[currentIndex - 1].product_variant === currentFam) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && 
           dataArray[currentIndex + span].channel_ref === currentRef &&
           dataArray[currentIndex + span].product_variant === currentFam) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>TBE Tracking Log</h1>
          <p className="sub-tag">Synchronized Channel & Ring Family Sequencing Matrices</p>
        </div>
        
        <div className="control-actions">
          <input 
            type="date" 
            className="search-box" 
            title="Start Date"
            value={startDate} 
            onChange={(e) => setStartDate(e.target.value)} 
          />
          <span style={{margin: '0 5px', color: '#fff'}}>to</span>
          <input 
            type="date" 
            className="search-box" 
            title="End Date"
            value={endDate} 
            onChange={(e) => setEndDate(e.target.value)} 
          />

          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchTBEDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>
          
          <input
            className="search-box"
            placeholder="Search Channel, MO, or Family..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={isInitializing}
          />
        </div>
      </div>

      {error && <div className="error-box">⚠️ Network Error: {error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>Compiling Remote Workbook Matrix Caches...</strong></p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying server memory buffer...</div>}

      {!loading && !isInitializing && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="4" className="meta-head">Connection Mapping</th>
                <th colSpan="2" className="sho-head">SHO Department (Split)</th>
                <th colSpan="2" className="tb-head">Transit Buffer (Split)</th>
                <th colSpan="3" className="ch-head">Channel Section (Combined Rollup)</th>
                <th className="meta-head">Status Tracker</th>
              </tr>
              <tr className="sub-header">
                <th>Channel Ref</th>
                <th>MO</th>
                <th>Ring Family</th>
                <th>Ring Type</th>
                <th>Qty</th>
                <th>In Date</th>
                <th>Qty</th>
                <th>Out Date</th>
                <th>Qty</th>
                <th>In Date</th>
                <th>Out Date</th>
                <th>Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                const familySpan = getFamilyRowSpan(sortedSummary, idx);
                const uniqueKey = `${row.channel_ref || 'b'}-${row.product_variant || 'b'}-${row.ring_type || 'b'}-${idx}`;
                
                return (
                  <tr key={uniqueKey} className="data-row">
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-mo-cell fw-bold">
                        {row.channel_ref || '-'}
                      </td>
                    )}
                    
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-mo-cell text-muted" style={{fontSize: '0.9em'}}>
                        {row.mo_ref || '-'}
                      </td>
                    )}

                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="fw-bold text-primary">
                        {row.product_variant}
                      </td>
                    )}
                    
                    {/* MODIFIED: Clickable element triggers Modal with raw logs */}
                    <td 
                      className="fw-bold text-primary" 
                      style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      title="Click to view detailed variant logs"
                      onClick={() => {
                        setSelectedDetails({
                          title: `${row.channel_ref || 'General'} | ${row.product_variant} | ${row.ring_type}`,
                          details: row.details || []
                        });
                      }}
                    >
                      {row.ring_type} ↗
                    </td>
                    
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '0'}</td>
                    <td>{row.sho_in || '-'}</td>
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '0'}</td>
                    <td>{row.tb_out || '-'}</td>
                    
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell fw-bold text-success">
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell">{row.ch_in || '-'}</td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell">{row.ch_out || '-'}</td>
                    )}
                    
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`}>
                        {row.status || 'In Process'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="12" className="empty-state">
                    No records found matching the current search criteria or date range.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* MODIFIED: Drill-Down Details Modal Component */}
      {selectedDetails && (
        <div className="modal-overlay" onClick={() => setSelectedDetails(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Raw Entry Logs: {selectedDetails.title}</h2>
              <button className="close-btn" onClick={() => setSelectedDetails(null)}>&times;</button>
            </div>
            <div className="modal-body">
              {selectedDetails.details.length > 0 ? (
                <table className="details-table">
                  <thead>
                    <tr>
                      <th>Source Category</th>
                      <th>Raw Variant String</th>
                      <th>Production Date</th>
                      <th>Quantity Logged</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedDetails.details.map((item, i) => (
                      <tr key={i}>
                        <td>
                          <span className={`status-badge ${item.source.includes('Channel') ? 'completed' : 'pending'}`}>
                            {item.source}
                          </span>
                        </td>
                        <td className="fw-bold">{item.variant}</td>
                        <td>{item.date}</td>
                        <td>{Math.ceil(item.qty).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="empty-state" style={{padding: '20px'}}>No individual raw entries logged for this specific combination.</p>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default TBE;
