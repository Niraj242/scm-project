import React, { useState, useEffect } from 'react';
import './Afterchannel.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Afterchannel = () => {
  const [activeTab, setActiveTab] = useState('accurate');
  const [entryMode, setEntryMode] = useState('IN'); 
  const [ledgers, setLedgers] = useState({ accurate: [], cps: [], rework: [], dismantling: [], autopackaging: [], fps: [] });
  
  const [moNumber, setMoNumber] = useState('');
  const [selectedVariant, setSelectedVariant] = useState('');
  const [bearingFamily, setBearingFamily] = useState(''); 
  const [editingRecord, setEditingRecord] = useState(null);
  
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState('');
  const [expandedMOs, setExpandedMOs] = useState({});
  const [expandedVariants, setExpandedVariants] = useState({});

  // Scraps & Dispatches
  const [irScrapVal, setIrScrapVal] = useState('');
  const [orScrapVal, setOrScrapVal] = useState('');
  const [cageScrapVal, setCageScrapVal] = useState('');
  const [ballScrapVal, setBallScrapVal] = useState('');
  const [rollerScrapVal, setRollerScrapVal] = useState('');
  const [remarkVal, setRemarkVal] = useState('');
  
  const [irSentVal, setIrSentVal] = useState('');
  const [irStationVal, setIrStationVal] = useState('');
  const [orSentVal, setOrSentVal] = useState('');
  const [orStationVal, setOrStationVal] = useState('');
  const [cageSentVal, setCageSentVal] = useState('');
  const [cageStationVal, setCageStationVal] = useState('');
  const [rollerSentVal, setRollerSentVal] = useState('');
  const [rollerStationVal, setRollerStationVal] = useState('');

  useEffect(() => {
    fetchLedgers();
  }, []);

  const fetchLedgers = async () => {
    try {
      const res = await fetch(`${API}/api/afterchannel/summary_ledgers`);
      const json = await res.json();
      if (json.status === 'success' || json.data) {
        setLedgers({
          accurate: json.data?.accurate || [],
          cps: json.data?.cps || [],
          rework: json.data?.rework || [],
          dismantling: json.data?.dismantling || json.data?.vibration || [],
          autopackaging: json.data?.autopackaging || [],
          fps: json.data?.fps || []
        });
      }
    } catch (err) {
      console.error("Ledger Sync Failure:", err);
    }
  };

  const resetComponentScrapStates = () => {
    setIrScrapVal(''); setOrScrapVal(''); setCageScrapVal(''); setBallScrapVal(''); setRollerScrapVal(''); setRemarkVal('');
    setIrSentVal(''); setIrStationVal(''); setOrSentVal(''); setOrStationVal('');
    setCageSentVal(''); setCageStationVal(''); setRollerSentVal(''); setRollerStationVal('');
  };

  const handleFormSubmit = async (e, endpoint) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = {
      id: editingRecord ? editingRecord.id : undefined,
      mo: moNumber.toUpperCase(),
      bearing_type: selectedVariant.toUpperCase(),
      type: selectedVariant.toUpperCase(),
      bearingFamily: bearingFamily || null
    };

    const numFields = ['qtyIn', 'qtySent', 'qty_in', 'qty_sent', 'ballScrap', 'rollerScrap', 'cageScrap', 'irScrap', 'orScrap', 'irSent', 'orSent', 'cageSent', 'rollerSent'];

    for (let [key, value] of fd.entries()) {
      let finalValue = value;
      if (numFields.includes(key)) finalValue = (value !== '' && !isNaN(Number(value))) ? Number(value) : 0;
      else if (!value || value.trim() === '') finalValue = null;
      payload[key] = finalValue;
      
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
      if (snakeKey !== key) payload[snakeKey] = finalValue;
    }

    try {
      const targetEndpoint = endpoint === 'dismantling' ? 'vibration' : endpoint;
      const res = await fetch(`${API}/api/afterchannel/${targetEndpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      
      alert(editingRecord ? "Entry Updated Successfully!" : "Record Logged Successfully!");
      e.target.reset();
      setEditingRecord(null); resetComponentScrapStates();
      await fetchLedgers();
    } catch (err) { alert("Submission Error: " + err.message); }
  };

  const handleEdit = (record) => {
    setMoNumber(record.mo || ''); setSelectedVariant(record.type || record.bearing_type || '');
    setBearingFamily(record.bearing_family || record.bearingFamily || '');
    setEntryMode((record.qty_sent || record.qtySent) ? 'OUT' : 'IN');
    
    setIrScrapVal(record.ir_scrap ?? ''); setOrScrapVal(record.or_scrap ?? ''); setCageScrapVal(record.cage_scrap ?? '');
    setBallScrapVal(record.ball_scrap ?? ''); setRollerScrapVal(record.roller_scrap ?? ''); setRemarkVal(record.remark || '');
    
    setIrSentVal(record.ir_sent ?? ''); setIrStationVal(record.ir_station || '');
    setOrSentVal(record.or_sent ?? ''); setOrStationVal(record.or_station || '');
    setCageSentVal(record.cage_sent ?? ''); setCageStationVal(record.cage_station || '');
    setRollerSentVal(record.roller_sent ?? ''); setRollerStationVal(record.roller_station || '');

    setEditingRecord(record);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (id, tab) => {
    if(!window.confirm("Are you sure you want to delete this entry permanently?")) return;
    try {
      const endpoint = tab === 'dismantling' ? 'vibration' : tab;
      const res = await fetch(`${API}/api/afterchannel/${endpoint}/${id}`, { method: 'DELETE' });
      if(res.ok) { await fetchLedgers(); if(editingRecord && editingRecord.id === id) setEditingRecord(null); }
    } catch(err) { alert("Delete Error: " + err.message); }
  };

  const isScrapStation = (val) => String(val || '').trim().toLowerCase().includes('scrap');

  // --- CORE SUMMARY HIERARCHY LOGIC ---
  const createEmptyFlowObject = () => ({
    accIn: 0, accOut: 0, cpsIn: 0, cpsOut: 0, rwIn: 0, rwOut: 0,
    disIn: 0, disOut: 0, apIn: 0, apOut: 0, fpsIn: 0, fpsOut: 0,
    irScrap: 0, orScrap: 0, cageScrap: 0, ballScrap: 0, totalScrap: 0, records: []
  });

  const addFlowCounts = (node, r) => {
    const dept = r._dept;
    if (dept === 'accurate') { if (r.qty_in) node.accIn += Number(r.qty_in); if (r.qty_sent) node.accOut += Number(r.qty_sent); }
    else if (dept === 'cps') { if (r.qty_in) node.cpsIn += Number(r.qty_in); if (r.qty_sent) node.cpsOut += Number(r.qty_sent); }
    else if (dept === 'rework') { if (r.qty_in) node.rwIn += Number(r.qty_in); if (r.qty_sent) node.rwOut += Number(r.qty_sent); }
    else if (dept === 'dismantling') {
        if (r.qty_in) node.disIn += Number(r.qty_in);
        if (r.qty_sent) node.disOut += Number(r.qty_sent);
        if (r.ir_sent) node.disOut += Number(r.ir_sent);
        if (r.or_sent) node.disOut += Number(r.or_sent);
        if (r.cage_sent) node.disOut += Number(r.cage_sent);
        if (r.roller_sent) node.disOut += Number(r.roller_sent);
        node.irScrap += (Number(r.ir_scrap) || 0); node.orScrap += (Number(r.or_scrap) || 0);
        node.cageScrap += (Number(r.cage_scrap) || 0); node.ballScrap += (Number(r.ball_scrap) || 0) + (Number(r.roller_scrap) || 0);
        node.totalScrap = node.irScrap + node.orScrap + node.cageScrap + node.ballScrap;
    }
    else if (dept === 'autopackaging') { if (r.qty_in) node.apIn += Number(r.qty_in); if (r.qty_sent) node.apOut += Number(r.qty_sent); }
    else if (dept === 'fps') { if (r.qty_in) node.fpsIn += Number(r.qty_in); if (r.qty_sent) node.fpsOut += Number(r.qty_sent); }
  };

  const generateSummaryData = () => {
    const safeLedgers = { accurate: ledgers.accurate||[], cps: ledgers.cps||[], rework: ledgers.rework||[], dismantling: ledgers.dismantling||ledgers.vibration||[], autopackaging: ledgers.autopackaging||[], fps: ledgers.fps||[] };
    const allLists = [
      ...safeLedgers.accurate.map(r=>({...r, _dept:'accurate'})), ...safeLedgers.cps.map(r=>({...r, _dept:'cps'})), 
      ...safeLedgers.rework.map(r=>({...r, _dept:'rework'})), ...safeLedgers.dismantling.map(r=>({...r, _dept:'dismantling'})), 
      ...safeLedgers.autopackaging.map(r=>({...r, _dept:'autopackaging'})), ...safeLedgers.fps.map(r=>({...r, _dept:'fps'}))
    ];
    
    const summaryMap = {};
    allLists.forEach(item => {
      if (!item.mo) return;
      const mo = item.mo.toUpperCase();
      let variant = (item.bearing_type || item.type || item.item_type || '').toUpperCase();
      if (!variant || variant === 'DGBB' || variant === 'TRB') variant = 'FAMILY / OVERALL';

      if (!summaryMap[mo]) summaryMap[mo] = { mo, totals: createEmptyFlowObject(), variants: {} };
      if (!summaryMap[mo].variants[variant]) summaryMap[mo].variants[variant] = createEmptyFlowObject();

      addFlowCounts(summaryMap[mo].variants[variant], item);
      addFlowCounts(summaryMap[mo].totals, item);
      summaryMap[mo].variants[variant].records.push(item);
    });

    let result = Object.values(summaryMap).sort((a, b) => a.mo.localeCompare(b.mo));
    if (ledgerSearchQuery.trim()) result = result.filter(item => item.mo.includes(ledgerSearchQuery.toUpperCase()));
    return result;
  };

  const renderMoDispatchDetails = (records) => {
    const outRecs = records.filter(r => r.qty_sent > 0 || r.ir_sent > 0 || r.or_sent > 0 || r.cage_sent > 0 || r.roller_sent > 0 || r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0);
    if (outRecs.length === 0) return <div style={{padding: '10px', color: '#64748b', fontStyle: 'italic'}}>No dispatch/scrap events recorded here yet.</div>;
    const grouped = outRecs.reduce((acc, curr) => { if(!acc[curr._dept]) acc[curr._dept] = []; acc[curr._dept].push(curr); return acc; }, {});

    return (
      <div style={{display: 'flex', gap: '20px', flexWrap: 'wrap', padding: '15px', background: '#f8fafc', borderBottom: '2px solid #cbd5e1', boxShadow: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)'}}>
        {Object.keys(grouped).map(dept => (
          <div key={dept} style={{flex: '1 1 250px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px'}}>
            <h4 style={{margin: '0 0 10px 0', color: '#0f172a', borderBottom: '1px solid #e2e8f0', paddingBottom: '5px', textTransform:'uppercase', fontSize:'13px'}}>{dept} Activity</h4>
            <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
              {grouped[dept].map((r, i) => (
                <div key={i} style={{fontSize: '0.85em', background: '#f1f5f9', padding: '8px', borderRadius: '4px'}}>
                  {r.qty_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.qty_sent}</strong> sent to <strong>{r.next_station || 'N/A'}</strong></div>}
                  {r.ir_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.ir_sent} IR</strong> sent to <strong>{r.ir_station || 'N/A'}</strong></div>}
                  {r.or_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.or_sent} OR</strong> sent to <strong>{r.or_station || 'N/A'}</strong></div>}
                  {r.cage_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.cage_sent} Cage</strong> sent to <strong>{r.cage_station || 'N/A'}</strong></div>}
                  {r.roller_sent > 0 && <div><strong style={{color: '#2563eb'}}>{r.roller_sent} Roller/Ball</strong> sent to <strong>{r.roller_station || 'N/A'}</strong></div>}
                  {(r.ir_scrap > 0 || r.or_scrap > 0 || r.cage_scrap > 0 || r.ball_scrap > 0 || r.roller_scrap > 0) && (
                      <div style={{color: '#dc2626', marginTop: '4px'}}>
                          Scrap: {[r.ir_scrap && `${r.ir_scrap} IR`, r.or_scrap && `${r.or_scrap} OR`, r.cage_scrap && `${r.cage_scrap} Cage`, (r.ball_scrap||r.roller_scrap) && `${r.ball_scrap||r.roller_scrap} Ball/Rollers`].filter(Boolean).join(', ')}
                      </div>
                  )}
                  <span style={{color: '#64748b'}}>On: {r.out_date || r.outDate} | Shift: {r.shift_out}</span>
                  {r.remark && <div style={{color: '#b45309', marginTop: '4px', fontStyle: 'italic'}}>"{r.remark}"</div>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderDepartmentLedger = (deptKey, deptName) => {
    const records = (ledgers[deptKey] || []).filter(l => {
      const search = ledgerSearchQuery.toUpperCase();
      return (l.mo || '').toUpperCase().includes(search) || (l.bearing_type || l.type || l.item_type || '').toUpperCase().includes(search);
    });
    if (records.length === 0) return <div style={{marginTop: '30px', padding: '20px', textAlign: 'center', background: '#f8fafc', color: '#64748b'}}>No entries found.</div>;
    return (
      <div style={{marginTop: '30px', background: '#fff', borderRadius: '8px', border: '1px solid #cbd5e1', overflow: 'hidden'}}>
        <div style={{background: '#0f172a', padding: '15px', color: '#fff', fontWeight: 'bold'}}>{deptName} - Activity Log</div>
        <div style={{overflowX: 'auto'}}>
          <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9em'}}>
            <thead>
              <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                <th style={{padding: '10px'}}>MO</th><th style={{padding: '10px'}}>Variant</th><th style={{padding: '10px'}}>Date IN</th><th style={{padding: '10px', background: '#eff6ff'}}>Qty IN</th><th style={{padding: '10px'}}>Date OUT</th><th style={{padding: '10px'}}>Next Station</th><th style={{padding: '10px', background: '#fffbeb'}}>Qty OUT</th><th style={{padding: '10px'}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i} style={{borderBottom: '1px solid #e2e8f0', background: i%2===0?'#fff':'#f8fafc'}}>
                  <td style={{padding: '10px', fontWeight: 'bold'}}>{r.mo || '-'}</td><td style={{padding: '10px'}}>{r.bearing_type || r.type || r.item_type || '-'}</td><td style={{padding: '10px'}}>{r.in_date || r.inDate || '-'}</td><td style={{padding: '10px', fontWeight: 'bold', color: '#1d4ed8'}}>{r.qty_in || r.qtyIn || '-'}</td><td style={{padding: '10px'}}>{r.out_date || r.outDate || '-'}</td><td style={{padding: '10px'}}>{r.next_station || r.nextStation || '-'}</td><td style={{padding: '10px', fontWeight: 'bold', color: '#b45309'}}>{r.qty_sent || r.qtySent || r.ir_sent || '-'}</td>
                  <td style={{padding: '10px'}}>
                    <button type="button" onClick={() => handleEdit(r)} style={{marginRight: '8px', cursor: 'pointer', border: 'none', background: 'none'}}>✏️</button>
                    <button type="button" onClick={() => handleDelete(r.id, deptKey)} style={{cursor: 'pointer', border: 'none', background: 'none'}}>🗑️</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="afterchannel-container" style={{padding: '20px', fontFamily: 'sans-serif'}}>
      <datalist id="depts-list"><option value="Accurate" /><option value="CPS" /><option value="Rework" /><option value="Dismantling" /><option value="Autopackaging" /><option value="FPS" /><option value="Scrap" /></datalist>
      
      <div className="ac-header" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #cbd5e1', paddingBottom: '10px'}}>
        <h1 style={{fontSize: '1.6em', color: '#0f172a'}}>Afterchannel Processing</h1>
        <div className="tab-buttons" style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
          {['accurate', 'cps', 'rework', 'dismantling', 'autopackaging', 'fps'].map(tab => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => {setActiveTab(tab); setEditingRecord(null); setBearingFamily(''); resetComponentScrapStates();}} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === tab ? '#0f172a' : '#e2e8f0', color: activeTab === tab ? '#fff' : '#000', border: 'none', borderRadius: '4px', fontWeight: '600'}}>{tab.toUpperCase()}</button>
          ))}
          <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')} style={{padding: '10px 15px', cursor: 'pointer', background: activeTab === 'summary' ? '#16a34a' : '#bbf7d0', color: activeTab === 'summary' ? '#fff' : '#14532d', border: 'none', borderRadius: '4px', fontWeight: 'bold'}}>📊 SUMMARY</button>
        </div>
      </div>

      {activeTab !== 'summary' && (
        <div style={{marginBottom: '20px', background: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
          <div style={{display: 'flex', gap: '20px'}}>
            <div style={{flex: 1}}><label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>Variant / Item Type</label><input value={selectedVariant} onChange={(e)=>setSelectedVariant(e.target.value)} placeholder="Type Variant..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required /></div>
            <div style={{flex: 1}}><label style={{display: 'block', fontWeight: '600', marginBottom: '5px'}}>MO Number</label><input value={moNumber} onChange={(e) => setMoNumber(e.target.value)} placeholder="Type MO..." style={{width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px'}} required /></div>
          </div>
          <div style={{display: 'flex', gap: '20px', marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #cbd5e1'}}>
            <button type="button" onClick={() => setEntryMode('IN')} style={{padding: '8px 20px', background: entryMode === 'IN' ? '#2563eb' : '#fff', color: entryMode === 'IN' ? '#fff' : '#2563eb', border: '2px solid #2563eb', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📥 LOG IN (Receiving)</button>
            <button type="button" onClick={() => setEntryMode('OUT')} style={{padding: '8px 20px', background: entryMode === 'OUT' ? '#ea580c' : '#fff', color: entryMode === 'OUT' ? '#fff' : '#ea580c', border: '2px solid #ea580c', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer'}}>📤 LOG OUT (Dispatch)</button>
            {editingRecord && <button type="button" onClick={() => { setEditingRecord(null); setMoNumber(''); setSelectedVariant(''); setBearingFamily(''); resetComponentScrapStates(); }} style={{padding: '8px 20px', background: '#64748b', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', marginLeft: 'auto'}}>Cancel Edit</button>}
          </div>
        </div>
      )}

      <div className="ac-content">
        {/* OTHER TABS SIMPLIFIED FOR BREVITY, DISMANTLING FULLY EXPANDED */}
        {['accurate', 'cps', 'rework', 'autopackaging', 'fps'].includes(activeTab) && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, activeTab)}>
              <fieldset style={{border: `1px solid ${entryMode==='IN'?'#cbd5e1':'#ea580c'}`, padding: '15px', borderRadius: '6px'}}>
                <legend style={{fontWeight: 'bold', color: entryMode==='IN'?'#000':'#ea580c'}}>{activeTab.toUpperCase()} - {entryMode==='IN' ? 'Receiving Log' : 'Dispatch Log'}</legend>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    {entryMode === 'IN' ? (
                      <>
                        <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                        <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                        <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        {activeTab === 'fps' && <div><label>Customer Order</label><input type="text" name="customerOrder" defaultValue={editingRecord?.customer_order || ''} style={{width:'100%', padding:'6px'}}/></div>}
                      </>
                    ) : (
                      <>
                        <div><label>Next Station</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station || ''} style={{width:'100%', padding:'6px'}}/></div>
                        <div><label>Qty Sent</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                        <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                      </>
                    )}
                </div>
              </fieldset>
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger(activeTab, activeTab.toUpperCase())}
          </div>
        )}

        {/* ================= DISMANTLING TAB (MULTI-DISPATCH FEATURE) ================= */}
        {activeTab === 'dismantling' && (
          <div>
            <form key={editingRecord ? editingRecord.id : 'new'} onSubmit={(e) => handleFormSubmit(e, 'dismantling')}>
              <div style={{marginBottom: '15px', padding: '12px', background: '#f1f5f9', borderRadius: '6px', border: '1px solid #cbd5e1', display: 'flex', gap: '10px'}}>
                <label style={{fontWeight: 'bold'}}>Bearing Family:</label>
                <select name="bearingFamily" value={bearingFamily} onChange={(e) => setBearingFamily(e.target.value)} style={{padding: '6px'}} required><option></option><option value="DGBB">DGBB</option><option value="TRB">TRB</option></select>
              </div>

              {entryMode === 'IN' ? (
                <fieldset style={{border: '1px solid #cbd5e1', padding: '15px', borderRadius: '6px'}}>
                  <legend style={{fontWeight: 'bold'}}>Dismantling - Receiving Log</legend>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>In Date</label><input type="date" name="inDate" defaultValue={editingRecord?.in_date || ''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift In</label><select name="shiftIn" defaultValue={editingRecord?.shift_in || ''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                    <div><label>Material In From</label><input list="depts-list" name="materialInFrom" defaultValue={editingRecord?.material_in_from || ''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Qty In</label><input type="number" name="qtyIn" defaultValue={editingRecord?.qty_in || ''} style={{width:'100%', padding:'6px'}} required/></div>
                  </div>
                </fieldset>
              ) : (
                <fieldset style={{border: '1px solid #ea580c', padding: '15px', borderRadius: '6px', background: '#fff7ed'}}>
                  <legend style={{fontWeight: 'bold', color: '#ea580c'}}>Dismantling - Dispatch Log</legend>
                  
                  {/* MULTI COMPONENT SPLITTER */}
                  <div style={{background: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #cbd5e1', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 12px 0', color: '#1e3a8a', borderBottom: '1px solid #e2e8f0', paddingBottom: '6px'}}>Specific Component Outbound Destinations</h4>
                    
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>IR Sent Qty</label><input type="number" name="irSent" value={irSentVal} onChange={e=>setIrSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>IR Next Station</label><input list="depts-list" name="irStation" value={irStationVal} onChange={e=>setIrStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>OR Sent Qty</label><input type="number" name="orSent" value={orSentVal} onChange={e=>setOrSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>OR Next Station</label><input list="depts-list" name="orStation" value={orStationVal} onChange={e=>setOrStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px', marginBottom: '10px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>Cage Sent Qty</label><input type="number" name="cageSent" value={cageSentVal} onChange={e=>setCageSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>Cage Next Station</label><input list="depts-list" name="cageStation" value={cageStationVal} onChange={e=>setCageStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px'}}>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Sent Qty</label><input type="number" name="rollerSent" value={rollerSentVal} onChange={e=>setRollerSentVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em', fontWeight:'600'}}>{bearingFamily === 'TRB' ? 'Roller' : 'Ball'} Next Station</label><input list="depts-list" name="rollerStation" value={rollerStationVal} onChange={e=>setRollerStationVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                  </div>

                  <div style={{background: '#f8fafc', padding: '15px', borderRadius: '6px', border: '1px dashed #ef4444', marginBottom: '20px'}}>
                    <h4 style={{margin: '0 0 12px 0', color: '#dc2626'}}>Component Scrap Entry</h4>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px'}}>
                      <div><label style={{fontSize:'0.85em'}}>IR Scrap</label><input type="number" name="irScrap" value={irScrapVal} onChange={e=>setIrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>OR Scrap</label><input type="number" name="orScrap" value={orScrapVal} onChange={e=>setOrScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>Cage Scrap</label><input type="number" name="cageScrap" value={cageScrapVal} onChange={e=>setCageScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                      <div><label style={{fontSize:'0.85em'}}>Ball/Roll Scrap</label><input type="number" name="ballScrap" value={ballScrapVal} onChange={e=>setBallScrapVal(e.target.value)} style={{width:'100%', padding:'5px'}} /></div>
                    </div>
                  </div>

                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px'}}>
                    <div><label>Overall Qty Sent (Optional)</label><input type="number" name="qtySent" defaultValue={editingRecord?.qty_sent||''} style={{width:'100%', padding:'6px'}}/></div>
                    <div><label>Next Station (Overall)</label><input list="depts-list" name="nextStation" defaultValue={editingRecord?.next_station||''} style={{width:'100%', padding:'6px'}}/></div>
                    <div style={{gridColumn: 'span 1'}}><label>Remarks</label><input type="text" name="remark" value={remarkVal} onChange={e=>setRemarkVal(e.target.value)} style={{width:'100%', padding:'6px'}} placeholder="General remarks..."/></div>
                    <div><label>Out Date</label><input type="date" name="outDate" defaultValue={editingRecord?.out_date||''} style={{width:'100%', padding:'6px'}} required/></div>
                    <div><label>Shift Out</label><select name="shiftOut" defaultValue={editingRecord?.shift_out||''} style={{width:'100%', padding:'6px'}}><option></option><option>1</option><option>2</option><option>3</option></select></div>
                  </div>
                </fieldset>
              )}
              <button type="submit" style={{marginTop:'15px', padding:'10px 25px', background: entryMode==='IN'?'#2563eb':'#ea580c', color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer'}}>{editingRecord ? 'Update Entry' : 'Save Entry'}</button>
            </form>
            {renderDepartmentLedger('dismantling', 'Dismantling Processing')}
          </div>
        )}

        {/* ================= SUMMARY VIEW ================= */}
        {activeTab === 'summary' && (
          <div className="summary-view" style={{background: '#fff', padding: '25px', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', border: '1px solid #e2e8f0'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px'}}>
              <h2 style={{fontSize: '1.4em', margin: 0, color: '#0f172a', fontWeight: 'bold'}}>MO Variant Flow Hierarchy</h2>
              <input type="text" placeholder="Search Master Order (MO)..." value={ledgerSearchQuery} onChange={(e) => setLedgerSearchQuery(e.target.value)} style={{padding: '10px 15px', width: '350px', border: '2px solid #cbd5e1', borderRadius: '6px', outline: 'none'}} />
            </div>

            <div style={{overflowX: 'auto'}}>
              <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82em'}}>
                <thead>
                  <tr style={{background: '#f1f5f9', borderBottom: '2px solid #cbd5e1'}}>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', color: '#0f172a', minWidth: '180px'}}>Master Order / Variant</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rw IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Rw OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Dism OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>CPS OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Acc OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>Pkg OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1'}}>FPS IN</th><th style={{padding: '10px', border: '1px solid #cbd5e1'}}>FPS OUT</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>IR Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>OR Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Cg Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fee2e2'}}>Rl Scrp</th>
                    <th style={{padding: '10px', border: '1px solid #cbd5e1', background:'#fca5a5'}}>Tot Scrp</th>
                  </tr>
                </thead>
                <tbody>
                  {generateSummaryData().map(moData => (
                    <React.Fragment key={moData.mo}>
                      {/* LEVEL 0: MO ROW */}
                      <tr onClick={() => setExpandedMOs(p => ({...p, [moData.mo]: !p[moData.mo]}))} style={{cursor: 'pointer', background: expandedMOs[moData.mo] ? '#e2e8f0' : '#f8fafc', fontWeight: 'bold', color: '#1e293b'}}>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{expandedMOs[moData.mo] ? '▼' : '▶'} {moData.mo}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.rwIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.rwOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.disIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.disOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.cpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.cpsOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.accIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.accOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.apIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.apOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.fpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{moData.totals.fpsOut || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.irScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.orScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.cageScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{moData.totals.ballScrap || '-'}</td>
                        <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fee2e2', color:'#b91c1c'}}>{moData.totals.totalScrap || '-'}</td>
                      </tr>

                      {expandedMOs[moData.mo] && Object.entries(moData.variants).map(([variant, vData]) => {
                        const vKey = `${moData.mo}-${variant}`;
                        return (
                          <React.Fragment key={variant}>
                            {/* LEVEL 1: VARIANT ROW */}
                            <tr onClick={() => setExpandedVariants(p => ({...p, [vKey]: !p[vKey]}))} style={{cursor: 'pointer', background: '#ffffff', color: '#334155'}}>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px 10px 10px 25px', borderLeft: '4px solid #3b82f6', fontWeight: 'bold'}}>{expandedVariants[vKey] ? '▼' : '▶'} {variant}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.rwIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.rwOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.disIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.disOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.cpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.cpsOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.accIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.accOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.apIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.apOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.fpsIn || '-'}</td><td style={{border: '1px solid #cbd5e1', padding: '10px'}}>{vData.fpsOut || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.irScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.orScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.cageScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fef2f2', color:'#991b1b'}}>{vData.ballScrap || '-'}</td>
                              <td style={{border: '1px solid #cbd5e1', padding: '10px', background:'#fee2e2', color:'#b91c1c'}}>{vData.totalScrap || '-'}</td>
                            </tr>
                            
                            {/* LEVEL 2: COMPONENT DISPATCH DETAILS */}
                            {expandedVariants[vKey] && (
                              <tr><td colSpan="18" style={{border: '1px solid #cbd5e1', padding: 0}}>{renderMoDispatchDetails(vData.records)}</td></tr>
                            )}
                          </React.Fragment>
                        );
                      })}

                      {/* MO BOTTOM TOTAL ROW */}
                      {expandedMOs[moData.mo] && (
                        <tr style={{background: '#cbd5e1', fontWeight: 'bold', borderTop: '2px solid #64748b', color: '#0f172a'}}>
                          <td style={{border: '1px solid #94a3b8', padding: '10px', textAlign: 'right'}}>TOTAL FOR {moData.mo}:</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.rwIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.rwOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.disIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.disOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.cpsIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.cpsOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.accIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.accOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.apIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.apOut || '-'}</td>
                          <td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.fpsIn || '-'}</td><td style={{border: '1px solid #94a3b8', padding: '10px'}}>{moData.totals.fpsOut || '-'}</td>
                          <td colSpan="5" style={{border: '1px solid #94a3b8', padding: '10px', textAlign: 'center', background: '#fca5a5'}}>Grand Total Scrap: {moData.totals.totalScrap}</td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Afterchannel;
