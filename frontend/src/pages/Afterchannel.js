import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); // True separation of forms
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

  // FIXED: Explicitly casting to String() prevents the 0 qty bug for numeric variants
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

  // FIXED: Converts empty strings to null to satisfy FastAPI's strict Pydantic Optional types
  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    
    const payload = {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase()
    };

    // Parse form data safely
    for (let [key, value] of fd.entries()) {
      if (value === "") {
        payload[key] = null; // Fixes the 422 error
      } else if (['qtyIn', 'qtySent', 'ballScrap', 'cageSealScrap'].includes(key)) {
        payload[key] = Number(value); // Force integers for FastAPI
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
        throw new Error(JSON.stringify(errJson.message) || `HTTP Error ${response.status}`);
      }
      
      alert("Operational Record Logged Successfully!");
      e.target.reset();
      fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      
      {/* --- DATALISTS (Built from your images) --- */}
      <datalist id="depts-list">
        <option value="Channel" />
        <option value="Accurate" />
        <option value="CPS" />
        <option value="Rework" />
        <option value="Dismantling" />
        <option value="Packaging" />
        <option value="FPS" />
        <option value="Scrap" />
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

      {/* --- HEADER --- */}
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
      </div>
    </div>
  );
};

export default Afterchannel;
