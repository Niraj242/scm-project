import React, { useState } from 'react';
import './Traceability.css';

const Traceability = () => {
  const [mo, setMo] = useState('');
  const [data, setData] = useState(null);

  const fetchTraceability = async () => {
    try {
      // Replace with your actual Render backend URL
      const response = await fetch(`https://scm-backend-pshv.onrender.com/traceability_report/${mo}`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error("Error fetching traceability:", error);
    }
  };

  return (
    <div className="traceability-container">
      <h2>MO Traceability Lookup</h2>
      <input value={mo} onChange={(e) => setMo(e.target.value)} placeholder="Enter MO Number" />
      <button onClick={fetchTraceability}>Track MO</button>
      
      {data && (
        <div className="result-card">
          <p>Status: {data.status}</p>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};
export default Traceability;
