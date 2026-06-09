import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); // 'IN' or 'OUT' toggle
  const [moCache, setMoCache] = useState({});
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMoDetail, setSelectedMoDetail] = useState(null);

  // Core Operational Form State
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
      console.error("Failed to fetch Master Data", err);
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
      console.error("Failed to load ledgers", err);
    }
  };

  // Bulletproof Production Sum Logic
  const calculateProduction = (rawRows, variantToMatch) => {
    const cleanMatch = (variantToMatch || '').trim().toUpperCase();
    return rawRows
      .filter(r => (r.type || '').trim().toUpperCase() === cleanMatch)
      .reduce((sum, r) => {
        let val = r.production || r.Production || r.qty || r.Qty || r.QTY || 0;
        // Strip commas if the database returns strings like "1,500"
        if (typeof val === 'string') val = val.replace(/,/g, '');
        return sum + (parseFloat(val) || 0);
      }, 0);
  };

  const handleMoBlur = () => {
    const key = moNumber.trim().toUpperCase();
    if (moCache[key]) {
      const rawRows = moCache[key];
      const uniqueVariants = [...new Set(rawRows.map(r => (r.type || '').trim()))].filter(Boolean);
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

  const submitForm = async (endpoint, payload) => {
    try {
      const response = await fetch(`${API}/api/afterchannel/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        // Now shows the actual backend error if it fails
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.message || `Backend rejected submission (Status: ${response.status})`);
      }
      
      alert("Entry Successfully Logged!");
      fetchLedgers();
    } catch (err) {
      alert("Submission Error: " + err.message);
    }
  };

  const handleAccurateSubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    submitForm('accurate', {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      inDate: fd.get('inDate'),
      shiftIn: fd.get('shiftIn'),
      pc: fd.get('pc'),
      materialInFrom: fd.get('materialInFrom'),
      qtyIn: fd.get('qtyIn') ? Number(fd.get('qtyIn')) : null,
      nextStation: fd.get('nextStation'),
      qtySent: fd.get('qtySent') ? Number(fd.get('qtySent')) : null,
      outDate: fd.get('outDate'),
      shiftOut: fd.get('shiftOut')
    });
  };

  const handleCpsSubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    submitForm('cps', {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      item: fd.get('item'),
      inDate: fd.get('inDate'),
      shiftIn: fd.get('shiftIn'),
      rcNo: fd.get('rcNo'),
      materialInFrom: fd.get('materialInFrom'),
      channel: fd.get('channel'),
      qtyIn: fd.get('qtyIn') ? Number(fd.get('qtyIn')) : null,
      nextStation: fd.get('nextStation'),
      qtySent: fd.get('qtySent') ? Number(fd.get('qtySent')) : null,
      outDate: fd.get('outDate'),
      shiftOut: fd.get('shiftOut')
    });
  };

  const handleReworkSubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    submitForm('rework', {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      inDate: fd.get('inDate'),
      shiftIn: fd.get('shiftIn'),
      channel: fd.get('channel'),
      lineSegment: fd.get('lineSegment'),
      materialInFrom: fd.get('materialInFrom'),
      qtyIn: fd.get('qtyIn') ? Number(fd.get('qtyIn')) : null,
      reworkActivity: fd.get('reworkActivity'),
      nextStation: fd.get('nextStation'),
      qtySent: fd.get('qtySent') ? Number(fd.get('qtySent')) : null,
      outDate: fd.get('outDate'),
      shiftOut: fd.get('shiftOut'),
      operator: fd.get('operator'),
      remark: fd.get('remark')
    });
  };

  const handleVibrationSubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    submitForm('vibration', {
      mo: moNumber.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      inDate: fd.get('inDate'),
      shiftIn: fd.get('shiftIn'),
      channel: fd.get('channel'),
      lineSegment: fd.get('lineSegment'),
      reason: fd.get('reason'),
      materialInFrom: fd.get('materialInFrom'),
      qtyIn: fd.get('qtyIn') ? Number(fd.get('qtyIn')) : null,
      activity: fd.get('activity'),
      ballScrap: fd.get('ballScrap') ? Number(fd.get('ballScrap')) : null,
      cageSealScrap: fd.get('cageSealScrap') ? Number(fd.get('cageSealScrap')) : null,
      ringType: fd.get('ringType'),
      nextStation: fd.get('nextStation'),
      qtySent: fd.get('qtySent') ? Number(fd.get('qtySent')) : null,
      outDate: fd.get('outDate'),
      shiftOut: fd.get('shiftOut'),
      operator: fd.get('operator'),
      remark: fd.get('remark')
    });
  };

  const renderMoVariantHeader = () => (
    <div style={{marginBottom: '20px'}}>
      <div className="mo-variant-header" style={{display: 'flex', gap: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
        <div className="form-group" style={{flex: 1}}>
          <label style={{display: 'block', fontWeight: '600', marginBottom: '5px', color: '#334155'}}>MO Number</label>
          <input type="text" value={moNumber} onChange={(e) => setMoNumber(e.target.value)} onBlur={handleMoBlur} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
        </div>
        <div className="form-group" style={{flex: 1}}>
          <label style={{display: 'block', fontWeight: '600', marginBottom: '5px', color: '#334155'}}>Bearing Variant (Type)</label>
          {availableVariants.length > 0 ? (
            <select value={selectedVariant} onChange={handleVariantChange} style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required>
              <option value="">-- Select Variant --</option>
              {availableVariants.map(v => <option key={v.type} value={v.type}>{v.type}</option>)}
            </select>
          ) : (
            <input type="text" value={selectedVariant} onChange={(e) => setSelectedVariant(e.target.value)} placeholder="Manual Entry Override" style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required />
          )}
        </div>
        <div className="form-group" style={{flex: 1}}>
          <label style={{display: 'block', fontWeight: '600', marginBottom: '5px', color: '#334155'}}>Actual Production Qty</label>
          <input type="text" value={actualProductionQty > 0 ? actualProductionQty.toLocaleString() : '-'} readOnly style={{width: '100%', padding: '8px', background: '#e2e8f0', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 'bold'}} />
        </div>
      </div>

      {/* IN / OUT Toggle */}
      <div style={{display: 'flex', gap: '15px', marginTop: '15px', padding: '10px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '6px'}}>
        <label style={{fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer'}}>
          <input type="radio" value="IN" checked={entryMode === 'IN'} onChange={() => setEntryMode('IN')} />
          Log Receiving (IN)
        </label>
        <label style={{fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer'}}>
          <input type="radio" value="OUT" checked={entryMode === 'OUT'} onChange={() => setEntryMode('OUT')} />
          Log Dispatch (OUT)
        </label>
      </div>
    </div>
  );

  // SUMMARY MODAL LOGIC...
  const openSummaryModal = (mo) => {
    if (!moCache[mo]) return;
    const rawRows = moCache[mo];
    const uniqueVariants = [...new Set(rawRows.map(r => (r.type || '').trim()))].filter(Boolean);
    
    const variantBreakdown = uniqueVariants.map(baseVariant => {
      const prodQty = calculateProduction(rawRows, baseVariant);
      const prefixMatch = baseVariant.match(/^\d+/);
      const family = prefixMatch ? prefixMatch[0] : baseVariant;

      const accurateFilter = ledgers.accurate.filter(l => l.mo === mo && l.type.includes(family));
      const irRows = accurateFilter.filter(l => l.type.includes('IR') || l.type.includes('IM'));
      const orRows = accurateFilter.filter(l => l.type.includes('OR') || l.type.includes('OM'));

      return {
        variant: baseVariant,
        prodQty,
        irIn: irRows.reduce((sum, l) => sum + (l.qty_in || 0), 0),
        irOut: irRows.reduce((sum, l) => sum + (l.qty_sent || 0), 0),
        orIn: orRows.reduce((sum, l) => sum + (l.qty_in || 0), 0),
        orOut: orRows.reduce((sum, l) => sum + (l.qty_sent || 0), 0),
        cpsIn: ledgers.cps.filter(l => l.mo === mo && l.type === baseVariant).reduce((sum, l) => sum + (l.qty_in || 0), 0),
        cpsOut: ledgers.cps.filter(l => l.mo === mo && l.type === baseVariant).reduce((sum, l) => sum + (l.qty_sent || 0), 0),
        rwIn: ledgers.rework.filter(l => l.mo === mo && l.type === baseVariant).reduce((sum, l) => sum + (l.qty_in || 0), 0),
        rwOut: ledgers.rework.filter(l => l.mo === mo && l.type === baseVariant).reduce((sum, l) => sum + (l.qty_sent || 0), 0),
        disIn: ledgers.dismantling.filter(l => l.mo === mo && (l.type === baseVariant || l.type === family || baseVariant.includes(l.type))).reduce((sum, l) => sum + (l.qty_in || 0), 0),
        scrapSum: ledgers.dismantling.filter(l => l.mo === mo && (l.type === baseVariant || l.type === family || baseVariant.includes(l.type))).reduce((sum, l) => sum + (l.ball_scrap || 0) + (l.cage_seal_scrap || 0), 0)
      };
    });

    setSelectedMoDetail({ mo, breakdown: variantBreakdown });
  };

  const filteredMos = Object.keys(moCache).filter(mo => 
    mo.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      
      {/* Dropdown Options */}
      <datalist id="station-names">
        <option value="Accurate" />
        <option value="CPS" />
        <option value="Rework" />
        <option value="Vibration" />
        <option value="Dismantling" />
        <option value="Packaging" />
        <option value="Store" />
        <option value="Grinding" />
        <option value="Channel" />
      </datalist>

      <datalist id="activity-names">
        <option value="Inspection" />
        <option value="Polishing" />
        <option value="Washing" />
        <option value="Rust Removal" />
        <option value="Re-Assembly" />
        <option value="Sorting" />
      </datalist>

      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing Node</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px'}}>
          {['accurate', 'cps', 'rework', 'vibration'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>
              {tab.toUpperCase()}
            </button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>
            📊 SYSTEM FLOW SUMMARY
          </button>
        </div>
      </div>

      <div className="ac-content">
        {/* ================= ACCURATE OPERATING GRID ================= */}
        {activeTab === 'accurate' && (
          <form className="professional-form" onSubmit={handleAccurateSubmit}>
            {renderMoVariantHeader()}
            <div style={{display: 'grid', gridTemplateColumns: '1fr', gap: '20px'}}>
              {entryMode === 'IN' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Receiving Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>PC No.</label><input type="text" name="pc" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="station-names" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              {entryMode === 'OUT' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Dispatch Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>Next Station</label><input list="station-names" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                  </div>
                </fieldset>
              )}
            </div>
            <button type="submit" style={{marginTop:'20px', padding:'10px 20px', background:'#2563eb', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer', fontWeight:'bold'}}>Commit Record</button>
          </form>
        )}

        {/* ================= CPS OPERATING GRID ================= */}
        {activeTab === 'cps' && (
          <form className="professional-form" onSubmit={handleCpsSubmit}>
            {renderMoVariantHeader()}
            <div style={{display: 'grid', gridTemplateColumns: '1fr', gap: '20px'}}>
              {entryMode === 'IN' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Receiving Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>Item</label><input type="text" name="item" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>RC No.</label><input type="text" name="rcNo" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="station-names" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Channel</label><input type="text" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              {entryMode === 'OUT' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Dispatch Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>Next Station</label><input list="station-names" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                  </div>
                </fieldset>
              )}
            </div>
            <button type="submit" style={{marginTop:'20px', padding:'10px 20px', background:'#2563eb', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer', fontWeight:'bold'}}>Commit Record</button>
          </form>
        )}

        {/* ================= REWORK OPERATING GRID ================= */}
        {activeTab === 'rework' && (
          <form className="professional-form" onSubmit={handleReworkSubmit}>
            {renderMoVariantHeader()}
            <div style={{display: 'grid', gridTemplateColumns: '1fr', gap: '20px'}}>
              {entryMode === 'IN' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Receiving Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>Channel</label><input type="text" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineSegment" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="station-names" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Rework Activity</label><input list="activity-names" name="reworkActivity" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              {entryMode === 'OUT' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Dispatch Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>Next Station</label><input list="station-names" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>Operator</label><input type="text" name="operator" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Remark</label><input type="text" name="remark" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
            </div>
            <button type="submit" style={{marginTop:'20px', padding:'10px 20px', background:'#2563eb', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer', fontWeight:'bold'}}>Commit Record</button>
          </form>
        )}

        {/* ================= VIBRATION/DISMANTLING OPERATING GRID ================= */}
        {activeTab === 'vibration' && (
          <form className="professional-form" onSubmit={handleVibrationSubmit}>
            {renderMoVariantHeader()}
            <div style={{display: 'grid', gridTemplateColumns: '1fr', gap: '20px'}}>
              {entryMode === 'IN' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Receiving Details</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift In</label><select name="shiftIn" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>Channel</label><input type="text" name="channel" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Line Segment</label><input type="text" name="lineSegment" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Reason</label><input type="text" name="reason" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Material In From</label><input list="station-names" name="materialInFrom" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Activity</label><input list="activity-names" name="activity" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Ring Type</label><input type="text" name="ringType" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
              {entryMode === 'OUT' && (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}><legend style={{fontWeight: 'bold', padding: '0 5px'}}>Dispatch Details & Scrap</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px'}}>
                    <div><label>Ball Scrap</label><input type="number" name="ballScrap" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Cage/Seal Scrap</label><input type="number" name="cageSealScrap" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Next Station</label><input list="station-names" name="nextStation" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty Sent</label><input type="number" name="qtySent" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Shift Out</label><select name="shiftOut" style={{width:'100%', padding:'6px'}}><option></option><option>I</option><option>II</option><option>III</option></select></div>
                    <div><label>Operator</label><input type="text" name="operator" style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Remark</label><input type="text" name="remark" style={{width:'100%', padding:'6px'}}/></div>
                  </div>
                </fieldset>
              )}
            </div>
            <button type="submit" style={{marginTop:'20px', padding:'10px 20px', background:'#2563eb', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer', fontWeight:'bold'}}>Commit Record</button>
          </form>
        )}

        {/* ================= SUMMARY TRACKER REFERENCE CATALOG ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '20px', borderRadius: '8px', border: '1px solid #cbd5e1'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.3em', margin: 0, color: '#1e293b'}}>Active Master Orders (MO) Reference Index</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} style={{padding: '8px 12px', width: '320px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '0.95em'}} />
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
                  <tr key={mo} style={{borderBottom: '1px solid #e2e8f0'}} className="summary-row-hover">
                    <td style={{padding: '14px 12px', fontWeight: '700', color: '#1e40af'}}>{mo}</td>
                    <td style={{padding: '14px 12px', color: '#64748b'}}>{moCache[mo] ? moCache[mo].length : 0} Variant Matrices Compiled</td>
                    <td style={{padding: '14px 12px', textAlign: 'right'}}>
                      <button onClick={() => openSummaryModal(mo)} style={{padding: '7px 14px', background: '#0284c7', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: '600', fontSize: '0.9em'}}>
                        View Detailed Pipeline {"\u2192"}
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredMos.length === 0 && (
                  <tr>
                    <td colSpan="3" style={{padding: '30px', textAlign: 'center', color: '#94a3b8', fontWeight: '500'}}>No master production orders located matching query parameter.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ================= SUMMARY MODAL ================= */}
      {selectedMoDetail && (
        <div className="modal-backdrop" style={{position: 'fixed', top:0, left:0, width:'100vw', height:'100vh', background:'rgba(15, 23, 42, 0.6)', display:'flex', justifyContent:'center', alignItems:'center', zIndex: 1000, backdropFilter: 'blur(2px)'}}>
          <div className="modal-window" style={{background:'#fff', padding:'25px', borderRadius:'8px', width:'95%', maxWidth:'1500px', maxHeight:'85vh', overflowY:'auto', boxShadow:'0 20px 25px -5px rgba(0,0,0,0.15)'}}>
            
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', borderBottom:'2px solid #cbd5e1', paddingBottom:'15px', marginBottom:'20px'}}>
              <div>
                <h2 style={{margin: 0, fontSize: '1.4em', color: '#0f172a'}}>Cross-Department Flow Trace Analysis</h2>
                <p style={{margin: '4px 0 0 0', color: '#64748b', fontSize: '0.95em'}}>Target Master Order Vector Reference: <strong style={{color:'#1e40af'}}>{selectedMoDetail.mo}</strong></p>
              </div>
              <button onClick={() => setSelectedMoDetail(null)} style={{background:'#f1f5f9', border:'none', fontSize:'1.4em', cursor:'pointer', color:'#64748b', width:'36px', height:'36px', borderRadius:'4px', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:'bold'}}>{"\u00D7"}</button>
            </div>

            <div style={{overflowX: 'auto'}}>
              <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.88em', minWidth: '1200px'}}>
                <thead>
                  <tr style={{background: '#f8fafc', borderTop: '1px solid #cbd5e1'}}>
                    <th rowSpan="2" style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'left', color: '#334155'}}>Variant Model Specification</th>
                    <th rowSpan="2" style={{border: '1px solid #cbd5e1', padding: '12px', background: '#f0fdf4', color: '#166534', textAlign: 'center'}}>Actual Prod Qty</th>
                    <th colSpan="2" style={{border: '1px solid #cbd5e1', padding: '8px', background: '#eff6ff', color: '#1e40af', textAlign: 'center'}}>Channel (Accurate) - IR/IM</th>
                    <th colSpan="2" style={{border: '1px solid #cbd5e1', padding: '8px', background: '#f0f9ff', color: '#0369a1', textAlign: 'center'}}>Channel (Accurate) - OR/OM</th>
                    <th colSpan="2" style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fffbeb', color: '#9a3412', textAlign: 'center'}}>Assembly (CPS Center)</th>
                    <th colSpan="2" style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fdf4ff', color: '#86198f', textAlign: 'center'}}>Rework Segment</th>
                    <th colSpan="2" style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fef2f2', color: '#991b1b', textAlign: 'center'}}>Dismantling Area</th>
                  </tr>
                  <tr style={{background: '#f8fafc'}}>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#eff6ff', color: '#1e40af', textAlign: 'center'}}>Total In</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#eff6ff', color: '#1e40af', textAlign: 'center'}}>Total Out</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#f0f9ff', color: '#0369a1', textAlign: 'center'}}>Total In</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#f0f9ff', color: '#0369a1', textAlign: 'center'}}>Total Out</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fffbeb', color: '#9a3412', textAlign: 'center'}}>Total In</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fffbeb', color: '#9a3412', textAlign: 'center'}}>Total Out</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fdf4ff', color: '#86198f', textAlign: 'center'}}>Total In</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fdf4ff', color: '#86198f', textAlign: 'center'}}>Total Out</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fef2f2', color: '#991b1b', textAlign: 'center'}}>Total In</th>
                    <th style={{border: '1px solid #cbd5e1', padding: '8px', background: '#fee2e2', color: '#991b1b', textAlign: 'center'}}>Scrap Sum</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedMoDetail.breakdown.map((row, i) => (
                    <tr key={i} style={{borderBottom: '1px solid #e2e8f0'}} className="summary-modal-row">
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', fontWeight: '700', color: '#334155'}}>{row.variant}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', fontWeight: '700', color: '#16a34a', background: '#f0fdf4', textAlign: 'center'}}>{row.prodQty ? row.prodQty.toLocaleString() : 0}</td>
                      
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', background: '#f8fafc'}}>{row.irIn > 0 ? row.irIn.toLocaleString() : '-'}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', background: '#f8fafc'}}>{row.irOut > 0 ? row.irOut.toLocaleString() : '-'}</td>
                      
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center'}}>{row.orIn > 0 ? row.orIn.toLocaleString() : '-'}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center'}}>{row.orOut > 0 ? row.orOut.toLocaleString() : '-'}</td>
                      
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', background: '#f8fafc'}}>{row.cpsIn > 0 ? row.cpsIn.toLocaleString() : '-'}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', background: '#f8fafc'}}>{row.cpsOut > 0 ? row.cpsOut.toLocaleString() : '-'}</td>
                      
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center'}}>{row.rwIn > 0 ? row.rwIn.toLocaleString() : '-'}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center'}}>{row.rwOut > 0 ? row.rwOut.toLocaleString() : '-'}</td>
                      
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', background: '#fff5f5'}}>{row.disIn > 0 ? row.disIn.toLocaleString() : '-'}</td>
                      <td style={{border: '1px solid #cbd5e1', padding: '12px', textAlign: 'center', color: '#dc2626', fontWeight: '700', background: '#fee2e2'}}>{row.scrapSum > 0 ? row.scrapSum.toLocaleString() : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

          </div>
        </div>
      )}
    </div>
  );
};

export default Afterchannel;
