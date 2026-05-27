import React, { useState } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  // =====================================================
  // SEARCH MO FLOW
  // =====================================================
  const handleSearch = async (e) => {
    e.preventDefault();
    if (!search.trim()) return;

    try {
      setLoading(true);
      setError('');
      setData(null);

      const response = await fetch(`${API}/traceability_report/${search.trim()}`);
      
      if (!response.ok) {
        throw new Error('MO not found or data is still loading in background.');
      }

      const result = await response.json();
      
      if (result.status === 'success') {
        setData(result.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // =====================================================
  // UI
  // =====================================================
  return (
    <div className="traceability-container">
      <div className="header-section">
        <h1>MO Traceability Tracking</h1>
        
        <form onSubmit={handleSearch} className="search-form">
          <input
            className="search-box"
            placeholder="Enter MO Number (e.g. M108)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="search-btn" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </div>

      {error && <div className="error-box">{error}</div>}

      {!loading && data && data.flow_data && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>MO</th>
                <th>Department/Location</th>
                <th>Product/ Part Name</th>
                <th>In Date</th>
                <th>Out Date</th>
                <th>Qty In</th>
                <th>Qty Out</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.flow_data.map((row, index) => {
                // Determine if we need to show the MO cell (only on the first row to span across)
                const isFirstRow = index === 0;

                return (
                  <tr key={index}>
                    {isFirstRow && (
                      <td rowSpan={data.flow_data.length} className="mo-cell">
                        <strong>{data.mo}</strong>
                      </td>
                    )}
                    <td>{row.department}</td>
                    <td>{row.product || '-'}</td>
                    <td>{row.in_date || '-'}</td>
                    <td>{row.out_date || '-'}</td>
                    <td>{row.qty_in}</td>
                    <td>{row.qty_out}</td>
                    <td>
                      <span className={`status-badge ${row.status?.toLowerCase().replace(' ', '-')}`}>
                        {row.status || '-'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Traceability;
