import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMoDetail, setSelectedMoDetail] = useState(null);

  const [moNumber, setMoNumber] = useState('');
  const [availableVariants, setAvailableVariants] = useState([]);
  const [selectedVariant, setSelectedVariant] = useState('');
  const [actualProductionQty, setActualProductionQty] = useState(0);

  useEffect(() => {
    fetchMasterData();
    fetchLedgers();
  }, []);

  const fetchMasterData = async () => {
    try {
      const res = await fetch(`${API}/api/mo-lookup`);
      const data = await res.json();
      if (data.status === 'success') {
        setMoCache(data.data || {});
      }
    } catch (err) {
      console.error("Master Reference Load Failure:", err);
    }
  };

  const fetchLedgers = async () => {
    try {
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`);
      const json = await res.json();
      if (json.status === 'success') {
        setLedgers(json.data);
      }
    } catch (err) {
      console.error("Ledger Sync Failure:", err);
    }
  };

  const calculateProduction = (rawRows, variantToMatch) => {
    if (!rawRows || !Array.isArray(rawRows)) return 0;
    const cleanMatch = String(variantToMatch || '').trim().toUpperCase();
    
    return rawRows.reduce((sum, r) => {
      const rowType = String(r.type || r.Type || '').trim().toUpperCase();
      if (rowType === cleanMatch) {
        let val = r.qty || r.production || 0;
        if (typeof val === 'string') val = val.replace(/,/g, '');
        return sum + (parseFloat(val) || 0);
      }
      return sum;
    }, 0);
  };

  const handleMoBlur = () => {
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      const rawRows = moCache[key];
      const uniqueVariants = [...new Set(rawRows.map(r => String(r.type || '').trim()))].filter(Boolean);
      setAvailableVariants(uniqueVariants.map(type => ({ type })));

      if (uniqueVariants.length === 1) {
        const vType = uniqueVariants[0];
        setSelectedVariant(vType);
        setActualProductionQty(calculateProduction(rawRows, vType));
      } else {
        setSelectedVariant('');
        setActualProductionQty(0);
      }
    } else {
      setAvailableVariants([]);
      setSelectedVariant('');
      setActualProductionQty(0);
    }
  };

  const handleVariantChange = (e) => {
    const variantName = e.target.value;
    setSelectedVariant(variantName);
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      setActualProductionQty(calculateProduction(moCache[key], variantName));
    }
  };

  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    
    const payload = {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase()
    };

    for (let [key, value] of fd.entries()) {
      if (value === "") {
        payload[key] = null;
      } else if (['qtyIn', 'qtySent', 'ballScrap', 'cageSealScrap'].includes(key)) {
        payload[key] = Number(value);
      } else {
        payload[key] = value;
      }
    }

    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(JSON.stringify(errJson.detail || errJson.message) || `HTTP Error ${response.status}`);
      }
      
      alert("Operational Record Logged Successfully!");
      e.target.reset();
      fetchLedgers(); // Refresh data table
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  // --- RESTORED SUMMARY LOGIC ---
  const filteredMos = Object.keys(moCache).filter(mo => 
    mo.toUpperCase().includes(searchQuery.toUpperCase())
  );

  const openSummaryModal = (mo) => {
    const rawRows = moCache[mo] || [];
    const variants = [...new Set(rawRows.map(r => String(r.type || '').trim()))].filter(Boolean);
    
    const breakdown = variants.map(v => {
      const prodQty = calculateProduction(rawRows, v);
      
      const accLedger = ledgers.accurate.filter(l => l.mo === mo && l.type === v);
      const accIn = accLedger.reduce((sum, l) => sum + (Number(l.qty_in) || 0), 0);
      const accOut = accLedger.reduce((sum, l) => sum + (Number(l.qty_sent) || 0), 0);

      const cpsLedger = ledgers.cps.filter(l => l.mo === mo && l.type === v);
      const cpsIn = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_in) || 0), 0);
      const cpsOut = cpsLedger.reduce((sum, l) => sum + (Number(l.qty_sent) || 0), 0);

      const rwLedger = ledgers.rework.filter(l => l.mo === mo && l.type === v);
      const rwIn = rwLedger.reduce((sum, l) => sum + (Number(l.qty_in) || 0), 0);
      const rwOut = rwLedger.reduce((sum, l) => sum + (Number(l.qty_sent) || 0), 0);

      const disLedger = ledgers.dismantling.filter(l => l.mo === mo && l.type === v);
      const disIn = disLedger.reduce((sum, l) => sum + (Number(l.qty_in) || 0), 0);
      const scrapSum = disLedger.reduce((sum, l) => sum + (Number(l.ball_scrap) || 0) + (Number(l.cage_seal_scrap) || 0), 0);

      return {
        variant: v, prodQty,
        accIn, accOut,
        cpsIn, cpsOut,
        rwIn, rwOut,
        disIn, scrapSum
      };
    });

    setSelectedMoDetail({ mo, breakdown });
  };

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      
      <datalist id="depts-list">
        <option value="Channel" /><option value="Accurate" /><option value="CPS" />
        <option value="Rework" /><option value="Dismantling" /><option value="Packaging" />
        <option value="FPS" /><option value="Scrap" />
      </datalist>

      <datalist id="channels-list">
        {['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'].map(ch => <option key={ch} value={ch} />)}
      </datalist>

      <datalist id="rework-activities">
        <option value="Cartons Removal" /><option value="Grease Removal" /><option value="Grease and shield Removal" />
        <option value="Manual Greesing" /><option value="Nailon Cage Fitting" /><option value="OD Ovality Remove" />
        <option value="OD Polish" /><option value="Rusty Removal" /><option value="Scrur Fitting" />
        <option value="Shield Removal" /><option value="Snap Ring Fitting" /><option value="Snap Ring Removal" />
        <option value="Stain Mark Removal" /><option value="Stamping and Shield Removal" /><option value="Stamping Removal" />
        <option value="Surface Polish" /><option value="Visual" />
      </datalist>

      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px'}}>
          {['accurate', 'cps', 'rework', 'vibration'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>
            📊 SUMMARY
          </button>
        </div>
      </div>

      {activeTab !== 'summary' && (
        <div style={{marginBottom: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
          <div style={{display: 'flex', gap: '20px'}}>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>MO Number</label>
              <input type="text" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Variant</label>
              {availableVariants.length > 0 ? (
                <select value={selectedVariant} onChange={handleVariantChange} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required>
                  <option value="">-- Select Variant --</option>
                  {availableVariants.map(v => <option key={v.type} value={v.type}>{v.type}</option>)}
                </select>
              ) : (
                <input type="text" value={selectedVariant} onChange={(e) => setSelectedVariant(e.target.value)} placeholder="Manual Entry" style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
              )}
            </div>
            <div style={{flex: 1}}>
              <label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Total Production Qty</label>
              <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '0'} readOnly style={{width: '100%', padding: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold', color: '#16a34a'}} />
            </div>
          </div>

          <div style={{display: 'flex', gap: '20px', marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #cbd5e1'}}>
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📥 LOG IN (Receiving)
            </button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>
              📤 LOG OUT (Dispatch)
            </button>
          </div>
        </div>
      )}

      <div className="ac-content">
        {/* ================= ACCURATE TAB ================= */}
        {activeTab === 'accurate' && (
          <form onSubmit={(e) => handleFormSubmit(e, 'accurate')}>
            {entryMode === 'IN' ? (
              <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Accurate - Receiving Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>PC</label><input type="text" name="pc" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Material In From</label><input list="depts-list" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}} required/></div>
                </div>
              </fieldset>
            ) : (
              <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Accurate - Dispatch Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>Next Station</label><input list="depts-list" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                </div>
              </fieldset>
            )}
            <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>Save Entry</button>
          </form>
        )}

        {/* ================= CPS TAB ================= */}
        {activeTab === 'cps' && (
          <form onSubmit={(e) => handleFormSubmit(e, 'cps')}>
            {entryMode === 'IN' ? (
              <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>CPS Assembly - Receiving Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>Item</label><select name="item" style={{width:'100%', padding:'6px'}}><option></option><option>Seal</option><option>Shield</option><option>OM Black</option><option>OM White</option><option>IM Black</option><option>IM White</option></select></div>
                  <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>RC No</label><input type="text" name="rcNo" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Material In From</label><input list="depts-list" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Channel</label><input list="channels-list" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}} required/></div>
                </div>
              </fieldset>
            ) : (
              <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>CPS Assembly - Dispatch Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>Next Station</label><input list="depts-list" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                </div>
              </fieldset>
            )}
            <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>Save Entry</button>
          </form>
        )}

        {/* ================= REWORK TAB ================= */}
        {activeTab === 'rework' && (
          <form onSubmit={(e) => handleFormSubmit(e, 'rework')}>
            {entryMode === 'IN' ? (
              <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Rework Station - Receiving Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>Channel</label><input list="channels-list" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Line Segment</label><input type="text" name="lineSegment" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Material In From</label><input list="depts-list" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Rework Activity</label><input list="rework-activities" name="reworkActivity" style={{width:'100%', padding:'6px'}}/></div>
                </div>
              </fieldset>
            ) : (
              <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Rework Station - Dispatch Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>Next Station</label><input list="depts-list" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>Operator</label><input type="text" name="operator" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Remark</label><input type="text" name="remark" style={{width:'100%', padding:'6px'}}/></div>
                </div>
              </fieldset>
            )}
            <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>Save Entry</button>
          </form>
        )}

        {/* ================= VIBRATION / DISMANTLING TAB ================= */}
        {activeTab === 'vibration' && (
          <form onSubmit={(e) => handleFormSubmit(e, 'vibration')}>
            {entryMode === 'IN' ? (
              <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold'}}>Vibration Dismantling - Receiving Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>Channel</label><input list="channels-list" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Line Segment</label><input type="text" name="lineSegment" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Reason</label><select name="reason" style={{width:'100%', padding:'6px'}}><option></option><option>D4</option><option>OD Mark</option></select></div>
                  <div><label>Material In From</label><input list="depts-list" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Activity</label><select name="activity" style={{width:'100%', padding:'6px'}}><option></option><option>Ball Remove</option><option>Rivet Press</option></select></div>
                  <div><label>Ring Type</label><select name="ringType" style={{width:'100%', padding:'6px'}}><option></option><option>IR</option><option>OR</option></select></div>
                </div>
              </fieldset>
            ) : (
              <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', color: '#ea580c'}}>Vibration Dismantling - Output Log</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                  <div><label>Ball Scrap</label><input type="number" name="ballScrap" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Cage/Seal Scrap</label><input type="number" name="cageSealScrap" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Next Station</label><input list="depts-list" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}} required/></div>
                  <div><label>Shift</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  <div><label>Operator</label><input type="text" name="operator" style={{width:'100%', padding:'6px'}}/></div>
                  <div><label>Remark</label><input type="text" name="remark" style={{width:'100%', padding:'6px'}}/></div>
                </div>
              </fieldset>
            )}
            <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', fontWeight:'bold', cursor:'pointer'}}>Save Entry</button>
          </form>
        )}

        {/* ================= SUMMARY & MODAL (RESTORED) ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '20px', borderRadius: '8px', border: '1px solid #cbd5e1'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.3em', margin: 0, color: '#1e293b'}}>Active Master Orders (MO) Reference Index</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} style={{padding: '8px 12px', width: '320px', border: '1px solid #cbd5e1', borderRadius: '6px'}} />
            </div>
            
            <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.95em'}}>
              <thead>
                <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                  <th style={{padding: '12px', fontWeight: '700', color: '#475569'}}>Master Order (MO) ID</th>
                  <th style={{padding: '12px', fontWeight: '700', color: '#475569'}}>Registered Specifications Count</th>
                  <th style={{padding: '12px', fontWeight: '700', color: '#475569', textAlign: 'right'}}>Audit Control</th>
                </tr>
              </thead>
              <tbody>
                {filteredMos.map(mo => (
                  <tr key={mo} style={{borderBottom: '1px solid #e2e8f0'}}>
                    <td style={{padding: '14px 12px', fontWeight: '700', color: '#1e40af'}}>{mo}</td>
                    <td style={{padding: '14px 12px', color: '#64748b'}}>{moCache[mo] ? moCache[mo].length : 0} Variant Matrices Compiled</td>
                    <td style={{padding: '14px 12px', textAlign: 'right'}}>
                      <button onClick={() => openSummaryModal(mo)} style={{padding: '7px 14px', background: '#0284c7', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: '600'}}>
                        View Detailed Pipeline →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedMoDetail && (
        <div className="modal-backdrop" style={{position: 'fixed', top:0, left:0, width:'100vw', height:'100vh', background:'rgba(15, 23, 42, 0.6)', display:'flex', justifyContent:'center', alignItems:'center', zIndex: 1000}}>
          <div className="modal-window" style={{background:'#fff', padding:'25px', borderRadius:'8px', width:'95%', maxWidth:'1200px', maxHeight:'85vh', overflowY:'auto'}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', borderBottom:'2px solid #cbd5e1', paddingBottom:'15px', marginBottom:'20px'}}>
              <h2>Cross-Department Flow Trace Analysis ({selectedMoDetail.mo})</h2>
              <button onClick={() => setSelectedMoDetail(null)} style={{fontSize:'1.5em', cursor:'pointer', border:'none', background:'none'}}>×</button>
            </div>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.88em'}}>
              <thead>
                <tr style={{background: '#f8fafc'}}>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Variant Model</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Actual Prod Qty</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Accurate In</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Accurate Out</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>CPS In</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>CPS Out</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Rework In</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Rework Out</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Dismantle In</th>
                  <th style={{border: '1px solid #cbd5e1', padding: '10px'}}>Scrap Sum</th>
                </tr>
              </thead>
              <tbody>
                {selectedMoDetail.breakdown.map((row, i) => (
                  <tr key={i} style={{borderBottom: '1px solid #e2e8f0', textAlign: 'center'}}>
                    <td style={{padding:'10px', fontWeight:'bold', textAlign:'left'}}>{row.variant}</td>
                    <td style={{padding:'10px', background:'#f0fdf4', color:'#16a34a', fontWeight:'bold'}}>{row.prodQty.toLocaleString()}</td>
                    <td style={{padding:'10px'}}>{row.accIn || '-'}</td><td style={{padding:'10px'}}>{row.accOut || '-'}</td>
                    <td style={{padding:'10px'}}>{row.cpsIn || '-'}</td><td style={{padding:'10px'}}>{row.cpsOut || '-'}</td>
                    <td style={{padding:'10px'}}>{row.rwIn || '-'}</td><td style={{padding:'10px'}}>{row.rwOut || '-'}</td>
                    <td style={{padding:'10px'}}>{row.disIn || '-'}</td><td style={{padding:'10px', color:'#dc2626', fontWeight: 'bold'}}>{row.scrapSum || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Afterchannel;
