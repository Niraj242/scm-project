import React, { useEffect, useState } from 'react';

import { useParams } from 'react-router-dom';

import './Traceability.css';

const API =
  'https://scm-backend-pshv.onrender.com';

const TraceabilityFlow = () => {

  const { mo } = useParams();

  const [loading, setLoading] =
    useState(false);

  const [data, setData] = useState(null);

  // =====================================================
  // LOAD FLOW
  // =====================================================

  useEffect(() => {

    fetchFlow();

  }, [mo]);

  const fetchFlow = async () => {

    try {

      setLoading(true);

      const response = await fetch(
        `${API}/traceability_report/${mo}`
      );

      const result = await response.json();

      setData(result);

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  // =====================================================
  // UI
  // =====================================================

  return (

    <div className="traceability-container">

      <div className="flow-header">

        <h1>
          MO Flow : {mo}
        </h1>

      </div>

      {loading && (
        <div className="loading-box">
          Loading Flow...
        </div>
      )}

      {!loading && data && (

        <>

          <div className="summary-grid">

            <div className="summary-card">
              <h3>MO</h3>
              <p>{data.searched_mo}</p>
            </div>

            <div className="summary-card">
              <h3>Family</h3>
              <p>{data.family}</p>
            </div>

            <div className="summary-card">
              <h3>Total Stages</h3>
              <p>{data.total_records}</p>
            </div>

            <div className="summary-card">
              <h3>Start Date</h3>
              <p>{data.start_date || '-'}</p>
            </div>

            <div className="summary-card">
              <h3>End Date</h3>
              <p>{data.end_date || '-'}</p>
            </div>

            <div className="summary-card">
              <h3>Status</h3>
              <p>{data.status}</p>
            </div>

          </div>

          <div className="table-wrapper">

            <table>

              <thead>

                <tr>

                  <th>Date</th>

                  <th>Department</th>

                  <th>Channel</th>

                  <th>Sheet</th>

                  <th>MO</th>

                  <th>Bearing Family</th>

                  <th>Shift</th>

                  <th>Production</th>

                  <th>Cumulative</th>

                  <th>Approved Qty</th>

                  <th>Returned Qty</th>

                  <th>Transit Qty</th>

                  <th>Output Qty</th>

                  <th>Next Station</th>

                  <th>Ring Type</th>

                  <th>Status</th>

                  <th>Remark</th>

                </tr>

              </thead>

              <tbody>

                {data.timeline?.map(
                  (row, index) => (

                    <tr key={index}>

                      <td>
                        {row.date || '-'}
                      </td>

                      <td>
                        {row.department || '-'}
                      </td>

                      <td>
                        {row.channel || '-'}
                      </td>

                      <td>
                        {row.sheet || '-'}
                      </td>

                      <td>
                        {row.mo || '-'}
                      </td>

                      <td>
                        {row.family || '-'}
                      </td>

                      <td>
                        {row.shift || '-'}
                      </td>

                      <td>
                        {row.production || '-'}
                      </td>

                      <td>
                        {row.cumulative_production || '-'}
                      </td>

                      <td>
                        {row.qty_approved || '-'}
                      </td>

                      <td>
                        {row.qty_returned || '-'}
                      </td>

                      <td>
                        {row.transit_qty || '-'}
                      </td>

                      <td>
                        {row.output_qty || '-'}
                      </td>

                      <td>
                        {row.next_station || '-'}
                      </td>

                      <td>
                        {row.ring_type || '-'}
                      </td>

                      <td>
                        {row.status || '-'}
                      </td>

                      <td>
                        {row.remark || '-'}
                      </td>

                    </tr>
                  )
                )}

              </tbody>

            </table>

          </div>

        </>
      )}

    </div>
  );
};

export default TraceabilityFlow;
