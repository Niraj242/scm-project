import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  const fetchSummaryDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records.');
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setTimeout(fetchSummaryDashboard, 4000);
      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (moString) => {
    try {
      setLoading(true);
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      const json = await res.json();
      if (json.status === 'success') {
        setSelectedMoFlow({
          mo: moString,
          flow_data: json.data.timeline || [] 
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Filter & Sort using Model.py column names
  const filteredSummary = summaryData.filter(item => 
    (item.normalized_mo && String(item.normalized_mo).toLowerCase().includes(search.toLowerCase())) ||
    (item.tag_type && String(item.tag_type).toLowerCase().includes(search.toLowerCase()))
  );

  const sortedSummary = [...filteredSummary].sort((a, b) => 
    (a.normalized_mo || '').localeCompare(b.normalized_mo || '')
  );

  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].normalized_mo;
    if (currentIndex > 0 && dataArray[currentIndex - 1].normalized_mo === currentMo) return 0;
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].normalized_mo === currentMo) span++;
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>TBE Calibration Tracking</h1>
          <p className="sub-tag">{selectedMoFlow ? `Flow for: ${selectedMoFlow.mo}` : "Transit Buffer Dashboard"}</p>
        </div>
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)}>← Back</button>
          ) : (
            <input className="search-box" placeholder="Filter by MO..." value={search} onChange={(e) => setSearch(e.target.value)} />
          )}
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      
      {!loading && !selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="sub-header">
                <th>MO Number</th>
                <th>Ring Type</th>
                <th>Target Qty</th>
                <th>Production</th>
                <th>Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => (
                <tr key={idx} className="data-row">
                  {getMoRowSpan(sortedSummary, idx) > 0 && (
                    <td rowSpan={getMoRowSpan(sortedSummary, idx)} className="merged-mo-cell">
                      <button className="mo-link-btn" onClick={() => handleViewDetail(row.normalized_mo)}>
                        {row.normalized_mo}
                      </button>
                    </td>
                  )}
                  <td>{row.tag_type || '-'}</td>
                  <td>{row.pc_qty ? Number(row.pc_qty).toLocaleString() : '-'}</td>
                  <td>{row.production ? Number(row.production).toLocaleString() : '-'}</td>
                  <td>{row.date ? new Date(row.date).toLocaleDateString() : '-'}</td>
                  <td><span className="status-badge">{row.status || 'Active'}</span></td>
                </tr>
              ))}
              {sortedSummary.length === 0 && (
                <tr><td colSpan="6" className="empty-state">No matching data located.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr><th>MO Reference</th><th>Status</th></tr>
            </thead>
            <tbody>
              {selectedMoFlow.flow_data.map((row, idx) => (
                <tr key={idx}>
                  <td>{selectedMoFlow.mo}</td>
                  <td>{row.status || 'In Progress'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TBE;
